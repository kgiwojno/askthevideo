"""Tests for src/metadata.py."""

from unittest.mock import patch, MagicMock
import json
from src.metadata import fetch_video_metadata


class TestFetchVideoMetadata:
    def test_valid_video_returns_fields(self):
        mock_data = {
            "title": "Test Video",
            "author_name": "Test Channel",
            "thumbnail_url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(mock_data).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = fetch_video_metadata("abc123")

        assert result["video_title"] == "Test Video"
        assert result["channel"] == "Test Channel"
        assert result["thumbnail_url"] == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"

    def test_invalid_id_returns_fallback(self):
        with patch("urllib.request.urlopen", side_effect=Exception("404")):
            result = fetch_video_metadata("invalid_id_xyz")

        assert result["video_title"] == "Unknown"
        assert result["channel"] == "Unknown"
        assert result["thumbnail_url"] == ""
