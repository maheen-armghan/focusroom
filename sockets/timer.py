"""
backend/sockets/timer.py
Host controls the session countdown timer.
"""
from backend.services import timer_service
from backend.sockets.connection import get_participant
from backend.utils.logger import get_logger

log = get_logger(__name__)


def register(sio):

    async def _tick_callback(room_id: str, remaining: int, ended: bool):
        """Called by timer_service every second."""
        if ended:
            await sio.emit("room:timer:ended", {}, room=room_id)
            # Auto-trigger session end
            from backend.sockets.session import trigger_session_end
            await trigger_session_end(sio, room_id)
        else:
            await sio.emit("room:timer:tick",
                           {"remaining": remaining},
                           room=room_id)
            # 5-minute warning
            if remaining == 300:
                await sio.emit("room:timer:warning",
                               {"msg": "Session ending in 5 minutes"},
                               room=room_id)

    @sio.on("room:timer:set")
    async def on_timer_set(sid, data):
        """data = {room_id, user_id, duration_seconds}"""
        room_id  = data.get("room_id")
        user_id  = data.get("user_id")
        duration = int(data.get("duration_seconds", 1500))

        # Clamp to 5 min – 8 hours
        duration = max(300, min(duration, 28800))

        p = get_participant(room_id, user_id)
        if not p or not p.get("is_host"):
            await sio.emit("error", {"msg": "Only the host can set the timer"}, to=sid)
            return

        state = await timer_service.set_timer(room_id, duration)
        await sio.emit("room:timer:state", state, room=room_id)

    @sio.on("room:timer:start")
    async def on_timer_start(sid, data):
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        p       = get_participant(room_id, user_id)
        if not p or not p.get("is_host"):
            return
        state = await timer_service.start_timer(room_id, _tick_callback)
        await sio.emit("room:timer:state", state, room=room_id)

    @sio.on("room:timer:pause")
    async def on_timer_pause(sid, data):
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        p       = get_participant(room_id, user_id)
        if not p or not p.get("is_host"):
            return
        state = await timer_service.pause_timer(room_id)
        await sio.emit("room:timer:state", state, room=room_id)
        from backend.services.chat_service import save_system_message
        msg = await save_system_message(room_id, "Host paused the timer")
        await sio.emit("room:chat:message", msg, room=room_id)

    @sio.on("room:timer:resume")
    async def on_timer_resume(sid, data):
        room_id = data.get("room_id")
        user_id = data.get("user_id")
        p       = get_participant(room_id, user_id)
        if not p or not p.get("is_host"):
            return
        state = await timer_service.resume_timer(room_id, _tick_callback)
        await sio.emit("room:timer:state", state, room=room_id)
