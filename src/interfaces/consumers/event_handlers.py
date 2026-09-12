"""Turns a raw pub/sub payload into a validated IngestJob call.

Kept separate from the transport loop (:mod:`job_consumer`) so message
parsing/validation can be unit tested without a real Redis connection.
"""

from __future__ import annotations

import json

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.audit_repository import AuditRepository
from src.repositories.job_repository import JobRepository
from src.repositories.tenant_repository import TenantRepository
from src.services.celery_tasks import CeleryJobDispatcher
from src.shared.types import JobId, TenantId, UserId
from src.shared.validators import SubmitJobRequestSchema
from src.use_cases.ingest_job import IngestJob

logger = structlog.get_logger(__name__)


async def handle_job_submission_message(session: AsyncSession, raw_message: str) -> JobId | None:
    """Parses and ingests one message. Returns the created JobId, or None if
    the message was malformed (logged and dropped, never raised -- one bad
    message on the channel must not take down the consumer loop)."""
    try:
        payload = json.loads(raw_message)
        request = SubmitJobRequestSchema.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.error("job_consumer.invalid_message", error=str(exc), raw=raw_message)
        return None

    use_case = IngestJob(
        tenant_repo=TenantRepository(session),
        job_repo=JobRepository(session),
        audit_repo=AuditRepository(session),
        dispatcher=CeleryJobDispatcher(),
    )
    job = await use_case.execute(
        tenant_id=TenantId(request.tenant_id),
        user_id=UserId(request.user_id),
        file_path=request.file_path,
        file_type=request.file_type,
    )
    await session.commit()
    logger.info("job_consumer.ingested", job_id=str(job.id))
    return job.id
