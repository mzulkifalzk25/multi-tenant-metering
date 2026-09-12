from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.tenant import Tenant
from src.repositories.database import TenantModel
from src.shared.types import TenantId


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, tenant_id: TenantId) -> Tenant | None:
        row = await self._session.get(TenantModel, tenant_id)
        return self._to_entity(row) if row is not None else None

    async def save(self, tenant: Tenant) -> None:
        row = await self._session.get(TenantModel, tenant.id)
        if row is None:
            row = TenantModel(id=tenant.id)
            self._session.add(row)
        row.name = tenant.name
        row.is_active = tenant.is_active
        row.created_at = tenant.created_at
        await self._session.flush()

    @staticmethod
    def _to_entity(row: TenantModel) -> Tenant:
        return Tenant(
            id=TenantId(row.id),
            name=row.name,
            is_active=row.is_active,
            created_at=row.created_at,
        )
