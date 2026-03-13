# AskTheVideo — Phase 2 Build Deviations & Decisions

This document records every place where the actual build differs from the original spec in `docs/spec/CLAUDE_CODE_HANDOFF.md` and `docs/spec/FASTAPI_BACKEND_SPEC.md`, plus bugs discovered and fixed during implementation and testing.

---

## 1. `pinecone-client` → `pinecone` (requirements.txt)

**Spec said:** `pinecone-client`
**Actual:** `pinecone`

**Reason:** The `pinecone-client` package has been officially renamed to `pinecone`. Using the old name installs a stub that raises an exception at import time:
```
Exception: The official Pinecone python package has been renamed from
`pinecone-client` to `pinecone`.
```

---

## 2. `src/vectorstore.py` — `query_chunks()` filter left as notebook original

**Spec said:** Fix `query_chunks()` filter to `== "chunk"` (bug noted in handoff).
**Actual:** Left as `!= "metadata"` (verbatim from notebook 03).

**Reason:** The handoff explicitly called out the fix only for `src/tools.py` (`_query_chunks`). `src/vectorstore.py` is a separate module generated from notebook 03 and is left unchanged. `src/tools.py` has the corrected `== "chunk"` filter as specified.

---

## 3. `scripts/extract.py` — multi-line import fix

**Spec said:** Write an extractor that moves all imports to the top of each file.
**Actual:** The initial extractor split on a line-by-line basis and broke multi-line parenthesised imports, e.g.:

```python
# Broken output (before fix)
from youtube_transcript_api._errors import (
import re                          # <-- inserted in the middle
    TranscriptsDisabled,
    ...
)
```

**Fix:** The `collect_imports()` function was updated to track open parentheses and keep continuation lines together with their opening `from ... import (` line.

---

## 4. SSE streaming — `agent.stream()` runs in a thread pool

**Spec said:** Use `agent.stream()` with `stream_mode="updates"` inside the async event generator.
**Actual:** `agent.stream()` is synchronous and blocks the event loop. Running it directly inside an `async def` generator prevented uvicorn from flushing SSE events to the browser (they all arrived at once after the full response, or the browser timed out).

**Fix:** `agent.stream()` is offloaded to a background thread via `asyncio.to_thread()`. Chunks are passed back to the async generator through an `asyncio.Queue` using `loop.call_soon_threadsafe()`.

---

## 5. SSE streaming — `stream_mode="updates"` → `stream_mode="messages"`

**Spec said:** Use `stream_mode="updates"`.
**Actual:** `stream_mode="updates"` returns each node's full state in one batch — no token-by-token output. Tested in the venv: the `agent` node key contains the complete final `AIMessage` in a single event.

**Fix:** Switched to `stream_mode="messages"` which yields `(chunk, metadata)` pairs at the token level. The `metadata["langgraph_node"]` field identifies which node emitted the chunk (`"model"` for LLM output). Also discovered that `chunk.content` is a list of dicts `[{"text": "...", "type": "text"}]`, not a plain string.

---

## 6. SSE event format — `{"text": ...}` → `{"token": ...}`

**Spec said:** Emit `event: token` / `data: {"text": "..."}` SSE events.
**Actual:** The React frontend (built with Lovable) reads `data:` lines and checks for `A.token` in the parsed JSON. It completely ignores `event:` prefix lines. Sending `{"text": "..."}` meant `A.token` was always `undefined` — nothing was displayed in the chat.

**Fix:** Token events now emit `data: {"token": "..."}` (no `event:` prefix, field renamed from `text` to `token`). Done event emits `data: {"limits": {...}}` which the frontend detects via `A.limits`.

**Discovery method:** Decompiled the minified frontend JS (`frontend/assets/index-fgc_TARV.js`) to find the actual SSE parsing logic.

---

## 7. `koyeb.yaml` added

**Spec said:** Nothing about `koyeb.yaml`.
**Actual:** Without this file, Koyeb ignores the `Dockerfile` and uses buildpack auto-detection.

**Fix:** Added `koyeb.yaml` at repo root:
```yaml
build:
  builder: docker
  docker:
    dockerfile: Dockerfile
```

---

## 8. `.env.docker` generation

**Spec said:** Nothing about `.env.docker`.
**Actual:** `docker run --env-file` requires plain `KEY=value` format. The project's `.env` uses `export KEY=value`. Running `docker run --env-file .env` fails.

**Fix:** Generate `.env.docker` with:
```bash
sed 's/^export //' .env > .env.docker
```
`.env.docker` is gitignored.

---

## 9. `scripts/docker_build.sh` added

**Spec said:** Nothing about a build script.
**Actual:** Added `scripts/docker_build.sh` for convenient manual rebuilds. Supports `IMAGE_NAME` and `TAG` env vars.

---

## 10. `api/main.py` — conditional static file mounting

**Spec said:** `app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")`
**Actual:** If `frontend/assets/` does not exist (e.g. placeholder only), `StaticFiles` raises an error at startup.

**Fix:** Mount is conditional:
```python
if Path("frontend/assets").exists():
    app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")
```

---

## 11. Admin panel backend — `EVENT_LOG_PATH` fallback for local dev

**Spec said:** `EVENT_LOG_PATH` defaults to `/app/events.log`.
**Actual:** `/app/events.log` doesn't exist outside Docker, causing `FileNotFoundError` on import during local dev and tests.

**Fix:** `src/metrics.py` uses a smart default:
```python
_default_log = "/app/events.log" if os.path.isdir("/app") else "events.log"
EVENT_LOG_PATH = os.getenv("EVENT_LOG_PATH", _default_log)
```

---

## 12. Admin panel backend — `get_client_ip()` in shared `api/utils.py`

**Spec said:** Define `get_client_ip()` inline in route handlers.
**Actual:** Both `ask.py` and `videos.py` need the same function. Importing from one route to another creates fragile cross-dependencies.

**Fix:** Created `api/utils.py` with `get_client_ip()` and both routes import from there.

---

## 13. Timestamp links — plain text timestamps → clickable markdown links

**Spec said:** Nothing specific about timestamp link format.
**Actual:** Claude's tool responses included timestamps like `[2:30]` or `[2:30-5:00]` as plain text. The frontend renders markdown (react-markdown with `target="_blank"` on links), but timestamps weren't formatted as markdown links, so they weren't clickable.

**Root cause:** Two issues:
1. `_build_full_text()` (used by summarize/topics tools) formatted chunk headers as `[0:00–2:00]` with no video URL, so Claude had no URL to reference.
2. System prompts told Claude to "reference timestamps" but never instructed it to format them as clickable markdown links.

**Fix:**
- `_build_full_text()` now includes the video URL in markdown link format: `[0:00–2:00](https://youtu.be/ID?t=0)`
- All 4 tool system prompts (vector_search, summarize, topics, compare) now explicitly instruct Claude to output timestamps as `[MM:SS](https://youtu.be/ID?t=SECONDS)`
- Agent system prompt in `src/agent.py` also updated

**Note:** Previously cached summaries/topics in Pinecone still have the old plain-text format. To get clickable links, delete and re-add the video (or clear the cached `_summary` / `_topics` records from Pinecone).

---

## 14. Video selection — agent rebuilds on selection change

**Spec said:** `POST /api/ask` should only use selected videos.
**Actual:** `get_or_create_agent()` passed ALL `session["loaded_videos"]` to the agent's system prompt and used the full list as the cache key. Toggling a video's `selected` state didn't trigger an agent rebuild, so the LLM still saw all videos.

**Root cause:** Two issues in `api/routes/ask.py`:
1. `get_or_create_agent()` built the agent with all video IDs, not just selected ones
2. The cache key (`_agent_videos`) didn't reflect selection state, so deselecting a video didn't force a rebuild

**Fix:**
- `get_or_create_agent()` now takes a `selected_videos` parameter and uses it for both the system prompt and cache key
- Both `/ask` and `/ask/stream` filter to selected videos before building tools and agent
- Fallback: if no videos are selected, all loaded videos are used

---

## 15. Frontend bug — React 18 batching broke PATCH `selected` value

**Discovered:** The PATCH endpoint always received `selected=true` regardless of user action.

**Root cause (frontend):** The toggle callback captured the current `selected` state inside a React `setState` updater function. Due to React 18 automatic batching, the updater hadn't executed when the PATCH request fired, so the captured variable was `undefined` and `!undefined === true`.

**Fix (frontend, deployed via Lovable):** Read the current state from the `videos` variable directly before calling `setState`, not from inside the updater callback.

**Backend note:** No workaround needed — the frontend was fixed. The backend PATCH uses `body.selected` as-is.

---

## 16. API cost tracking showing $0 — missing `record_tokens()` in tools

**Discovered:** Admin panel always showed $0.00 estimated cost despite multiple queries being answered.

**Root cause:** The `TokenTracker` LangChain callback on the agent LLM only tracked token usage from **agent routing calls** (deciding which tool to call and formatting the final answer). The 3 direct `client.messages.create()` calls in `src/tools.py` — which perform the actual heavy work (vector_search, summarize, compare) and consume the bulk of API tokens — never called `record_tokens()`.

**Fix:**
- Added `from src.metrics import record_tokens` to `src/tools.py`
- Added `record_tokens(response.usage.input_tokens, response.usage.output_tokens)` after all 3 `client.messages.create()` calls in `src/tools.py`
- Made `TokenTracker` in `src/agent.py` more robust with a `usage_metadata` fallback for LangChain ≥0.2

**Note:** Changes were made in notebooks 04 and 05, then regenerated via `scripts/extract.py`.

---

## 17. Tool cache/API logging in event log

**Spec said:** Nothing about logging tool cache hits.
**Actual:** No way to tell if `summarize_video` or `list_topics` results came from Pinecone cache or a fresh Claude API call.

**Fix:** Added `log_event("TOOL", source, ...)` calls in the `@tool` wrappers for `summarize_video` and `list_topics` in `api/routes/ask.py`. The `source` is `"cache"` or `"api"` based on the `cached` field returned by the underlying functions. Example log line:
```
TOOL    cache    —    summarize_video video=e-gwvmhyU7A
```

**Note:** `vector_search` and `compare_videos` always hit the API (no caching), so no log is emitted for those.

---

## 18. Log detail field — pipe character splitting bug

**Spec said:** N/A (discovered during #16).
**Actual:** `log_event()` uses `|` as the column delimiter. The initial detail string `"summarize_video | video=xxx"` contained a pipe, which caused `get_recent_events()` to split it into extra columns — the video ID was lost in the admin panel display.

**Fix:** Changed detail format to use spaces instead of pipes: `"summarize_video video=xxx"`.

---

## 19. `scripts/extract.py` — handle string source format from NotebookEdit

**Spec said:** N/A.
**Actual:** The `NotebookEdit` tool writes cell source as a single string, while Jupyter saves it as a list of lines. The extractor only handled the list format — `source_lines[0]` on a string returns the first character, so `# @export` was never matched.

**Fix:** Added type check:
```python
if isinstance(raw_source, str):
    source_lines = raw_source.splitlines(keepends=True)
else:
    source_lines = raw_source
```

---

## 20. Error response format — `HTTPException` detail wrapping

**Spec said:** N/A (discovered from frontend testing).
**Actual:** FastAPI's `HTTPException(400, detail={"error": "...", "code": "..."})` returns `{"detail": {"error": "...", "code": "..."}}`. The frontend reads `response.json().error` at the top level, which is `undefined`, so it always displayed "An unexpected error occurred."

**Root cause:** FastAPI wraps the `detail` argument inside a `{"detail": ...}` envelope. The frontend expects `{"error": "...", "code": "..."}` at the top level.

**Fix:** Added two exception handlers in `api/main.py`:
1. `HTTPException` handler — returns `exc.detail` dict directly as the response body (no wrapping)
2. Global `Exception` handler — catches uncaught errors and returns `{"error": "An internal error occurred.", "code": "INTERNAL_ERROR"}` with a 500 status, plus logs the error

---

## 21. Static file serving from `frontend/` root

**Spec said:** Serve `frontend/assets/` via `StaticFiles` mount and `frontend/index.html` as catch-all.
**Actual:** Files in the `frontend/` root directory (e.g. `favicon.png`, `favicon.ico`, `robots.txt`, `placeholder.svg`) were not accessible. Requests to `/favicon.png` hit the catch-all route and returned `index.html` instead.

**Fix:** Updated the catch-all route in `api/main.py` to check if the requested path matches a real file in `frontend/` before falling back to `index.html`:
```python
if path:
    static_file = Path("frontend") / path
    if static_file.is_file():
        return FileResponse(str(static_file))
```

---

## 22. Transcript error handling — `IpBlocked`, `RequestBlocked`, and catch-all

**Spec said:** Only catch `TranscriptsDisabled`, `NoTranscriptFound`, `VideoUnavailable` in `fetch_transcript`.
**Actual:** YouTube can also throw `IpBlocked` and `RequestBlocked` (e.g. from cloud server IPs like Koyeb). These fell through to a generic catch-all that showed "Could not load video" with no useful detail. The user couldn't tell if the video didn't exist or if YouTube was blocking the server.

**Fix (notebook 01 → `src/transcript.py`):**
- Added `IpBlocked` and `RequestBlocked` imports
- `IpBlocked` / `RequestBlocked` → `ValueError("YouTube is blocking transcript requests. Please try again later.")`
- Generic `except Exception` → `ValueError("Could not fetch transcript for video {id}: {ExceptionType}")`
- All exceptions now converted to `ValueError` with descriptive messages

**Fix (`api/routes/videos.py`):**
- All transcript errors logged to event log
- IP blocking returns HTTP 503 with code `"IP_BLOCKED"`
- Every error message is passed through to the frontend (no more generic fallback)

---

## 23. YouTube IP blocking — attempted workarounds (abandoned)

**Problem:** YouTube blocks transcript requests from Koyeb's cloud server IPs (both US and EU regions). All new video loads fail with `IpBlocked`.

**Approaches tried and abandoned:**

1. **Cloudflare Worker proxy** (`scripts/cloudflare-worker.js`) — Used YouTube's Innertube API with Android client. Worked for some videos (e.g. music videos) but YouTube also blocks Cloudflare IPs for many videos. The `baseUrl` timedtext endpoint returns empty (0 bytes) from Cloudflare's IPs. Tried multiple Innertube clients (WEB, ANDROID, IOS, TVHTML5), the `get_transcript` endpoint (requires session auth), and various cookie/User-Agent combinations. Only ANDROID and IOS return caption tracks, but the actual transcript fetch is blocked per-video.

2. **Google Cloud Function proxy** (`scripts/gcf-transcript-proxy/`) — Same approach as Cloudflare but on Google Cloud (hypothesis: Google owns YouTube, so less likely to block). Code written and tested locally but not deployed — pivoted to approach 3 first.

3. **yt-dlp fallback** — Added `yt-dlp` as a second extraction method in the fallback chain (`youtube_transcript_api` → `yt-dlp` → proxy). yt-dlp uses a different YouTube code path (player page parsing + subtitle URLs) but ultimately hits the same timedtext endpoint, so it's also blocked from datacenter IPs.

**Key finding:** YouTube's blocking operates at multiple levels — the Innertube player API, the timedtext endpoint, and even the `get_transcript` API all enforce IP restrictions. The blocking is also per-video: popular music videos are less restricted than other content.

**Resolution:** All proxy/fallback code removed from production. Replaced with Webshare residential proxy (see #24).

**Reference files kept:** `scripts/cloudflare-worker.js` and `scripts/gcf-transcript-proxy/` remain in the repo as reference for what was tried.

---

## 24. Webshare residential proxy for YouTube transcripts

**Problem:** YouTube blocks transcript requests from all datacenter IPs (Koyeb, Cloudflare, and likely GCF). See #23 for the full investigation.

**Fix:** Integrated Webshare rotating residential proxy directly into `youtube_transcript_api` via its built-in `proxy_config` parameter:

- Added `_get_transcript_api()` helper in `src/transcript.py` (notebook 01, cell `21d441b1`)
- Uses `GenericProxyConfig` (not `WebshareProxyConfig`) with `http://{username}:{password}@p.webshare.io:80/`
- The `-rotate` suffix in the username tells Webshare to rotate IPs automatically
- When `WEBSHARE_USERNAME` and `WEBSHARE_PASSWORD` env vars are missing (local dev), falls back to direct connection
- `fetch_transcript()` now calls `_get_transcript_api()` instead of `YouTubeTranscriptApi()` directly

**New env vars:** `WEBSHARE_USERNAME`, `WEBSHARE_PASSWORD`

**Why this works:** Residential proxies use real ISP IP addresses that YouTube doesn't block (unlike datacenter IPs from cloud providers). The proxy is transparent to the `youtube_transcript_api` library — no code path changes needed, just a different HTTP transport.

---

## 25. `scripts/extract.py` — skip indented imports during hoisting

**Spec said:** N/A (discovered when adding yt-dlp fallback, kept after cleanup).
**Actual:** The `collect_imports()` function treated any line starting with `import` or `from` as a top-level import to hoist, including indented imports inside functions (e.g. `    import yt_dlp` as a lazy import). This broke the generated file by pulling the import out of its function scope.

**Fix:** Added indentation check — only hoist imports that start at column 0:
```python
elif not line[0:1].isspace() and (stripped.startswith("import ") or stripped.startswith("from ")):
```

---

## 26. Improved transcript error messages — proxy-aware user feedback

**Spec said:** N/A.
**Actual:** The initial error handling (#22) used a single generic message for `IpBlocked`/`RequestBlocked` and had no awareness of proxy failures. With the Webshare proxy (#24), two new failure modes exist: (a) the proxy IP gets temporarily blocked by YouTube (rotating to a new IP on retry fixes it), and (b) the proxy itself is down or unreachable.

**Fix (notebook 01 → `src/transcript.py`):**

| Exception | User message | Rationale |
|-----------|-------------|-----------|
| `IpBlocked`, `RequestBlocked` | "Temporary issue fetching this video. Please try again in a few seconds." | Webshare's `-rotate` suffix assigns a new residential IP on next request; retry likely succeeds |
| `ConnectionError`, `OSError`, `TimeoutError` | "Transcript service is temporarily unavailable. Please try again later." | Proxy is down or unreachable |
| Other exceptions containing "proxy", "connect", or "tunnel" | "Transcript service is temporarily unavailable. Please try again later." | Catches proxy auth failures, tunnel errors, etc. |
| `TranscriptsDisabled`, `NoTranscriptFound`, `VideoUnavailable` | (unchanged — specific per-video messages) | Not proxy-related |
| All other exceptions | "Could not fetch transcript for video {id}: {ErrorType}" | Unknown errors, logged for debugging |

Proxy-related errors are also logged at `ERROR` level with full exception details for server-side debugging, while user-facing messages stay friendly and actionable.

---

## 27. `src/errors.py` — Discord alerting implemented with throttling

**Spec said:** Implement critical alerting via Discord webhooks for production failures (credit exhaustion, quota limits, proxy failures).
**Actual:** `src/errors.py` rewritten with throttled `send_discord_alert()`. Removed `UserFacingError` (redundant with `HTTPException` — see #20) and `safe_execute()` (replaced by direct alert calls at each error site).

**Design decisions:**
- **Direct calls over wrapper:** Each error site calls `send_discord_alert()` directly with a specific `alert_type`, giving precise control over message content and which errors trigger alerts.
- **10-minute throttling:** Per `alert_type` — prevents Discord spam during cascading failures while still alerting on new error categories.
- **Lazy import in `src/metrics.py`:** Budget threshold check uses `from src.errors import send_discord_alert` inside the function to avoid circular import (`metrics` ← `errors` ← `metrics`).

**6 alert scenarios integrated:**

| Alert type | Location | Trigger |
|---|---|---|
| `anthropic_api` | `src/tools.py` (`_claude_create`) | Any `APIError` from Claude (credits, rate limits, 500s) |
| `ip_blocked` | `src/transcript.py` | `IpBlocked` or `RequestBlocked` from YouTube |
| `proxy_down` | `src/transcript.py` | Proxy connection failures (timeout, refused, tunnel error) |
| `pinecone_error` | `src/vectorstore.py` | `PineconeException` on embed, upsert, or query |
| `uncaught_500` | `api/main.py` | Global exception handler catches unhandled errors |
| `budget_threshold` | `src/metrics.py` | Estimated cost reaches 80% of $5 budget |

**Files modified:** `src/errors.py` (rewritten), `src/transcript.py` (via notebook 01), `src/tools.py` (via notebook 04), `src/vectorstore.py` (via notebook 03), `api/main.py`, `src/metrics.py`

---

## 28. `APP_URL` constant — defined but not yet used

**Spec said:** `APP_URL` for frontend wake-up ping (keeping Koyeb free tier alive) and redirect logic.
**Actual:** Defined in `config/settings.py` as `"https://app.askthevideo.com"` but not referenced by any Python code. The frontend wake-up logic is client-side JavaScript (in `SYSTEM_DESIGN.md` examples), not server-side.

**Status:** Kept for future use. Discord alerts (#27) were implemented without app links — alert messages are concise error descriptions, not navigation links.

---

## 29. `create_react_agent` → `create_agent` (LangGraph deprecation)

**Spec said:** Use `create_react_agent` from `langgraph.prebuilt` with `prompt=` parameter.
**Actual:** `create_react_agent` was deprecated in LangGraph V1.0 (to be removed in V2.0). Running the original import raises `LangGraphDeprecatedSinceV10`.

**Fix:** Production code (`src/agent.py`, via notebook 05) uses the new API:
```python
from langchain.agents import create_agent
agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT, checkpointer=memory)
```

Key changes:
- Import moved from `langgraph.prebuilt` → `langchain.agents`
- Function renamed from `create_react_agent` → `create_agent`
- Parameter renamed from `prompt=` → `system_prompt=`

**Note:** Notebook 05 exploration cells still use the old `create_react_agent` to show the deprecation warning and migration journey. The `@export` production cell uses the new API.

---

## 30. Tool wrappers catch all exceptions to prevent cascade failure

**Spec said:** N/A (bug discovered during stress testing).
**Actual:** When a tool call fails mid-execution (e.g., Anthropic 429 rate limit), the conversation history in MemorySaver contains a `tool_use` without a matching `tool_result`. The Anthropic API rejects all subsequent messages in that thread, making the entire session unusable after a single tool error.

**Fix:** All 5 LangChain `@tool` wrappers in `api/routes/ask.py` (`build_tools()`) now catch exceptions and return an error string instead of raising. The agent receives the error as a normal tool result and relays it to the user. Conversation context is fully preserved.

```python
@tool
def vector_search(question: str) -> str:
    try:
        result = _vector_search(...)
        return result.get("answer", "No relevant content found.")
    except Exception as e:
        log_event("ERROR", "tool", "—", f"vector_search: {type(e).__name__}: {str(e)[:80]}")
        return f"Sorry, I couldn't complete the search right now. Error: {type(e).__name__}"
```

**Files modified:** `api/routes/ask.py` only. No changes to `src/tools.py`, `src/agent.py`, or notebooks.

**Full details:** See `docs/BUG_CASCADE_FAILURE.md`.

---

## 31. Supabase persistent logging for metrics and events

**Spec said:** In-memory metrics with local file event log.
**Actual:** Metrics and events are volatile — container restart loses all historical data. Admin panel showed zeroes after each Koyeb redeploy.

**Fix:** Added Supabase REST API integration to `src/metrics.py`:
- **Dual-write:** `log_event()` writes to both local rotating file and Supabase `events` table
- **Token snapshots:** `record_tokens()` persists cumulative token usage to `metrics_snapshots` table
- **Startup restore:** `_restore_from_supabase()` seeds in-memory `_app_metrics` from Supabase on container start
- **Read path:** `get_recent_events()` reads from Supabase (last 7 days) with local file fallback
- **No SDK:** Uses `urllib.request` directly with publishable key + RLS policies (INSERT + SELECT only)
- **Fire-and-forget:** Supabase writes run in daemon threads to avoid blocking requests
- **Lazy config:** `_get_supabase_config()` reads env vars at call time (not import time) so `dotenv` has time to load
- **Test guard:** Returns empty config when `TESTING=1` to prevent unit tests from writing to production Supabase

**Supabase tables:**
- `events` — columns: `id`, `created_at`, `event_type`, `subtype`, `ip`, `detail`, `environment`
- `metrics_snapshots` — columns: `id`, `created_at`, `total_input_tokens`, `total_output_tokens`, `estimated_cost`, `total_queries`, `total_videos_loaded`, `active_sessions`, `ram_mb`, `environment`

**Environment separation:** Both tables include an `environment` column (populated from `APP_ENV` env var, default `"local"`). All reads (admin panel, startup restore) filter by current environment, so local Docker logs never mix with production data.

**RLS policies:** Publishable key can INSERT and SELECT only — no UPDATE/DELETE even if key leaks. Data cleanup requires Supabase SQL Editor.

**New env vars:** `SUPABASE_URL`, `SUPABASE_KEY`, `APP_ENV`

**New file:** `tests/conftest.py` — sets `TESTING=1` before any imports to prevent Supabase writes during testing.

---

## 32. Free tier limits reduced from 5/10 to 3/5

**Spec said:** 5 videos per session, 10 questions per session.
**Actual:** Reduced to 3 videos and 5 questions to manage costs during demo period.

**Files modified:** `config/settings.py`, `tests/test_session.py`

---

## 33. Enhanced observability — per-query, per-tool, and session depth logging

**Spec said:** Basic event logging (`log_event` with type/subtype/ip/detail).
**Actual:** Event detail strings now include structured performance and usage data for analytics.

**What was added:**

| Data point | Where logged | Example detail |
|------------|-------------|----------------|
| Query latency (end-to-end) | `QUERY`/`KEY` events | `latency=14320ms` |
| Per-query token usage | `QUERY`/`KEY` events | `tokens=8700/450` |
| Tool used per query | `QUERY`/`KEY` events | `tool=vector_search` |
| Tool execution latency | `TOOL` events | `vector_search latency=675ms` |
| Video duration (new loads) | `VIDEO new` events | `duration=3600s` |
| Transcript fetch time | `VIDEO new` events | `fetch=2150ms` |
| Video duration (cache hits) | `VIDEO cache` events | `duration=4:33` |
| Session engagement depth | `SESSION end` events | `tier=free questions=4 videos=2` |

**Files modified:** `api/routes/ask.py`, `api/routes/videos.py`, `api/session.py`

**No schema changes required** — all data stored in existing `detail` text column. Queryable via SQL `substring()` with regex.

Additionally, `get_recent_events()` now parses the `detail` string and returns structured fields (e.g. `tool`, `latency_ms`, `tokens_in`, `tokens_out`, `duration_s`, `questions`, `tier`) alongside the raw `detail`. This allows the admin frontend to display parsed columns without client-side regex.

**Files modified:** `api/routes/ask.py`, `api/routes/videos.py`, `api/session.py`, `src/metrics.py` (`_parse_detail()` + updated `get_recent_events()`)

---

## 34. Slow query Discord alert

**Spec said:** 6 Discord alert scenarios.
**Actual:** Added a 7th: `slow_query` — fires when a query takes longer than 60 seconds. Uses the same 10-minute per-type throttle as other alerts.

**Why:** Queries over 60s indicate the user likely gave up waiting. Without this alert, slow queries would only be visible by manually checking event logs.

**Files modified:** `api/routes/ask.py` (both `/ask` and `/ask/stream`)

---

## 35. Budget cycle tracking with cumulative cost and pre-Supabase offset

**Spec said:** Fixed `PROJECT_BUDGET = $5.00` with single 80% threshold alert.
**Actual:** Budget is now cycle-based — each $5 reload is a cycle that auto-detects from cumulative spend. Alert fires at 80% of each cycle.

**How it works:**
- `BUDGET_CYCLE = 5.00` — each reload amount
- `INITIAL_COST_OFFSET` env var — pre-Supabase spend (set once: `$7.65`)
- Cumulative cost = tracked tokens cost + offset
- Cycle auto-detected: `cycle_start = floor(cumulative / 5) * 5`
- Alert fires when `cumulative >= cycle_start + $4.00` (80%)
- No env var updates needed on reload — cycles advance automatically

**Admin API `cost` section now returns:**

| Field | Description |
|-------|-------------|
| `estimated_cost` | Cumulative all-time spend |
| `cost_offset` | Pre-Supabase historical spend |
| `budget_cycle` | Reload amount ($5.00) |
| `budget_cycle_spent` | Spent in current cycle |
| `budget_cycle_remaining` | Remaining in current cycle |
| `budget_total_loaded` | Total ever loaded (cycle ceiling) |

**New env vars:**
- `INITIAL_COST_OFFSET` (default `0`) — pre-Supabase cumulative spend in USD
- `INITIAL_INPUT_TOKENS` (default `0`) — pre-Supabase cumulative input tokens
- `INITIAL_OUTPUT_TOKENS` (default `0`) — pre-Supabase cumulative output tokens

**Files modified:** `src/metrics.py`, `api/routes/admin.py`, `tests/test_metrics.py`

---

## 36. Anonymous user tracking

**Spec said:** No user identification — sessions are ephemeral with no cross-session linking.
**Actual:** Anonymous persistent user tracking via `localStorage` UUID, `X-User-ID` header, and Supabase `users` table.

**How it works:**
- Frontend generates UUID on first visit, stores in `localStorage` as `atv_uid`
- Sent as `X-User-ID` header on `/api/videos`, `/api/ask`, `/api/ask/stream`
- Backend upserts user record in Supabase on session start (fire-and-forget)
- Increments `total_questions` and `total_videos` on each respective action
- All events tagged with `user_id` in the `events` table
- No cookies — no consent banner needed

**Supabase schema changes:**
- New `users` table: `uid`, `first_seen`, `last_seen`, `total_sessions`, `total_questions`, `total_videos`, `environment`
- New `user_id` column on `events` table
- RLS: INSERT + SELECT + UPDATE on `users` (UPDATE needed for upsert on return visits)

**Admin API returns new `users` section:**

| Field | Description |
|-------|-------------|
| `total_users` | Total unique users |
| `returning_users` | Users with >1 session |
| `avg_sessions_per_user` | Average sessions per user |
| `avg_questions_per_user` | Average questions per user |

**Tracking scope:** Video loads and questions only. Page visits (`GET /api/status`) do not trigger user tracking.

**Files modified:** `src/metrics.py`, `api/session.py`, `api/routes/ask.py`, `api/routes/videos.py`, `api/routes/admin.py`

---

## 37. Discord alerts upgraded to color-coded embeds

**Spec said:** Plain text Discord webhook messages.
**Actual:** Color-coded embed cards with title, description, footer (environment), and timestamp. Added `User-Agent` header to fix Discord blocking Python's default user agent.

**Alert styles:**

| Alert Type | Title | Color |
|------------|-------|-------|
| `budget_threshold` | 💰 Budget Threshold | Yellow |
| `slow_query` | 🐢 Slow Query | Orange |
| `anthropic_error` | 🚨 Anthropic API Error | Red |
| `youtube_blocked` | 🚫 YouTube IP Blocked | Orange |
| `proxy_down` | 🔌 Proxy Down | Red |
| `pinecone_error` | 💾 Pinecone Error | Red |
| `uncaught_500` | 💥 Uncaught Server Error | Red |

**Files modified:** `src/errors.py`

---

## 38. Auth and admin login event logging

**Spec said:** No logging of authentication attempts.
**Actual:** All access key and admin login attempts are logged with IP address, including both successful and failed attempts.

**New event types:**

| Event | Type | Subtype | Detail |
|-------|------|---------|--------|
| Valid access key | `AUTH` | `success` | `tier=key` |
| Invalid access key | `AUTH` | `fail` | `invalid_key` |
| Admin login success | `ADMIN` | `success` | `admin_login` |
| Admin login fail | `ADMIN` | `fail` | `invalid_token` |
| Admin metrics unauthorized | `ADMIN` | `fail` | `invalid_token_metrics` |

**Files modified:** `api/routes/auth.py`, `api/routes/admin.py`

---

## 39. Admin brute force detection with escalating alerts

**Spec said:** No brute force detection.
**Actual:** Failed admin login attempts tracked per IP in a 30-minute sliding window. Discord alerts escalate every 3 attempts.

**Escalation:**

| Attempts | Severity | Color |
|----------|----------|-------|
| 3 | Minor (warning) | Yellow |
| 6 | Elevated | Orange |
| 9+ | Critical (every 3) | Red |

- Both `/admin/auth` and `/admin/metrics` endpoints count toward the same tracker
- Successful login clears the IP's failed attempt history
- Each severity level has its own Discord throttle

**Files modified:** `api/routes/admin.py`, `src/errors.py`

---

## Summary table

| # | File | Spec | Actual | Reason |
|---|------|------|--------|--------|
| 1 | `requirements.txt` | `pinecone-client` | `pinecone` | Package renamed upstream |
| 2 | `src/vectorstore.py` | Fix filter to `== "chunk"` | Left as `!= "metadata"` | Fix only applies to `src/tools.py` per spec |
| 3 | `scripts/extract.py` | Move imports to top | Fixed multi-line import handling | Extractor bug |
| 4 | `api/routes/ask.py` | Sync stream in async gen | Thread pool + asyncio.Queue | Blocked event loop |
| 5 | `api/routes/ask.py` | `stream_mode="updates"` | `stream_mode="messages"` | No token-level output with updates |
| 6 | `api/routes/ask.py` | `{"text": "..."}` | `{"token": "..."}` | Frontend expects `token` field |
| 7 | `koyeb.yaml` | Not in spec | Added | Required for Koyeb Docker builds |
| 8 | `.env.docker` | Not in spec | Added (gitignored) | Required for `docker run --env-file` |
| 9 | `scripts/docker_build.sh` | Not in spec | Added | Convenience script |
| 10 | `api/main.py` | Unconditional mount | Conditional mount | Prevents startup error |
| 11 | `src/metrics.py` | `/app/events.log` | Smart fallback to `events.log` locally | Prevents crash outside Docker |
| 12 | `api/utils.py` | Inline `get_client_ip()` | Shared utility module | Avoids cross-route imports |
| 13 | `src/tools.py`, `src/agent.py` | Plain timestamps | Markdown link timestamps | Timestamps now clickable in UI |
| 14 | `api/routes/ask.py` | All videos to agent | Only selected videos | Agent now respects selection state |
| 15 | Frontend (Lovable) | N/A | React 18 setState batching bug | PATCH always sent `true`; fixed in frontend |
| 16 | `src/tools.py`, `src/agent.py` | Only agent callback | Added `record_tokens()` to all 3 tool API calls | API cost was $0; bulk of tokens untracked |
| 17 | `api/routes/ask.py` | No tool cache logging | `log_event("TOOL", cache/api)` | Visibility into cache hits vs API calls |
| 18 | `api/routes/ask.py` | N/A | Removed `|` from log detail | Pipe split bug in `get_recent_events()` |
| 19 | `scripts/extract.py` | List-of-lines source only | Handle string source too | NotebookEdit writes strings, not lists |
| 20 | `api/main.py` | Default `HTTPException` handler | Custom handler strips `detail` wrapper | Frontend expects `{error, code}` at top level |
| 21 | `api/main.py` | Only serve `assets/` + `index.html` | Serve any file from `frontend/` root | Favicon, robots.txt etc. now accessible |
| 22 | `src/transcript.py`, `api/routes/videos.py` | 3 exception types only | Added `IpBlocked`, `RequestBlocked`, catch-all | Descriptive errors for all failure modes |
| 23 | `scripts/cloudflare-worker.js`, `scripts/gcf-transcript-proxy/` | Direct YouTube fetch only | Tried CF Worker, GCF proxy, yt-dlp — all blocked | YouTube blocks all datacenter IPs; resolved by #24 |
| 24 | `src/transcript.py` (notebook 01) | Direct `YouTubeTranscriptApi()` | `_get_transcript_api()` with Webshare proxy | Residential proxy bypasses YouTube IP blocks on cloud deployments |
| 25 | `scripts/extract.py` | Hoist all `import`/`from` lines | Only hoist non-indented imports | Indented imports (lazy/conditional) must stay in their function scope |
| 26 | `src/transcript.py` (notebook 01) | Single `IpBlocked` message | Proxy-aware error messages with retry hints | Distinguishes IP rotation (retry) vs proxy down (wait) |
| 27 | `src/errors.py` + 5 files | Discord alerts + `UserFacingError` + `safe_execute` | Throttled `send_discord_alert()` only, 6 alert sites | `UserFacingError` redundant (#20), `safe_execute` replaced by direct calls, 10-min throttling |
| 28 | `config/settings.py` | `APP_URL` constant defined | Not used in Python code | Alerts implemented without app links; kept for future use |
| 29 | `src/agent.py` (notebook 05) | `create_react_agent` from `langgraph.prebuilt` | `create_agent` from `langchain.agents` | Deprecated in LangGraph V1.0; `prompt=` renamed to `system_prompt=` |
| 30 | `api/routes/ask.py` | Tools could raise exceptions | All 5 tool wrappers catch exceptions, return error strings | Prevents cascade failure: dangling `tool_use` without `tool_result` broke sessions |
| 31 | `src/metrics.py`, `tests/conftest.py` | In-memory metrics + local file log | Supabase persistent logging with dual-write + startup restore | Container restarts lost all historical data |
| 32 | `config/settings.py` | 5 videos / 10 questions | 3 videos / 5 questions | Cost management during demo period |
| 33 | `api/routes/ask.py`, `api/routes/videos.py`, `api/session.py`, `src/metrics.py` | Basic event detail strings | Enriched with latency, tokens, tool, duration, session depth + parsed fields in API | Observability for performance and usage analytics |
| 34 | `api/routes/ask.py` | 6 Discord alert types | 7th alert: `slow_query` (>60s) | Detect queries where user likely gave up |
| 35 | `src/metrics.py`, `api/routes/admin.py` | Fixed $5 budget with single alert | Cycle-based: auto-detect $5 reloads, alert at 80% of each cycle, cumulative tracking | Budget reloads don't require config changes |
| 36 | `src/metrics.py`, `api/session.py`, `api/routes/ask.py`, `api/routes/videos.py`, `api/routes/admin.py` | No user identification | Anonymous tracking via localStorage UUID + Supabase `users` table | Cross-session user analytics without cookies |
| 37 | `src/errors.py` | Plain text Discord messages | Color-coded embeds with title, environment footer, timestamp + User-Agent fix | Visual clarity, fixes Discord blocking Python user agent |
| 38 | `api/routes/auth.py`, `api/routes/admin.py` | No auth logging | All login attempts logged (AUTH/ADMIN events) with IP and success/fail | Security audit trail |
| 39 | `api/routes/admin.py`, `src/errors.py` | No brute force detection | Escalating alerts at 3/6/9+ failed admin logins per IP in 30-min window | Intrusion detection |
