# Bug Fix: Corrupted Conversation History on Tool Failure

**Status: FIXED**

## Bug description

When a tool call fails mid-execution (e.g., Anthropic API rate limit 429, timeout, or any exception), the conversation history stored in MemorySaver contains a `tool_use` message without a corresponding `tool_result`. Every subsequent question in the same session then fails with:

```
messages.N: `tool_use` ids were found without `tool_result` blocks immediately after: toolu_XXXX
```

This cascading failure makes the entire session unusable after a single tool error.

## How to reproduce (before fix)

1. Load two 3-hour videos
2. Ask 10+ questions rapidly (1-second gaps)
3. When a question triggers `list_topics` or `summarize_video` (which send all chunks to Claude), the Anthropic API returns 429 rate limit
4. The tool_use block is saved to MemorySaver but no tool_result follows
5. All subsequent questions fail with the `tool_use` without `tool_result` error

## Root cause

The agent's error handling does not inject a `tool_result` into the conversation history when a tool call raises an exception. The Anthropic API requires every `tool_use` message to be followed by a `tool_result` in the next message. When the tool fails, MemorySaver has already recorded the `tool_use` but there is no `tool_result` to match it.

## Fix applied

**Approach:** Tools never raise — all 5 LangChain `@tool` wrappers in `api/routes/ask.py` (`build_tools()`) catch exceptions and return an error string instead of propagating the exception.

**File modified:** `api/routes/ask.py` — `build_tools()` function only. No changes to `src/tools.py`, `src/agent.py`, notebooks, or any Phase 1 code.

**Before:**
```python
@tool
def vector_search(question: str) -> str:
    """Search transcript chunks..."""
    result = _vector_search(pc, index, anthropic_client, question, selected_videos)
    return result.get("answer", "No relevant content found.")
```

**After:**
```python
@tool
def vector_search(question: str) -> str:
    """Search transcript chunks..."""
    try:
        result = _vector_search(pc, index, anthropic_client, question, selected_videos)
        return result.get("answer", "No relevant content found.")
    except Exception as e:
        log_event("ERROR", "tool", "—", f"vector_search: {type(e).__name__}: {str(e)[:80]}")
        return f"Sorry, I couldn't complete the search right now. Error: {type(e).__name__}"
```

**Why this works:** From MemorySaver's perspective, the conversation is always valid — every `tool_use` gets a `tool_result` (the error string). The agent sees the error as a normal tool response and relays it naturally to the user. Conversation context is fully preserved for subsequent questions.

**What the user sees:** The agent responds with something like "I'm having trouble right now, the search tool returned an error. Please try again." — then the next question works normally.

## Options considered

| Option | Description | Chosen? | Why |
|--------|-------------|---------|-----|
| **Tool-level try/except** | Wrap each tool so it never raises | **Yes** | Prevents the problem at the source. Conversation always valid. |
| **Reset thread_id on error** | Start fresh conversation after any error | No | Loses all conversation context (multi-turn history gone) |
| **Inject synthetic ToolMessage** | Find dangling tool_use_id and append ToolMessage to MemorySaver | No | Complex, fragile (depends on MemorySaver internals), only needed if tools can still raise |

## Edge case: agent-level LLM failure

If the exception happens outside a tool (e.g., the agent's own routing LLM call fails), Option 1 doesn't cover it. This is handled by the existing `except Exception` in the `/ask` and `/ask/stream` endpoints, which returns a 500 error. These failures are rare (no tool_use is emitted, so no dangling state) and don't corrupt the conversation history.

## Test

After fixing:

1. Load a video
2. Trigger a rate limit error (send a heavy request, or temporarily set a very low rate limit)
3. Verify the agent responds with a friendly error message (not a 500)
4. Send another question
5. Verify the second question works normally (no cascade failure)
6. Verify conversation context is preserved (follow-up questions reference earlier turns)
