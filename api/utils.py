"""Shared API utilities."""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Get client IP from reverse proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
