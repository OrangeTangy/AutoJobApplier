from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "AutoJobApplier"
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    debug: bool = False

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str

    # ── Security ──────────────────────────────────────────────────────────────
    secret_key: str
    database_encryption_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    algorithm: str = "HS256"

    # ── LLM ───────────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 4096

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = "/app/storage"
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # ── Gmail OAuth ───────────────────────────────────────────────────────────
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:3000/api/auth/gmail/callback"

    # ── Rate Limits ───────────────────────────────────────────────────────────
    ingest_rate_limit: int = 20       # per user per hour
    llm_rate_limit: int = 50          # per user per hour
    max_llm_tasks_per_user: int = 3

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_concurrency: int = 4

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Sentry (optional) ─────────────────────────────────────────────────────
    sentry_dsn: str = ""

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL is required")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
