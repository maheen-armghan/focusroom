"""backend/sockets/files.py — broadcast file list updates."""
from backend.utils.logger import get_logger

log = get_logger(__name__)


def register(sio):

    @sio.on("room:files:refresh")
    async def on_files_refresh(sid, data):
        """Client requests current file list — served by REST API."""
        pass   # File list is fetched via GET /api/rooms/{id}/files
