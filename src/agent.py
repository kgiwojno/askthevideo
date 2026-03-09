"""Auto-generated from notebooks. Do not edit directly."""

import os
from langchain_anthropic import ChatAnthropic
from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from src.metrics import record_tokens





class TokenTracker(BaseCallbackHandler):
    """Records token usage to global metrics store."""

    def on_llm_end(self, response, **kwargs):
        # Try llm_output.usage (non-streaming)
        usage = response.llm_output.get("usage", {}) if response.llm_output else {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        # Fallback: check generations[0].message.usage_metadata (LangChain >=0.2)
        if not (input_tokens or output_tokens) and response.generations:
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    um = getattr(msg, "usage_metadata", None) if msg else None
                    if um:
                        input_tokens += um.get("input_tokens", 0)
                        output_tokens += um.get("output_tokens", 0)
        if input_tokens or output_tokens:
            record_tokens(input_tokens, output_tokens)


def create_askthevideo_agent(tools: list, loaded_videos: list[str]) -> tuple:
    """Create a LangGraph agent with the given tools.

    Args:
        tools: list of LangChain @tool functions
        loaded_videos: list of currently loaded video_ids

    Returns:
        (agent, memory) tuple
    """
    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.0, callbacks=[TokenTracker()])
    memory = MemorySaver()

    system_prompt = (
        "You are AskTheVideo, an AI assistant that answers questions about YouTube videos. "
        f"Currently loaded videos: {loaded_videos}\n\n"
        "Rules:\n"
        "- Use the available tools to answer questions. Do not make up information.\n"
        "- For specific questions about video content, use vector_search.\n"
        "- For 'what is this about' or 'summarize', use summarize_video with the video_id.\n"
        "- For 'what topics' or 'outline', use list_topics with the video_id.\n"
        "- For comparisons across videos, use compare_videos.\n"
        "- For video info (title, duration, channel), use get_metadata.\n"
        "- Always pass video_id as a string, not a list.\n"
        "- Include timestamps as clickable markdown links in your answers, e.g. [2:30](https://youtu.be/ID?t=150)."
    )

    agent = create_agent(llm, tools, system_prompt=system_prompt, checkpointer=memory)
    return agent, memory