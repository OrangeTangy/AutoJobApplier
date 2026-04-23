from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_app_data_dir() -> Path:
    """Return the per-user application data directory for persistent storage."""
    if override := os.environ.get("AUTOJOB_DATA_DIR"):
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "AutoJobApplier"


APP_DATA_DIR = _default_app_data_dir()
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///{(APP_DATA_DIR / 'autojobapplier.db').as_posix()}"
_DEFAULT_STORAGE_PATH = str(APP_DATA_DIR / "storage")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_name: str = "AutoJobApplier"
    environment: Literal["development", "staging", "production"] = "production"
    log_level: str = "INFO"
    debug: bool = False
    app_data_dir: str = str(APP_DATA_DIR)

    # ── Desktop launcher ──────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True

    # ── Database (SQLite by default) ──────────────────────────────────────────
    database_url: str = _DEFAULT_SQLITE_URL
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # ── Redis (optional — unused in desktop mode) ─────────────────────────────
    redis_url: str = ""

    # ── Security ──────────────────────────────────────────────────────────────
    secret_key: str = ""
    database_encryption_key: str = ""
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30
    algorithm: str = "HS256"

    # ── LLM (optional — not required) ─────────────────────────────────────────
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 4096

    # ── Storage ───────────────────────────────────────────────────────────────
    storage_backend: Literal["local", "s3"] = "local"
    local_storage_path: str = _DEFAULT_STORAGE_PATH
    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"

    # ── Gmail OAuth ───────────────────────────────────────────────────────────
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://127.0.0.1:8765/api/v1/ingestion/gmail/callback"

    # ── Rate Limits ───────────────────────────────────────────────────────────
    ingest_rate_limit: int = 60
    llm_rate_limit: int = 100
    max_llm_tasks_per_user: int = 4

    # ── In-process task queue ─────────────────────────────────────────────────
    worker_threads: int = 4
    scheduler_enabled: bool = True

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://127.0.0.1:8765", "http://localhost:8765"]

    # ── Sentry (optional) ─────────────────────────────────────────────────────
    sentry_dsn: str = ""

    # ── Frontend static assets (populated for packaged app) ───────────────────
    frontend_dist_dir: str = ""

    @field_validator("secret_key")
    @classmethod
    def _generate_secret_key(cls, v: str) -> str:
        """Persist a random secret_key to the app data dir if none is set."""
        if v:
            return v
        key_file = APP_DATA_DIR / "secret.key"
        if key_file.exists():
            return key_file.read_text().strip()
        import secrets as _secrets
        new_key = _secrets.token_urlsafe(64)
        key_file.write_text(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return new_key

    @field_validator("database_encryption_key")
    @classmethod
    def _generate_fernet_key(cls, v: str) -> str:
        """Persist a random Fernet key to the app data dir if none is set."""
        if v:
            return v
        key_file = APP_DATA_DIR / "fernet.key"
        if key_file.exists():
            return key_file.read_text().strip()
        try:
            from cryptography.fernet import Fernet
            new_key = Fernet.generate_key().decode()
        except ImportError:
            import base64
            new_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        key_file.write_text(new_key)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return new_key

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def celery_broker_url(self) -> str:
        """Kept for backwards compatibility — unused in desktop mode."""
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        """Kept for backwards compatibility — unused in desktop mode."""
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
