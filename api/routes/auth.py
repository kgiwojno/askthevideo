"""POST /api/auth endpoint."""

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel

from api.session import get_or_create_session, build_limits
from api.utils import get_client_ip
from src.auth import validate_access_key
from src.metrics import log_event

router = APIRouter()


class AuthRequest(BaseModel):
    key: str


@router.post("/auth")
def post_auth(
    body: AuthRequest,
    request: Request,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    sid, session = get_or_create_session(x_session_id)
    valid = validate_access_key(body.key)
    ip = get_client_ip(request)
    if valid:
        session["unlimited"] = True
        log_event("AUTH", "success", ip, "tier=key")
    else:
        log_event("AUTH", "fail", ip, "invalid_key")
    response: dict = {"session_id": sid, "valid": valid}
    if valid:
        response["limits"] = build_limits(session)
    return response
