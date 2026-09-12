"""Environment-driven configuration, loaded once at process startup."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from src.shared.constants import (
    DEFAULT_BACKOFF_BASE_SECONDS,
    DEFAULT_MAX_FILE_SIZE_MB,
    DEFAULT_MAX_RETRY_ATTEMPTS,
    DEFAULT_RECOVERY_SCAN_INTERVAL_SECONDS,
    DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
)


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    job_ingestion_channel: str
    celery_broker_url: str
    celery_result_backend: str
    celery_max_retries: int
    celery_retry_backoff_base_seconds: int
    max_file_size_mb: int
    stuck_job_threshold_minutes: int
    recovery_scan_interval_seconds: int
    llm_api_key: str | None
    llm_model: str
    port: int
    environment: str
    log_level: str

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()
        return cls(
            database_url=_require("DATABASE_URL"),
            redis_url=_require("REDIS_URL"),
            job_ingestion_channel=os.environ.get("JOB_INGESTION_CHANNEL", "jobs.ingest"),
            celery_broker_url=_require("CELERY_BROKER_URL"),
            celery_result_backend=_require("CELERY_RESULT_BACKEND"),
            celery_max_retries=int(
                os.environ.get("CELERY_MAX_RETRIES", DEFAULT_MAX_RETRY_ATTEMPTS)
            ),
            celery_retry_backoff_base_seconds=int(
                os.environ.get("CELERY_RETRY_BACKOFF_BASE_SECONDS", DEFAULT_BACKOFF_BASE_SECONDS)
            ),
            max_file_size_mb=int(os.environ.get("MAX_FILE_SIZE_MB", DEFAULT_MAX_FILE_SIZE_MB)),
            stuck_job_threshold_minutes=int(
                os.environ.get("STUCK_JOB_THRESHOLD_MINUTES", DEFAULT_STUCK_JOB_THRESHOLD_MINUTES)
            ),
            recovery_scan_interval_seconds=int(
                os.environ.get(
                    "RECOVERY_SCAN_INTERVAL_SECONDS", DEFAULT_RECOVERY_SCAN_INTERVAL_SECONDS
                )
            ),
            llm_api_key=os.environ.get("LLM_API_KEY") or None,
            llm_model=os.environ.get("LLM_MODEL", "openrouter/auto"),
            port=int(os.environ.get("PORT", 8000)),
            environment=os.environ.get("ENVIRONMENT", "development"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
