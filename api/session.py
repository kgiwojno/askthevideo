"""In-memory session management."""

import uuid
from datetime import datetime, timedelta

from config.settings import SESSION_TTL_HOURS

sessions: dict[str, dict] = {}
SESSION_TTL = timedelta(hours=SESSION_TTL_HOURS)


def get_or_create_session(session_id: str | None) -> tuple[str, dict]:
    """Get existing session or create new one. Cleans expired sessions."""
    now = datetime.utcnow()
    expired = [k for k, v in sessions.items() if now - v["created_at"] > SESSION_TTL]
    for k in expired:
        del sessions[k]

    if session_id and session_id in sessions:
        return session_id, sessions[session_id]

    new_id = str(uuid.uuid4())
    sessions[new_id] = {
        "created_at": now,
        "loaded_videos": [],
        "question_count": 0,
        "chat_history": [],
        "unlimited": False,
        "agent": None,
        "agent_thread_id": new_id,
        "_agent_videos": [],
    }
    return new_id, sessions[new_id]


def build_limits(session: dict) -> dict:
    """Build the limits object for API responses."""
    from config.settings import MAX_VIDEOS_FREE, MAX_QUESTIONS_FREE

    return {
        "videos_loaded": len(session["loaded_videos"]),
        "videos_max": None if session["unlimited"] else MAX_VIDEOS_FREE,
        "questions_used": session["question_count"],
        "questions_max": None if session["unlimited"] else MAX_QUESTIONS_FREE,
        "unlimited": session["unlimited"],
    }
