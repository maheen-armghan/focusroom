"""
backend/services/chat_service.py
Store and retrieve chat messages in Redis for session duration.
"""
from __future__ import annotations
import time
import json
import uuid
from collections import Counter

from backend.storage.redis_client import get_redis
from backend.utils.logger import get_logger

log = get_logger(__name__)
MAX_MSG_LEN = 500
MSG_TTL     = 90000   # 25 hours


async def save_message(room_id: str, user_id: str, username: str,
                       avatar: str, text: str) -> dict:
    if len(text) > MAX_MSG_LEN:
        text = text[:MAX_MSG_LEN]

    redis = await get_redis()
    msg   = {
        "msg_id":    str(uuid.uuid4())[:8],
        "room_id":   room_id,
        "user_id":   user_id,
        "username":  username,
        "avatar":    avatar,
        "text":      text,
        "timestamp": time.time(),
        "is_system": False,
    }
    await redis.rpush(f"chat:{room_id}", json.dumps(msg))
    await redis.expire(f"chat:{room_id}", MSG_TTL)
    return msg


async def save_system_message(room_id: str, text: str) -> dict:
    redis = await get_redis()
    msg   = {
        "msg_id":    str(uuid.uuid4())[:8],
        "room_id":   room_id,
        "user_id":   "system",
        "username":  "System",
        "avatar":    "🔔",
        "text":      text,
        "timestamp": time.time(),
        "is_system": True,
    }
    await redis.rpush(f"chat:{room_id}", json.dumps(msg))
    await redis.expire(f"chat:{room_id}", MSG_TTL)
    return msg


async def get_all_messages(room_id: str) -> list[dict]:
    redis = await get_redis()
    raw   = await redis.lrange(f"chat:{room_id}", 0, -1)
    return [json.loads(m) for m in raw]


async def get_chat_stats(room_id: str) -> dict:
    msgs     = await get_all_messages(room_id)
    human    = [m for m in msgs if not m["is_system"]]
    if not human:
        return {"count": 0, "most_active": None}
    counts   = Counter(m["username"] for m in human)
    return {
        "count":       len(human),
        "most_active": counts.most_common(1)[0][0],
    }


async def delete_chat(room_id: str):
    redis = await get_redis()
    await redis.delete(f"chat:{room_id}")
