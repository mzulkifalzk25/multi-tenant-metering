"""End-to-end integration tests against real PostgreSQL, Redis, and Celery.

Celery runs in eager mode (``task_always_eager``): tasks execute
synchronously in-process, which exercises the real task code path without
requiring a separate worker process. Skipped automatically unless the
docker-compose services are reachable.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import struct
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.entities.execution import Execution
from src.entities.job import Job
from src.interfaces.consumers.job_consumer import JobConsumer
from src.repositories.audit_repository import AuditRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.job_repository import JobRepository
from src.repositories.tenant_repository import TenantRepository
from src.repositories.work_unit_repository import WorkUnitRepository
from src.services.document_processor import DocumentProcessor
from src.services.job_orchestrator import JobOrchestrator
from src.shared.constants import FileType
from src.shared.types import ExecutionId, JobId, JobStatus, TenantId, UserId, WorkUnitStatus
from src.tests.fixtures import make_tenant
from src.use_cases.ingest_job import IngestJob
from src.use_cases.schedule_recovery import ScheduleRecovery

pytestmark = pytest.mark.integration


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.dispatched: list[tuple[JobId, TenantId]] = []

    def dispatch(self, job_id: JobId, tenant_id: TenantId) -> None:
        self.dispatched.append((job_id, tenant_id))


def _write_minimal_pdf(path: Path, page_count: int) -> None:
    body = b"%PDF-1.4\n" + (b"/Type /Page\n" * page_count)
    path.write_bytes(body)


def _write_minimal_mp4(path: Path, duration_seconds: int, timescale: int = 1) -> None:
    mvhd_payload = (
        b"\x00\x00\x00\x00"  # version + flags
        + b"\x00\x00\x00\x00"  # creation time
        + b"\x00\x00\x00\x00"  # modification time
        + struct.pack(">I", timescale)
        + struct.pack(">I", duration_seconds * timescale)
    )
    mvhd_box = struct.pack(">I", 8 + len(mvhd_payload)) + b"mvhd" + mvhd_payload
    moov_box = struct.pack(">I", 8 + len(mvhd_box)) + b"moov" + mvhd_box
    path.write_bytes(moov_box)


@pytest.mark.asyncio
async def test_ingest_and_process_pdf_end_to_end(
    db_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    pdf_path = tmp_path / "document.pdf"
    _write_minimal_pdf(pdf_path, page_count=3)

    async with db_session_factory() as session:
        await TenantRepository(session).save(make_tenant(tenant_id="integration-tenant"))
        await session.commit()

    dispatcher = _RecordingDispatcher()
    async with db_session_factory() as session:
        ingest = IngestJob(
            tenant_repo=TenantRepository(session),
            job_repo=JobRepository(session),
            audit_repo=AuditRepository(session),
            dispatcher=dispatcher,
        )
        job = await ingest.execute(
            tenant_id=TenantId("integration-tenant"),
            user_id=UserId("integration-user"),
            file_path=str(pdf_path),
            file_type=FileType.PDF,
        )
        await session.commit()

    assert dispatcher.dispatched == [(job.id, TenantId("integration-tenant"))]

    orchestrator = JobOrchestrator(db_session_factory, DocumentProcessor())
    result = await orchestrator.run(job.id, TenantId("integration-tenant"))
    assert result.status == JobStatus.COMPLETED.value

    async with db_session_factory() as session:
        work_units = await WorkUnitRepository(session).list_by_execution(
            ExecutionId(result.execution_id)
        )
        assert len(work_units) == 3
        assert all(wu.status == WorkUnitStatus.COMPLETED for wu in work_units)

        audit_entries = await AuditRepository(session).list_by_job(job.id)
        event_types = [entry.event_type.value for entry in audit_entries]
        assert "job_ingested" in event_types
        assert "execution_completed" in event_types


@pytest.mark.asyncio
async def test_ingest_and_process_video_end_to_end(
    db_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    video_path = tmp_path / "clip.mp4"
    _write_minimal_mp4(video_path, duration_seconds=25)  # -> 3 sampled frames at 10s intervals

    async with db_session_factory() as session:
        await TenantRepository(session).save(make_tenant(tenant_id="video-tenant"))
        job_repo = JobRepository(session)
        job = Job(
            id=JobId("video-job-1"),
            tenant_id=TenantId("video-tenant"),
            user_id=UserId("video-user"),
            file_path=str(video_path),
            file_type=FileType.VIDEO,
        )
        await job_repo.save(job)
        await session.commit()

    orchestrator = JobOrchestrator(db_session_factory, DocumentProcessor())
    result = await orchestrator.run(JobId("video-job-1"), TenantId("video-tenant"))

    assert result.status == JobStatus.COMPLETED.value
    async with db_session_factory() as session:
        work_units = await WorkUnitRepository(session).list_by_execution(
            ExecutionId(result.execution_id)
        )
        assert len(work_units) == 3


@pytest.fixture
def celery_eager() -> Iterator[None]:
    """task_always_eager lives on the module-level celery_app singleton, so
    it must be restored after the test -- otherwise it silently changes how
    every *other* test that dispatches a task behaves too, since Celery's
    eager mode swallows exceptions raised by a task unless .get() is
    called, which turns a real bug in another test into a silent no-op."""
    from src.services import celery_tasks

    original = celery_tasks.celery_app.conf.task_always_eager
    celery_tasks.celery_app.conf.task_always_eager = True
    try:
        yield
    finally:
        celery_tasks.celery_app.conf.task_always_eager = original


@pytest.mark.asyncio
async def test_process_job_task_via_celery_eager(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    celery_eager: None,
) -> None:
    from src.services import celery_tasks

    # celery_tasks.database already targets TEST_DATABASE_URL (see the
    # os.environ defaults set at the top of conftest.py) and has not opened
    # any connection yet, so its first use safely binds to whichever event
    # loop is current at that point -- which must be the thread below's, not
    # this test's own loop, since asyncpg connections are loop-bound.

    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")

    async with db_session_factory() as session:
        await TenantRepository(session).save(make_tenant(tenant_id="celery-tenant"))
        job = Job(
            id=JobId("celery-job-1"),
            tenant_id=TenantId("celery-tenant"),
            user_id=UserId("celery-user"),
            file_path=str(image_path),
            file_type=FileType.IMAGE,
        )
        await JobRepository(session).save(job)
        await session.commit()

    # A real Celery worker calls this task from its own thread, with no
    # asyncio event loop running -- which is what lets the task safely use
    # asyncio.run() internally. Dispatching from a plain `await` here would
    # collide with pytest-asyncio's own loop in this thread, so run it in a
    # separate thread to match production invocation faithfully.
    def _run_task_eagerly() -> dict[str, str | int]:
        async_result = celery_tasks.process_job_task.delay("celery-job-1", "celery-tenant")
        return async_result.get(timeout=10)  # type: ignore[no-any-return]

    outcome = await asyncio.to_thread(_run_task_eagerly)

    assert outcome["status"] == JobStatus.COMPLETED.value

    async with db_session_factory() as session:
        history_job = await JobRepository(session).get_by_id(
            JobId("celery-job-1"), TenantId("celery-tenant")
        )
        assert history_job is not None
        assert history_job.status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_schedule_recovery_dispatches_new_generation(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        await TenantRepository(session).save(make_tenant(tenant_id="recovery-tenant"))
        job = Job(
            id=JobId("recovery-job-1"),
            tenant_id=TenantId("recovery-tenant"),
            user_id=UserId("recovery-user"),
            file_path="/tmp/whatever.jpg",
            file_type=FileType.IMAGE,
        )
        job.register_execution(ExecutionId("recovery-job-1::gen-0"))
        await JobRepository(session).save(job)

        stuck_execution = Execution(
            id=ExecutionId("recovery-job-1::gen-0"), job_id=job.id, generation=0
        )
        stuck_execution.mark_started()
        stuck_execution.started_at = datetime.now(UTC) - timedelta(minutes=30)
        await ExecutionRepository(session).save(stuck_execution)
        await session.commit()

    dispatcher = _RecordingDispatcher()
    async with db_session_factory() as session:
        use_case = ScheduleRecovery(
            job_repo=JobRepository(session),
            execution_repo=ExecutionRepository(session),
            audit_repo=AuditRepository(session),
            dispatcher=dispatcher,
            stuck_threshold_minutes=15,
        )
        recovered = await use_case.execute()
        await session.commit()

    assert recovered == 1
    assert dispatcher.dispatched == [(JobId("recovery-job-1"), TenantId("recovery-tenant"))]

    async with db_session_factory() as session:
        stuck_after = await ExecutionRepository(session).get_by_id(
            ExecutionId("recovery-job-1::gen-0")
        )
        assert stuck_after is not None
        assert stuck_after.status == JobStatus.FAILED


@pytest.mark.asyncio
async def test_job_consumer_ingests_message_from_redis_pubsub(
    db_session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis[str],
) -> None:
    async with db_session_factory() as session:
        await TenantRepository(session).save(make_tenant(tenant_id="pubsub-tenant"))
        await session.commit()

    consumer = JobConsumer(
        redis_client=redis_client,
        channel="jobs.ingest.test",
        session_factory=db_session_factory,
    )
    consumer_task = asyncio.create_task(consumer.run_forever())
    await asyncio.sleep(0.2)  # let the subscription establish

    message = json.dumps(
        {
            "tenant_id": "pubsub-tenant",
            "user_id": "pubsub-user",
            "file_path": "/uploads/via-pubsub.jpg",
            "file_type": "image",
        }
    )
    await redis_client.publish("jobs.ingest.test", message)
    await asyncio.sleep(0.5)  # let the consumer pick it up

    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task

    async with db_session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT id FROM jobs WHERE tenant_id = :tenant_id"),
                {"tenant_id": "pubsub-tenant"},
            )
        ).fetchall()
        assert len(rows) == 1


# --- HTTP API (FastAPI) -----------------------------------------------------------


def test_health_endpoint_reports_ok(postgres_available: bool, redis_available: bool) -> None:
    from fastapi.testclient import TestClient

    from src.frameworks.fastapi_app import create_app

    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_submit_and_fetch_job_via_api(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from fastapi.testclient import TestClient

    from src.frameworks.fastapi_app import create_app

    async with db_session_factory() as session:
        await TenantRepository(session).save(make_tenant(tenant_id="api-tenant"))
        await session.commit()

    with TestClient(create_app()) as client:
        submit_response = client.post(
            "/jobs/api-tenant/submit",
            headers={"X-Tenant-Id": "api-tenant", "X-User-Id": "api-user"},
            json={"file_path": "/uploads/via-api.jpg", "file_type": "image"},
        )
        assert submit_response.status_code == 200, submit_response.text
        job_id = submit_response.json()["job_id"]
        assert submit_response.json()["status"] == JobStatus.PENDING.value

        history_response = client.get(
            f"/jobs/api-tenant/{job_id}",
            headers={"X-Tenant-Id": "api-tenant"},
        )
        assert history_response.status_code == 200, history_response.text
        history = history_response.json()
        assert history["job_id"] == job_id
        assert history["status"] == JobStatus.PENDING.value
        assert any(entry["event_type"] == "job_ingested" for entry in history["audit_log"])


def test_submit_job_rejects_tenant_mismatch() -> None:
    from fastapi.testclient import TestClient

    from src.frameworks.fastapi_app import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/jobs/tenant-a/submit",
            headers={"X-Tenant-Id": "tenant-b", "X-User-Id": "api-user"},
            json={"file_path": "/uploads/via-api.jpg", "file_type": "image"},
        )

    assert response.status_code == 403


def test_get_job_returns_404_for_unknown_job(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """db_session_factory is unused directly but ensures the schema exists
    in the database create_app()'s own Database instance points at."""
    from fastapi.testclient import TestClient

    from src.frameworks.fastapi_app import create_app

    with TestClient(create_app()) as client:
        response = client.get(
            "/jobs/api-tenant/does-not-exist",
            headers={"X-Tenant-Id": "api-tenant"},
        )

    assert response.status_code == 404
