# AskTheVideo -- Phase 2 Handoff for Claude Code

## What this is

You are picking up a project that has completed Phase 1 (notebook-based exploration and validation). Six Jupyter notebooks have been built and tested, with production code tagged for extraction. Your job is Phase 2: extract the code, build the FastAPI backend, and deploy.

**Do not redesign anything.** The architecture, tool definitions, prompts, chunking strategy, and all decisions are final. They were validated empirically in notebooks. Your job is mechanical assembly.

**Architecture:** React frontend (built separately in Lovable) + FastAPI backend. All `src/` modules stay identical. Only the serving layer is new.

---

## Project location

```
askthevideo/
├── .env                    # API keys (exists, do not modify)
├── .venv/                  # Python 3.12 venv (exists)
├── requirements.txt        # Needs update: remove streamlit, add fastapi+uvicorn+sse-starlette
├── requirements-dev.txt    # Dev deps (exists)
├── data/
│   └── test_transcripts.json   # Cached test data
├── notebooks/
│   ├── 01_transcript_fetch.ipynb
│   ├── 02_chunking.ipynb
│   ├── 03_pinecone_operations.ipynb
│   ├── 04_claude_tools.ipynb
│   ├── 05_agent_routing.ipynb
│   └── 06_integration_flow.ipynb
├── src/                    # TARGET: extract production code here
├── api/                    # TARGET: FastAPI routing layer here
├── scripts/                # TARGET: extract.py goes here
├── tests/                  # TARGET: unit tests go here
├── config/                 # TARGET: settings.py goes here
├── frontend/               # TARGET: React build output (provided separately)
├── docs/                   # Design docs (read-only reference)
└── landing/                # Landing page (built separately)
```

## Python environment

- Python 3.12 with venv (NOT conda)
- Activate: `source .venv/bin/activate`
- The venv prompt shows "askthevideo"
- All dependencies already installed (add fastapi, uvicorn, sse-starlette)

---

## Step 1: Extract production code from notebooks

Each notebook has cells tagged with `# @export src/target.py` as the first line.

### Extraction mapping

| Notebook | Target file | What it contains |
|---|---|---|
| 01_transcript_fetch | `src/transcript.py` | `extract_video_id()`, `fetch_transcript()` |
| 02_chunking | `src/chunking.py` | `format_time()`, `chunk_transcript()` |
| 03_pinecone_operations | `src/vectorstore.py` | `get_pinecone_index()`, `embed_texts()`, `upsert_chunks()`, `upsert_metadata_record()`, `query_chunks()`, `fetch_metadata()`, `namespace_exists()` |
| 04_claude_tools | `src/tools.py` | `_embed_texts()`, `_query_chunks()`, `_fetch_all_chunks()`, `_build_full_text()`, `_fetch_or_generate_cached()`, `vector_search()`, `summarize_video()`, `get_topics()`, `compare_videos()`, `get_metadata()` |
| 05_agent_routing | `src/agent.py` | `create_askthevideo_agent()` |

### Extraction rules

1. Read each .ipynb file as JSON
2. Find code cells where the first line matches `# @export <path>`
3. Remove the `# @export` line itself
4. Group cells by target file
5. Deduplicate imports (multiple cells may import the same module)
6. Move all imports to the top of each file
7. Add header: `"""Auto-generated from notebooks. Do not edit directly."""`
8. Write to `src/`

### Create `scripts/extract.py` and `Makefile`:

```makefile
.PHONY: extract format lint test all

extract:
	python scripts/extract.py

format:
	black src/ api/

lint:
	ruff check src/ api/

test:
	pytest tests/ -v

all: extract format lint test
```

### Critical: query_chunks filter

In `src/tools.py`, verify `_query_chunks()` filters with:
```python
if m.metadata.get("type", "chunk") == "chunk"
```
NOT `!= "metadata"`. Bug found in notebook 06.

---

## Step 2: Build files NOT from notebooks

### `config/settings.py`
```python
"""Application constants and configuration."""

CHUNK_WINDOW_SECONDS = 120
CHUNK_CARRY_SNIPPETS = 3
EMBED_MODEL = "llama-text-embed-v2"
EMBED_BATCH_SIZE = 50
SENTINEL_VECTOR = [1e-7] + [0.0] * 1023
CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_VIDEOS_FREE = 5
MAX_QUESTIONS_FREE = 10
MAX_DURATION_FREE = 3600
SESSION_TTL_HOURS = 2
APP_NAME = "AskTheVideo"
APP_URL = "https://app.askthevideo.com"
```

### `src/metadata.py`
Video metadata via YouTube oEmbed (validated in notebook 06):
- `fetch_video_metadata(video_id)` returns `{"video_title", "channel", "thumbnail_url"}`
- `thumbnail_url` is the YouTube thumbnail image URL (used by frontend for video list display)
- On error returns `{"video_title": "Unknown", "channel": "Unknown", "thumbnail_url": ""}`
- Also store `thumbnail_url` in Pinecone metadata record so cached videos have it too

### `src/validation.py`
- `validate_youtube_url(url)` -- extract and validate video ID
- `validate_question(text)` -- length cap (500 chars)

### `src/errors.py`
- `UserFacingError(message, code)` exception class
- `send_discord_alert(message)` -- webhook notification
- `safe_execute(func, *args)` -- try/except with Discord on failure

### `src/auth.py`
- `validate_access_key(key)` -- check against VALID_ACCESS_KEYS env var

---

## Step 3: Build FastAPI backend

See FASTAPI_BACKEND_SPEC.md for the full API specification.

### File structure

```
api/
├── __init__.py
├── main.py              # FastAPI app, static file serving
├── session.py           # In-memory session management
├── dependencies.py      # Pinecone + Anthropic client singletons
└── routes/
    ├── __init__.py
    ├── videos.py        # POST/GET/DELETE/PATCH /api/videos
    ├── ask.py           # POST /api/ask + POST /api/ask/stream
    ├── auth.py          # POST /api/auth
    └── status.py        # GET /api/status, /health, /api/history
```

### Key design decisions

**Session management:** In-memory dict, UUID key, 2-hour TTL. Session ID via `X-Session-ID` header.

**Tool building:** Tools built per-request with session's selected video list as closure. Replaces global `loaded_videos` from notebooks.

**Agent recreation:** Recreate when loaded_videos changes (system prompt includes video list). Stored on session dict.

**Static file serving:** `/assets/*` mapped to `frontend/assets/`. Catch-all serves `frontend/index.html`.

**Error responses:** All return `{"error": "...", "code": "..."}` with HTTP status codes.

**Limits object:** Every mutating endpoint returns current limits.

**Video responses include `thumbnail_url`:** Fetched from oEmbed during ingestion, stored in Pinecone metadata for cached videos. Frontend uses this to display thumbnails in the video list.

### Streaming endpoint: POST /api/ask/stream

This is the preferred endpoint for the frontend. Returns Server-Sent Events (SSE) so the answer streams token-by-token.

**Event types:**
- `tool` -- agent selected a tool (`{"tool_used": "vector_search"}`)
- `token` -- chunk of the answer (`{"text": "Based"}`)
- `done` -- stream complete (`{"limits": {...}}`)
- `error` -- failure (`{"error": "...", "code": "..."}`)

**Implementation uses `sse-starlette` package** (add to requirements.txt). Uses LangGraph's `.stream()` method with `stream_mode="updates"` to emit incremental updates.

The non-streaming `POST /api/ask` endpoint must also exist as a fallback.

**See FASTAPI_BACKEND_SPEC.md** for the full implementation sketch including the event generator function.

### Thumbnail storage in Pinecone

When ingesting a video, `fetch_video_metadata()` returns `thumbnail_url`. Store it in the Pinecone metadata record alongside existing fields:

```python
pine_index.upsert(vectors=[{
    "id": f"{video_id}_metadata",
    "values": SENTINEL_VECTOR,
    "metadata": {
        "type": "metadata",
        "video_id": video_id,
        "video_title": title,
        "channel": channel,
        "thumbnail_url": thumbnail_url,    # <-- add this
        "duration_seconds": duration_seconds,
        "duration_display": format_time(duration_seconds),
        "chunk_count": len(chunks),
        "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
}], namespace=video_id)
```

When returning cached video data, include `thumbnail_url` from the fetched metadata record.

---

## Step 4: Dockerfile + deployment

### Dockerfile

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

### requirements.txt

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

**Removed:** `streamlit`
**Added:** `fastapi`, `uvicorn[standard]`, `sse-starlette`

### Koyeb deployment

- Port: 8000
- Health check: HTTP GET `/health`
- Environment variables: copy from .env
- RAM budget: ~35MB (FastAPI) + ~80MB (ML deps) + ~15MB (sessions) = ~130MB, ~380MB headroom

### React placeholder for testing

Before the Lovable build is available:
```bash
mkdir -p frontend
echo '<html><body><h1>AskTheVideo API</h1></body></html>' > frontend/index.html
```

---

## Step 5: Unit tests

### `tests/test_validation.py`
- `extract_video_id`: 7 valid URL formats + 3 invalid
- `validate_question`: normal, empty, over-length

### `tests/test_chunking.py`
- Empty input, short transcript, carry snippet continuity, required keys

### `tests/test_metadata.py`
- Valid video ID returns title, channel, thumbnail_url
- Invalid ID returns fallback values

### `tests/test_session.py`
- Create new session, return existing, TTL expiration

### `tests/test_api.py`
Using FastAPI `TestClient`:
- `GET /health` returns 200
- `GET /api/status` returns session_id
- `POST /api/videos` with valid/invalid URL
- `POST /api/ask` without videos returns 400
- `POST /api/ask/stream` returns SSE events
- `POST /api/auth` with valid/invalid keys

---

## Environment variables (.env)

All already configured. Do not modify.

```
ANTHROPIC_API_KEY=sk-ant-...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=askthevideo
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
LANGSMITH_PROJECT=askthevideo
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ADMIN_TOKEN=...
VALID_ACCESS_KEYS=ASKTHEVIDEO2026
```

---

## What NOT to do

- Do not change chunking strategy (120s window, 3-snippet carry)
- Do not change embedding model (llama-text-embed-v2, 1024 dims)
- Do not change Claude model (claude-sonnet-4-6)
- Do not change tool descriptions or system prompts (10/10 routing accuracy)
- Do not use `create_react_agent` from `langgraph.prebuilt` (deprecated). Use `create_agent` from `langchain.agents` with `system_prompt=`
- Do not use pure zero vectors. Use sentinel: `[1e-7] + [0.0] * 1023`
- Do not filter query results with `!= "metadata"`. Use `== "chunk"`
- Do not use conda. Use existing venv (.venv, Python 3.12)
- Do not install Python 3.14
- Do not use Streamlit
- Do not modify React frontend files

---

## Reference documents (read in order)

1. **FASTAPI_BACKEND_SPEC.md** -- full API spec, all endpoints including streaming, session management
2. **SYSTEM_DESIGN.md** -- complete architecture
3. **BUILD_ORDER.md** -- progress tracker
4. **PROJECT_PLAN.md** -- all 73 decisions
5. **SETUP_GUIDE.md** -- environment setup
6. **COST_BREAKDOWN.md** -- measured costs
7. **REACT_FRONTEND_SPEC.md** -- frontend API contract (reference only, frontend built separately)

---

## Success criteria

Phase 2 is done when:

1. `make all` passes (extract, format, lint, test)
2. `uvicorn api.main:app` starts locally
3. `GET /health` returns 200
4. `POST /api/videos` ingests a video and returns thumbnail_url
5. `POST /api/ask` returns an answer with timestamps
6. `POST /api/ask/stream` streams tokens via SSE
7. Cached video loads instantly (no re-embedding)
8. Session limits work (blocks at 11th question, 6th video)
9. Access key unlocks unlimited mode
10. Docker image builds and runs within 512MB
11. Deployed to Koyeb at app.askthevideo.com
12. React frontend served at `/`, API at `/api/`
