# AskTheVideo — API Endpoint Reference

11 endpoints + 1 health check. All API routes are prefixed with `/api`.

**Session management:** Pass `X-Session-ID` header (UUID) to create/retrieve sessions. Auto-creates if missing. Sessions expire after 2 hours.

**Error format:** All errors return `{"error": "message", "code": "CODE"}` at top level.

---

## Health Check

### `GET /health`

Basic health check for load balancers. Not under `/api` prefix.

**Response (200):**
```json
{"status": "ok"}
```

---

## Status & History

### `GET /api/status`

Check API availability and current session status.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Response (200) — no session:**
```json
{"status": "ok", "app": "AskTheVideo"}
```

**Response (200) — with session:**
```json
{
  "session_id": "uuid",
  "status": "ok",
  "limits": {
    "videos_loaded": 0,
    "videos_max": 5,
    "questions_used": 0,
    "questions_max": 10,
    "unlimited": false
  }
}
```

---

### `GET /api/history`

Retrieve chat history for current session.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | Yes | Session UUID |

**Response (200):**
```json
{
  "session_id": "uuid",
  "messages": [
    {"role": "user", "content": "question text"},
    {"role": "assistant", "content": "answer text"}
  ]
}
```

---

## Video Management

### `POST /api/videos`

Add a YouTube video to the session. Fetches transcript, chunks it, embeds in Pinecone.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Request body:**
```json
{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
```

**Response (200):**
```json
{
  "session_id": "uuid",
  "video": {
    "video_id": "dQw4w9WgXcQ",
    "title": "Video Title",
    "channel": "Channel Name",
    "duration_display": "4:33",
    "thumbnail_url": "https://...",
    "chunk_count": 42,
    "status": "ingested",
    "selected": true
  },
  "limits": {...}
}
```

`status` is `"ingested"` (first time) or `"cached"` (already in Pinecone).

**Error codes:**

| Status | Code | When |
|--------|------|------|
| 400 | `INVALID_URL` | Not a valid YouTube URL |
| 400 | `NO_TRANSCRIPT` | Video has captions disabled |
| 400 | `VIDEO_UNAVAILABLE` | Video deleted, private, or geo-blocked |
| 400 | `TRANSCRIPT_ERROR` | Other transcript fetch error |
| 403 | `VIDEO_LIMIT` | Free tier: 3 videos per session |
| 403 | `DURATION_EXCEEDED` | Free tier: video exceeds 60 minutes |
| 503 | `IP_BLOCKED` | YouTube blocking server IP |

---

### `GET /api/videos`

List all videos in the current session.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Response (200):**
```json
{
  "session_id": "uuid",
  "videos": [{...video objects...}],
  "limits": {...}
}
```

---

### `DELETE /api/videos/{video_id}`

Remove a video from the session. Does not delete from Pinecone.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Response (200):**
```json
{
  "session_id": "uuid",
  "removed": "dQw4w9WgXcQ",
  "limits": {...}
}
```

| Status | Code | When |
|--------|------|------|
| 404 | `NOT_FOUND` | Video not in session |

---

### `PATCH /api/videos/{video_id}`

Toggle whether a video is included in queries. Triggers agent rebuild.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Request body:**
```json
{"selected": true}
```

**Response (200):**
```json
{
  "session_id": "uuid",
  "video_id": "dQw4w9WgXcQ",
  "selected": true
}
```

| Status | Code | When |
|--------|------|------|
| 404 | `NOT_FOUND` | Video not in session |

---

## Authentication

### `POST /api/auth`

Validate an access key to unlock unlimited usage (no video/question caps, no duration limit).

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Request body:**
```json
{"key": "access_key_string"}
```

**Response (200) — valid key:**
```json
{
  "session_id": "uuid",
  "valid": true,
  "limits": {
    "videos_loaded": 0,
    "videos_max": null,
    "questions_used": 0,
    "questions_max": null,
    "unlimited": true
  }
}
```

**Response (200) — invalid key:**
```json
{
  "session_id": "uuid",
  "valid": false
}
```

---

## Question Answering

### `POST /api/ask`

Synchronous question answering. The agent picks the right tool, executes it, and returns the full answer.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Request body:**
```json
{"question": "What is the main topic discussed?"}
```

**Response (200):**
```json
{
  "session_id": "uuid",
  "answer": "The video discusses...",
  "tool_used": "vector_search",
  "limits": {...}
}
```

`tool_used` is one of: `vector_search`, `summarize_video`, `list_topics`, `compare_videos`, `get_metadata`, or `null`.

**Error codes:**

| Status | Code | When |
|--------|------|------|
| 400 | `NO_VIDEOS` | No videos loaded in session |
| 400 | `QUESTION_TOO_LONG` | Question exceeds length limit |
| 403 | `QUESTION_LIMIT` | Free tier: 5 questions per session |

---

### `POST /api/ask/stream`

Streaming question answering via SSE. Same logic as `/api/ask` but returns tokens in real-time.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Session-ID` | No | Session UUID |

**Request body:**
```json
{"question": "What is the main topic discussed?"}
```

**SSE response** (each line is `data: <json>`):
```
data: {"tool_used": "vector_search"}
data: {"token": "The "}
data: {"token": "video "}
data: {"token": "discusses"}
...
data: {"limits": {...}}
```

**Event types:**
- `{"tool_used": "..."}` — emitted once when agent picks a tool
- `{"token": "..."}` — emitted per token (real-time streaming)
- `{"limits": {...}}` — emitted at end of stream
- `{"error": "...", "code": "..."}` — on failure

**Error codes:** Same as `/api/ask`.

**Implementation notes:**
- Uses `asyncio.to_thread()` + `asyncio.Queue` (agent.stream is sync)
- `stream_mode="messages"` for per-token output
- Frontend reads `data:` lines, parses JSON, checks for `.token` field

---

## Admin

### `POST /api/admin/auth`

Validate admin token for dashboard access.

**Request body:**
```json
{"token": "admin_secret"}
```

**Response (200):**
```json
{"valid": true}
```

Token is compared against `ADMIN_TOKEN` environment variable.

---

### `GET /api/admin/metrics`

Dashboard metrics: system stats, session counts, cost tracking, Pinecone stats, recent events.

| Header | Required | Description |
|--------|----------|-------------|
| `X-Admin-Token` | Yes | Admin token |

**Response (200):**
```json
{
  "realtime": {
    "active_sessions": 12,
    "ram_mb": 256.1,
    "cpu_percent": 23.4,
    "uptime_hours": 48.2
  },
  "sessions": {
    "total_queries": 342,
    "total_videos_loaded": 89,
    "total_videos_cached": 45,
    "key_queries": 45,
    "error_count": 3,
    "alert_count": 1
  },
  "cost": {
    "total_input_tokens": 1234567,
    "total_output_tokens": 567890,
    "estimated_cost": 12.34,
    "budget_total": 5.00,
    "budget_remaining": -7.34
  },
  "pinecone": {
    "cached_videos": 42,
    "total_vectors": 8456,
    "index_fullness_percent": 8.5
  },
  "events": [
    {"timestamp": "...", "type": "QUERY", "subtype": "free", "ip": "...", "detail": "..."}
  ],
  "last_updated": "2025-03-10T14:24:12"
}
```

| Status | Code | When |
|--------|------|------|
| 403 | `INVALID_TOKEN` | Missing or wrong `X-Admin-Token` header |

---

## Free Tier Limits

| Limit | Value | Unlocked with access key |
|-------|-------|--------------------------|
| Videos per session | 3 | Unlimited |
| Questions per session | 5 | Unlimited |
| Max video duration | 60 minutes | Unlimited |
| Session TTL | 2 hours | 2 hours |

---

## Video Selection Logic

- **Default:** All loaded videos are queried if none explicitly selected
- **Selective:** If any video has `selected=true`, only those are searched
- **Agent rebuild:** Changing selection triggers a new agent instance with updated system prompt

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes | Claude AI access |
| `PINECONE_API_KEY` | Yes | Vector database |
| `PINECONE_INDEX_NAME` | No | Index name (default: `askthevideo`) |
| `VALID_ACCESS_KEYS` | Yes | Comma-separated access keys |
| `ADMIN_TOKEN` | Yes | Admin panel access |
| `WEBSHARE_USERNAME` | Production | Residential proxy username |
| `WEBSHARE_PASSWORD` | Production | Residential proxy password |
| `DISCORD_WEBHOOK_URL` | No | Error alerting webhook |
| `LANGSMITH_API_KEY` | No | LLM tracing |
| `LANGSMITH_TRACING` | No | Enable/disable tracing |
| `LANGSMITH_ENDPOINT` | No | LangSmith URL (EU: `https://eu.api.smith.langchain.com`) |
| `LANGSMITH_PROJECT` | No | LangSmith project name |
