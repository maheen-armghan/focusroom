"""
backend/services/timer_service.py
Server-canonical timer — stored in Redis so page refreshes
and reconnects don't cause drift.
"""
from __future__ import annotations
import time
import json
import asyncio
from typing import Callable, Optional

from backend.storage.redis_client import get_redis
from backend.utils.logger import get_logger

log = get_logger(__name__)
TIMER_TTL = 90000

_tick_tasks: dict[str, asyncio.Task] = {}   # room_id → background tick task


async def set_timer(room_id: str, duration_seconds: int) -> dict:
    redis = await get_redis()
    state = {
        "room_id":           room_id,
        "duration_seconds":  duration_seconds,
        "remaining_seconds": duration_seconds,
        "status":            "idle",
        "started_at":        None,
        "paused_at":         None,
    }
    await redis.setex(f"timer:{room_id}", TIMER_TTL, json.dumps(state))
    return state


async def start_timer(room_id: str, tick_callback: Callable) -> dict:
    """Start the timer. tick_callback(room_id, remaining) called every second."""
    state = await _get_state(room_id)
    if not state:
        return {}
    state["status"]     = "running"
    state["started_at"] = time.time()
    await _save_state(room_id, state)
    _start_tick_task(room_id, tick_callback)
    return state


async def pause_timer(room_id: str) -> dict:
    state = await _get_state(room_id)
    if not state or state["status"] != "running":
        return state or {}
    state["status"]    = "paused"
    state["paused_at"] = time.time()
    await _save_state(room_id, state)
    _cancel_tick_task(room_id)
    return state


async def resume_timer(room_id: str, tick_callback: Callable) -> dict:
    state = await _get_state(room_id)
    if not state or state["status"] != "paused":
        return state or {}
    state["status"]    = "running"
    state["paused_at"] = None
    await _save_state(room_id, state)
    _start_tick_task(room_id, tick_callback)
    return state


async def get_timer_state(room_id: str) -> Optional[dict]:
    state = await _get_state(room_id)
    if not state:
        return None
    # If running, compute live remaining time
    if state["status"] == "running" and state["started_at"]:
        elapsed   = time.time() - state["started_at"]
        remaining = max(0, state["duration_seconds"] - int(elapsed))
        state["remaining_seconds"] = remaining
        if remaining == 0:
            state["status"] = "ended"
    return state


# ── internals ─────────────────────────────────────────────────────────────────

async def _get_state(room_id: str) -> Optional[dict]:
    redis = await get_redis()
    raw   = await redis.get(f"timer:{room_id}")
    return json.loads(raw) if raw else None


async def _save_state(room_id: str, state: dict):
    redis = await get_redis()
    await redis.setex(f"timer:{room_id}", TIMER_TTL, json.dumps(state))


def _start_tick_task(room_id: str, tick_callback: Callable):
    _cancel_tick_task(room_id)
    task = asyncio.create_task(_tick_loop(room_id, tick_callback))
    _tick_tasks[room_id] = task


def _cancel_tick_task(room_id: str):
    task = _tick_tasks.pop(room_id, None)
    if task and not task.done():
        task.cancel()


async def _tick_loop(room_id: str, tick_callback: Callable):
    """Decrement timer every second and call tick_callback."""
    try:
        while True:
            await asyncio.sleep(1)
            state = await _get_state(room_id)
            if not state or state["status"] != "running":
                break

            remaining = state["remaining_seconds"] - 1
            state["remaining_seconds"] = remaining

            if remaining <= 0:
                state["remaining_seconds"] = 0
                state["status"] = "ended"
                await _save_state(room_id, state)
                await tick_callback(room_id, 0, ended=True)
                break

            await _save_state(room_id, state)
            await tick_callback(room_id, remaining, ended=False)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.error(f"Timer tick error for {room_id}: {e}")
