"""
backend/sockets/chat.py
Real-time chat message handling.
"""
from backend.services.chat_service import save_message, get_all_messages
from backend.utils.logger import get_logger

log = get_logger(__name__)


def register(sio):

    @sio.on("room:chat:send")
    async def on_chat_send(sid, data):
        """
        data = {room_id, user_id, username, avatar, text}
        """
        room_id  = data.get("room_id")
        text     = (data.get("text") or "").strip()

        if not text:
            return

        msg = await save_message(
            room_id  = room_id,
            user_id  = data.get("user_id"),
            username = data.get("username", "Anonymous"),
            avatar   = data.get("avatar", "🦊"),
            text     = text,
        )
        # Broadcast to everyone in the room (including sender)
        await sio.emit("room:chat:message", msg, room=room_id)

    @sio.on("room:chat:history")
    async def on_chat_history(sid, data):
        """Send full chat history to a newly joined user."""
        room_id  = data.get("room_id")
        messages = await get_all_messages(room_id)
        await sio.emit("room:chat:history", {"messages": messages}, to=sid)
