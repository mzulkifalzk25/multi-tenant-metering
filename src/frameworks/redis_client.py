"""Redis connection factory used for job-ingestion pub/sub."""

from __future__ import annotations

from redis.asyncio import Redis


def create_redis_client(redis_url: str) -> Redis[str]:
    return Redis.from_url(redis_url, decode_responses=True)
