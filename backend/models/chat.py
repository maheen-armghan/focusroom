"""backend/models/chat.py"""
from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    msg_id:    str
    room_id:   str
    user_id:   str
    username:  str
    avatar:    str
    text:      str
    timestamp: float
    is_system: bool = False


class ChatSummary(BaseModel):
    room_id:        str
    summary_text:   str
    generated_at:   float
    message_count:  int
    most_active:    Optional[str] = None
