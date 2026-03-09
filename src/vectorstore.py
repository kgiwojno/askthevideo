"""Auto-generated from notebooks. Do not edit directly."""

from pinecone import Pinecone
import os
import time



EMBED_MODEL = "llama-text-embed-v2"
EMBED_BATCH_SIZE = 50
SENTINEL_VECTOR = [1e-7] + [0.0] * 1023


def get_pinecone_index():
    """Connect to Pinecone and return the index."""
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index_name = os.getenv("PINECONE_INDEX_NAME", "askthevideo")
    return pc, pc.Index(index_name)


def embed_texts(pc, texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """Embed a list of texts via Pinecone Inference API.

    Args:
        pc: Pinecone client
        texts: list of strings to embed
        input_type: "passage" for documents, "query" for search queries
    Returns:
        list of embedding vectors (list of floats)
    """
    all_embeddings = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i:i + EMBED_BATCH_SIZE]
        embs = pc.inference.embed(
            model=EMBED_MODEL,
            inputs=batch,
            parameters={"input_type": input_type, "truncate": "END"},
        )
        all_embeddings.extend([e.values for e in embs])
    return all_embeddings


def upsert_chunks(pc, index, chunks: list[dict], video_id: str) -> int:
    """Embed and upsert transcript chunks into Pinecone.

    Args:
        pc: Pinecone client
        index: Pinecone index
        chunks: list of chunk dicts from chunk_transcript()
        video_id: YouTube video ID (used as namespace)
    Returns:
        number of vectors upserted
    """
    texts = [c["text"] for c in chunks]
    embeddings = embed_texts(pc, texts, input_type="passage")

    vectors = []
    for chunk, emb in zip(chunks, embeddings):
        vectors.append({
            "id": f"{video_id}_chunk_{chunk['chunk_index']:03d}",
            "values": emb,
            "metadata": {
                "video_id": video_id,
                "type": "chunk",
                "text": chunk["text"],
                "text_timestamped": chunk["text_timestamped"],
                "start_time": chunk["start_time"],
                "end_time": chunk["end_time"],
                "start_display": chunk["start_display"],
                "end_display": chunk["end_display"],
                "chunk_index": chunk["chunk_index"],
                "video_url": chunk["video_url"],
            },
        })

    index.upsert(vectors=vectors, namespace=video_id)
    return len(vectors)


def upsert_metadata_record(index, video_id: str, metadata: dict):
    """Store a metadata record (sentinel vector) in the video namespace.

    Args:
        index: Pinecone index
        video_id: YouTube video ID
        metadata: dict with video_title, channel, duration_seconds, etc.
    """
    record = {
        "id": f"{video_id}_metadata",
        "values": SENTINEL_VECTOR,
        "metadata": {
            "type": "metadata",
            "video_id": video_id,
            **metadata,
            "ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    index.upsert(vectors=[record], namespace=video_id)


def query_chunks(pc, index, question: str, video_id: str, top_k: int = 5) -> list[dict]:
    """Embed a question and retrieve matching chunks.

    Args:
        pc: Pinecone client
        index: Pinecone index
        question: user's question
        video_id: namespace to search
        top_k: number of results
    Returns:
        list of dicts with score + metadata
    """
    emb = embed_texts(pc, [question], input_type="query")[0]
    results = index.query(
        vector=emb,
        namespace=video_id,
        top_k=top_k,
        include_metadata=True,
    )
    return [
        {"score": m.score, "id": m.id, **m.metadata}
        for m in results.matches
        if m.metadata.get("type") != "metadata"
    ]


def fetch_metadata(index, video_id: str) -> dict | None:
    """Fetch the metadata record for a video. Returns None if not found."""
    result = index.fetch(ids=[f"{video_id}_metadata"], namespace=video_id)
    vec = result.vectors.get(f"{video_id}_metadata")
    if vec:
        return dict(vec.metadata)
    return None


def namespace_exists(index, video_id: str) -> bool:
    """Check if a video namespace already has vectors."""
    stats = index.describe_index_stats()
    return video_id in stats.namespaces