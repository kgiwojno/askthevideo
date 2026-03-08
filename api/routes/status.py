"""GET /api/status, GET /api/history, GET /health endpoints."""

from fastapi import APIRouter, Header

from api.session import get_or_create_session, build_limits
from config.settings import APP_NAME

router = APIRouter()


@router.get("/status")
def get_status(x_session_id: str | None = Header(None, alias="X-Session-ID")):
    if not x_session_id:
        return {"status": "ok", "app": APP_NAME}
    # If session_id provided but doesn't exist, create it
    sid, session = get_or_create_session(x_session_id)
    return {
        "session_id": sid,
        "status": "ok",
        "limits": build_limits(session),
    }


@router.get("/history")
def get_history(x_session_id: str | None = Header(None, alias="X-Session-ID")):
    sid, session = get_or_create_session(x_session_id)
    return {
        "session_id": sid,
        "messages": session["chat_history"],
    }
