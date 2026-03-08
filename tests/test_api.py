"""Integration tests for the FastAPI app using TestClient."""

from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

import api.session as session_module


@pytest.fixture(autouse=True)
def clear_sessions():
    session_module.sessions.clear()
    yield
    session_module.sessions.clear()


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


class TestHealth:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStatus:
    def test_status_no_session(self, client):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_status_with_session(self, client):
        # Create a session first
        _, session = session_module.get_or_create_session(None)
        # Get a valid session ID
        sid = list(session_module.sessions.keys())[0]
        response = client.get("/api/status", headers={"X-Session-ID": sid})
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == sid
        assert "limits" in data


class TestPostVideos:
    def test_invalid_url_returns_400(self, client):
        response = client.post("/api/videos", json={"url": "https://vimeo.com/123"})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_URL"

    def test_valid_url_calls_pipeline(self, client):
        mock_transcript = {
            "video_id": "dQw4w9WgXcQ",
            "language": "en",
            "is_generated": False,
            "snippets": [{"text": "hello", "start": 0.0, "duration": 5.0}],
            "duration_seconds": 5.0,
        }
        mock_oembed = {
            "video_title": "Test Video",
            "channel": "Test Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        }
        mock_index = MagicMock()
        mock_index.describe_index_stats.return_value = MagicMock(namespaces={})
        mock_pc = MagicMock()

        with (
            patch("api.routes.videos.get_pinecone", return_value=(mock_pc, mock_index)),
            patch("api.routes.videos.fetch_transcript", return_value=mock_transcript),
            patch("api.routes.videos.fetch_video_metadata", return_value=mock_oembed),
            patch("api.routes.videos.upsert_chunks", return_value=1),
            patch("api.routes.videos.upsert_metadata_record"),
            patch("api.routes.videos.namespace_exists", return_value=False),
        ):
            response = client.post(
                "/api/videos",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["video"]["video_id"] == "dQw4w9WgXcQ"
        assert data["video"]["thumbnail_url"] == mock_oembed["thumbnail_url"]
        assert "limits" in data


class TestPostAsk:
    def test_ask_without_videos_returns_400(self, client):
        response = client.post("/api/ask", json={"question": "What is this?"})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "NO_VIDEOS"

    def test_ask_with_videos_returns_answer(self, client):
        # Pre-load a video into the session
        sid, session = session_module.get_or_create_session(None)
        session["loaded_videos"].append({
            "video_id": "dQw4w9WgXcQ",
            "title": "Test",
            "channel": "TestCh",
            "duration_display": "3:31",
            "thumbnail_url": "",
            "chunk_count": 2,
            "status": "cached",
            "selected": True,
        })

        mock_result = {"messages": [
            MagicMock(content="This is the answer.", tool_calls=[]),
        ]}
        mock_result["messages"][0].tool_calls = []

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = mock_result
        mock_index = MagicMock()
        mock_pc = MagicMock()

        with (
            patch("api.routes.ask.get_pinecone", return_value=(mock_pc, mock_index)),
            patch("api.routes.ask.get_anthropic", return_value=MagicMock()),
            patch("api.routes.ask.get_or_create_agent", return_value=mock_agent),
        ):
            response = client.post(
                "/api/ask",
                json={"question": "What is this about?"},
                headers={"X-Session-ID": sid},
            )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "limits" in data


class TestAuth:
    def test_valid_key(self, client):
        with patch.dict("os.environ", {"VALID_ACCESS_KEYS": "TESTKEY123"}):
            response = client.post("/api/auth", json={"key": "TESTKEY123"})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["limits"]["unlimited"] is True

    def test_invalid_key(self, client):
        with patch.dict("os.environ", {"VALID_ACCESS_KEYS": "TESTKEY123"}):
            response = client.post("/api/auth", json={"key": "WRONGKEY"})
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
