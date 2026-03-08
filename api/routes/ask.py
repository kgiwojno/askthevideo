"""POST /api/ask and POST /api/ask/stream endpoints."""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Header, HTTPException
from langchain_core.tools import tool
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.dependencies import get_pinecone, get_anthropic
from api.session import get_or_create_session, build_limits
from config.settings import MAX_QUESTIONS_FREE
from src.agent import create_askthevideo_agent
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
        result = _vector_search(pc, index, anthropic_client, question, selected_videos)
        return result.get("answer", "No relevant content found.")

    @tool
    def summarize_video(video_id: str) -> str:
        """Generate or retrieve a summary for a specific video by video_id."""
        result = _summarize_video(index, anthropic_client, video_id)
        return result.get("summary", "Could not generate summary.")

    @tool
    def list_topics(video_id: str) -> str:
        """List the main topics covered in a specific video by video_id."""
        result = _get_topics(index, anthropic_client, video_id)
        return result.get("topics", "Could not retrieve topics.")

    @tool
    def compare_videos(question: str) -> str:
        """Compare what multiple loaded videos say about a topic or question."""
        result = _compare_videos(pc, index, anthropic_client, question, selected_videos)
        return result.get("answer", "No relevant content found.")

    @tool
    def get_metadata(video_id: str) -> str:
        """Get metadata (title, channel, duration) for a specific video by video_id."""
        result = _get_metadata(index, video_id)
        if result["found"]:
            m = result["metadata"]
            return (
                f"Title: {m.get('video_title', 'Unknown')}\n"
                f"Channel: {m.get('channel', 'Unknown')}\n"
                f"Duration: {m.get('duration_display', 'Unknown')}"
            )
        return f"No metadata found for video_id: {video_id}"

    return [vector_search, summarize_video, list_topics, compare_videos, get_metadata]


def get_or_create_agent(session: dict, tools: list):
    """Return existing agent or recreate if video list changed."""
    current_videos = [v["video_id"] for v in session["loaded_videos"]]
    if session["agent"] is None or session["_agent_videos"] != current_videos:
        agent, _ = create_askthevideo_agent(tools, current_videos)
        session["agent"] = agent
        session["_agent_videos"] = current_videos.copy()
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
    tools = build_tools(selected, pc, index, anthropic_client)
    agent = get_or_create_agent(session, tools)
    config = {"configurable": {"thread_id": session["agent_thread_id"]}}

    try:
        result = agent.invoke(
            {"messages": [("user", question)]},
            config,
        )
    except Exception as e:
        raise HTTPException(500, detail={"error": str(e), "code": "INTERNAL_ERROR"})

    messages = result.get("messages", [])
    answer = ""
    tool_used = None
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_used = msg.tool_calls[0]["name"]
        if hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
            answer = msg.content

    session["question_count"] += 1
    session["chat_history"].append({"role": "user", "content": question})
    session["chat_history"].append({"role": "assistant", "content": answer})

    return {
        "session_id": sid,
        "answer": answer,
        "tool_used": tool_used,
        "limits": build_limits(session),
    }


@router.post("/ask/stream")
async def post_ask_stream(
    body: AskRequest,
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
    tools = build_tools(selected, pc, index, anthropic_client)
    agent = get_or_create_agent(session, tools)
    config = {"configurable": {"thread_id": session["agent_thread_id"]}}

    async def event_generator() -> AsyncGenerator:
        try:
            full_answer = ""
            tool_used = None

            for event in agent.stream(
                {"messages": [("user", question)]},
                config,
                stream_mode="updates",
            ):
                for key, value in event.items():
                    if key == "agent":
                        msgs = value.get("messages", [])
                        for msg in msgs:
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                tool_used = msg.tool_calls[0]["name"]
                                yield {
                                    "event": "tool",
                                    "data": json.dumps({"tool_used": tool_used}),
                                }
                            elif hasattr(msg, "content") and isinstance(msg.content, str) and msg.content:
                                new_text = msg.content
                                if new_text != full_answer:
                                    delta = new_text[len(full_answer):]
                                    full_answer = new_text
                                    if delta:
                                        yield {
                                            "event": "token",
                                            "data": json.dumps({"text": delta}),
                                        }

            session["question_count"] += 1
            session["chat_history"].append({"role": "user", "content": question})
            session["chat_history"].append({"role": "assistant", "content": full_answer})

            yield {"event": "done", "data": json.dumps({"limits": build_limits(session)})}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e), "code": "INTERNAL_ERROR"})}

    return EventSourceResponse(event_generator())
