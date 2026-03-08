"""Auto-generated from notebooks. Do not edit directly."""

import os
import time
from anthropic import Anthropic
from pinecone import Pinecone

CLAUDE_MODEL = "claude-sonnet-4-6"
EMBED_MODEL = "llama-text-embed-v2"
EMBED_BATCH_SIZE = 50
SENTINEL_VECTOR = [1e-7] + [0.0] * 1023


def _get_clients():
    """Initialise and return Anthropic + Pinecone clients."""
    anthropic_client = Anthropic()
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "askthevideo"))
    return anthropic_client, pc, index


def _embed_texts(pc, texts, input_type="passage"):
    """Embed texts via Pinecone Inference API."""
    all_embs = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i:i + EMBED_BATCH_SIZE]
        embs = pc.inference.embed(
            model=EMBED_MODEL, inputs=batch,
            parameters={"input_type": input_type, "truncate": "END"},
        )
        all_embs.extend([e.values for e in embs])
    return all_embs


def _query_chunks(pc, index, question, video_id, top_k=5):
    """Embed question and retrieve matching chunks from a namespace."""
    emb = _embed_texts(pc, [question], input_type="query")[0]
    results = index.query(
        vector=emb, namespace=video_id,
        top_k=top_k, include_metadata=True,
    )
    return [
        {"score": m.score, "id": m.id, **m.metadata}
        for m in results.matches
        if m.metadata.get("type", "chunk") == "chunk"
    ]


def _fetch_all_chunks(index, video_id):
    """Fetch all chunk records for a video, sorted by chunk_index."""
    stats = index.describe_index_stats()
    total = int(stats.namespaces.get(video_id, {}).get("vector_count", 0))
    chunk_ids = [f"{video_id}_chunk_{i:03d}" for i in range(total)]
    fetched = index.fetch(ids=chunk_ids, namespace=video_id)
    chunks = []
    for cid in chunk_ids:
        vec = fetched.vectors.get(cid)
        if vec and vec.metadata.get("type", "chunk") == "chunk":
            chunks.append(dict(vec.metadata))
    chunks.sort(key=lambda c: c.get("chunk_index", 0))
    return chunks


def _build_full_text(chunks):
    """Build plain-text transcript from chunks (with timestamp headers)."""
    return "\n\n".join(
        f"[{c['start_display']}–{c['end_display']}]\n{c['text']}"
        for c in chunks
    )


def _fetch_or_generate_cached(index, client, video_id, record_suffix, system_prompt, user_prompt_prefix):
    """Shared pattern: check Pinecone cache, generate with Claude if missing, cache result."""
    record_id = f"{video_id}_{record_suffix}"

    cached = index.fetch(ids=[record_id], namespace=video_id)
    vec = cached.vectors.get(record_id)
    if vec and vec.metadata.get("text"):
        return {"text": vec.metadata["text"], "cached": True, "usage": None}

    chunks = _fetch_all_chunks(index, video_id)
    if not chunks:
        return {"text": "No transcript data found.", "cached": False, "usage": None}

    full_text = _build_full_text(chunks)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": f"{user_prompt_prefix}\n\n{full_text}"}],
    )

    result_text = response.content[0].text

    index.upsert(
        vectors=[{
            "id": record_id,
            "values": SENTINEL_VECTOR,
            "metadata": {
                "type": record_suffix,
                "video_id": video_id,
                "text": result_text,
            },
        }],
        namespace=video_id,
    )

    return {
        "text": result_text,
        "cached": False,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


def vector_search(pc, index, client, question, video_ids):
    """Search transcript chunks and answer with Claude."""
    all_chunks = []
    per_video_k = max(3, 10 // len(video_ids))
    for vid in video_ids:
        all_chunks.extend(_query_chunks(pc, index, question, vid, top_k=per_video_k))

    if not all_chunks:
        return {"answer": "No relevant content found.", "usage": None}

    all_chunks.sort(key=lambda c: c["score"], reverse=True)
    all_chunks = all_chunks[:10]

    context_parts = []
    for c in all_chunks:
        header = f"[{c['start_display']}–{c['end_display']}] ({c['video_url']})"
        context_parts.append(f"{header}\n{c['text_timestamped']}")
    context = "\n\n---\n\n".join(context_parts)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system="You answer questions about YouTube videos using transcript excerpts. "
               "Always reference specific timestamps from the excerpts. "
               "If the excerpts don't contain relevant information, say so.",
        messages=[{
            "role": "user",
            "content": f"Transcript excerpts:\n\n{context}\n\n---\n\nQuestion: {question}",
        }],
    )

    return {
        "answer": response.content[0].text,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "chunks_used": len(all_chunks),
    }


def summarize_video(index, client, video_id):
    """Generate or retrieve cached video summary."""
    result = _fetch_or_generate_cached(
        index, client, video_id,
        record_suffix="summary",
        system_prompt=(
            "You summarise YouTube videos from their transcript. "
            "Provide: a one-paragraph overview, then 5-7 key points with timestamps. "
            "Be concise and specific."
        ),
        user_prompt_prefix="Summarise this video transcript:",
    )
    return {"summary": result["text"], "cached": result["cached"], "usage": result["usage"]}


def get_topics(index, client, video_id):
    """Generate or retrieve cached topic list."""
    result = _fetch_or_generate_cached(
        index, client, video_id,
        record_suffix="topics",
        system_prompt=(
            "You extract the main topics from a YouTube video transcript. "
            "Return a numbered list of 8-12 topics, each with a timestamp range "
            "and a one-sentence description. Format: '1. [MM:SS-MM:SS] Topic — description'"
        ),
        user_prompt_prefix="Extract the main topics from this transcript:",
    )
    return {"topics": result["text"], "cached": result["cached"], "usage": result["usage"]}


def compare_videos(pc, index, client, question, video_ids):
    """Compare what multiple videos say about a topic."""
    all_chunks = []
    per_video_k = max(3, 10 // len(video_ids))

    for vid in video_ids:
        chunks = _query_chunks(pc, index, question, vid, top_k=per_video_k)
        for c in chunks:
            c["video_id"] = vid
        all_chunks.extend(chunks)

    if not all_chunks:
        return {"answer": "No relevant content found.", "usage": None}

    all_chunks.sort(key=lambda c: c["score"], reverse=True)

    by_video = {}
    for c in all_chunks:
        vid = c["video_id"]
        if vid not in by_video:
            by_video[vid] = []
        by_video[vid].append(c)

    context_parts = []
    for vid, chunks in by_video.items():
        header = f"=== Video: {vid} ==="
        excerpts = [
            f"[{c['start_display']}–{c['end_display']}] ({c['video_url']})\n{c['text_timestamped']}"
            for c in chunks
        ]
        context_parts.append(header + "\n\n" + "\n\n".join(excerpts))

    context = ("\n\n" + "=" * 40 + "\n\n").join(context_parts)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1536,
        system="You compare what different YouTube videos say about a topic. "
               "Highlight similarities and differences. Reference specific timestamps. "
               "If only one video is provided, summarise what it says about the topic.",
        messages=[{
            "role": "user",
            "content": f"Compare these videos on the topic:\n\nQuestion: {question}\n\n{context}",
        }],
    )

    return {
        "answer": response.content[0].text,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "videos_queried": len(video_ids),
        "chunks_used": len(all_chunks),
    }


def get_metadata(index, video_id):
    """Fetch video metadata from Pinecone."""
    result = index.fetch(ids=[f"{video_id}_metadata"], namespace=video_id)
    vec = result.vectors.get(f"{video_id}_metadata")
    if vec:
        return {"metadata": dict(vec.metadata), "found": True}
    return {"metadata": None, "found": False}
