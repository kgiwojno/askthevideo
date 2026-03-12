"""Error handling utilities with Discord alerting and throttling."""

import os
import time
import threading
import urllib.request
import json
import logging

from src.metrics import record_metric, log_event

logger = logging.getLogger(__name__)

# Throttle: one alert per error type per 10 minutes
_THROTTLE_SECONDS = 600
_last_alert: dict[str, float] = {}
_throttle_lock = threading.Lock()


_ALERT_STYLES = {
    "budget_threshold": {"title": "\U0001f4b0 Budget Threshold", "color": 16776960},
    "slow_query":       {"title": "\U0001f422 Slow Query",       "color": 16744448},
    "anthropic_error":  {"title": "\U0001f6a8 Anthropic API Error", "color": 16711680},
    "youtube_blocked":  {"title": "\U0001f6ab YouTube IP Blocked",  "color": 16744448},
    "proxy_down":       {"title": "\U0001f50c Proxy Down",          "color": 16711680},
    "pinecone_error":   {"title": "\U0001f4be Pinecone Error",      "color": 16711680},
    "uncaught_500":     {"title": "\U0001f4a5 Uncaught Server Error", "color": 16711680},
}
_DEFAULT_STYLE = {"title": "\u26a0\ufe0f Alert", "color": 15105570}


def send_discord_alert(message: str, alert_type: str = "general") -> None:
    """Post a notification to the Discord webhook if configured.

    Throttled: at most one alert per *alert_type* every 10 minutes.
    Sends color-coded embeds for visual clarity.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return

    now = time.time()
    with _throttle_lock:
        last = _last_alert.get(alert_type, 0)
        if now - last < _THROTTLE_SECONDS:
            logger.debug("Discord alert throttled: %s", alert_type)
            return
        _last_alert[alert_type] = now

    record_metric("alert_count")
    log_event("ALERT", "discord", "—", f"[{alert_type}] {message[:80]}")

    style = _ALERT_STYLES.get(alert_type, _DEFAULT_STYLE)
    env = os.getenv("APP_ENV", "local")
    payload = json.dumps({
        "embeds": [{
            "title": style["title"],
            "description": message[:4000],
            "color": style["color"],
            "footer": {"text": f"AskTheVideo \u2022 {env.capitalize()}"},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }]
    }).encode()
    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AskTheVideo/1.0",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        logger.warning("Failed to send Discord alert for %s", alert_type)
