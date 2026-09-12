from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.execution import Execution
from src.repositories.database import ExecutionModel, WorkUnitModel
from src.shared.types import ExecutionId, JobId, JobStatus, WorkUnitId


class ExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, execution_id: ExecutionId) -> Execution | None:
        row = await self._session.get(ExecutionModel, execution_id)
        if row is None:
            return None
        return await self._to_entity(row)

    async def save(self, execution: Execution) -> None:
        row = await self._session.get(ExecutionModel, execution.id)
        if row is None:
            row = ExecutionModel(
                id=execution.id, job_id=execution.job_id, generation=execution.generation
            )
            self._session.add(row)
        row.status = execution.status.value
        row.started_at = execution.started_at
        row.completed_at = execution.completed_at
        await self._session.flush()

    async def list_by_job(self, job_id: JobId) -> list[Execution]:
        stmt = (
            select(ExecutionModel)
            .where(ExecutionModel.job_id == job_id)
            .order_by(ExecutionModel.generation)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [await self._to_entity(row) for row in rows]

    async def list_stuck_processing(
        self, *, now: datetime, threshold_minutes: int
    ) -> list[Execution]:
        cutoff = now - timedelta(minutes=threshold_minutes)
        stmt = select(ExecutionModel).where(
            ExecutionModel.status == JobStatus.PROCESSING.value,
            ExecutionModel.started_at.is_not(None),
            ExecutionModel.started_at < cutoff,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [await self._to_entity(row) for row in rows]

    async def _to_entity(self, row: ExecutionModel) -> Execution:
        work_unit_ids = (
            (
                await self._session.execute(
                    select(WorkUnitModel.id)
                    .where(WorkUnitModel.execution_id == row.id)
                    .order_by(WorkUnitModel.unit_number)
                )
            )
            .scalars()
            .all()
        )
        return Execution(
            id=ExecutionId(row.id),
            job_id=JobId(row.job_id),
            generation=row.generation,
            status=JobStatus(row.status),
            started_at=row.started_at,
            completed_at=row.completed_at,
            work_unit_ids=[WorkUnitId(wid) for wid in work_unit_ids],
        )
