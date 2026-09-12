"""Wires the SQLAlchemy engine/session factory to application settings."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.frameworks.settings import Settings
from src.repositories.database import create_engine, create_session_factory


class Database:
    def __init__(self, settings: Settings) -> None:
        self._engine: AsyncEngine = create_engine(
            settings.database_url, echo=settings.environment == "development"
        )
        self._session_factory: async_sessionmaker[AsyncSession] = create_session_factory(
            self._engine
        )

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    async def get_session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()
