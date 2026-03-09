"""Global metrics store, event logging, and token tracking."""

import os
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from collections import deque

import psutil

# --- Event Log ---
_default_log = "/app/events.log" if os.path.isdir("/app") else "events.log"
EVENT_LOG_PATH = os.getenv("EVENT_LOG_PATH", _default_log)
event_logger = logging.getLogger("events")
event_logger.setLevel(logging.INFO)
event_handler = RotatingFileHandler(
    EVENT_LOG_PATH,
    maxBytes=500_000,       # ~5,000 lines
    backupCount=1           # max 1MB disk
)
event_handler.setFormatter(logging.Formatter("%(message)s"))
event_logger.addHandler(event_handler)


def log_event(event_type: str, subtype: str, ip: str = "—", detail: str = ""):
    """Write structured event to rotating log file.

    Event types: QUERY, VIDEO, SESSION, ERROR, KEY, ALERT
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {event_type:<7} | {subtype:<6} | {ip:<15} | {detail}"
    event_logger.info(line)


def get_recent_events(n: int = 50) -> list[dict]:
    """Read last N events from log file, parsed into dicts."""
    if not os.path.exists(EVENT_LOG_PATH):
        return []
    with open(EVENT_LOG_PATH, "r") as f:
        lines = list(deque(f, maxlen=n))

    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 5:
            events.append({
                "timestamp": parts[0],
                "type": parts[1],
                "subtype": parts[2],
                "ip": parts[3],
                "detail": parts[4],
            })
    return events


# --- App Metrics Store ---
_app_metrics = {
    "lock": threading.Lock(),
    "start_time": time.time(),

    "active_sessions": 0,

    "total_queries": 0,
    "total_videos_loaded": 0,
    "total_videos_cached": 0,
    "key_queries": 0,
    "error_count": 0,
    "alert_count": 0,

    "total_input_tokens": 0,
    "total_output_tokens": 0,
}

# Claude Sonnet 4.6 pricing
COST_INPUT_PER_1K = 0.003     # $3 per 1M tokens
COST_OUTPUT_PER_1K = 0.015    # $15 per 1M tokens
PROJECT_BUDGET = 5.00


def record_metric(key: str, increment: int = 1):
    """Thread-safe metric increment."""
    with _app_metrics["lock"]:
        _app_metrics[key] += increment


def record_tokens(input_tokens: int, output_tokens: int):
    """Record token usage from a Claude API call."""
    with _app_metrics["lock"]:
        _app_metrics["total_input_tokens"] += input_tokens
        _app_metrics["total_output_tokens"] += output_tokens


def get_metrics() -> dict:
    """Return snapshot of all metrics with computed fields."""
    with _app_metrics["lock"]:
        m = {k: v for k, v in _app_metrics.items() if k != "lock"}

    m["uptime_hours"] = round((time.time() - m["start_time"]) / 3600, 1)
    m["ram_mb"] = round(psutil.Process().memory_info().rss / 1024 ** 2, 1)
    m["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    m["estimated_cost"] = round(
        (m["total_input_tokens"] / 1000 * COST_INPUT_PER_1K)
        + (m["total_output_tokens"] / 1000 * COST_OUTPUT_PER_1K),
        4,
    )
    m["budget_remaining"] = round(PROJECT_BUDGET - m["estimated_cost"], 2)
    return m
