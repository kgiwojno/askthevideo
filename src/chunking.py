"""Auto-generated from notebooks. Do not edit directly."""


def format_time(seconds: float) -> str:
    """Convert seconds to H:MM:SS or M:SS display format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def chunk_transcript(
    snippets: list[dict],
    video_id: str,
    window_seconds: int = 120,
    carry_snippets: int = 3,
) -> list[dict]:
    """Chunk transcript snippets into time-based windows.

    Args:
        snippets: list of {"text": str, "start": float, "duration": float}
        video_id: YouTube video ID (for generating URLs)
        window_seconds: target chunk duration in seconds
        carry_snippets: number of snippets to carry from previous chunk for context

    Returns:
        list of chunk dicts with:
            - text: plain text (for embedding)
            - text_timestamped: text with inline timestamps (for LLM context)
            - start_time: float (seconds)
            - end_time: float (seconds)
            - start_display: str (human readable)
            - end_display: str (human readable)
            - chunk_index: int
            - video_url: str (deep link to timestamp)
    """
    if not snippets:
        return []

    chunks = []
    carry = []
    i = 0

    while i < len(snippets):
        chunk_snippets = list(carry)
        window_start = snippets[i]["start"]

        while i < len(snippets) and snippets[i]["start"] < window_start + window_seconds:
            chunk_snippets.append(snippets[i])
            i += 1

        plain_parts = [s["text"].replace("\n", " ") for s in chunk_snippets]
        text = " ".join(plain_parts)

        stamped_lines = [
            f"[{format_time(s['start'])}] {s['text'].replace(chr(10), ' ')}"
            for s in chunk_snippets
        ]
        text_timestamped = "\n".join(stamped_lines)

        start_time = chunk_snippets[0]["start"]
        end_time = chunk_snippets[-1]["start"] + chunk_snippets[-1]["duration"]

        chunks.append({
            "text": text,
            "text_timestamped": text_timestamped,
            "start_time": start_time,
            "end_time": end_time,
            "start_display": format_time(start_time),
            "end_display": format_time(end_time),
            "chunk_index": len(chunks),
            "video_url": f"https://youtu.be/{video_id}?t={int(start_time)}",
        })

        non_carry = chunk_snippets[len(carry):]
        carry = non_carry[-carry_snippets:] if carry_snippets > 0 else []

    return chunks
