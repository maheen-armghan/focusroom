"""
backend/api/files.py
File upload (local disk in dev, S3 in production) and listing.
"""
from __future__ import annotations
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse

from backend.config import get_settings
from backend.services.room_service import get_room
from backend.storage.redis_client import get_redis
from backend.utils.sanitize import sanitize_filename
import json

router   = APIRouter(prefix="/api/rooms", tags=["files"])
settings = get_settings()

MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED   = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".pptx", ".txt", ".md"}


@router.post("/{room_id}/files")
async def upload_file(
    room_id:    str,
    user_id:    str  = Form(...),
    username:   str  = Form(...),
    file:       UploadFile = File(...),
):
    room = await get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, f"File type {ext} not allowed")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {settings.MAX_FILE_SIZE_MB} MB limit")

    safe_name = sanitize_filename(file.filename)
    file_id   = str(uuid.uuid4())[:8]
    stored_name = f"{file_id}_{safe_name}"

    # ── Local storage (dev) ────────────────────────────────────────────────────
    upload_dir = Path(settings.LOCAL_STORAGE_DIR) / room_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path  = upload_dir / stored_name

    with open(file_path, "wb") as f:
        f.write(content)

    file_meta = {
        "file_id":      file_id,
        "room_id":      room_id,
        "uploader_id":  user_id,
        "uploader_name": username,
        "filename":     safe_name,
        "stored_name":  stored_name,
        "size_bytes":   len(content),
        "uploaded_at":  time.time(),
        "url":          f"/api/rooms/{room_id}/files/{file_id}/download",
    }

    redis = await get_redis()
    await redis.rpush(f"files:{room_id}", json.dumps(file_meta))
    await redis.expire(f"files:{room_id}", settings.FILE_TTL_HOURS * 3600)

    return file_meta


@router.get("/{room_id}/files")
async def list_files(room_id: str):
    redis = await get_redis()
    raw   = await redis.lrange(f"files:{room_id}", 0, -1)
    return [json.loads(f) for f in raw]


@router.get("/{room_id}/files/{file_id}/download")
async def download_file(room_id: str, file_id: str):
    redis = await get_redis()
    raw   = await redis.lrange(f"files:{room_id}", 0, -1)
    for item in raw:
        meta = json.loads(item)
        if meta["file_id"] == file_id:
            path = Path(settings.LOCAL_STORAGE_DIR) / room_id / meta["stored_name"]
            if not path.exists():
                raise HTTPException(404, "File not found on disk")
            return FileResponse(str(path), filename=meta["filename"])
    raise HTTPException(404, "File not found")


@router.delete("/{room_id}/files/{file_id}")
async def delete_file(room_id: str, file_id: str, user_id: str):
    redis = await get_redis()
    raw   = await redis.lrange(f"files:{room_id}", 0, -1)
    for item in raw:
        meta = json.loads(item)
        if meta["file_id"] == file_id:
            if meta["uploader_id"] != user_id:
                raise HTTPException(403, "Only the uploader can delete this file")
            # Remove from Redis list
            await redis.lrem(f"files:{room_id}", 1, item)
            # Remove from disk
            path = Path(settings.LOCAL_STORAGE_DIR) / room_id / meta["stored_name"]
            if path.exists():
                os.remove(path)
            return {"deleted": True}
    raise HTTPException(404, "File not found")
