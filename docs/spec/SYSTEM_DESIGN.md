# System Design — AskTheVideo

## Overall Architecture

```
                              USER
                               │
                ┌──────────────┴──────────────┐
                ▼                              ▼
┌───────────────────────────┐  ┌───────────────────────────────┐
│  LANDING PAGE             │  │  APP                          │
│  yourdomain.com           │  │  app.yourdomain.com           │
│                           │  │                               │
│  Static HTML/CSS/JS       │  │  Streamlit (Python)           │
│  Hosted on OVH*           │  │  Hosted on Koyeb (Docker)     │
│                           │  │                               │
│  - Hero + CTA             │  │  - Chat UI                    │
│  - How it works            │  │  - Video ingestion            │
│  - Features               │  │  - LangGraph Agent            │
│  - Cost / Limitations     │  │  - Question/video limits      │
│  - BMC / Support          │  │  - Access key validation      │
│  - About project + author │  │                               │
│  - FAQ                    │  │          │         │          │
│                           │  │    (1) Add video   (2) Ask    │
│  [Try the App →] ─────────┼──┼──→      ▼         ▼          │
│                           │  │  ┌─────────┐ ┌──────────┐    │
│                           │  │  │Ingestion│ │Query     │    │
│                           │  │  │Pipeline │ │Pipeline  │    │
│                           │  │  └────┬────┘ └────┬─────┘    │
│                           │  │       │           │          │
│                           │  └───────┼───────────┼──────────┘
│                           │          │           │
└───────────────────────────┘          ▼           ▼
                            ┌──────────────────────────────────┐
                            │       EXTERNAL SERVICES          │
                            │                                  │
                            │  ┌───────────┐  ┌────────────┐  │
                            │  │ YouTube   │  │ Pinecone   │  │
                            │  │ transcript│  │ vectors +  │  │
                            │  │ API       │  │ embeddings │  │
                            │  │ FREE      │  │ FREE TIER  │  │
                            │  └───────────┘  └────────────┘  │
                            │                                  │
                            │  ┌───────────┐  ┌────────────┐  │
                            │  │ Anthropic │  │ LangSmith  │  │
                            │  │ Claude    │  │ tracing +  │  │
                            │  │ Sonnet 4.6│  │ eval       │  │
                            │  │ PAY/USE   │  │ FREE TIER  │  │
                            │  └───────────┘  └────────────┘  │
                            │                                  │
                            │  ┌───────────┐                   │
                            │  │ Google    │                   │
                            │  │ Analytics │                   │
                            │  │ FREE      │                   │
                            │  └───────────┘                   │
                            └──────────────────────────────────┘

* Landing page is static files — can be hosted anywhere
  (OVH, GitHub Pages, Netlify, etc.)
```

---

## App Detail — Streamlit (Koyeb)

```
┌──────────────────────────────────────────────────────────────────┐
│                        STREAMLIT UI (Koyeb)                      │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │ Sidebar   │  │ Chat Window  │  │ Video Library              │ │
│  │ - URL     │  │ - Messages   │  │ - Loaded videos list       │ │
│  │   input   │  │ - Citations  │  │ - Status per video         │ │
│  │ - Secret  │  │ - Timestamp  │  │ - Delete button            │ │
│  │   key     │  │   links      │  │                            │ │
│  │ - Links   │  │              │  │                            │ │
│  │   (BMC,   │  │              │  │                            │ │
│  │   feedback,│  │              │  │                            │ │
│  │   etc.)   │  │              │  │                            │ │
│  └──────────┘  └──────────────┘  └────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
        │                    │
        │ (1) Add video      │ (2) Ask question
        ▼                    ▼
┌─────────────────┐  ┌─────────────────────────────────────────────┐
│ INGESTION       │  │ QUERY PIPELINE                              │
│ PIPELINE        │  │                                             │
│                 │  │  User question                              │
│ YouTube URL     │  │       ↓                                     │
│     ↓           │  │  [LangGraph Agent] ──→ selects tool         │
│ [yt-transcript] │  │       ↓                                     │
│     ↓           │  │  ┌─────────────────────────────────┐        │
│ Raw transcript  │  │  │ TOOLS                           │        │
│ + timestamps    │  │  │                                 │        │
│     ↓           │  │  │ 1. vector_search(query)         │        │
│ [Time-based     │  │  │    → Pinecone similarity search │        │
│  chunking]      │  │  │    → returns chunks + metadata  │        │
│     ↓           │  │  │                                 │        │
│ Chunks with     │  │  │ 2. summarize_video(video_id)    │        │
│ metadata        │  │  │    → fetch all chunks for video │        │
│     ↓           │  │  │    → Claude summarizes          │        │
│ [Pinecone       │  │  │                                 │        │
│  Inference]     │  │  │ 3. list_topics(video_id)        │        │
│     ↓           │  │  │    → fetch all chunks for video │        │
│ Embeddings      │  │  │    → Claude extracts topics     │        │
│     ↓           │  │  │                                 │        │
│ [Pinecone DB]   │  │  │ 4. compare_videos(query,        │        │
│ namespace:      │  │  │    video_ids)                   │        │
│ video_id        │  │  │    → search across namespaces   │        │
│                 │  │  │    → Claude compares             │        │
│                 │  │  │                                 │        │
│                 │  │  │ 5. get_metadata(video_id)       │        │
│                 │  │  │    → return stored video info   │        │
│                 │  │  └─────────────────────────────────┘        │
│                 │  │       ↓                                     │
│                 │  │  Tool result + conversation history          │
│                 │  │       ↓                                     │
│                 │  │  [Claude Sonnet 4.6] → answer with citations     │
│                 │  │       ↓                                     │
│                 │  │  Response to UI (with timestamp links)       │
│                 │  │                                             │
│                 │  │  [MemorySaver] → stores conversation        │
└─────────────────┘  └─────────────────────────────────────────────┘

External Services:
┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
│ YouTube     │  │ Pinecone     │  │ Anthropic   │  │ LangSmith  │
│ (transcript │  │ (vectors +   │  │ (Claude     │  │ (tracing + │
│  API)       │  │  embeddings) │  │  Sonnet 4.6)│  │  eval)     │
│ FREE        │  │ FREE TIER    │  │ PAY-PER-USE │  │ FREE TIER  │
└─────────────┘  └──────────────┘  └─────────────┘  └────────────┘
```

---

## Part 1: Ingestion Pipeline (adding a video)

### Flow
1. User pastes YouTube URL in sidebar
2. Check video limit (5 per session, unless unlimited key active)
3. Extract video_id from URL (e.g. `dQw4w9WgXcQ`)
4. **Check if namespace exists in Pinecone** → if yes, fetch `{video_id}_metadata` record, skip to step 14 (instant reuse)
5. Fetch transcript via `youtube-transcript-api` (v1.0+: instantiate `YouTubeTranscriptApi()`, call `.fetch(video_id)`, returns `FetchedTranscript` with `.snippets`)
6. If no transcript → show error, skip (stretch: Whisper fallback)
7. **Check video duration** (last transcript segment timestamp) → if >60 min and free user → reject with message
8. Fetch video metadata (title, channel, duration) via YouTube oEmbed or yt-dlp
9. Chunk transcript by time windows (~60-90s with ~10-15s overlap)
10. Each chunk gets metadata: video_id, video_title, channel, start_time, end_time, chunk_index
11. Embed chunks via Pinecone Inference API (`llama-text-embed-v2`)
12. Upsert vectors into Pinecone, namespace = video_id
13. **Create `{video_id}_metadata` record** (sentinel vector `[1e-7, 0, ...]`, video info in metadata) in same namespace
14. Add video to session state (loaded_videos list)
15. Show confirmation — "Video loaded"

### Chunk structure example
```python
{
    "id": "dQw4w9WgXcQ_chunk_003",
    "values": [0.012, -0.034, ...],  # 1024-dim embedding vector
    "metadata": {
        "video_id": "dQw4w9WgXcQ",
        "video_title": "How Neural Networks Work",
        "channel": "3Blue1Brown",
        "text": "So the basic idea behind a neural network is...",
        "start_time": 180.0,    # seconds
        "end_time": 270.0,      # seconds
        "start_display": "3:00", # human readable
        "end_display": "4:30",
        "chunk_index": 3,
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    }
}
```

### Cached summary/topics record example
```python
# Stored in Pinecone after first summary generation
{
    "id": "dQw4w9WgXcQ_summary",
    "values": [1e-7, 0.0, ...],  # sentinel vector (Pinecone rejects pure zeros)
    "metadata": {
        "video_id": "dQw4w9WgXcQ",
        "type": "summary",
        "text": "This video explains how neural networks learn by...",
        "generated_at": "2026-02-26T10:00:00Z"
    }
}
```

### Special records per namespace
Each video namespace contains three types of records:
```
Namespace: dQw4w9WgXcQ
├── dQw4w9WgXcQ_chunk_000    (regular chunk, with embedding)
├── dQw4w9WgXcQ_chunk_001    (regular chunk, with embedding)
├── ...
├── dQw4w9WgXcQ_metadata     (sentinel vector, video info)     ← created at ingestion
├── dQw4w9WgXcQ_summary      (sentinel vector, cached summary) ← created on first summary request
└── dQw4w9WgXcQ_topics       (sentinel vector, cached topics)  ← created on first topics request
```

### Metadata record example
```python
{
    "id": "dQw4w9WgXcQ_metadata",
    "values": [1e-7, 0.0, ...],  # sentinel vector (Pinecone rejects pure zeros)
    "metadata": {
        "type": "metadata",
        "video_id": "dQw4w9WgXcQ",
        "video_title": "How Neural Networks Work",
        "channel": "3Blue1Brown",
        "duration_seconds": 1230,
        "duration_display": "20:30",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "chunk_count": 15,
        "ingested_at": "2026-02-26T10:00:00Z"
    }
}
```

### Key decisions for this part
- **Video duration cap:** 60 min for free users, unlimited for contributors (checked via last transcript timestamp before chunking)
- **Embedding dimension:** 1024 (model default via `create_index_for_model`). Matryoshka architecture means 1024 retains ~98-99% of full 2048 quality. Spoken transcripts don't benefit from the last 1-2%.
- **Chunk window:** ~60-90 seconds of transcript per chunk
- **Note:** Pinecone recommends 400-500 tokens per chunk for llama-text-embed-v2. Our 60-90s windows produce ~160-400 tokens depending on speaker pace — mostly below recommendation. However, spoken transcripts have lower semantic density than academic text, and smaller chunks give more precise timestamps. **Plan:** Start with 60-90s, test retrieval quality during development, increase to 120-150s if results are poor.
- **Overlap:** ~10-15 seconds between chunks (prevents losing context at boundaries)
- **Metadata:** Store enough to generate clickable timestamp links (`https://youtu.be/{video_id}?t={start_time_seconds}`)
- **Video metadata source:** YouTube oEmbed API (free, no API key) or parse from page

---

## Part 2: Query Pipeline (asking a question)

### LangChain + LangGraph relationship
```
LangChain (foundation)
├── LLM wrappers (ChatAnthropic)
├── Tools (@tool decorator)
├── Text splitters (chunking)
├── Vector store integrations (Pinecone)
├── Prompts, chains, LCEL
│
└── LangGraph (agent layer, built on top of LangChain)
    ├── create_agent() — agent that decides which tool to use
    ├── MemorySaver — conversation persistence
    ├── Graph-based execution (nodes, edges, state)
    └── Tool routing + multi-step reasoning
```

LangChain provides the building blocks. LangGraph orchestrates them into an agent that reasons about which tools to use and when. Both are required — LangGraph depends on LangChain.

### Flow
1. User types question in chat input
2. Check question limit (10 per session, unless unlimited key active)
3. Question + conversation history → LangGraph agent
4. Agent decides which tool(s) to use based on the question
5. Tool executes → returns context to agent
6. Agent + context → Claude Sonnet 4.6 generates answer
7. Answer includes citations: [Video Title, Timestamp] with clickable links
8. Answer displayed in chat, conversation saved in memory

### Agent setup (following teacher's notebook pattern)
```python
# Pattern from notebook, adapted for our stack
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.0)
memory = MemorySaver()
tools = [vector_search, summarize_video, list_topics, compare_videos, get_metadata]
agent = create_agent(llm, tools, system_prompt=system_prompt, checkpointer=memory)

# Per-conversation config
config = {"configurable": {"thread_id": session_id}}
response = agent.invoke({"messages": [("user", question)]}, config)
```

### Citation format in answers
```
Based on the video "How Neural Networks Work" by 3Blue1Brown,
the key concept is... [3:00-4:30](https://youtu.be/dQw4w9WgXcQ?t=180)

The creator also mentions... [12:15-13:00](https://youtu.be/dQw4w9WgXcQ?t=735)
```

---

## Part 3: Agent Tools (detailed)

### Tool 1: vector_search
- **Purpose:** Answer specific questions using relevant transcript chunks
- **Input:** query string
- **Process:** Embed query via Pinecone Inference → query each selected video's namespace separately → merge results by score → return top-k chunks with metadata
- **Top-k:** 5 total (or scale per-video if multiple selected, same pattern as compare_videos)
- **Result filter:** Only records with `type == "chunk"` are returned. Sentinel records (metadata, summary, topics) are excluded even if they score above zero.
- **Output:** List of relevant text chunks with timestamps
- **Used when:** User asks a factual question about video content

### Tool 2: summarize_video
- **Purpose:** Generate a full summary of one video
- **Input:** video_id
- **Process:**
  1. Check Pinecone for cached summary (`{video_id}_summary` record)
  2. If cached → return immediately (zero API cost)
  3. If not → fetch all chunks for namespace → send to Claude → store result as `{video_id}_summary` in Pinecone (sentinel vector, summary in metadata)
- **Output:** Structured summary (key points, main argument, conclusions)
- **Used when:** "Summarize this video", "What's this video about?"

### Tool 3: list_topics
- **Purpose:** Extract main topics/themes from a video
- **Input:** video_id
- **Process:**
  1. Check Pinecone for cached topics (`{video_id}_topics` record)
  2. If cached → return immediately
  3. If not → fetch all chunks → Claude extracts topics with timestamps → store as `{video_id}_topics` in Pinecone
- **Output:** List of topics with approximate timestamps
- **Used when:** "What topics does this video cover?", "Give me an outline"

### Tool 4: compare_videos
- **Purpose:** Compare what multiple videos say about a topic
- **Input:** query string + list of video_ids
- **Process:**
  1. Embed query once via Pinecone Inference
  2. Query each namespace separately (sequential, ~100-200ms each)
  3. Fixed per-video allocation: `per_video_k = max(3, 10 // len(video_ids))`
  4. Merge all chunks (every video guaranteed representation)
  5. Send merged chunks + comparison prompt to Claude
- **Latency:** 2 videos = ~200-400ms extra, 5 videos = ~500-1000ms (negligible vs Claude's 2-5s)
- **No cap:** 5-video session limit already constrains. Worst case: 5 × 3 chunks = 15 chunks = ~6K tokens
- **Output:** Comparison with per-video citations
- **Used when:** "What do these videos say differently about X?", "Compare their advice on Y"

```python
# Implementation sketch
def compare_videos(query, video_ids):
    query_embedding = embed_query(query)
    all_chunks = []
    per_video_k = max(3, 10 // len(video_ids))
    
    for vid in video_ids:
        results = index.query(
            vector=query_embedding,
            namespace=vid,
            top_k=per_video_k,
            include_metadata=True
        )
        all_chunks.extend(results.matches)
    
    return format_comparison_context(all_chunks)
```

### Tool 5: get_metadata
- **Purpose:** Return video information
- **Input:** video_id
- **Process:** Fetch `{video_id}_metadata` record from Pinecone by ID → extract metadata fields
- **Output:** Title, channel, duration, upload date, URL, chunk count
- **Used when:** "What video is loaded?", "Who made this video?", "How long is it?"

---

## Part 4: Streamlit UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  🎬 AskTheVideo                                    [?] [⚙️]    │
├────────────┬────────────────────────────────────────────────────┤
│            │                                                    │
│ ADD VIDEO  │  Welcome! Paste a YouTube URL to get started.      │
│ [URL input]│                                                    │
│ [Load btn] │  ─────────────────────────────────────────         │
│            │                                                    │
│ ────────── │  🧑 User: What are the key points in this video?   │
│            │                                                    │
│ LOADED     │  🤖 Assistant: Based on "How Neural Networks        │
│ VIDEOS     │  Work", the key points are:                        │
│ ☑ Video 1  │  1. Neural networks learn by... [2:30-3:45]        │
│ ☑ Video 2  │  2. Backpropagation works by... [8:00-9:15]        │
│ ☐ Video 3  │  3. The training process... [15:20-16:40]          │
│ [x delete] │                                                    │
│            │  ─────────────────────────────────────────         │
│ ────────── │                                                    │
│            │  🧑 User: Compare what video 1 and 2 say about     │
│ 🔑 Access  │  learning rates                                    │
│ [key input]│                                                    │
│            │  🤖 Assistant: The two videos take different        │
│ ────────── │  approaches to learning rates...                   │
│            │                                                    │
│ 📊 3/5     │                                                    │
│ videos     │                                                    │
│ 📊 7/10    │                                                    │
│ questions  │                                                    │
│            │  ┌──────────────────────────────────────────┐      │
│ ────────── │  │  Ask a question about your videos...     │      │
│ ☕ Buy Me  │  └──────────────────────────────────────────┘      │
│   a Coffee │                                                    │
│ 📝 Feedback│                                                    │
│            │                                                    │
├────────────┴────────────────────────────────────────────────────┤
│  Powered by Claude Sonnet 4.6 & Pinecone  │  GA tracking (hidden)   │
└─────────────────────────────────────────────────────────────────┘
```

### Sidebar elements
1. **URL input** — text input + "Load Video" button
2. **Video library** — list of loaded videos with checkboxes (select which to query) and delete buttons
3. **Access key** — text input for unlimited access (1 shared key, delivered via BMC thank-you page). Sidebar only — no URL parameter, safe on shared/public computers.
4. **Limits display** — "X/5 videos loaded" + "X/10 questions remaining" (or "Unlimited" if key active)
5. **Links** — Buy Me a Coffee, Feedback (Google Form)

### Chat area
- Standard Streamlit chat (st.chat_message + st.chat_input)
- Answers include clickable timestamp links
- Loading spinner during processing

### Additional pages/sections
- Optional: "About" page explaining how it works

---

## Part 5: Access Control & Limits

### Access key
```python
import os

VALID_KEYS = set(os.getenv("VALID_ACCESS_KEYS", "").split(","))
KEY_DAILY_ALERT_THRESHOLD = 50

# Sidebar input only (no URL parameter — safe on shared computers)
def is_unlimited():
    return st.session_state.get("access_key", "") in VALID_KEYS
```

### Question tracking
```python
# In Streamlit session state
if "question_count" not in st.session_state:
    st.session_state.question_count = 0      # total questions this session
if "loaded_videos" not in st.session_state:
    st.session_state.loaded_videos = []       # list of video_ids in session
if "key_queries_today" not in st.session_state:
    st.session_state.key_queries_today = 0    # unlimited key usage counter

# Check question limit before each question
def check_question_limit():
    if is_unlimited():
        return True
    return st.session_state.question_count < 10

# Check video limit before loading
def check_video_limit():
    if is_unlimited():
        return True
    return len(st.session_state.loaded_videos) < 5
```

### Key usage monitoring
```python
def track_query(question: str):
    """Call after every successful query. Monitors key usage for abuse."""
    st.session_state.question_count += 1
    
    if is_unlimited():
        st.session_state.key_queries_today += 1
        count = st.session_state.key_queries_today
        logger.info(f"Unlimited query #{count} | question={question[:50]}")
        
        if count == KEY_DAILY_ALERT_THRESHOLD:
            notify_developer(
                "High Key Usage",
                f"Unlimited key used {count} times in this session"
            )
```

### Input Validation & Sanitization

```python
import re
from urllib.parse import urlparse, parse_qs

# Accepted YouTube URL patterns
YOUTUBE_PATTERNS = [
    r'^https?://(www\.)?youtube\.com/watch\?v=[\w-]{11}',
    r'^https?://youtu\.be/[\w-]{11}',
    r'^https?://(www\.)?youtube\.com/embed/[\w-]{11}',
]
MAX_QUESTION_LENGTH = 500  # characters

def extract_video_id(url: str) -> str | None:
    """Extract and validate YouTube video ID from URL.
    Returns 11-char video ID or None if invalid."""
    url = url.strip()
    
    # Reject non-YouTube domains
    parsed = urlparse(url)
    if parsed.hostname not in ("youtube.com", "www.youtube.com", "youtu.be"):
        return None
    
    # Extract video ID
    if parsed.hostname == "youtu.be":
        video_id = parsed.path.lstrip("/")
    else:
        video_id = parse_qs(parsed.query).get("v", [None])[0]
    
    # Validate: exactly 11 chars, alphanumeric + hyphen/underscore
    if video_id and re.match(r'^[\w-]{11}$', video_id):
        return video_id
    return None

def validate_question(question: str) -> str | None:
    """Validate and sanitize user question.
    Returns cleaned question or None if invalid."""
    question = question.strip()
    if not question or len(question) > MAX_QUESTION_LENGTH:
        return None
    return question
```

**Threats mitigated:**

| Threat | Protection |
|---|---|
| SQL/NoSQL injection via URL | Only 11-char alphanumeric IDs pass validation |
| XSS via URL or question | Streamlit auto-escapes output; validation strips unexpected input |
| Non-YouTube URLs | Domain whitelist (youtube.com, youtu.be only) |
| Oversized questions | 500 char limit prevents context window abuse |
| URL manipulation (path traversal, redirects) | Parsed via `urlparse`, only known patterns accepted |

### Video reuse logic
```python
def load_video(video_id):
    # Check if already embedded in Pinecone
    try:
        result = index.fetch(
            ids=[f"{video_id}_metadata"],
            namespace=video_id
        )
        if result.vectors:
            # Namespace exists — fetch metadata, skip embedding
            meta = result.vectors[f"{video_id}_metadata"].metadata
            st.session_state.loaded_videos.append({
                "video_id": video_id,
                "title": meta["video_title"],
                "channel": meta["channel"],
                "duration": meta["duration_display"]
            })
            return "Video loaded instantly (cached)"
    except Exception:
        pass  # Namespace doesn't exist, proceed with ingestion
    
    # New video — fetch transcript, chunk, embed, upsert
    transcript = fetch_transcript(video_id)
    metadata = fetch_video_metadata(video_id)
    chunks = chunk_transcript(transcript)
    embed_and_upsert(chunks, namespace=video_id)
    upsert_metadata_record(video_id, metadata, len(chunks))
    st.session_state.loaded_videos.append({
        "video_id": video_id,
        "title": metadata["title"],
        "channel": metadata["channel"],
        "duration": metadata["duration_display"]
    })
    return "Video processed and loaded"
```

### Environment variables (Koyeb)
```
ANTHROPIC_API_KEY=sk-ant-...
PINECONE_API_KEY=pcsk_...
LANGSMITH_API_KEY=lsv2_...
VALID_ACCESS_KEYS=ASKTHEVIDEO2026   # Shared key, auto-delivered via BMC thank-you. Rotate if abused.
GA_TRACKING_ID=G-XXXXXXXXXX
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ADMIN_TOKEN=your_secret_admin_token_here
```

---

## Part 6: LangSmith Integration

### Tracing
- All agent invocations automatically traced when LANGSMITH_API_KEY is set
- Set environment variables:
  ```
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_PROJECT=askthevideo
  ```

### Evaluation
- Prepare 10-15 test Q&A pairs across 3-4 videos
- Categories to test:
  - Factual questions (specific detail from one video)
  - Summary requests
  - Topic listing
  - Cross-video comparison
  - Follow-up questions (memory test)
  - Out-of-scope questions (agent shouldn't use tools)
- Metrics: relevance, accuracy, citation correctness
- Run via LangSmith evaluation framework or manual scoring

---

## Part 7: Deployment (Koyeb)

### Docker setup
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Streamlit production config
```toml
# .streamlit/config.toml
[server]
maxUploadSize = 5           # MB — we only accept URL strings, not file uploads
maxMessageSize = 50         # MB — websocket messages (our chat messages are tiny)
enableXsrfProtection = true # Security: prevent cross-site request forgery
runOnSave = false           # No hot-reload in production
fileWatcherType = "none"    # Disable file watcher — saves CPU/RAM in production

[client]
showErrorDetails = false    # SECURITY: prevent stack traces from leaking env vars/API keys

[browser]
gatherUsageStats = false    # No telemetry
```

### Concurrent user monitoring

Lightweight session counter with Discord alert when threshold exceeded. Uses the global metrics store from `metrics.py` (see Part 11):

```python
# In metrics.py — session tracking uses the shared _app_metrics dict
CONCURRENT_ALERT_THRESHOLD = 10

def register_session():
    """Call once on session start."""
    with _app_metrics["lock"]:
        _app_metrics["active_sessions"] += 1
        count = _app_metrics["active_sessions"]
    logger.info(f"Session started. Active sessions: {count}")
    if count >= CONCURRENT_ALERT_THRESHOLD:
        notify_developer(
            "High Concurrency",
            f"Active sessions: {count} (threshold: {CONCURRENT_ALERT_THRESHOLD})"
        )

def unregister_session():
    """Call on session end (Streamlit on_session_end callback)."""
    with _app_metrics["lock"]:
        _app_metrics["active_sessions"] = max(0, _app_metrics["active_sessions"] - 1)
        count = _app_metrics["active_sessions"]
    logger.info(f"Session ended. Active sessions: {count}")
```

### requirements.txt (estimated)
```
streamlit
langchain
langchain-anthropic
langchain-pinecone
langgraph
pinecone-client
youtube-transcript-api
python-dotenv
psutil
```

### requirements-dev.txt (local development only — not in Docker image)
```
-r requirements.txt
pytest
black
ruff
jupyter
ipykernel
```

### Deployment steps
1. Push Docker image to Koyeb (via GitHub integration or Docker registry)
2. Set environment variables in Koyeb dashboard
3. Configure custom domain (CNAME from OVH DNS)
4. Verify app runs within 512MB RAM

### Memory optimization tactics
- Use `python:3.12-slim` base image
- Minimize dependencies
- Don't load anything into memory that Pinecone handles
- Streamlit config: disable file watcher, limit message sizes
- Monitor with Koyeb dashboard + concurrent session counter

### Validated baseline (Day 1 — Streamlit + psutil only)

| Metric | Local (Docker) | Koyeb free tier |
|---|---|---|
| RAM (cgroup) | 43 MB | 90 MB |
| Koyeb platform overhead | — | ~13 MB |
| Remaining headroom | — | ~420 MB |

Note: `psutil` RSS reports ~740MB which includes shared libraries — misleading in containers. Always use cgroup memory (`/sys/fs/cgroup/memory.current`) or `docker stats` for actual usage.

---

## Part 8: Error Handling Architecture

### Severity levels

| Level | Behavior | Notification |
|---|---|---|
| **Expected** | User-friendly message, no retry | None |
| **Transient** | 1 retry, then user message | None |
| **Critical** | User message + Discord webhook alert | Developer notified immediately |
| **Unknown** | Generic message + Discord webhook alert | Developer notified immediately |

### YouTube / Transcript errors

| Error | Cause | User message | Level |
|---|---|---|---|
| No transcript | Video has no captions | "This video has no transcript available. Try a video with captions enabled." | Expected |
| Video not found | Bad URL / private / deleted | "Video not found. Check the URL or try a different video." | Expected |
| Age-restricted | YouTube blocks access | "This video is age-restricted and can't be accessed." | Expected |
| Network timeout | YouTube slow/down | "Couldn't reach YouTube. Please try again." | Transient |
| Library error | youtube-transcript-api bug | "Transcript service error. Please try again or try a different video." | Unknown |

### Pinecone errors

| Error | Cause | User message | Level |
|---|---|---|---|
| Connection refused | Pinecone down | "Database temporarily unavailable. Please try again in a moment." | Transient |
| Index paused | Free tier inactivity | "Database is waking up. Please wait ~30 seconds and try again." | Transient |
| Storage full | 2GB exceeded | "Storage limit reached. Please contact the developer." | Critical 🔔 |
| Read/write limit | 1M reads or 2M writes/mo | "Monthly usage limit reached. Service will resume next month." | Critical 🔔 |
| Embedding token limit | 5M tokens/mo exceeded | "Embedding quota reached. Service will resume next month." | Critical 🔔 |
| Dimension mismatch | Code bug | "Internal error. Please report this issue." | Critical 🔔 |
| Timeout | Slow query | "Search is taking too long. Please try again." | Transient |

### Anthropic / Claude errors

| Error | Cause | User message | Level |
|---|---|---|---|
| 429 rate limit | Too many requests | "AI service is busy. Please wait a moment and try again." | Transient |
| 402 / insufficient credits | API credits exhausted | "AI service is temporarily unavailable. The developer has been notified." | Critical 🔔 |
| Budget exceeded | Monthly spend cap hit | Same as above | Critical 🔔 |
| 500 server error | Anthropic outage | "AI service is experiencing issues. Please try again later." | Transient |
| Context too long | Prompt exceeds limit | "This query produced too much context. Try a more specific question." | Expected |
| Timeout (>30s) | Slow generation | "Response is taking too long. Please try again." | Transient |

### LangSmith errors

| Error | Cause | User message | Level |
|---|---|---|---|
| Any error | Any | *(silent — never shown to user, never blocks the app)* | Ignored |

### Application-level errors

| Error | Cause | User message | Level |
|---|---|---|---|
| Session limit reached | 10 questions used | "You've used all 10 questions. Refresh for a new session, or contribute for unlimited access." | Expected |
| Video limit reached | 5 videos loaded | "Maximum 5 videos per session. Remove a video to add another." | Expected |
| Duration limit exceeded | Video > 60 min (free) | "Free tier supports videos up to 60 minutes. Contribute for unlimited access." | Expected |
| Invalid URL | Not a YouTube URL | "Please enter a valid YouTube URL." | Expected |
| Unhandled exception | Any uncaught error | "Something unexpected happened. Please try again. If this persists, contact the developer." | Unknown 🔔 |

### Developer notification (Discord webhook)

```python
import requests
import os
import logging

logger = logging.getLogger(__name__)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def notify_developer(error_type: str, details: str):
    """Send critical error notification via Discord webhook.
    Never raises — notification failure must not crash the app."""
    try:
        if not DISCORD_WEBHOOK_URL:
            logger.warning(f"No webhook configured. Alert: {error_type}: {details}")
            return
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": f"🚨 **AskTheVideo Alert**\n**{error_type}**\n{details}"
        }, timeout=5)
    except Exception:
        pass  # Notification failure should never crash the app
```

### Global error catcher

```python
class UserFacingError(Exception):
    """Error with a message safe to show to the user."""
    def __init__(self, user_message: str, notify: bool = False):
        self.user_message = user_message
        self.notify = notify
        super().__init__(user_message)

def safe_execute(func, *args, error_context="", **kwargs):
    """Wraps every tool and user-facing function.
    Known errors re-raise with user message.
    Unknown errors → log + notify + generic message."""
    try:
        return func(*args, **kwargs)
    except UserFacingError:
        raise  # Already has a user-friendly message
    except Exception as e:
        logger.error(f"Unhandled error in {error_context}: {e}", exc_info=True)
        notify_developer("Unhandled Exception", f"{error_context}: {type(e).__name__}: {str(e)}")
        raise UserFacingError(
            "Something unexpected happened. Please try again. "
            "If this persists, contact the developer.",
            notify=False  # Already notified above
        )
```

### Retry pattern (for transient errors)

```python
import time

def retry_once(func, *args, retry_delay=2, error_context="", **kwargs):
    """Single retry for transient errors (Pinecone, Anthropic)."""
    try:
        return func(*args, **kwargs)
    except (ConnectionError, TimeoutError) as e:
        logger.warning(f"Transient error in {error_context}, retrying: {e}")
        time.sleep(retry_delay)
        return func(*args, **kwargs)  # Second failure will propagate
```

Add `DISCORD_WEBHOOK_URL` to Koyeb environment variables (see Part 5: Access Control for full list).

---

## Part 9: File Structure

```
askthevideo/
├── app.py                  # Main Streamlit app
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt    # Dev deps: pytest, black, ruff, jupyter
├── .env.example            # Template for env vars
├── .gitignore
├── README.md
├── .streamlit/
│   └── config.toml         # Production config (message limits, no file watcher)
│
├── src/
│   ├── __init__.py
│   ├── transcript.py       # YouTube transcript extraction
│   ├── chunking.py         # Time-based chunking logic
│   ├── vectorstore.py      # Pinecone operations (embed, upsert, query)
│   ├── agent.py            # LangGraph agent setup + tools
│   ├── tools.py            # Tool definitions (search, summarize, etc.)
│   ├── errors.py           # UserFacingError, safe_execute, notify_developer, retry_once
│   ├── metrics.py          # Global app metrics store, record_metric, record_tokens, get_metrics, event log
│   ├── admin.py            # Admin dashboard renderer (render_admin)
│   # Runtime: /app/events.log (rotating, max 1MB, created automatically)
│   ├── auth.py             # Access key validation + question/video limits
│   └── validation.py       # URL parsing, video ID extraction, question sanitization
│
├── landing/                # Static landing page (deployed to OVH)
│   ├── index.html
│   ├── style.css
│   └── assets/             # Images, icons, favicons
│
├── config/
│   └── settings.py         # Constants (chunk size, overlap, limits, etc.)
│
├── tests/
│   ├── test_validation.py  # URL parsing, video ID, question length
│   ├── test_chunking.py    # Chunk sizes, token counts, timestamps
│   ├── test_metrics.py     # record_metric, cost calculation
│   ├── test_access.py      # is_unlimited, question/video limits
│   ├── test_errors.py      # UserFacingError, safe_execute
│   └── eval_questions.json # LangSmith evaluation test set
│
├── notebooks/              # Development & validation (run locally before extraction to src/)
│   ├── 01_transcript_fetch.ipynb
│   ├── 02_chunking.ipynb
│   ├── 03_pinecone_operations.ipynb
│   ├── 04_claude_tools.ipynb
│   ├── 05_agent_routing.ipynb
│   └── 06_integration_flow.ipynb
│
├── scripts/
│   └── extract.py          # Automated notebook → src/ extraction pipeline
│
├── Makefile                # make extract / make format / make lint / make test / make all
│
├── docs/
│   ├── report.pdf
│   ├── presentation.pptx
│   └── speaker_notes.md
│
└── extras/
    ├── demo_script.md
    └── linkedin_post.md
```

---

## Part 10: Landing Page (`yourdomain.com`)

### Architecture
- **Static HTML/CSS/JS** hosted on OVH PHP hosting
- **No backend needed** — purely informational
- **CTA links** to `app.yourdomain.com` (Streamlit on Koyeb)
- **Google Analytics** shared tracking ID across landing + app
- **Pre-warm system** — wakes Koyeb + Pinecone in background while user reads page

### Cold Start Mitigation (pre-warm flow)

```
User lands on yourdomain.com (OVH — instant, static HTML)
    │
    ├── Page renders immediately, user reads hero/features
    │
    └── Background JS fires on page load:
        └── Ping app.yourdomain.com → wakes Koyeb container
            └── Koyeb startup code → pings Pinecone (wakes index)
    
    ... user spends 15-30s reading landing page ...
    
    User clicks "Try the App →"
        │
        ├── Pre-warm succeeded (got response): → redirect to app (instant)
        │
        └── Still waking (no response yet): → show holding page
            ├── Branded overlay: "App is waking up from deep sleep..."
            ├── Animated spinner
            ├── Poll every 3 seconds
            ├── Auto-redirect when ready
            └── Timeout after 60s with fallback message
```

**Pre-warm JS (in landing page):**
```javascript
const APP_URL = "https://app.yourdomain.com";
let appReady = false;

// Pre-warm on page load (fire and forget)
function pingApp() {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = img.onerror = () => resolve(true);
    img.src = `${APP_URL}/?ping=${Date.now()}`;
    setTimeout(() => resolve(false), 10000);
  });
}

pingApp().then(ok => { appReady = ok; });

// "Try the App" button handler
document.getElementById('try-app-btn').addEventListener('click', (e) => {
  if (appReady) {
    window.location.href = APP_URL;
  } else {
    e.preventDefault();
    showWakeUpScreen();
  }
});

function showWakeUpScreen() {
  document.getElementById('wakeup-overlay').style.display = 'flex';
  const poll = setInterval(async () => {
    const ok = await pingApp();
    if (ok) {
      clearInterval(poll);
      window.location.href = APP_URL;
    }
  }, 3000);
  // Timeout after 60s
  setTimeout(() => {
    clearInterval(poll);
    document.getElementById('wakeup-message').textContent =
      "Taking longer than expected. Please try refreshing the page.";
  }, 60000);
}
```

**Streamlit startup (pre-warms Pinecone):**
```python
@st.cache_resource
def init_services():
    """Initialize and pre-warm external services on container start."""
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index("askthevideo")
    index.describe_index_stats()  # Wakes Pinecone if paused
    return index
```

**Timing estimates:**

| Scenario | User wait time |
|---|---|
| User spends 15-30s on landing page | 0s (both services pre-warmed) |
| User clicks immediately (<5s) | 10-25s (holding page shown) |
| Extended dormancy (3+ weeks, Pinecone paused) | 30-60s (holding page shown) |

### SEO Strategy
- Semantic HTML5 (`<header>`, `<main>`, `<section>`, `<article>`, `<footer>`)
- Meta tags: title, description, keywords
- Open Graph tags (for social sharing previews)
- Structured data (JSON-LD — WebApplication schema)
- Fast load time (static files, no framework)
- Mobile responsive

### Page Structure

```
┌─────────────────────────────────────────────────────────┐
│ HERO                                                     │
│ Headline: "Ask Any YouTube Video a Question"             │
│ Subheadline: Stop rewatching. Start asking.              │
│ [Try the App →] button                                   │
├─────────────────────────────────────────────────────────┤
│ HOW IT WORKS                                             │
│ ① Paste a YouTube URL                                    │
│ ② Ask a question in plain English                        │
│ ③ Get an answer with exact timestamps                    │
├─────────────────────────────────────────────────────────┤
│ FEATURES                                                 │
│ 🔍 Search — find specific details buried in long videos  │
│ 📝 Summarize — get the key points without watching       │
│ 📋 Topics — see what a video covers at a glance          │
│ ⚖️ Compare — see what multiple videos say about a topic  │
│ 🔗 Timestamps — clickable links to exact moments         │
├─────────────────────────────────────────────────────────┤
│ COST & LIMITATIONS                                       │
│ Free tier: 5 videos per session, 10 questions per session  │
│ Why limits? AI costs money — each answer uses Claude API  │
│ Want unlimited? Enter an access key (see below)          │
├─────────────────────────────────────────────────────────┤
│ SUPPORT THE PROJECT                                      │
│ This is a solo project by a bootcamp student.            │
│ Every coffee helps keep the servers running.             │
│ [☕ Buy Me a Coffee] button                              │
│ With a contribution, get an unlimited access key          │
│ (delivered instantly on the thank-you page).              │
├─────────────────────────────────────────────────────────┤
│ ABOUT THE PROJECT                                        │
│ Built as the final project for IronHack AI Engineering   │
│ Bootcamp (2026). Tech stack: Claude Sonnet 4.6,          │
│ Pinecone, LangChain, LangGraph, Streamlit.              │
│ [GitHub repo link]                                       │
├─────────────────────────────────────────────────────────┤
│ ABOUT ME                                                 │
│ Brief bio, photo (optional), links                       │
│ [GitHub] [LinkedIn]                                      │
├─────────────────────────────────────────────────────────┤
│ FAQ                                                      │
│ - What videos work? (Any with captions/transcripts)      │
│ - Is my data stored? (Transcripts cached, no personal    │
│   data collected)                                        │
│ - Do I lose my session on refresh? (Yes, but your        │
│   videos reload instantly from cache)                    │
│ - How accurate are the answers? (Based on transcript,    │
│   AI can make mistakes)                                  │
│ - Can I use it in other languages? (English only for     │
│   now)                                                   │
├─────────────────────────────────────────────────────────┤
│ FOOTER                                                   │
│ [Try the App →] │ [GitHub] │ [LinkedIn] │ [BMC]          │
│ © 2026 Krzysztof Giwojno │ IronHack AI Engineering      │
└─────────────────────────────────────────────────────────┘
```

### Landing page files
```
landing/
├── index.html          # Single-page, all sections + pre-warm JS + wake-up overlay
├── style.css           # Responsive design, visual theme TBD
└── assets/
    ├── favicon.ico
    ├── og-image.png    # Social sharing preview image
    └── icons/          # Feature icons if needed
```

---

## Part 11: Admin Dashboard

Hidden page accessible via `app.yourdomain.com?admin=SECRET_TOKEN`. Single-view aggregation of app-specific metrics. Auto-refreshes every 30 seconds.

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│ 🔧 AskTheVideo — Admin Dashboard              [🔄 Refresh] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  REAL-TIME                                                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐│
│  │ Active     │ │ RAM        │ │ CPU        │ │ Uptime   ││
│  │ Sessions   │ │ Usage      │ │            │ │          ││
│  │     3      │ │ 340/512 MB │ │   12.3%    │ │  4.2h    ││
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘│
│                                                             │
│  SESSION STATS (since container start)                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐│
│  │ Total      │ │ Videos     │ │ Key        │ │ Errors   ││
│  │ Queries    │ │ Loaded     │ │ Queries    │ │ / Alerts ││
│  │    127     │ │     34     │ │     15     │ │   2 / 3  ││
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘│
│                                                             │
│  API COST ESTIMATE (since container start)                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐│
│  │ Input      │ │ Output     │ │ Estimated  │ │ Budget   ││
│  │ Tokens     │ │ Tokens     │ │ Cost       │ │ Remaining││
│  │  245,230   │ │   38,410   │ │   $1.31    │ │ 🟢 $3.69 ││
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘│
│                                                             │
│  PINECONE (persistent — survives restarts)                  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │ Cached     │ │ Total      │ │ Index      │             │
│  │ Videos     │ │ Vectors    │ │ Fullness   │             │
│  │     42     │ │   3,150    │ │    1.2%    │             │
│  └────────────┘ └────────────┘ └────────────┘             │
│                                                             │
│  RECENT EVENTS (last 20 — from events.log)                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 14:25:01 | QUERY   | free  | 83.12.x.x | "what..  │   │
│  │ 14:24:30 | VIDEO   | cache | 83.12.x.x | "Pyth..  │   │
│  │ 14:23:55 | SESSION | start | 83.12.x.x | active=4 │   │
│  │ 14:20:10 | KEY     | query | 91.45.x.x | "compa.. │   │
│  │ 14:15:22 | ERROR   | TRANS | 83.12.x.x | Pineco.. │   │
│  │ 14:15:22 | ALERT   | disc. | —         | Pineco.. │   │
│  │ 14:10:05 | VIDEO   | new   | 91.45.x.x | "ML F..  │   │
│  │ 14:05:00 | SESSION | end   | —         | active=3  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  EXTERNAL DASHBOARDS                                        │
│  [LangSmith] [Koyeb] [Google Analytics] [Discord]          │
│                                                             │
│  Auto-refresh: 30s                          Last: 14:25:01  │
└─────────────────────────────────────────────────────────────┘
```

### Global App Metrics Store

All metrics tracked in a thread-safe global dict, shared across all Streamlit sessions:

```python
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
from collections import deque
import psutil
import streamlit as st

# --- Event Log Setup ---
EVENT_LOG_PATH = "/app/events.log"
event_logger = logging.getLogger("events")
event_logger.setLevel(logging.INFO)
event_handler = RotatingFileHandler(
    EVENT_LOG_PATH,
    maxBytes=500_000,       # ~5,000 lines, auto-rotates
    backupCount=1           # Keep 1 backup → max 1MB disk
)
event_handler.setFormatter(logging.Formatter("%(message)s"))
event_logger.addHandler(event_handler)

def get_client_ip() -> str:
    """Get client IP from Koyeb reverse proxy headers."""
    try:
        headers = st.context.headers
        return headers.get("X-Forwarded-For", "unknown").split(",")[0].strip()
    except Exception:
        return "unknown"

def log_event(event_type: str, subtype: str, ip: str = "—", detail: str = ""):
    """Write structured event to rotating log file.
    
    Event types: QUERY, VIDEO, SESSION, ERROR, KEY, ALERT
    Format: timestamp | TYPE | subtype | ip | detail
    """
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {event_type:<7} | {subtype:<6} | {ip:<15} | {detail}"
    event_logger.info(line)
```

### Event Types Reference

| Type | Subtypes | IP? | Detail |
|---|---|---|---|
| QUERY | free | ✅ | Question text (truncated 50 chars) |
| KEY | query | ✅ | Question text + key usage count |
| VIDEO | cache, new | ✅ | Video title, ID, chunk count (if new) |
| SESSION | start, end | ✅ start, — end | Active session count |
| ERROR | EXPCT, TRANS, CRIT, UNKN | ✅ | Error context, type, message (truncated 80 chars) |
| ALERT | discord | — | Alert type + details (mirrors Discord notification) |

**IP tracking:** Client IP captured from `X-Forwarded-For` header (set by Koyeb reverse proxy). Useful for spotting abuse patterns (same IP hitting key endpoint repeatedly). Session end events log `—` because Streamlit's `on_session_end` callback doesn't have request context.

```python
def get_recent_events(n: int = 20) -> list[str]:
    """Read last N lines from event log file."""
    import os
    if not os.path.exists(EVENT_LOG_PATH):
        return []
    with open(EVENT_LOG_PATH, "r") as f:
        return list(deque(f, maxlen=n))
```

```python
# --- App Metrics Store ---
_app_metrics = {
    "lock": threading.Lock(),
    "start_time": time.time(),
    
    # Session tracking
    "active_sessions": 0,
    
    # Counters (since container start)
    "total_queries": 0,
    "total_videos_loaded": 0,
    "total_videos_cached": 0,       # newly embedded (not from cache)
    "key_queries": 0,
    "error_count": 0,
    "alert_count": 0,
    
    # Token tracking (for cost estimation)
    "total_input_tokens": 0,
    "total_output_tokens": 0,
}

# Claude Sonnet 4 pricing
COST_INPUT_PER_1K = 0.003     # $3 per 1M input tokens
COST_OUTPUT_PER_1K = 0.015    # $15 per 1M output tokens
PROJECT_BUDGET = 5.00          # Total project budget in USD

def record_metric(key: str, increment: int = 1):
    """Thread-safe metric increment."""
    with _app_metrics["lock"]:
        _app_metrics[key] += increment

def record_tokens(input_tokens: int, output_tokens: int):
    """Record token usage from a Claude API call."""
    with _app_metrics["lock"]:
        _app_metrics["total_input_tokens"] += input_tokens
        _app_metrics["total_output_tokens"] += output_tokens

def get_metrics() -> dict:
    """Return snapshot of all metrics."""
    with _app_metrics["lock"]:
        m = dict(_app_metrics)
    
    # Computed fields
    m.pop("lock")
    m["uptime_hours"] = (time.time() - m["start_time"]) / 3600
    m["ram_mb"] = psutil.Process().memory_info().rss / 1024**2
    m["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    m["estimated_cost"] = (
        (m["total_input_tokens"] / 1000 * COST_INPUT_PER_1K) +
        (m["total_output_tokens"] / 1000 * COST_OUTPUT_PER_1K)
    )
    m["budget_remaining"] = PROJECT_BUDGET - m["estimated_cost"]
    return m
```

### Token Tracking Integration

Capture tokens from every Claude call via LangChain callback:

```python
from langchain_core.callbacks import BaseCallbackHandler

class TokenTracker(BaseCallbackHandler):
    """Callback handler that records token usage to global metrics."""
    
    def on_llm_end(self, response, **kwargs):
        usage = response.llm_output.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        record_tokens(input_tokens, output_tokens)
        logger.info(f"Tokens: in={input_tokens}, out={output_tokens}")

# Attach to agent
token_tracker = TokenTracker()
agent = create_agent(
    model=llm,
    tools=tools,
    checkpointer=memory,
    callbacks=[token_tracker]
)
```

### Metric Recording Points

Where to call `record_metric()` and `log_event()` in the app:

```python
# In track_query()
def track_query(question: str):
    st.session_state.question_count += 1
    record_metric("total_queries")
    ip = get_client_ip()
    
    if is_unlimited():
        record_metric("key_queries")
        count = st.session_state.key_queries_today + 1
        st.session_state.key_queries_today = count
        log_event("KEY", "query", ip, f'"{question[:50]}" | count={count}')
        
        if count == KEY_DAILY_ALERT_THRESHOLD:
            notify_developer("High Key Usage", f"Key used {count} times in session")
    else:
        log_event("QUERY", "free", ip, f'"{question[:50]}"')

# In load_video()
def load_video(video_id):
    ip = get_client_ip()
    record_metric("total_videos_loaded")
    
    # ... fetch/check Pinecone ...
    if cached:
        log_event("VIDEO", "cache", ip, f'"{title}" | video={video_id[:11]}')
    else:
        record_metric("total_videos_cached")
        log_event("VIDEO", "new", ip, f'"{title}" | video={video_id[:11]} | chunks={chunk_count}')

# In register_session() / unregister_session()
def register_session():
    with _app_metrics["lock"]:
        _app_metrics["active_sessions"] += 1
        count = _app_metrics["active_sessions"]
    ip = get_client_ip()
    log_event("SESSION", "start", ip, f"active={count}")
    
    if count >= CONCURRENT_ALERT_THRESHOLD:
        notify_developer("High Concurrency", f"Active sessions: {count}")

def unregister_session():
    with _app_metrics["lock"]:
        _app_metrics["active_sessions"] = max(0, _app_metrics["active_sessions"] - 1)
        count = _app_metrics["active_sessions"]
    log_event("SESSION", "end", "—", f"active={count}")

# In safe_execute() error handler
def safe_execute(fn, error_context):
    try:
        return fn()
    except Exception as e:
        record_metric("error_count")
        ip = get_client_ip()
        log_event("ERROR", severity, ip, f"{error_context}: {type(e).__name__}: {str(e)[:80]}")
        # ... existing error handling ...

# In notify_developer() — log every Discord alert as an event too
def notify_developer(error_type: str, details: str):
    record_metric("alert_count")
    log_event("ALERT", "discord", "—", f"{error_type}: {details}")
    # ... existing Discord webhook code ...
```

### Admin Dashboard Renderer

```python
import streamlit as st
import os

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
AUTO_REFRESH_SECONDS = 30

def render_admin() -> bool:
    """Render admin dashboard if valid token provided.
    Returns True if admin page was rendered (skip normal app)."""
    token = st.query_params.get("admin")
    if token != ADMIN_TOKEN or not ADMIN_TOKEN:
        return False
    
    st.set_page_config(page_title="AskTheVideo — Admin", page_icon="🔧", layout="wide")
    st.title("🔧 AskTheVideo — Admin Dashboard")
    
    m = get_metrics()
    
    # --- Row 1: Real-time ---
    st.subheader("Real-time")
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("Active Sessions", m["active_sessions"])
    r1c2.metric("RAM Usage", f"{m['ram_mb']:.0f} / 512 MB")
    r1c3.metric("CPU", f"{m['cpu_percent']:.1f}%")
    r1c4.metric("Uptime", f"{m['uptime_hours']:.1f}h")
    
    # --- Row 2: Session stats ---
    st.subheader("Session Stats (since container start)")
    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("Total Queries", m["total_queries"])
    r2c2.metric("Videos Loaded", m["total_videos_loaded"])
    r2c3.metric("Key Queries", m["key_queries"])
    r2c4.metric("Errors / Alerts", f"{m['error_count']} / {m['alert_count']}")
    
    # --- Row 3: API Cost ---
    st.subheader("API Cost Estimate (since container start)")
    r3c1, r3c2, r3c3, r3c4 = st.columns(4)
    r3c1.metric("Input Tokens", f"{m['total_input_tokens']:,}")
    r3c2.metric("Output Tokens", f"{m['total_output_tokens']:,}")
    r3c3.metric("Estimated Cost", f"${m['estimated_cost']:.2f}")
    budget_color = "🟢" if m["budget_remaining"] > 2 else "🟡" if m["budget_remaining"] > 0.5 else "🔴"
    r3c4.metric("Budget Remaining", f"{budget_color} ${m['budget_remaining']:.2f}")
    
    # --- Row 4: Pinecone ---
    st.subheader("Pinecone (persistent)")
    try:
        stats = index.describe_index_stats()
        ns_count = len(stats.get("namespaces", {}))
        total_vectors = stats.get("total_vector_count", 0)
        # Starter plan: 100,000 vectors max for 2GB
        fullness = (total_vectors / 100000) * 100
        
        r4c1, r4c2, r4c3 = st.columns(3)
        r4c1.metric("Cached Videos", ns_count)
        r4c2.metric("Total Vectors", f"{total_vectors:,}")
        r4c3.metric("Index Fullness", f"{fullness:.1f}%")
    except Exception as e:
        st.error(f"Pinecone error: {e}")
    
    # --- Row 5: Recent Events ---
    st.subheader("Recent Events (last 20)")
    events = get_recent_events(20)
    if events:
        # Display as monospace code block for alignment
        st.code("".join(events), language=None)
    else:
        st.info("No events logged yet.")
    
    # --- Row 6: External dashboards ---
    st.subheader("External Dashboards")
    lc1, lc2, lc3, lc4 = st.columns(4)
    lc1.markdown("[🔗 LangSmith](https://smith.langchain.com)")
    lc2.markdown("[🔗 Koyeb](https://app.koyeb.com)")
    lc3.markdown("[🔗 Google Analytics](https://analytics.google.com)")
    lc4.markdown("[🔗 Discord](https://discord.com)")
    
    # --- Auto-refresh ---
    st.divider()
    st.caption(f"Auto-refresh: {AUTO_REFRESH_SECONDS}s | Last updated: {time.strftime('%H:%M:%S')}")
    time.sleep(AUTO_REFRESH_SECONDS)
    st.rerun()
    
    return True
```

### Usage in app.py

```python
# Top of app.py — check admin before normal rendering
if render_admin():
    st.stop()

# ... normal app code below ...
```

### Environment variable

```
ADMIN_TOKEN=your_secret_admin_token_here
```

### Data persistence notes

| Data | Persistence | Notes |
|---|---|---|
| Metric counters (queries, tokens, errors) | Lost on container restart | In-memory dict. Acceptable for bootcamp |
| Event log (`events.log`) | Survives session resets, lost on container restart | Rotating file on ephemeral Koyeb filesystem. Max 1MB |
| Pinecone stats (cached videos, vectors) | Persistent (survives restarts) | Stored in Pinecone, fetched live via API |
| Budget remaining | Resets on restart | Based on accumulated token count. Update `PROJECT_BUDGET` constant if adding credits |
| Client IPs | In event log only | From `X-Forwarded-For` header via Koyeb reverse proxy |

**Note:** All local data (metrics, event log) is lost on container restart. Koyeb free tier has no persistent storage. Stretch goal: Axiom external log sink (30 day retention) for crash investigation. See Stretch Goals #10.

### Observability stack summary

| Layer | Tool | What it covers |
|---|---|---|
| Agent behavior | LangSmith | Tool routing, token usage per call, latency, full traces |
| Critical alerts | Discord webhooks | Errors, credit exhaustion, high concurrency, key abuse |
| Container health | Koyeb dashboard | Container CPU, RAM, restarts, deploy logs |
| Traffic analytics | Google Analytics | Visitors, geography, page views, session duration |
| App-level metrics | Admin dashboard | Sessions, RAM, CPU, queries, costs, Pinecone stats — single view |
| Event log | Admin dashboard | Last 20 events from rotating file log. Tracks queries, video loads, sessions (with IP), errors, alerts. Survives session resets, lost on container restart. |

---

## Part 12: Privacy & Compliance

### GDPR Considerations

The app processes personal data from EU users (developer is Berlin-based). Key compliance areas:

| Area | Current state | Remediation |
|---|---|---|
| Cookie consent | Not implemented. GA sets cookies without consent | Add cookie consent banner before loading GA script |
| Privacy policy | None | Create privacy policy page on landing site |
| IP logging | Client IPs logged in `events.log` | Truncate to /24 (anonymize last octet): `ip.rsplit(".", 1)[0] + ".x"` |
| User questions | Truncated in logs, full text sent to Anthropic API | Disclose third-party data processing in privacy policy |
| Right to erasure | No mechanism | Sessions are ephemeral — data self-deletes on container restart. Pinecone stores only video transcripts (public data), not user queries |
| Data retention | Event log: until container restart. Pinecone: indefinite | Document retention periods in privacy policy |

**Minimum for bootcamp:**
- Add a brief privacy note to the landing page footer ("Your questions are processed by Claude AI. No personal data is stored permanently.")
- Anonymize IPs in event log (truncate last octet)
- Document full GDPR remediation plan in this section

**For production:** Full cookie consent (e.g., Cookiebot), comprehensive privacy policy, Data Processing Agreement with Anthropic, IP anonymization in GA (`anonymize_ip: true`).

### YouTube ToS & Legal Risk

The `youtube-transcript-api` library scrapes YouTube's internal transcript endpoint. It is **not** an official YouTube API.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| YouTube blocks the scraping endpoint | Low (stable for years) | App breaks entirely | Document yt-dlp as backup. Monitor for library updates |
| YouTube rate-limits by IP | Medium (heavy use) | Slower ingestion | Koyeb IP rotates on container restart |
| Legal challenge (YouTube ToS violation) | Very low (bootcamp project) | Cease and desist | Remove app. No commercial use at current scale |
| Transcript content copyright | Low (fair use for analysis) | Takedown request | App analyzes, doesn't republish. Transformative use argument |

**For bootcamp:** Document as known risk. Mention in presentation as external dependency.
**For production:** Migrate to YouTube Data API v3 (official, quota-based, no transcript endpoint — would need Whisper for transcription).

---

## Part 13: Testing Strategy

### Test categories

#### Unit Tests
```
tests/
├── test_validation.py      # URL parsing, video ID extraction, question length
├── test_chunking.py        # Transcript chunking logic, window sizes, token counts
├── test_metrics.py         # record_metric, record_tokens, cost calculation
├── test_access.py          # is_unlimited, check_question_limit, check_video_limit
└── test_errors.py          # UserFacingError, safe_execute behavior
```

**Key test cases:**

| Test | Input | Expected |
|---|---|---|
| Valid YouTube URL | `https://www.youtube.com/watch?v=dQw4w9WgXcQ` | Returns `dQw4w9WgXcQ` |
| Short YouTube URL | `https://youtu.be/dQw4w9WgXcQ` | Returns `dQw4w9WgXcQ` |
| Non-YouTube URL | `https://vimeo.com/12345` | Returns `None` |
| Injection attempt | `https://youtube.com/watch?v='; DROP TABLE` | Returns `None` |
| Empty question | `""` | Returns `None` |
| Oversized question | 501+ chars | Returns `None` |
| Cost calculation | 1000 input, 500 output tokens | $0.0105 |
| Chunk 60s transcript | 150 words of text | 1 chunk with correct timestamps |

#### Integration Tests
```
tests/
├── test_pinecone.py        # Upsert → query round-trip, metadata record fetch, namespace check
├── test_anthropic.py       # Claude API call with token tracking
└── test_transcript.py      # youtube-transcript-api fetch for known video IDs
```

#### Agent Routing Tests
```
tests/
├── test_routing.py         # Verify tool selection for different query types
```

| Query | Expected tool |
|---|---|
| "What is this video about?" | `summarize_video` |
| "What does it say about learning rates?" | `vector_search` |
| "What topics are covered?" | `get_topics` |
| "Compare what both videos say about X" | `compare_videos` |
| "When was this uploaded?" | `get_metadata` |

#### Load Testing (manual, during Issue 5 validation)
- Open 5 browser tabs simultaneously, send queries
- Monitor RAM via admin dashboard and `psutil`
- Verify response times stay under 10 seconds
- Check for race conditions in global metrics dict

### Development Workflow: Notebooks → .py extraction

Development follows a **notebooks-first** approach. Each notebook validates a component against real data before code is extracted into production modules. This matches the bootcamp workflow and provides maximum visibility into data shapes, retrieval quality, costs, and edge cases.

#### Notebook sequence

```
notebooks/
├── 01_transcript_fetch.ipynb
├── 02_chunking.ipynb
├── 03_pinecone_operations.ipynb
├── 04_claude_tools.ipynb
├── 05_agent_routing.ipynb
└── 06_integration_flow.ipynb
```

#### 01_transcript_fetch.ipynb

**Goal:** Understand what real transcript data looks like. Discover edge cases before designing around assumptions.

| Test | What to observe |
|---|---|
| Fetch transcript for a known video | Raw data shape (list of dicts? keys? format?) |
| Inspect timestamps | Format, gaps, overlaps, precision |
| Long video (60 min) | Total data volume, memory footprint |
| Short video (2 min) | Minimum viable content, edge case |
| Video with no transcript | Exact error type and message |
| Video with auto-generated captions | Quality difference vs. manual captions |
| Non-English video | Does language detection work? |

**Output:** Understanding of data shape. Edge cases documented in notebook markdown cells. Decision: proceed with design assumptions or adjust.

#### 02_chunking.ipynb

**Goal:** Validate chunk sizes against real transcripts. Lock in window size based on actual token counts, not estimates.

| Test | What to observe |
|---|---|
| Chunk same transcript at 60s, 90s, 120s, 150s windows | Token count per chunk at each size |
| Visualize token distribution | Histogram — are most chunks in the 200-400 range? |
| Inspect chunk boundaries | Do they cut mid-sentence? Mid-word? |
| Validate start/end timestamps | Correct? Match original transcript? |
| Test overlap between chunks | Is context preserved across boundaries? |
| Count chunks per video at each window size | Impacts Pinecone storage + query top_k |

**Output:** Locked-in chunk size with data to back the decision. Working `chunk_transcript()` function.

#### 03_pinecone_operations.ipynb

**Goal:** Verify the full embedding → upsert → query round-trip. Test retrieval quality — are the right chunks returned for a given question?

| Test | What to observe |
|---|---|
| Create/connect to index | Confirm 1024 dimensions, llama-text-embed-v2 |
| Generate embeddings for real chunks | Latency per chunk, embedding shape |
| Upsert to a test namespace | Confirm successful, check vector count |
| Query: "What does the video say about X?" | Are top-5 chunks relevant? Correct timestamps? |
| Query: Vague question | What comes back? Is it useful? |
| Query: Question about content NOT in video | Does it return low-similarity results? |
| Upsert metadata record (sentinel vector + metadata) | Fetch by ID, verify fields |
| Fetch from empty namespace | What error? How to handle? |
| Cross-namespace query (2 videos) | Sequential queries, merge results, verify both represented |
| Measure latency | Per upsert, per query, per fetch |

**Output:** Validated Pinecone operations. Retrieval quality assessment. Latency benchmarks. Working `embed_and_upsert()`, `query_namespace()`, `upsert_metadata_record()` functions.

#### 04_claude_tools.ipynb

**Goal:** Test each agent tool individually. Measure token usage and cost per tool call. Validate output quality.

| Test | What to observe |
|---|---|
| `vector_search`: question → Pinecone → context → Claude → answer | Answer quality, timestamps included? |
| `summarize_video`: all chunks → Claude → summary | Length, quality, cost (tokens in/out) |
| `summarize_video` again (same video) → cache hit | Pinecone _summary record works? Instant? |
| `get_topics`: all chunks → Claude → topic list | Reasonable topics? With timestamps? |
| `get_topics` again → cache hit | Pinecone _topics record works? |
| `compare_videos`: 2 videos, same question | Both videos represented? Fair comparison? |
| `get_metadata`: fetch metadata record | All fields present? Formatted correctly? |
| Measure token usage per tool call | Compare with COST_BREAKDOWN.md estimates |

**Output:** Working tools with validated output quality. Actual cost per tool call (update COST_BREAKDOWN.md if estimates were off).

#### 05_agent_routing.ipynb

**Goal:** Wire up the LangGraph agent with all tools. Verify it routes queries to the correct tool. Tune tool descriptions if routing is wrong.

| Test | Expected tool | Pass? |
|---|---|---|
| "What is this video about?" | `summarize_video` | |
| "Summarize the key points" | `summarize_video` | |
| "What does it say about backpropagation?" | `vector_search` | |
| "Explain the part about gradient descent" | `vector_search` | |
| "What topics are covered?" | `get_topics` | |
| "List the main subjects discussed" | `get_topics` | |
| "Compare what both videos say about X" | `compare_videos` | |
| "How do video A and B differ on Y?" | `compare_videos` | |
| "When was this uploaded?" | `get_metadata` | |
| "How long is this video?" | `get_metadata` | |
| "Hi" (no video context) | Direct response (no tool) | |
| Ambiguous: "Tell me about this video" | summarize or vector_search | |

**Also test:**
- Multi-turn conversation — does MemorySaver work? Can agent reference prior answers?
- Follow-up question — "Tell me more about that" → uses previous context?
- Question about video not loaded → graceful error?

**Output:** Agent with validated routing. Tool descriptions finalized. If routing accuracy is below ~80%, iterate on tool descriptions before proceeding.

#### 06_integration_flow.ipynb

**Goal:** Full end-to-end pipeline. Validate costs against estimates. Test session limits.

| Test | What to observe |
|---|---|
| Full flow: URL → transcript → chunks → embed → query → answer | Total latency, total cost |
| Load same video again | Cache hit? Instant? Metadata preserved? |
| Load 5 videos, then compare | Cross-namespace works? All videos represented? |
| Ask 10 questions (free limit) | Counter works? 11th question blocked? |
| Enter access key → ask more | Unlimited mode works? |
| Invalid YouTube URL | Validation rejects it? |
| Video with no transcript | Error message shown? |
| Measure full session cost | Compare with $0.15 estimate |

**Output:** Validated full pipeline. Updated cost estimates if needed. Confidence to wire into Streamlit.

#### Automated Extraction Pipeline: notebooks → .py files

Production code is extracted automatically from notebooks using cell tags. No manual copy-paste.

**Cell tagging convention:**

In notebooks, any cell containing production code gets a marker comment as its first line:

```python
# @export src/transcript.py
def fetch_transcript(video_id: str) -> list[dict]:
    """Fetch transcript segments for a YouTube video."""
    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)
    return [{"text": s.text, "start": s.start, "duration": s.duration}
            for s in transcript.snippets]
```

Cells without the `# @export` tag are exploration/test code — ignored during extraction. This means every notebook is a mix of:
- Tagged cells → extracted to production .py files
- Untagged cells → experiments, prints, plots, inspection (stay in notebook only)

**Extraction mapping:**

| Notebook | Tagged cells export to |
|---|---|
| 01_transcript_fetch | `src/transcript.py` |
| 02_chunking | `src/chunking.py` |
| 03_pinecone_operations | `src/vectorstore.py` |
| 04_claude_tools | `src/tools.py` |
| 05_agent_routing | `src/agent.py` |
| 06_integration_flow | May contribute to multiple files or `src/config.py` |
| Design docs (Part 5, 8, 11) | `src/validation.py`, `src/errors.py`, `src/metrics.py`, `src/admin.py`, `src/auth.py` — built directly from design specs |

**Pipeline: `make all`**

```
make all
    │
    ├── Step 1: Extract (make extract)
    │   ├── Read .ipynb files
    │   ├── Parse notebook JSON, find cells starting with # @export
    │   ├── Group by target file
    │   ├── Collect all tagged cells per target .py file
    │   ├── Deduplicate imports
    │   │   Multiple cells may import the same module — keep one copy
    │   │   Move all imports to top of file
    │   └── Write .py files
    │       Add auto-generated header comment with source notebook reference
    │       Write imports block, then functions/classes in notebook order
    │
    ├── Step 2: Format (make format)
    │   black src/              (auto-format)
    │
    ├── Step 3: Lint (make lint)
    │   ruff check src/         (lint, catch issues)
    │
    ├── Step 4: Test (make test)
    │   pytest tests/ -v        (unit + integration tests)
    │
    └── Report
        ✅ All passed — files ready in src/
        ❌ Failures — fix in notebook, re-extract
```

Each step can also be run individually: `make extract`, `make format`, `make lint`, `make test`.

**Extraction script: `scripts/extract.py`**

```python
#!/usr/bin/env python3
"""Extract production code from notebooks into src/ modules.

Usage: python scripts/extract.py
   or: make extract

Reads all notebooks in notebooks/ directory, finds cells tagged with
# @export <target_file>, groups by target, deduplicates imports,
and writes clean .py files.
"""

import json
import re
from pathlib import Path
from collections import defaultdict

NOTEBOOKS_DIR = Path("notebooks")
HEADER = '''"""Auto-generated from notebooks by extract.py.
Sources: {sources}
Do not edit directly — modify the notebook and re-extract.
"""

'''

def extract_all():
    """Main extraction pipeline."""
    # Collect tagged cells from all notebooks
    exports = defaultdict(list)   # target_file -> [(source_notebook, code)]
    
    for nb_path in sorted(NOTEBOOKS_DIR.glob("*.ipynb")):
        with open(nb_path) as f:
            nb = json.load(f)
        
        for cell in nb.get("cells", []):
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell["source"])
            
            # Check for @export tag
            match = re.match(r"^# @export (.+)\n", source)
            if match:
                target = match.group(1).strip()
                # Remove the @export tag line from the code
                code = re.sub(r"^# @export .+\n", "", source)
                exports[target].append((nb_path.name, code))
    
    # Write each target file
    for target, cells in exports.items():
        target_path = Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        sources = sorted(set(nb for nb, _ in cells))
        all_code = [code for _, code in cells]
        
        # Separate imports from functions/classes
        imports, body = split_imports(all_code)
        
        with open(target_path, "w") as f:
            f.write(HEADER.format(sources=", ".join(sources)))
            f.write("\n".join(sorted(set(imports))))  # Deduplicated imports
            f.write("\n\n\n")
            f.write("\n\n".join(body))                # Functions/classes
            f.write("\n")
        
        print(f"  ✅ {target} ({len(cells)} cells from {', '.join(sources)})")
    
    print(f"\nExtracted {sum(len(c) for c in exports.values())} cells → {len(exports)} files")

def split_imports(code_blocks: list[str]) -> tuple[list[str], list[str]]:
    """Separate import lines from function/class definitions.
    
    Note: Only handles single-line imports. Multi-line imports like
    'from module import (\n    thing1,\n    thing2\n)' should be written
    as single lines in tagged cells: 'from module import thing1, thing2'
    """
    imports = []
    body = []
    
    for block in code_blocks:
        block_imports = []
        block_body = []
        for line in block.strip().split("\n"):
            if line.startswith("import ") or line.startswith("from "):
                block_imports.append(line)
            else:
                block_body.append(line)
        imports.extend(block_imports)
        body.append("\n".join(block_body).strip())
    
    return imports, [b for b in body if b]  # Filter empty blocks

if __name__ == "__main__":
    print("Extracting production code from notebooks...\n")
    extract_all()
```

**Makefile:**

```makefile
.PHONY: extract test lint format all

extract:
	python scripts/extract.py

format:
	black src/

lint:
	ruff check src/

test:
	pytest tests/ -v

# Full pipeline: extract → format → lint → test
all: extract format lint test
	@echo "✅ Pipeline complete"
```

**Generated file header example:**

```python
"""Auto-generated from notebooks by extract.py.
Sources: 01_transcript_fetch.ipynb
Do not edit directly — modify the notebook and re-extract.
"""

from youtube_transcript_api import YouTubeTranscriptApi


def fetch_transcript(video_id: str) -> list[dict]:
    """Fetch transcript segments for a YouTube video.
    Returns list of {'text': str, 'start': float, 'duration': float}."""
    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.fetch(video_id)
    return [{"text": s.text, "start": s.start, "duration": s.duration}
            for s in transcript.snippets]
```

**Rules for tagging cells in notebooks:**

1. Only tag cells containing finished, production-ready code
2. One `# @export` tag per cell (first line only)
3. Multiple cells can export to the same target file — they'll be combined in order
4. Don't tag exploration/debugging cells (prints, plots, experiments)
5. Include docstrings in tagged cells — they carry over to production
6. Don't worry about import deduplication in notebooks — the script handles it
7. Use single-line imports only in tagged cells (the extractor doesn't handle multi-line `from x import (\n...)` syntax)

**Files NOT extracted from notebooks (built from design specs):**

These files are written directly from the design doc patterns, not developed in notebooks:

| File | Source | Why not a notebook |
|---|---|---|
| `src/validation.py` | Part 5 design | Pure logic, no API exploration needed |
| `src/errors.py` | Part 8 design | Error handling wrappers, no data to explore |
| `src/metrics.py` | Part 11 design | Global state management, tested via admin dashboard |
| `src/admin.py` | Part 11 design | Streamlit-specific rendering, tested in app |
| `src/auth.py` | Part 5 design | Access key validation, simple logic |
| `app.py` | Wires everything | Streamlit UI, built after all modules extracted |

**Added to project root:**

```
scripts/
└── extract.py          # Notebook → .py extraction pipeline
Makefile                # At project root: make extract / make test / make all
```

### What to test where

| Test in notebooks (development) | Test in Streamlit app (integration) |
|---|---|
| Data shapes, API responses | UI layout, sidebar, chat flow |
| Retrieval quality, chunk relevance | Session state persistence |
| Agent routing decisions | Access key input |
| Token usage, cost per call | Error messages displayed to user |
| Chunking parameters, window sizes | Pre-warm + holding page |
| Individual tool correctness | Concurrent sessions |
| Multi-turn memory | Admin dashboard rendering |

### For bootcamp
Implement unit tests for validation and cost calculation (highest risk, easiest to test). Document remaining test cases as evidence of engineering thinking. Run agent routing tests manually during development via notebooks.

### For production
Full test suite with pytest. CI/CD runs tests on every push. Integration tests against staging Pinecone index (separate from production). Agent routing tests as part of LangSmith evaluation dataset.

---

## Part 14: Scaling Roadmap

### Phase 1: 0-50 daily users (current architecture)

**No changes needed.** Free tiers hold across all services.

| Resource | Usage | Headroom |
|---|---|---|
| Anthropic API | ~$5-15/month | Budget covers 1-3 months |
| Pinecone Starter | ~50-200 videos cached | 99% free capacity |
| Koyeb free tier | 1 container, 512MB | Handles 5-10 concurrent |
| LangSmith free | ~500 traces/month | Well within free tier |

### Phase 2: 50-200 daily users — first bottlenecks

| Bottleneck | Symptom | Fix | Cost |
|---|---|---|---|
| Anthropic costs | $50-150/month | Real revenue needed or apply for Anthropic startup credits | Revenue required |
| Koyeb 512MB RAM | OOM kills at 20+ concurrent | Upgrade to Koyeb Starter ($7.90/mo) | $7.90/mo |
| No user accounts | Can't track retention or upsell | Add auth (Supabase free tier, or Clerk) | Free-$25/mo |
| Session persistence | Users complain about losing history | Supabase/Turso for session storage | Free tier |
| Monitoring gaps | Need crash investigation | Axiom (stretch goal becomes mandatory) | Free tier |

### Phase 3: 200-1,000 daily users — architectural changes

| Change | Why | Effort |
|---|---|---|
| **Split frontend/backend** | Streamlit doesn't scale horizontally. FastAPI backend + React/Next.js frontend | 2-4 weeks |
| **Async ingestion queue** | Video processing blocks the user. Celery + Redis for background jobs | 1 week |
| **User accounts + video library** | Retention requires persistent personal data | 1 week |
| **Pinecone Standard plan** | Approaching Starter limits (2GB, 100K vectors) | $70/mo |
| **CDN for landing page** | OVH can't handle traffic spikes. Cloudflare or Vercel | 1 day |
| **Subscription revenue** | API costs demand real revenue. $5-10/month per user | 1 week (Stripe integration) |
| **Namespace cleanup job** | Unbounded growth approaches Pinecone limits | 1 day |

### Phase 4: 1,000+ daily users — different product

At this scale ($500+/month Anthropic alone), the project becomes a business:

| Requirement | Detail |
|---|---|
| Revenue | Subscription model ($5-10/month). Break-even at ~100 paid subscribers |
| Infrastructure | Multi-region deployment, load balancing, auto-scaling |
| Cost optimization | Fine-tuned smaller model for common queries, semantic caching layer |
| Legal | Full GDPR compliance, YouTube Data API v3 (official), Terms of Service, privacy policy |
| Team | Can't solo this — need at least 1 additional engineer + 1 product person |
| Observability | Sentry for errors, Datadog/Grafana for metrics, PagerDuty for alerting |

### Key architectural decision points

```
0-50 users:     Current architecture (monolith, free tiers)
     │
     │ Trigger: Anthropic bill > $50/month OR >10 concurrent regularly
     ▼
50-200 users:   Add auth + persistence + paid Koyeb
     │
     │ Trigger: Streamlit becomes bottleneck OR need async processing
     ▼
200-1K users:   Split to FastAPI + React, async queue, paid Pinecone
     │
     │ Trigger: Need team, legal, multi-region
     ▼
1K+ users:      Full SaaS product with subscription model
```
---

## Stretch Goals (if time allows)

1. **Google AdSense integration** — ads on landing page + app sidebar (monetization)
2. **Whisper API fallback** for videos without transcripts
3. **Voice input** — browser mic → speech-to-text → chat input
   - Option A: Browser Web Speech API (free, zero backend, Chrome/Edge only)
   - Option B: Streamlit `st.audio_input()` + OpenAI Whisper API ($0.006/min)
   - Teacher suggestion (Carlos) — bonus feature for demo
4. **Voice output with character voices** — read responses aloud in a selected voice
   - Option A: Browser SpeechSynthesis API (free, limited voices, no character voices)
   - Option B: ElevenLabs API (high quality character voices, free 10K chars/mo)
   - Option C: OpenAI TTS API ($15/1M chars, ~$0.005 per response)
   - Teacher suggestion (Carlos) — impressive demo feature
5. **Multi-language support** (Claude handles this natively)
6. **Video thumbnail display** in loaded videos list
7. **Export chat** as PDF or markdown
8. **Playlist support** — paste a YouTube playlist URL, load all videos
9. **Force re-embed button** — delete namespace and re-process video (handles stale cache from re-uploaded content)
10. **Axiom log persistence** — external log sink (free tier, 30 day retention). Fire-and-forget HTTP POST from `log_event()`. Survives container crashes/restarts. Local `events.log` stays for admin dashboard display, Axiom catches everything else.

---

## Future Improvements (if project takes off post-launch)

These are not bootcamp scope. They address known limitations that only matter at scale.

1. **Session persistence** — replace ephemeral `st.session_state` with external DB (Supabase/Turso free tier). Enables: surviving refresh, cross-device sessions, reliable rate limiting, user accounts
2. **User accounts + authentication** — email or OAuth login. Enables: persistent video libraries, usage history, contribution tracking
3. **BMC contribution tracking** — webhook from BMC to log contributions and notify via Discord. Key delivery is already automatic via thank-you page; webhook adds visibility.
4. **Server-side rate limiting** — IP-based or account-based limits via middleware. Prevents refresh exploit at scale
5. **Premium tier** — paid subscription for power users (higher limits, priority processing, longer videos, API access)
6. **CDN for landing page** — move static assets to Cloudflare/Vercel for global performance
7. **Horizontal scaling** — if concurrent users exceed 10-15: Koyeb paid tier (more RAM/CPU), multiple containers behind a load balancer, or split architecture (FastAPI backend + lightweight frontend). Only invest when monitoring shows consistent demand.
8. **Observability stack** — structured logging, error tracking (Sentry), uptime monitoring
9. **Stale cache detection** — version hash comparison (hash first chunk text, compare on reuse) to detect re-uploaded videos with changed transcripts
10. **Query-level caching** — hash (query + video_ids) → cached response. Prevents duplicate API calls for repeated questions. Not needed at bootcamp scale (10 question limit self-regulates).
11. **MemorySaver → SqliteSaver** — move conversation history to disk if RAM becomes tight at scale. Also enables history trimming (keep last N turns per session).
12. **Pinecone namespace cleanup** — scheduled job to delete namespaces older than N days (using `ingested_at` from metadata record). Prevents unbounded growth toward 2GB/100K vector limit. At ~205KB per video, ~10,000 videos fit before hitting cap — plenty for bootcamp, ticking clock at scale.
13. **Docker multi-stage build** — separate build stage (install deps) from runtime stage (copy only runtime artifacts). Reduces image size from ~500MB-1GB to ~300-400MB. Faster cold starts on Koyeb (image pulled on every container start).
14. **CI/CD pipeline** — GitHub Actions: lint → test → build → deploy to Koyeb. Staging environment before production. Automated rollback on health check failure.

