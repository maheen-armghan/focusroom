"""
FocusRoom — backend/main.py
===========================
Entry point.  Mounts FastAPI + Socket.IO as a single ASGI app.
Serves the frontend static files from ../frontend/

Run:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from backend.api.focus import router as focus_router
app.include_router(focus_router)

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
from backend.api.auth     import router as auth_router          # ← ADDED

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

    # Create auth DB tables on first run
    from backend.models.user_auth import init_db             # ← ADDED
    await init_db()                                          # ← ADDED

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
app.include_router(auth_router)                              # ← ADDED


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}

"""
# ── Serve frontend static files ───────────────────────────────────────────────
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    log.warning(f"Frontend directory not found: {frontend_dir}")
"""
# ── Serve frontend static files ───────────────────────────────────────────────
# Mount on /static instead of / to avoid intercepting API routes
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    # Mount individual asset folders, not root /
    dist_dir = frontend_dir / "dist"
    if dist_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")
    log.info(f"Frontend assets mounted")
else:
    log.warning(f"Frontend directory not found: {frontend_dir}")


# ── Catch-all for React SPA — serves index.html for all non-API routes ────────
from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve React app for all non-API routes."""
    # Don't intercept API or socket routes
    if full_path.startswith("api/") or full_path.startswith("socket.io"):
        from fastapi import HTTPException
        raise HTTPException(404)
    
    index = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Frontend not built yet — run npm run build"}
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