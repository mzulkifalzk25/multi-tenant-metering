from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.job import Job
from src.repositories.database import ExecutionModel, JobModel
from src.shared.constants import FileType
from src.shared.types import ExecutionId, JobId, JobStatus, TenantId, UserId


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, job_id: JobId, tenant_id: TenantId) -> Job | None:
        stmt = select(JobModel).where(JobModel.id == job_id, JobModel.tenant_id == tenant_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return await self._load(row)

    async def get_by_id_unscoped(self, job_id: JobId) -> Job | None:
        row = await self._session.get(JobModel, job_id)
        return await self._load(row)

    async def _load(self, row: JobModel | None) -> Job | None:
        if row is None:
            return None
        execution_ids = (
            (
                await self._session.execute(
                    select(ExecutionModel.id)
                    .where(ExecutionModel.job_id == row.id)
                    .order_by(ExecutionModel.generation)
                )
            )
            .scalars()
            .all()
        )
        return self._to_entity(row, list(execution_ids))

    async def save(self, job: Job) -> None:
        row = await self._session.get(JobModel, job.id)
        if row is None:
            row = JobModel(id=job.id, tenant_id=job.tenant_id)
            self._session.add(row)
        row.user_id = job.user_id
        row.file_path = job.file_path
        row.file_type = job.file_type.value
        row.status = job.status.value
        row.created_at = job.created_at
        await self._session.flush()

    @staticmethod
    def _to_entity(row: JobModel, execution_ids: list[str]) -> Job:
        return Job(
            id=JobId(row.id),
            tenant_id=TenantId(row.tenant_id),
            user_id=UserId(row.user_id),
            file_path=row.file_path,
            file_type=FileType(row.file_type),
            status=JobStatus(row.status),
            created_at=row.created_at,
            execution_ids=[ExecutionId(eid) for eid in execution_ids],
        )
