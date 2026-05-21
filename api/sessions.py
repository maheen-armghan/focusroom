"""backend/api/sessions.py"""
from fastapi import APIRouter, HTTPException
from backend.services.room_service import get_room

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/{room_id}/leaderboard")
async def get_leaderboard(room_id: str):
    room = await get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    # Leaderboard is computed at session end and stored; return from Redis
    from backend.storage.redis_client import get_redis
    import json
    redis = await get_redis()
    raw   = await redis.get(f"leaderboard:{room_id}")
    if not raw:
        raise HTTPException(404, "Leaderboard not yet available")
    return json.loads(raw)
