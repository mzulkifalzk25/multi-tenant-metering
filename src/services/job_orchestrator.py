"""Wires a database session and repositories around ProcessJob for a single
Celery task invocation, and commits the unit of work on success."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.repositories.audit_repository import AuditRepository
from src.repositories.execution_repository import ExecutionRepository
from src.repositories.job_repository import JobRepository
from src.repositories.status_repository import StatusRepository
from src.repositories.work_unit_repository import WorkUnitRepository
from src.shared.types import ExecutionId, JobId, TenantId
from src.use_cases.process_job import ProcessJob
from src.use_cases.protocols import DocumentProcessorProtocol


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    execution_id: str
    generation: int
    status: str


class _SessionUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()


class JobOrchestrator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        document_processor: DocumentProcessorProtocol,
    ) -> None:
        self._session_factory = session_factory
        self._document_processor = document_processor

    async def run(
        self,
        job_id: JobId,
        tenant_id: TenantId,
        execution_id: ExecutionId | None = None,
    ) -> OrchestrationResult:
        async with self._session_factory() as session:
            use_case = ProcessJob(
                job_repo=JobRepository(session),
                execution_repo=ExecutionRepository(session),
                work_unit_repo=WorkUnitRepository(session),
                status_repo=StatusRepository(session),
                audit_repo=AuditRepository(session),
                document_processor=self._document_processor,
                unit_of_work=_SessionUnitOfWork(session),
            )
            execution = await use_case.execute(job_id, tenant_id, execution_id)
            return OrchestrationResult(
                execution_id=str(execution.id),
                generation=execution.generation,
                status=execution.status.value,
            )
