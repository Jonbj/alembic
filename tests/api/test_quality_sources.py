"""FIX-04: per-source funnel + latency + P&L endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_sources_endpoint_shape():
    with patch("src.store.pg_store.PostgreSQLStore") as MockStore:
        store = MockStore.return_value.__enter__.return_value
        cursor = MagicMock()
        cursor.description = [("source",), ("n",)]
        cursor.fetchall.return_value = []
        store._get_connection.return_value.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        store._get_connection.return_value.cursor.return_value.__exit__ = MagicMock(return_value=False)
        resp = client.get("/api/quality/sources?days=14")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("window_days", "funnel", "signals", "trades", "trace_coverage"):
        assert key in body


def test_sources_endpoint_survives_db_error():
    """Read-only observability must degrade gracefully, like /api/quality/metrics."""
    with patch("src.store.pg_store.PostgreSQLStore", side_effect=RuntimeError("db down")):
        resp = client.get("/api/quality/sources")
    assert resp.status_code == 200
    assert resp.json()["funnel"] == []
