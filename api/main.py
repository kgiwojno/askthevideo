"""FastAPI application entry point."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import admin, ask, auth, status, videos
from api.utils import get_client_ip
from src.metrics import log_event
from src.errors import send_discord_alert

load_dotenv()

app = FastAPI(title="AskTheVideo API")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return detail dict directly so frontend gets {error, code} at top level."""
    content = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail), "code": "ERROR"}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    ip = get_client_ip(request)
    log_event("ERROR", "500", ip, f"{request.url.path}: {type(exc).__name__}: {str(exc)[:80]}")
    send_discord_alert(
        f"Uncaught 500: {request.url.path} — {type(exc).__name__}: {str(exc)[:200]}",
        alert_type="uncaught_500",
    )
    return JSONResponse(
        status_code=500,
        content={"error": "An internal error occurred. Please try again.", "code": "INTERNAL_ERROR"},
    )

app.include_router(videos.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


def _get_git_sha() -> str:
    """Read git commit hash baked into the image at build time."""
    try:
        return Path("/app/.git_sha").read_text().strip()
    except Exception:
        return "unknown"


_GIT_SHA = _get_git_sha()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "commit": _GIT_SHA,
        "deployment_id": os.getenv("KOYEB_INSTANCE_ID", "local"),
    }


# Static files — only mount if frontend/assets exists
_assets_dir = Path("frontend/assets")
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/{path:path}")
async def serve_react(path: str):
    # Serve static files from frontend/ root (favicon, robots.txt, etc.)
    if path:
        static_file = Path("frontend") / path
        if static_file.is_file():
            return FileResponse(str(static_file))
    # Fall back to React SPA
    index = Path("frontend/index.html")
    if index.exists():
        return FileResponse(str(index))
    return {"message": "AskTheVideo API", "docs": "/docs"}
