"""
backend/services/summary_service.py
Generate post-session chat summary using Google Gemini API.
"""
from __future__ import annotations
import time
from backend.services.chat_service import get_all_messages, get_chat_stats
from backend.config import get_settings
from backend.utils.logger import get_logger

log      = get_logger(__name__)
settings = get_settings()

MAX_CHAT_CHARS = 50_000

SYSTEM_PROMPT = """You are a study session assistant. Given a chat log from a group study session, produce a concise structured summary.

Return ONLY this format, nothing else:

📋 Session Chat Summary
───────────────────────
🗂 Key Topics Discussed
  • [topic 1]
  • [topic 2]

📌 Action Items
  • [person]: [task]

🔗 Links Shared
  • [url] (shared by [name])

💬 Message Stats
  • [N] total messages | Most active: [name] ([n] messages)

Rules:
- Paraphrase — never quote messages verbatim
- If no action items found, write "None identified"
- If no links found, write "None shared"
- Keep the whole summary under 300 words
- If fewer than 5 messages, respond only with: "Not enough chat activity to summarise."
"""


async def generate_summary(room_id: str, room_name: str = "Study Room",
                            duration_str: str = "") -> str:
    messages = await get_all_messages(room_id)
    human    = [m for m in messages if not m.get("is_system")]

    if len(human) < 5:
        return "Not enough chat activity to summarise."

    # Build chat log string
    lines = []
    for m in human:
        lines.append(f"{m['username']}: {m['text']}")

    chat_log = "\n".join(lines)
    if len(chat_log) > MAX_CHAT_CHARS:
        chat_log = chat_log[-MAX_CHAT_CHARS:]   # keep most recent

    stats = await get_chat_stats(room_id)

    user_prompt = (
        f"Session: {room_name}  |  Duration: {duration_str}\n"
        f"Participants: {', '.join(set(m['username'] for m in human))}\n\n"
        f"Chat log:\n{chat_log}"
    )

    # ── Try Gemini ────────────────────────────────────────────────────────────
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model    = genai.GenerativeModel(settings.GEMINI_MODEL)
            response = model.generate_content(
                SYSTEM_PROMPT + "\n\n" + user_prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.3,
                ),
            )
            return response.text.strip()
        except Exception as e:
            log.error(f"Gemini API error: {e}")

    # ── Fallback summary (no API key or API failure) ───────────────────────────
    participants = list(set(m["username"] for m in human))
    return (
        f"📋 Session Chat Summary\n"
        f"───────────────────────\n"
        f"Participants: {', '.join(participants)}\n\n"
        f"💬 Message Stats\n"
        f"  • {stats['count']} total messages"
        + (f" | Most active: {stats['most_active']}" if stats["most_active"] else "")
        + "\n\n(AI summary unavailable — add GEMINI_API_KEY to .env for full summaries)"
    )
