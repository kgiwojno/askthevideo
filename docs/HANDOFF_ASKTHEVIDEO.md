# AskTheVideo — Presentation & Commercial Materials Handoff

This document provides everything needed to build the final presentation and commercial materials for the AskTheVideo project. It covers architecture, development journey, technical challenges, what worked, what didn't, testing strategy, and key numbers.

---

## 1. What AskTheVideo Is

**One-liner:** Ask questions about YouTube videos using AI — get answers with exact timestamps you can click to jump to that moment.

**How it works:**
1. User pastes a YouTube URL
2. Backend fetches the transcript, chunks it into 2-minute windows, embeds the text, and stores vectors in Pinecone
3. User asks questions in natural language
4. An AI agent (LangGraph + Claude) decides which tool to use, retrieves relevant transcript excerpts, and answers with clickable timestamp links
5. Responses stream token-by-token via SSE for a real-time chat feel

**Stack:**
- **Frontend:** React (built with Lovable), served as static files from the same container
- **Backend:** FastAPI (Python 3.12)
- **AI:** Claude Sonnet 4.6 (Anthropic) via LangGraph agent
- **Vector DB:** Pinecone (serverless, cosine similarity, 1024-dim embeddings)
- **Embeddings:** Pinecone Inference API (`llama-text-embed-v2`)
- **Deployment:** Docker on Koyeb (auto-deploy on push to main)
- **Domain:** app.askthevideo.com

---

## 2. The 5 AI Tools

The agent has 5 tools and autonomously picks the right one based on the user's question:

| Tool | What it does | Claude needed? | Cached? |
|------|-------------|----------------|---------|
| **vector_search** | Finds relevant transcript excerpts and answers with timestamp citations | Yes | No (always fresh) |
| **summarize_video** | Full video summary with key points and timestamps | Yes | Yes (Pinecone) |
| **get_topics** | Extracts 8-12 main topics with timestamp ranges | Yes | Yes (Pinecone) |
| **compare_videos** | Compares what multiple videos say about a topic | Yes | No |
| **get_metadata** | Returns video title, channel, duration, etc. | No | N/A (direct lookup) |

**Caching strategy:** Summaries and topics are expensive (full transcript sent to Claude). Results are cached in Pinecone as sentinel-vector records. First call: ~22s + ~$0.14. Subsequent calls: ~0.6s + $0.00.

---

## 3. Development Journey (Phase 1 → Phase 2)

### Phase 1: Notebook Exploration (7 notebooks)

Built and validated everything in Jupyter notebooks before writing any production code:

1. **Notebook 01 — Transcript Fetch:** Explored `youtube-transcript-api`, tested edge cases (disabled captions, auto-generated, non-English, long videos), built `fetch_transcript()` and `extract_video_id()`
2. **Notebook 02 — Chunking:** Designed 2-minute sliding window with 3-snippet carry-over for context continuity. Tested on 3.5-min and 182-min videos
3. **Notebook 03 — Pinecone Operations:** Set up vector index, tested embedding + retrieval quality, designed sentinel-vector pattern for metadata/cache records
4. **Notebook 04 — Claude Tools:** Built and measured all 5 tools individually with real data, tracked token usage and cost per call
5. **Notebook 05 — Agent Routing:** Wired tools into LangGraph agent, tested routing accuracy (10/10), multi-turn conversation, and migrated from deprecated `create_react_agent` to `create_agent`
6. **Notebook 06 — Integration Flow:** Full end-to-end pipeline test: URL → transcript → chunks → embed → query → answer
7. **Notebook 07 — Evaluation:** Quality and performance evaluation of the complete system

### Phase 2: Production Build

Used a custom `scripts/extract.py` to extract production code from `# @export` tagged notebook cells. This kept notebooks as the single source of truth — any change goes through the notebook first, then regenerates `src/` files.

**What was built:**
- FastAPI backend with 11 API endpoints
- Session management (in-memory, 2-hour TTL)
- SSE streaming for real-time token delivery
- Docker containerization + Koyeb deployment
- Admin panel backend (metrics, events, session management)
- 51 unit tests + 15 end-to-end smoke tests
- Discord alerting for 7 critical error scenarios
- Supabase persistent logging with environment separation (local vs production)
- Access key authentication for unlimited usage

---

## 4. The YouTube IP Blocking Challenge

**The biggest technical challenge of the project.**

### The Problem

YouTube blocks transcript requests from cloud server IPs. When deployed to Koyeb, every video load failed with `IpBlocked`. This works perfectly on localhost but fails on any cloud provider.

### What We Tried (and Why It Failed)

#### Attempt 1: Cloudflare Worker Proxy
- **Idea:** Route transcript requests through a Cloudflare Worker using YouTube's internal Innertube API
- **Implementation:** Built a full Worker (`scripts/cloudflare-worker.js`) that used the Android Innertube client, parsed caption tracks, and fetched timed text
- **Result:** YouTube also blocks Cloudflare's IPs. The timedtext endpoint returns 0 bytes. Tried multiple Innertube clients (WEB, ANDROID, IOS, TVHTML5), the `get_transcript` endpoint, cookie forwarding, and various User-Agent strings
- **Key finding:** YouTube's blocking operates at multiple levels — player API, timedtext endpoint, and get_transcript API all enforce IP restrictions

#### Attempt 2: Google Cloud Function Proxy
- **Idea:** Google owns YouTube, so maybe GCF IPs aren't blocked
- **Implementation:** Built a Cloud Function (`scripts/gcf-transcript-proxy/main.py`) with the same Innertube approach
- **Result:** Code written and tested locally but pivoted before deploying — same timedtext endpoint would likely be blocked

#### Attempt 3: yt-dlp Fallback
- **Idea:** yt-dlp uses a different YouTube code path (player page parsing + subtitle URLs)
- **Implementation:** Added `yt-dlp` as a fallback in the transcript fetch chain
- **Result:** yt-dlp ultimately hits the same timedtext endpoint, so it's also blocked from datacenter IPs

#### Solution: Webshare Residential Proxy
- **What:** Route `youtube-transcript-api` requests through Webshare's rotating residential proxy network
- **Why it works:** Residential proxies use real ISP IP addresses (not datacenter IPs), which YouTube doesn't block
- **Implementation:** 10 lines of code — `GenericProxyConfig` with `http://{username}:{password}@p.webshare.io:80/`
- **Cost:** Webshare has a free tier with 10 rotating residential IPs
- **The `-rotate` suffix:** Adding `-rotate` to the username automatically assigns a new residential IP on each request, so if one IP gets temporarily flagged, the next request goes through a different one

**Lesson learned:** YouTube's IP blocking is comprehensive. No amount of API cleverness (different clients, endpoints, headers) bypasses it from datacenter IPs. The only reliable solution is residential IP addresses.

---

## 5. Key Technical Challenges Solved

### SSE Streaming (Deviations #4, #5, #6)

Three things went wrong with the spec's streaming approach:

1. **Blocked event loop:** `agent.stream()` is synchronous. Running it in an `async def` generator froze uvicorn — all tokens arrived at once after completion. **Fix:** Offloaded to a thread pool via `asyncio.to_thread()` + `asyncio.Queue`.

2. **Wrong stream mode:** `stream_mode="updates"` returns complete state per node, not per-token. **Fix:** Switched to `stream_mode="messages"` which yields `(chunk, metadata)` pairs at the token level.

3. **Wrong JSON field name:** Frontend expected `{"token": "..."}` but backend sent `{"text": "..."}`. Found by decompiling the minified React JS. **Fix:** Changed field name.

### Cost Tracking Showing $0 (Deviation #16)

The LangChain callback on the agent only tracked routing tokens (deciding which tool to call). The 3 direct Anthropic API calls in the tools — which do the actual heavy work — were untracked. Admin panel always showed $0. **Fix:** Added `record_tokens()` after every `client.messages.create()` call.

### React 18 Batching Bug (Deviation #15)

Video selection toggle always sent `selected=true` to the backend, regardless of user action. Root cause: React 18's automatic batching — the callback captured stale state. **Fix:** Applied in the frontend (Lovable).

### Tool Failure Cascade (Deviation #30)

A single tool error (e.g., Anthropic 429 rate limit) permanently broke the session. Root cause: MemorySaver recorded a `tool_use` message but no `tool_result` followed when the tool raised an exception. The Anthropic API rejects all subsequent messages with dangling `tool_use` blocks. **Fix:** All 5 tool wrappers in `api/routes/ask.py` catch exceptions and return error strings — tools never raise. Conversation context is fully preserved.

### Extract Script Bugs (Deviations #3, #19, #25)

The notebook-to-production extractor had three bugs:
1. Broke multi-line parenthesised imports (inserted code between `from X import (` and `)`)
2. Only handled list-of-lines format, not string format (NotebookEdit writes strings)
3. Hoisted indented imports out of function scope (e.g. `import yt_dlp` inside a fallback function)

---

## 6. Production Alerting

Discord webhook alerts for 7 critical scenarios, with 10-minute per-type throttling to prevent spam:

| Alert | Trigger | Why it matters |
|-------|---------|----------------|
| Anthropic API error | Credit exhaustion, rate limits, 500s | Stops all AI functionality |
| YouTube IP blocked | `IpBlocked`/`RequestBlocked` | Proxy may need attention |
| Proxy down | Connection timeout/refused | No videos can be loaded |
| Pinecone error | Embed, upsert, or query failures | Vector DB unavailable |
| Uncaught 500 | Any unhandled server error | Unknown bug in production |
| Budget threshold | 80% of current $5 budget cycle | Running out of API credits |
| Slow query | Query latency exceeds 60 seconds | User likely gave up waiting |

---

## 7. Cost Analysis

### Per-Tool Cost (measured on 182-minute podcast)

| Tool | Input tokens | Output tokens | Cost | Latency |
|------|-------------|---------------|------|---------|
| vector_search | ~8,700 | ~450 | $0.033 | ~14s |
| summarize_video (fresh) | ~43,500 | ~720 | $0.141 | ~22s |
| summarize_video (cached) | 0 | 0 | $0.000 | ~0.6s |
| get_topics (fresh) | ~43,500 | ~850 | $0.143 | ~23s |
| get_topics (cached) | 0 | 0 | $0.000 | ~0.6s |
| compare_videos (1 video) | ~8,900 | ~940 | $0.041 | ~26s |
| get_metadata | 0 | 0 | $0.000 | ~0.2s |

### Session Cost Estimate

A typical 5-question free tier session on a 60-minute video: **~$0.15-0.20**

On the 182-minute test video: **~$0.35** per free session

### Budget

$5 Anthropic credit budget supports **~25+ free sessions** on typical 60-min videos. Budget alert fires at 80% ($4.00).

### Pricing (Claude Sonnet 4.6)
- Input: $3 per million tokens
- Output: $15 per million tokens

---

## 8. Free Tier Limits

| Limit | Value |
|-------|-------|
| Videos per session | 3 |
| Questions per session | 5 |
| Max video duration | 60 minutes |
| Session TTL | 2 hours |

Access key authentication unlocks unlimited usage (no video/question caps, no duration limit).

---

## 9. Testing Strategy

### Unit Tests (51 tests, offline, < 2s)

| Test file | What it covers |
|-----------|---------------|
| `test_api.py` | All API endpoints — happy paths, error cases, session handling |
| `test_chunking.py` | Chunking logic — window sizes, carry-over, edge cases |
| `test_validation.py` | URL parsing (5 formats + invalid), question validation |
| `test_session.py` | Session creation, TTL expiration, limits |
| `test_metadata.py` | YouTube oEmbed metadata fetch |
| `test_metrics.py` | Token recording, metric snapshots |
| `test_admin.py` | Admin panel endpoints |

### Smoke Tests (15 scenarios, end-to-end)

Run against a live server (local or production). Tests the full flow including real YouTube API calls, Pinecone operations, and Claude responses:

1. Health check
2. Status without session
3. Invalid YouTube URL → 400
4. Load a real video (Rick Astley, ~30s)
5. Cache hit (same video, must respond < 5s)
6. List loaded videos
7. Ask without videos → 400
8. Ask a question (full response)
9. Ask via SSE streaming (token events + done event)
10. Question too long → 400
11. Auth with valid key → unlimited
12. Auth with invalid key → rejected
13. Chat history retrieval
14. Toggle video selection (PATCH)
15. Delete video

---

## 10. Architecture Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Notebooks as source of truth | `# @export` cells → `scripts/extract.py` → `src/` | Keeps exploration and production code in sync; prevents drift |
| Pinecone for caching | Sentinel-vector records in same namespace | No extra infrastructure; cache lives next to the data it's derived from |
| In-memory sessions | Dict with TTL cleanup | Simple, no database needed; sessions are ephemeral (2h) |
| Single container | FastAPI serves both API + React static files | One deployment unit; no CORS, no separate frontend hosting |
| LangGraph agent | `create_agent` with 5 tools | Agent decides which tool to use; supports multi-turn conversation |
| Residential proxy | Webshare via `GenericProxyConfig` | Only reliable way to bypass YouTube IP blocking from cloud |
| Persistent logging | Supabase (dual-write + startup restore) | Container restarts on Koyeb lose in-memory metrics; Supabase preserves historical data across deploys |
| Anonymous user tracking | `localStorage` UUID + `X-User-ID` header + Supabase `users` table | No cookies (no consent banner); tracks returning users, sessions/user, questions/user |

---

## 11. All 37 Documented Deviations from Original Spec

Every place where the actual build differs from the original spec is documented in `docs/DEVIATIONS.md`. Categories:

| Category | Count | Examples |
|----------|-------|---------|
| Package/dependency changes | 2 | `pinecone-client` → `pinecone`, `create_react_agent` → `create_agent` |
| Streaming fixes | 3 | Thread pool, stream mode, JSON field name |
| Frontend/UX fixes | 4 | Error format, static files, clickable timestamps, React batching bug |
| Infrastructure additions | 3 | `koyeb.yaml`, `.env.docker`, docker build script |
| Extract script bugs | 3 | Multi-line imports, string format, indented imports |
| YouTube IP blocking | 4 | 3 failed attempts + residential proxy solution |
| Error handling improvements | 3 | Proxy-aware messages, expanded exception types, tool cascade failure fix |
| Production operations | 7 | Cost tracking, tool cache logging, log format fix, event log path, Supabase persistent logging, enhanced observability, budget cycle tracking |
| Alerting & monitoring | 4 | Discord integration, unused APP_URL constant, slow query alert, color-coded embeds |
| Code organization | 2 | Shared utility module, video selection filtering |
| Configuration changes | 1 | Free tier limits reduced from 5/10 to 3/5 |
| User analytics | 1 | Anonymous user tracking via localStorage UUID + Supabase |

---

## 12. What Worked Well

- **Notebook-first development:** Validating everything in notebooks before production code prevented costly redesigns. Every tool was measured for cost, latency, and quality before any API code was written.
- **Pinecone caching pattern:** Sentinel-vector records for summaries/topics eliminated repeat API calls. Cache hit: 0.6s/$0 vs fresh: 22s/$0.14.
- **SSE streaming:** Once the three issues were resolved, token-by-token streaming provides an excellent UX — users see the response forming in real-time.
- **Extract script pipeline:** Despite 3 bugs found and fixed, the notebook → extract → production pipeline kept the codebase clean and the source of truth unambiguous.
- **Webshare residential proxy:** Simple, cheap, reliable. 10 lines of code solved a problem that 3 previous approaches couldn't.
- **Smoke tests:** 15 end-to-end scenarios catch real integration issues that unit tests miss (SSE parsing, session flow, actual YouTube API behavior).

## 13. What Didn't Work

- **Cloudflare Worker proxy:** YouTube blocks Cloudflare IPs just as aggressively as other cloud providers. The Innertube API approach was technically interesting but fundamentally flawed — the timedtext endpoint enforces IP restrictions regardless of the client type.
- **yt-dlp as fallback:** Different code path, same blocked endpoint. Datacenter IPs are datacenter IPs.
- **`stream_mode="updates"`:** The LangGraph documentation was misleading — "updates" doesn't mean "streaming updates", it means "one update per node completion." No token-level output.
- **Safe_execute wrapper pattern:** Wrapping every function call in a generic error handler loses context about what failed and why. Direct alert calls at each error site with specific `alert_type` values proved much more useful.
- **UserFacingError exception class:** Redundant with FastAPI's `HTTPException` which already carries status codes and structured error details. Added complexity without value.

---

## 14. Key Numbers for Slides

| Metric | Value |
|--------|-------|
| Lines of production Python code | ~1,750 (src/ + api/ + config/) |
| Jupyter notebook cells (Phase 1) | 7 notebooks |
| Unit tests | 51 |
| End-to-end smoke tests | 15 |
| API endpoints | 11 |
| AI tools | 5 |
| Deviations from spec | 37 (all documented) |
| YouTube IP blocking workarounds tried | 3 (all failed) |
| Final solution (Webshare proxy) | ~10 lines of code |
| Cost per 5-question session (60-min video) | ~$0.15-0.20 |
| Cached summary response time | ~0.6 seconds |
| Fresh summary response time | ~22 seconds |
| Vector search end-to-end latency (Pinecone) | ~675ms |
| Discord alert scenarios | 7 |
| Alert throttle window | 10 minutes per error type |

---

## 15. Environment Variables

| Variable | Purpose | Required? |
|----------|---------|-----------|
| `ANTHROPIC_API_KEY` | Claude AI access | Yes |
| `PINECONE_API_KEY` | Vector database | Yes |
| `PINECONE_INDEX_NAME` | Index name (default: `askthevideo`) | No |
| `WEBSHARE_USERNAME` | Residential proxy (cloud only) | Production |
| `WEBSHARE_PASSWORD` | Residential proxy (cloud only) | Production |
| `VALID_ACCESS_KEYS` | Comma-separated access keys | Yes |
| `ADMIN_TOKEN` | Admin panel access | Yes |
| `SUPABASE_URL` | Supabase REST API base URL | Optional |
| `SUPABASE_KEY` | Supabase publishable key (RLS-protected) | Optional |
| `APP_ENV` | Environment tag for logs (`production`, `local`) | Production |
| `INITIAL_COST_OFFSET` | Pre-Supabase cumulative spend in USD | Production |
| `INITIAL_INPUT_TOKENS` | Pre-Supabase cumulative input tokens | Production |
| `INITIAL_OUTPUT_TOKENS` | Pre-Supabase cumulative output tokens | Production |
| `DISCORD_WEBHOOK_URL` | Error alerting | Optional |
| `LANGSMITH_API_KEY` | LLM tracing | Optional |
| `LANGSMITH_TRACING` | Enable/disable tracing | Optional |
| `LANGSMITH_ENDPOINT` | LangSmith URL | Optional |
| `LANGSMITH_PROJECT` | LangSmith project name | Optional |

---

## 16. File Structure Reference

```
askthevideo/
├── src/                        # Core library (generated from notebooks)
│   ├── transcript.py           # YouTube transcript fetch + Webshare proxy
│   ├── chunking.py             # 2-min window chunking with carry-over
│   ├── vectorstore.py          # Pinecone embed/upsert/query
│   ├── tools.py                # 5 Claude tools
│   ├── agent.py                # LangGraph agent factory
│   ├── errors.py               # Discord alerting with throttling
│   ├── metrics.py              # Token tracking, cost, event logging, Supabase persistence
│   ├── metadata.py             # YouTube oEmbed metadata
│   ├── validation.py           # Input validation
│   └── auth.py                 # Access key validation
├── api/                        # FastAPI routing layer
│   ├── main.py                 # App entry + static serving + error handlers
│   ├── session.py              # In-memory session management
│   ├── dependencies.py         # Pinecone + Anthropic singletons
│   ├── utils.py                # Shared helpers (get_client_ip)
│   └── routes/
│       ├── videos.py           # POST/GET/DELETE/PATCH /api/videos
│       ├── ask.py              # POST /api/ask + /api/ask/stream (SSE)
│       ├── auth.py             # POST /api/auth
│       ├── status.py           # GET /api/status, /api/history
│       └── admin.py            # Admin panel endpoints
├── config/settings.py          # App constants
├── notebooks/                  # Phase 1 (source of truth for src/)
│   ├── 01_transcript_fetch.ipynb
│   ├── 02_chunking.ipynb
│   ├── 03_pinecone_operations.ipynb
│   ├── 04_claude_tools.ipynb
│   ├── 05_agent_routing.ipynb
│   ├── 06_integration_flow.ipynb
│   └── 07_evaluation.ipynb
├── tests/                      # 51 unit tests (conftest.py sets TESTING=1)
├── data/
│   └── test_transcripts.json   # Test fixture data
├── scripts/
│   ├── extract.py              # Notebook → src/ extractor
│   ├── smoke_test.py           # 15 e2e tests
│   ├── docker_build.sh         # Docker build helper
│   ├── cloudflare-worker.js    # [Reference] Failed CF Worker approach
│   └── gcf-transcript-proxy/   # [Reference] Failed GCF approach
├── frontend/                   # React build (from Lovable)
├── docs/
│   ├── DEVIATIONS.md           # 35 documented deviations
│   ├── HANDOFF_ASKTHEVIDEO.md  # This file
│   ├── API_ENDPOINTS.md        # Full API reference (11 endpoints)
│   ├── KNOWN_ISSUES.md         # Non-critical issues for future fix
│   ├── SUPABASE_SETUP.md       # Supabase setup: tables, RLS, maintenance
│   └── spec/                   # Original planning documents
│       ├── PROJECT_PLAN.md
│       ├── SYSTEM_DESIGN.md
│       ├── FASTAPI_BACKEND_SPEC.md
│       ├── ADMIN_PANEL_BACKEND_SPEC.md
│       ├── CLAUDE_CODE_HANDOFF.md
│       ├── COST_BREAKDOWN.md
│       └── SETUP_GUIDE.md
├── Dockerfile
├── Makefile
├── koyeb.yaml
├── requirements.txt
└── requirements-dev.txt        # Dev-only dependencies
```
