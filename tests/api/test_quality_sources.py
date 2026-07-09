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


def test_rows_converts_decimal_to_float():
    """Postgres NUMERIC columns (e.g. ROUND(...)::numeric) come back from psycopg
    as decimal.Decimal. FastAPI's default JSON encoder serializes Decimal as a
    *string*, silently breaking the `number | null` contract declared for these
    fields in frontend/src/api/quality.ts — and crashing any .toFixed() call on
    the frontend, e.g. Quality.tsx's `trd.total_net_pnl.toFixed(2)` (confirmed via
    a live API call returning `"total_net_pnl":"-208.65"`, a quoted JSON string).
    _rows() must convert Decimal -> float before the value ever reaches FastAPI's
    encoder, at the single chokepoint both quality endpoints share.
    """
    from decimal import Decimal

    from src.api.routes.quality_routes import _rows

    cursor = MagicMock()
    cursor.description = [("source",), ("total_net_pnl",), ("n_trades",)]
    cursor.fetchall.return_value = [("alpaca_benzinga", Decimal("-208.65"), 21)]

    rows = _rows(cursor, "SELECT source, total_net_pnl, n_trades FROM trades")

    assert rows == [{"source": "alpaca_benzinga", "total_net_pnl": -208.65, "n_trades": 21}]
    assert isinstance(rows[0]["total_net_pnl"], float), \
        "Decimal must be converted to float, not left for FastAPI to stringify"
    assert isinstance(rows[0]["n_trades"], int), "non-Decimal values must pass through unchanged"
