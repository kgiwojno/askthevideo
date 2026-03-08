# AskTheVideo

Ask questions about YouTube videos using AI. Load any video, then chat with it — get answers with timestamps.

**Stack:** FastAPI backend + React frontend (served from same container) + Pinecone vector store + Claude (Anthropic).

---

## Project structure

```
askthevideo/
├── src/                    # Core library modules (extracted from notebooks)
│   ├── transcript.py       # YouTube transcript fetching
│   ├── chunking.py         # Time-window chunking
│   ├── vectorstore.py      # Pinecone operations
│   ├── tools.py            # Claude tool implementations
│   ├── agent.py            # LangGraph agent factory
│   ├── metadata.py         # YouTube oEmbed metadata
│   ├── validation.py       # Input validation
│   ├── errors.py           # Error handling + Discord alerts
│   └── auth.py             # Access key validation
├── api/                    # FastAPI routing layer
│   ├── main.py             # App entry point + static file serving
│   ├── session.py          # In-memory session management
│   ├── dependencies.py     # Pinecone + Anthropic singletons
│   └── routes/
│       ├── videos.py       # POST/GET/DELETE/PATCH /api/videos
│       ├── ask.py          # POST /api/ask + /api/ask/stream (SSE)
│       ├── auth.py         # POST /api/auth
│       └── status.py       # GET /api/status, /api/history
├── config/
│   └── settings.py         # App constants (models, limits, TTLs)
├── notebooks/              # Phase 1 exploration (reference only)
├── tests/                  # Unit + integration tests
├── scripts/
│   └── extract.py          # Extracts production code from notebooks
├── frontend/               # React build output (served at /)
├── Dockerfile
├── Makefile
└── requirements.txt
```

---

## Local development

### Prerequisites

- Python 3.12
- `.env` file with all required keys (see Environment variables below)

### Setup

```bash
# Activate the existing venv
source .venv/bin/activate

# Install dependencies (if not already installed)
pip install -r requirements.txt
```

### Run the server

```bash
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

### Run tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

### Makefile targets

```bash
make extract   # Re-extract src/ code from notebooks
make format    # Format with black
make lint      # Lint with ruff
make test      # Run pytest
make all       # extract → format → lint → test
```

---

## Docker

### Build the image

```bash
docker build -t askthevideo .
```

### Add the React frontend before building (optional)

The `frontend/` directory is copied into the image. If you have a production React build, place it there before building:

```bash
# Copy your React build output
cp -r /path/to/react-build/* frontend/

# Then build
docker build -t askthevideo .
```

Without a React build, a placeholder page is served at `/`. The API always works at `/api/`.

### Run locally with Docker

Create a file called `.env.docker` with your environment variables (one per line, no `export`):

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

Then run:

```bash
docker run --env-file .env.docker -p 8000:8000 askthevideo
```

Check it's running:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### Tag and push to a registry (for deployment)

```bash
# Example: push to Docker Hub
docker tag askthevideo yourdockerhubuser/askthevideo:latest
docker push yourdockerhubuser/askthevideo:latest

# Example: push to GitHub Container Registry
docker tag askthevideo ghcr.io/yourorg/askthevideo:latest
docker push ghcr.io/yourorg/askthevideo:latest
```

---

## Deployment (Koyeb via GitHub)

**Important:** Koyeb defaults to buildpack auto-detection and ignores the `Dockerfile` unless told otherwise. The `koyeb.yaml` file in the repo root forces it to use Docker:

```yaml
build:
  builder: docker
  docker:
    dockerfile: Dockerfile
```

This file is already committed. Without it, Koyeb builds its own image via buildpack instead.

### Steps

1. **Connect the GitHub repo** in the Koyeb dashboard (New service → GitHub).

2. **Configure the service:**
   - Builder: Docker (enforced by `koyeb.yaml`)
   - Port: `8000`
   - Health check: HTTP GET `/health`

3. **Set environment variables** in the Koyeb dashboard — copy all keys from your `.env` file.

4. **Assign the domain** `app.askthevideo.com` in Koyeb's domain settings.

5. **Deploy** — every push to `main` triggers a rebuild automatically.

The container serves the React app at `/` and the API at `/api/`.

---

## API endpoints

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

Session ID is passed via `X-Session-ID` header. First request omits it; the response includes a `session_id` to use on subsequent requests.

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `PINECONE_API_KEY` | Pinecone API key |
| `PINECONE_INDEX_NAME` | Pinecone index name (default: `askthevideo`) |
| `LANGSMITH_API_KEY` | LangSmith tracing key |
| `LANGSMITH_TRACING` | Enable tracing (`true`/`false`) |
| `LANGSMITH_ENDPOINT` | LangSmith endpoint URL |
| `LANGSMITH_PROJECT` | LangSmith project name |
| `DISCORD_WEBHOOK_URL` | Discord webhook for error alerts (optional) |
| `ADMIN_TOKEN` | Admin token |
| `VALID_ACCESS_KEYS` | Comma-separated list of valid access keys |

---

## Free tier limits (per session)

| Limit | Value |
|-------|-------|
| Videos | 5 |
| Questions | 10 |
| Max video duration | 60 minutes |
| Session TTL | 2 hours |

Limits are lifted when a valid access key is submitted to `POST /api/auth`.
