"""backend/api/rooms.py"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.services.room_service import create_room, get_room
from backend.services.invite_service import get_room_id_by_code, regenerate_code

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    host_name:        str
    theme:            str = "cafe"
    duration_minutes: Optional[int] = None


@router.post("")
async def post_create_room(req: CreateRoomRequest):
    room = await create_room(
        host_name        = req.host_name,
        theme            = req.theme,
        duration_minutes = req.duration_minutes,
    )
    return room


@router.get("/{room_id}")
async def get_room_detail(room_id: str):
    room = await get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    return room


@router.post("/{room_id}/regenerate-code")
async def post_regen_code(room_id: str):
    room = await get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    new_code = await regenerate_code(room_id)
    return {"invite_code": new_code}
