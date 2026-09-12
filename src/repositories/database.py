"""SQLAlchemy 2.0 async engine/session setup and ORM schema.

Engine and session-factory creation are exposed as functions rather than
module-level singletons so tests can point them at an isolated database
without monkeypatching import-time state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_tenant_status", "tenant_id", "status"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    executions: Mapped[list[ExecutionModel]] = relationship(
        back_populates="job", order_by="ExecutionModel.generation"
    )


class ExecutionModel(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("job_id", "generation", name="uq_executions_job_generation"),
        Index("ix_executions_job_status", "job_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("jobs.id"), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[JobModel] = relationship(back_populates="executions")
    work_units: Mapped[list[WorkUnitModel]] = relationship(
        back_populates="execution", order_by="WorkUnitModel.unit_number"
    )
    status_row: Mapped[StatusModel | None] = relationship(back_populates="execution", uselist=False)


class WorkUnitModel(Base):
    __tablename__ = "work_units"
    __table_args__ = (
        UniqueConstraint(
            "execution_id", "unit_type", "unit_number", name="uq_work_units_idempotency"
        ),
        Index("ix_work_units_execution_status", "execution_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("jobs.id"), nullable=False)
    execution_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("executions.id"), nullable=False
    )
    unit_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(String(2048))

    execution: Mapped[ExecutionModel] = relationship(back_populates="work_units")


class StatusModel(Base):
    __tablename__ = "statuses"

    execution_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("executions.id"), primary_key=True
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    execution: Mapped[ExecutionModel] = relationship(back_populates="status_row")


class AuditLogModel(Base):
    """Insert-only table: no repository method ever issues an UPDATE or DELETE."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_job_created", "job_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("jobs.id"), nullable=False)
    execution_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("executions.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(2048), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(database_url, echo=echo, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
