from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.status import Status
from src.repositories.database import StatusModel
from src.shared.constants import StageName
from src.shared.types import ExecutionId


class StatusRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, status: Status) -> None:
        row = await self._session.get(StatusModel, status.execution_id)
        if row is None:
            row = StatusModel(execution_id=status.execution_id)
            self._session.add(row)
        row.stage = status.stage.value
        row.updated_at = status.updated_at
        await self._session.flush()

    async def get_by_execution(self, execution_id: ExecutionId) -> Status | None:
        row = await self._session.get(StatusModel, execution_id)
        if row is None:
            return None
        return Status(
            execution_id=ExecutionId(row.execution_id),
            stage=StageName(row.stage),
            updated_at=row.updated_at,
        )
