# AskTheVideo — Known Issues & Future Improvements

Non-critical issues identified during final review. Documented here for future reference.

---

## 1. Hardcoded model name in `src/agent.py`

**Location:** `src/agent.py:46` (generated from `notebooks/05_agent_routing.ipynb`, cell `002aba9d`)

**Issue:** Model name is hardcoded as `"claude-sonnet-4-6"` instead of importing `CLAUDE_MODEL` from `config/settings.py`.

**Impact:** If the model is changed in `config/settings.py`, the agent will still use the old model.

**Why not fixed now:** `src/agent.py` is auto-generated from the notebook `@export` cell. The notebook needs `CLAUDE_MODEL` defined locally to run standalone in Jupyter. Importing from `config/settings` inside the `@export` cell would work for production but would require `sys.path` manipulation in the notebook.

**Future fix:** Add `from config.settings import CLAUDE_MODEL` to the `@export` cell and use it in `create_askthevideo_agent()`. The `sys.path` cell already exists in the notebook for this purpose.

---

## 2. Duplicate constants across generated files

**Locations:**
- `config/settings.py` — intended source of truth
- `src/tools.py:16-19` (from notebook 04) — `CLAUDE_MODEL`, `EMBED_MODEL`, `EMBED_BATCH_SIZE`, `SENTINEL_VECTOR`
- `src/vectorstore.py:15-17` (from notebook 03) — `EMBED_MODEL`, `EMBED_BATCH_SIZE`, `SENTINEL_VECTOR`

**Issue:** Same constants defined in 3 places. If `config/settings.py` is updated, the generated files won't reflect the change until the notebooks are also updated and re-extracted.

**Impact:** Low — all three locations currently have identical values. Risk is drift on future model/config changes.

**Why not fixed now:** Same as #1. Notebooks need to be self-contained for Jupyter execution. The exploration cells define these constants locally, and the `@export` cells inherit them.

**Future fix:** Refactor `@export` cells to import from `config.settings` instead of defining locally. Requires updating notebooks 03, 04, and 05 and ensuring `sys.path` is set before each `@export` cell.

---

## 3. Unused `APP_URL` constant

**Location:** `config/settings.py:15`

**Issue:** `APP_URL = "https://app.askthevideo.com"` is defined but never referenced in any Python code.

**Impact:** None — dead code.

**Why not fixed now:** Already documented as deviation #28. Kept intentionally for potential future use (e.g., Discord alert messages with app links, health check pings for Koyeb free tier).

**Future fix:** Either use it in Discord alerts or remove it.

---

## 4. Notebook execution requires manual `sys.path` cells

**Locations:** Notebooks 04 and 05, cells added before `@export` cells.

**Issue:** Production `@export` cells import from `src.*` which requires the project root on `sys.path`. When running from `notebooks/` directory in Jupyter, this fails without a manual `import sys; sys.path.insert(0, "..")` cell.

**Impact:** None on production. Minor inconvenience for notebook re-runs — if someone forgets to run the `sys.path` cell first, the `@export` cell fails with `ModuleNotFoundError`.

**Why not fixed now:** This is inherent to the notebook-first architecture. The `sys.path` cells are clearly labeled and placed immediately before the `@export` cells.

**Future fix:** Could add a shared `notebooks/setup.py` helper that all notebooks import at the top, or use `%cd ..` magic in each notebook.

---

## 5. Agent-level LLM failure not covered by tool error handling

**Location:** `api/routes/ask.py` — the `except Exception` blocks in `/ask` (line 126) and `/ask/stream` (line 194)

**Issue:** The cascade failure fix (deviation #30) only covers tool-level exceptions. If the agent's own routing LLM call fails (e.g., Anthropic API is completely down, not just rate-limited), the exception happens *before* any `tool_use` is emitted, so it doesn't corrupt MemorySaver state. However, if a failure occurs *after* the agent emits a `tool_use` but *before* the tool executes (an unlikely but theoretically possible race condition in LangGraph internals), the dangling `tool_use` problem could still occur.

**Impact:** Very low — this scenario requires a failure in the narrow window between LangGraph emitting the tool call and executing it. In practice, tool-level errors (rate limits, timeouts) are the real trigger, and those are now fully handled.

**Why not fixed now:** The current fix covers all observed failure modes. The edge case is theoretical and would require modifying MemorySaver internals or resetting the thread_id as a fallback, which loses conversation context.

**Future fix:** If this edge case is ever observed in production, add a fallback in the `except Exception` block that checks the MemorySaver state for dangling `tool_use` messages and either injects a synthetic `ToolMessage` or resets the thread_id. Monitor via the existing Discord alerting (`uncaught_500` alert type) — if sessions start breaking without tool-level errors in the event log, this edge case is the likely cause.

---

## 6. `datetime.utcnow()` deprecation warnings in session management

**Location:** `api/session.py:15`

**Issue:** Python 3.12 deprecates `datetime.datetime.utcnow()` in favor of `datetime.datetime.now(datetime.UTC)`. The test suite shows 18 `DeprecationWarning` instances from this call.

**Impact:** None currently — the function works correctly. Will break in a future Python version when `utcnow()` is removed.

**Why not fixed now:** Cosmetic warning only. No functional impact.

**Future fix:** Replace `datetime.utcnow()` with `datetime.now(datetime.UTC)` in `api/session.py` and `tests/test_session.py`.

---

## 7. No returning user identification across sessions

**Location:** `api/session.py` — sessions are ephemeral (in-memory, 2-hour TTL, no persistence)

**Issue:** There is no way to identify returning users across sessions. Each page load or session expiry creates a brand new session with no link to previous visits. Usage analytics (session depth, tool distribution, video loads) are all per-session with no user-level aggregation.

**Impact:** None for current demo/portfolio use. Becomes important for commercial use — can't answer questions like "how many unique users?", "do users come back?", "what's the average sessions per user?".

**Why not fixed now:** Out of scope for the current project phase. Would require persistent user identification (cookies, fingerprinting, or auth) and a user-level data model.

**Future fix (commercial):**
- Add a persistent anonymous user ID via a long-lived cookie (e.g. `atv_uid` UUID, 1-year expiry)
- Store in a Supabase `users` table with `first_seen`, `last_seen`, `total_sessions`, `total_questions`
- Link events to user ID for user-level analytics (retention, engagement, conversion from free to paid)
- If auth is added (e.g. email login for paid tier), merge anonymous sessions into the authenticated user profile
