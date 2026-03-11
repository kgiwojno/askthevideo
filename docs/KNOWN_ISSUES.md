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
