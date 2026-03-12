"""POST /api/admin/auth and GET /api/admin/metrics endpoints."""

import os
import time

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from api.dependencies import get_pinecone
from src.metrics import get_metrics, get_recent_events, get_user_stats, BUDGET_CYCLE

router = APIRouter()


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


@router.post("/admin/auth")
def admin_auth(request: AdminAuthRequest):
    valid = request.token == os.getenv("ADMIN_TOKEN", "")
    return {"valid": valid}


@router.get("/admin/metrics")
def admin_metrics(x_admin_token: str = Header(None, alias="X-Admin-Token")):
    if x_admin_token != os.getenv("ADMIN_TOKEN", ""):
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
