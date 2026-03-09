"""Auto-generated from notebooks. Do not edit directly."""

import os
import json
import logging
import urllib.request
import urllib.error
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    IpBlocked,
    RequestBlocked,
)
import re



logger = logging.getLogger(__name__)


def _fetch_via_ytdlp(video_id: str) -> dict:
    """Fetch transcript using yt-dlp (fallback for IP blocks).

    yt-dlp uses a different YouTube code path than youtube_transcript_api
    and may succeed where the other is blocked.
    """
    import yt_dlp

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "subtitlesformat": "json3",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Try manual subs first, then auto subs
    subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}
    is_generated = False

    sub_data = None
    lang_code = None
    for lang in ["en", "en-US", "en-GB"]:
        if lang in subs:
            for fmt in subs[lang]:
                if fmt.get("ext") == "json3":
                    sub_data = fmt
                    lang_code = lang
                    break
            if sub_data:
                break

    if not sub_data:
        is_generated = True
        for lang in ["en", "en-US", "en-GB"]:
            if lang in auto_subs:
                for fmt in auto_subs[lang]:
                    if fmt.get("ext") == "json3":
                        sub_data = fmt
                        lang_code = lang
                        break
                if sub_data:
                    break

    if not sub_data:
        raise ValueError(f"No English subtitles found via yt-dlp for video {video_id}")

    # Download the subtitle data
    sub_url = sub_data.get("url", "")
    if not sub_url:
        raise ValueError(f"No subtitle URL from yt-dlp for video {video_id}")

    req = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        json_data = json.loads(resp.read().decode())

    # Parse json3 format
    snippets = []
    for event in json_data.get("events", []):
        if "segs" not in event or "tStartMs" not in event:
            continue
        text = "".join(s.get("utf8", "") for s in event["segs"]).strip()
        if text:
            snippets.append({
                "text": text,
                "start": event["tStartMs"] / 1000,
                "duration": event.get("dDurationMs", 0) / 1000,
            })

    if not snippets:
        raise ValueError(f"yt-dlp returned empty transcript for video {video_id}")

    last = snippets[-1]
    return {
        "video_id": video_id,
        "language": lang_code or "en",
        "is_generated": is_generated,
        "snippets": snippets,
        "duration_seconds": last["start"] + last["duration"],
    }


def _fetch_via_proxy(video_id: str) -> dict:
    """Fetch transcript via Cloudflare Worker proxy (fallback for IP blocks)."""
    proxy_url = os.getenv("TRANSCRIPT_PROXY_URL")
    proxy_secret = os.getenv("TRANSCRIPT_PROXY_SECRET", "")
    if not proxy_url:
        raise ValueError("YouTube is blocking requests and no transcript proxy is configured.")

    payload = json.dumps({"video_id": video_id}).encode()
    headers = {"Content-Type": "application/json"}
    if proxy_secret:
        headers["Authorization"] = f"Bearer {proxy_secret}"

    req = urllib.request.Request(proxy_url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            err_data = json.loads(body)
            msg = err_data.get("error", body[:100])
        except Exception:
            msg = body[:100] or f"HTTP {e.code}"
        raise ValueError(f"Transcript proxy error: {msg}")
    except Exception as e:
        raise ValueError(f"Transcript proxy unreachable: {type(e).__name__}")

    return {
        "video_id": data["video_id"],
        "language": data.get("language", "unknown"),
        "is_generated": data.get("is_generated", True),
        "snippets": data["snippets"],
        "duration_seconds": data["duration_seconds"],
    }


def fetch_transcript(video_id: str) -> dict:
    """Fetch transcript for a YouTube video.

    Fallback chain:
        1. youtube_transcript_api (fastest, direct API)
        2. yt-dlp (different extraction path, may bypass IP blocks)
        3. Cloudflare/GCF proxy (if TRANSCRIPT_PROXY_URL is set)

    Returns dict with:
        - video_id: str
        - language: str
        - is_generated: bool
        - snippets: list of {text, start, duration}
        - duration_seconds: float (estimated from last snippet)

    Raises:
        ValueError: if transcript is unavailable
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
    except (IpBlocked, RequestBlocked) as ip_err:
        logger.warning("youtube_transcript_api blocked for %s, trying yt-dlp", video_id)
        try:
            return _fetch_via_ytdlp(video_id)
        except Exception as ytdlp_err:
            logger.warning("yt-dlp failed for %s: %s, trying proxy", video_id, ytdlp_err)
            return _fetch_via_proxy(video_id)
    except Exception as e:
        raise ValueError(f"Could not fetch transcript for video {video_id}: {type(e).__name__}")

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
    # Already a raw video ID (11 chars, alphanumeric + _ -)
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