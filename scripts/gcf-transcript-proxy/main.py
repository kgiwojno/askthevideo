"""Google Cloud Function — YouTube Transcript Proxy.

Uses YouTube's Innertube API with the Android client to fetch transcripts.
Google Cloud IPs are less likely to be blocked by YouTube.

Deploy: gcloud functions deploy youtube-transcript-proxy --runtime python312 \
         --trigger-http --allow-unauthenticated --entry-point handler \
         --set-secrets 'PROXY_SECRET=PROXY_SECRET:latest'

Free tier: 2M invocations/month, 400k GB-seconds.
"""

import json
import os
import re
import urllib.request
import urllib.error

ANDROID_CONTEXT = {
    "client": {
        "clientName": "ANDROID",
        "clientVersion": "20.10.38",
    },
}

INNERTUBE_API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"


def handler(request):
    """HTTP Cloud Function entry point."""
    # CORS
    if request.method == "OPTIONS":
        return ("", 204, {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        })

    if request.method != "POST":
        return json_err("POST only", 405)

    # Auth
    secret = os.environ.get("PROXY_SECRET", "")
    if secret:
        auth = request.headers.get("Authorization", "")
        token = auth.replace("Bearer ", "")
        if token != secret:
            return json_err("Unauthorized", 401)

    # Parse body
    try:
        body = request.get_json(force=True)
    except Exception:
        return json_err("Invalid JSON", 400)

    video_id = body.get("video_id", "")
    if not video_id or not isinstance(video_id, str):
        return json_err("video_id required", 400)

    try:
        return fetch_transcript(video_id)
    except Exception as e:
        return json_err(f"Proxy error: {e}", 500)


def fetch_transcript(video_id):
    """Fetch transcript using Android Innertube client."""
    # Step 1: Call player API to get caption tracks
    player_data = innertube_player(video_id)

    status = (player_data.get("playabilityStatus") or {}).get("status", "")
    if status == "ERROR":
        reason = (player_data.get("playabilityStatus") or {}).get(
            "reason", f"Video {video_id} is unavailable"
        )
        return json_err(reason, 404)

    captions = (
        (player_data.get("captions") or {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    )
    if not captions:
        return json_err(f"No captions available for video {video_id}", 404)

    # Prefer manual English → auto English → first
    track = (
        next((c for c in captions if c.get("languageCode") == "en" and c.get("kind") != "asr"), None)
        or next((c for c in captions if c.get("languageCode") == "en"), None)
        or next((c for c in captions if c.get("languageCode", "").startswith("en")), None)
        or captions[0]
    )

    # Step 2: Fetch transcript from baseUrl
    base_url = track.get("baseUrl", "")
    if not base_url:
        return json_err("No transcript URL available", 404)

    snippets = fetch_and_parse_transcript(base_url)
    if not snippets:
        return json_err(f"Transcript is empty for video {video_id}", 404)

    last = snippets[-1]
    result = {
        "video_id": video_id,
        "language": (track.get("name") or {}).get("simpleText", track.get("languageCode", "unknown")),
        "language_code": track.get("languageCode", ""),
        "is_generated": track.get("kind") == "asr",
        "snippets": snippets,
        "duration_seconds": last["start"] + last["duration"],
    }
    return (json.dumps(result), 200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
    })


def innertube_player(video_id):
    """Call Innertube player API with Android client."""
    payload = json.dumps({
        "context": ANDROID_CONTEXT,
        "videoId": video_id,
    }).encode()
    req = urllib.request.Request(
        f"https://www.youtube.com/youtubei/v1/player?key={INNERTUBE_API_KEY}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def fetch_and_parse_transcript(base_url):
    """Fetch transcript XML from baseUrl and parse it."""
    # Try default format (XML)
    req = urllib.request.Request(base_url, headers={
        "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 14; en_US)",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode()
    except Exception:
        text = ""

    if text:
        snippets = parse_xml(text)
        if snippets:
            return snippets

    # Fallback: try json3 format
    req2 = urllib.request.Request(base_url + "&fmt=json3", headers={
        "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 14; en_US)",
    })
    try:
        with urllib.request.urlopen(req2, timeout=20) as resp2:
            text2 = resp2.read().decode()
        if text2:
            data = json.loads(text2)
            return parse_json3(data)
    except Exception:
        pass

    return []


def parse_xml(xml):
    """Parse transcript XML: <text start="0" dur="1.5">Hello</text> or <p t="0" d="1920">Hello</p>."""
    snippets = []

    # Standard format: <text start="..." dur="...">
    for m in re.finditer(r'<text\s+start="([\d.]+)"\s+dur="([\d.]+)"[^>]*>([\s\S]*?)</text>', xml):
        text = decode_entities(m.group(3)).strip()
        if text:
            snippets.append({
                "text": text,
                "start": float(m.group(1)),
                "duration": float(m.group(2)),
            })

    if snippets:
        return snippets

    # Format 3: <p t="..." d="..."> (milliseconds)
    for m in re.finditer(r'<p\s+t="(\d+)"\s+d="(\d+)"[^>]*>([\s\S]*?)</p>', xml):
        text = decode_entities(m.group(3)).strip()
        if text:
            snippets.append({
                "text": text,
                "start": int(m.group(1)) / 1000,
                "duration": int(m.group(2)) / 1000,
            })

    return snippets


def parse_json3(data):
    """Parse JSON3 transcript format."""
    snippets = []
    for event in data.get("events", []):
        if "segs" not in event or "tStartMs" not in event:
            continue
        text = "".join(s.get("utf8", "") for s in event["segs"])
        if text.strip():
            snippets.append({
                "text": text,
                "start": event["tStartMs"] / 1000,
                "duration": event.get("dDurationMs", 0) / 1000,
            })
    return snippets


def decode_entities(s):
    # Strip inner XML tags like <s t="420" ac="248">word</s>
    s = re.sub(r"<[^>]+>", "", s)
    return (
        s.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("\n", " ")
    )


def json_err(msg, status):
    return (
        json.dumps({"error": str(msg)}),
        status,
        {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
    )
