"""FastAPI application entry point."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import ask, auth, status, videos

load_dotenv()

app = FastAPI(title="AskTheVideo API")

app.include_router(videos.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(status.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


# Static files — only mount if frontend/assets exists
_assets_dir = Path("frontend/assets")
if _assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


@app.get("/{path:path}")
async def serve_react(path: str):
    index = Path("frontend/index.html")
    if index.exists():
        return FileResponse(str(index))
    return {"message": "AskTheVideo API", "docs": "/docs"}
