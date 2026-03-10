import asyncio
import logging

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
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
    RecommendationMode,
    RecommendationRequest,
    RecommendationResponse,
    TokenPayload,
)
from apps.common.settings import settings

app = FastAPI(title="MovieMatch Gateway", version="0.1.0")
install_observability(app, service_name="gateway")
logger = logging.getLogger("gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        service="gateway",
        details={
            "orchestrator_url": settings.orchestrator_url,
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
) -> RecommendationResponse:
    payload.user_id = payload.user_id or int(token_payload.sub)
    url = f"{settings.orchestrator_url}/recommendations/{mode.value}"
    headers = {}
    auth_header = request.headers.get("Authorization")
    if auth_header:
        headers["Authorization"] = auth_header
    response: httpx.Response | None = None
    async with httpx.AsyncClient(timeout=settings.external_request_timeout_seconds) as client:
        last_exc: Exception | None = None
        for attempt in range(1, settings.external_request_retry_attempts + 1):
            try:
                response = await client.post(url, json=payload.model_dump(), headers=headers)
                response.raise_for_status()
                break
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(
                    "orchestrator_request_retry",
                    extra={
                        "trace_id": getattr(request.state, "trace_id", "n/a"),
                        "attempt": attempt,
                        "path": f"/recommendations/{mode.value}",
                    },
                )
                if attempt < settings.external_request_retry_attempts:
                    await asyncio.sleep(settings.external_request_retry_backoff_seconds * attempt)

        if response is None:
            raise HTTPException(status_code=502, detail=f"Orchestrator unavailable: {last_exc}") from last_exc

    return RecommendationResponse.model_validate(response.json())
