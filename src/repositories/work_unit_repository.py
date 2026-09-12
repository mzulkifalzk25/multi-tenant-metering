from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.work_unit import WorkUnit
from src.repositories.database import WorkUnitModel
from src.shared.constants import WorkUnitType
from src.shared.types import ExecutionId, JobId, WorkUnitId, WorkUnitStatus


class WorkUnitRepository:
    """Work units are keyed by a deterministic idempotency key (see
    :meth:`WorkUnit.idempotency_key`), so re-expanding the same execution
    generation twice upserts in place instead of creating duplicates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, work_unit: WorkUnit) -> None:
        await self.save_many([work_unit])

    async def save_many(self, work_units: list[WorkUnit]) -> None:
        if not work_units:
            return
        # Postgres rejects ON CONFLICT DO UPDATE touching the same row twice
        # within one statement, so a batch with repeated ids (e.g. the same
        # spec expanded twice by a retried caller) must be deduplicated first.
        deduped_by_id = {wu.id: wu for wu in work_units}
        stmt = pg_insert(WorkUnitModel).values(
            [
                {
                    "id": wu.id,
                    "job_id": wu.job_id,
                    "execution_id": wu.execution_id,
                    "unit_type": wu.unit_type.value,
                    "unit_number": wu.unit_number,
                    "status": wu.status.value,
                    "error": wu.error,
                }
                for wu in deduped_by_id.values()
            ]
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[WorkUnitModel.id],
            set_={
                "status": stmt.excluded.status,
                "error": stmt.excluded.error,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_by_execution(self, execution_id: ExecutionId) -> list[WorkUnit]:
        stmt = (
            select(WorkUnitModel)
            .where(WorkUnitModel.execution_id == execution_id)
            .order_by(WorkUnitModel.unit_number)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_entity(row) for row in rows]

    async def get_by_id(self, work_unit_id: WorkUnitId) -> WorkUnit | None:
        row = await self._session.get(WorkUnitModel, work_unit_id)
        return self._to_entity(row) if row is not None else None

    @staticmethod
    def _to_entity(row: WorkUnitModel) -> WorkUnit:
        return WorkUnit(
            id=WorkUnitId(row.id),
            job_id=JobId(row.job_id),
            execution_id=ExecutionId(row.execution_id),
            unit_type=WorkUnitType(row.unit_type),
            unit_number=row.unit_number,
            status=WorkUnitStatus(row.status),
            error=row.error,
        )
