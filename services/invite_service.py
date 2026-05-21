"""
backend/services/invite_service.py
Generate and validate 6-char invite codes stored in Redis.
"""
from __future__ import annotations
from typing import Optional

from backend.storage.redis_client import get_redis
from backend.utils.code_gen import generate_invite_code, normalize_code
from backend.config import get_settings
from backend.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

MAX_ATTEMPTS = 10


async def create_invite_code(room_id: str) -> str:
    """Generate a collision-free code and store room_id → code mapping."""
    redis = await get_redis()
    ttl   = settings.INVITE_CODE_TTL_SEC

    for _ in range(MAX_ATTEMPTS):
        code = generate_invite_code()
        key  = f"room:code:{code}"
        # SET NX — only set if key doesn't exist (collision check)
        ok = await redis.set(key, room_id, ex=ttl, nx=True)
        if ok:
            # Also store reverse mapping room_id → code for display
            await redis.setex(f"room:invite:{room_id}", ttl, code)
            log.info(f"Invite code created: {code} → {room_id}")
            return code

    raise RuntimeError("Could not generate unique invite code after 10 attempts")


async def get_room_id_by_code(code: str) -> Optional[str]:
    """Return room_id for a given code, or None if invalid/expired."""
    redis   = await get_redis()
    norm    = normalize_code(code)
    room_id = await redis.get(f"room:code:{norm}")
    return room_id


async def invalidate_code(code: str):
    """Delete a code immediately (e.g. host regenerated it)."""
    redis = await get_redis()
    await redis.delete(f"room:code:{normalize_code(code)}")


async def regenerate_code(room_id: str) -> str:
    """Invalidate old code and generate a fresh one."""
    redis    = await get_redis()
    old_code = await redis.get(f"room:invite:{room_id}")
    if old_code:
        await invalidate_code(old_code)
    return await create_invite_code(room_id)
