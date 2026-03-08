"""Auto-generated from notebooks. Do not edit directly."""

import re
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)


def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats.

    Supports:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://www.youtube.com/v/VIDEO_ID
        - Raw video ID (11 characters)

    Raises:
        ValueError: if no valid video ID can be extracted
    """
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()

    patterns = [
        r"(?:youtube\.com/watch\?.*v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/v/)([A-Za-z0-9_-]{11})",
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError(f"Could not extract video ID from: {url}")


def fetch_transcript(video_id: str) -> dict:
    """Fetch transcript for a YouTube video.

    Returns dict with:
        - video_id: str
        - language: str
        - is_generated: bool
        - snippets: list of {text, start, duration}
        - duration_seconds: float (estimated from last snippet)

    Raises:
        ValueError: if transcript is unavailable (disabled, not found, or video removed)
    """
    ytt_api = YouTubeTranscriptApi()

    try:
        transcript = ytt_api.fetch(video_id)
    except TranscriptsDisabled:
        raise ValueError(f"Transcripts are disabled for video {video_id}")
    except NoTranscriptFound:
        raise ValueError(f"No transcript found for video {video_id}")
    except VideoUnavailable:
        raise ValueError(f"Video {video_id} is unavailable")

    snippets = [
        {"text": s.text, "start": s.start, "duration": s.duration}
        for s in transcript.snippets
    ]

    last = transcript.snippets[-1]
    duration_seconds = last.start + last.duration

    return {
        "video_id": video_id,
        "language": transcript.language,
        "is_generated": transcript.is_generated,
        "snippets": snippets,
        "duration_seconds": duration_seconds,
    }
