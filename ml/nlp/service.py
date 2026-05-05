import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import asyncpg
import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pgvector.asyncpg import register_vector
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

load_dotenv()

MODEL_NAME = "intfloat/multilingual-e5-base"
EMBEDDING_DIM = 768

_SQL_FILE = (
    Path(__file__).parent.parent.parent / "backend" / "db" / "queries" / "hybrid_search.sql"
)
_INLINE_SQL = """
WITH semantic_results AS (
    SELECT id,
           ROW_NUMBER() OVER (ORDER BY embedding <=> $1::vector) AS rank,
           1.0 - (embedding <=> $1::vector) AS semantic_score
    FROM movies
    WHERE embedding IS NOT NULL
      AND ($4::int IS NULL OR year >= $4)
      AND ($5::int IS NULL OR year <= $5)
      AND ($6::float IS NULL OR avg_rating >= $6)
    ORDER BY embedding <=> $1::vector
    LIMIT 250
),
text_results AS (
    SELECT m.id,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(m.search_vector, query, 32) DESC) AS rank,
           ts_rank_cd(m.search_vector, query, 32) AS text_score
    FROM movies m, plainto_tsquery('english', $2) AS query
    WHERE m.search_vector @@ query
      AND ($4::int IS NULL OR m.year >= $4)
      AND ($5::int IS NULL OR m.year <= $5)
      AND ($6::float IS NULL OR m.avg_rating >= $6)
    ORDER BY text_score DESC
    LIMIT 250
),
rrf AS (
    SELECT COALESCE(s.id, t.id) AS movie_id,
           COALESCE(1.0 / (60.0 + s.rank), 0.0) * 0.6
             + COALESCE(1.0 / (60.0 + t.rank), 0.0) * 0.4 AS rrf_score,
           COALESCE(s.semantic_score, 0.0) AS semantic_score,
           COALESCE(t.text_score, 0.0) AS text_score
    FROM semantic_results s
    FULL OUTER JOIN text_results t ON s.id = t.id
)
SELECT m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
       r.rrf_score, r.semantic_score, r.text_score,
       ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name ORDER BY g.name), NULL) AS genres
FROM rrf r
JOIN movies m ON m.id = r.movie_id
LEFT JOIN movie_genres mg ON mg.movie_id = m.id
LEFT JOIN genres g ON g.id = mg.genre_id
GROUP BY m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
         r.rrf_score, r.semantic_score, r.text_score
ORDER BY r.rrf_score DESC
LIMIT $3 OFFSET $7
"""
HYBRID_SEARCH_SQL = _SQL_FILE.read_text() if _SQL_FILE.exists() else _INLINE_SQL

_model: SentenceTransformer | None = None
_pool: asyncpg.Pool | None = None


async def _init_vector(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


_vocab: list[str] = []
_vocab_set: set[str] = set()


async def _load_vocabulary(pool: asyncpg.Pool) -> None:
    """Build a de-duped set of lowercase words from all movie titles + a small
    slice of descriptions. Used by the query-typo corrector before search.
    Words shorter than 4 chars are skipped (no useful fuzzy correction)."""
    global _vocab, _vocab_set
    import re
    rows = await pool.fetch("SELECT title, COALESCE(description, '') AS desc FROM movies")
    seen: set[str] = set()
    for r in rows:
        for field in (r["title"], r["desc"][:200]):
            for w in re.findall(r"[A-Za-z]{4,}", field or ""):
                seen.add(w.lower())
    _vocab = sorted(seen)
    _vocab_set = seen


COMMON_WORDS = {
    "the", "and", "a", "an", "of", "in", "on", "at", "to", "for", "with",
    "from", "by", "about", "into", "onto", "that", "this", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "should", "could", "may", "might",
    "not", "no", "nor", "so", "but", "or", "if", "as", "than",
    "fight", "fights", "against", "film", "movie", "story", "man", "men",
    "boy", "girl", "woman", "world", "life",
}


_CYRILLIC_RE = None


def _has_cyrillic(s: str) -> bool:
    global _CYRILLIC_RE
    if _CYRILLIC_RE is None:
        import re
        _CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
    return bool(_CYRILLIC_RE.search(s))


def _translate_to_english(query: str) -> str:
    """Translate non-English queries to English via Google Translate.
    Catches all errors — on failure we just return the original query."""
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source="auto", target="en").translate(query) or query
    except Exception as e:
        structlog.get_logger().warning("translate_failed", error=str(e))
        return query


def _correct_query(query: str) -> str:
    """Replace likely-misspelled query words with their closest vocabulary
    match. Leaves short/common/in-vocab words untouched. Costs O(|vocab|) per
    replacement but fast enough with rapidfuzz on ~30k words."""
    if not _vocab:
        return query
    from rapidfuzz import process, fuzz
    import re
    tokens = re.findall(r"\S+", query)
    out: list[str] = []
    for tok in tokens:
        w = tok.lower()
        core = re.sub(r"[^a-z0-9]", "", w)
        if len(core) < 4 or core in COMMON_WORDS or core in _vocab_set:
            out.append(tok)
            continue
        match = process.extractOne(core, _vocab, scorer=fuzz.ratio, score_cutoff=82)
        if match:
            out.append(match[0])
        else:
            out.append(tok)
    return " ".join(out)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _model, _pool
    logger = structlog.get_logger()
    logger.info("nlp_service_starting", model=MODEL_NAME)

    loop = asyncio.get_running_loop()
    _model = await loop.run_in_executor(None, SentenceTransformer, MODEL_NAME)
    await loop.run_in_executor(
        None,
        lambda: _model.encode(
            ["warmup sentence"], normalize_embeddings=True, show_progress_bar=False
        ),
    )
    logger.info("sentence_transformer_loaded", embedding_dim=EMBEDDING_DIM)

    postgres_url = os.environ["POSTGRES_URL"].replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    _pool = await asyncpg.create_pool(
        postgres_url,
        min_size=3,
        max_size=10,
        command_timeout=10,
        init=_init_vector,
    )
    await _load_vocabulary(_pool)
    logger.info("nlp_service_ready", vocab_size=len(_vocab))
    yield

    await _pool.close()
    logger.info("nlp_service_stopped")


app = FastAPI(title="MovieMatch NLP Service", version="1.0.0", lifespan=lifespan)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=200)
    year_from: int | None = Field(None, ge=1900, le=2030)
    year_to: int | None = Field(None, ge=1900, le=2030)
    min_rating: float | None = Field(None, ge=1.0, le=5.0)


class SearchResult(BaseModel):
    movie_id: int
    title: str
    year: int | None
    avg_rating: float | None
    poster_path: str | None
    genres: list[str]
    rrf_score: float
    semantic_score: float
    text_score: float


@app.post("/search", response_model=list[SearchResult])
async def search(req: SearchRequest) -> list[SearchResult]:
    if _model is None or _pool is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    start = time.perf_counter()
    # Multilingual embedding model handles Russian / other scripts natively,
    # so no translate step. We still spell-correct Latin-script typos against
    # the corpus vocabulary; Cyrillic queries fall through as-is.
    effective_query = _correct_query(req.query) if not _has_cyrillic(req.query) else req.query
    if effective_query != req.query:
        structlog.get_logger().info(
            "query_autocorrect", orig=req.query, corrected=effective_query
        )

    loop = asyncio.get_running_loop()
    # E5 requires "query: " prefix so the model knows this is a query, not a
    # passage (asymmetric retrieval setup).
    prefixed = f"query: {effective_query}"
    query_embedding = await loop.run_in_executor(
        None,
        lambda: _model.encode(
            [prefixed], normalize_embeddings=True, show_progress_bar=False
        )[0],
    )

    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            HYBRID_SEARCH_SQL,
            query_embedding,
            effective_query,
            req.limit,
            req.year_from,
            req.year_to,
            req.min_rating,
            req.offset,
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    structlog.get_logger().info(
        "search_complete",
        query_preview=req.query[:50],
        results=len(rows),
        latency_ms=latency_ms,
    )

    return [
        SearchResult(
            movie_id=r["id"],
            title=r["title"],
            year=r["year"],
            avg_rating=float(r["avg_rating"]) if r["avg_rating"] is not None else None,
            poster_path=r["poster_path"],
            genres=list(r["genres"] or []),
            rrf_score=float(r["rrf_score"]),
            semantic_score=float(r["semantic_score"]),
            text_score=float(r["text_score"]),
        )
        for r in rows
    ]


@app.post("/reindex")
async def trigger_reindex(force: bool = False) -> dict[str, object]:
    if _model is None or _pool is None:
        raise HTTPException(status_code=503, detail="Not ready")
    asyncio.create_task(_do_reindex(force))
    return {"status": "started", "force": force}


async def _do_reindex(force: bool) -> None:
    from indexer import index_all_movies

    await index_all_movies(model=_model, pool=_pool, force=force)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "embedding_dim": EMBEDDING_DIM,
        "db_connected": _pool is not None,
    }
