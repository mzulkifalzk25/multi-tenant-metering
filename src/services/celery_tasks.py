"""Celery task definitions: idempotent job processing and recovery scanning.

Both tasks are thin wrappers: all business logic lives in the use-case
layer, reached through :class:`JobOrchestrator` / :class:`ScheduleRecovery`.
A task's only infrastructure-specific job is opening a DB session per
invocation and translating failures into Celery's retry mechanism.
"""

from __future__ import annotations

import asyncio

import structlog
from celery import Task

from src.frameworks.celery_config import create_celery_app
from src.frameworks.database import Database
from src.frameworks.settings import Settings
from src.repositories.audit_repository import AuditRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.job_repository import JobRepository
from src.services.document_processor import DocumentProcessor
from src.services.job_orchestrator import JobOrchestrator
from src.services.llm_service import LLMServiceProtocol, NullLLMService, OpenRouterLLMService
from src.shared.constants import compute_backoff_seconds
from src.shared.types import ExecutionId, JobId, TenantId
from src.use_cases.schedule_recovery import ScheduleRecovery

logger = structlog.get_logger(__name__)

settings = Settings.from_env()
celery_app = create_celery_app(settings)
database = Database(settings)


def _build_llm_service() -> LLMServiceProtocol:
    if settings.llm_api_key:
        return OpenRouterLLMService(settings.llm_api_key, settings.llm_model)
    return NullLLMService()


class CeleryJobDispatcher:
    """Implements JobDispatcherProtocol on top of the Celery task queue."""

    def dispatch(self, job_id: JobId, tenant_id: TenantId) -> None:
        process_job_task.delay(str(job_id), str(tenant_id))


@celery_app.task(bind=True, max_retries=settings.celery_max_retries, name="process_job_task")  # type: ignore[misc]
def process_job_task(
    self: Task,
    job_id: str,
    tenant_id: str,
    execution_id: str | None = None,
) -> dict[str, str | int]:
    orchestrator = JobOrchestrator(
        database.session_factory, DocumentProcessor(llm_service=_build_llm_service())
    )
    try:
        result = asyncio.run(
            orchestrator.run(
                JobId(job_id),
                TenantId(tenant_id),
                ExecutionId(execution_id) if execution_id else None,
            )
        )
    except Exception as exc:  # noqa: BLE001 - translated into a Celery retry
        countdown = compute_backoff_seconds(
            self.request.retries, base_seconds=settings.celery_retry_backoff_base_seconds
        )
        logger.warning(
            "process_job_task.retry",
            job_id=job_id,
            tenant_id=tenant_id,
            attempt=self.request.retries,
            countdown=countdown,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=countdown) from exc

    logger.info(
        "process_job_task.completed",
        job_id=job_id,
        execution_id=result.execution_id,
        generation=result.generation,
        status=result.status,
    )
    return {
        "execution_id": result.execution_id,
        "generation": result.generation,
        "status": result.status,
    }


@celery_app.task(name="schedule_recovery_task")  # type: ignore[misc]
def schedule_recovery_task() -> int:
    """Periodic task (see beat_schedule in celery_config) that finds
    executions stuck in PROCESSING beyond the configured threshold and
    dispatches a fresh, non-destructive retry generation for each."""

    async def _run() -> int:
        async with database.session_factory() as session:
            use_case = ScheduleRecovery(
                job_repo=JobRepository(session),
                execution_repo=ExecutionRepository(session),
                audit_repo=AuditRepository(session),
                dispatcher=CeleryJobDispatcher(),
                stuck_threshold_minutes=settings.stuck_job_threshold_minutes,
                max_retry_attempts=settings.celery_max_retries,
            )
            recovered = await use_case.execute()
            await session.commit()
            return recovered

    recovered_count = asyncio.run(_run())
    logger.info("schedule_recovery_task.completed", recovered=recovered_count)
    return recovered_count
