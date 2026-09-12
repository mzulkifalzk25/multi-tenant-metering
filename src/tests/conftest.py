"""Shared pytest fixtures.

Fixtures that need real infrastructure (PostgreSQL, Redis) probe for it on
the ports docker-compose.yml exposes and skip gracefully if it is not
running, so ``pytest`` still passes the unit-test suite in an environment
with no services up, while ``docker compose up -d && pytest`` also
exercises the integration suite.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator

TEST_DATABASE_URL = "postgresql+asyncpg://pipeline:pipeline@localhost:5544/document_pipeline"
TEST_REDIS_URL = "redis://localhost:6380/0"

# Settings.from_env() is called at *import time* by src.frameworks.fastapi_app
# and src.services.celery_tasks. Some test module may import those
# (transitively, e.g. via jobs_routes) before ever reaching a fixture, so
# these defaults must be in place before any project module is imported --
# hence setting them here, at conftest module scope, rather than in a
# fixture.
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
os.environ.setdefault("REDIS_URL", TEST_REDIS_URL)
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6380/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6380/2")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from src.repositories.database import (  # noqa: E402
    create_all,
    create_engine,
    create_session_factory,
    drop_all,
)


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    return _port_open("localhost", 5544)


@pytest.fixture(scope="session")
def redis_available() -> bool:
    return _port_open("localhost", 6380)


@pytest_asyncio.fixture
async def db_session_factory(
    postgres_available: bool,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if not postgres_available:
        pytest.skip("PostgreSQL is not available on localhost:5544 -- run docker-compose up -d")
    engine = create_engine(TEST_DATABASE_URL)
    await create_all(engine)
    try:
        yield create_session_factory(engine)
    finally:
        await drop_all(engine)
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with db_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def redis_client(redis_available: bool) -> AsyncIterator[Redis[str]]:
    if not redis_available:
        pytest.skip("Redis is not available on localhost:6380 -- run docker-compose up -d")
    client: Redis[str] = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        # types-redis lags redis-py 5.x's aclose() (the non-deprecated
        # replacement for close()); it exists at runtime.
        await client.aclose()  # type: ignore[attr-defined]
