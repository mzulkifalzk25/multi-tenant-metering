from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.frameworks.database import Database
from src.interfaces.api.auth import (
    ensure_path_tenant_matches,
    get_authenticated_tenant,
    get_authenticated_user,
)
from src.repositories.audit_repository import AuditRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.job_repository import JobRepository
from src.repositories.tenant_repository import TenantRepository
from src.repositories.work_unit_repository import WorkUnitRepository
from src.services.celery_tasks import CeleryJobDispatcher
from src.shared.types import JobId, TenantId, UserId
from src.shared.validators import (
    AuditLogResponseSchema,
    ExecutionResponseSchema,
    JobHistoryResponseSchema,
    JobSubmittedResponseSchema,
    SubmitJobBodySchema,
    WorkUnitResponseSchema,
)
from src.use_cases.get_job_history import GetJobHistory
from src.use_cases.ingest_job import IngestJob

router = APIRouter()


async def _get_session(request: Request) -> AsyncIterator[AsyncSession]:
    database: Database = request.app.state.database
    async with database.session_factory() as session:
        yield session


@router.post("/{tenant_id}/submit", response_model=JobSubmittedResponseSchema)
async def submit_job(
    tenant_id: str,
    body: SubmitJobBodySchema,
    authenticated_tenant: TenantId = Depends(get_authenticated_tenant),
    user_id: UserId = Depends(get_authenticated_user),
    session: AsyncSession = Depends(_get_session),
) -> JobSubmittedResponseSchema:
    ensure_path_tenant_matches(tenant_id, authenticated_tenant)

    use_case = IngestJob(
        tenant_repo=TenantRepository(session),
        job_repo=JobRepository(session),
        audit_repo=AuditRepository(session),
        dispatcher=CeleryJobDispatcher(),
    )
    job = await use_case.execute(
        tenant_id=authenticated_tenant,
        user_id=user_id,
        file_path=body.file_path,
        file_type=body.file_type,
    )
    await session.commit()
    return JobSubmittedResponseSchema(job_id=str(job.id), status=job.status.value)


@router.get("/{tenant_id}/{job_id}", response_model=JobHistoryResponseSchema)
async def get_job(
    tenant_id: str,
    job_id: str,
    authenticated_tenant: TenantId = Depends(get_authenticated_tenant),
    session: AsyncSession = Depends(_get_session),
) -> JobHistoryResponseSchema:
    ensure_path_tenant_matches(tenant_id, authenticated_tenant)

    use_case = GetJobHistory(
        job_repo=JobRepository(session),
        execution_repo=ExecutionRepository(session),
        work_unit_repo=WorkUnitRepository(session),
        audit_repo=AuditRepository(session),
    )
    history = await use_case.execute(JobId(job_id), authenticated_tenant)

    return JobHistoryResponseSchema(
        job_id=str(history.job.id),
        tenant_id=str(history.job.tenant_id),
        status=history.job.status.value,
        file_type=history.job.file_type.value,
        created_at=history.job.created_at,
        executions=[
            ExecutionResponseSchema(
                id=str(eh.execution.id),
                generation=eh.execution.generation,
                status=eh.execution.status.value,
                started_at=eh.execution.started_at,
                completed_at=eh.execution.completed_at,
                work_units=[
                    WorkUnitResponseSchema(
                        id=str(wu.id),
                        unit_type=wu.unit_type.value,
                        unit_number=wu.unit_number,
                        status=wu.status.value,
                        error=wu.error,
                    )
                    for wu in eh.work_units
                ],
            )
            for eh in history.executions
        ],
        audit_log=[
            AuditLogResponseSchema(
                id=str(entry.id),
                event_type=entry.event_type,
                message=entry.message,
                created_at=entry.created_at,
            )
            for entry in history.audit_log
        ],
    )
