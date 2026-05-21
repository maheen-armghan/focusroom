"""
backend/models/user_auth.py
SQLAlchemy User model + async SQLite database setup.
No PostgreSQL, no Alembic — tables created automatically on first run.
Database file saved to D:/projects/focusroom/focusroom.db
"""
from __future__ import annotations
import time
from sqlalchemy import Column, String, Boolean, Float
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# ── Database file — SQLite on local disk ──────────────────────────────────────
DATABASE_URL = "sqlite+aiosqlite:///./focusroom.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id               = Column(String, primary_key=True)   # UUID string
    email            = Column(String, unique=True, index=True, nullable=False)
    username         = Column(String, unique=True, index=True, nullable=False)
    hashed_password  = Column(String, nullable=False)
    avatar           = Column(String, default="🦊")
    is_active        = Column(Boolean, default=True)
    created_at       = Column(Float, default=time.time)


async def init_db():
    """Create tables if they don't exist. Called at app startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session
