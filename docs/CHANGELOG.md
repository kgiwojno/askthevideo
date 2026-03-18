# Changelog

All notable changes to the AskTheVideo backend are documented here.

---

## 2026-03-18

### Added
- **Supabase `videos` table** — persistent video catalog tracking every video loaded (successes + failures)
  - `upsert_video()`, `record_video_error()`, `update_video_languages()`, `get_video_catalog()` in `src/metrics.py`
  - Background `ytt_api.list()` call on transcript fetch failures to log available languages
  - Video catalog exposed via admin metrics endpoint (`"videos"` array)
- **IP logging on all user-facing events** — SESSION start, TOOL calls/errors, uncaught 500s now include client IP
  - `get_or_create_session()` accepts `ip` parameter
  - `build_tools()` passes IP through to tool log events
- **Transcript language logging** — VIDEO event detail now includes `lang=` and `generated=` fields on new video loads

### Changed
- **Health endpoint** — `KOYEB_DEPLOYMENT_ID` → `KOYEB_INSTANCE_ID` (correct Koyeb env var name)

### Documentation
- Moved archived docs to `docs/archive/`: HANDOFF, DEVIATIONS, BUG_CASCADE_FAILURE, README
- Created this changelog (replaces per-deviation tracking going forward)

---

## 2026-03-15

### Added
- **Health endpoint version info** — returns `commit` (git SHA baked at Docker build time) and `deployment_id` (Koyeb instance ID)
  - Dockerfile updated to bake `.git_sha` at build time
- **Admin brute force detection** — escalating Discord alerts at 3/6/9+ failed admin logins per IP in 30-min window
- **Auth logging** — all access key and admin login attempts logged (AUTH/ADMIN events) with IP and success/fail
- **Color-coded Discord embeds** — 10 alert types with severity colors, environment footer, timestamp
  - Fixed Discord 403 by adding `User-Agent: AskTheVideo/1.0` header
- **Anonymous user tracking** — localStorage UUID + `X-User-ID` header + Supabase `users` table
- **Deploy script** — interactive menu (Frontend/Backend/Both/Cancel) with commit, push, optional Koyeb deploy
- **MIT License** — added with author Krzysztof Giwojno

### Changed
- **README** — complete rewrite with Author, Related Repositories, AI Assistance, License sections
- **Free tier limits** documented accurately (3 videos, 5 questions)
- `.env.example` and `.env.docker.example` created with all env vars

---

## 2026-03-11

### Added
- **Supabase persistent logging** — dual-write events + metrics snapshots, startup restore
- **Budget cycle tracking** — auto-detect $5 reloads, alert at 80% of each cycle
- **Slow query alert** — Discord notification when query exceeds 60s
- **Tool cascade failure fix** — all 5 tool wrappers catch exceptions, return error strings

### Initial release
- FastAPI backend with 5 AI tools (vector_search, summarize_video, list_topics, compare_videos, get_metadata)
- LangGraph agent with SSE streaming
- Pinecone vector store with namespace caching
- Webshare residential proxy for YouTube transcript fetching
- Admin panel with real-time metrics
- 51 unit tests + 15 smoke tests
