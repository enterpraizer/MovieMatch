import logging
import os
import time
import uuid
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_is_dev = os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG"
_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
_level = getattr(logging, _level_name, logging.INFO)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer() if _is_dev else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(_level),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_ns = time.perf_counter_ns()

        logger = structlog.get_logger().bind(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
            logger.info(
                "http_request",
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_agent=request.headers.get("user-agent", "")[:100],
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(duration_ms)
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
            logger.error("http_request_failed", error=str(exc), duration_ms=duration_ms)
            raise
