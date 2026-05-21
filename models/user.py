"""backend/models/user.py"""
from pydantic import BaseModel
from typing import Optional


class Participant(BaseModel):
    user_id:    str
    username:   str
    avatar:     str = "🦊"
    room_id:    str
    joined_at:  float   # unix timestamp
    is_host:    bool = False


class FocusReading(BaseModel):
    user_id:    str
    room_id:    str
    score:      float       # 0-100
    state:      str         # focused | distracted | closed
    timestamp:  float
