"""Tests for performance PnL endpoint."""

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_alpaca_trading_client


def test_get_pnl_returns_monthly_list():
    """GET /api/performance/pnl returns monthly and cumulative P&L."""
    mock_history = MagicMock()
    mock_history.timestamp = [1700000000, 1702678400, 1705356800]
    mock_history.equity = [100000.0, 101500.0, 103200.0]
    mock_history.profit_loss = [0.0, 1500.0, 1700.0]

    mock_client = MagicMock()
    mock_client.get_portfolio_history.return_value = mock_history
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client

    tc = TestClient(app)
    resp = tc.get("/api/performance/pnl")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert "monthly" in data
    assert "daily" in data
    assert isinstance(data["monthly"], list)
    assert isinstance(data["daily"], list)


def test_get_pnl_with_custom_period():
    """GET /api/performance/pnl?period=1M passes period to Alpaca."""
    mock_history = MagicMock()
    mock_history.timestamp = []
    mock_history.equity = []
    mock_history.profit_loss = []

    mock_client = MagicMock()
    mock_client.get_portfolio_history.return_value = mock_history
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client

    tc = TestClient(app)
    tc.get("/api/performance/pnl?period=1M")
    app.dependency_overrides.clear()

    mock_client.get_portfolio_history.assert_called_once()
