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


# ── /api/performance/daily — NAV mark-to-market enrichment ────────────────────
# The Giornaliero page summed closed trades only: 2026-07-17 showed −$18.46
# while the real day was −$115.60 NAV. Day rows and summary now carry the
# mark-to-market NAV change from risk_reports snapshots.

from src.api.deps import get_pg_store


def _daily_pg_mock(day_rows, nav_rows):
    pg = MagicMock()
    pg.fetch_daily_pnl.return_value = day_rows
    pg.fetch_nav_daily.return_value = nav_rows
    return pg


def _day(date_str, net=0.0):
    return {
        "date": date_str, "trades_closed": 1, "total_gross_pnl": net,
        "total_costs": 0.0, "total_net_pnl": net, "winners": 0, "losers": 1,
        "trades": [],
    }


def test_daily_pnl_days_carry_nav_mtm_change():
    pg = _daily_pg_mock(
        day_rows=[_day("2026-07-16", -83.88), _day("2026-07-17", -18.46)],
        nav_rows=[
            {"date": "2026-07-15", "nav": 100.0},
            {"date": "2026-07-16", "nav": 90.0},
            {"date": "2026-07-17", "nav": 85.0},
        ],
    )
    app.dependency_overrides[get_pg_store] = lambda: pg
    tc = TestClient(app)
    resp = tc.get("/api/performance/daily?from_date=2026-07-16&to_date=2026-07-17")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    days = resp.json()["days"]
    assert days[0]["nav_eod"] == 90.0
    assert days[0]["nav_change_1d"] == -10.0
    assert days[1]["nav_change_1d"] == -5.0
    # summary: last snapshot in range vs last snapshot BEFORE from_date
    assert resp.json()["summary"]["nav_change_period"] == -15.0


def test_daily_pnl_nav_fields_null_without_snapshot():
    pg = _daily_pg_mock(
        day_rows=[_day("2026-07-17", -18.46)],
        nav_rows=[],
    )
    app.dependency_overrides[get_pg_store] = lambda: pg
    tc = TestClient(app)
    resp = tc.get("/api/performance/daily?from_date=2026-07-17&to_date=2026-07-17")
    app.dependency_overrides.clear()

    day = resp.json()["days"][0]
    assert day["nav_change_1d"] is None
    assert day["nav_eod"] is None
    assert resp.json()["summary"]["nav_change_period"] is None
