"""backend/models/user.py"""
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid

from pydantic import BaseModel, EmailStr
from typing import Optional

from backend.database import Base


# ══════════════════════════════════════════════════════════════════════════════
# SQLALCHEMY MODEL (Database)
# ══════════════════════════════════════════════════════════════════════════════

class User(Base):
    """Database user table."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username}>"


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS (API Request/Response)
# ══════════════════════════════════════════════════════════════════════════════

class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    username: str
    password: str


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User response (no password)."""
    id: str
    email: str
    username: str
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class Participant(BaseModel):
    user_id:    str
    username:   str
    avatar:     str = "🦊"
    room_id:    str
    joined_at:  float   # unix timestamp
    is_host:    bool = False


class FocusReading(BaseModel):
    user_id:    str
    room_id:    str
    score:      float       # 0-100
    state:      str         # focused | distracted | closed
    timestamp:  float
