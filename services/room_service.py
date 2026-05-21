"""
backend/services/room_service.py
Create, retrieve, and close study rooms.
"""
from __future__ import annotations
import json
import time
import uuid
from typing import Optional

from backend.storage.redis_client import get_redis
from backend.services.invite_service import create_invite_code
from backend.config import get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()


async def create_room(host_name: str, theme: str = "cafe",
                      duration_minutes: Optional[int] = None) -> dict:
    redis = await get_redis()
    room_id     = str(uuid.uuid4())
    invite_code = await create_invite_code(room_id)
    ttl         = settings.ROOM_TTL_HOURS * 3600

    room = {
        "room_id":          room_id,
        "invite_code":      invite_code,
        "theme":            theme,
        "host_name":        host_name,
        "created_at":       time.time(),
        "duration_minutes": duration_minutes,
        "is_active":        True,
    }
    await redis.setex(f"room:{room_id}", ttl, json.dumps(room))
    log.info(f"Room created: {room_id} code={invite_code}")
    return room


async def get_room(room_id: str) -> Optional[dict]:
    redis = await get_redis()
    data  = await redis.get(f"room:{room_id}")
    return json.loads(data) if data else None


async def close_room(room_id: str):
    redis = await get_redis()
    data  = await redis.get(f"room:{room_id}")
    if data:
        room = json.loads(data)
        room["is_active"] = False
        # Keep for 24h after close so leaderboard link still works
        await redis.setex(f"room:{room_id}", 86400, json.dumps(room))
    log.info(f"Room closed: {room_id}")
