"""POST /api/auth endpoint."""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.session import get_or_create_session, build_limits
from src.auth import validate_access_key

router = APIRouter()


class AuthRequest(BaseModel):
    key: str


@router.post("/auth")
def post_auth(
    body: AuthRequest,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    sid, session = get_or_create_session(x_session_id)
    valid = validate_access_key(body.key)
    if valid:
        session["unlimited"] = True
    response: dict = {"session_id": sid, "valid": valid}
    if valid:
        response["limits"] = build_limits(session)
    return response
