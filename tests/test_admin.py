"""Tests for admin endpoints."""

import os
os.environ.setdefault("ADMIN_TOKEN", "dupa.8")

from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_admin_auth_valid():
    res = client.post("/api/admin/auth", json={"token": "dupa.8"})
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_admin_auth_invalid():
    res = client.post("/api/admin/auth", json={"token": "wrong"})
    assert res.status_code == 200
    assert res.json()["valid"] is False


def test_admin_metrics_no_token():
    res = client.get("/api/admin/metrics")
    assert res.status_code == 403


@patch("api.routes.admin.get_pinecone")
def test_admin_metrics_valid(mock_pc):
    mock_index = mock_pc.return_value[1]
    mock_index.describe_index_stats.return_value = {
        "namespaces": {},
        "total_vector_count": 0,
    }
    res = client.get("/api/admin/metrics", headers={"X-Admin-Token": "dupa.8"})
    assert res.status_code == 200
    data = res.json()
    assert "realtime" in data
    assert "sessions" in data
    assert "cost" in data
    assert "pinecone" in data
    assert "events" in data
