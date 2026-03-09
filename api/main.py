"""FastAPI application entry point."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes import admin, ask, auth, status, videos
from src.metrics import log_event

load_dotenv()

app = FastAPI(title="AskTheVideo API")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return detail dict directly so frontend gets {error, code} at top level."""
    content = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail), "code": "ERROR"}
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log_event("ERROR", "500", "—", f"{request.url.path}: {type(exc).__name__}: {str(exc)[:80]}")
    return JSONResponse(
        status_code=500,
        content={"error": "An internal error occurred. Please try again.", "code": "INTERNAL_ERROR"},
    )

app.include_router(videos.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


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
