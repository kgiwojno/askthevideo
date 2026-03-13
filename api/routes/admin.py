"""POST /api/admin/auth and GET /api/admin/metrics endpoints."""

import os
import time
import threading
from collections import defaultdict

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from api.dependencies import get_pinecone
from api.utils import get_client_ip
from src.errors import send_discord_alert
from src.metrics import get_metrics, get_recent_events, get_user_stats, log_event, BUDGET_CYCLE

router = APIRouter()

# Track failed admin login attempts per IP within a 30-minute window
_admin_fail_lock = threading.Lock()
_admin_fails: dict[str, list[float]] = defaultdict(list)
_ADMIN_FAIL_WINDOW = 1800  # 30 minutes


class AdminAuthRequest(BaseModel):
    token: str


def get_pinecone_stats() -> dict:
    """Fetch Pinecone index stats for admin dashboard."""
    try:
        pc, index = get_pinecone()
        stats = index.describe_index_stats()
        ns_count = len(stats.get("namespaces", {}))
        total_vectors = stats.get("total_vector_count", 0)
        fullness = round((total_vectors / 100_000) * 100, 1)
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


def _record_admin_fail(ip: str):
    """Track failed admin login and alert at 3/6/9/... attempts within the window."""
    now = time.time()
    with _admin_fail_lock:
        # Prune old attempts outside window
        _admin_fails[ip] = [t for t in _admin_fails[ip] if now - t < _ADMIN_FAIL_WINDOW]
        _admin_fails[ip].append(now)
        count = len(_admin_fails[ip])

    if count >= 3 and count % 3 == 0:
        if count <= 3:
            severity = "warning"
            label = "Minor"
        elif count <= 6:
            severity = "elevated"
            label = "Elevated"
        else:
            severity = "critical"
            label = "Critical"
        send_discord_alert(
            f"{label}: {count} failed admin login attempts from IP {ip} "
            f"in the last {_ADMIN_FAIL_WINDOW // 60} minutes.",
            alert_type=f"admin_brute_{severity}",
        )


@router.post("/admin/auth")
def admin_auth(body: AdminAuthRequest, request: Request):
    valid = body.token == os.getenv("ADMIN_TOKEN", "")
    ip = get_client_ip(request)
    if valid:
        log_event("ADMIN", "success", ip, "admin_login")
        # Clear failed attempts on successful login
        with _admin_fail_lock:
            _admin_fails.pop(ip, None)
    else:
        log_event("ADMIN", "fail", ip, "invalid_token")
        _record_admin_fail(ip)
    return {"valid": valid}


@router.get("/admin/metrics")
def admin_metrics(request: Request, x_admin_token: str = Header(None, alias="X-Admin-Token")):
    if x_admin_token != os.getenv("ADMIN_TOKEN", ""):
        ip = get_client_ip(request)
        log_event("ADMIN", "fail", ip, "invalid_token_metrics")
        _record_admin_fail(ip)
        raise HTTPException(403, detail={"error": "Forbidden", "code": "INVALID_TOKEN"})

    m = get_metrics()
    events = get_recent_events(50)
    pc_stats = get_pinecone_stats()
    user_stats = get_user_stats()

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
            "total_input_tokens": m["cumulative_input_tokens"],
            "total_output_tokens": m["cumulative_output_tokens"],
            "estimated_cost": m["estimated_cost"],
            "cost_offset": m["cost_offset"],
            "budget_cycle": BUDGET_CYCLE,
            "budget_cycle_spent": m["budget_cycle_spent"],
            "budget_cycle_remaining": m["budget_cycle_remaining"],
            "budget_total_loaded": m["budget_total_loaded"],
            # Frontend-expected fields
            "cycle_budget": BUDGET_CYCLE,
            "cycle_used": m["budget_cycle_spent"],
            "total_spend": m["estimated_cost"],
            "total_loaded": m["budget_total_loaded"],
        },
        "pinecone": pc_stats,
        "users": user_stats,
        "events": events,
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
