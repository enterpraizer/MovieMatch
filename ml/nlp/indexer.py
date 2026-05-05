import argparse
import asyncio
import os
import time
from typing import Any

import asyncpg
from dotenv import load_dotenv
from pgvector.asyncpg import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv()

MODEL_NAME = "intfloat/multilingual-e5-base"
BATCH_SIZE = 256

FETCH_ALL = """
SELECT m.id, m.title, m.year, m.description,
       ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres,
       ARRAY_AGG(p.name) FILTER (WHERE mc.role = 'director') AS directors,
       ARRAY_AGG(p.name ORDER BY mc.order_index)
         FILTER (WHERE mc.role = 'actor') AS actors
FROM movies m
LEFT JOIN movie_genres mg ON mg.movie_id = m.id
LEFT JOIN genres g ON g.id = mg.genre_id
LEFT JOIN movie_credits mc ON mc.movie_id = m.id
LEFT JOIN people p ON p.id = mc.person_id
GROUP BY m.id
ORDER BY m.id
"""

FETCH_UNINDEXED = """
SELECT m.id, m.title, m.year, m.description,
       ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
FROM movies m
LEFT JOIN movie_genres mg ON mg.movie_id = m.id
LEFT JOIN genres g ON g.id = mg.genre_id
WHERE m.embedding IS NULL
GROUP BY m.id
ORDER BY m.id
"""


def build_document(movie: dict[str, Any]) -> str:
    parts = [
        movie.get("title") or "",
        f"({movie['year']})" if movie.get("year") else "",
        " ".join(movie.get("genres") or []),
        (movie.get("description") or "")[:500],
        " ".join(movie.get("directors") or []),
        " ".join((movie.get("actors") or [])[:5]),
    ]
    return " | ".join(p for p in parts if p.strip())


async def _fetch_movies(pool: asyncpg.Pool, force: bool) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(FETCH_ALL if force else FETCH_UNINDEXED)
    return [dict(r) for r in rows]


async def _store_batch(
    pool: asyncpg.Pool,
    batch: list[dict[str, Any]],
    embeddings: Any,
) -> None:
    async with pool.acquire() as conn:
        await conn.executemany(
            "UPDATE movies SET embedding = $1, embedding_updated_at = NOW() WHERE id = $2",
            [(emb, m["id"]) for emb, m in zip(embeddings, batch)],
        )


async def index_all_movies(
    model: SentenceTransformer | None = None,
    pool: asyncpg.Pool | None = None,
    force: bool = False,
) -> dict[str, Any]:
    own_pool = pool is None
    if model is None:
        print(f"Loading model: {MODEL_NAME}")
        model = SentenceTransformer(MODEL_NAME)

    if own_pool:
        postgres_url = os.environ["POSTGRES_URL"].replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        pool = await asyncpg.create_pool(
            postgres_url, min_size=2, max_size=5, init=register_vector
        )

    try:
        movies = await _fetch_movies(pool, force)
        if not movies:
            return {"count": 0, "message": "All movies already indexed"}

        print(f"Indexing {len(movies)} movies in batches of {BATCH_SIZE}...")
        start = time.time()

        for i in range(0, len(movies), BATCH_SIZE):
            batch = movies[i : i + BATCH_SIZE]
            # E5 models require "passage: " prefix on stored documents for
            # optimal retrieval performance; the matching "query: " prefix
            # lives in the NLP service at search time.
            docs = [f"passage: {build_document(m)}" for m in batch]
            embeddings = model.encode(
                docs,
                batch_size=BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            await _store_batch(pool, batch, embeddings)

            done = i + len(batch)
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"  {done}/{len(movies)} | {elapsed:.1f}s | {rate:.0f} mov/s")

        return {"count": len(movies), "elapsed_seconds": round(time.time() - start, 1)}
    finally:
        if own_pool and pool is not None:
            await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index movie embeddings into PostgreSQL")
    parser.add_argument("--force", action="store_true", help="Re-index all movies")
    args = parser.parse_args()
    result = asyncio.run(index_all_movies(force=args.force))
    print(f"\nDone: {result}")
