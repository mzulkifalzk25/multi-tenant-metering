"""Use case: find executions stuck in PROCESSING and get them moving again.

Recovery never mutates a stuck execution's history beyond marking it
failed -- its work units and audit trail stay exactly as they were. A
fresh Execution generation is dispatched separately if the job still has
retries left, which is what makes this non-destructive.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.shared.constants import DEFAULT_MAX_RETRY_ATTEMPTS, AuditEventType
from src.use_cases.protocols import (
    AuditRepositoryProtocol,
    ExecutionRepositoryProtocol,
    JobDispatcherProtocol,
    JobRepositoryProtocol,
)


class ScheduleRecovery:
    def __init__(
        self,
        job_repo: JobRepositoryProtocol,
        execution_repo: ExecutionRepositoryProtocol,
        audit_repo: AuditRepositoryProtocol,
        dispatcher: JobDispatcherProtocol,
        *,
        stuck_threshold_minutes: int,
        max_retry_attempts: int = DEFAULT_MAX_RETRY_ATTEMPTS,
    ) -> None:
        self._job_repo = job_repo
        self._execution_repo = execution_repo
        self._audit_repo = audit_repo
        self._dispatcher = dispatcher
        self._stuck_threshold_minutes = stuck_threshold_minutes
        self._max_retry_attempts = max_retry_attempts

    async def execute(self) -> int:
        now = datetime.now(UTC)
        stuck_executions = await self._execution_repo.list_stuck_processing(
            now=now, threshold_minutes=self._stuck_threshold_minutes
        )

        recovered = 0
        for execution in stuck_executions:
            job = await self._job_repo.get_by_id_unscoped(execution.job_id)
            if job is None:
                continue

            execution.mark_failed()
            await self._execution_repo.save(execution)
            await self._audit_repo.record(
                job_id=job.id,
                execution_id=execution.id,
                event_type=AuditEventType.RECOVERY_RESCHEDULED,
                message=(
                    f"Execution generation {execution.generation} stuck beyond "
                    f"{self._stuck_threshold_minutes}m, marked failed by recovery scheduler"
                ),
            )

            if execution.generation + 1 < self._max_retry_attempts:
                job.mark_failed()
                await self._job_repo.save(job)
                self._dispatcher.dispatch(job.id, job.tenant_id)
                recovered += 1
            else:
                job.mark_failed()
                await self._job_repo.save(job)

        return recovered
