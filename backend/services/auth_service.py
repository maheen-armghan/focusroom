"""
backend/services/auth_service.py
User registration, login, and JWT token creation/verification.
"""
from __future__ import annotations
import uuid
import time
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user_auth import User
from backend.config import get_settings
from backend.utils.logger import get_logger

log      = get_logger(__name__)
settings = get_settings()
pwd_ctx  = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ══════════════════════════════════════════════════════════════════════════════
# PASSWORD
# ══════════════════════════════════════════════════════════════════════════════

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


# ══════════════════════════════════════════════════════════════════════════════
# JWT
# ══════════════════════════════════════════════════════════════════════════════

def create_access_token(user_id: str, username: str, avatar: str) -> str:
    payload = {
        "sub":      user_id,
        "username": username,
        "avatar":   avatar,
        "iat":      time.time(),
        "exp":      time.time() + settings.JWT_EXPIRE_MINS * 60,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET,
                          algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# REGISTER
# ══════════════════════════════════════════════════════════════════════════════

async def register_user(
    db: AsyncSession,
    email: str,
    username: str,
    password: str,
    avatar: str = "🦊",
) -> dict:
    """
    Create a new user. Returns the user dict + access token.
    Raises ValueError if email or username already taken.
    """
    # Check email
    result = await db.execute(select(User).where(User.email == email.lower()))
    if result.scalar_one_or_none():
        raise ValueError("Email already registered")

    # Check username
    result = await db.execute(select(User).where(User.username == username))
    if result.scalar_one_or_none():
        raise ValueError("Username already taken")

    user = User(
        id              = str(uuid.uuid4()),
        email           = email.lower(),
        username        = username,
        hashed_password = hash_password(password),
        avatar          = avatar,
        created_at      = time.time(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.username, user.avatar)
    log.info(f"New user registered: {username}")
    return _user_response(user, token)


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════

async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    """
    Verify credentials. Returns user dict + access token.
    Raises ValueError on bad credentials.
    """
    result = await db.execute(select(User).where(User.email == email.lower()))
    user   = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise ValueError("Invalid email or password")

    token = create_access_token(user.id, user.username, user.avatar)
    log.info(f"User logged in: {user.username}")
    return _user_response(user, token)


# ══════════════════════════════════════════════════════════════════════════════
# GET CURRENT USER (from JWT token)
# ══════════════════════════════════════════════════════════════════════════════

async def get_current_user(db: AsyncSession, token: str) -> Optional[User]:
    payload = decode_token(token)
    if not payload:
        return None
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    return result.scalar_one_or_none()


# ── helpers ───────────────────────────────────────────────────────────────────

def _user_response(user: User, token: str) -> dict:
    return {
        "user_id":  user.id,
        "username": user.username,
        "email":    user.email,
        "avatar":   user.avatar,
        "token":    token,
    }
