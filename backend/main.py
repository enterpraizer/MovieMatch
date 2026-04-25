from contextlib import asynccontextmanager
from typing import AsyncIterator

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from config import get_settings
from db.database import close_db_pool, init_db_pool
from exceptions import AppException
from middleware.logging import RequestLoggingMiddleware
from middleware.rate_limit import RateLimitMiddleware
from routers import auth, health, movies, ratings, recommendations, watchlist


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger = structlog.get_logger()

    logger.info("application_starting", version="1.0.0")

    await init_db_pool()
    logger.info("database_pool_ready")

    app.state.redis = await aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        max_connections=20,
    )
    logger.info("redis_connected")

    logger.info("application_ready")
    yield

    await close_db_pool()
    await app.state.redis.aclose()
    logger.info("application_stopped")


settings = get_settings()

app = FastAPI(
    title="MovieMatch API",
    description="Hybrid AI movie recommendation system",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Middleware order: added last = executes first on request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)
app.add_middleware(RateLimitMiddleware, redis_url=settings.redis_url)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(AppException)
async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": getattr(request.state, "request_id", ""),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request data validation failed",
                "details": [
                    {
                        "field": ".".join(str(loc) for loc in e["loc"]),
                        "msg": e["msg"],
                        "type": e["type"],
                    }
                    for e in exc.errors()
                ],
                "request_id": getattr(request.state, "request_id", ""),
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    structlog.get_logger().error(
        "unhandled_exception",
        error=str(exc),
        error_type=type(exc).__name__,
        path=str(request.url.path),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "request_id": getattr(request.state, "request_id", ""),
            }
        },
    )


app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/v1/auth", tags=["Auth"])
app.include_router(movies.router, prefix="/v1/movies", tags=["Movies"])
app.include_router(ratings.router, prefix="/v1/ratings", tags=["Ratings"])
app.include_router(
    recommendations.router, prefix="/v1/recommendations", tags=["Recommendations"]
)
app.include_router(watchlist.router, prefix="/v1/watchlist", tags=["Watchlist"])


Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/ready", "/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
