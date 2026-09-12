"""Use case: assemble a job's full processing history for the API."""

from __future__ import annotations

from dataclasses import dataclass

from src.entities.audit_log import AuditLogEntry
from src.entities.execution import Execution
from src.entities.job import Job
from src.entities.work_unit import WorkUnit
from src.shared.errors import JobNotFoundError
from src.shared.types import JobId, TenantId
from src.use_cases.protocols import (
    AuditRepositoryProtocol,
    ExecutionRepositoryProtocol,
    JobRepositoryProtocol,
    WorkUnitRepositoryProtocol,
)
from src.use_cases.scope_validator import ScopeValidator


@dataclass(frozen=True, slots=True)
class ExecutionHistory:
    execution: Execution
    work_units: list[WorkUnit]


@dataclass(frozen=True, slots=True)
class JobHistory:
    job: Job
    executions: list[ExecutionHistory]
    audit_log: list[AuditLogEntry]


class GetJobHistory:
    def __init__(
        self,
        job_repo: JobRepositoryProtocol,
        execution_repo: ExecutionRepositoryProtocol,
        work_unit_repo: WorkUnitRepositoryProtocol,
        audit_repo: AuditRepositoryProtocol,
    ) -> None:
        self._job_repo = job_repo
        self._execution_repo = execution_repo
        self._work_unit_repo = work_unit_repo
        self._audit_repo = audit_repo

    async def execute(self, job_id: JobId, tenant_id: TenantId) -> JobHistory:
        job = await self._job_repo.get_by_id(job_id, tenant_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")
        ScopeValidator.ensure_job_in_tenant(job, tenant_id)

        executions = await self._execution_repo.list_by_job(job_id)
        execution_histories = [
            ExecutionHistory(
                execution=execution,
                work_units=await self._work_unit_repo.list_by_execution(execution.id),
            )
            for execution in executions
        ]
        audit_log = await self._audit_repo.list_by_job(job_id)

        return JobHistory(job=job, executions=execution_histories, audit_log=audit_log)
