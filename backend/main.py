"""
FocusRoom — backend/main.py
===========================
Entry point.  Mounts FastAPI + Socket.IO as a single ASGI app.
Serves the frontend static files from ../frontend/

Run:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path

import socketio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.utils.logger import get_logger
from backend.storage.redis_client import close_redis

# ── API routers ───────────────────────────────────────────────────────────────
from backend.api.rooms    import router as rooms_router
from backend.api.invite   import router as invite_router
from backend.api.sessions import router as sessions_router
from backend.api.files    import router as files_router

# ── Socket.IO event handlers ──────────────────────────────────────────────────
from backend.sockets import connection, focus, chat, timer, session, files as sio_files

log      = get_logger("main")
settings = get_settings()


# ══════════════════════════════════════════════════════════════════════════════
# SOCKET.IO SERVER
# ══════════════════════════════════════════════════════════════════════════════

sio = socketio.AsyncServer(
    async_mode      = "asgi",
    cors_allowed_origins = "*",        # tighten in production
    logger          = False,
    engineio_logger = False,
)

# Register all socket event handlers
connection.register(sio)
focus.register(sio)
chat.register(sio)
timer.register(sio)
session.register(sio)
sio_files.register(sio)


# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI APP
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    log.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Load ML model once at startup
    from backend.ml.cnn_model import load_model
    load_model(settings.MODEL_PATH)

    # Ensure local upload directory exists
    Path(settings.LOCAL_STORAGE_DIR).mkdir(parents=True, exist_ok=True)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log.info("Shutting down…")
    await close_redis()


app = FastAPI(
    title       = settings.APP_NAME,
    version     = settings.APP_VERSION,
    description = "AI-Powered Collaborative Study Platform",
    lifespan    = lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# REST routers
app.include_router(rooms_router)
app.include_router(invite_router)
app.include_router(sessions_router)
app.include_router(files_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


# ── Serve frontend static files ───────────────────────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    log.warning(f"Frontend directory not found: {frontend_dir}")


# ══════════════════════════════════════════════════════════════════════════════
# MOUNT SOCKET.IO ONTO FASTAPI
# ══════════════════════════════════════════════════════════════════════════════

app = socketio.ASGIApp(sio, other_asgi_app=app)


# ══════════════════════════════════════════════════════════════════════════════
# DEV SERVER  (python -m backend.main)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host    = settings.HOST,
        port    = settings.PORT,
        reload  = settings.DEBUG,
    )
