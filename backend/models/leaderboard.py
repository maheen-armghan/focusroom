"""backend/models/leaderboard.py"""
from pydantic import BaseModel
from typing import Optional


class LeaderboardEntry(BaseModel):
    rank:          int
    user_id:       str
    username:      str
    avatar:        str
    avg_score:     float
    focused_time:  int        # seconds
    trophy:        bool = False
    late_join:     bool = False
    no_camera:     bool = False
