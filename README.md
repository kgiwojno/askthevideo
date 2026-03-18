# AskTheVideo

**Author:** Krzysztof Giwojno

Ask questions about YouTube videos using AI. Load any video, then chat with it — get answers with timestamps.

**Stack:** FastAPI backend + React frontend (served from same container) + Pinecone vector store + Claude (Anthropic).

---

## Related Repositories

| Repository | Description |
|------------|-------------|
| **[askthevideo](https://github.com/kgiwojno/askthevideo)** | Backend + API (this repo) |
| **[askthevideo-frontend](https://github.com/kgiwojno/askthevideo-frontend)** | React frontend |
| **[askthevideo-landing-page](https://github.com/kgiwojno/askthevideo-landing-page)** | Landing page |

---

## Project Structure

```
askthevideo/
├── src/                        # Core library (generated from notebooks)
│   ├── transcript.py           # YouTube transcript fetch + Webshare proxy
│   ├── chunking.py             # 2-min window chunking with carry-over
│   ├── vectorstore.py          # Pinecone embed/upsert/query
│   ├── tools.py                # 5 Claude tools
│   ├── agent.py                # LangGraph agent factory
│   ├── metrics.py              # Token tracking, cost, event logging, Supabase persistence
│   ├── errors.py               # Discord alerting with throttling
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
│       ├── admin.py            # POST /api/admin/auth + GET /api/admin/metrics
│       └── status.py           # GET /api/status, /api/history
├── config/
│   └── settings.py             # App constants (models, limits, TTLs)
├── notebooks/                  # Phase 1 exploration (source of truth for src/)
│   ├── 01_transcript_fetch.ipynb
│   ├── 02_chunking.ipynb
│   ├── 03_pinecone_operations.ipynb
│   ├── 04_claude_tools.ipynb
│   ├── 05_agent_routing.ipynb
│   ├── 06_integration_flow.ipynb
│   └── 07_evaluation.ipynb
├── tests/                      # 51 unit tests
├── data/
│   └── test_transcripts.json   # Test fixture data
├── scripts/
│   ├── extract.py              # Notebook → src/ extractor
│   ├── smoke_test.py           # 15 e2e tests
│   ├── docker_build.sh         # Docker build helper
│   ├── cloudflare-worker.js    # [Reference] Failed CF Worker approach
│   └── gcf-transcript-proxy/   # [Reference] Failed GCF approach
├── frontend/                   # React build (from Lovable)
├── docs/                       # Project documentation
│   ├── HANDOFF_ASKTHEVIDEO.md  # Master handoff document
│   ├── API_ENDPOINTS.md        # Full API reference
│   ├── DEVIATIONS.md           # 42 spec deviations documented
│   ├── KNOWN_ISSUES.md         # Non-critical issues for future fix
│   ├── BUG_CASCADE_FAILURE.md  # Tool failure cascade analysis
│   ├── SUPABASE_SETUP.md       # Supabase setup guide
│   └── spec/                   # Original planning documents (pre-build)
├── Dockerfile
├── Makefile
├── koyeb.yaml
├── requirements.txt
├── requirements-dev.txt
├── .env.example              # Template for local .env
├── .env.docker.example       # Template for docker .env
└── LICENSE
```

---

## Local Development

### Prerequisites

- Python 3.12
- `.env` file with required keys (see Environment Variables below)

### Setup and Run

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

### Tests

```bash
# Unit tests (fast, offline — no API keys needed)
pytest tests/ -v

# Smoke tests (requires a running server)
python scripts/smoke_test.py http://localhost:8000

# Against production
python scripts/smoke_test.py https://app.askthevideo.com
```

### Makefile Targets

```bash
make extract   # Re-extract src/ code from notebooks
make format    # Format with black
make lint      # Lint with ruff
make test      # Run pytest
make all       # extract → format → lint → test
```

---

## Docker

### Build and Run

```bash
# Generate plain env file (no `export` prefix)
sed 's/^export //' .env > .env.docker

# Build
./scripts/docker_build.sh

# Run
docker run --env-file .env.docker -p 8000:8000 askthevideo:latest

# Verify
curl http://localhost:8000/health
# {"status": "ok"}
```

### Frontend

The `frontend/` directory is copied into the image. Drop in a production React build before building:

```bash
cp -r /path/to/react-build/* frontend/
./scripts/docker_build.sh
```

Without a React build, a placeholder page is served at `/`. The API always works at `/api/`.

---

## Deployment (Koyeb)

The `koyeb.yaml` in the repo root forces Koyeb to use Docker (instead of buildpack auto-detection):

```yaml
build:
  builder: docker
  docker:
    dockerfile: Dockerfile
```

### Steps

1. **Connect the GitHub repo** in the Koyeb dashboard
2. **Configure:** Port `8000`, health check HTTP GET `/health`
3. **Set environment variables** from your `.env` file
4. **Assign domain** `app.askthevideo.com`
5. **Deploy** — every push to `main` triggers a rebuild

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/status` | Session status + limits |
| `GET` | `/api/history` | Chat history |
| `POST` | `/api/videos` | Load a YouTube video |
| `GET` | `/api/videos` | List loaded videos |
| `DELETE` | `/api/videos/{id}` | Remove video from session |
| `PATCH` | `/api/videos/{id}` | Toggle video selection |
| `POST` | `/api/ask` | Ask a question (full response) |
| `POST` | `/api/ask/stream` | Ask a question (SSE streaming) |
| `POST` | `/api/auth` | Validate access key |
| `POST` | `/api/admin/auth` | Admin panel authentication |
| `GET` | `/api/admin/metrics` | Admin metrics + events |

Session ID is passed via `X-Session-ID` header. First request omits it; the response includes a `session_id` to use on subsequent requests.

Full API reference: [docs/API_ENDPOINTS.md](docs/API_ENDPOINTS.md)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `PINECONE_API_KEY` | Yes | Pinecone API key |
| `PINECONE_INDEX_NAME` | No | Index name (default: `askthevideo`) |
| `VALID_ACCESS_KEYS` | Yes | Comma-separated access keys |
| `ADMIN_TOKEN` | Yes | Admin panel access token |
| `WEBSHARE_USERNAME` | Production | Residential proxy username |
| `WEBSHARE_PASSWORD` | Production | Residential proxy password |
| `SUPABASE_URL` | No | Supabase REST API base URL |
| `SUPABASE_KEY` | No | Supabase publishable key (RLS-protected) |
| `APP_ENV` | Production | Environment tag (`production` or `local`) |
| `INITIAL_COST_OFFSET` | No | Pre-Supabase cumulative spend in USD |
| `INITIAL_INPUT_TOKENS` | No | Pre-Supabase cumulative input tokens |
| `INITIAL_OUTPUT_TOKENS` | No | Pre-Supabase cumulative output tokens |
| `DISCORD_WEBHOOK_URL` | No | Discord webhook for error alerts |
| `LANGSMITH_API_KEY` | No | LangSmith tracing key |
| `LANGSMITH_TRACING` | No | Enable tracing (`true`/`false`) |
| `LANGSMITH_ENDPOINT` | No | LangSmith endpoint URL |
| `LANGSMITH_PROJECT` | No | LangSmith project name |

---

## Free Tier Limits (per session)

| Limit | Value |
|-------|-------|
| Videos | 3 |
| Questions | 5 |
| Max video duration | 60 minutes |
| Session TTL | 2 hours |

Access key authentication unlocks unlimited usage.

---

## AI Assistance

This project was built with assistance from AI development tools:

- **Claude** (Anthropic) — code generation, debugging,
  and documentation cleanup via Claude Code and claude.ai
- **Lovable** — application scaffolding and UI development

All architectural decisions, feature design, and final implementation
reflect the author's judgment. All code has been reviewed and tested.

---

## License

MIT License © 2026 Krzysztof Giwojno — see [LICENSE](LICENSE) for details.
