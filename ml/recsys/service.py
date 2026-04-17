import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg
import numpy as np
import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from pgvector.asyncpg import register_vector
from pydantic import BaseModel, Field

load_dotenv()

_model: Any = None
_pool: asyncpg.Pool | None = None
_movie_idx_map: dict[int, int] = {}
_item_embeddings: np.ndarray | None = None


async def _precompute_item_embeddings() -> None:
    global _movie_idx_map, _item_embeddings
    if _pool is None:
        return

    import numpy as np
    import torch

    N_GENRES = 19
    ITEM_FEATURE_DIM = N_GENRES + 3
    NLP_DIM = 384
    GENOME_DIM = 1128

    def parse_vec(raw, dim):
        if raw is None:
            return np.zeros(dim, dtype=np.float32)
        if isinstance(raw, str):
            raw = [float(x) for x in raw.strip("[]{}").split(",") if x.strip()]
        return np.asarray(raw, dtype=np.float32)

    async with _pool.acquire() as conn:
        genre_list = [
            r["slug"]
            for r in await conn.fetch("SELECT slug FROM genres ORDER BY id")
        ]
        rows = await conn.fetch(
            """
            SELECT m.id, m.year, m.avg_rating, m.popularity_score,
                   m.embedding, m.genome_scores,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.slug), NULL) AS genres
            FROM movies m
            LEFT JOIN movie_genres mg ON mg.movie_id = m.id
            LEFT JOIN genres g ON g.id = mg.genre_id
            GROUP BY m.id
            ORDER BY m.id
            """
        )

    if not rows:
        structlog.get_logger().warning("no_movies_found")
        return

    genre_to_idx = {g: i for i, g in enumerate(genre_list)}
    ids: list[int] = []
    feats_list: list[np.ndarray] = []
    nlp_list: list[np.ndarray] = []
    gen_list: list[np.ndarray] = []

    for r in rows:
        feat = np.zeros(ITEM_FEATURE_DIM, dtype=np.float32)
        for g in r["genres"] or []:
            if g in genre_to_idx and genre_to_idx[g] < N_GENRES:
                feat[genre_to_idx[g]] = 1.0
        if r["year"]:
            feat[N_GENRES] = (r["year"] - 1900) / 130.0
        if r["avg_rating"]:
            feat[N_GENRES + 1] = float(r["avg_rating"]) / 5.0
        if r["popularity_score"]:
            feat[N_GENRES + 2] = min(float(r["popularity_score"]) / 50.0, 1.0)

        ids.append(r["id"])
        feats_list.append(feat)
        nlp_list.append(parse_vec(r["embedding"], NLP_DIM))
        gen_list.append(parse_vec(r["genome_scores"], GENOME_DIM))

    if _model is not None:
        # Trained tower: run forward pass to get real 256-dim embeddings
        try:
            device = next(_model.parameters()).device
        except StopIteration:
            device = torch.device("cpu")

        item_ids_t = torch.tensor(
            list(range(1, len(ids) + 1)), dtype=torch.long, device=device
        )
        feats_t = torch.tensor(np.array(feats_list), dtype=torch.float32, device=device)
        nlp_t = torch.tensor(np.array(nlp_list), dtype=torch.float32, device=device)
        gen_t = torch.tensor(np.array(gen_list), dtype=torch.float32, device=device)

        _model.eval()
        with torch.no_grad():
            try:
                emb = _model.encode_item(item_ids_t, feats_t, nlp_t, gen_t)
            except TypeError:
                # Old-signature fallback (encode_item without genome)
                emb = _model.encode_item(item_ids_t, feats_t, nlp_t)

        _item_embeddings = emb.cpu().numpy().astype(np.float32)
        _movie_idx_map = {mid: i for i, mid in enumerate(ids)}
        structlog.get_logger().info(
            "tower_item_embeddings_built",
            count=len(ids),
            dim=int(_item_embeddings.shape[1]),
        )
    else:
        # Fallback: use raw NLP embeddings (original behavior)
        _item_embeddings = np.array(nlp_list, dtype=np.float32)
        norms = np.linalg.norm(_item_embeddings, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        _item_embeddings = _item_embeddings / norms
        _movie_idx_map = {mid: i for i, mid in enumerate(ids)}
        structlog.get_logger().warning(
            "no_model_loaded_using_nlp_fallback",
            count=len(ids),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _model, _pool
    logger = structlog.get_logger()
    logger.info("recsys_service_starting")

    url = os.environ.get("POSTGRES_URL", "").replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    _pool = await asyncpg.create_pool(
        url, min_size=2, max_size=5, init=register_vector
    )

    try:
        import mlflow.pytorch

        mlflow.set_tracking_uri(
            os.environ.get("MLFLOW_TRACKING_URI", "./mlruns")
        )
        _model = mlflow.pytorch.load_model("models:/two_tower_recsys/Latest")
        _model.eval()
        logger.info("two_tower_model_loaded")
    except Exception as e:
        logger.warning("model_load_failed_using_popularity", error=str(e))
        _model = None

    await _precompute_item_embeddings()
    logger.info("recsys_service_ready")
    yield

    if _pool is not None:
        await _pool.close()
    logger.info("recsys_service_stopped")


app = FastAPI(title="MovieMatch RecSys Service", version="1.0.0", lifespan=lifespan)


class RatingItem(BaseModel):
    movie_id: int
    score: float


class RecommendRequest(BaseModel):
    ratings: list[RatingItem]
    k: int = Field(default=10, ge=1, le=50)


class RecommendResult(BaseModel):
    movie_id: int
    score: float


class RecommendResponse(BaseModel):
    results: list[RecommendResult]
    model_version: str
    fallback: bool = False


async def _popularity_fallback(k: int) -> RecommendResponse:
    if _pool is None:
        return RecommendResponse(
            results=[], model_version="no_db", fallback=True
        )
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, popularity_score
            FROM movies
            WHERE rating_count > 10
            ORDER BY popularity_score DESC
            LIMIT $1
            """,
            k,
        )
    return RecommendResponse(
        results=[
            RecommendResult(
                movie_id=r["id"],
                score=round(float(r["popularity_score"]), 4),
            )
            for r in rows
        ],
        model_version="popularity_fallback",
        fallback=True,
    )


@app.post("/recommend", response_model=RecommendResponse)
async def recommend(req: RecommendRequest) -> RecommendResponse:
    if _item_embeddings is None or len(_item_embeddings) == 0:
        return await _popularity_fallback(req.k)

    scored_items = [
        (r.movie_id, r.score)
        for r in req.ratings
        if r.movie_id in _movie_idx_map
    ]
    if len(scored_items) < 1:
        return await _popularity_fallback(req.k)

    indices = np.array([_movie_idx_map[mid] for mid, _ in scored_items])
    weights = np.array([s / 5.0 for _, s in scored_items], dtype=np.float32)
    weight_sum = weights.sum()
    if weight_sum > 0:
        weights /= weight_sum

    user_emb = (_item_embeddings[indices] * weights[:, np.newaxis]).sum(axis=0)
    norm = np.linalg.norm(user_emb)
    if norm > 1e-8:
        user_emb /= norm

    scores = _item_embeddings @ user_emb

    seen = {_movie_idx_map[r.movie_id] for r in req.ratings if r.movie_id in _movie_idx_map}
    for idx in seen:
        scores[idx] = -np.inf

    top_k = np.argsort(scores)[::-1][: req.k]
    id_list = list(_movie_idx_map.keys())

    results = [
        RecommendResult(movie_id=id_list[i], score=round(float(scores[i]), 4))
        for i in top_k
        if scores[i] > -np.inf
    ]
    return RecommendResponse(
        results=results,
        model_version="embedding_similarity_v1",
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "items_in_memory": len(_movie_idx_map),
    }
