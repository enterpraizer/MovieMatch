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
_cross_encoder: Any = None
_pool: asyncpg.Pool | None = None
_movie_idx_map: dict[int, int] = {}
_item_embeddings: np.ndarray | None = None
_faiss_index: Any = None  # faiss.IndexHNSWFlat


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
        arr = np.asarray(raw, dtype=np.float32)
        # The NLP column was re-indexed to 768 dim (E5-base) while the trained
        # Two-Tower still expects 384 dim (old MiniLM semantic space).
        # Truncating keeps shapes compatible; the NLP signal is then only
        # approximate but the rest of the tower (id + genome + features)
        # carries the bulk of the signal anyway.
        if arr.shape[0] != dim:
            if arr.shape[0] > dim:
                arr = arr[:dim]
            else:
                padded = np.zeros(dim, dtype=np.float32)
                padded[: arr.shape[0]] = arr
                arr = padded
        return arr

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
        _build_faiss_index()
        structlog.get_logger().info(
            "tower_item_embeddings_built",
            count=len(ids),
            dim=int(_item_embeddings.shape[1]),
            faiss=_faiss_index is not None,
        )
    else:
        # Fallback: use raw NLP embeddings (original behavior)
        _item_embeddings = np.array(nlp_list, dtype=np.float32)
        norms = np.linalg.norm(_item_embeddings, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-8)
        _item_embeddings = _item_embeddings / norms
        _movie_idx_map = {mid: i for i, mid in enumerate(ids)}
        _build_faiss_index()
        structlog.get_logger().warning(
            "no_model_loaded_using_nlp_fallback",
            count=len(ids),
        )


def _build_faiss_index() -> None:
    """Build FAISS HNSW index over _item_embeddings for fast top-K search."""
    global _faiss_index
    _faiss_index = None
    if _item_embeddings is None or len(_item_embeddings) == 0:
        return
    if os.environ.get("DISABLE_FAISS", "").lower() in {"1", "true", "yes"}:
        return
    try:
        import faiss  # type: ignore
        dim = _item_embeddings.shape[1]
        index = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = 64
        index.hnsw.efSearch = 64
        index.add(np.ascontiguousarray(_item_embeddings))
        _faiss_index = index
    except Exception as e:
        structlog.get_logger().warning("faiss_unavailable_using_numpy", error=str(e))
        _faiss_index = None


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

    # Optional Cross-Encoder for multi-stage re-ranking
    global _cross_encoder
    try:
        import mlflow.pytorch
        _cross_encoder = mlflow.pytorch.load_model("models:/cross_encoder/Latest")
        _cross_encoder.eval()
        logger.info("cross_encoder_loaded")
    except Exception as e:
        logger.info("cross_encoder_unavailable", error=str(e))
        _cross_encoder = None

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
    # Signed weights centred at 3.0: likes pull, dislikes push away.
    # 0.5→-1, 1→-1, 2.5→-0.25, 3.0→0, 4.5→+0.75, 5.0→+1. Clamp to [-1,+1]
    # so a single extreme rating doesn't swamp the user vector.
    signed = np.clip(
        np.array([(s - 3.0) / 2.0 for _, s in scored_items], dtype=np.float32),
        -1.0, 1.0,
    )
    user_emb = (_item_embeddings[indices] * signed[:, np.newaxis]).sum(axis=0)
    norm = np.linalg.norm(user_emb)
    if norm < 1e-6:
        # All neutral (3.0) or perfectly balanced likes and dislikes —
        # no directional signal, fall back to popularity.
        return await _popularity_fallback(req.k)
    user_emb /= norm

    seen = {_movie_idx_map[r.movie_id] for r in req.ratings if r.movie_id in _movie_idx_map}
    id_list = list(_movie_idx_map.keys())

    # Fast path via FAISS HNSW — ask for more than k, then filter seen
    if _faiss_index is not None:
        # Multi-stage: retrieve many candidates, re-rank with cross-encoder
        retrieval_k = 200 if _cross_encoder is not None else max(req.k + len(seen) + 20, req.k * 2)
        query = np.ascontiguousarray(user_emb[np.newaxis, :], dtype=np.float32)
        D, I = _faiss_index.search(query, retrieval_k)
        cand_idxs: list[int] = []
        cand_scores: list[float] = []
        for rank in range(I.shape[1]):
            idx = int(I[0, rank])
            if idx in seen or idx < 0:
                continue
            cand_idxs.append(idx)
            cand_scores.append(float(D[0, rank]))

        if _cross_encoder is not None and cand_idxs:
            # Stage 2: deep scoring
            import torch as _t
            try:
                device = next(_cross_encoder.parameters()).device
            except StopIteration:
                device = _t.device("cpu")
            with _t.no_grad():
                u_t = _t.tensor(user_emb, dtype=_t.float32, device=device).unsqueeze(0).expand(len(cand_idxs), -1)
                i_t = _t.tensor(_item_embeddings[cand_idxs], dtype=_t.float32, device=device)
                ce_scores = _cross_encoder(u_t, i_t).cpu().numpy()
            order = np.argsort(-ce_scores)[: req.k]
            picks = [(cand_idxs[j], float(ce_scores[j])) for j in order]
            model_version = "two_tower_v4+cross_encoder"
        else:
            picks = list(zip(cand_idxs[: req.k], cand_scores[: req.k]))
            model_version = "two_tower_v4_faiss"

        results = [
            RecommendResult(movie_id=id_list[i], score=round(s, 4))
            for i, s in picks
        ]
    else:
        scores = _item_embeddings @ user_emb
        for idx in seen:
            scores[idx] = -np.inf
        top_k = np.argsort(scores)[::-1][: req.k]
        results = [
            RecommendResult(movie_id=id_list[i], score=round(float(scores[i]), 4))
            for i in top_k
            if scores[i] > -np.inf
        ]
        model_version = "two_tower_v4_numpy"
    return RecommendResponse(
        results=results,
        model_version=model_version,
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "cross_encoder_loaded": _cross_encoder is not None,
        "faiss_index": _faiss_index is not None,
        "items_in_memory": len(_movie_idx_map),
    }
