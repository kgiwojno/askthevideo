"""Auto-generated from notebooks. Do not edit directly."""

from langchain_anthropic import ChatAnthropic
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver


def create_askthevideo_agent(tools: list, loaded_videos: list[str]) -> tuple:
    """Create a LangGraph agent with the given tools.

    Args:
        tools: list of LangChain @tool functions
        loaded_videos: list of currently loaded video_ids

    Returns:
        (agent, memory) tuple
    """
    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0.0)
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
        "- Include timestamp links in your answers when available."
    )

    agent = create_agent(llm, tools, system_prompt=system_prompt, checkpointer=memory)
    return agent, memory
