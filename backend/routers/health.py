import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import metrics
from config import get_settings
from db.database import execute_val

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _check_ml(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url.rstrip('/')}/health")
            return "ok" if resp.status_code == 200 else "degraded"
    except Exception:
        return "degraded"


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    settings = get_settings()
    checks: dict[str, Any] = {}

    try:
        await asyncio.wait_for(execute_val("SELECT 1"), timeout=2.0)
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    try:
        redis = request.app.state.redis
        await asyncio.wait_for(redis.ping(), timeout=2.0)
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    recsys, nlp, cv = await asyncio.gather(
        _check_ml(settings.ml_recsys_url),
        _check_ml(settings.ml_nlp_url),
        _check_ml(settings.ml_cv_url),
    )
    checks["recsys"] = recsys
    checks["nlp"] = nlp
    checks["cv"] = cv

    metrics.ml_service_up.labels(service="recsys").set(1 if recsys == "ok" else 0)
    metrics.ml_service_up.labels(service="nlp").set(1 if nlp == "ok" else 0)
    metrics.ml_service_up.labels(service="cv").set(1 if cv == "ok" else 0)

    is_ready = checks["database"] == "ok" and checks["redis"] == "ok"
    status_code = 200 if is_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "degraded",
            "checks": checks,
        },
    )
