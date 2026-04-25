import asyncio
import os
from typing import Any

import asyncpg
import httpx
import numpy as np
import structlog

from workers.celery_app import app


def _parse_vector(raw: Any, dim: int) -> np.ndarray:
    if raw is None:
        return np.zeros(dim, dtype=np.float32)
    if isinstance(raw, str):
        raw = [float(x) for x in raw.strip("[]{}").split(",") if x.strip()]
    return np.asarray(raw, dtype=np.float32)


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    name="workers.tasks.recommendations.refresh_all_movie_embeddings",
)
def refresh_all_movie_embeddings(self: Any) -> None:
    """Trigger NLP service to re-index new/stale movie embeddings."""
    logger = structlog.get_logger()

    async def _run() -> None:
        nlp_url = os.environ.get("ML_NLP_URL", "http://localhost:8002")
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(f"{nlp_url}/reindex", json={"force": False})
            resp.raise_for_status()
            logger.info("embedding_refresh_triggered", result=resp.json())

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error("embedding_refresh_failed", error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="workers.tasks.recommendations.refresh_user_embedding",
)
def refresh_user_embedding(self: Any, user_id: str) -> None:
    """Recompute user embedding as weighted mean of rated-movie embeddings."""
    logger = structlog.get_logger()

    async def _run() -> None:
        dsn = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                """
                SELECT m.embedding, r.score
                FROM ratings r
                JOIN movies m ON m.id = r.movie_id
                WHERE r.user_id = $1::uuid
                  AND m.embedding IS NOT NULL
                  AND r.score >= 3.0
                ORDER BY r.updated_at DESC
                LIMIT 100
                """,
                user_id,
            )

            if not rows:
                logger.info("user_embedding_skipped_no_positives", user_id=user_id)
                return

            embeddings = np.stack([_parse_vector(r["embedding"], 384) for r in rows])
            weights = np.array([float(r["score"]) / 5.0 for r in rows], dtype=np.float32)
            weight_sum = weights.sum()
            if weight_sum <= 0:
                logger.info("user_embedding_skipped_zero_weights", user_id=user_id)
                return
            weights = weights / weight_sum

            user_emb = (embeddings * weights[:, np.newaxis]).sum(axis=0)
            norm = float(np.linalg.norm(user_emb))
            if norm <= 1e-8:
                logger.info("user_embedding_skipped_zero_norm", user_id=user_id)
                return
            user_emb = user_emb / norm

            vec_str = "[" + ",".join(f"{x:.6f}" for x in user_emb.tolist()) + "]"
            await conn.execute(
                """
                INSERT INTO user_embeddings (user_id, embedding, model_version, updated_at)
                VALUES ($1::uuid, $2::vector, 'weighted_mean_v1', NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    model_version = EXCLUDED.model_version,
                    updated_at = NOW()
                """,
                user_id,
                vec_str,
            )
            logger.info(
                "user_embedding_refreshed",
                user_id=user_id,
                n_ratings=len(rows),
            )
        finally:
            await conn.close()

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error("user_embedding_failed", user_id=user_id, error=str(exc))
        raise self.retry(exc=exc)
