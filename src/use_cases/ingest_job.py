"""Use case: turn an inbound submission (HTTP or pub/sub) into a Job."""

from __future__ import annotations

import uuid

from src.entities.job import Job
from src.shared.constants import AuditEventType, FileType
from src.shared.errors import TenantNotFoundError
from src.shared.types import JobId, JobStatus, TenantId, UserId
from src.use_cases.protocols import (
    AuditRepositoryProtocol,
    JobDispatcherProtocol,
    JobRepositoryProtocol,
    TenantRepositoryProtocol,
)


class IngestJob:
    def __init__(
        self,
        tenant_repo: TenantRepositoryProtocol,
        job_repo: JobRepositoryProtocol,
        audit_repo: AuditRepositoryProtocol,
        dispatcher: JobDispatcherProtocol,
    ) -> None:
        self._tenant_repo = tenant_repo
        self._job_repo = job_repo
        self._audit_repo = audit_repo
        self._dispatcher = dispatcher

    async def execute(
        self,
        *,
        tenant_id: TenantId,
        user_id: UserId,
        file_path: str,
        file_type: FileType,
    ) -> Job:
        tenant = await self._tenant_repo.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")
        tenant.ensure_active()

        job = Job(
            id=JobId(str(uuid.uuid4())),
            tenant_id=tenant_id,
            user_id=user_id,
            file_path=file_path,
            file_type=file_type,
            status=JobStatus.PENDING,
        )
        await self._job_repo.save(job)
        await self._audit_repo.record(
            job_id=job.id,
            execution_id=None,
            event_type=AuditEventType.JOB_INGESTED,
            message=f"Job ingested for tenant {tenant_id}: {file_path} ({file_type.value})",
        )
        self._dispatcher.dispatch(job.id, tenant_id)
        return job
