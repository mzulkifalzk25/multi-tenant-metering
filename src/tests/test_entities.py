from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from src.entities.audit_log import AuditLogEntry
from src.entities.execution import Execution
from src.entities.job import Job
from src.entities.status import Status
from src.entities.tenant import Tenant
from src.entities.work_unit import WorkUnit
from src.shared.constants import AuditEventType, FileType, StageName, WorkUnitType
from src.shared.errors import InvalidJobStatusError
from src.shared.types import (
    AuditLogId,
    ExecutionId,
    JobId,
    JobStatus,
    TenantId,
    UserId,
    WorkUnitId,
)

# --- Job ---------------------------------------------------------------------


def _make_job(status: JobStatus = JobStatus.PENDING) -> Job:
    return Job(
        id=JobId("job1"),
        tenant_id=TenantId("tenant1"),
        user_id=UserId("user1"),
        file_path="/path/to/file.pdf",
        file_type=FileType.PDF,
        status=status,
    )


def test_job_can_retry_when_failed() -> None:
    assert _make_job(JobStatus.FAILED).can_retry() is True


def test_job_can_retry_when_pending() -> None:
    assert _make_job(JobStatus.PENDING).can_retry() is True


def test_job_cannot_retry_when_completed() -> None:
    assert _make_job(JobStatus.COMPLETED).can_retry() is False


def test_job_cannot_retry_when_processing() -> None:
    assert _make_job(JobStatus.PROCESSING).can_retry() is False


def test_job_is_terminal_state() -> None:
    assert _make_job(JobStatus.COMPLETED).is_terminal_state() is True
    assert _make_job(JobStatus.FAILED).is_terminal_state() is True
    assert _make_job(JobStatus.PENDING).is_terminal_state() is False


def test_job_next_generation_increments_with_registered_executions() -> None:
    job = _make_job()
    assert job.next_generation() == 0
    job.register_execution(ExecutionId("job1::gen-0"))
    assert job.next_generation() == 1


def test_job_register_execution_moves_to_processing() -> None:
    job = _make_job()
    job.register_execution(ExecutionId("job1::gen-0"))
    assert job.status == JobStatus.PROCESSING
    assert job.execution_ids == [ExecutionId("job1::gen-0")]


def test_job_ensure_mutable_raises_when_completed() -> None:
    job = _make_job(JobStatus.COMPLETED)
    with pytest.raises(InvalidJobStatusError):
        job.ensure_mutable()


def test_job_ensure_mutable_allows_pending() -> None:
    _make_job(JobStatus.PENDING).ensure_mutable()


# --- Execution ---------------------------------------------------------------


def test_execution_lifecycle() -> None:
    execution = Execution(id=ExecutionId("exec1"), job_id=JobId("job1"), generation=0)
    assert execution.status.value == "pending"

    execution.mark_started()
    assert execution.status.value == "processing"
    assert execution.started_at is not None

    execution.mark_completed()
    assert execution.status == JobStatus.COMPLETED
    assert execution.completed_at is not None


def test_execution_mark_started_is_idempotent() -> None:
    execution = Execution(id=ExecutionId("exec1"), job_id=JobId("job1"), generation=0)
    execution.mark_started()
    first_started_at = execution.started_at
    execution.mark_started()
    assert execution.started_at == first_started_at


def test_execution_is_stuck_only_when_processing_past_threshold() -> None:
    execution = Execution(id=ExecutionId("exec1"), job_id=JobId("job1"), generation=0)
    now = datetime.now(UTC)
    assert execution.is_stuck(now=now, threshold_minutes=15) is False

    execution.mark_started()
    started_at = execution.started_at
    assert started_at is not None
    assert execution.is_stuck(now=started_at, threshold_minutes=15) is False

    future = started_at + timedelta(minutes=16)
    assert execution.is_stuck(now=future, threshold_minutes=15) is True


def test_execution_not_stuck_once_completed() -> None:
    execution = Execution(id=ExecutionId("exec1"), job_id=JobId("job1"), generation=0)
    execution.mark_started()
    execution.mark_completed()
    future = datetime.now(UTC) + timedelta(hours=1)
    assert execution.is_stuck(now=future, threshold_minutes=15) is False


# --- WorkUnit ------------------------------------------------------------------


def test_work_unit_idempotency_key_is_deterministic() -> None:
    key_a = WorkUnit.idempotency_key(ExecutionId("exec1"), WorkUnitType.PAGE, 3)
    key_b = WorkUnit.idempotency_key(ExecutionId("exec1"), WorkUnitType.PAGE, 3)
    assert key_a == key_b


def test_work_unit_idempotency_key_differs_by_coordinate() -> None:
    base = WorkUnit.idempotency_key(ExecutionId("exec1"), WorkUnitType.PAGE, 3)
    assert base != WorkUnit.idempotency_key(ExecutionId("exec1"), WorkUnitType.PAGE, 4)
    assert base != WorkUnit.idempotency_key(ExecutionId("exec1"), WorkUnitType.FRAME, 3)
    assert base != WorkUnit.idempotency_key(ExecutionId("exec2"), WorkUnitType.PAGE, 3)


def test_work_unit_state_transitions() -> None:
    work_unit = WorkUnit(
        id=WorkUnitId("wu1"),
        job_id=JobId("job1"),
        execution_id=ExecutionId("exec1"),
        unit_type=WorkUnitType.PAGE,
        unit_number=0,
    )
    assert work_unit.status.value == "pending"

    work_unit.mark_processing()
    assert work_unit.status.value == "processing"

    work_unit.mark_failed("boom")
    assert work_unit.status.value == "failed"
    assert work_unit.error == "boom"

    work_unit.mark_completed()
    assert work_unit.status.value == "completed"
    assert work_unit.error is None


# --- Status --------------------------------------------------------------------


def test_status_valid_transition() -> None:
    status = Status(execution_id=ExecutionId("exec1"))
    status.advance(StageName.EXPANDED)
    assert status.stage == StageName.EXPANDED


def test_status_invalid_transition_raises() -> None:
    status = Status(execution_id=ExecutionId("exec1"))
    with pytest.raises(ValueError):
        status.advance(StageName.COMPLETED)


def test_status_terminal_stages_have_no_further_transitions() -> None:
    status = Status(execution_id=ExecutionId("exec1"), stage=StageName.COMPLETED)
    assert status.is_terminal() is True
    with pytest.raises(ValueError):
        status.advance(StageName.FAILED)


# --- AuditLogEntry ---------------------------------------------------------------


def test_audit_log_entry_is_immutable() -> None:
    entry = AuditLogEntry.record(
        id=AuditLogId("audit1"),
        job_id=JobId("job1"),
        execution_id=ExecutionId("exec1"),
        event_type=AuditEventType.JOB_INGESTED,
        message="job ingested",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.message = "tampered"  # type: ignore[misc]


def test_audit_log_entry_allows_no_execution_for_pre_execution_events() -> None:
    entry = AuditLogEntry.record(
        id=AuditLogId("audit1"),
        job_id=JobId("job1"),
        execution_id=None,
        event_type=AuditEventType.JOB_INGESTED,
        message="job ingested",
    )
    assert entry.execution_id is None


# --- Tenant ----------------------------------------------------------------------


def test_tenant_ensure_active_raises_when_inactive() -> None:
    tenant = Tenant(id=TenantId("tenant1"), name="Acme", is_active=False)
    with pytest.raises(ValueError):
        tenant.ensure_active()


def test_tenant_ensure_active_passes_when_active() -> None:
    Tenant(id=TenantId("tenant1"), name="Acme", is_active=True).ensure_active()
