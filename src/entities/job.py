"""Domain model for a Job: a single uploaded document awaiting processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.shared.constants import FileType
from src.shared.errors import InvalidJobStatusError
from src.shared.types import ExecutionId, JobId, JobStatus, TenantId, UserId


@dataclass(slots=True)
class Job:
    """A document submitted for processing.

    A Job never mutates its own history: every processing attempt is
    recorded as a separate Execution generation referenced by
    ``execution_ids``, so failed attempts remain inspectable forever.
    """

    id: JobId
    tenant_id: TenantId
    user_id: UserId
    file_path: str
    file_type: FileType
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    execution_ids: list[ExecutionId] = field(default_factory=list)

    def is_terminal_state(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED)

    def can_retry(self) -> bool:
        return self.status in (JobStatus.FAILED, JobStatus.PENDING)

    def next_generation(self) -> int:
        """The generation number the next Execution for this job should use."""
        return len(self.execution_ids)

    def register_execution(self, execution_id: ExecutionId) -> None:
        self.execution_ids.append(execution_id)
        self.status = JobStatus.PROCESSING

    def mark_completed(self) -> None:
        self.status = JobStatus.COMPLETED

    def mark_failed(self) -> None:
        self.status = JobStatus.FAILED

    def ensure_mutable(self) -> None:
        """Guard used before mutating state that only makes sense pre-completion."""
        if self.status == JobStatus.COMPLETED:
            raise InvalidJobStatusError(f"Job {self.id} is already completed")
