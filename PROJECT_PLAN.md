# Project Plan — YouTube Video QA Chatbot

## Project Info

- **Working name:** AskTheVideo (shortlisted, not final)
- **Team:** Solo — Krzysztof Giwojno
- **Bootcamp:** IronHack AI Engineering, Project III (Final)
- **Timeline:** ~7 working days
- **Deployment target:** OVH (landing) + Koyeb (app)

---

## Concept

A general-purpose YouTube video QA chatbot. Users paste any YouTube URL(s) and ask natural language questions about the content. The app retrieves relevant transcript segments and generates answers with citations (video title + timestamp links).

**Core problems solved:**
1. "I watched a video but can't find that one specific thing they said" → search + timestamp
2. "There are 50 videos on this topic, no time to watch them all" → synthesize across videos

---

## Architecture

```
User pastes YouTube URL(s)
        ↓
[youtube-transcript-api] → raw transcript with timestamps
        ↓
[LangChain text splitter] → time-based chunks (~60-90s with overlap)
        ↓
[Pinecone Inference — llama-text-embed-v2] → embeddings (free tier)
        ↓
[Pinecone DB] → stored in namespace per video (free tier)
        ↓
User asks a question
        ↓
[LangGraph Agent] → 5 tools: search, summarize, topics, compare, metadata
        ↓
[Anthropic Claude Sonnet 4.6] → generates answer with citations
        ↓
[Streamlit on Koyeb] → chat UI with clickable timestamp links
```

---

## Cost Breakdown

### Per-video costs (first time embedded)

| Action | Tokens | Cost |
|---|---|---|
| 10-min video embedding | ~2,400 tokens | Free (Pinecone Inference) |
| 30-min video embedding | ~7,400 tokens | Free (Pinecone Inference) |
| 60-min video embedding | ~14,700 tokens | Free (Pinecone Inference) |
| Storage in Pinecone | varies | Free (2GB limit) |

### Per-query costs (Claude Sonnet 4.6 — $3/$15 per MTok input/output)

| Action | Input tokens | Output tokens | Cost |
|---|---|---|---|
| vector_search (5 chunks + prompt + question) | ~2,000-3,000 | ~300-500 | ~$0.01-0.02 |
| summarize_video (all chunks, 60-min) | ~15,000 | ~500 | ~$0.05 |
| summarize_video (cached) | 0 | 0 | $0.00 |
| list_topics (all chunks, 60-min) | ~15,000 | ~500 | ~$0.05 |
| list_topics (cached) | 0 | 0 | $0.00 |
| compare_videos (2 videos, 5 chunks each) | ~4,000-5,000 | ~500 | ~$0.02 |
| get_metadata | 0 | 0 | $0.00 (no LLM) |

### Typical session estimate (one free user)

- Loads 3 videos (embedding: free)
- Asks 10 questions (~8 search, 1 summary, 1 topics)
- 8 × $0.015 + 1 × $0.05 + 1 × $0.05 = **~$0.22 per session (max)**
- Typical session (free user, 10 question limit): **~$0.15**

### Project budget

| Scenario | Estimate |
|---|---|
| Development testing (~50 queries) | ~$1.00 |
| LangSmith eval (15 pairs × 3 runs) | ~$0.70 |
| Live demo (presentation day) | ~$0.50 |
| 20 real users × 1 session each | ~$3.00 |
| **Total realistic budget** | **~$5-7** |

### Monthly free tier headroom (at 20 users/day)

| Resource | Limit | Estimated usage | Status |
|---|---|---|---|
| Pinecone Inference | 5M tokens/mo | ~1.5M/mo | ✅ |
| Pinecone reads | 1M/mo | ~6K/mo | ✅ |
| Pinecone writes | 2M/mo | ~3K/mo | ✅ |
| Pinecone storage | 2GB | hundreds of videos | ✅ |
| LangSmith traces | 5K/mo | ~600/mo | ✅ |

**Bottom line:** Only real cost is Anthropic API credits (~$7-10 total). Everything else within free tiers.

### Server resources (Koyeb free tier)

| Resource | Limit | Estimated need |
|---|---|---|
| RAM | 512 MB | ~300-500 MB (unvalidated — test day 1) |
| CPU | 0.1 vCPU | Sufficient (thin orchestration layer) |
| Disk | 2 GB | ~500 MB (code + deps) |

**Key insight:** Pinecone handles vectors, embeddings, and cached summaries. Server is just orchestration.

---

## Components

### 1. Transcript Pipeline
- **Library:** youtube-transcript-api
- **Input:** YouTube URL(s)
- **Output:** Raw transcript with timestamps
- **No-transcript handling:** Error message + skip. Stretch goal: Whisper API fallback (Groq free or OpenAI) if time allows

### 2. Chunking
- **Library:** LangChain text splitters
- **Strategy:** Time-based (~60-90 second windows with overlap)
- **Reasoning:** Keeps chunks aligned with video timeline, makes timestamp citations clean
- **Metadata per chunk:** video_id, video_title, start_timestamp, end_timestamp, chunk_index, channel_name
- **Token output:** ~160-400 tokens per chunk depending on speaker pace (see analysis below)
- **Pinecone recommendation:** 400-500 tokens per chunk for llama-text-embed-v2
- **Plan:** Start with 60-90s, test retrieval quality, increase to 120-150s if needed

**Chunk size analysis:**

| Speaker pace | Words/min | 60s chunk | 90s chunk | 120s chunk | 150s chunk |
|---|---|---|---|---|---|
| Slow (tutorials) | ~120 wpm | ~160 tok | ~240 tok | ~320 tok | ~400 tok |
| Normal (interviews) | ~150 wpm | ~200 tok | ~300 tok | ~400 tok | ~500 tok |
| Fast (lectures) | ~180-200 wpm | ~250 tok | ~375 tok | ~500 tok | ~625 tok |

Current 60-90s windows produce chunks mostly below Pinecone's 400-500 recommendation. However, spoken transcripts have lower semantic density than academic text (filler words, repetition, simpler sentences), so fewer tokens may still capture meaning well. Smaller chunks also give more precise timestamp citations — a key feature. Will test and adjust during development.

### 3. Embeddings
- **Choice:** Pinecone Inference API — `llama-text-embed-v2`
- **Free tier:** 5M tokens/mo (sufficient for hundreds of videos)
- **Model specs:** Up to 2048 tokens per chunk, variable dimensions (384-2048), multilingual
- **Dimension: 1024** (model default)
- **Speed:** ~100-500ms per batch (up to 96 items), full video ingestion 3-6 seconds
- **Reasoning:** Higher retrieval quality than e5-large, supports longer chunks

**Why 1024 and not 2048?**
The model uses Matryoshka Representation Learning — lower dimensions are the first N values of the full 2048 vector, not a retrained model. At 1024, retrieval quality is ~98-99% of full 2048 baseline.

| Dimension | Storage per video (50 chunks) | Videos in 2GB | Quality vs 2048 |
|---|---|---|---|
| 384 | ~77 KB | ~26,000 | ~90-93% |
| 768 | ~154 KB | ~13,000 | ~95-97% |
| **1024** | **~205 KB** | **~10,000** | **~98-99%** |
| 2048 | ~410 KB | ~5,000 | 100% |

Decision factors:
- 1024 is the Pinecone default — best tested, zero-config with `create_index_for_model`
- Community reports show 2048 can be finicky to configure (API returns 1024 regardless of parameter in some SDK versions)
- Content is spoken language transcripts, not dense technical text — last 1-2% quality is imperceptible
- Storage headroom is massive at 1024 (~10,000 videos in 2GB) — no need to optimize further
- Search speed at our scale (hundreds of vectors) is negligible at any dimension

### 4. Vector Database
- **Choice:** Pinecone (free tier — cloud hosted)
- **Free tier:** 5 indexes, 100 namespaces each, 2GB storage, 2M writes/mo, 1M reads/mo
- **Embeddings:** Handled by Pinecone Inference API (llama-text-embed-v2)
- **Namespace strategy:** One namespace per video_id (clean separation)
- **Cross-user reuse:** Fetch `{video_id}_metadata` by ID → if exists, reuse (instant). If not, embed new video.
- **Deletion:** Session-only — "delete" removes from user's session, vectors persist in Pinecone for reuse by other users
- **Special records per namespace:** `_metadata` (created at ingestion), `_summary` (cached on first request), `_topics` (cached on first request) — all zero-vector with data in metadata fields
- **Query approach:** Sequential per-namespace queries, fixed per-video allocation: `max(3, 10 // n_videos)`. Pinecone doesn't support cross-namespace queries — design around it.
- **Note:** Indexes pause after 3 weeks of inactivity on free tier

### 5. LLM
- **Provider:** Anthropic (own credits)
- **Model:** Claude Sonnet 4.6 (`claude-sonnet-4-6`)
- **Released:** February 17, 2026 — latest Sonnet, near-Opus quality at Sonnet pricing
- **Pricing:** $3/$15 per million input/output tokens (same as Sonnet 4.5)
- **Context:** 200K tokens (1M in beta)
- **Max output:** 64K tokens
- **Estimated cost:** ~$0.01-0.05 per query, ~$5-7 total for project lifecycle (see Cost Breakdown)
- **Optional features:** Adaptive thinking, effort parameter (medium for most queries)
- **Requires:** `langchain-anthropic>=1.3.0`

### 6. LangChain + LangGraph Agent

**Framework relationship:**
```
LangChain (foundation)
├── LLM wrappers (ChatAnthropic)
├── Tools (@tool decorator)
├── Text splitters (chunking)
├── Vector store integrations (Pinecone)
├── Prompts, chains, LCEL
│
└── LangGraph (agent layer, built on top of LangChain)
    ├── create_react_agent() — agent that decides which tool to use
    ├── MemorySaver — conversation persistence
    ├── Graph-based execution (nodes, edges, state)
    └── Tool routing + multi-step reasoning
```

- **LangChain provides:** LLM wrappers, tool definitions, Pinecone integration, text splitters
- **LangGraph provides:** Agent orchestration, tool routing, conversation memory
- **Tools:**
  - **Vector search** — retrieve relevant chunks from Pinecone for Q&A
  - **Summarize video** — generate a full summary of a loaded video
  - **List key topics** — extract main topics/themes from a video
  - **Compare across videos** — synthesize answers from multiple videos on same topic
  - **Get video metadata** — return title, channel, duration, date, URL
- **Memory:** LangGraph `MemorySaver` (in-memory, per-session conversation history)

### 7. Frontend
- **Framework:** Streamlit
- **Features (planned):**
  - URL input (sidebar or main)
  - Chat interface (st.chat_message / st.chat_input)
  - Processing status / progress indicator
  - Clickable timestamp links in answers
  - Video library / history of loaded videos

### 8. Deployment
- **Landing page:** Static HTML/CSS/JS on OVH PHP hosting (`yourdomain.com`)
- **App:** Streamlit on Koyeb free tier (`app.yourdomain.com`)
  - 512MB RAM, 0.1 vCPU, 2GB SSD
  - Custom subdomain via CNAME
  - Docker deployment (Dockerfile in repo)
  - Frankfurt or Washington D.C. region
- **Fallback plan:** Split architecture
  - OVH serves JS/HTML frontend (chat UI) instead of landing page
  - Koyeb runs Python backend API (FastAPI/Flask)
  - Only switch if Koyeb Streamlit causes issues
- **DNS:** `yourdomain.com` → OVH, `app.yourdomain.com` → CNAME to Koyeb
- **Cold start mitigation:** Landing page pre-warms Koyeb + Pinecone in background on page load. Holding page with spinner for fast clickers. See SYSTEM_DESIGN.md Part 10.

### 8b. Landing Page
- **Host:** OVH PHP hosting (static HTML/CSS/JS)
- **URL:** `yourdomain.com`
- **Visual style:** TBD (decide before building)
- **SEO:** Semantic HTML, meta tags, Open Graph, structured data
- **Google Analytics:** Shared with app

### 9. Error Handling & Monitoring
- **Architecture:** 4 severity levels (Expected, Transient, Critical, Unknown) — see SYSTEM_DESIGN.md Part 8
- **Developer alerts:** Discord webhook for critical errors (credit exhaustion, free tier limits, unhandled exceptions)
- **Retry policy:** 1 retry for transient errors (Pinecone, Anthropic), no retry for expected errors
- **Global catcher:** `safe_execute()` wrapper catches unhandled exceptions → log + notify + generic user message
- **LangSmith:** Silent failure — tracing never blocks the app
- **Logging:** Python `logging` module to stdout (Koyeb captures container logs)
- **Sections:**
  1. Hero — headline + subheadline + CTA "Try the App →"
  2. How It Works — 3-step visual (paste URL → ask question → get answer)
  3. Feature Highlights — search, summarize, compare, topics, metadata
  4. Cost Transparency — free tier limits, why it costs, what you get
  5. Support the Project — Buy Me a Coffee
  6. About the Project — IronHack bootcamp, tech stack, learnings
  7. About You — brief bio, GitHub, LinkedIn
  8. FAQ — common questions
  9. Footer — links, credits, CTA repeat

### 9. LangSmith
- **Usage:** Tracing agent calls, evaluating answer quality
- **Eval approach:** 10-15 test Q&A pairs across 3-4 videos, manual scoring of relevance + accuracy
- **Detail:** Finalize when building

---

## Requirements Mapping

| Project Requirement | Implementation | Status |
|---|---|---|
| RAG system | Pinecone retrieval → Claude Sonnet 4.6 generation | DECIDED |
| Vector database | Pinecone (free tier) + Pinecone Inference embeddings | DECIDED |
| LangChain agents + tools | LangGraph agent (create_react_agent) with 5 LangChain tools | DECIDED |
| Memory | LangGraph MemorySaver (in-memory, per-session) | DECIDED |
| Speech recognition / multimodal | Transcript extraction from video (audio→text) | PLANNED |
| Web app deployment | Landing on OVH + Streamlit on Koyeb (app.subdomain) | DECIDED |
| LangSmith testing + eval | Tracing + 10-15 test Q&A pairs | PLANNED |
| Documentation | README + PDF report + slides | PLANNED |

---

## Decision Log

| # | Decision | Choice | Reasoning | Date |
|---|---|---|---|---|
| 1 | Topic/niche | General-purpose (any YouTube URL) | More useful, better demo, stronger portfolio piece | — |
| 2 | Voice input | No (text-only) | Simpler scope for 7 days solo | — |
| 3 | Language | English only | Simpler scope | — |
| 4 | Frontend | Streamlit | Fastest to build, built-in chat UI, pure Python | — |
| 5 | Vector DB | Pinecone (free tier, cloud) | Offloads storage+search from server, 2GB free | — |
| 6 | LLM provider | Anthropic (own credits) | Full control, no shared class limits | — |
| 7 | Embedding model | Pinecone Inference — llama-text-embed-v2, 1024 dimensions | Default dim, 98-99% of full 2048 quality, zero-config, no API quirks. Spoken transcripts don't need last 1-2% | — |
| 8 | Claude model tier | Sonnet 4.6 (`claude-sonnet-4-6`) | Latest model (Feb 17, 2026), near-Opus quality at Sonnet price, better instruction following, fewer hallucinations | — |
| 9 | Chunking strategy | Time-based (~60-90s, start here, increase to 120-150s if retrieval quality is poor) | Aligns with video timeline, clean timestamp citations. Test-driven tuning | — |
| 10 | Hosting platform | OVH (landing page) + Koyeb free (app) | Landing page gets real SEO on OVH, app runs on Koyeb with 512MB | — |
| 11 | Domain structure | yourdomain.com (landing) + app.yourdomain.com (app) | Clean separation, proper SEO for landing page | — |
| 12 | Pinecone namespaces | One per video | Clean separation, easy reuse across users | — |
| 12b | No-transcript handling | Error+skip (Whisper API as stretch goal) | Covers 90%+ of videos, saves time, add Whisper only if time allows | — |
| 13 | Agent tools | 5 tools: search, summarize, topics, compare, metadata | Covers both core problems + impressive demo | — |
| 14 | App name | AskTheVideo (askthevideo.com) | Domain purchased, name locked in | NB06 |
| 15 | Question limits | 10 per session (not per video), tracked in session state | Simpler model, controls cost, avoids cross-video counting ambiguity | — |
| 16 | Video limits | 5 videos per session (unlimited with key) | Prevents abuse, free tier cost control | — |
| 17 | Cross-user reuse | Check namespace exists → reuse, skip re-embedding | Saves tokens, instant load for repeat videos | — |
| 18 | Video deletion | Session-only (vectors persist in Pinecone for reuse) | Simplest approach, benefits other users | — |
| 19 | Unlimited access | 1 shared key, no expiry, auto-delivered via BMC thank-you message | Sidebar input only (no URL param — safe on shared computers). Usage monitoring + Discord alert. Rotate via Koyeb env var if abused | — |
| 20 | Analytics | Google Analytics (build it) | Visitor tracking, useful for presentation | — |
| 21 | Ads | Google AdSense — stretch goal (build if time), presentation slide regardless | Break-even at ~50 users/day, combined with BMC makes project self-sustaining | — |
| 22 | Buy Me a Coffee | Build it (link in sidebar/footer) | Zero effort, real monetization option | — |
| 23 | Feedback form | Google Forms (external link) | Zero backend, responses in Google Sheets | — |
| 24 | Video duration cap | 60 min (free), unlimited (contributors) | Controls token cost on summarize/topics tools | — |
| 25 | Summary/topics caching | Pinecone special records ({video_id}_summary) | Zero-vector records, text in metadata. Persistent, cross-user, no extra infra | — |
| 26 | Session persistence | Accept ephemeral — deliberate trade-off | $0.15/reset not worth 4-6hrs dev. Video reuse mitigates. Future: external DB | — |
| 27 | Embedding dimension | 1024 (model default) | Matryoshka = 98-99% of 2048 quality. Zero-config, no API bugs. Spoken transcripts don't need last 1-2% | — |
| 28 | Chunk size strategy | Start 60-90s, test, increase if needed | Below Pinecone's 400-500 token recommendation but spoken language = lower density. Smaller chunks = more precise timestamps. Test-driven decision | — |
| 29 | Cross-namespace queries | Sequential per-namespace + fixed per-video top-k allocation | Pinecone can't query across namespaces. Loop + merge. max(3, 10//n) per video. No cap. | — |
| 30 | Video metadata on reuse | Store `{video_id}_metadata` record in Pinecone (zero vector) | Fetch by ID on reuse — instant. Same pattern as _summary/_topics. Also used by get_metadata tool | — |
| 31 | Tool routing | Handle during agent build — precise descriptions + LangSmith eval | Not a design decision. vector_search as fallback if uncertain | — |
| 32 | youtube-transcript-api risk | Accept, pin version, document yt-dlp backup | Standard approach, no better free alternative. Mention in presentation | — |
| 33 | Health check | Streamlit HTTP 200 on `/` + Koyeb config | Verify during day 1 deployment | — |
| 34 | Stale cache | Accept for bootcamp. Force re-embed as stretch goal | Rare edge case. Post-bootcamp: version hash comparison | — |
| 35 | Error handling | Full architecture: 4 severity levels, per-service error tables, global catcher | Document now, implement during build. See SYSTEM_DESIGN.md Part 8 | — |
| 36 | Critical error notification | Discord webhook | Real-time, one line of code, free. Covers credit exhaustion, free tier limits, unhandled exceptions | — |
| 37 | Cold start mitigation | Landing page pre-warm + holding page + auto-redirect | No cron job. JS pings Koyeb on page load, Koyeb startup pings Pinecone. Holding page for fast clickers | — |
| 38 | Pinecone index pausing | Solved by pre-warm (#37) | Koyeb startup calls describe_index_stats(). Any landing page visit keeps Pinecone alive | — |
| 39 | MemorySaver RAM | Accept ephemeral, no cap needed | ~100KB per session (10 turns). 50 concurrent = 5MB = 1% of budget. Container restarts clear all | — |
| 40 | Query caching | Not built — document as future improvement | LLM references prior answers naturally. 10-question limit prevents waste. ~$0.015 per duplicate not worth optimizing | — |
| 41 | Concurrent users | Accept for bootcamp. Streamlit config + session monitoring + Discord alert | 5-10 concurrent fine. Demo from own session. Future: horizontal scaling if monitoring shows demand | — |
| 42 | Voice input (stretch) | Browser Web Speech API (free) or Whisper API ($0.006/min) | Teacher suggestion (Carlos). Impressive demo feature, low effort if using browser API | — |
| 43 | Voice output with character voices (stretch) | ElevenLabs (free 10K chars/mo) or OpenAI TTS ($0.005/response) | Teacher suggestion (Carlos). Flashiest demo feature — answers read aloud in a selected voice | — |
| 44 | Access key flow | 1 shared key, sidebar only, BMC auto-delivery | No URL param (shared computer risk). Usage monitoring + Discord alert at 50 queries/day. Rotate if abused | — |
| 45 | Observability / admin dashboard | Full admin page: real-time, session stats, API cost tracker, Pinecone, event log, external links | Auto-refresh 30s. Token tracking via LangChain callback. Rotating event log (500KB) with IP, 6 event types. No in-memory buffer — file-based | — |
| 46 | Log persistence | Stretch goal: Axiom free tier (30 day retention, HTTP POST) | Local events.log is ephemeral (dies with container). Axiom catches crashes/restarts. Discord alerts stay problem-only | — |
| 47 | Input validation | URL whitelist + video ID regex + question length cap (500 chars) | Prevents injection, non-YouTube URLs, oversized inputs. Design in SYSTEM_DESIGN Part 5, build during implementation | — |
| 48 | GDPR/privacy | Partial compliance: anonymize IPs (truncate last octet), privacy note on landing page | Full remediation (cookie consent, privacy policy, Anthropic DPA) documented as future work | — |
| 49 | YouTube ToS risk | Accept for bootcamp, document as known limitation | youtube-transcript-api scrapes internal endpoint. Document yt-dlp backup. Production: migrate to official API | — |
| 50 | Streamlit error info leak | Add `showErrorDetails = false` to config.toml | Prevents stack traces from exposing env vars/API keys in production | — |
| 51 | Testing strategy | Document test cases, implement unit tests for validation + cost calc | Full test strategy in SYSTEM_DESIGN Part 13. Agent routing tests manual during dev | — |
| 52 | Scaling roadmap | 4-phase plan documented | Phase 1: current. Phase 2: auth + paid Koyeb. Phase 3: FastAPI split. Phase 4: full SaaS. See SYSTEM_DESIGN Part 14 | — |
| 53 | Pinecone namespace cleanup | Future improvement — TTL-based cleanup using ingested_at | ~10K videos before hitting 2GB cap. No urgency at bootcamp scale | — |
| 54 | Docker image optimization | Future improvement — multi-stage build | Reduces image size, faster cold starts on Koyeb | — |
| 55 | Development workflow | Notebooks first → extract to .py | 6 notebooks validate components against real data before production code. Matches bootcamp workflow. See SYSTEM_DESIGN Part 13 | — |
| 56 | Code extraction | Automated: `# @export` cell tags + extract.py script + Makefile | No manual copy-paste. `make all` runs extract → format → lint → test. .py headers reference source notebook | — |
| 57 | Build approach | Hybrid: Claude.ai chat for notebooks (learning), Claude Code for production assembly | Notebooks = exploration + guided discovery. Production .py files = mechanical assembly. Switch point: after all 6 notebooks validated | — |
| 58 | Python version | 3.12 (not 3.14) | Python 3.14 incompatible: langchain/pinecone ecosystem caps at `<3.14`, simsimd has no compatible version. 3.12 has widest ML/AI library support | — |
| 59 | youtube-transcript-api | v1.0+ breaking change: instantiate `YouTubeTranscriptApi()`, use `.fetch()` not `.get_transcript()` | Returns `FetchedTranscript` with `.snippets` (list of `FetchedTranscriptSnippet` with `.text`, `.start`, `.duration`), `.language`, `.is_generated`. Old class-method API removed | — |

---

## Open Questions

1. Koyeb 512MB RAM — need to keep Streamlit + deps lean, test early
2. App name — AskTheVideo shortlisted, decide before deployment
3. LangSmith eval — finalize test Q&A set when building
4. Overlap size for time-based chunks — how many seconds of overlap between windows?
5. Chunk size tuning — start with 60-90s, test retrieval quality, increase to 120-150s if poor. Pinecone recommends 400-500 tokens; our 60-90s windows produce ~160-400 tokens. Decision: test-driven.

---

## Known Limitations (deliberate trade-offs)

| Limitation | Why accepted | Impact | Future fix |
|---|---|---|---|
| Session resets on refresh | Every fix costs 3-6 hours for a <$1 problem | User re-enters videos (instant reload from cache) + question count resets | External DB (Supabase/Turso) |
| Question limit bypassable via refresh | $0.15 per reset, not financially significant at bootcamp scale | Negligible cost exposure | Server-side rate limiting |
| Chat history lost on refresh | Ephemeral by design, aligns with session model | User starts conversation fresh | Session persistence via DB |
| Single container, limited concurrency | Streamlit handles 5-10 concurrent fine (I/O-bound) | Degrades above 10-15 concurrent users | Horizontal scaling, paid tier |
| Event log lost on container restart | Koyeb free tier has no persistent storage | No crash investigation trail | Axiom external log sink (stretch goal) |
| youtube-transcript-api dependency | Standard approach, no better free alternative | If library breaks, app can't fetch transcripts | yt-dlp as documented backup |
| Stale cache on video re-upload | Rare edge case (same URL, different content) | Outdated answers from old transcript | Force re-embed button + version hash comparison |
| GDPR partial compliance | Bootcamp project, not commercial. IP logged truncated. | No cookie consent for GA, no formal privacy policy | Full GDPR remediation (cookie consent, privacy policy, DPA with Anthropic) |
| YouTube ToS risk (transcript scraping) | youtube-transcript-api scrapes internal endpoint, not official API | YouTube could block or change endpoint | Migrate to YouTube Data API v3 + Whisper for transcription |
| No automated tests | Time constraint — design docs cover test cases | Bugs caught manually during development | pytest suite with CI/CD pipeline |
| Pinecone namespaces grow unbounded | No cleanup mechanism. ~205KB per video, 10K fit in 2GB | Ticking clock at scale (months/years) | Namespace TTL cleanup job using `ingested_at` metadata |
| No input validation against abuse | URL validation + question length limit designed but not yet built | Injection, oversized inputs, non-YouTube URLs | Build validation during implementation (Part 5 design ready) |

---

## Deliverables Checklist

| Deliverable | Status | File |
|---|---|---|
| Source code | ☐ | webapp/ |
| README.md | ☐ | README.md |
| PDF Report | ☐ | docs/ |
| Presentation (PPTX) | ☐ | docs/ |
| Speaker notes | ☐ | docs/ |
| Demo (video/live) | ☐ | extras/ |
| LinkedIn post | ☐ | extras/ |
| Deployed web app | ☐ | OVH (landing) + Koyeb (app) |
| Landing page | ☐ | OVH hosting |

---

## Quality Standards (from Past Project Feedback)

Based on instructor feedback from Projects 2 and 3. Strengths to maintain and weaknesses to fix.

### ✅ MAINTAIN — Scored well, keep doing this

**Presentation:**
- Executive summary at the start (best presentation in cohort)
- Detailed cost and time analysis per model/approach
- Informative confusion matrices with detailed legends (misclassifications, TP, TN)
- Thorough data preprocessing and EDA coverage

**Code:**
- Excellent README with full project summary
- Correct preprocessing and model training methodology
- Good exploration of different models/approaches
- Clear understanding of what each step does and why

### 🔧 FIX — Flagged for improvement

**Notebook structure:**
- Use markdown cells with `#`, `##`, `###` headings to create clear sections
- Add text cells between code blocks explaining the reasoning / line of thought
- Anyone reading the notebook should be able to follow the logic without running code
- Target: every code cell or group of related cells should have a markdown cell above it

### Applied to This Project

| Standard | How to apply |
|---|---|
| Executive summary | First slide: what it does, who it's for, one-line result |
| Cost/time analysis | Show API costs per query, embedding costs, free tier math |
| Detailed evaluation | LangSmith eval results with breakdown by question type |
| Strong README | Follow established template, include architecture diagram |
| Model exploration | Document why Claude Sonnet 4.6, why llama-text-embed-v2 |
| **Notebook structure** | **Every notebook: markdown sections + reasoning cells** |
| EDA/preprocessing | Show transcript analysis, chunk distribution, edge cases |

---

## Monetization & Extras

### Question & Video Limits
- **Free tier:** 10 questions per session, 5 videos per session, max 60-min video duration
- **Unlimited (with key):** No video limit, no question limit, no duration limit
- **Tracking:** Streamlit session state per session
- **Unlimited access:** Sidebar key input only (no URL parameter — safe on shared/public computers)
  - 1 shared key (e.g., `ASKTHEVIDEO2026`), auto-delivered via BMC custom thank-you message
  - No expiry — rotate manually via Koyeb env var if abused
  - Usage monitoring: log all unlimited queries, Discord alert if daily threshold (50) exceeded
- **Valid keys:** Stored in `VALID_ACCESS_KEYS` environment variable on Koyeb

### Analytics
- **Google Analytics** — inject GA tracking script via `st.components.v1.html()`
- **Purpose:** Visitor counts, geography, usage patterns — useful for presentation

### Feedback
- **Google Forms** — external link in sidebar or footer
- **Zero backend work** — responses collected in Google Sheets automatically
- **Purpose:** User feedback for presentation + future improvements

### Monetization
- **Built:** "Buy Me a Coffee" link — landing page + app sidebar
- **Stretch goal:** Google AdSense — landing page + app (implement if time allows)
- **Presentation:** Full monetization projection slide (break-even analysis, combined revenue model, path to self-sustaining) — see COST_BREAKDOWN.md

---

## Running Notes

*(Add notes during development — metrics, issues, pivots)*

---

*Last updated: brainstorm phase*
| 65 | LangSmith endpoint | EU endpoint (`https://eu.api.smith.langchain.com`) | Account hosted in EU. Default US endpoint returns 403. Add `LANGSMITH_ENDPOINT` to `.env` | NB05 |
| 66 | Query chunk filter | `type == "chunk"` (not `!= "metadata"`) | Sentinel records for summary/topics also lack chunk fields (start_display, etc.). Explicit chunk filter prevents KeyError and ensures only real chunks returned | NB06 |
| 67 | Ingestion cache check | Check namespace exists + metadata record before re-embedding | Cache hit returns in 0.4s vs 2-4s for fresh ingestion. Cross-user reuse works automatically | NB06 |
| 68 | Voice input | Browser Web Speech API with feature detection | Free, zero backend. Mic button shown only on supported browsers (Chrome, Edge, Safari). Firefox users see no button. Graceful degradation. Carlos suggestion | — |
| 69 | Video thumbnails | Display oEmbed thumbnail_url in video list | Already returned by API, pure frontend, makes video list look professional | — |
| 70 | Chat export | Client-side markdown file download | Pure frontend, no API needed. Users can save research. Good demo feature | — |
| 71 | Voice output | Browser SpeechSynthesis API with read-aloud button | Free, zero backend. Speaker icon on each assistant message. Feature detection for unsupported browsers | — |
| 72 | Streaming responses | SSE endpoint POST /api/ask/stream | FastAPI EventSourceResponse. Answer streams word-by-word instead of 20s spinner. Major UX improvement | — |
| 73 | Frontend framework | React (Lovable) + FastAPI backend | Replaced Streamlit. Full design control, lower memory (~35MB vs ~90MB), better UX | — |
