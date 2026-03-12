"""Global metrics store, event logging, and token tracking."""

import os
import json
import threading
import time
import logging
import urllib.request
from logging.handlers import RotatingFileHandler
from collections import deque

import psutil

# --- Supabase Config (lazy — read after dotenv loads) ---
_supabase_logger = logging.getLogger("supabase")


def _get_app_env() -> str:
    """Return current environment name (e.g. 'production', 'local')."""
    return os.getenv("APP_ENV", "local")


def _get_supabase_config() -> tuple[str, str]:
    """Return (url, key) from env. Read lazily so dotenv has time to load.
    Returns empty strings during tests (TESTING=1) to prevent writes.
    """
    if os.getenv("TESTING"):
        return "", ""
    return os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")


def _supabase_request(method: str, path: str, data: dict | None = None) -> dict | list | None:
    """Make a request to Supabase REST API. Returns parsed JSON or None on failure."""
    url_base, key = _get_supabase_config()
    if not url_base or not key:
        return None
    url = f"{url_base}{path}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if method == "GET":
        headers["Accept"] = "application/json"
    body = json.dumps(data).encode() if data else None
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except Exception as e:
        _supabase_logger.debug("Supabase %s %s failed: %s", method, path, e)
        return None


def _post_to_supabase(table: str, data: dict):
    """Insert a row into a Supabase table (fire-and-forget in background thread)."""
    threading.Thread(
        target=_supabase_request,
        args=("POST", f"/rest/v1/{table}", data),
        daemon=True,
    ).start()


# --- Event Log (local file) ---
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
    """Write structured event to rotating log file and Supabase.

    Event types: QUERY, VIDEO, SESSION, ERROR, KEY, ALERT, TOOL
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {event_type:<7} | {subtype:<6} | {ip:<15} | {detail}"
    event_logger.info(line)

    _post_to_supabase("events", {
        "event_type": event_type,
        "subtype": subtype,
        "ip": ip,
        "detail": detail,
        "environment": _get_app_env(),
    })


import re

_KV_PATTERN = re.compile(r'(\w+)=(\d+(?:\.\d+)?(?:ms|s)?)')


def _parse_detail(detail: str) -> dict:
    """Extract key=value pairs from a detail string into typed fields.

    Examples:
        'tool=vector_search latency=14320ms tokens=8700/450'
        → {"tool": "vector_search", "latency_ms": 14320, "tokens_in": 8700, "tokens_out": 450}
    """
    parsed = {}
    # Extract tool name
    m = re.search(r'tool=(\w+)', detail)
    if m:
        parsed["tool"] = m.group(1)
    # Extract latency
    m = re.search(r'latency=(\d+)ms', detail)
    if m:
        parsed["latency_ms"] = int(m.group(1))
    # Extract per-query tokens (tokens=in/out)
    m = re.search(r'tokens=(\d+)/(\d+)', detail)
    if m:
        parsed["tokens_in"] = int(m.group(1))
        parsed["tokens_out"] = int(m.group(2))
    # Extract video duration in seconds
    m = re.search(r'duration=(\d+)s', detail)
    if m:
        parsed["duration_s"] = int(m.group(1))
    # Extract fetch time
    m = re.search(r'fetch=(\d+)ms', detail)
    if m:
        parsed["fetch_ms"] = int(m.group(1))
    # Extract chunk count
    m = re.search(r'chunks=(\d+)', detail)
    if m:
        parsed["chunks"] = int(m.group(1))
    # Extract session depth (questions/videos)
    m = re.search(r'questions=(\d+)', detail)
    if m:
        parsed["questions"] = int(m.group(1))
    m = re.search(r'videos=(\d+)', detail)
    if m:
        parsed["videos"] = int(m.group(1))
    # Extract tier
    m = re.search(r'tier=(\w+)', detail)
    if m:
        parsed["tier"] = m.group(1)
    # Extract video_id
    m = re.search(r'video=([A-Za-z0-9_-]+)', detail)
    if m:
        parsed["video_id"] = m.group(1)
    return parsed


def get_recent_events(n: int = 50) -> list[dict]:
    """Read recent events. Tries Supabase first (last 7 days), falls back to local file."""
    env = _get_app_env()
    result = _supabase_request(
        "GET",
        f"/rest/v1/events?environment=eq.{env}&order=created_at.desc&limit={n}"
        f"&created_at=gte.{time.strftime('%Y-%m-%dT00:00:00', time.gmtime(time.time() - 7 * 86400))}",
    )
    if result is not None:
        events = []
        for e in result:
            detail = e.get("detail", "")
            ev = {
                "timestamp": e.get("created_at", ""),
                "type": e.get("event_type", ""),
                "subtype": e.get("subtype", ""),
                "ip": e.get("ip", ""),
                "detail": detail,
            }
            ev.update(_parse_detail(detail))
            events.append(ev)
        return events

    # Fallback: local file
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
            detail = parts[4]
            ev = {
                "timestamp": parts[0],
                "type": parts[1],
                "subtype": parts[2],
                "ip": parts[3],
                "detail": detail,
            }
            ev.update(_parse_detail(detail))
            events.append(ev)
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
BUDGET_CYCLE = 5.00           # Each reload adds $5


def _get_initial_cost_offset() -> float:
    """Pre-Supabase spend that isn't tracked in metrics. Set once via env var."""
    return float(os.getenv("INITIAL_COST_OFFSET", "0"))


def _get_initial_token_offsets() -> tuple[int, int]:
    """Pre-Supabase token usage. Set once via env vars."""
    return (
        int(os.getenv("INITIAL_INPUT_TOKENS", "0")),
        int(os.getenv("INITIAL_OUTPUT_TOKENS", "0")),
    )


def record_metric(key: str, increment: int = 1):
    """Thread-safe metric increment."""
    with _app_metrics["lock"]:
        _app_metrics[key] += increment


BUDGET_ALERT_THRESHOLD = 0.80  # Alert at 80% of each $5 cycle


def record_tokens(input_tokens: int, output_tokens: int):
    """Record token usage from a Claude API call. Alerts at 80% of current budget cycle."""
    with _app_metrics["lock"]:
        _app_metrics["total_input_tokens"] += input_tokens
        _app_metrics["total_output_tokens"] += output_tokens
        total_in = _app_metrics["total_input_tokens"]
        total_out = _app_metrics["total_output_tokens"]

    tracked_cost = (total_in / 1000 * COST_INPUT_PER_1K) + (total_out / 1000 * COST_OUTPUT_PER_1K)
    cumulative_cost = tracked_cost + _get_initial_cost_offset()

    # Cycle-based alert: which $5 block are we in, and are we at 80%?
    cycle_start = int(cumulative_cost / BUDGET_CYCLE) * BUDGET_CYCLE
    cycle_threshold = cycle_start + BUDGET_CYCLE * BUDGET_ALERT_THRESHOLD
    if cumulative_cost >= cycle_threshold:
        from src.errors import send_discord_alert
        cycle_num = int(cumulative_cost / BUDGET_CYCLE) + 1
        send_discord_alert(
            f"Budget alert: ${cumulative_cost:.2f} cumulative "
            f"(cycle {cycle_num}: ${cumulative_cost - cycle_start:.2f}/${BUDGET_CYCLE:.2f}). "
            f"Tokens: {total_in:,} in / {total_out:,} out.",
            alert_type="budget_threshold",
        )

    # Persist token snapshot to Supabase
    _post_to_supabase("metrics_snapshots", {
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "estimated_cost": round(cumulative_cost, 4),
        "total_queries": _app_metrics["total_queries"],
        "total_videos_loaded": _app_metrics["total_videos_loaded"],
        "active_sessions": _app_metrics["active_sessions"],
        "ram_mb": round(psutil.Process().memory_info().rss / 1024 ** 2, 1),
        "environment": _get_app_env(),
    })


def _restore_from_supabase():
    """Seed in-memory metrics from Supabase on startup. Called once at import time."""
    # Restore counters from event counts
    result = _supabase_request(
        "GET",
        "/rest/v1/rpc/get_event_counts",
    )
    # Fallback: count events directly if RPC not available
    env = _get_app_env()
    if result is None:
        for event_type, metric_key in [
            ("QUERY", "total_queries"),
            ("VIDEO", "total_videos_loaded"),
            ("ERROR", "error_count"),
            ("ALERT", "alert_count"),
            ("KEY", "key_queries"),
        ]:
            count_result = _supabase_request(
                "GET",
                f"/rest/v1/events?event_type=eq.{event_type}&environment=eq.{env}&select=id",
            )
            if count_result is not None:
                with _app_metrics["lock"]:
                    _app_metrics[metric_key] = len(count_result)
    else:
        if isinstance(result, list) and result:
            result = result[0]
        if isinstance(result, dict):
            with _app_metrics["lock"]:
                _app_metrics["total_queries"] = result.get("total_queries", 0)
                _app_metrics["total_videos_loaded"] = result.get("total_videos_loaded", 0)
                _app_metrics["error_count"] = result.get("error_count", 0)
                _app_metrics["alert_count"] = result.get("alert_count", 0)
                _app_metrics["key_queries"] = result.get("key_queries", 0)

    # Restore token totals from latest metrics snapshot
    snapshot = _supabase_request(
        "GET",
        f"/rest/v1/metrics_snapshots?environment=eq.{env}&order=created_at.desc&limit=1",
    )
    if snapshot and isinstance(snapshot, list) and snapshot:
        s = snapshot[0]
        with _app_metrics["lock"]:
            _app_metrics["total_input_tokens"] = s.get("total_input_tokens", 0)
            _app_metrics["total_output_tokens"] = s.get("total_output_tokens", 0)

    _supabase_logger.info(
        "Restored metrics from Supabase: queries=%d, videos=%d, tokens=%d/%d",
        _app_metrics["total_queries"],
        _app_metrics["total_videos_loaded"],
        _app_metrics["total_input_tokens"],
        _app_metrics["total_output_tokens"],
    )


# Restore historical data on startup
_restore_from_supabase()


def get_metrics() -> dict:
    """Return snapshot of all metrics with computed fields."""
    with _app_metrics["lock"]:
        m = {k: v for k, v in _app_metrics.items() if k != "lock"}

    m["uptime_hours"] = round((time.time() - m["start_time"]) / 3600, 1)
    m["ram_mb"] = round(psutil.Process().memory_info().rss / 1024 ** 2, 1)
    m["cpu_percent"] = psutil.cpu_percent(interval=0.1)

    # Cumulative tokens (tracked + pre-Supabase offset)
    offset_in, offset_out = _get_initial_token_offsets()
    m["cumulative_input_tokens"] = m["total_input_tokens"] + offset_in
    m["cumulative_output_tokens"] = m["total_output_tokens"] + offset_out

    tracked_cost = (
        (m["total_input_tokens"] / 1000 * COST_INPUT_PER_1K)
        + (m["total_output_tokens"] / 1000 * COST_OUTPUT_PER_1K)
    )
    cumulative_cost = tracked_cost + _get_initial_cost_offset()
    cycle_start = int(cumulative_cost / BUDGET_CYCLE) * BUDGET_CYCLE

    m["estimated_cost"] = round(cumulative_cost, 4)
    m["cost_offset"] = _get_initial_cost_offset()
    m["budget_cycle"] = BUDGET_CYCLE
    m["budget_cycle_spent"] = round(cumulative_cost - cycle_start, 4)
    m["budget_cycle_remaining"] = round(BUDGET_CYCLE - (cumulative_cost - cycle_start), 2)
    m["budget_total_loaded"] = round(cycle_start + BUDGET_CYCLE, 2)
    return m
