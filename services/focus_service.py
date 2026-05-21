"""
backend/services/focus_service.py
Store per-user focus readings and compute aggregates.
"""
from __future__ import annotations
import time
import json
from typing import Optional

from backend.storage.redis_client import get_redis
from backend.utils.logger import get_logger

log = get_logger(__name__)
SCORE_TTL = 90000   # 25 hours


async def record_score(room_id: str, user_id: str, score: float, state: str):
    """Append a focus reading to the user's time-series list in Redis."""
    redis   = await get_redis()
    reading = json.dumps({"score": score, "state": state, "ts": time.time()})
    key     = f"focus:{room_id}:{user_id}"
    await redis.rpush(key, reading)
    await redis.expire(key, SCORE_TTL)
    # Keep latest score for quick lookup
    await redis.setex(f"focus:latest:{room_id}:{user_id}",
                      SCORE_TTL, json.dumps({"score": score, "state": state}))


async def get_latest_scores(room_id: str, user_ids: list[str]) -> dict:
    """Return {user_id: {score, state}} for all users in room."""
    redis  = await get_redis()
    result = {}
    for uid in user_ids:
        raw = await redis.get(f"focus:latest:{room_id}:{uid}")
        result[uid] = json.loads(raw) if raw else {"score": 0, "state": "unknown"}
    return result


async def get_user_average(room_id: str, user_id: str) -> float:
    """Compute average focus score from the full time-series."""
    redis    = await get_redis()
    readings = await redis.lrange(f"focus:{room_id}:{user_id}", 0, -1)
    if not readings:
        return 0.0
    scores = [json.loads(r)["score"] for r in readings]
    return round(sum(scores) / len(scores), 1)


async def get_focused_seconds(room_id: str, user_id: str,
                               threshold: float = 60.0) -> int:
    """Count seconds where score was above threshold (≈ focused)."""
    redis    = await get_redis()
    readings = await redis.lrange(f"focus:{room_id}:{user_id}", 0, -1)
    # Each reading is taken every ~2 seconds
    return sum(2 for r in readings if json.loads(r)["score"] >= threshold)


async def get_group_average(room_id: str, user_ids: list[str]) -> float:
    """Average of all users' latest scores."""
    if not user_ids:
        return 0.0
    redis = await get_redis()
    scores = []
    for uid in user_ids:
        raw = await redis.get(f"focus:latest:{room_id}:{uid}")
        if raw:
            scores.append(json.loads(raw)["score"])
    return round(sum(scores) / len(scores), 1) if scores else 0.0
