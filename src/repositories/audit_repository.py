from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.audit_log import AuditLogEntry
from src.repositories.database import AuditLogModel
from src.shared.constants import AuditEventType
from src.shared.types import AuditLogId, ExecutionId, JobId


class AuditRepository:
    """Append-only: this class exposes no update or delete method, so every
    audit entry that has ever been written remains readable forever."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        job_id: JobId,
        execution_id: ExecutionId | None,
        event_type: AuditEventType,
        message: str,
    ) -> AuditLogEntry:
        entry = AuditLogEntry.record(
            id=AuditLogId(str(uuid.uuid4())),
            job_id=job_id,
            execution_id=execution_id,
            event_type=event_type,
            message=message,
        )
        row = AuditLogModel(
            id=entry.id,
            job_id=entry.job_id,
            execution_id=entry.execution_id,
            event_type=entry.event_type.value,
            message=entry.message,
            created_at=entry.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return entry

    async def list_by_job(self, job_id: JobId) -> list[AuditLogEntry]:
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.job_id == job_id)
            .order_by(AuditLogModel.created_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            AuditLogEntry(
                id=AuditLogId(row.id),
                job_id=JobId(row.job_id),
                execution_id=ExecutionId(row.execution_id) if row.execution_id else None,
                event_type=AuditEventType(row.event_type),
                message=row.message,
                created_at=row.created_at,
            )
            for row in rows
        ]
