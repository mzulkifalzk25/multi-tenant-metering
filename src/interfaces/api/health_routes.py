from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from src.frameworks.database import Database
from src.shared.validators import HealthResponseSchema

router = APIRouter()


@router.get("", response_model=HealthResponseSchema)
async def health_check(request: Request) -> HealthResponseSchema:
    database: Database = request.app.state.database

    database_status = "ok"
    try:
        async with database.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - health check must never raise
        database_status = "unavailable"

    redis_status = "ok"
    try:
        await request.app.state.redis.ping()
    except Exception:  # noqa: BLE001 - health check must never raise
        redis_status = "unavailable"

    overall = "ok" if database_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponseSchema(status=overall, database=database_status, redis=redis_status)
