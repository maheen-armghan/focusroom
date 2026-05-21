"""
backend/services/leaderboard_service.py
Compute end-of-session leaderboard with trophy assignment.
"""
from __future__ import annotations
from backend.services.focus_service import get_user_average, get_focused_seconds
from backend.utils.logger import get_logger

log = get_logger(__name__)


async def compute_leaderboard(room_id: str, participants: list[dict]) -> list[dict]:
    """
    participants: list of {user_id, username, avatar, joined_at, camera_on}
    Returns ranked list of LeaderboardEntry dicts.
    """
    entries = []
    for p in participants:
        uid       = p["user_id"]
        cam_on    = p.get("camera_on", True)
        avg_score = await get_user_average(room_id, uid) if cam_on else 0.0
        focused_s = await get_focused_seconds(room_id, uid) if cam_on else 0

        entries.append({
            "user_id":      uid,
            "username":     p["username"],
            "avatar":       p.get("avatar", "🦊"),
            "avg_score":    avg_score,
            "focused_time": focused_s,
            "no_camera":    not cam_on,
            "late_join":    p.get("late_join", False),
            "trophy":       False,
            "rank":         0,
        })

    # Sort: camera-off always last, then by avg_score desc
    with_cam    = [e for e in entries if not e["no_camera"]]
    without_cam = [e for e in entries if e["no_camera"]]
    with_cam.sort(key=lambda e: e["avg_score"], reverse=True)

    # Assign ranks (ties share rank)
    rank = 1
    for i, entry in enumerate(with_cam):
        if i > 0 and entry["avg_score"] < with_cam[i-1]["avg_score"]:
            rank = i + 1
        entry["rank"] = rank

    # Trophy: everyone tied at rank 1 gets it
    if with_cam:
        top_score = with_cam[0]["avg_score"]
        for entry in with_cam:
            if entry["avg_score"] == top_score:
                entry["trophy"] = True

    # No-camera entries get rank after everyone else
    last_rank = len(with_cam) + 1
    for entry in without_cam:
        entry["rank"] = last_rank

    return with_cam + without_cam
