"""POST /api/ask and POST /api/ask/stream endpoints."""

import asyncio
import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Header, HTTPException, Request
from langchain_core.tools import tool
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.dependencies import get_pinecone, get_anthropic
from api.session import get_or_create_session, build_limits
from config.settings import MAX_QUESTIONS_FREE
from api.utils import get_client_ip
from src.agent import create_askthevideo_agent
from src.errors import send_discord_alert
from src.metrics import record_metric, log_event, get_metrics

SLOW_QUERY_THRESHOLD_MS = 60_000  # Alert if query takes >60s
from src.tools import (
    vector_search as _vector_search,
    summarize_video as _summarize_video,
    get_topics as _get_topics,
    compare_videos as _compare_videos,
    get_metadata as _get_metadata,
)
from src.validation import validate_question

router = APIRouter()


class AskRequest(BaseModel):
    question: str


def build_tools(selected_videos: list[str], pc, index, anthropic_client):
    """Build LangChain @tool wrappers with session video list as closure."""

    @tool
    def vector_search(question: str) -> str:
        """Search transcript chunks across loaded videos and answer a specific question."""
        try:
            t0 = time.monotonic()
            result = _vector_search(pc, index, anthropic_client, question, selected_videos)
            ms = int((time.monotonic() - t0) * 1000)
            log_event("TOOL", "api", "—", f"vector_search latency={ms}ms")
            return result.get("answer", "No relevant content found.")
        except Exception as e:
            log_event("ERROR", "tool", "—", f"vector_search: {type(e).__name__}: {str(e)[:80]}")
            return f"Sorry, I couldn't complete the search right now. Error: {type(e).__name__}"

    @tool
    def summarize_video(video_id: str) -> str:
        """Generate or retrieve a summary for a specific video by video_id."""
        try:
            t0 = time.monotonic()
            result = _summarize_video(index, anthropic_client, video_id)
            ms = int((time.monotonic() - t0) * 1000)
            source = "cache" if result.get("cached") else "api"
            log_event("TOOL", source, "—", f"summarize_video video={video_id} latency={ms}ms")
            return result.get("summary", "Could not generate summary.")
        except Exception as e:
            log_event("ERROR", "tool", "—", f"summarize_video: {type(e).__name__}: {str(e)[:80]}")
            return f"Sorry, I couldn't generate a summary right now. Error: {type(e).__name__}"

    @tool
    def list_topics(video_id: str) -> str:
        """List the main topics covered in a specific video by video_id."""
        try:
            t0 = time.monotonic()
            result = _get_topics(index, anthropic_client, video_id)
            ms = int((time.monotonic() - t0) * 1000)
            source = "cache" if result.get("cached") else "api"
            log_event("TOOL", source, "—", f"list_topics video={video_id} latency={ms}ms")
            return result.get("topics", "Could not retrieve topics.")
        except Exception as e:
            log_event("ERROR", "tool", "—", f"list_topics: {type(e).__name__}: {str(e)[:80]}")
            return f"Sorry, I couldn't retrieve topics right now. Error: {type(e).__name__}"

    @tool
    def compare_videos(question: str) -> str:
        """Compare what multiple loaded videos say about a topic or question."""
        try:
            t0 = time.monotonic()
            result = _compare_videos(pc, index, anthropic_client, question, selected_videos)
            ms = int((time.monotonic() - t0) * 1000)
            log_event("TOOL", "api", "—", f"compare_videos latency={ms}ms")
            return result.get("answer", "No relevant content found.")
        except Exception as e:
            log_event("ERROR", "tool", "—", f"compare_videos: {type(e).__name__}: {str(e)[:80]}")
            return f"Sorry, I couldn't compare videos right now. Error: {type(e).__name__}"

    @tool
    def get_metadata(video_id: str) -> str:
        """Get metadata (title, channel, duration) for a specific video by video_id."""
        try:
            t0 = time.monotonic()
            result = _get_metadata(index, video_id)
            ms = int((time.monotonic() - t0) * 1000)
            log_event("TOOL", "local", "—", f"get_metadata video={video_id} latency={ms}ms")
            if result["found"]:
                m = result["metadata"]
                return (
                    f"Title: {m.get('video_title', 'Unknown')}\n"
                    f"Channel: {m.get('channel', 'Unknown')}\n"
                    f"Duration: {m.get('duration_display', 'Unknown')}"
                )
            return f"No metadata found for video_id: {video_id}"
        except Exception as e:
            log_event("ERROR", "tool", "—", f"get_metadata: {type(e).__name__}: {str(e)[:80]}")
            return f"Sorry, I couldn't retrieve video metadata right now. Error: {type(e).__name__}"

    return [vector_search, summarize_video, list_topics, compare_videos, get_metadata]


def get_or_create_agent(session: dict, tools: list, selected_videos: list[str]):
    """Return existing agent or recreate if selected video list changed."""
    if session["agent"] is None or session["_agent_videos"] != selected_videos:
        agent, _ = create_askthevideo_agent(tools, selected_videos)
        session["agent"] = agent
        session["_agent_videos"] = selected_videos.copy()
    return session["agent"]


def _check_preconditions(session: dict):
    """Raise HTTPException if session is not ready to answer."""
    if not session["loaded_videos"]:
        raise HTTPException(400, detail={"error": "No videos loaded.", "code": "NO_VIDEOS"})
    if not session["unlimited"] and session["question_count"] >= MAX_QUESTIONS_FREE:
        raise HTTPException(403, detail={"error": "Question limit reached.", "code": "QUESTION_LIMIT"})


@router.post("/ask")
def post_ask(
    body: AskRequest,
    request: Request,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    sid, session = get_or_create_session(x_session_id)
    _check_preconditions(session)

    try:
        question = validate_question(body.question)
    except ValueError as e:
        raise HTTPException(400, detail={"error": str(e), "code": "QUESTION_TOO_LONG"})

    pc, index = get_pinecone()
    anthropic_client = get_anthropic()
    selected = [v["video_id"] for v in session["loaded_videos"] if v.get("selected", True)]
    if not selected:
        selected = [v["video_id"] for v in session["loaded_videos"]]
    tools = build_tools(selected, pc, index, anthropic_client)
    agent = get_or_create_agent(session, tools, selected)
    config = {"configurable": {"thread_id": session["agent_thread_id"]}}

    # Capture token state before query for per-query delta
    metrics_before = get_metrics()
    t0 = time.monotonic()

    try:
        result = agent.invoke(
            {"messages": [("user", question)]},
            config,
        )
    except Exception as e:
        raise HTTPException(500, detail={"error": str(e), "code": "INTERNAL_ERROR"})

    latency_ms = int((time.monotonic() - t0) * 1000)
    metrics_after = get_metrics()
    tokens_in = metrics_after["total_input_tokens"] - metrics_before["total_input_tokens"]
    tokens_out = metrics_after["total_output_tokens"] - metrics_before["total_output_tokens"]

    messages = result.get("messages", [])
    answer = ""
    tool_used = None
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_used = msg.tool_calls[0]["name"]
        if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
            answer = msg.content

    if latency_ms > SLOW_QUERY_THRESHOLD_MS:
        send_discord_alert(
            f"Slow query: {latency_ms / 1000:.1f}s — tool={tool_used or 'none'} "
            f"tokens={tokens_in}/{tokens_out} q=\"{question[:50]}\"",
            alert_type="slow_query",
        )

    session["question_count"] += 1
    session["chat_history"].append({"role": "user", "content": question})
    session["chat_history"].append({"role": "assistant", "content": answer})

    record_metric("total_queries")
    ip = get_client_ip(request)
    query_detail = (
        f'"{question[:50]}" tool={tool_used or "none"} '
        f"latency={latency_ms}ms tokens={tokens_in}/{tokens_out}"
    )
    if session["unlimited"]:
        record_metric("key_queries")
        log_event("KEY", "query", ip, f"{query_detail} count={session['question_count']}")
    else:
        log_event("QUERY", "free", ip, query_detail)

    return {
        "session_id": sid,
        "answer": answer,
        "tool_used": tool_used,
        "limits": build_limits(session),
    }


@router.post("/ask/stream")
async def post_ask_stream(
    body: AskRequest,
    request: Request,
    x_session_id: str | None = Header(None, alias="X-Session-ID"),
):
    sid, session = get_or_create_session(x_session_id)
    _check_preconditions(session)

    try:
        question = validate_question(body.question)
    except ValueError as e:
        raise HTTPException(400, detail={"error": str(e), "code": "QUESTION_TOO_LONG"})

    pc, index = get_pinecone()
    anthropic_client = get_anthropic()
    selected = [v["video_id"] for v in session["loaded_videos"] if v.get("selected", True)]
    if not selected:
        selected = [v["video_id"] for v in session["loaded_videos"]]
    tools = build_tools(selected, pc, index, anthropic_client)
    agent = get_or_create_agent(session, tools, selected)
    config = {"configurable": {"thread_id": session["agent_thread_id"]}}

    # Capture token state before query for per-query delta
    metrics_before = get_metrics()
    t0 = time.monotonic()

    async def event_generator() -> AsyncGenerator:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def _run_stream():
            """Run synchronous agent.stream() in a thread, pushing to the queue."""
            try:
                for chunk, metadata in agent.stream(
                    {"messages": [("user", question)]},
                    config,
                    stream_mode="messages",
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk, metadata))
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", e, None))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, ("done", None, None))

        task = asyncio.ensure_future(asyncio.to_thread(_run_stream))

        try:
            full_answer = ""
            tool_used = None
            emitted_tools: set = set()

            while True:
                kind, a, b = await queue.get()

                if kind == "done":
                    break

                if kind == "error":
                    yield {"data": json.dumps({"error": str(a), "code": "INTERNAL_ERROR"})}
                    return

                chunk, metadata = a, b
                node = metadata.get("langgraph_node", "")

                # Tool call announcement
                if node == "model" and hasattr(chunk, "tool_calls"):
                    for tc in (chunk.tool_calls or []):
                        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                        if name and name not in emitted_tools:
                            tool_used = name
                            emitted_tools.add(name)
                            yield {"data": json.dumps({"tool_used": name})}

                # Token streaming — content is list of dicts [{'text': '...', 'type': 'text'}]
                if node == "model" and hasattr(chunk, "content"):
                    content = chunk.content
                    if isinstance(content, str):
                        text = content
                    elif isinstance(content, list):
                        text = "".join(
                            c.get("text", "") for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        )
                    else:
                        text = ""
                    if text:
                        full_answer += text
                        yield {"data": json.dumps({"token": text})}

            await task

            latency_ms = int((time.monotonic() - t0) * 1000)
            metrics_after = get_metrics()
            tokens_in = metrics_after["total_input_tokens"] - metrics_before["total_input_tokens"]
            tokens_out = metrics_after["total_output_tokens"] - metrics_before["total_output_tokens"]

            if latency_ms > SLOW_QUERY_THRESHOLD_MS:
                send_discord_alert(
                    f"Slow query: {latency_ms / 1000:.1f}s — tool={tool_used or 'none'} "
                    f"tokens={tokens_in}/{tokens_out} q=\"{question[:50]}\"",
                    alert_type="slow_query",
                )

            session["question_count"] += 1
            session["chat_history"].append({"role": "user", "content": question})
            session["chat_history"].append({"role": "assistant", "content": full_answer})

            record_metric("total_queries")
            ip = get_client_ip(request)
            query_detail = (
                f'"{question[:50]}" tool={tool_used or "none"} '
                f"latency={latency_ms}ms tokens={tokens_in}/{tokens_out}"
            )
            if session["unlimited"]:
                record_metric("key_queries")
                log_event("KEY", "query", ip, f"{query_detail} count={session['question_count']}")
            else:
                log_event("QUERY", "free", ip, query_detail)

            yield {"data": json.dumps({"limits": build_limits(session)})}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e), "code": "INTERNAL_ERROR"})}

    return EventSourceResponse(event_generator())
