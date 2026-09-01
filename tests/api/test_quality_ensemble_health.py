"""#427: per-cycle ensemble-health endpoint on the Quality dashboard."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_endpoint_shape():
    """The endpoint must return window_days, cycles, summary on success."""
    with patch("src.store.pg_store.PostgreSQLStore") as MockStore:
        store = MockStore.return_value.__enter__.return_value
        cursor = MagicMock()
        cursor.description = [("a",)]
        cursor.fetchall.return_value = []
        store._get_connection.return_value.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        store._get_connection.return_value.cursor.return_value.__exit__ = MagicMock(return_value=False)
        resp = client.get("/api/quality/ensemble_health?days=7")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("window_days", "cycles", "summary"):
        assert key in body, f"missing key {key} in {body}"


def test_endpoint_survives_db_error():
    """Read-only observability must degrade gracefully, like /api/quality/metrics."""
    with patch("src.store.pg_store.PostgreSQLStore", side_effect=RuntimeError("db down")):
        resp = client.get("/api/quality/ensemble_health")
    assert resp.status_code == 200
    assert resp.json()["cycles"] == []


def test_endpoint_computes_full_ensemble_share_from_summary():
    """The aggregate full_ensemble_share is the metric #427 needs surfaced —
    the same number the in-worker Telegram alert compares against 0.5."""
    with patch("src.store.pg_store.PostgreSQLStore") as MockStore:
        store = MockStore.return_value.__enter__.return_value
        cursor = MagicMock()

        # The endpoint runs two queries. Each query reassigns `cur.description`
        # in real psycopg; on MagicMock the attribute must change between
        # fetchall calls so `_rows` reads the right column list. Real cursors
        # reset description on execute; we mirror that explicitly here.
        cycle_desc = [("cycle_started_at",), ("cycle_ended_at",),
                      ("n_ensemble",), ("n_single",), ("n_finbert",),
                      ("aggregate",), ("rth",)]
        summary_desc = [("n_cycles",), ("total_ensemble",), ("total_single",),
                        ("total_finbert",), ("total_aggregate",),
                        ("rth_cycles",), ("rth_share",)]
        cursor.fetchall.side_effect = [
            [],  # per-cycle detail (none in this test)
            # Column order matches the aggregate SELECT:
            # n_cycles, total_ensemble, total_single, total_finbert,
            # total_aggregate, rth_cycles, rth_share.
            # 2 cycles; 8 ensemble / 2 single / 20 finbert = 30 total.
            [(2, 8, 2, 20, 30, 1, 0.5)],
        ]
        def _execute(sql, params):
            # First call is the per-cycle query; second is the aggregate.
            cursor.description = (
                cycle_desc if "ensemble_cycle_health" in sql and "ORDER BY" in sql
                else summary_desc
            )
        cursor.execute.side_effect = _execute

        store._get_connection.return_value.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        store._get_connection.return_value.cursor.return_value.__exit__ = MagicMock(return_value=False)
        resp = client.get("/api/quality/ensemble_health?days=7")
    assert resp.status_code == 200
    body = resp.json()
    # full_ensemble_share = total_ensemble / total_aggregate = 8 / 30 ≈ 0.267
    assert body["summary"]["full_ensemble_share"] == round(8 / 30, 3)