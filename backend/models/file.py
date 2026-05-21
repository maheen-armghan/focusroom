"""backend/models/file.py"""
from pydantic import BaseModel
from typing import Optional


class SharedFile(BaseModel):
    file_id:    str
    room_id:    str
    uploader_id:   str
    uploader_name: str
    filename:   str
    size_bytes: int
    uploaded_at: float
    url:        Optional[str] = None   # download URL
