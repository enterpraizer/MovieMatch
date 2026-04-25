from typing import Any

from fastapi import APIRouter, Depends, Query, Response

import structlog

from db.database import execute_one, execute_query, execute_write
from dependencies import get_current_user, get_redis, get_verified_user
from exceptions import MovieNotFoundError, RatingNotFoundError
from schemas.movies import MovieResponse
from schemas.recommendations import RatingInput
from services.cache import invalidate_user

router = APIRouter()


@router.post("", status_code=201)
async def rate_movie(
    data: RatingInput,
    current_user: dict[str, Any] = Depends(get_verified_user),
    redis: Any = Depends(get_redis),
) -> dict[str, Any]:
    movie = await execute_one("SELECT id FROM movies WHERE id = $1", data.movie_id)
    if movie is None:
        raise MovieNotFoundError(data.movie_id)

    user_id = current_user["id"]
    await execute_write(
        """
        INSERT INTO ratings (user_id, movie_id, score)
        VALUES ($1::uuid, $2, $3)
        ON CONFLICT (user_id, movie_id) DO UPDATE
        SET score = EXCLUDED.score, updated_at = NOW()
        """,
        user_id,
        data.movie_id,
        data.score,
    )
    await execute_write(
        """
        UPDATE movies SET
            avg_rating = (SELECT AVG(score) FROM ratings WHERE movie_id = $1),
            rating_count = (SELECT COUNT(*) FROM ratings WHERE movie_id = $1)
        WHERE id = $1
        """,
        data.movie_id,
    )

    await invalidate_user(redis, user_id)

    try:
        from workers.tasks.recommendations import refresh_user_embedding
        refresh_user_embedding.delay(user_id)
    except Exception:
        pass

    return {"movie_id": data.movie_id, "score": data.score, "message": "Rating saved"}


@router.get("/me")
async def list_my_ratings(
    cursor: int | None = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = current_user["id"]
    params: list[Any] = [user_id]
    cursor_clause = ""
    if cursor is not None:
        params.append(cursor)
        cursor_clause = f"AND r.id < ${len(params)}"
    params.append(limit + 1)

    rows = await execute_query(
        f"""
        SELECT
            r.id AS rating_id,
            m.id AS movie_id,
            m.title,
            m.year,
            m.poster_path,
            r.score,
            r.updated_at AS rated_at,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM ratings r
        JOIN movies m ON m.id = r.movie_id
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE r.user_id = $1::uuid {cursor_clause}
        GROUP BY r.id, m.id
        ORDER BY r.id DESC
        LIMIT ${len(params)}
        """,
        *params,
    )

    from routers.movies import _poster_url

    items = [
        {
            "movie_id": r["movie_id"],
            "title": r["title"],
            "year": r["year"],
            "poster_url": _poster_url(r["poster_path"]),
            "score": float(r["score"]),
            "rated_at": r["rated_at"].isoformat() if r.get("rated_at") else None,
            "updated_at": r["rated_at"].isoformat() if r.get("rated_at") else None,
            "genres": list(r.get("genres") or []),
        }
        for r in rows[:limit]
    ]
    next_cursor = rows[limit - 1]["rating_id"] if len(rows) > limit else None
    return {"items": items, "next_cursor": next_cursor}


@router.delete("/me", status_code=204)
async def delete_all_my_ratings(
    current_user: dict[str, Any] = Depends(get_verified_user),
    redis: Any = Depends(get_redis),
) -> Response:
    """Wipe every rating the current user has — 'Start over' flow."""
    user_id = current_user["id"]
    rows = await execute_query(
        "DELETE FROM ratings WHERE user_id = $1::uuid RETURNING movie_id",
        user_id,
    )
    if rows:
        mids = [int(r["movie_id"]) for r in rows]
        # Recompute movie aggregates for each affected film (cheap; max ~N rated).
        for mid in mids:
            await execute_write(
                """
                UPDATE movies SET
                    avg_rating = COALESCE((SELECT AVG(score) FROM ratings WHERE movie_id = $1), 0),
                    rating_count = COALESCE((SELECT COUNT(*) FROM ratings WHERE movie_id = $1), 0)
                WHERE id = $1
                """,
                mid,
            )
    await invalidate_user(redis, user_id)
    structlog.get_logger().info("ratings_bulk_deleted", user_id=user_id, count=len(rows))
    return Response(status_code=204)


@router.delete("/{movie_id}", status_code=204)
async def delete_rating(
    movie_id: int,
    current_user: dict[str, Any] = Depends(get_verified_user),
    redis: Any = Depends(get_redis),
) -> Response:
    user_id = current_user["id"]
    deleted = await execute_one(
        "DELETE FROM ratings WHERE user_id = $1::uuid AND movie_id = $2 RETURNING id",
        user_id,
        movie_id,
    )
    if deleted is None:
        raise RatingNotFoundError()

    await execute_write(
        """
        UPDATE movies SET
            avg_rating = (SELECT AVG(score) FROM ratings WHERE movie_id = $1),
            rating_count = (SELECT COUNT(*) FROM ratings WHERE movie_id = $1)
        WHERE id = $1
        """,
        movie_id,
    )
    await invalidate_user(redis, user_id)
    return Response(status_code=204)
