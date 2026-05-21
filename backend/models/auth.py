"""
backend/api/auth.py
POST /api/auth/register  — create account
POST /api/auth/login     — get JWT token
GET  /api/auth/me        — get current user info from token
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user_auth import get_db
from backend.services.auth_service import register_user, login_user, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request schemas ───────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    EmailStr
    username: str
    password: str
    avatar:   str = "🦊"


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a new account.
    Returns: {user_id, username, email, avatar, token}
    """
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if len(req.username) < 2:
        raise HTTPException(400, "Username must be at least 2 characters")

    try:
        return await register_user(
            db       = db,
            email    = req.email,
            username = req.username,
            password = req.password,
            avatar   = req.avatar,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Login with email + password.
    Returns: {user_id, username, email, avatar, token}
    """
    try:
        return await login_user(db, req.email, req.password)
    except ValueError as e:
        raise HTTPException(401, str(e))


@router.get("/me")
async def me(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user from Authorization: Bearer <token> header.
    Frontend calls this on app load to restore session.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")

    token = authorization.split(" ", 1)[1]
    user  = await get_current_user(db, token)
    if not user:
        raise HTTPException(401, "Token expired or invalid")

    return {
        "user_id":  user.id,
        "username": user.username,
        "email":    user.email,
        "avatar":   user.avatar,
    }
