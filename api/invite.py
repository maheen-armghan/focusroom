"""backend/api/invite.py"""
from fastapi import APIRouter, HTTPException
from backend.services.invite_service import get_room_id_by_code
from backend.services.room_service import get_room

router = APIRouter(prefix="/api/join", tags=["invite"])


@router.get("/{code}")
async def join_by_code(code: str):
    room_id = await get_room_id_by_code(code)
    if not room_id:
        raise HTTPException(404, "This code is invalid or the session has ended.")
    room = await get_room(room_id)
    if not room or not room.get("is_active"):
        raise HTTPException(410, "This session has ended.")
    return room
