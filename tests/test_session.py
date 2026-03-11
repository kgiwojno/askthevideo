"""Tests for api/session.py."""

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import api.session as session_module
from api.session import get_or_create_session, build_limits


@pytest.fixture(autouse=True)
def clear_sessions():
    """Reset global sessions dict between tests."""
    session_module.sessions.clear()
    yield
    session_module.sessions.clear()


class TestGetOrCreateSession:
    def test_creates_new_session_when_none(self):
        sid, session = get_or_create_session(None)
        assert sid is not None
        assert session["loaded_videos"] == []
        assert session["question_count"] == 0
        assert session["unlimited"] is False

    def test_returns_existing_session(self):
        sid1, _ = get_or_create_session(None)
        sid2, session2 = get_or_create_session(sid1)
        assert sid2 == sid1

    def test_creates_new_when_id_not_found(self):
        sid, _ = get_or_create_session("nonexistent-id")
        assert sid != "nonexistent-id"

    def test_ttl_expiration(self):
        sid, _ = get_or_create_session(None)
        # Backdate creation time past TTL
        session_module.sessions[sid]["created_at"] = datetime.utcnow() - timedelta(hours=3)
        # Creating a new session should clean up expired ones
        new_sid, _ = get_or_create_session(None)
        assert sid not in session_module.sessions
        assert new_sid in session_module.sessions


class TestBuildLimits:
    def test_free_limits(self):
        _, session = get_or_create_session(None)
        limits = build_limits(session)
        assert limits["videos_max"] == 3
        assert limits["questions_max"] == 5
        assert limits["unlimited"] is False
        assert limits["videos_loaded"] == 0
        assert limits["questions_used"] == 0

    def test_unlimited_limits(self):
        _, session = get_or_create_session(None)
        session["unlimited"] = True
        limits = build_limits(session)
        assert limits["videos_max"] is None
        assert limits["questions_max"] is None
        assert limits["unlimited"] is True
