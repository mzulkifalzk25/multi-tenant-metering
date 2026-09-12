"""Repository tests against a real PostgreSQL instance.

Skipped automatically (see conftest.py) unless docker-compose's postgres
service is reachable on localhost:5544.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.entities.audit_log import AuditLogEntry
from src.entities.execution import Execution
from src.entities.status import Status
from src.entities.work_unit import WorkUnit
from src.repositories.audit_repository import AuditRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.job_repository import JobRepository
from src.repositories.status_repository import StatusRepository
from src.repositories.tenant_repository import TenantRepository
from src.repositories.work_unit_repository import WorkUnitRepository
from src.shared.constants import AuditEventType, StageName, WorkUnitType
from src.shared.types import ExecutionId, TenantId, WorkUnitId
from src.tests.fixtures import make_job, make_tenant

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_tenant_repository_round_trip(db_session: AsyncSession) -> None:
    repo = TenantRepository(db_session)
    tenant = make_tenant(tenant_id="t-repo-1")

    await repo.save(tenant)
    await db_session.commit()

    fetched = await repo.get_by_id(tenant.id)
    assert fetched is not None
    assert fetched.name == tenant.name
    assert fetched.is_active is True


@pytest.mark.asyncio
async def test_job_repository_scopes_by_tenant(db_session: AsyncSession) -> None:
    tenant_repo = TenantRepository(db_session)
    job_repo = JobRepository(db_session)
    tenant = make_tenant(tenant_id="t-repo-2")
    await tenant_repo.save(tenant)

    job = make_job(job_id="job-repo-1", tenant_id="t-repo-2")
    await job_repo.save(job)
    await db_session.commit()

    assert await job_repo.get_by_id(job.id, tenant.id) is not None
    assert await job_repo.get_by_id(job.id, TenantId("someone-else")) is None
    assert await job_repo.get_by_id_unscoped(job.id) is not None


@pytest.mark.asyncio
async def test_execution_repository_finds_stuck_executions(db_session: AsyncSession) -> None:
    tenant_repo = TenantRepository(db_session)
    job_repo = JobRepository(db_session)
    execution_repo = ExecutionRepository(db_session)

    tenant = make_tenant(tenant_id="t-repo-3")
    await tenant_repo.save(tenant)
    job = make_job(job_id="job-repo-2", tenant_id="t-repo-3")
    await job_repo.save(job)

    stuck = Execution(id=ExecutionId("job-repo-2::gen-0"), job_id=job.id, generation=0)
    stuck.mark_started()
    stuck.started_at = datetime.now(UTC) - timedelta(minutes=30)
    await execution_repo.save(stuck)

    healthy = Execution(id=ExecutionId("job-repo-2::gen-1"), job_id=job.id, generation=1)
    healthy.mark_started()
    await execution_repo.save(healthy)
    await db_session.commit()

    results = await execution_repo.list_stuck_processing(
        now=datetime.now(UTC), threshold_minutes=15
    )
    result_ids = {e.id for e in results}
    assert stuck.id in result_ids
    assert healthy.id not in result_ids


@pytest.mark.asyncio
async def test_work_unit_repository_upsert_is_idempotent(db_session: AsyncSession) -> None:
    tenant_repo = TenantRepository(db_session)
    job_repo = JobRepository(db_session)
    execution_repo = ExecutionRepository(db_session)
    work_unit_repo = WorkUnitRepository(db_session)

    tenant = make_tenant(tenant_id="t-repo-4")
    await tenant_repo.save(tenant)
    job = make_job(job_id="job-repo-3", tenant_id="t-repo-4")
    await job_repo.save(job)
    execution = Execution(id=ExecutionId("job-repo-3::gen-0"), job_id=job.id, generation=0)
    await execution_repo.save(execution)

    work_unit = WorkUnit(
        id=WorkUnitId(WorkUnit.idempotency_key(execution.id, WorkUnitType.PAGE, 0)),
        job_id=job.id,
        execution_id=execution.id,
        unit_type=WorkUnitType.PAGE,
        unit_number=0,
    )
    await work_unit_repo.save_many([work_unit, work_unit])  # duplicate in the same batch
    await db_session.commit()

    stored = await work_unit_repo.list_by_execution(execution.id)
    assert len(stored) == 1

    work_unit.mark_completed()
    await work_unit_repo.save(work_unit)
    await db_session.commit()

    stored_again = await work_unit_repo.list_by_execution(execution.id)
    assert len(stored_again) == 1
    assert stored_again[0].status.value == "completed"


@pytest.mark.asyncio
async def test_status_repository_upsert(db_session: AsyncSession) -> None:
    tenant_repo = TenantRepository(db_session)
    job_repo = JobRepository(db_session)
    execution_repo = ExecutionRepository(db_session)
    status_repo = StatusRepository(db_session)

    tenant = make_tenant(tenant_id="t-repo-5")
    await tenant_repo.save(tenant)
    job = make_job(job_id="job-repo-4", tenant_id="t-repo-5")
    await job_repo.save(job)
    execution = Execution(id=ExecutionId("job-repo-4::gen-0"), job_id=job.id, generation=0)
    await execution_repo.save(execution)

    status = Status(execution_id=execution.id)
    await status_repo.upsert(status)
    await db_session.commit()

    status.advance(StageName.EXPANDED)
    await status_repo.upsert(status)
    await db_session.commit()

    fetched = await status_repo.get_by_execution(execution.id)
    assert fetched is not None
    assert fetched.stage == StageName.EXPANDED


@pytest.mark.asyncio
async def test_audit_repository_is_append_only(db_session: AsyncSession) -> None:
    tenant_repo = TenantRepository(db_session)
    job_repo = JobRepository(db_session)
    execution_repo = ExecutionRepository(db_session)
    audit_repo = AuditRepository(db_session)

    tenant = make_tenant(tenant_id="t-repo-6")
    await tenant_repo.save(tenant)
    job = make_job(job_id="job-repo-5", tenant_id="t-repo-6")
    await job_repo.save(job)
    execution = Execution(id=ExecutionId("job-repo-5::gen-0"), job_id=job.id, generation=0)
    await execution_repo.save(execution)

    await audit_repo.record(
        job_id=job.id,
        execution_id=execution.id,
        event_type=AuditEventType.EXECUTION_STARTED,
        message="started",
    )
    await audit_repo.record(
        job_id=job.id,
        execution_id=None,
        event_type=AuditEventType.JOB_INGESTED,
        message="ingested",
    )
    await db_session.commit()

    entries = await audit_repo.list_by_job(job.id)
    assert len(entries) == 2
    assert all(isinstance(entry, AuditLogEntry) for entry in entries)
    assert entries[0].created_at <= entries[1].created_at
    # AuditRepository intentionally exposes no update/delete method.
    assert not hasattr(audit_repo, "update")
    assert not hasattr(audit_repo, "delete")
