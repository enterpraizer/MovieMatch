import logging

from celery.result import AsyncResult
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.common.auth import create_token_pair, decode_token, hash_password, require_access_token, verify_password
from apps.common.db.models import User
from apps.common.db.session import get_db
from apps.common.observability import install_observability
from apps.common.schemas import (
    HealthResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RecommendationJobStatusResponse,
    RecommendationJobSubmitResponse,
    RecommendationMode,
    RecommendationRequest,
    RecommendationResponse,
    TokenPayload,
)
from apps.common.settings import settings
from apps.workers.celery_app import celery_app
from apps.workers.celery_tasks import run_collaborative, run_mood, run_nlp

app = FastAPI(title="MovieMatch Orchestrator", version="0.1.0")
install_observability(app, service_name="orchestrator")
logger = logging.getLogger("orchestrator")


def _submit_recommendation_task(mode: RecommendationMode, payload: RecommendationRequest) -> str:
    payload_data = payload.model_dump(mode="json")
    if mode == RecommendationMode.collaborative:
        task = run_collaborative.apply_async(args=[payload_data], queue="cf")
    elif mode == RecommendationMode.nlp:
        task = run_nlp.apply_async(args=[payload_data], queue="nlp")
    else:
        task = run_mood.apply_async(args=[payload_data], queue="mood")
    return task.id


def _map_celery_state(state: str) -> str:
    mapping = {
        "PENDING": "queued",
        "RECEIVED": "queued",
        "STARTED": "running",
        "RETRY": "retry",
        "SUCCESS": "completed",
        "FAILURE": "failed",
    }
    return mapping.get(state, state.lower())


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


@app.post("/recommendations/{mode}", response_model=RecommendationJobSubmitResponse, status_code=202)
async def recommendations(
    mode: RecommendationMode,
    payload: RecommendationRequest,
    token_payload: TokenPayload = Depends(require_access_token),
) -> RecommendationJobSubmitResponse:
    payload.user_id = payload.user_id or int(token_payload.sub)
    job_id = _submit_recommendation_task(mode=mode, payload=payload)
    return RecommendationJobSubmitResponse(job_id=job_id, status="queued")


@app.get("/recommendations/jobs/{job_id}", response_model=RecommendationJobStatusResponse)
async def recommendation_job_status(
    job_id: str,
    token_payload: TokenPayload = Depends(require_access_token),  # noqa: ARG001
) -> RecommendationJobStatusResponse:
    result = AsyncResult(job_id, app=celery_app)
    mapped_status = _map_celery_state(result.state)

    if result.state == "SUCCESS":
        payload = RecommendationResponse.model_validate(result.result)
        return RecommendationJobStatusResponse(job_id=job_id, status=mapped_status, result=payload)
    if result.state == "FAILURE":
        return RecommendationJobStatusResponse(job_id=job_id, status=mapped_status, error=str(result.result))
    return RecommendationJobStatusResponse(job_id=job_id, status=mapped_status)
