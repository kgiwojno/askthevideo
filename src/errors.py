"""Error handling utilities."""

import os
import urllib.request
import urllib.error
import json
import traceback


class UserFacingError(Exception):
    """An error with a user-readable message and machine code."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


def send_discord_alert(message: str) -> None:
    """Post a notification to the Discord webhook if configured."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return
    payload = json.dumps({"content": message[:2000]}).encode()
    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def safe_execute(func, *args, **kwargs):
    """Execute func(*args, **kwargs), sending a Discord alert on failure.

    Returns the result on success, or raises the original exception after alerting.
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        alert = f"[AskTheVideo] Error in {func.__name__}:\n```\n{traceback.format_exc()[-1500:]}\n```"
        send_discord_alert(alert)
        raise
