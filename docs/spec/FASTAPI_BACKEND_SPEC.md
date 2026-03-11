# AskTheVideo -- FastAPI Backend Specification

## Architecture

Single container serving both the React frontend and the Python API:

```
app.askthevideo.com
    |
    |-- /              -> React static files (index.html, JS, CSS)
    |-- /api/videos    -> FastAPI endpoints
    |-- /api/ask       -> FastAPI endpoints (non-streaming)
    |-- /api/ask/stream -> FastAPI SSE endpoint (streaming)
    |-- /api/status    -> FastAPI endpoints
    +-- /health        -> Health check
```

One Koyeb service, one domain, one container. FastAPI serves React's build output as static files and handles API requests.

---

## Session management

### Approach: in-memory sessions with UUID

```python
import uuid
from datetime import datetime, timedelta

sessions: dict[str, dict] = {}
SESSION_TTL = timedelta(hours=2)

def get_or_create_session(session_id: str | None) -> tuple[str, dict]:
    """Get existing session or create new one. Cleans expired sessions."""
    now = datetime.utcnow()
    expired = [k for k, v in sessions.items() if now - v["created_at"] > SESSION_TTL]
    for k in expired:
        del sessions[k]

    if session_id and session_id in sessions:
        return session_id, sessions[session_id]

    new_id = str(uuid.uuid4())
    sessions[new_id] = {
        "created_at": now,
        "loaded_videos": [],
        "question_count": 0,
        "chat_history": [],
        "unlimited": False,
        "agent": None,
        "agent_thread_id": new_id,
        "_agent_videos": [],
    }
    return new_id, sessions[new_id]
```

### Session ID transport

React sends `X-Session-ID` header on every request. First request has no header; API creates session and returns `session_id` in response. No cookies.

---

## API endpoints

### POST /api/videos

Load a video. Ingests transcript, chunks, embeds, upserts to Pinecone.

**Request:**
```json
{
    "url": "https://youtube.com/watch?v=dQw4w9WgXcQ"
}
```

**Response (success):**
```json
{
    "session_id": "uuid",
    "video": {
        "video_id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "channel": "Rick Astley",
        "duration_display": "3:31",
        "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        "chunk_count": 2,
        "status": "ingested"
    },
    "limits": {
        "videos_loaded": 1,
        "videos_max": 5,
        "questions_used": 0,
        "questions_max": 10,
        "unlimited": false
    }
}
```

**Note:** `thumbnail_url` comes from the YouTube oEmbed API (fetched during ingestion). Also stored in the Pinecone metadata record for cached videos.

**Error codes:**

| Code | HTTP | Meaning |
|---|---|---|
| `INVALID_URL` | 400 | Not a valid YouTube URL |
| `NO_TRANSCRIPT` | 400 | Video has no captions |
| `VIDEO_UNAVAILABLE` | 400 | Video removed or private |
| `DURATION_EXCEEDED` | 403 | Video longer than 60 min (free tier) |
| `VIDEO_LIMIT` | 403 | 5 videos already loaded |
| `INTERNAL_ERROR` | 500 | Unexpected failure |

**Backend flow:**
1. Validate URL (extract_video_id)
2. Check video limit
3. Check if namespace exists in Pinecone (cache hit)
4. If cached: fetch metadata (includes thumbnail_url), return immediately
5. If new: fetch transcript, check duration, fetch oEmbed metadata (title, channel, thumbnail_url), chunk, embed, upsert
6. Add to session, recreate agent with updated video list
7. Return video info + limits

### GET /api/videos

List loaded videos for the current session.

**Response:**
```json
{
    "session_id": "uuid",
    "videos": [
        {
            "video_id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel": "Rick Astley",
            "duration_display": "3:31",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
            "selected": true
        }
    ],
    "limits": { ... }
}
```

### DELETE /api/videos/{video_id}

Remove a video from session (does not delete from Pinecone).

**Response:**
```json
{
    "session_id": "uuid",
    "removed": "dQw4w9WgXcQ",
    "limits": { ... }
}
```

### PATCH /api/videos/{video_id}

Toggle video selection.

**Request:**
```json
{
    "selected": true
}
```

**Response:**
```json
{
    "session_id": "uuid",
    "video_id": "dQw4w9WgXcQ",
    "selected": true
}
```

### POST /api/ask

Send a question. Returns the complete answer (non-streaming).

**Request:**
```json
{
    "question": "What do they say about Perplexity AI?"
}
```

**Response:**
```json
{
    "session_id": "uuid",
    "answer": "Based on the video, at [1:53](https://youtu.be/...) ...",
    "tool_used": "vector_search",
    "limits": { ... }
}
```

**Error codes:**

| Code | HTTP | Meaning |
|---|---|---|
| `QUESTION_LIMIT` | 403 | 10 questions reached |
| `NO_VIDEOS` | 400 | No videos loaded |
| `QUESTION_TOO_LONG` | 400 | Over 500 characters |
| `INTERNAL_ERROR` | 500 | Agent failure |

### POST /api/ask/stream

**Streaming version of `/api/ask`.** Returns the answer token-by-token via Server-Sent Events (SSE). Preferred by the frontend for better UX.

**Request:** same as `/api/ask`:
```json
{
    "question": "What do they say about Perplexity AI?"
}
```

**Response:** SSE event stream (`Content-Type: text/event-stream`)

**Event types:**

| Event | Data | When |
|---|---|---|
| `tool` | `{"tool_used": "vector_search"}` | Agent selects a tool |
| `token` | `{"text": "Based"}` | Each chunk of the answer |
| `done` | `{"limits": {...}}` | Stream complete |
| `error` | `{"error": "...", "code": "..."}` | Failure mid-stream |

**SSE format:**
```
event: tool
data: {"tool_used": "vector_search"}

event: token
data: {"text": "Based"}

event: token
data: {"text": " on"}

event: token
data: {"text": " the video"}

...

event: done
data: {"limits": {"videos_loaded": 1, "videos_max": 5, "questions_used": 4, "questions_max": 10, "unlimited": false}}
```

**Backend implementation:**

```python
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import json

@router.post("/ask/stream")
async def ask_stream(request: AskRequest, session_id: str = Header(None, alias="X-Session-ID")):
    sid, session = get_or_create_session(session_id)

    # Validate
    if not session["loaded_videos"]:
        raise HTTPException(400, detail={"error": "No videos loaded.", "code": "NO_VIDEOS"})
    if not session["unlimited"] and session["question_count"] >= MAX_QUESTIONS_FREE:
        raise HTTPException(403, detail={"error": "Question limit reached.", "code": "QUESTION_LIMIT"})

    async def event_generator():
        try:
            # Build tools and agent
            pc, index = get_pinecone()
            anthropic_client = get_anthropic()
            selected = [v["video_id"] for v in session["loaded_videos"] if v.get("selected", True)]
            tools = build_tools(selected, pc, index, anthropic_client)
            agent = get_or_create_agent(session, tools)
            config = {"configurable": {"thread_id": session["agent_thread_id"]}}

            # Stream agent response
            full_answer = ""
            tool_used = None

            for event in agent.stream(
                {"messages": [("user", request.question)]},
                config,
                stream_mode="updates",
            ):
                # Extract tool calls
                for key, value in event.items():
                    if key == "agent":
                        msgs = value.get("messages", [])
                        for msg in msgs:
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                tool_used = msg.tool_calls[0]["name"]
                                yield {"event": "tool", "data": json.dumps({"tool_used": tool_used})}
                            elif hasattr(msg, "content") and isinstance(msg.content, str):
                                # Final answer from agent
                                new_text = msg.content
                                if new_text and new_text != full_answer:
                                    delta = new_text[len(full_answer):]
                                    full_answer = new_text
                                    yield {"event": "token", "data": json.dumps({"text": delta})}

            # Update session
            session["question_count"] += 1
            session["chat_history"].append({"role": "user", "content": request.question})
            session["chat_history"].append({"role": "assistant", "content": full_answer})

            yield {"event": "done", "data": json.dumps({"limits": build_limits(session)})}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e), "code": "INTERNAL_ERROR"})}

    return EventSourceResponse(event_generator())
```

**Note:** The streaming implementation depends on how LangGraph's `.stream()` emits updates. The sketch above shows the pattern; the exact event parsing may need adjustment based on the actual LangGraph stream output. Test locally and adapt.

**Dependency:** add `sse-starlette` to requirements.txt.

### POST /api/auth

Validate an access key.

**Request:**
```json
{
    "key": "ASKTHEVIDEO2026"
}
```

**Response (valid):**
```json
{
    "session_id": "uuid",
    "valid": true,
    "limits": {
        "videos_loaded": 1,
        "videos_max": null,
        "questions_used": 4,
        "questions_max": null,
        "unlimited": true
    }
}
```

**Response (invalid):**
```json
{
    "session_id": "uuid",
    "valid": false
}
```

### GET /api/status

Health check + session status.

**Response (no session):**
```json
{
    "status": "ok",
    "app": "AskTheVideo"
}
```

**Response (with session):**
```json
{
    "session_id": "uuid",
    "status": "ok",
    "limits": { ... }
}
```

### GET /api/history

Return chat history.

**Response:**
```json
{
    "session_id": "uuid",
    "messages": [
        {"role": "user", "content": "What is this video about?"},
        {"role": "assistant", "content": "This video covers..."}
    ]
}
```

### GET /health

Simple health check for Koyeb. `200 OK` with `{"status": "ok"}`.

---

## Backend structure

```
api/
    __init__.py
    main.py              # FastAPI app, static file serving
    session.py           # In-memory session management
    dependencies.py      # Pinecone + Anthropic client singletons
    routes/
        __init__.py
        videos.py        # POST/GET/DELETE/PATCH /api/videos
        ask.py           # POST /api/ask + POST /api/ask/stream
        auth.py          # POST /api/auth
        status.py        # GET /api/status, /health, /api/history
```

### main.py

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.routes import videos, ask, auth, status

app = FastAPI(title="AskTheVideo API")

app.include_router(videos.router, prefix="/api")
app.include_router(ask.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(status.router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok"}

app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")

@app.get("/{path:path}")
async def serve_react(path: str):
    return FileResponse("frontend/index.html")
```

### dependencies.py

```python
from functools import lru_cache
from pinecone import Pinecone
from anthropic import Anthropic
import os

@lru_cache()
def get_pinecone():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "askthevideo"))
    index.describe_index_stats()  # Warm up
    return pc, index

@lru_cache()
def get_anthropic():
    return Anthropic()
```

---

## Agent management

Tools are built per-request with the session's video list as a closure:

```python
def build_tools(selected_videos, pc, index, anthropic_client):
    @tool
    def vector_search(question: str) -> str:
        # Uses selected_videos from closure
        ...
    return [vector_search, summarize_video, list_topics, compare_videos, get_metadata]
```

Agent is recreated when loaded_videos changes:

```python
def get_or_create_agent(session, tools):
    current_videos = [v["video_id"] for v in session["loaded_videos"]]
    if session["agent"] is None or session["_agent_videos"] != current_videos:
        agent, memory = create_askthevideo_agent(tools, current_videos)
        session["agent"] = agent
        session["_agent_videos"] = current_videos.copy()
    return session["agent"]
```

---

## Limits helper

```python
def build_limits(session):
    return {
        "videos_loaded": len(session["loaded_videos"]),
        "videos_max": None if session["unlimited"] else MAX_VIDEOS_FREE,
        "questions_used": session["question_count"],
        "questions_max": None if session["unlimited"] else MAX_QUESTIONS_FREE,
        "unlimited": session["unlimited"],
    }
```

---

## Error responses

All errors:
```json
{"error": "Human-readable message", "code": "MACHINE_CODE"}
```

HTTP status codes: 200 success, 400 bad request, 403 limit reached, 404 not found, 500 internal.

---

## Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY api/ api/
COPY config/ config/
COPY frontend/ frontend/
EXPOSE 8000
HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Requirements

```
fastapi
uvicorn[standard]
sse-starlette
langchain
langchain-anthropic
langgraph
pinecone-client
youtube-transcript-api
python-dotenv
anthropic
```

---

## Memory budget

| Component | Estimated RAM |
|---|---|
| Python + FastAPI + uvicorn | ~35MB |
| langchain + langgraph + anthropic + pinecone | ~80MB |
| React static files (from disk) | ~0MB |
| 10 concurrent sessions | ~15MB |
| Headroom | ~380MB |
| **Total budget** | **512MB** |

---

## CORS

Not needed (single container, same origin).

---

## What stays the same

All `src/` modules unchanged: transcript.py, chunking.py, vectorstore.py, tools.py, agent.py, metadata.py, validation.py, errors.py. The only new code is `api/` (routing layer + session management).
