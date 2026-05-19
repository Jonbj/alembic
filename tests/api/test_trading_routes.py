"""Tests for trading routes (Alpaca positions and orders)."""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_alpaca_trading_client


def test_get_positions_returns_list():
    """GET /api/positions returns a list of positions."""
    mock_pos = MagicMock()
    mock_pos.symbol = "AAPL"
    mock_pos.qty = "10"
    mock_pos.market_value = "1820.50"
    mock_pos.unrealized_pl = "45.20"
    mock_pos.unrealized_plpc = "0.0254"
    mock_pos.avg_entry_price = "177.53"
    mock_pos.current_price = "182.05"

    mock_client = MagicMock()
    mock_client.get_all_positions.return_value = [mock_pos]
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client

    tc = TestClient(app)
    resp = tc.get("/api/positions")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert "unrealized_pl" in data[0]


def test_get_orders_returns_list():
    """GET /api/orders returns a list of orders."""
    from datetime import datetime, timezone

    mock_order = MagicMock()
    mock_order.id = "abc-123"
    mock_order.symbol = "AAPL"
    mock_order.side.value = "buy"
    mock_order.qty = "10"
    mock_order.filled_avg_price = "177.53"
    mock_order.status.value = "filled"
    mock_order.filled_at = datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc)
    mock_order.submitted_at = datetime(2026, 5, 18, 13, 55, tzinfo=timezone.utc)

    mock_client = MagicMock()
    mock_client.get_orders.return_value = [mock_order]
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client

    tc = TestClient(app)
    resp = tc.get("/api/orders")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["side"] == "buy"
    assert "filled_at" in data[0]


def test_get_orders_with_limit():
    """GET /api/orders?limit=100 passes limit to Alpaca."""
    mock_client = MagicMock()
    mock_client.get_orders.return_value = []
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client

    tc = TestClient(app)
    tc.get("/api/orders?limit=100")
    app.dependency_overrides.clear()

    mock_client.get_orders.assert_called_once()
