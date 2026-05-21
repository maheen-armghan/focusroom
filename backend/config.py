"""
FocusRoom — backend/config.py
All settings loaded from .env via pydantic-settings.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME:        str  = "FocusRoom"
    APP_VERSION:     str  = "1.1.0"
    DEBUG:           bool = False
    HOST:            str  = "0.0.0.0"
    PORT:            int  = 8000

    # ── Security ──────────────────────────────────────────────────────────────
    JWT_SECRET:      str  = "change-me-in-production"
    JWT_ALGORITHM:   str  = "HS256"
    JWT_EXPIRE_MINS: int  = 1440          # 24 hours

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL:       str  = "redis://localhost:6379/0"

    # ── Database (PostgreSQL) ─────────────────────────────────────────────────
    DATABASE_URL:    str  = "postgresql://user:password@localhost:5432/focusroom"
    GEMINI_API_KEY:  str  = ""
    GEMINI_MODEL:    str  = "gemini-1.5-flash"

    # ── Storage (S3 / Cloudflare R2) ──────────────────────────────────────────
    S3_BUCKET:       str  = "focusroom-files"
    S3_REGION:       str  = "auto"
    S3_ENDPOINT_URL: str  = ""            # empty = AWS; set for R2/localstack
    AWS_ACCESS_KEY:  str  = ""
    AWS_SECRET_KEY:  str  = ""
    USE_LOCAL_STORAGE: bool = True        # True = save files to disk (dev mode)
    LOCAL_STORAGE_DIR: str = "local_uploads"

    # ── ML model ──────────────────────────────────────────────────────────────
    MODEL_PATH:      str  = "ml/model_weights/best_model.keras"
    MODEL_IMG_SIZE:  int  = 32            # must match training --img_size

    # ── Session limits ────────────────────────────────────────────────────────
    MAX_USERS_PER_ROOM:  int = 10
    ROOM_TTL_HOURS:      int = 24
    FILE_TTL_HOURS:      int = 25         # 1h after session max length
    MAX_FILE_SIZE_MB:    int = 25
    MAX_ROOM_STORAGE_MB: int = 200
    INVITE_CODE_TTL_SEC: int = 86400      # 24 h


@lru_cache
def get_settings() -> Settings:
    return Settings()
