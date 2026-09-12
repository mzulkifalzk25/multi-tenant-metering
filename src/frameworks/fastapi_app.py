"""FastAPI application factory: routers, lifespan, and error translation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.frameworks.database import Database
from src.frameworks.redis_client import create_redis_client
from src.frameworks.settings import Settings
from src.interfaces.api.health_routes import router as health_router
from src.interfaces.api.jobs_routes import router as jobs_router
from src.shared.errors import (
    DocumentProcessingError,
    DomainError,
    ExecutionNotFoundError,
    IdempotencyError,
    InvalidJobStatusError,
    JobNotFoundError,
    TenantNotFoundError,
    TenantScopeViolationError,
    UnsupportedFileTypeError,
    WorkUnitNotFoundError,
)

_ERROR_STATUS_CODES: dict[type[DomainError], int] = {
    JobNotFoundError: 404,
    ExecutionNotFoundError: 404,
    WorkUnitNotFoundError: 404,
    TenantNotFoundError: 404,
    TenantScopeViolationError: 403,
    InvalidJobStatusError: 409,
    UnsupportedFileTypeError: 400,
    IdempotencyError: 409,
    DocumentProcessingError: 422,
}


def _status_code_for(error: DomainError) -> int:
    for error_type, status_code in _ERROR_STATUS_CODES.items():
        if isinstance(error, error_type):
            return status_code
    return 400


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    database = Database(settings)
    redis_client = create_redis_client(settings.redis_url)
    app.state.settings = settings
    app.state.database = database
    app.state.redis = redis_client
    try:
        yield
    finally:
        # types-redis lags redis-py 5.x's aclose() (the non-deprecated
        # replacement for close()); it exists at runtime.
        await redis_client.aclose()  # type: ignore[attr-defined]
        await database.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Async Document Pipeline", lifespan=_lifespan)

    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=_status_code_for(exc), content={"detail": str(exc)})

    return app
