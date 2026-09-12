"""Immutable audit log entry.

Audit entries are created once via :meth:`AuditLogEntry.record` and never
mutated afterwards. The dataclass is frozen so any accidental attempt to
edit a historical entry fails fast at the type level.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.shared.constants import AuditEventType
from src.shared.types import AuditLogId, ExecutionId, JobId


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    id: AuditLogId
    job_id: JobId
    execution_id: ExecutionId | None
    event_type: AuditEventType
    message: str
    created_at: datetime

    @classmethod
    def record(
        cls,
        *,
        id: AuditLogId,
        job_id: JobId,
        execution_id: ExecutionId | None,
        event_type: AuditEventType,
        message: str,
    ) -> AuditLogEntry:
        return cls(
            id=id,
            job_id=job_id,
            execution_id=execution_id,
            event_type=event_type,
            message=message,
            created_at=datetime.now(UTC),
        )
