"""
backend/models/room.py
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class RoomCreate(BaseModel):
    theme: str = "cafe"           # cafe | library | garden | dorm | train
    host_name: str
    duration_minutes: Optional[int] = None


class RoomState(BaseModel):
    room_id: str
    invite_code: str
    theme: str
    host_name: str
    created_at: datetime
    duration_minutes: Optional[int] = None
    participant_count: int = 0
    is_active: bool = True
