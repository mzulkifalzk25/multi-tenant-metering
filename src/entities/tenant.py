"""Domain model for a tenant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.shared.types import TenantId


@dataclass(slots=True)
class Tenant:
    id: TenantId
    name: str
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def ensure_active(self) -> None:
        if not self.is_active:
            raise ValueError(f"Tenant {self.id} is not active")
