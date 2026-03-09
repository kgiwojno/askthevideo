"""Tests for src/metrics.py."""

import os
import tempfile

from src.metrics import record_metric, record_tokens, get_metrics, log_event, get_recent_events
import src.metrics as metrics


def test_record_metric():
    before = get_metrics()["total_queries"]
    record_metric("total_queries")
    after = get_metrics()["total_queries"]
    assert after == before + 1


def test_record_tokens():
    before = get_metrics()
    record_tokens(100, 50)
    after = get_metrics()
    assert after["total_input_tokens"] >= before["total_input_tokens"] + 100
    assert after["total_output_tokens"] >= before["total_output_tokens"] + 50
    assert after["estimated_cost"] > 0


def test_log_event(tmp_path):
    original_path = metrics.EVENT_LOG_PATH
    test_log = str(tmp_path / "test_events.log")
    metrics.EVENT_LOG_PATH = test_log
    # Re-create handler pointing at tmp file
    import logging
    from logging.handlers import RotatingFileHandler
    metrics.event_logger.handlers.clear()
    handler = RotatingFileHandler(test_log, maxBytes=500_000, backupCount=1)
    handler.setFormatter(logging.Formatter("%(message)s"))
    metrics.event_logger.addHandler(handler)

    try:
        log_event("QUERY", "free", "127.0.0.1", "test query")
        events = get_recent_events(10)
        assert len(events) >= 1
        assert events[-1]["type"] == "QUERY"
    finally:
        metrics.EVENT_LOG_PATH = original_path


def test_get_metrics_has_computed_fields():
    m = get_metrics()
    assert "uptime_hours" in m
    assert "ram_mb" in m
    assert "cpu_percent" in m
    assert "estimated_cost" in m
    assert "budget_remaining" in m
