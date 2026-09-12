"""Domain model for an Execution: one non-destructive attempt at a Job.

Every retry creates a *new* Execution with an incremented ``generation``
rather than mutating a previous one. This keeps a full, immutable history
of every attempt a job has gone through, which the audit log and recovery
scheduler both rely on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.shared.types import ExecutionId, JobId, JobStatus, WorkUnitId


@dataclass(slots=True)
class Execution:
    id: ExecutionId
    job_id: JobId
    generation: int
    status: JobStatus = JobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    work_unit_ids: list[WorkUnitId] = field(default_factory=list)

    def mark_started(self) -> None:
        """Idempotent: resuming an already-started execution (a Celery retry
        of the same generation) must not reset ``started_at``, or the
        recovery scheduler's stuck-execution detection would never fire."""
        if self.started_at is None:
            self.started_at = datetime.now(UTC)
        self.status = JobStatus.PROCESSING

    def mark_completed(self) -> None:
        self.completed_at = datetime.now(UTC)
        self.status = JobStatus.COMPLETED

    def mark_failed(self) -> None:
        self.completed_at = datetime.now(UTC)
        self.status = JobStatus.FAILED

    def register_work_unit(self, work_unit_id: WorkUnitId) -> None:
        self.work_unit_ids.append(work_unit_id)

    def is_stuck(self, *, now: datetime, threshold_minutes: int) -> bool:
        """An execution is stuck if it started processing and never finished
        within the recovery threshold."""
        if self.status != JobStatus.PROCESSING or self.started_at is None:
            return False
        elapsed = now - self.started_at
        return elapsed.total_seconds() > threshold_minutes * 60
