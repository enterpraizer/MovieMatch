from typing import Any

from fastapi import APIRouter, Depends, Response

from db.database import execute_one, execute_query, execute_write
from dependencies import get_current_user, get_verified_user
from exceptions import MovieNotFoundError
from routers.movies import _poster_url
from schemas.movies import MovieResponse

router = APIRouter()


@router.get("", response_model=list[MovieResponse])
async def list_watchlist(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[MovieResponse]:
    rows = await execute_query(
        """
        SELECT m.id, m.title, m.year, m.avg_rating, m.rating_count,
               m.poster_path,
               COALESCE(ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL), ARRAY[]::text[]) AS genres
        FROM watchlist w
        JOIN movies m ON m.id = w.movie_id
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE w.user_id = $1::uuid
        GROUP BY m.id, w.added_at
        ORDER BY w.added_at DESC
        """,
        current_user["id"],
    )
    return [
        MovieResponse(
            id=r["id"],
            title=r["title"],
            year=r["year"],
            avg_rating=float(r["avg_rating"]) if r["avg_rating"] is not None else None,
            rating_count=int(r["rating_count"] or 0),
            genres=list(r["genres"] or []),
            poster_url=_poster_url(r.get("poster_path")),
        )
        for r in rows
    ]


@router.post("/{movie_id}", status_code=201)
async def add_to_watchlist(
    movie_id: int,
    current_user: dict[str, Any] = Depends(get_verified_user),
) -> dict[str, Any]:
    movie = await execute_one("SELECT id FROM movies WHERE id = $1", movie_id)
    if movie is None:
        raise MovieNotFoundError(movie_id)
    await execute_write(
        """
        INSERT INTO watchlist (user_id, movie_id)
        VALUES ($1::uuid, $2)
        ON CONFLICT (user_id, movie_id) DO NOTHING
        """,
        current_user["id"],
        movie_id,
    )
    return {"movie_id": movie_id, "in_watchlist": True}


@router.delete("/{movie_id}", status_code=204)
async def remove_from_watchlist(
    movie_id: int,
    current_user: dict[str, Any] = Depends(get_verified_user),
) -> Response:
    await execute_write(
        "DELETE FROM watchlist WHERE user_id = $1::uuid AND movie_id = $2",
        current_user["id"],
        movie_id,
    )
    return Response(status_code=204)


@router.get("/ids", response_model=list[int])
async def list_watchlist_ids(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[int]:
    rows = await execute_query(
        "SELECT movie_id FROM watchlist WHERE user_id = $1::uuid",
        current_user["id"],
    )
    return [int(r["movie_id"]) for r in rows]
