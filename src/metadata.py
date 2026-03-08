"""Video metadata via YouTube oEmbed API."""

import urllib.request
import urllib.error
import json


def fetch_video_metadata(video_id: str) -> dict:
    """Fetch video title, channel, and thumbnail via YouTube oEmbed.

    Returns:
        dict with video_title, channel, thumbnail_url
    On any error returns fallback values.
    """
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return {
            "video_title": data.get("title", "Unknown"),
            "channel": data.get("author_name", "Unknown"),
            "thumbnail_url": data.get("thumbnail_url", f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"),
        }
    except Exception:
        return {
            "video_title": "Unknown",
            "channel": "Unknown",
            "thumbnail_url": "",
        }
