from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile

import metrics
from config import get_settings
from dependencies import get_current_user, get_optional_user, get_redis
from exceptions import InvalidImageError
from schemas.recommendations import (
    CollaborativeRequest,
    RecommendResponse,
    SearchRequest,
)
from services import recommendations as reco_service

router = APIRouter()


def _detect_image_mime(head: bytes) -> str | None:
    """Detect image MIME from magic bytes — no libmagic / system deps."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _record(rec_type: str, result: RecommendResponse) -> None:
    metrics.recommendations_total.labels(
        recommendation_type=rec_type,
        cached=str(bool(result.cached)).lower(),
        model_version=result.model_version or "unknown",
    ).inc()


@router.post("/collaborative", response_model=RecommendResponse)
async def collaborative(
    body: CollaborativeRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    redis: Any = Depends(get_redis),
) -> RecommendResponse:
    ratings = [r.model_dump() for r in body.ratings]
    if not ratings:
        # Fall back to the user's persisted ratings so the endpoint works
        # on a fresh device where the client has no local rating cache.
        from db.database import execute_query
        db_rows = await execute_query(
            "SELECT movie_id, score::float AS score FROM ratings "
            "WHERE user_id = $1::uuid ORDER BY updated_at DESC LIMIT 500",
            current_user["id"],
        )
        ratings = [{"movie_id": int(r["movie_id"]), "score": float(r["score"])} for r in db_rows]

    with metrics.recommendation_timer("collaborative"):
        result = await reco_service.get_collaborative_recommendations(
            user_id=str(current_user["id"]),
            ratings=ratings,
            limit=body.limit,
            filters=body.filters.model_dump() if body.filters else None,
            redis=redis,
            request_id=getattr(request.state, "request_id", ""),
        )
    _record("collaborative", result)
    return result


@router.post("/search", response_model=RecommendResponse)
async def search(
    body: SearchRequest,
    request: Request,
    current_user: dict[str, Any] | None = Depends(get_optional_user),
) -> RecommendResponse:
    with metrics.recommendation_timer("search"):
        result = await reco_service.get_search_recommendations(
            query=body.query,
            limit=body.limit,
            offset=body.offset,
            filters=body.filters.model_dump() if body.filters else None,
            request_id=getattr(request.state, "request_id", ""),
        )
    _record("search", result)
    return result


@router.post("/emotion", response_model=RecommendResponse)
async def emotion(
    request: Request,
    image: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> RecommendResponse:
    settings = get_settings()
    content = await image.read()

    try:
        if len(content) > settings.max_upload_size_bytes:
            raise InvalidImageError(
                f"File exceeds {settings.max_upload_size_bytes // 1024 // 1024}MB limit"
            )

        mime = _detect_image_mime(content[:16])
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            raise InvalidImageError(f"Unsupported image type {mime or 'unknown'}, use JPEG or PNG")

        with metrics.recommendation_timer("emotion"):
            result = await reco_service.get_emotion_recommendations(
                image_bytes=content,
                limit=10,
                request_id=getattr(request.state, "request_id", ""),
            )
        _record("emotion", result)
        return result
    finally:
        del content
