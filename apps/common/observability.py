from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from apps.common.settings import settings


REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "path"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "trace_id"):
            payload["trace_id"] = getattr(record, "trace_id")
        for key in ("method", "path", "status_code", "duration_ms", "attempt"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))


def configure_sentry(service_name: str) -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        server_name=service_name,
    )


def install_observability(app: FastAPI, service_name: str) -> None:
    configure_logging()
    configure_sentry(service_name)
    logger = logging.getLogger(service_name)

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next: Callable) -> Response:
        trace_id = request.headers.get("X-Trace-Id", str(uuid4()))
        request.state.trace_id = trace_id
        path = request.url.path
        method = request.method
        start = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            logger.exception("request_failed", extra={"trace_id": trace_id})
            raise
        finally:
            elapsed = time.perf_counter() - start
            REQUEST_COUNT.labels(service_name, method, path, str(status_code)).inc()
            REQUEST_DURATION.labels(service_name, method, path).observe(elapsed)
            logger.info(
                "request_complete",
                extra={
                    "trace_id": trace_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )

        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)
