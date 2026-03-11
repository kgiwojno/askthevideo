# AskTheVideo — Development Setup Guide

Complete setup instructions for local development. Covers macOS and Windows.

---

## Prerequisites

| Tool | Version | Mac | Windows |
|---|---|---|---|
| Python | 3.12 | `brew install python@3.12` | [python.org](https://www.python.org/downloads/) — check "Add to PATH" |
| Git | latest | `brew install git` | [git-scm.com](https://git-scm.com/download/win) |
| Docker | latest | [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/) | [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/) |
| VS Code | latest | [code.visualstudio.com](https://code.visualstudio.com/) | [code.visualstudio.com](https://code.visualstudio.com/) |

### VS Code Extensions (recommended)

- Python (Microsoft)
- Jupyter (Microsoft)
- Python Environment Manager
- GitLens

### Verify prerequisites

```bash
python --version    # 3.12
git --version
docker --version
```

On Windows, use PowerShell or Git Bash. Commands below use bash syntax — adapt if using CMD.

---

## 1. Clone the Repository

```bash
git clone https://github.com/<your-username>/askthevideo.git
cd askthevideo
```

---

## 2. Create Virtual Environment

The `--prompt` flag sets the display name in your terminal to `(askthevideo)` instead of the default `(.venv)`.

**macOS:**
```bash
python3 -m venv .venv --prompt askthevideo
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv --prompt askthevideo
.venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**
```bash
python -m venv .venv --prompt askthevideo
source .venv/Scripts/activate
```

**Windows (CMD):**
```cmd
python -m venv .venv --prompt askthevideo
.venv\Scripts\activate.bat
```

Verify activation — your terminal prompt should show `(askthevideo)`.

---

## 3. Install Dependencies

```bash
# Development (includes production deps + dev tools)
pip install -r requirements-dev.txt

# Production only (for Docker / deployment)
pip install -r requirements.txt
```

### Troubleshooting: pip install failures

**macOS — SSL certificate errors:**
```bash
# Install certificates for Python
/Applications/Python\ 3.12/Install\ Certificates.command
```

**Windows — long path errors:**
```powershell
# Run PowerShell as Administrator
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

**Both — pip version:**
```bash
pip install --upgrade pip
```

---

## 4. Environment Variables

Copy the template and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```
ANTHROPIC_API_KEY=sk-ant-...
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=askthevideo
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com  # Required for EU-hosted accounts
LANGSMITH_PROJECT=askthevideo
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ADMIN_TOKEN=<choose-a-secret-token>
VALID_ACCESS_KEYS=<your-access-key>
```

### Where to get API keys

| Service | URL | Free tier |
|---|---|---|
| Anthropic | [console.anthropic.com](https://console.anthropic.com/) | $5 free credit on signup |
| Pinecone | [app.pinecone.io](https://app.pinecone.io/) | 1 free index (2GB, 100K vectors) |
| LangSmith | [smith.langchain.com](https://smith.langchain.com/) | Free for personal use |
| Discord Webhook | Server Settings → Integrations → Webhooks | Free |

**IMPORTANT:** Never commit `.env` to git. It's already in `.gitignore`.

---

## 5. Validate API Access

Run these checks before starting development. Each should complete without errors.

### Anthropic API

```python
# Run in Python REPL or a test notebook
from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic
client = Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=100,
    messages=[{"role": "user", "content": "Say 'API working' and nothing else."}]
)
print(response.content[0].text)
print(f"Input tokens: {response.usage.input_tokens}")
print(f"Output tokens: {response.usage.output_tokens}")
```

Expected: prints "API working" and token counts.

### Pinecone

```python
from dotenv import load_dotenv
load_dotenv()

import os
from pinecone import Pinecone

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# List existing indexes
print("Existing indexes:", pc.list_indexes().names())

# Create index if it doesn't exist
index_name = os.getenv("PINECONE_INDEX_NAME", "askthevideo")
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=1024,          # llama-text-embed-v2 dimension
        metric="cosine",
        spec={"serverless": {"cloud": "aws", "region": "us-east-1"}}
    )
    print(f"Created index: {index_name}")
else:
    print(f"Index already exists: {index_name}")

# Connect and check stats
index = pc.Index(index_name)
print("Index stats:", index.describe_index_stats())
```

Expected: prints index stats (0 vectors if new).

### youtube-transcript-api

```python
from youtube_transcript_api import YouTubeTranscriptApi

# Known video with English transcript
ytt_api = YouTubeTranscriptApi()
transcript = ytt_api.fetch("dQw4w9WgXcQ")
print(f"Segments: {len(transcript.snippets)}")
print(f"First: {transcript.snippets[0]}")
print(f"Language: {transcript.language}")
print(f"Auto-generated: {transcript.is_generated}")
```

Expected: prints segment count, first snippet (with `.text`, `.start`, `.duration`), language, and whether auto-generated.

### LangSmith

```python
from dotenv import load_dotenv
load_dotenv()

import os
print(f"LANGSMITH_TRACING: {os.getenv('LANGSMITH_TRACING')}")
print(f"LANGSMITH_PROJECT: {os.getenv('LANGSMITH_PROJECT')}")

# Make a traced call
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-sonnet-4-20250514")
response = llm.invoke("Say 'LangSmith tracing working' and nothing else.")
print(response.content)
print("Check https://smith.langchain.com for the trace.")
```

Expected: prints response and a trace appears in LangSmith dashboard.

---

## 6. Project Structure

After setup, your project should look like this:

```
askthevideo/
├── .env                    # Your API keys (NOT committed)
├── .env.example            # Template (committed)
├── .gitignore
├── .venv/                  # Virtual environment (NOT committed)
├── README.md
├── Makefile
├── requirements.txt        # Production deps
├── requirements-dev.txt    # Dev deps (includes production)
├── .streamlit/
│   └── config.toml
├── src/                    # Production code (extracted from notebooks)
│   └── __init__.py
├── notebooks/              # Development notebooks
├── scripts/
│   └── extract.py          # Notebook → src/ extraction
├── tests/
├── config/
│   └── settings.py
├── landing/
│   └── assets/
├── docs/
└── extras/
```

---

## 7. Jupyter Setup

Register the virtual environment as a Jupyter kernel (uses the Python 3.12 from your venv):

```bash
pip install ipykernel
python -m ipykernel install --user --name=askthevideo --display-name="AskTheVideo (Python 3.12)"
```

When opening notebooks, select the "AskTheVideo (Python 3.12)" kernel.

### VS Code Jupyter

1. Open a `.ipynb` file
2. Click "Select Kernel" (top right)
3. Choose "AskTheVideo (Python 3.12)" from the list

---

## 8. Running the App Locally

### Streamlit (during/after development)

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`

### Docker (testing deployment)

```bash
docker build -t askthevideo .
docker run -p 8501:8501 --env-file .env askthevideo
```

Opens at `http://localhost:8501`

---

## 9. Common Issues

### macOS

| Issue | Fix |
|---|---|
| `zsh: command not found: python` | Use `python3` instead, or `brew install python@3.11` |
| Port 8501 already in use | `lsof -i :8501` then `kill <PID>` |
| Docker not running | Open Docker Desktop app first |
| SSL errors with pip | Run Install Certificates command (see section 3) |

### Windows

| Issue | Fix |
|---|---|
| `python` not found | Reinstall Python, check "Add to PATH" |
| Execution policy blocks .ps1 | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| Port 8501 already in use | `netstat -ano | findstr 8501` then `taskkill /PID <PID> /F` |
| Docker not starting | Enable WSL 2: `wsl --install` in admin PowerShell |
| Line ending issues | `git config --global core.autocrlf true` |

### Both platforms

| Issue | Fix |
|---|---|
| `ModuleNotFoundError` | Check you're in the `.venv`: `which python` (Mac) / `where python` (Win) |
| `.env` not loading | Ensure `load_dotenv()` is called before accessing env vars |
| Pinecone timeout | Check region matches (us-east-1), retry after 30s |
| Anthropic 401 | Verify API key starts with `sk-ant-` |
| LangSmith traces not appearing | Confirm `LANGSMITH_TRACING=true` (not `True` or `1`) |

---

## 10. Development Workflow

1. **Activate environment** every session:
   - Mac: `source .venv/bin/activate`
   - Windows: `.venv\Scripts\Activate.ps1`

2. **Work in notebooks** (01-06): explore, validate, tag production cells with `# @export`

3. **Extract to production files:** `make all` (runs extract → format → lint → test)

4. **Test locally:** `streamlit run app.py`

5. **Deploy:** push to GitHub → Koyeb auto-deploys

See `BUILD_ORDER.md` for the full development plan.

---

*Setup guide for AskTheVideo — IronHack AI Engineering Bootcamp capstone project.*
