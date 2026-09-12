"""Pydantic v2 schemas used at the boundaries: HTTP API and pub/sub messages.

All models are strict: no silent coercion between types, and unknown fields
are rejected so malformed producer messages fail loudly instead of being
partially ingested.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.shared.constants import AuditEventType, FileType


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SubmitJobRequestSchema(StrictModel):
    tenant_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    # Pydantic strict mode requires an actual Enum *instance* by default and
    # will reject the plain string every real JSON producer sends (e.g.
    # "pdf") -- strict=False here is a deliberate, narrow opt-out so the
    # boundary still coerces string -> FileType while everything else on
    # this model stays strict.
    file_type: FileType = Field(strict=False)

    @field_validator("file_path")
    @classmethod
    def file_path_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("file_path must not be blank")
        return value


class SubmitJobBodySchema(StrictModel):
    """HTTP request body for POST /jobs/{tenant_id}/submit.

    tenant_id and user_id are deliberately absent here: they come from the
    URL path and the authenticated caller, never from client-supplied JSON,
    so a caller cannot submit a job on another tenant's behalf.
    """

    file_path: str = Field(min_length=1)
    file_type: FileType = Field(strict=False)


class JobSubmittedResponseSchema(StrictModel):
    job_id: str
    status: str


class WorkUnitResponseSchema(StrictModel):
    id: str
    unit_type: str
    unit_number: int
    status: str
    error: str | None


class ExecutionResponseSchema(StrictModel):
    id: str
    generation: int
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    work_units: list[WorkUnitResponseSchema]


class AuditLogResponseSchema(StrictModel):
    id: str
    event_type: AuditEventType
    message: str
    created_at: datetime


class JobHistoryResponseSchema(StrictModel):
    job_id: str
    tenant_id: str
    status: str
    file_type: str
    created_at: datetime
    executions: list[ExecutionResponseSchema]
    audit_log: list[AuditLogResponseSchema]


class HealthResponseSchema(StrictModel):
    status: str
    database: str
    redis: str
