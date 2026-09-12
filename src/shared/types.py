"""Branded domain identifiers and core enums shared across all layers."""

from __future__ import annotations

from enum import Enum
from typing import NewType

TenantId = NewType("TenantId", str)
JobId = NewType("JobId", str)
ExecutionId = NewType("ExecutionId", str)
WorkUnitId = NewType("WorkUnitId", str)
UserId = NewType("UserId", str)
AuditLogId = NewType("AuditLogId", str)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkUnitStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"

    def is_terminal(self) -> bool:
        return self in (WorkUnitStatus.COMPLETED, WorkUnitStatus.FAILED)
