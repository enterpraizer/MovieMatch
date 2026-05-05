import time
from typing import Any, Awaitable, Callable

import structlog
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/v1/recommendations/emotion": (10, 60),
    "/v1/recommendations/collaborative": (60, 60),
    "/v1/recommendations/search": (60, 60),
    "/v1/auth/login": (10, 60),
    "/v1/auth/register": (5, 60),
}
DEFAULT_RATE: tuple[int, int] = (120, 60)
SKIP_PATHS: set[str] = {"/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, redis_url: str) -> None:
        super().__init__(app)
        self._redis_url = redis_url
        self._redis: Any = None

    async def _get_redis(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis

            self._redis = await aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _get_limit(self, path: str) -> tuple[int, int]:
        for prefix, limit in RATE_LIMITS.items():
            if path.startswith(prefix):
                return limit
        return DEFAULT_RATE

    def _get_identifier(self, request: Request) -> str:
        user = getattr(getattr(request.state, "user", None), "id", None)
        if user:
            return f"u:{user}"
        return f"ip:{request.client.host if request.client else 'unknown'}"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        max_req, window = self._get_limit(request.url.path)
        identifier = self._get_identifier(request)
        window_key = int(time.time() // window)
        key = f"rl:{identifier}:{request.url.path}:{window_key}"

        try:
            redis = await self._get_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window + 1)

            if count > max_req:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": f"Rate limit: {max_req} requests per {window}s",
                            "request_id": getattr(request.state, "request_id", ""),
                        }
                    },
                    headers={
                        "Retry-After": str(window),
                        "X-RateLimit-Limit": str(max_req),
                    },
                )
        except Exception as e:
            structlog.get_logger().warning("rate_limit_redis_error", error=str(e))
            # Fail open — don't block requests when Redis is down

        return await call_next(request)
