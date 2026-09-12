"""Redis pub/sub consumer for job ingestion.

Runs as a standalone process (or background task) subscribed to the
configured ingestion channel. Connection drops are retried with backoff
so a transient Redis restart does not require restarting the consumer.
"""

from __future__ import annotations

import asyncio

import structlog
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.interfaces.consumers.event_handlers import handle_job_submission_message
from src.shared.constants import compute_backoff_seconds

logger = structlog.get_logger(__name__)


class JobConsumer:
    def __init__(
        self,
        redis_client: Redis[str],
        channel: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._redis = redis_client
        self._channel = channel
        self._session_factory = session_factory

    async def run_forever(self) -> None:
        attempt = 0
        while True:
            try:
                await self._subscribe_and_listen()
                attempt = 0
            except RedisConnectionError as exc:
                delay = compute_backoff_seconds(attempt)
                logger.warning(
                    "job_consumer.connection_lost", error=str(exc), retry_in_seconds=delay
                )
                await asyncio.sleep(delay)
                attempt += 1

    async def _subscribe_and_listen(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel)
        logger.info("job_consumer.subscribed", channel=self._channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                await self._handle_message(message["data"])
        finally:
            await pubsub.unsubscribe(self._channel)

    async def _handle_message(self, raw_message: str) -> None:
        async with self._session_factory() as session:
            try:
                await handle_job_submission_message(session, raw_message)
            except Exception:  # noqa: BLE001 - one bad message must not kill the loop
                logger.exception("job_consumer.handler_error")
