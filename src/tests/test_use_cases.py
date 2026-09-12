from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from src.shared.constants import DEFAULT_STUCK_JOB_THRESHOLD_MINUTES, AuditEventType, FileType
from src.shared.errors import (
    ExecutionNotFoundError,
    JobNotFoundError,
    TenantNotFoundError,
    TenantScopeViolationError,
)
from src.shared.types import ExecutionId, JobId, JobStatus, TenantId, UserId, WorkUnitStatus
from src.tests.fixtures import (
    FakeAuditRepository,
    FakeDocumentProcessor,
    FakeExecutionRepository,
    FakeJobDispatcher,
    FakeJobRepository,
    FakeStatusRepository,
    FakeTenantRepository,
    FakeUnitOfWork,
    FakeWorkUnitRepository,
    make_execution,
    make_job,
    make_tenant,
)
from src.use_cases.get_job_history import GetJobHistory
from src.use_cases.ingest_job import IngestJob
from src.use_cases.process_job import ProcessJob
from src.use_cases.schedule_recovery import ScheduleRecovery
from src.use_cases.scope_validator import ScopeValidator

# --- IngestJob -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_job_creates_pending_job_and_dispatches() -> None:
    tenant_repo = FakeTenantRepository([make_tenant()])
    job_repo = FakeJobRepository()
    audit_repo = FakeAuditRepository()
    dispatcher = FakeJobDispatcher()
    use_case = IngestJob(tenant_repo, job_repo, audit_repo, dispatcher)

    job = await use_case.execute(
        tenant_id=TenantId("tenant-1"),
        user_id=UserId("user-1"),
        file_path="/uploads/doc.pdf",
        file_type=FileType.PDF,
    )

    assert job.status == JobStatus.PENDING
    assert await job_repo.get_by_id(job.id, TenantId("tenant-1")) is not None
    assert dispatcher.dispatched == [(job.id, TenantId("tenant-1"))]
    assert len(audit_repo.entries) == 1
    assert audit_repo.entries[0].execution_id is None


@pytest.mark.asyncio
async def test_ingest_job_raises_when_tenant_missing() -> None:
    use_case = IngestJob(
        FakeTenantRepository(), FakeJobRepository(), FakeAuditRepository(), FakeJobDispatcher()
    )
    with pytest.raises(TenantNotFoundError):
        await use_case.execute(
            tenant_id=TenantId("ghost"),
            user_id=UserId("user-1"),
            file_path="/uploads/doc.pdf",
            file_type=FileType.PDF,
        )


@pytest.mark.asyncio
async def test_ingest_job_raises_when_tenant_inactive() -> None:
    use_case = IngestJob(
        FakeTenantRepository([make_tenant(is_active=False)]),
        FakeJobRepository(),
        FakeAuditRepository(),
        FakeJobDispatcher(),
    )
    with pytest.raises(ValueError):
        await use_case.execute(
            tenant_id=TenantId("tenant-1"),
            user_id=UserId("user-1"),
            file_path="/uploads/doc.pdf",
            file_type=FileType.PDF,
        )


# --- ProcessJob ------------------------------------------------------------------


@dataclass(slots=True)
class ProcessJobHarness:
    job_repo: FakeJobRepository
    execution_repo: FakeExecutionRepository
    work_unit_repo: FakeWorkUnitRepository
    status_repo: FakeStatusRepository
    audit_repo: FakeAuditRepository
    unit_of_work: FakeUnitOfWork

    def use_case(self, document_processor: FakeDocumentProcessor) -> ProcessJob:
        """A fresh ProcessJob over the same repos but a different processor,
        simulating a new Celery task invocation picking up where the last
        one left off."""
        return ProcessJob(
            job_repo=self.job_repo,
            execution_repo=self.execution_repo,
            work_unit_repo=self.work_unit_repo,
            status_repo=self.status_repo,
            audit_repo=self.audit_repo,
            document_processor=document_processor,
            unit_of_work=self.unit_of_work,
        )


def _build_process_job(job_repo: FakeJobRepository) -> ProcessJobHarness:
    return ProcessJobHarness(
        job_repo=job_repo,
        execution_repo=FakeExecutionRepository(),
        work_unit_repo=FakeWorkUnitRepository(),
        status_repo=FakeStatusRepository(),
        audit_repo=FakeAuditRepository(),
        unit_of_work=FakeUnitOfWork(),
    )


@pytest.mark.asyncio
async def test_process_job_completes_all_work_units() -> None:
    job = make_job()
    harness = _build_process_job(FakeJobRepository([job]))
    document_processor = FakeDocumentProcessor(unit_count=3)

    execution = await harness.use_case(document_processor).execute(job.id, job.tenant_id)

    assert execution.status == JobStatus.COMPLETED
    assert execution.generation == 0
    work_units = await harness.work_unit_repo.list_by_execution(execution.id)
    assert len(work_units) == 3
    assert all(wu.status == WorkUnitStatus.COMPLETED for wu in work_units)
    updated_job = await harness.job_repo.get_by_id(job.id, job.tenant_id)
    assert updated_job is not None and updated_job.status == JobStatus.COMPLETED
    assert harness.unit_of_work.commit_count > 0


@pytest.mark.asyncio
async def test_process_job_isolates_failing_work_units() -> None:
    job = make_job()
    harness = _build_process_job(FakeJobRepository([job]))
    document_processor = FakeDocumentProcessor(unit_count=3, fail_unit_numbers=frozenset({1}))

    execution = await harness.use_case(document_processor).execute(job.id, job.tenant_id)

    assert execution.status == JobStatus.FAILED
    work_units = await harness.work_unit_repo.list_by_execution(execution.id)
    statuses = {wu.unit_number: wu.status for wu in work_units}
    assert statuses[0] == WorkUnitStatus.COMPLETED
    assert statuses[1] == WorkUnitStatus.FAILED
    assert statuses[2] == WorkUnitStatus.COMPLETED
    # per-item isolation: the processor still saw all three units
    assert len(document_processor.processed) == 3


@pytest.mark.asyncio
async def test_process_job_resume_skips_completed_units() -> None:
    job = make_job()
    harness = _build_process_job(FakeJobRepository([job]))
    failing_processor = FakeDocumentProcessor(unit_count=2, fail_unit_numbers=frozenset({1}))

    first_attempt = await harness.use_case(failing_processor).execute(job.id, job.tenant_id)
    assert first_attempt.status == JobStatus.FAILED
    assert len(failing_processor.processed) == 2

    # Resume the SAME execution generation with a processor that now succeeds.
    fixed_processor = FakeDocumentProcessor(unit_count=2)
    second_attempt = await harness.use_case(fixed_processor).execute(
        job.id, job.tenant_id, execution_id=first_attempt.id
    )

    assert second_attempt.id == first_attempt.id
    assert second_attempt.status == JobStatus.COMPLETED
    # unit 0 was already completed and must not be reprocessed
    assert [wu.unit_number for wu in fixed_processor.processed] == [1]
    work_units = await harness.work_unit_repo.list_by_execution(first_attempt.id)
    assert all(wu.status == WorkUnitStatus.COMPLETED for wu in work_units)


@pytest.mark.asyncio
async def test_process_job_retry_after_terminal_failure_creates_new_generation() -> None:
    job = make_job()
    harness = _build_process_job(FakeJobRepository([job]))
    failing_processor = FakeDocumentProcessor(unit_count=1, fail_unit_numbers=frozenset({0}))

    first = await harness.use_case(failing_processor).execute(job.id, job.tenant_id)
    assert first.status == JobStatus.FAILED
    assert first.generation == 0

    fixed_processor = FakeDocumentProcessor(unit_count=1)
    second = await harness.use_case(fixed_processor).execute(job.id, job.tenant_id)

    assert second.generation == 1
    assert second.id != first.id
    assert second.status == JobStatus.COMPLETED

    executions = await harness.execution_repo.list_by_job(job.id)
    assert {e.id for e in executions} == {first.id, second.id}
    assert first.status == JobStatus.FAILED  # untouched by the new generation


@pytest.mark.asyncio
async def test_process_job_raises_when_job_missing() -> None:
    harness = _build_process_job(FakeJobRepository())
    with pytest.raises(JobNotFoundError):
        await harness.use_case(FakeDocumentProcessor()).execute(
            JobId("ghost"), TenantId("tenant-1")
        )


@pytest.mark.asyncio
async def test_process_job_raises_when_execution_id_unknown() -> None:
    job = make_job()
    harness = _build_process_job(FakeJobRepository([job]))
    with pytest.raises(ExecutionNotFoundError):
        await harness.use_case(FakeDocumentProcessor()).execute(
            job.id, job.tenant_id, execution_id=ExecutionId("nonexistent")
        )


@pytest.mark.asyncio
async def test_process_job_enforces_tenant_scope() -> None:
    job = make_job(tenant_id="tenant-1")
    harness = _build_process_job(FakeJobRepository([job]))
    with pytest.raises(JobNotFoundError):
        # FakeJobRepository.get_by_id already filters by tenant, so a
        # mismatched tenant looks like "not found" from outside -- this is
        # the correct, safe failure mode (no cross-tenant existence leak).
        await harness.use_case(FakeDocumentProcessor()).execute(job.id, TenantId("tenant-2"))


def test_scope_validator_raises_on_mismatched_tenant() -> None:
    job = make_job(tenant_id="tenant-1")
    with pytest.raises(TenantScopeViolationError):
        ScopeValidator.ensure_job_in_tenant(job, TenantId("tenant-2"))


def test_scope_validator_passes_on_matching_tenant() -> None:
    job = make_job(tenant_id="tenant-1")
    ScopeValidator.ensure_job_in_tenant(job, TenantId("tenant-1"))


# --- ScheduleRecovery -------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_recovery_reschedules_stuck_executions() -> None:
    job = make_job(status=JobStatus.PROCESSING)
    job.register_execution(ExecutionId("job-1::gen-0"))
    job_repo = FakeJobRepository([job])

    execution = make_execution()
    execution.mark_started()
    execution.started_at = datetime.now(UTC) - timedelta(
        minutes=DEFAULT_STUCK_JOB_THRESHOLD_MINUTES + 1
    )
    execution_repo = FakeExecutionRepository([execution])
    audit_repo = FakeAuditRepository()
    dispatcher = FakeJobDispatcher()

    use_case = ScheduleRecovery(
        job_repo,
        execution_repo,
        audit_repo,
        dispatcher,
        stuck_threshold_minutes=DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
    )
    recovered = await use_case.execute()

    assert recovered == 1
    stuck = await execution_repo.get_by_id(execution.id)
    assert stuck is not None and stuck.status == JobStatus.FAILED
    assert dispatcher.dispatched == [(job.id, job.tenant_id)]
    assert len(audit_repo.entries) == 1


@pytest.mark.asyncio
async def test_schedule_recovery_ignores_healthy_executions() -> None:
    job = make_job(status=JobStatus.PROCESSING)
    execution = make_execution()
    execution.mark_started()

    use_case = ScheduleRecovery(
        FakeJobRepository([job]),
        FakeExecutionRepository([execution]),
        FakeAuditRepository(),
        FakeJobDispatcher(),
        stuck_threshold_minutes=DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
    )
    assert await use_case.execute() == 0


@pytest.mark.asyncio
async def test_schedule_recovery_stops_dispatching_beyond_max_attempts() -> None:
    job = make_job(status=JobStatus.PROCESSING)
    execution = make_execution(generation=4)
    execution.mark_started()
    execution.started_at = datetime.now(UTC) - timedelta(
        minutes=DEFAULT_STUCK_JOB_THRESHOLD_MINUTES + 1
    )
    dispatcher = FakeJobDispatcher()

    use_case = ScheduleRecovery(
        FakeJobRepository([job]),
        FakeExecutionRepository([execution]),
        FakeAuditRepository(),
        dispatcher,
        stuck_threshold_minutes=DEFAULT_STUCK_JOB_THRESHOLD_MINUTES,
        max_retry_attempts=5,
    )
    recovered = await use_case.execute()

    assert recovered == 0
    assert dispatcher.dispatched == []


# --- GetJobHistory -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_history_assembles_full_history() -> None:
    job = make_job()
    job.register_execution(ExecutionId("job-1::gen-0"))
    job_repo = FakeJobRepository([job])
    execution = make_execution()
    execution_repo = FakeExecutionRepository([execution])
    work_unit_repo = FakeWorkUnitRepository()
    audit_repo = FakeAuditRepository()
    await audit_repo.record(
        job_id=job.id,
        execution_id=execution.id,
        event_type=AuditEventType.EXECUTION_STARTED,
        message="started",
    )

    use_case = GetJobHistory(job_repo, execution_repo, work_unit_repo, audit_repo)
    history = await use_case.execute(job.id, job.tenant_id)

    assert history.job.id == job.id
    assert len(history.executions) == 1
    assert history.executions[0].execution.id == execution.id
    assert len(history.audit_log) == 1


@pytest.mark.asyncio
async def test_get_job_history_raises_when_job_missing() -> None:
    use_case = GetJobHistory(
        FakeJobRepository(),
        FakeExecutionRepository(),
        FakeWorkUnitRepository(),
        FakeAuditRepository(),
    )
    with pytest.raises(JobNotFoundError):
        await use_case.execute(JobId("ghost"), TenantId("tenant-1"))
