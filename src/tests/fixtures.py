"""Entity factories and in-memory fake repositories for unit tests.

The fakes satisfy the Protocols in ``src.use_cases.protocols`` structurally
-- no inheritance needed -- so use cases can be exercised without a real
database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from src.entities.audit_log import AuditLogEntry
from src.entities.execution import Execution
from src.entities.job import Job
from src.entities.status import Status
from src.entities.tenant import Tenant
from src.entities.work_unit import WorkUnit
from src.shared.constants import AuditEventType, FileType, WorkUnitType
from src.shared.errors import DocumentProcessingError
from src.shared.types import (
    AuditLogId,
    ExecutionId,
    JobId,
    JobStatus,
    TenantId,
    UserId,
    WorkUnitId,
)
from src.use_cases.protocols import WorkUnitSpec


def make_tenant(*, tenant_id: str = "tenant-1", is_active: bool = True) -> Tenant:
    return Tenant(id=TenantId(tenant_id), name="Acme Inc", is_active=is_active)


def make_job(
    *,
    job_id: str = "job-1",
    tenant_id: str = "tenant-1",
    file_type: FileType = FileType.PDF,
    status: JobStatus = JobStatus.PENDING,
) -> Job:
    return Job(
        id=JobId(job_id),
        tenant_id=TenantId(tenant_id),
        user_id=UserId("user-1"),
        file_path="/uploads/document.pdf",
        file_type=file_type,
        status=status,
    )


def make_execution(
    *, execution_id: str = "job-1::gen-0", job_id: str = "job-1", generation: int = 0
) -> Execution:
    return Execution(id=ExecutionId(execution_id), job_id=JobId(job_id), generation=generation)


class FakeTenantRepository:
    def __init__(self, tenants: list[Tenant] | None = None) -> None:
        self._tenants: dict[TenantId, Tenant] = {t.id: t for t in (tenants or [])}

    async def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        return self._tenants.get(tenant_id)

    async def save(self, tenant: Tenant) -> None:
        self._tenants[tenant.id] = tenant


class FakeJobRepository:
    def __init__(self, jobs: list[Job] | None = None) -> None:
        self._jobs: dict[JobId, Job] = {j.id: j for j in (jobs or [])}

    async def get_by_id(self, job_id: JobId, tenant_id: TenantId) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            return None
        return job

    async def get_by_id_unscoped(self, job_id: JobId) -> Job | None:
        return self._jobs.get(job_id)

    async def save(self, job: Job) -> None:
        self._jobs[job.id] = job


class FakeExecutionRepository:
    def __init__(self, executions: list[Execution] | None = None) -> None:
        self._executions: dict[ExecutionId, Execution] = {e.id: e for e in (executions or [])}

    async def get_by_id(self, execution_id: ExecutionId) -> Execution | None:
        return self._executions.get(execution_id)

    async def save(self, execution: Execution) -> None:
        self._executions[execution.id] = execution

    async def list_by_job(self, job_id: JobId) -> list[Execution]:
        return sorted(
            (e for e in self._executions.values() if e.job_id == job_id),
            key=lambda e: e.generation,
        )

    async def list_stuck_processing(
        self, *, now: datetime, threshold_minutes: int
    ) -> list[Execution]:
        return [
            e
            for e in self._executions.values()
            if e.is_stuck(now=now, threshold_minutes=threshold_minutes)
        ]


class FakeWorkUnitRepository:
    def __init__(self) -> None:
        self._work_units: dict[WorkUnitId, WorkUnit] = {}

    async def save(self, work_unit: WorkUnit) -> None:
        self._work_units[work_unit.id] = work_unit

    async def save_many(self, work_units: list[WorkUnit]) -> None:
        for work_unit in work_units:
            existing = self._work_units.get(work_unit.id)
            self._work_units[work_unit.id] = existing if existing is not None else work_unit

    async def list_by_execution(self, execution_id: ExecutionId) -> list[WorkUnit]:
        return sorted(
            (wu for wu in self._work_units.values() if wu.execution_id == execution_id),
            key=lambda wu: wu.unit_number,
        )

    async def get_by_id(self, work_unit_id: WorkUnitId) -> WorkUnit | None:
        return self._work_units.get(work_unit_id)


class FakeStatusRepository:
    def __init__(self) -> None:
        self._statuses: dict[ExecutionId, Status] = {}

    async def upsert(self, status: Status) -> None:
        self._statuses[status.execution_id] = status

    async def get_by_execution(self, execution_id: ExecutionId) -> Status | None:
        return self._statuses.get(execution_id)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.entries: list[AuditLogEntry] = []

    async def record(
        self,
        *,
        job_id: JobId,
        execution_id: ExecutionId | None,
        event_type: AuditEventType,
        message: str,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            id=AuditLogId(str(uuid.uuid4())),
            job_id=job_id,
            execution_id=execution_id,
            event_type=event_type,
            message=message,
            created_at=datetime.now(UTC),
        )
        self.entries.append(entry)
        return entry

    async def list_by_job(self, job_id: JobId) -> list[AuditLogEntry]:
        return [e for e in self.entries if e.job_id == job_id]


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commit_count = 0

    async def commit(self) -> None:
        self.commit_count += 1


class FakeJobDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[tuple[JobId, TenantId]] = []

    def dispatch(self, job_id: JobId, tenant_id: TenantId) -> None:
        self.dispatched.append((job_id, tenant_id))


class FakeDocumentProcessor:
    """Fans a job out into a fixed number of units and always succeeds,
    unless ``fail_unit_numbers`` names units that should raise instead."""

    def __init__(
        self, *, unit_count: int = 3, fail_unit_numbers: frozenset[int] = frozenset()
    ) -> None:
        self._unit_count = unit_count
        self._fail_unit_numbers = fail_unit_numbers
        self.processed: list[WorkUnit] = []

    async def expand(self, job: Job) -> list[WorkUnitSpec]:
        return [WorkUnitSpec(WorkUnitType.PAGE, n) for n in range(self._unit_count)]

    async def process_unit(self, job: Job, work_unit: WorkUnit) -> None:
        self.processed.append(work_unit)
        if work_unit.unit_number in self._fail_unit_numbers:
            raise DocumentProcessingError(f"unit {work_unit.unit_number} failed")
