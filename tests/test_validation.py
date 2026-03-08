"""Tests for src/transcript.py (extract_video_id) and src/validation.py."""

import pytest
from src.transcript import extract_video_id
from src.validation import validate_question


class TestExtractVideoId:
    def test_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_v_url(self):
        assert extract_video_id("https://www.youtube.com/v/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_raw_video_id(self):
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_raw_video_id_with_underscores(self):
        assert extract_video_id("abc_def-12X") == "abc_def-12X"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError):
            extract_video_id("https://vimeo.com/123456")

    def test_invalid_short_id_raises(self):
        with pytest.raises(ValueError):
            extract_video_id("short")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            extract_video_id("")


class TestValidateQuestion:
    def test_normal_question(self):
        assert validate_question("What is this video about?") == "What is this video about?"

    def test_strips_whitespace(self):
        assert validate_question("  Hello  ") == "Hello"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_question("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            validate_question("   ")

    def test_exactly_500_chars(self):
        q = "a" * 500
        assert validate_question(q) == q

    def test_501_chars_raises(self):
        with pytest.raises(ValueError):
            validate_question("a" * 501)
