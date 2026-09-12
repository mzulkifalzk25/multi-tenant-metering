"""Use case: process a Job to completion, idempotently and non-destructively.

Two distinct retry paths are supported:

* **Idempotent resume** -- pass the same ``execution_id`` again (this is
  what a Celery task retry does). Already-completed work units are
  skipped; only unfinished ones are (re)processed. Safe to call any
  number of times for the same execution.
* **Non-destructive retry** -- omit ``execution_id`` after a prior
  execution reached a terminal state. A brand new Execution generation is
  created; the failed generation's row and audit trail are left untouched
  forever.
"""

from __future__ import annotations

from src.entities.execution import Execution
from src.entities.job import Job
from src.entities.status import Status
from src.entities.work_unit import WorkUnit
from src.shared.constants import AuditEventType, StageName
from src.shared.errors import ExecutionNotFoundError, JobNotFoundError
from src.shared.types import ExecutionId, JobId, TenantId, WorkUnitId, WorkUnitStatus
from src.use_cases.protocols import (
    AuditRepositoryProtocol,
    DocumentProcessorProtocol,
    ExecutionRepositoryProtocol,
    JobRepositoryProtocol,
    StatusRepositoryProtocol,
    UnitOfWorkProtocol,
    WorkUnitRepositoryProtocol,
)
from src.use_cases.scope_validator import ScopeValidator


class ProcessJob:
    def __init__(
        self,
        job_repo: JobRepositoryProtocol,
        execution_repo: ExecutionRepositoryProtocol,
        work_unit_repo: WorkUnitRepositoryProtocol,
        status_repo: StatusRepositoryProtocol,
        audit_repo: AuditRepositoryProtocol,
        document_processor: DocumentProcessorProtocol,
        unit_of_work: UnitOfWorkProtocol,
    ) -> None:
        self._job_repo = job_repo
        self._execution_repo = execution_repo
        self._work_unit_repo = work_unit_repo
        self._status_repo = status_repo
        self._audit_repo = audit_repo
        self._document_processor = document_processor
        self._unit_of_work = unit_of_work

    async def execute(
        self,
        job_id: JobId,
        tenant_id: TenantId,
        execution_id: ExecutionId | None = None,
    ) -> Execution:
        job = await self._job_repo.get_by_id(job_id, tenant_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")
        ScopeValidator.ensure_job_in_tenant(job, tenant_id)
        job.ensure_mutable()

        execution, is_new = await self._get_or_create_execution(job, execution_id)
        execution.mark_started()
        await self._execution_repo.save(execution)
        if is_new:
            job.register_execution(execution.id)
            await self._job_repo.save(job)
            await self._audit_repo.record(
                job_id=job.id,
                execution_id=execution.id,
                event_type=AuditEventType.EXECUTION_STARTED,
                message=f"Execution generation {execution.generation} started",
            )
            await self._unit_of_work.commit()

        status = await self._status_repo.get_by_execution(execution.id)
        if status is None:
            status = Status(execution_id=execution.id)
            await self._status_repo.upsert(status)

        work_units = await self._ensure_work_units_expanded(job, execution, status)

        if status.stage in (StageName.EXPANDED, StageName.FAILED):
            status.advance(StageName.EXECUTING)
            await self._status_repo.upsert(status)

        all_succeeded = await self._process_work_units(job, work_units)

        if all_succeeded:
            execution.mark_completed()
            job.mark_completed()
            status.advance(StageName.COMPLETED)
            await self._audit_repo.record(
                job_id=job.id,
                execution_id=execution.id,
                event_type=AuditEventType.EXECUTION_COMPLETED,
                message=f"Execution generation {execution.generation} completed",
            )
        else:
            execution.mark_failed()
            job.mark_failed()
            status.advance(StageName.FAILED)
            await self._audit_repo.record(
                job_id=job.id,
                execution_id=execution.id,
                event_type=AuditEventType.EXECUTION_FAILED,
                message=f"Execution generation {execution.generation} failed: "
                "one or more work units did not complete",
            )

        await self._execution_repo.save(execution)
        await self._job_repo.save(job)
        await self._status_repo.upsert(status)
        await self._unit_of_work.commit()
        return execution

    async def _get_or_create_execution(
        self, job: Job, execution_id: ExecutionId | None
    ) -> tuple[Execution, bool]:
        if execution_id is not None:
            execution = await self._execution_repo.get_by_id(execution_id)
            if execution is None or execution.job_id != job.id:
                raise ExecutionNotFoundError(f"Execution {execution_id} not found for job {job.id}")
            return execution, False

        generation = job.next_generation()
        execution = Execution(
            id=ExecutionId(f"{job.id}::gen-{generation}"),
            job_id=job.id,
            generation=generation,
        )
        return execution, True

    async def _ensure_work_units_expanded(
        self, job: Job, execution: Execution, status: Status
    ) -> list[WorkUnit]:
        if status.stage != StageName.INGESTED:
            return await self._work_unit_repo.list_by_execution(execution.id)

        specs = await self._document_processor.expand(job)
        work_units = [
            WorkUnit(
                id=WorkUnitId(
                    WorkUnit.idempotency_key(execution.id, spec.unit_type, spec.unit_number)
                ),
                job_id=job.id,
                execution_id=execution.id,
                unit_type=spec.unit_type,
                unit_number=spec.unit_number,
            )
            for spec in specs
        ]
        await self._work_unit_repo.save_many(work_units)
        status.advance(StageName.EXPANDED)
        await self._status_repo.upsert(status)
        await self._unit_of_work.commit()
        return work_units

    async def _process_work_units(self, job: Job, work_units: list[WorkUnit]) -> bool:
        all_succeeded = True
        for work_unit in work_units:
            if work_unit.status == WorkUnitStatus.COMPLETED:
                continue

            work_unit.mark_processing()
            await self._work_unit_repo.save(work_unit)
            await self._audit_repo.record(
                job_id=job.id,
                execution_id=work_unit.execution_id,
                event_type=AuditEventType.WORK_UNIT_STARTED,
                message=f"Work unit {work_unit.unit_type.value} #{work_unit.unit_number} started",
            )
            try:
                await self._document_processor.process_unit(job, work_unit)
            except Exception as exc:  # noqa: BLE001 - per-item isolation by design
                all_succeeded = False
                work_unit.mark_failed(str(exc))
                await self._work_unit_repo.save(work_unit)
                await self._audit_repo.record(
                    job_id=job.id,
                    execution_id=work_unit.execution_id,
                    event_type=AuditEventType.WORK_UNIT_FAILED,
                    message=(
                        f"Work unit {work_unit.unit_type.value} #{work_unit.unit_number} "
                        f"failed: {exc}"
                    ),
                )
                await self._unit_of_work.commit()
                continue

            work_unit.mark_completed()
            await self._work_unit_repo.save(work_unit)
            await self._audit_repo.record(
                job_id=job.id,
                execution_id=work_unit.execution_id,
                event_type=AuditEventType.WORK_UNIT_COMPLETED,
                message=f"Work unit {work_unit.unit_type.value} #{work_unit.unit_number} completed",
            )
            await self._unit_of_work.commit()
        return all_succeeded
