from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_url: str = Field(..., description="asyncpg PostgreSQL URL")
    redis_url: str = Field(..., description="Redis URL")
    secret_key: str = Field(..., min_length=32)
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=90)
    tmdb_api_key: str = Field(..., min_length=1)
    ml_recsys_url: str = Field(default="http://localhost:8001")
    ml_nlp_url: str = Field(default="http://localhost:8002")
    ml_cv_url: str = Field(default="http://localhost:8003")
    mlflow_tracking_uri: str = Field(default="./mlruns")
    log_level: str = Field(default="INFO")
    allowed_origins: list[str] = Field(default=["http://localhost:3000"])
    max_upload_size_bytes: int = Field(default=5 * 1024 * 1024)

    # Frontend base URL — used when composing verification links in emails.
    public_app_url: str = Field(default="http://localhost:3000")

    # SMTP — leave smtp_host empty to stay in dev mode (link prints to backend log).
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    smtp_start_tls: bool = Field(default=True)

    email_verification_ttl_minutes: int = Field(default=60, ge=5, le=1440)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
