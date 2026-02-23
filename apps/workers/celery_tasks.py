from __future__ import annotations

from uuid import uuid4

from apps.common.cache import CacheClient
from apps.common.db.session import SessionLocal
from apps.common.schemas import RecommendationMode, RecommendationRequest, RecommendationResponse
from apps.common.settings import settings
from apps.orchestrator.recommender import build_recommendations, persist_recommendation_result
from apps.workers.celery_app import celery_app

cache = CacheClient()


def _execute_mode(mode: RecommendationMode, payload_data: dict) -> dict:
    payload = RecommendationRequest.model_validate(payload_data)
    cache_key = f"rec:{mode.value}:{payload.user_id}:{payload.query or ''}:{payload.top_k}"
    cached = cache.get_json(cache_key)
    if cached:
        return cached

    with SessionLocal() as db:
        recommendations = build_recommendations(db=db, mode=mode, payload=payload)
        if not recommendations and mode != RecommendationMode.collaborative:
            fallback_payload = RecommendationRequest(
                user_id=payload.user_id,
                query=None,
                top_k=payload.top_k,
            )
            recommendations = build_recommendations(
                db=db,
                mode=RecommendationMode.collaborative,
                payload=fallback_payload,
            )

        if not recommendations:
            raise RuntimeError("No recommendations produced")

        persist_recommendation_result(db=db, mode=mode, payload=payload, recommendations=recommendations)
        db.commit()

    response = RecommendationResponse(
        mode=mode,
        recommendations=recommendations,
        trace_id=str(uuid4()),
    ).model_dump(mode="json")
    cache.set_json(cache_key, response, ttl_seconds=settings.recommendation_cache_ttl_seconds)
    return response


@celery_app.task(
    name="workers.run_collaborative",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": settings.worker_retry_attempts},
)
def run_collaborative(self, payload_data: dict) -> dict:  # noqa: ANN001
    return _execute_mode(RecommendationMode.collaborative, payload_data)


@celery_app.task(
    name="workers.run_nlp",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": settings.worker_retry_attempts},
)
def run_nlp(self, payload_data: dict) -> dict:  # noqa: ANN001
    return _execute_mode(RecommendationMode.nlp, payload_data)


@celery_app.task(
    name="workers.run_mood",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": settings.worker_retry_attempts},
)
def run_mood(self, payload_data: dict) -> dict:  # noqa: ANN001
    return _execute_mode(RecommendationMode.mood, payload_data)

