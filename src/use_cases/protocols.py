"""Ports the use-case layer depends on.

Concrete repositories (SQLAlchemy-backed) and services (Celery, document
readers) satisfy these Protocols structurally. Test doubles in
``src/tests/fixtures.py`` satisfy them the same way, with no inheritance
required, which keeps use cases decoupled from any particular
infrastructure while remaining fully typed under mypy --strict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.entities.audit_log import AuditLogEntry
from src.entities.execution import Execution
from src.entities.job import Job
from src.entities.status import Status
from src.entities.tenant import Tenant
from src.entities.work_unit import WorkUnit
from src.shared.constants import AuditEventType, WorkUnitType
from src.shared.types import ExecutionId, JobId, TenantId


class TenantRepositoryProtocol(Protocol):
    async def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        ...

    async def save(self, tenant: Tenant) -> None:
        ...


class JobRepositoryProtocol(Protocol):
    async def get_by_id(self, job_id: JobId, tenant_id: TenantId) -> Job | None:
        ...

    async def get_by_id_unscoped(self, job_id: JobId) -> Job | None:
        """Bypasses tenant scoping. Reserved for internal, non-user-facing
        callers such as the recovery scheduler, which must operate across
        tenants."""
        ...

    async def save(self, job: Job) -> None:
        ...


class ExecutionRepositoryProtocol(Protocol):
    async def get_by_id(self, execution_id: ExecutionId) -> Execution | None:
        ...

    async def save(self, execution: Execution) -> None:
        ...

    async def list_by_job(self, job_id: JobId) -> list[Execution]:
        ...

    async def list_stuck_processing(
        self, *, now: datetime, threshold_minutes: int
    ) -> list[Execution]:
        ...


class WorkUnitRepositoryProtocol(Protocol):
    async def save_many(self, work_units: list[WorkUnit]) -> None:
        ...

    async def save(self, work_unit: WorkUnit) -> None:
        ...

    async def list_by_execution(self, execution_id: ExecutionId) -> list[WorkUnit]:
        ...


class StatusRepositoryProtocol(Protocol):
    async def upsert(self, status: Status) -> None:
        ...

    async def get_by_execution(self, execution_id: ExecutionId) -> Status | None:
        ...


class AuditRepositoryProtocol(Protocol):
    async def record(
        self,
        *,
        job_id: JobId,
        execution_id: ExecutionId | None,
        event_type: AuditEventType,
        message: str,
    ) -> AuditLogEntry:
        ...

    async def list_by_job(self, job_id: JobId) -> list[AuditLogEntry]:
        ...


@dataclass(frozen=True, slots=True)
class WorkUnitSpec:
    """Plain description of a work unit to be created, before it has an id."""

    unit_type: WorkUnitType
    unit_number: int


class DocumentProcessorProtocol(Protocol):
    async def expand(self, job: Job) -> list[WorkUnitSpec]:
        ...

    async def process_unit(self, job: Job, work_unit: WorkUnit) -> None:
        ...


class JobDispatcherProtocol(Protocol):
    def dispatch(self, job_id: JobId, tenant_id: TenantId) -> None:
        ...


class UnitOfWorkProtocol(Protocol):
    """Commit checkpoint the use-case layer calls between processing steps,
    so a hard crash mid-execution only loses work since the last checkpoint
    rather than the whole attempt."""

    async def commit(self) -> None:
        ...
