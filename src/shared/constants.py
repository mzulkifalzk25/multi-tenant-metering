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
