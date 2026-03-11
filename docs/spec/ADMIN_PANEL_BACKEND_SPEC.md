# AskTheVideo -- Admin Panel Backend Specification

## For: Claude Code (build admin API endpoints + metrics infrastructure)

---

## 1. Overview

The admin panel is a React page at `/admin` (built separately). The backend provides two API endpoints and a metrics infrastructure that collects data from across the application.

**ADMIN_TOKEN:** `dupa.8` (set in .env as `ADMIN_TOKEN=dupa.8`)

---

## 2. New files

```
api/
└── routes/
    └── admin.py             # POST /api/admin/auth + GET /api/admin/metrics

src/
└── metrics.py               # Global metrics store, event logging, token tracking
```

---

## 3. API endpoints

### POST /api/admin/auth

Validate admin token.

```python
@router.post("/admin/auth")
def admin_auth(request: AdminAuthRequest):
    valid = request.token == os.getenv("ADMIN_TOKEN", "")
    return {"valid": valid}
```

No HTTP error on invalid token. Just return `{"valid": false}`. This avoids leaking information about whether the endpoint exists.

### GET /api/admin/metrics

Return all metrics. Protected by `X-Admin-Token` header.

```python
@router.get("/admin/metrics")
def admin_metrics(x_admin_token: str = Header(None, alias="X-Admin-Token")):
    if x_admin_token != os.getenv("ADMIN_TOKEN", ""):
        raise HTTPException(403, detail={"error": "Forbidden", "code": "INVALID_TOKEN"})

    m = get_metrics()
    events = get_recent_events(50)
    pc_stats = get_pinecone_stats()

    return {
        "realtime": {
            "active_sessions": m["active_sessions"],
            "ram_mb": m["ram_mb"],
            "ram_max_mb": 512,
            "cpu_percent": m["cpu_percent"],
            "uptime_hours": m["uptime_hours"],
        },
        "sessions": {
            "total_queries": m["total_queries"],
            "total_videos_loaded": m["total_videos_loaded"],
            "key_queries": m["key_queries"],
            "error_count": m["error_count"],
            "alert_count": m["alert_count"],
        },
        "cost": {
            "total_input_tokens": m["total_input_tokens"],
            "total_output_tokens": m["total_output_tokens"],
            "estimated_cost": m["estimated_cost"],
            "budget_total": PROJECT_BUDGET,
            "budget_remaining": m["budget_remaining"],
        },
        "pinecone": pc_stats,
        "events": events,
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
```

### Register the router

In `api/main.py`, add:
```python
from api.routes import admin
app.include_router(admin.router, prefix="/api")
```

---

## 4. src/metrics.py

Thread-safe global metrics store. All counters reset on container restart (deliberate).

```python
import threading
import time
import logging
import os
from logging.handlers import RotatingFileHandler
from collections import deque
import psutil

# --- Event Log ---
EVENT_LOG_PATH = os.getenv("EVENT_LOG_PATH", "/app/events.log")
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
```

---

## 5. Pinecone stats helper

Add to `api/routes/admin.py` or `src/metrics.py`:

```python
def get_pinecone_stats() -> dict:
    """Fetch Pinecone index stats for admin dashboard."""
    try:
        pc, index = get_pinecone()
        stats = index.describe_index_stats()
        ns_count = len(stats.get("namespaces", {}))
        total_vectors = stats.get("total_vector_count", 0)
        fullness = round((total_vectors / 100_000) * 100, 1)  # 100K vector limit on free tier
        return {
            "cached_videos": ns_count,
            "total_vectors": total_vectors,
            "index_fullness_percent": fullness,
        }
    except Exception:
        return {
            "cached_videos": 0,
            "total_vectors": 0,
            "index_fullness_percent": 0,
        }
```

---

## 6. Client IP extraction

For FastAPI (replaces the Streamlit-specific `st.context.headers`):

```python
from fastapi import Request

def get_client_ip(request: Request) -> str:
    """Get client IP from reverse proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```

Pass the `Request` object to functions that need the IP. In route handlers:

```python
@router.post("/ask")
async def ask_question(body: AskRequest, request: Request, ...):
    ip = get_client_ip(request)
    # ... use ip in log_event calls
```

---

## 7. Token tracking with LangChain callback

Capture token usage from every Claude call:

```python
from langchain_core.callbacks import BaseCallbackHandler

class TokenTracker(BaseCallbackHandler):
    """Records token usage to global metrics store."""

    def on_llm_end(self, response, **kwargs):
        usage = response.llm_output.get("usage", {}) if response.llm_output else {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        if input_tokens or output_tokens:
            record_tokens(input_tokens, output_tokens)
```

Attach when creating the LLM:

```python
from src.metrics import TokenTracker

token_tracker = TokenTracker()
llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=0.0,
    callbacks=[token_tracker],
)
```

---

## 8. Where to call record_metric() and log_event()

Integrate these calls into the existing route handlers:

### In routes/ask.py (after successful query)

```python
record_metric("total_queries")
ip = get_client_ip(request)

if session["unlimited"]:
    record_metric("key_queries")
    log_event("KEY", "query", ip, f'"{question[:50]}" | count={session["question_count"]}')
else:
    log_event("QUERY", "free", ip, f'"{question[:50]}"')
```

### In routes/videos.py (after loading a video)

```python
record_metric("total_videos_loaded")
ip = get_client_ip(request)

if status == "cached":
    log_event("VIDEO", "cache", ip, f'"{title}" | video={video_id}')
else:
    record_metric("total_videos_cached")
    log_event("VIDEO", "new", ip, f'"{title}" | video={video_id} | chunks={chunk_count}')
```

### In session.py (session creation/expiry)

```python
# On new session
record_metric("active_sessions")
log_event("SESSION", "start", ip, f"active={_app_metrics['active_sessions']}")

# On session expiry (in cleanup)
with _app_metrics["lock"]:
    _app_metrics["active_sessions"] = max(0, _app_metrics["active_sessions"] - 1)
log_event("SESSION", "end", "—", f"active={_app_metrics['active_sessions']}")
```

### In errors.py (on errors and Discord alerts)

```python
# In error handler
record_metric("error_count")
log_event("ERROR", severity, ip, f"{context}: {type(e).__name__}: {str(e)[:80]}")

# In send_discord_alert
record_metric("alert_count")
log_event("ALERT", "discord", "—", f"{alert_type}: {details}")
```

---

## 9. Environment variable

Add to `.env`:
```
ADMIN_TOKEN=dupa.8
```

Add to `.env.example`:
```
ADMIN_TOKEN=your_admin_token_here
```

---

## 10. Requirements

Add `psutil` to requirements.txt (if not already there). Needed for RAM and CPU metrics.

---

## 11. Data persistence

| Data | Persistence | Notes |
|---|---|---|
| Metric counters | Lost on container restart | In-memory dict, acceptable for bootcamp |
| Event log (events.log) | Lost on container restart | Rotating file on ephemeral Koyeb filesystem, max 1MB |
| Pinecone stats | Persistent | Fetched live from Pinecone API |
| Budget remaining | Resets on restart | Based on accumulated token count |

---

## 12. Testing

### tests/test_admin.py

```python
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_admin_auth_valid():
    res = client.post("/api/admin/auth", json={"token": "dupa.8"})
    assert res.status_code == 200
    assert res.json()["valid"] is True

def test_admin_auth_invalid():
    res = client.post("/api/admin/auth", json={"token": "wrong"})
    assert res.status_code == 200
    assert res.json()["valid"] is False

def test_admin_metrics_no_token():
    res = client.get("/api/admin/metrics")
    assert res.status_code == 403

def test_admin_metrics_valid():
    res = client.get("/api/admin/metrics", headers={"X-Admin-Token": "dupa.8"})
    assert res.status_code == 200
    data = res.json()
    assert "realtime" in data
    assert "sessions" in data
    assert "cost" in data
    assert "pinecone" in data
    assert "events" in data
```

### tests/test_metrics.py

```python
from src.metrics import record_metric, record_tokens, get_metrics, log_event

def test_record_metric():
    record_metric("total_queries")
    m = get_metrics()
    assert m["total_queries"] >= 1

def test_record_tokens():
    record_tokens(100, 50)
    m = get_metrics()
    assert m["total_input_tokens"] >= 100
    assert m["total_output_tokens"] >= 50
    assert m["estimated_cost"] > 0

def test_log_event(tmp_path):
    # Override EVENT_LOG_PATH for testing
    import src.metrics as metrics
    metrics.EVENT_LOG_PATH = str(tmp_path / "test_events.log")
    log_event("QUERY", "free", "127.0.0.1", "test query")
    events = metrics.get_recent_events(10)
    assert len(events) >= 1
    assert events[-1]["type"] == "QUERY"
```
