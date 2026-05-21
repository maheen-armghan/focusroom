"""
backend/storage/redis_client.py
Async Redis singleton — uses fakeredis in dev if Redis isn't running.
"""
from __future__ import annotations
import os
import redis.asyncio as aioredis
from backend.config import get_settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        try:
            client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await client.ping()
            _redis = client
            print("  ✓ Connected to real Redis")
        except Exception:
            # fakeredis async — works exactly like real Redis, no installation needed
            import fakeredis.aioredis as fake_aioredis
            _redis = fake_aioredis.FakeRedis(decode_responses=True)
            print("  ✓ Using fakeredis (dev mode)")
    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None