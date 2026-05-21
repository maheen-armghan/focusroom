"""backend/models/timer.py"""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class TimerStatus(str, Enum):
    idle    = "idle"
    running = "running"
    paused  = "paused"
    ended   = "ended"


class TimerState(BaseModel):
    room_id:          str
    duration_seconds: int
    remaining_seconds: int
    status:           TimerStatus = TimerStatus.idle
    started_at:       Optional[float] = None
    paused_at:        Optional[float] = None
