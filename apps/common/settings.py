import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    orchestrator_url: str = os.getenv("ORCHESTRATOR_URL", "http://localhost:8001")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "moviematch")
    postgres_user: str = os.getenv("POSTGRES_USER", "moviematch")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "moviematch")
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    refresh_token_expire_days: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    auth_auto_create_user: bool = _as_bool(os.getenv("AUTH_AUTO_CREATE_USER"), default=True)
    recommendation_cache_ttl_seconds: int = int(os.getenv("RECOMMENDATION_CACHE_TTL_SECONDS", "300"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    external_request_timeout_seconds: float = float(os.getenv("EXTERNAL_REQUEST_TIMEOUT_SECONDS", "8"))
    external_request_retry_attempts: int = int(os.getenv("EXTERNAL_REQUEST_RETRY_ATTEMPTS", "3"))
    external_request_retry_backoff_seconds: float = float(os.getenv("EXTERNAL_REQUEST_RETRY_BACKOFF_SECONDS", "0.25"))
    worker_timeout_seconds: float = float(os.getenv("WORKER_TIMEOUT_SECONDS", "5"))
    worker_retry_attempts: int = int(os.getenv("WORKER_RETRY_ATTEMPTS", "2"))
    worker_retry_backoff_seconds: float = float(os.getenv("WORKER_RETRY_BACKOFF_SECONDS", "0.2"))
    celery_task_always_eager: bool = _as_bool(os.getenv("CELERY_TASK_ALWAYS_EAGER"), default=False)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    sentry_environment: str = os.getenv("SENTRY_ENVIRONMENT", "development")
    sentry_traces_sample_rate: float = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    @property
    def database_url(self) -> str:
        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
