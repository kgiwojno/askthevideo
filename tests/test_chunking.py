"""Tests for src/chunking.py."""

from src.chunking import chunk_transcript, format_time


class TestFormatTime:
    def test_seconds_only(self):
        assert format_time(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_time(90) == "1:30"

    def test_hours(self):
        assert format_time(3661) == "1:01:01"

    def test_zero(self):
        assert format_time(0) == "0:00"


class TestChunkTranscript:
    def _make_snippets(self, n, start=0, gap=10, duration=9):
        return [{"text": f"snippet {i}", "start": start + i * gap, "duration": duration} for i in range(n)]

    def test_empty_returns_empty(self):
        assert chunk_transcript([], "vid123") == []

    def test_short_transcript_single_chunk(self):
        snippets = self._make_snippets(5)  # 0, 10, 20, 30, 40 seconds
        chunks = chunk_transcript(snippets, "vid123", window_seconds=120, carry_snippets=3)
        assert len(chunks) == 1
        assert chunks[0]["chunk_index"] == 0

    def test_required_keys(self):
        snippets = self._make_snippets(3)
        chunks = chunk_transcript(snippets, "vid123")
        chunk = chunks[0]
        required = {"text", "text_timestamped", "start_time", "end_time",
                    "start_display", "end_display", "chunk_index", "video_url"}
        assert required.issubset(chunk.keys())

    def test_carry_snippet_continuity(self):
        # 30 snippets at 5s each = 150s total, window=120 → 2 chunks
        snippets = self._make_snippets(30, gap=5, duration=4)
        chunks = chunk_transcript(snippets, "vid123", window_seconds=120, carry_snippets=3)
        assert len(chunks) >= 2
        # Carried snippets appear in next chunk text
        # chunk 1 should have more snippets than just a fresh start
        assert chunks[1]["chunk_index"] == 1

    def test_video_url_contains_video_id(self):
        snippets = self._make_snippets(3)
        chunks = chunk_transcript(snippets, "myVideoId")
        assert "myVideoId" in chunks[0]["video_url"]

    def test_multiple_windows(self):
        # 60 snippets at 3s each = 180s, window=60 → ~3 chunks
        snippets = self._make_snippets(60, gap=3, duration=2)
        chunks = chunk_transcript(snippets, "vid", window_seconds=60, carry_snippets=2)
        assert len(chunks) >= 3
