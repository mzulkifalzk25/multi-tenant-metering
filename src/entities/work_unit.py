"""Domain model for a WorkUnit: the smallest unit of fan-out work.

A PDF fans out into one WorkUnit per page, a video into one per sampled
frame, and an image into a single unit. Each unit is addressed by an
``idempotency_key`` derived deterministically from its coordinates within
an execution, so re-running the same execution generation twice can never
create duplicate units.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.shared.constants import WorkUnitType
from src.shared.types import ExecutionId, JobId, WorkUnitId, WorkUnitStatus


@dataclass(slots=True)
class WorkUnit:
    id: WorkUnitId
    job_id: JobId
    execution_id: ExecutionId
    unit_type: WorkUnitType
    unit_number: int
    status: WorkUnitStatus = WorkUnitStatus.PENDING
    error: str | None = None

    @staticmethod
    def idempotency_key(
        execution_id: ExecutionId, unit_type: WorkUnitType, unit_number: int
    ) -> str:
        return f"{execution_id}:{unit_type.value}:{unit_number}"

    def mark_processing(self) -> None:
        self.status = WorkUnitStatus.PROCESSING
        self.error = None

    def mark_completed(self) -> None:
        self.status = WorkUnitStatus.COMPLETED
        self.error = None

    def mark_failed(self, error: str) -> None:
        self.status = WorkUnitStatus.FAILED
        self.error = error

    def mark_retrying(self, error: str) -> None:
        self.status = WorkUnitStatus.RETRYING
        self.error = error
