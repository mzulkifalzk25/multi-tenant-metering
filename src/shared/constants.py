"""Enums and magic numbers that encode business rules for the pipeline."""

from __future__ import annotations

from enum import Enum


class FileType(str, Enum):
    PDF = "pdf"
    IMAGE = "image"
    VIDEO = "video"


class WorkUnitType(str, Enum):
    PAGE = "page"
    IMAGE = "image"
    FRAME = "frame"


class StageName(str, Enum):
    INGESTED = "ingested"
    EXPANDED = "expanded"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class AuditEventType(str, Enum):
    JOB_INGESTED = "job_ingested"
    EXECUTION_STARTED = "execution_started"
    WORK_UNIT_STARTED = "work_unit_started"
    WORK_UNIT_COMPLETED = "work_unit_completed"
    WORK_UNIT_FAILED = "work_unit_failed"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    RECOVERY_RESCHEDULED = "recovery_rescheduled"


# --- Retry / backoff policy -------------------------------------------------

DEFAULT_MAX_RETRY_ATTEMPTS = 5
DEFAULT_BACKOFF_BASE_SECONDS = 2
DEFAULT_BACKOFF_MAX_SECONDS = 900

# --- Recovery scheduler ------------------------------------------------------

DEFAULT_STUCK_JOB_THRESHOLD_MINUTES = 15
DEFAULT_RECOVERY_SCAN_INTERVAL_SECONDS = 300

# --- Document processing -----------------------------------------------------

DEFAULT_MAX_FILE_SIZE_MB = 500
VIDEO_FRAME_SAMPLE_INTERVAL_SECONDS = 10


def compute_backoff_seconds(
    attempt: int,
    base_seconds: int = DEFAULT_BACKOFF_BASE_SECONDS,
    max_seconds: int = DEFAULT_BACKOFF_MAX_SECONDS,
) -> int:
    """Exponential backoff with a ceiling: base * 2**attempt, capped."""
    if attempt < 0:
        raise ValueError("attempt must be non-negative")
    # int ** int is typed as returning Any in typeshed (a negative exponent
    # would produce a float), even though attempt is guaranteed >= 0 here.
    doubled: int = base_seconds * (2**attempt)
    return min(doubled, max_seconds)
