"""Verifies that a resource actually belongs to the tenant requesting it.

Every use case that accepts a tenant_id from an untrusted caller (the API,
a pub/sub message) must route the fetched entity through here before
acting on it, so a crafted job_id from another tenant can never leak data
or be mutated cross-tenant.
"""

from __future__ import annotations

from src.entities.job import Job
from src.shared.errors import TenantScopeViolationError
from src.shared.types import TenantId


class ScopeValidator:
    @staticmethod
    def ensure_job_in_tenant(job: Job, tenant_id: TenantId) -> None:
        if job.tenant_id != tenant_id:
            raise TenantScopeViolationError(f"Job {job.id} does not belong to tenant {tenant_id}")
