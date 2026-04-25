import asyncio
import os
from typing import Any

import asyncpg
import structlog

from workers.celery_app import app


@app.task(name="workers.tasks.analytics.update_popularity_scores")
def update_popularity_scores() -> None:
    logger = structlog.get_logger()

    async def _run() -> None:
        dsn = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                """
                WITH computed AS (
                    SELECT id,
                        LN(GREATEST(rating_count, 1) + 1)
                        * COALESCE(avg_rating, 3.0) AS raw
                    FROM movies
                ),
                normed AS (
                    SELECT id,
                        (raw - MIN(raw) OVER())
                        / NULLIF(MAX(raw) OVER() - MIN(raw) OVER(), 0) AS score
                    FROM computed
                )
                UPDATE movies m
                SET popularity_score = LEAST(COALESCE(n.score, 0) * 100.0, 9999.9999)
                FROM normed n
                WHERE m.id = n.id
                """
            )
            logger.info("popularity_scores_updated")
        finally:
            await conn.close()

    asyncio.run(_run())


@app.task(name="workers.tasks.analytics.recompute_movie_ratings")
def recompute_movie_ratings() -> None:
    logger = structlog.get_logger()

    async def _run() -> None:
        dsn = os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                """
                UPDATE movies m SET
                    avg_rating = r.avg_score,
                    rating_count = r.cnt
                FROM (
                    SELECT movie_id,
                        AVG(score)::numeric(3, 2) AS avg_score,
                        COUNT(*)::int AS cnt
                    FROM ratings GROUP BY movie_id
                ) r
                WHERE m.id = r.movie_id
                """
            )
            logger.info("movie_ratings_recomputed")
        finally:
            await conn.close()

    asyncio.run(_run())
