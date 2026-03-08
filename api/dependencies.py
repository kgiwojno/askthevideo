"""Pinecone + Anthropic client singletons."""

import os
from functools import lru_cache

from anthropic import Anthropic
from pinecone import Pinecone


@lru_cache()
def get_pinecone():
    """Return (pc, index) singleton, warming up the connection."""
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "askthevideo"))
    index.describe_index_stats()  # warm up
    return pc, index


@lru_cache()
def get_anthropic():
    """Return Anthropic client singleton."""
    return Anthropic()
