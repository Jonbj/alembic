"""Tests for the QX-01 golden label set annotation routes."""
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.auth import require_api_key
import pytest


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[require_api_key] = lambda: "test-key"
    yield
    app.dependency_overrides.pop(require_api_key, None)


def test_next_item_orders_full_text_adequacy_before_headline_only():
    """GET /api/labeling/next must prioritize text_adequacy='full' pending rows
    over 'headline_only' ones, not just serve the oldest label_id first."""
    fake_cursor = MagicMock()
    fake_cursor.fetchone.return_value = None
    fake_cursor.__enter__.return_value = fake_cursor
    fake_cursor.__exit__.return_value = False

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    fake_store = MagicMock()
    fake_store._get_connection.return_value = fake_conn
    fake_store.__enter__.return_value = fake_store
    fake_store.__exit__.return_value = False

    with patch("src.api.routes.labeling_routes._store", return_value=fake_store):
        tc = TestClient(app)
        resp = tc.get("/api/labeling/next", headers={"X-API-Key": "test-key"})

    assert resp.status_code == 200
    executed_sql = fake_cursor.execute.call_args[0][0]
    # The ORDER BY must rank full-text rows first, then fall back to label_id.
    assert "text_adequacy = 'full'" in executed_sql or "text_adequacy='full'" in executed_sql
    order_by_clause = executed_sql[executed_sql.upper().index("ORDER BY"):]
    adequacy_index = order_by_clause.index("text_adequacy")
    label_id_index = order_by_clause.rindex("label_id")
    assert adequacy_index < label_id_index
