"""
backend/sockets/connection.py
Socket.IO connect / disconnect / room:join / room:leave handlers.
"""
from __future__ import annotations
import time
import json
import uuid

from backend.storage.redis_client import get_redis
from backend.services.room_service import get_room
from backend.services.chat_service import save_system_message
from backend.utils.logger import get_logger

log = get_logger(__name__)

# In-memory participant store: {room_id: {user_id: participant_dict}}
# Also mirrored to Redis for persistence across restarts
_rooms: dict[str, dict] = {}


def register(sio):
    """Attach all connection handlers to the Socket.IO server instance."""

    @sio.event
    async def connect(sid, environ, auth):
        log.info(f"Client connected: {sid}")

    @sio.event
    async def disconnect(sid):
        log.info(f"Client disconnected: {sid}")
        await _handle_leave(sio, sid)

    @sio.on("room:join")
    async def on_join(sid, data):
        """
        data = {room_id, user_id, username, avatar, is_host}
        """
        room_id  = data.get("room_id")
        user_id  = data.get("user_id", str(uuid.uuid4()))
        username = data.get("username", "Anonymous")
        avatar   = data.get("avatar", "🦊")
        is_host  = data.get("is_host", False)

        room = await get_room(room_id)
        if not room:
            await sio.emit("error", {"msg": "Room not found"}, to=sid)
            return

        participant = {
            "sid":       sid,
            "user_id":   user_id,
            "username":  username,
            "avatar":    avatar,
            "room_id":   room_id,
            "joined_at": time.time(),
            "is_host":   is_host,
            "camera_on": True,
            "late_join": False,
        }

        # Track in memory
        if room_id not in _rooms:
            _rooms[room_id] = {}
        _rooms[room_id][user_id] = participant

        # Store sid → {user_id, room_id} for disconnect lookup
        await _store_sid_mapping(sid, user_id, room_id)

        await sio.enter_room(sid, room_id)

        # Send current room state to the joining user
        await sio.emit("room:state", {
            "room":         room,
            "participants": list(_rooms[room_id].values()),
        }, to=sid)

        # Notify everyone else
        msg = await save_system_message(room_id, f"{username} joined the session")
        await sio.emit("room:chat:message", msg, room=room_id)
        await sio.emit("room:participants", list(_rooms[room_id].values()), room=room_id)
        log.info(f"{username} joined room {room_id}")

    @sio.on("room:leave")
    async def on_leave(sid, data):
        await _handle_leave(sio, sid)


async def _handle_leave(sio, sid: str):
    mapping = await _get_sid_mapping(sid)
    if not mapping:
        return
    user_id = mapping["user_id"]
    room_id = mapping["room_id"]

    room_participants = _rooms.get(room_id, {})
    participant = room_participants.pop(user_id, None)
    username    = participant["username"] if participant else "Someone"

    await sio.leave_room(sid, room_id)
    msg = await save_system_message(room_id, f"{username} left the session")
    await sio.emit("room:chat:message", msg, room=room_id)
    await sio.emit("room:participants", list(room_participants.values()), room=room_id)
    await _delete_sid_mapping(sid)
    log.info(f"{username} left room {room_id}")


def get_room_participants(room_id: str) -> list[dict]:
    return list(_rooms.get(room_id, {}).values())


def get_participant(room_id: str, user_id: str) -> dict | None:
    return _rooms.get(room_id, {}).get(user_id)


# ── Redis sid helpers ──────────────────────────────────────────────────────────

async def _store_sid_mapping(sid: str, user_id: str, room_id: str):
    redis = await get_redis()
    await redis.setex(f"sid:{sid}", 90000,
                      json.dumps({"user_id": user_id, "room_id": room_id}))


async def _get_sid_mapping(sid: str) -> dict | None:
    redis = await get_redis()
    raw   = await redis.get(f"sid:{sid}")
    return json.loads(raw) if raw else None


async def _delete_sid_mapping(sid: str):
    redis = await get_redis()
    await redis.delete(f"sid:{sid}")
