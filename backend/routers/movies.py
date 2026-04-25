import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from db.database import execute_one, execute_query
from dependencies import get_redis
from exceptions import MovieNotFoundError
from schemas.movies import (
    CreditResponse,
    MovieDetailResponse,
    MovieListResponse,
    MovieResponse,
    PersonResponse,
)

router = APIRouter()

TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"


def _poster_url(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else f"{TMDB_IMG_BASE}{path}"


def _row_to_movie(row: dict[str, Any]) -> MovieResponse:
    return MovieResponse(
        id=row["id"],
        title=row["title"],
        year=row.get("year"),
        avg_rating=float(row["avg_rating"]) if row.get("avg_rating") is not None else None,
        rating_count=row.get("rating_count") or 0,
        genres=list(row.get("genres") or []),
        poster_url=_poster_url(row.get("poster_path")),
    )


@router.get("", response_model=MovieListResponse)
@router.get("/", response_model=MovieListResponse, include_in_schema=False)
async def list_movies(
    cursor: int | None = Query(None, ge=0),
    limit: int = Query(20, ge=1, le=50),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
    genres: list[str] | None = Query(None),
    min_rating: float | None = Query(None, ge=0.5, le=5.0),
    order_by: Literal["popularity", "rating", "year"] = "popularity",
) -> MovieListResponse:
    order_column = {
        "popularity": "m.popularity_score",
        "rating": "m.avg_rating",
        "year": "m.year",
    }[order_by]

    conditions: list[str] = []
    params: list[Any] = []

    def p(val: Any) -> str:
        params.append(val)
        return f"${len(params)}"

    if cursor is not None:
        conditions.append(f"m.id > {p(cursor)}")
    if year_from is not None:
        conditions.append(f"m.year >= {p(year_from)}")
    if year_to is not None:
        conditions.append(f"m.year <= {p(year_to)}")
    if min_rating is not None:
        conditions.append(f"m.avg_rating >= {p(min_rating)}")
    if genres:
        conditions.append(
            f"EXISTS (SELECT 1 FROM movie_genres mg2 "
            f"JOIN genres g2 ON g2.id = mg2.genre_id "
            f"WHERE mg2.movie_id = m.id AND g2.slug = ANY({p(genres)}))"
        )

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    query = f"""
        SELECT
            m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        {where_clause}
        GROUP BY m.id
        ORDER BY {order_column} DESC NULLS LAST, m.id ASC
        LIMIT {p(limit + 1)}
    """

    rows = await execute_query(query, *params)
    items = [_row_to_movie(r) for r in rows[:limit]]
    next_cursor = rows[limit - 1]["id"] if len(rows) > limit else None
    return MovieListResponse(items=items, next_cursor=next_cursor)


@router.get("/trending", response_model=list[MovieResponse])
async def trending(request: Request, redis: Any = Depends(get_redis)) -> list[MovieResponse]:
    cache_key = "movies:trending"
    cached = await redis.get(cache_key)
    if cached:
        return [MovieResponse(**m) for m in json.loads(cached)]

    rows = await execute_query(
        """
        SELECT
            m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.rating_count > 50
        GROUP BY m.id
        ORDER BY m.popularity_score DESC
        LIMIT 20
        """
    )
    items = [_row_to_movie(r) for r in rows]
    await redis.setex(cache_key, 1800, json.dumps([i.model_dump() for i in items]))
    return items


@router.get("/onboarding", response_model=list[MovieResponse])
async def onboarding_movies(
    redis: Any = Depends(get_redis),
    limit: int = Query(40, ge=10, le=100),
) -> list[MovieResponse]:
    """Popular + divisive movies for cold-start rating onboarding.

    Selects movies with high rating_count × stddev(rating) so the user's
    ratings carry information (not just "everyone likes this").
    Diversifies by genre: greedy round-robin across genres to avoid all
    drama / all action.
    """
    cache_key = f"movies:onboarding:{limit}"
    cached = await redis.get(cache_key)
    if cached:
        return [MovieResponse(**m) for m in json.loads(cached)]

    rows = await execute_query(
        """
        WITH stats AS (
            SELECT movie_id, COUNT(*) AS cnt, STDDEV(score) AS stdev
            FROM ratings
            GROUP BY movie_id
            HAVING COUNT(*) >= 100
        )
        SELECT
            m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres,
            s.cnt * COALESCE(s.stdev, 0) AS divisive_score
        FROM movies m
        JOIN stats s ON s.movie_id = m.id
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.poster_path IS NOT NULL AND m.poster_path != ''
        GROUP BY m.id, s.cnt, s.stdev
        ORDER BY divisive_score DESC
        LIMIT 200
        """
    )

    selected: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    genre_quota: dict[str, int] = {}
    max_per_genre = max(3, limit // 6)

    for r in rows:
        if r["id"] in seen_ids:
            continue
        genres = list(r.get("genres") or [])
        primary = genres[0] if genres else "_none"
        if genre_quota.get(primary, 0) >= max_per_genre:
            continue
        selected.append(r)
        seen_ids.add(r["id"])
        genre_quota[primary] = genre_quota.get(primary, 0) + 1
        if len(selected) >= limit:
            break

    if len(selected) < limit:
        for r in rows:
            if r["id"] not in seen_ids:
                selected.append(r)
                seen_ids.add(r["id"])
                if len(selected) >= limit:
                    break

    items = [_row_to_movie(r) for r in selected]
    await redis.setex(cache_key, 3600, json.dumps([i.model_dump() for i in items]))
    return items


@router.get("/search", response_model=list[MovieResponse])
async def search_movies(
    q: str = Query(..., min_length=1, max_length=200),
) -> list[MovieResponse]:
    pattern = f"%{q}%"
    rows = await execute_query(
        """
        SELECT
            m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.title ILIKE $1 OR m.title_original ILIKE $1
        GROUP BY m.id
        ORDER BY similarity(m.title, $2) DESC NULLS LAST, m.avg_rating DESC NULLS LAST
        LIMIT 10
        """,
        pattern,
        q,
    )
    return [_row_to_movie(r) for r in rows]


@router.get("/{movie_id}", response_model=MovieDetailResponse)
async def get_movie(movie_id: int, redis: Any = Depends(get_redis)) -> MovieDetailResponse:
    cache_key = f"movie:{movie_id}"
    cached = await redis.get(cache_key)
    if cached:
        return MovieDetailResponse(**json.loads(cached))

    movie = await execute_one(
        """
        SELECT
            m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
            m.description, m.runtime_minutes, m.imdb_id,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.id = $1
        GROUP BY m.id
        """,
        movie_id,
    )
    if movie is None:
        raise MovieNotFoundError(movie_id)

    credit_rows = await execute_query(
        """
        SELECT p.id, p.name, p.profile_path, mc.role, mc.character_name, mc.order_index
        FROM movie_credits mc
        JOIN people p ON p.id = mc.person_id
        WHERE mc.movie_id = $1
        ORDER BY mc.order_index NULLS LAST
        LIMIT 20
        """,
        movie_id,
    )
    credits = [
        CreditResponse(
            person=PersonResponse(
                id=c["id"], name=c["name"], profile_path=c.get("profile_path")
            ),
            role=c["role"],
            character_name=c.get("character_name"),
            order_index=c.get("order_index"),
        )
        for c in credit_rows
    ]

    detail = MovieDetailResponse(
        id=movie["id"],
        title=movie["title"],
        year=movie.get("year"),
        avg_rating=float(movie["avg_rating"]) if movie.get("avg_rating") is not None else None,
        rating_count=movie.get("rating_count") or 0,
        genres=list(movie.get("genres") or []),
        poster_url=_poster_url(movie.get("poster_path")),
        description=movie.get("description"),
        runtime_minutes=movie.get("runtime_minutes"),
        imdb_id=movie.get("imdb_id"),
        credits=credits,
    )
    await redis.setex(cache_key, 3600, detail.model_dump_json())
    return detail


@router.get("/{movie_id}/similar", response_model=list[MovieResponse])
async def similar_movies(
    movie_id: int,
    limit: int = Query(default=12, ge=1, le=30),
) -> list[MovieResponse]:
    target = await execute_one("SELECT embedding FROM movies WHERE id = $1", movie_id)
    if target is None:
        raise MovieNotFoundError(movie_id)
    if target.get("embedding") is None:
        rows = await execute_query(
            """
            SELECT m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
            FROM movies m
            JOIN movie_genres mg ON mg.movie_id = m.id
            JOIN genres g ON g.id = mg.genre_id
            WHERE mg.genre_id IN (SELECT genre_id FROM movie_genres WHERE movie_id = $1)
              AND m.id != $1
            GROUP BY m.id
            ORDER BY m.popularity_score DESC NULLS LAST
            LIMIT $2
            """,
            movie_id, limit,
        )
        return [_row_to_movie(r) for r in rows]

    rows = await execute_query(
        """
        SELECT m.id, m.title, m.year, m.avg_rating, m.rating_count, m.poster_path,
               ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.id != $1 AND m.embedding IS NOT NULL
        GROUP BY m.id
        ORDER BY m.embedding <=> (SELECT embedding FROM movies WHERE id = $1)
        LIMIT $2
        """,
        movie_id, limit,
    )
    return [_row_to_movie(r) for r in rows]
