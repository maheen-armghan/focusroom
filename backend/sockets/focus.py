"""
backend/sockets/focus.py
Receives base64 eye crop → CNN inference → broadcasts focus score.
"""
from backend.ml.cnn_model import predict
from backend.services.focus_service import record_score, get_group_average
from backend.sockets.connection import get_room_participants, get_participant
from backend.utils.logger import get_logger

log = get_logger(__name__)


def register(sio):

    @sio.on("room:focus:frame")
    async def on_focus_frame(sid, data):
        """
        data = {room_id, user_id, eye_crop_b64: str}
        Runs CNN inference and broadcasts the score to the whole room.
        """
        room_id     = data.get("room_id")
        user_id     = data.get("user_id")
        eye_b64     = data.get("eye_crop_b64", "")

        if not eye_b64:
            return

        result = predict(eye_b64)

        score = result["score"]
        state = result["state"]

        # Persist to Redis time-series
        await record_score(room_id, user_id, score, state)

        # Get participant info for the broadcast
        p = get_participant(room_id, user_id)
        username = p["username"] if p else "Unknown"
        avatar   = p["avatar"]   if p else "🦊"

        # Broadcast this user's score to everyone in the room
        await sio.emit("room:focus:score", {
            "user_id":  user_id,
            "username": username,
            "avatar":   avatar,
            "score":    score,
            "state":    state,
            "probs":    result.get("probs", {}),
        }, room=room_id)

        # Every 5 seconds broadcast group average
        # (simple counter — in production use a proper interval)
        participants = get_room_participants(room_id)
        uids         = [p["user_id"] for p in participants]
        group_avg    = await get_group_average(room_id, uids)
        await sio.emit("room:focus:group_avg", {
            "avg": group_avg
        }, room=room_id)

    @sio.on("room:camera:toggle")
    async def on_camera_toggle(sid, data):
        """data = {room_id, user_id, camera_on: bool}"""
        from backend.sockets.connection import _rooms
        room_id  = data.get("room_id")
        user_id  = data.get("user_id")
        cam_on   = data.get("camera_on", True)

        room_p = _rooms.get(room_id, {})
        if user_id in room_p:
            room_p[user_id]["camera_on"] = cam_on

        await sio.emit("room:participants",
                       list(room_p.values()),
                       room=room_id)
