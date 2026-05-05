import time
from typing import Any

import structlog

from db.database import execute_query
from exceptions import MLServiceUnavailableError
from schemas.recommendations import MovieRecommendation, RecommendResponse
from services import cv_client, nlp_client, recsys_client
from services.cache import get_cached, set_cached

MODEL_VERSION = "1.0.0"
COLD_START_THRESHOLD = 3
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"

EMOTION_TO_GENRES: dict[str, list[str]] = {
    "happy": ["Comedy", "Family", "Adventure"],
    "sad": ["Drama", "Romance"],
    "angry": ["Action", "Thriller", "Crime"],
    "fear": ["Horror", "Thriller", "Mystery"],
    "surprise": ["Science Fiction", "Fantasy", "Adventure"],
    "disgust": ["Horror", "Crime"],
    "neutral": ["Drama", "Documentary", "History"],
}


def _poster_url(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else f"{TMDB_IMG_BASE}{path}"


async def _enrich_recommendations(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    ids = [int(c["movie_id"]) for c in candidates if c.get("movie_id") is not None]
    if not ids:
        return []
    rows = await execute_query(
        """
        SELECT
            m.id, m.title, m.year, m.avg_rating, m.poster_path,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.id = ANY($1::int[])
        GROUP BY m.id
        """,
        ids,
    )
    return rows


async def _popularity_fallback(
    limit: int,
    genres: list[str] | None = None,
) -> list[dict[str, Any]]:
    if genres:
        return await execute_query(
            """
            SELECT
                m.id, m.title, m.year, m.avg_rating, m.poster_path,
                ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
            FROM movies m
            JOIN movie_genres mg ON mg.movie_id = m.id
            JOIN genres g ON g.id = mg.genre_id
            WHERE g.name = ANY($1::text[]) AND m.rating_count > 10
            GROUP BY m.id
            ORDER BY m.popularity_score DESC
            LIMIT $2
            """,
            genres,
            limit,
        )
    return await execute_query(
        """
        SELECT
            m.id, m.title, m.year, m.avg_rating, m.poster_path,
            ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.name), NULL) AS genres
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.rating_count > 10
        GROUP BY m.id
        ORDER BY m.popularity_score DESC
        LIMIT $1
        """,
        limit,
    )


def _row_to_reco(
    row: dict[str, Any],
    score: float | None,
    reason: str,
) -> MovieRecommendation:
    return MovieRecommendation(
        movie_id=row["id"],
        title=row["title"],
        year=row.get("year"),
        genres=list(row.get("genres") or []),
        avg_rating=float(row["avg_rating"]) if row.get("avg_rating") is not None else None,
        poster_url=_poster_url(row.get("poster_path")),
        score=score,
        reason=reason,
    )


async def get_collaborative_recommendations(
    user_id: str,
    ratings: list[dict[str, Any]],
    limit: int,
    filters: dict[str, Any] | None,
    redis: Any,
    request_id: str,
) -> RecommendResponse:
    start = time.perf_counter()
    cache_params = {"limit": limit, "filters": filters, "n_ratings": len(ratings)}

    cached = await get_cached(redis, user_id, "collaborative", cache_params)
    if cached is not None:
        cached["cached"] = True
        cached["request_id"] = request_id
        return RecommendResponse(**cached)

    is_cold_start = len(ratings) < COLD_START_THRESHOLD
    items: list[MovieRecommendation] = []
    model_version = MODEL_VERSION

    if is_cold_start:
        rows = await _popularity_fallback(limit)
        # None score = "no personalisation signal yet"; the UI should hide the
        # match-percent badge and frame this list as "Popular now".
        items = [_row_to_reco(r, None, "Popular now") for r in rows]
        model_version = "popularity"
    else:
        try:
            candidates = await recsys_client.get_recommendations(ratings, limit)
            scores = {int(c["movie_id"]): float(c.get("score", 0.0)) for c in candidates}
            rows = await _enrich_recommendations(candidates)
            rows.sort(key=lambda r: scores.get(r["id"], 0.0), reverse=True)
            items = [
                _row_to_reco(r, scores.get(r["id"], 0.0), "Based on your ratings")
                for r in rows
            ]
        except MLServiceUnavailableError:
            structlog.get_logger().warning("recsys_fallback", user_id=user_id)
            rows = await _popularity_fallback(limit)
            items = [_row_to_reco(r, None, "Popular (ML unavailable)") for r in rows]
            model_version = "popularity"

    latency_ms = int((time.perf_counter() - start) * 1000)
    response = RecommendResponse(
        items=items[:limit],
        model_version=model_version,
        latency_ms=latency_ms,
        request_id=request_id,
        cached=False,
    )
    await set_cached(redis, user_id, "collaborative", cache_params, response.model_dump())
    return response


async def get_search_recommendations(
    query: str,
    limit: int,
    filters: dict[str, Any] | None,
    request_id: str,
    offset: int = 0,
) -> RecommendResponse:
    start = time.perf_counter()
    items: list[MovieRecommendation] = []
    try:
        candidates = await nlp_client.search(query, limit, filters, offset=offset)
        # NLP returns `rrf_score` (not `score`); preserve its ordering exactly.
        scores = {
            int(c["movie_id"]): float(c.get("rrf_score", c.get("score", 0.0)))
            for c in candidates
        }
        ranking = {int(c["movie_id"]): i for i, c in enumerate(candidates)}
        rows = await _enrich_recommendations(candidates)
        rows.sort(key=lambda r: ranking.get(r["id"], 10**9))
        items = [
            _row_to_reco(r, scores.get(r["id"], 0.0), f"Matches '{query}'")
            for r in rows
        ]
    except MLServiceUnavailableError:
        structlog.get_logger().warning("nlp_fallback", query=query)
        rows = await _popularity_fallback(limit)
        items = [_row_to_reco(r, 0.3, "Popular (search unavailable)") for r in rows]

    latency_ms = int((time.perf_counter() - start) * 1000)
    return RecommendResponse(
        items=items[:limit],
        model_version=MODEL_VERSION,
        latency_ms=latency_ms,
        request_id=request_id,
    )


EMOTION_VERDICT: dict[str, str] = {
    "happy": "You look cheerful — here's more uplifting fuel.",
    "sad": "A bit down today? These warm, hopeful picks should help.",
    "angry": "Blow off some steam with these high-energy picks.",
    "fear": "Something calm and grounding to take the edge off.",
    "surprise": "Keeping the energy up with something bold and unexpected.",
    "disgust": "Let's reset with some clean, clever entertainment.",
    "neutral": "Neutral mood — here's a balanced mix.",
}


async def get_emotion_recommendations(
    image_bytes: bytes,
    limit: int,
    request_id: str,
) -> RecommendResponse:
    start = time.perf_counter()
    try:
        detection = await cv_client.detect_emotion(image_bytes)
    finally:
        del image_bytes

    emotion = str(detection.get("emotion", "neutral")).lower()
    confidence = float(detection.get("confidence", 0.0))
    genres = EMOTION_TO_GENRES.get(emotion, EMOTION_TO_GENRES["neutral"])
    verdict = EMOTION_VERDICT.get(emotion, EMOTION_VERDICT["neutral"])

    rows = await _popularity_fallback(limit, genres=genres)
    items = [
        _row_to_reco(r, confidence, f"Matches your mood: {emotion}") for r in rows
    ]

    latency_ms = int((time.perf_counter() - start) * 1000)
    return RecommendResponse(
        items=items[:limit],
        model_version=MODEL_VERSION,
        latency_ms=latency_ms,
        request_id=request_id,
        emotion=emotion,
        emotion_confidence=confidence,
        emotion_message=verdict,
    )
