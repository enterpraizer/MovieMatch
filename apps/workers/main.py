from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy.orm import Session

from apps.common.db.session import get_db
from apps.common.observability import install_observability
from apps.common.schemas import (
    HealthResponse,
    RecommendationMode,
    RecommendationRequest,
    RecommendationResponse,
)
from apps.common.settings import settings
from apps.workers.recommendation_worker import RecommendationWorker

app = FastAPI(title="MovieMatch Worker", version="0.1.0")
install_observability(app, service_name="worker")
worker = RecommendationWorker()


def require_internal_token(x_worker_token: str | None = Header(default=None)) -> None:
    if settings.worker_internal_token and x_worker_token != settings.worker_internal_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid worker token")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(service="worker")


@app.post("/run/{mode}", response_model=RecommendationResponse, dependencies=[Depends(require_internal_token)])
async def run_worker(mode: RecommendationMode, payload: RecommendationRequest, db: Session = Depends(get_db)) -> RecommendationResponse:
    recommendations = worker.run(db=db, mode=mode, payload=payload)
    return RecommendationResponse(
        mode=mode,
        recommendations=recommendations,
        trace_id=str(uuid4()),
    )

