"""
backend/sockets/session.py
Session end → leaderboard + Gemini chat summary.
"""
from __future__ import annotations
import asyncio

from backend.services.leaderboard_service import compute_leaderboard
from backend.services.summary_service import generate_summary
from backend.services.room_service import close_room, get_room
from backend.sockets.connection import get_room_participants
from backend.utils.logger import get_logger

log = get_logger(__name__)


def register(sio):

    @sio.on("room:session:end")
    async def on_session_end(sid, data):
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        await trigger_session_end(sio, room_id)


async def trigger_session_end(sio, room_id: str):
    """Called by timer expiry or host manual end."""
    log.info(f"Session ending: {room_id}")

    participants = get_room_participants(room_id)
    room         = await get_room(room_id)
    room_name    = room.get("theme", "Study Room").capitalize() if room else "Study Room"

    # ── Compute leaderboard synchronously ────────────────────────────────────
    leaderboard = await compute_leaderboard(room_id, participants)

    # ── Broadcast session end + leaderboard immediately ───────────────────────
    await sio.emit("room:session:ended", {
        "leaderboard": leaderboard,
        "summary":     None,   # will arrive separately in ~10s
    }, room=room_id)

    # ── Generate AI summary in background ────────────────────────────────────
    asyncio.create_task(_generate_and_send_summary(sio, room_id, room_name))

    # ── Close room ────────────────────────────────────────────────────────────
    await close_room(room_id)


async def _generate_and_send_summary(sio, room_id: str, room_name: str):
    try:
        summary = await generate_summary(room_id, room_name)
        await sio.emit("room:session:summary", {"summary": summary}, room=room_id)
    except Exception as e:
        log.error(f"Summary generation failed: {e}")
        await sio.emit("room:session:summary",
                       {"summary": "Summary unavailable."},
                       room=room_id)
