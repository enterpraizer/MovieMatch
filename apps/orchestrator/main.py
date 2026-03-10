import asyncio
import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.common.auth import create_token_pair, decode_token, hash_password, require_access_token, verify_password
from apps.common.cache import CacheClient
from apps.common.db.models import User
from apps.common.db.session import get_db
from apps.common.observability import install_observability
from apps.common.schemas import (
    HealthResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RecommendationMode,
    RecommendationRequest,
    RecommendationResponse,
    TokenPayload,
)
from apps.common.settings import settings
from apps.orchestrator.recommender import persist_recommendation_result
from apps.workers.recommendation_worker import RecommendationWorker

app = FastAPI(title="MovieMatch Orchestrator", version="0.1.0")
install_observability(app, service_name="orchestrator")
logger = logging.getLogger("orchestrator")
worker = RecommendationWorker()
cache = CacheClient()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        service="orchestrator",
        details={
            "database_url": settings.database_url,
            "redis_url": settings.redis_url,
        },
    )


@app.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        if not settings.auth_auto_create_user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        user = User(email=payload.email, password_hash=hash_password(payload.password))
        db.add(user)
        db.commit()
        db.refresh(user)
    elif not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return create_token_pair(user_id=user.id, email=user.email)


@app.post("/auth/refresh", response_model=LoginResponse)
async def refresh(payload: RefreshRequest) -> LoginResponse:
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    return create_token_pair(user_id=int(token_payload.sub), email=token_payload.email)


@app.post("/recommendations/{mode}", response_model=RecommendationResponse)
async def recommendations(
    mode: RecommendationMode,
    payload: RecommendationRequest,
    request: Request,
    token_payload: TokenPayload = Depends(require_access_token),
    db: Session = Depends(get_db),
) -> RecommendationResponse:
    payload.user_id = payload.user_id or int(token_payload.sub)
    cache_key = f"rec:{mode.value}:{payload.user_id}:{payload.query or ''}:{payload.top_k}"
    cached = cache.get_json(cache_key)
    if cached:
        return RecommendationResponse.model_validate(cached)

    recommendations_list = []
    last_exc: Exception | None = None
    for attempt in range(1, settings.worker_retry_attempts + 1):
        try:
            recommendations_list = await asyncio.wait_for(
                asyncio.to_thread(worker.run, db, mode, payload),
                timeout=settings.worker_timeout_seconds,
            )
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "worker_retry",
                extra={
                    "trace_id": getattr(request.state, "trace_id", "n/a"),
                    "attempt": attempt,
                    "path": f"/recommendations/{mode.value}",
                },
            )
            if attempt < settings.worker_retry_attempts:
                await asyncio.sleep(settings.worker_retry_backoff_seconds * attempt)

    if not recommendations_list and mode != RecommendationMode.collaborative:
        try:
            fallback_payload = RecommendationRequest(
                user_id=payload.user_id,
                query=None,
                top_k=payload.top_k,
            )
            recommendations_list = await asyncio.wait_for(
                asyncio.to_thread(worker.run, db, RecommendationMode.collaborative, fallback_payload),
                timeout=settings.worker_timeout_seconds,
            )
        except Exception:
            pass

    if not recommendations_list:
        raise HTTPException(status_code=503, detail=f"Recommendation worker unavailable: {last_exc}")

    persist_recommendation_result(db=db, mode=mode, payload=payload, recommendations=recommendations_list)
    db.commit()
    response = RecommendationResponse(
        mode=mode,
        recommendations=recommendations_list,
        trace_id=str(uuid4()),
    )
    cache.set_json(
        cache_key,
        response.model_dump(mode="json"),
        ttl_seconds=settings.recommendation_cache_ttl_seconds,
    )
    return response
