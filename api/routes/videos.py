"""POST/GET/DELETE/PATCH /api/videos endpoints."""

import time

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from api.dependencies import get_pinecone
from api.session import get_or_create_session, build_limits
from api.utils import get_client_ip
from src.metrics import record_metric, log_event
from config.settings import MAX_VIDEOS_FREE, MAX_DURATION_FREE, CHUNK_WINDOW_SECONDS, CHUNK_CARRY_SNIPPETS
from src.chunking import chunk_transcript, format_time
from src.metadata import fetch_video_metadata
from src.transcript import extract_video_id, fetch_transcript
from src.vectorstore import namespace_exists, fetch_metadata, upsert_chunks, upsert_metadata_record

router = APIRouter()


class VideoRequest(BaseModel):
    url: str


class VideoPatchRequest(BaseModel):
    selected: bool


@router.post("/videos")
def post_video(
    body: VideoRequest,
    request: Request,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    sid, session = get_or_create_session(x_session_id)

    # Validate URL
    try:
        video_id = extract_video_id(body.url)
    except ValueError:
        raise HTTPException(400, detail={"error": "Not a valid YouTube URL.", "code": "INVALID_URL"})

    # Check video limit
    if not session["unlimited"] and len(session["loaded_videos"]) >= MAX_VIDEOS_FREE:
        raise HTTPException(403, detail={"error": "Video limit reached.", "code": "VIDEO_LIMIT"})

    # Avoid duplicate in session
    existing_ids = [v["video_id"] for v in session["loaded_videos"]]
    if video_id in existing_ids:
        video_info = next(v for v in session["loaded_videos"] if v["video_id"] == video_id)
        return {"session_id": sid, "video": video_info, "limits": build_limits(session)}

    pc, index = get_pinecone()

    # Cache hit
    if namespace_exists(index, video_id):
        meta = fetch_metadata(index, video_id)
        if meta:
            video_info = {
                "video_id": video_id,
                "title": meta.get("video_title", "Unknown"),
                "channel": meta.get("channel", "Unknown"),
                "duration_display": meta.get("duration_display", ""),
                "thumbnail_url": meta.get("thumbnail_url", ""),
                "chunk_count": int(meta.get("chunk_count", 0)),
                "status": "cached",
                "selected": True,
            }
            session["loaded_videos"].append(video_info)
            session["agent"] = None  # force agent rebuild
            record_metric("total_videos_loaded")
            ip = get_client_ip(request)
            log_event(
                "VIDEO", "cache", ip,
                f'"{video_info["title"]}" video={video_id} duration={meta.get("duration_display", "?")}',
            )
            return {"session_id": sid, "video": video_info, "limits": build_limits(session)}

    # New video — fetch transcript
    t0 = time.monotonic()
    try:
        transcript = fetch_transcript(video_id)
    except ValueError as e:
        msg = str(e)
        log_event("ERROR", "video", get_client_ip(request), f"fetch_transcript: {msg[:80]}")
        if "blocking" in msg.lower():
            raise HTTPException(503, detail={"error": msg, "code": "IP_BLOCKED"})
        elif "disabled" in msg.lower():
            raise HTTPException(400, detail={"error": msg, "code": "NO_TRANSCRIPT"})
        elif "unavailable" in msg.lower():
            raise HTTPException(400, detail={"error": msg, "code": "VIDEO_UNAVAILABLE"})
        else:
            raise HTTPException(400, detail={"error": msg, "code": "TRANSCRIPT_ERROR"})

    # Duration check
    duration_seconds = transcript["duration_seconds"]
    if not session["unlimited"] and duration_seconds > MAX_DURATION_FREE:
        raise HTTPException(
            403,
            detail={"error": "Video exceeds 60-minute limit for free tier.", "code": "DURATION_EXCEEDED"},
        )

    # Fetch oEmbed metadata
    oembed = fetch_video_metadata(video_id)

    # Chunk + embed + upsert
    chunks = chunk_transcript(
        transcript["snippets"],
        video_id,
        window_seconds=CHUNK_WINDOW_SECONDS,
        carry_snippets=CHUNK_CARRY_SNIPPETS,
    )
    upsert_chunks(pc, index, chunks, video_id)
    upsert_metadata_record(index, video_id, {
        "video_title": oembed["video_title"],
        "channel": oembed["channel"],
        "thumbnail_url": oembed["thumbnail_url"],
        "duration_seconds": duration_seconds,
        "duration_display": format_time(duration_seconds),
        "chunk_count": len(chunks),
    })

    video_info = {
        "video_id": video_id,
        "title": oembed["video_title"],
        "channel": oembed["channel"],
        "duration_display": format_time(duration_seconds),
        "thumbnail_url": oembed["thumbnail_url"],
        "chunk_count": len(chunks),
        "status": "ingested",
        "selected": True,
    }
    session["loaded_videos"].append(video_info)
    session["agent"] = None  # force agent rebuild

    record_metric("total_videos_loaded")
    record_metric("total_videos_cached")
    fetch_ms = int((time.monotonic() - t0) * 1000)
    ip = get_client_ip(request)
    log_event(
        "VIDEO", "new", ip,
        f'"{oembed["video_title"]}" video={video_id} chunks={len(chunks)} '
        f"duration={duration_seconds}s fetch={fetch_ms}ms",
    )

    return {"session_id": sid, "video": video_info, "limits": build_limits(session)}


@router.get("/videos")
def get_videos(x_session_id: str | None = Header(None, alias="X-Session-ID")):
    sid, session = get_or_create_session(x_session_id)
    return {
        "session_id": sid,
        "videos": session["loaded_videos"],
        "limits": build_limits(session),
    }


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: str,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    sid, session = get_or_create_session(x_session_id)
    before = len(session["loaded_videos"])
    session["loaded_videos"] = [v for v in session["loaded_videos"] if v["video_id"] != video_id]
    if len(session["loaded_videos"]) == before:
        raise HTTPException(404, detail={"error": "Video not in session.", "code": "NOT_FOUND"})
    session["agent"] = None  # force agent rebuild
    return {"session_id": sid, "removed": video_id, "limits": build_limits(session)}


@router.patch("/videos/{video_id}")
def patch_video(
    video_id: str,
    body: VideoPatchRequest,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    sid, session = get_or_create_session(x_session_id)
    for v in session["loaded_videos"]:
        if v["video_id"] == video_id:
            v["selected"] = body.selected
            session["agent"] = None  # force agent rebuild on selection change
            return {"session_id": sid, "video_id": video_id, "selected": v["selected"]}
    raise HTTPException(404, detail={"error": "Video not in session.", "code": "NOT_FOUND"})
