"""
End-to-end smoke tests against a running AskTheVideo server.

Usage:
    python scripts/smoke_test.py                        # default: http://localhost:8000
    python scripts/smoke_test.py https://app.askthevideo.com
    BASE_URL=http://localhost:8000 python scripts/smoke_test.py
"""

import http.client
import json
import os
import sys
import time
from urllib.parse import urlparse
import urllib.request
import urllib.error

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else os.getenv("BASE_URL", "http://localhost:8000")
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley, short, has captions
ACCESS_KEY = os.getenv("VALID_ACCESS_KEYS", "ASKTHEVIDEO2026").split(",")[0].strip()

SESSION_ID = None
PASS = 0
FAIL = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def request(method, path, body=None, *, session_id=None):
    url = BASE_URL + path
    headers = {"Content-Type": "application/json"}
    sid = session_id if session_id is not None else SESSION_ID
    if sid:
        headers["X-Session-ID"] = sid
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def post_stream(path, body):
    """POST and collect SSE events. Returns (events, http_status)."""
    parsed = urlparse(BASE_URL)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if parsed.scheme == "https":
        import ssl
        conn = http.client.HTTPSConnection(host, port, context=ssl.create_default_context())
    else:
        conn = http.client.HTTPConnection(host, port, timeout=90)

    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if SESSION_ID:
        headers["X-Session-ID"] = SESSION_ID

    conn.request("POST", path, json.dumps(body).encode(), headers)
    resp = conn.getresponse()

    events = []
    current = {}
    for raw in resp:
        line = raw.decode().rstrip("\r\n")
        if line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
            except Exception:
                data = line[5:].strip()
            current["data"] = data
            # Classify by content if no event: prefix
            if "event" not in current and isinstance(data, dict):
                if "token" in data:
                    current["event"] = "token"
                elif "limits" in data:
                    current["event"] = "done"
                elif "error" in data:
                    current["event"] = "error"
                elif "tool_used" in data:
                    current["event"] = "tool"
        elif line == "" and current:
            events.append(current)
            current = {}
            if events[-1].get("event") in ("done", "error"):
                break
    conn.close()
    return events, resp.status


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✓  {name}")
        PASS += 1
    else:
        print(f"  ✗  {name}" + (f"\n       got: {detail}" if detail else ""))
        FAIL += 1


def info(msg):
    print(f"     {msg}")


def section(title):
    print(f"\n{'─' * 52}")
    print(f"  {title}")
    print(f"{'─' * 52}")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_health():
    section("1. Health check")
    status, body = request("GET", "/health")
    check("GET /health → 200", status == 200, body)
    check("body has status:ok", body.get("status") == "ok", body)


def test_status_no_session():
    section("2. GET /api/status (no session)")
    status, body = request("GET", "/api/status", session_id="")
    check("returns 200", status == 200, body)
    check("has status:ok", body.get("status") == "ok", body)
    check("no session_id in response", "session_id" not in body, body)


def test_invalid_url():
    section("3. Invalid YouTube URL")
    status, body = request("POST", "/api/videos", {"url": "https://vimeo.com/123456"})
    check("returns 400", status == 400, body)
    check("code is INVALID_URL", body.get("detail", {}).get("code") == "INVALID_URL", body)


def test_load_video():
    """Load video and capture session_id. Returns (session_id, video_id)."""
    global SESSION_ID
    section("4. Load video (may take 30-60s for new video)")
    info(f"URL: {TEST_VIDEO_URL}")
    t0 = time.time()
    status, body = request("POST", "/api/videos", {"url": TEST_VIDEO_URL}, session_id="")
    elapsed = time.time() - t0
    info(f"took {elapsed:.1f}s  status={status}")

    check("returns 200", status == 200, body)
    sid = body.get("session_id")
    check("session_id returned", bool(sid), body)
    SESSION_ID = sid
    info(f"session_id: {SESSION_ID}")

    video = body.get("video", {})
    check("video_id present", bool(video.get("video_id")), video)
    check("title present", bool(video.get("title")), video)
    check("channel present", bool(video.get("channel")), video)
    check("duration_display present", bool(video.get("duration_display")), video)
    check("status is ingested or cached", video.get("status") in ("ingested", "cached"), video)

    # thumbnail_url may be empty for videos cached before this field was added
    if video.get("thumbnail_url"):
        check("thumbnail_url present", True)
    else:
        info("thumbnail_url empty (video was cached before this field was added — OK)")

    limits = body.get("limits", {})
    check("limits.videos_loaded == 1", limits.get("videos_loaded") == 1, limits)
    check("limits.videos_max == 5", limits.get("videos_max") == 5, limits)
    return sid, video.get("video_id")


def test_cache_hit():
    section("5. Cache hit (same video, must respond in < 5s)")
    t0 = time.time()
    status, body = request("POST", "/api/videos", {"url": TEST_VIDEO_URL})
    elapsed = time.time() - t0
    info(f"took {elapsed:.1f}s")
    check("returns 200", status == 200, body)
    check("fast response (< 5s)", elapsed < 5, f"{elapsed:.1f}s")
    check("videos_loaded still 1 (deduped)", body.get("limits", {}).get("videos_loaded") == 1, body.get("limits"))


def test_get_videos():
    section("6. GET /api/videos")
    status, body = request("GET", "/api/videos")
    check("returns 200", status == 200, body)
    videos = body.get("videos", [])
    check("has 1 video", len(videos) == 1, videos)
    check("video has video_id", bool(videos[0].get("video_id")) if videos else False)
    check("video has title", bool(videos[0].get("title")) if videos else False)


def test_ask_no_videos():
    section("7. Ask without videos (fresh session)")
    status, body = request("POST", "/api/ask", {"question": "What is this about?"}, session_id="")
    check("returns 400", status == 400, body)
    check("code is NO_VIDEOS", body.get("detail", {}).get("code") == "NO_VIDEOS", body)


def test_ask():
    section("8. POST /api/ask")
    status, body = request("POST", "/api/ask", {"question": "What is this video about?"})
    info(f"status={status}")
    check("returns 200", status == 200, body)
    check("answer present", bool(body.get("answer")), body)
    check("tool_used present", body.get("tool_used") is not None, body)
    check("limits present", "limits" in body, body)
    check("question_count incremented", body.get("limits", {}).get("questions_used", 0) >= 1, body.get("limits"))
    if body.get("answer"):
        info(f"answer: {body['answer'][:120].replace(chr(10), ' ')}...")
    return body.get("answer", "")


def test_ask_stream():
    section("9. POST /api/ask/stream (SSE)")
    events, status = post_stream("/api/ask/stream", {"question": "Give me a one-sentence summary."})
    info(f"status={status}  events={len(events)}")
    check("HTTP 200", status == 200, status)
    event_types = [e.get("event") for e in events]
    info(f"event types: {event_types}")
    check("has token events", "token" in event_types, event_types)
    check("ends with done", event_types[-1] == "done" if event_types else False, event_types)
    check("no error event", "error" not in event_types, event_types)
    done = next((e for e in events if e.get("event") == "done"), None)
    if done:
        check("done event has limits", "limits" in done.get("data", {}), done)
    tokens = "".join(e["data"].get("token", "") for e in events if e.get("event") == "token")
    if tokens:
        info(f"streamed: {tokens[:120]}...")


def test_question_too_long():
    section("10. Question over 500 chars")
    status, body = request("POST", "/api/ask", {"question": "x" * 501})
    check("returns 400", status == 400, body)
    check("code is QUESTION_TOO_LONG", body.get("detail", {}).get("code") == "QUESTION_TOO_LONG", body)


def test_auth_valid():
    section("11. POST /api/auth — valid key")
    status, body = request("POST", "/api/auth", {"key": ACCESS_KEY})
    check("returns 200", status == 200, body)
    check("valid == true", body.get("valid") is True, body)
    check("limits.unlimited == true", body.get("limits", {}).get("unlimited") is True, body)
    check("limits.videos_max is null", body.get("limits", {}).get("videos_max") is None, body)
    check("limits.questions_max is null", body.get("limits", {}).get("questions_max") is None, body)


def test_auth_invalid():
    section("12. POST /api/auth — invalid key")
    status, body = request("POST", "/api/auth", {"key": "WRONGKEY"})
    check("returns 200", status == 200, body)
    check("valid == false", body.get("valid") is False, body)


def test_history():
    section("13. GET /api/history")
    status, body = request("GET", "/api/history")
    check("returns 200", status == 200, body)
    messages = body.get("messages", [])
    check("has messages (from ask tests)", len(messages) > 0, messages)
    check("messages have role+content", all("role" in m and "content" in m for m in messages) if messages else True)
    info(f"message count: {len(messages)}")


def test_patch_video(video_id):
    section("14. PATCH /api/videos/{video_id} — toggle selection")
    if not video_id:
        info("skipped (no video_id)")
        return
    status, body = request("PATCH", f"/api/videos/{video_id}", {"selected": False})
    check("returns 200", status == 200, body)
    check("selected == false", body.get("selected") is False, body)
    # Toggle back
    request("PATCH", f"/api/videos/{video_id}", {"selected": True})


def test_delete_video(video_id):
    section("15. DELETE /api/videos/{video_id}")
    if not video_id:
        info("skipped (no video_id)")
        return
    status, body = request("DELETE", f"/api/videos/{video_id}")
    check("returns 200", status == 200, body)
    check("removed field == video_id", body.get("removed") == video_id, body)
    check("limits.videos_loaded == 0", body.get("limits", {}).get("videos_loaded") == 0, body)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'=' * 52}")
    print(f"  AskTheVideo Smoke Tests")
    print(f"  Target: {BASE_URL}")
    print(f"{'=' * 52}")

    test_health()
    test_status_no_session()
    test_invalid_url()
    sid, video_id = test_load_video()
    test_cache_hit()
    test_get_videos()
    test_ask_no_videos()
    test_ask()
    test_ask_stream()
    test_question_too_long()
    test_auth_valid()
    test_auth_invalid()
    test_history()
    test_patch_video(video_id)
    test_delete_video(video_id)

    print(f"\n{'=' * 52}")
    total = PASS + FAIL
    status_icon = "✓" if FAIL == 0 else "✗"
    print(f"  {status_icon}  {PASS}/{total} passed" + (f"  ({FAIL} failed)" if FAIL else ""))
    print(f"{'=' * 52}\n")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
