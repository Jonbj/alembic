"""Tests for trading routes (Alpaca positions and orders)."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.auth import require_api_key
from src.api.deps import get_alpaca_trading_client, get_pg_store

_skip_auth = lambda: "test-key"


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
    mock_pg = MagicMock()
    mock_pg.fetch_open_trade_entry_time.return_value = "2026-05-18T14:00:00+00:00"
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth

    tc = TestClient(app)
    resp = tc.get("/api/positions")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert "unrealized_pl" in data[0]
    assert data[0]["entry_time"] == "2026-05-18T14:00:00+00:00"


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
    mock_pg = MagicMock()
    mock_pg.fetch_order_trace.return_value = {
        "abc-123": {
            "signal_id": 7,
            "decision_id": 11,
            "news_log_id": 1444,
            "trade_id": 19,
        }
    }
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth

    tc = TestClient(app)
    resp = tc.get("/api/orders")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["side"] == "buy"
    assert "filled_at" in data[0]
    assert data[0]["signal_id"] == 7
    assert data[0]["decision_id"] == 11
    assert data[0]["news_log_id"] == 1444
    assert data[0]["trade_id"] == 19
    mock_pg.fetch_order_trace.assert_called_once_with(["abc-123"])


def test_get_orders_with_limit():
    """GET /api/orders?limit=100 passes limit to Alpaca."""
    mock_client = MagicMock()
    mock_client.get_orders.return_value = []
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client
    app.dependency_overrides[get_pg_store] = lambda: MagicMock()
    app.dependency_overrides[require_api_key] = _skip_auth

    tc = TestClient(app)
    tc.get("/api/orders?limit=100")
    app.dependency_overrides.clear()

    mock_client.get_orders.assert_called_once()


def test_get_orders_with_order_id_fetches_exact_broker_order():
    """GET /api/orders?order_id=... fetches a single broker order and enriches trace."""
    from datetime import datetime, timezone

    mock_order = MagicMock()
    mock_order.id = "order-1"
    mock_order.symbol = "NVDA"
    mock_order.side.value = "sell"
    mock_order.qty = "2"
    mock_order.filled_avg_price = "900.00"
    mock_order.status.value = "filled"
    mock_order.filled_at = datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc)
    mock_order.submitted_at = datetime(2026, 5, 18, 13, 55, tzinfo=timezone.utc)

    mock_client = MagicMock()
    mock_client.get_order_by_id.return_value = mock_order
    mock_pg = MagicMock()
    mock_pg.fetch_order_trace.return_value = {"order-1": {"signal_id": 9, "decision_id": 22, "news_log_id": 33, "trade_id": 44}}
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth

    tc = TestClient(app)
    resp = tc.get("/api/orders?order_id=order-1")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "order-1"
    assert data[0]["decision_id"] == 22
    mock_client.get_order_by_id.assert_called_once_with("order-1")
    mock_client.get_orders.assert_not_called()


class TestTradesEndpoints:
    def test_get_trades_returns_list(self):
        from src.api.deps import get_alpaca_trading_client, get_pg_store
        mock_pg = MagicMock()
        mock_pg.fetch_trades.return_value = [
            {"id": 1, "symbol": "AAPL", "entry_time": "2026-06-05T10:00:00+00:00",
             "net_pnl": 12.5, "exit_time": None}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[get_alpaca_trading_client] = lambda: MagicMock()
        app.dependency_overrides[require_api_key] = lambda: "test-key"

        tc = TestClient(app)
        resp = tc.get("/api/trades")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()[0]["symbol"] == "AAPL"

    def test_get_trades_summary(self):
        from src.api.deps import get_pg_store
        mock_pg = MagicMock()
        mock_pg.fetch_trade_summary.return_value = {
            "total_trades": 5, "win_rate": 0.6, "avg_net_pnl": 14.0,
            "total_net_pnl": 70.0, "trades_per_week": 5.0,
            "avg_gross_pnl": 15.0, "avg_slippage_est": 1.0,
            "total_gross_pnl": 75.0, "total_notional": 3000.0,
            "avg_hold_minutes": 40.0, "return_on_notional": 0.023,
            "slippage_pct_of_gross": 0.07,
        }
        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[require_api_key] = lambda: "test-key"

        tc = TestClient(app)
        resp = tc.get("/api/trades/summary?days=7")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()["total_trades"] == 5

    def test_get_decisions_returns_list(self):
        from src.api.deps import get_pg_store
        mock_pg = MagicMock()
        mock_pg.fetch_decisions.return_value = [
            {"id": 1, "tick_time": "2026-06-05T10:00:00+00:00",
             "symbol": "NVDA", "score": 0.55, "decision": "BUY", "order_id": "x"}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[require_api_key] = lambda: "test-key"

        tc = TestClient(app)
        resp = tc.get("/api/decisions")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()[0]["decision"] == "BUY"
        mock_pg.fetch_decisions.assert_called_once_with(symbol=None, decision_id=None, limit=20)

    def test_get_decisions_by_decision_id(self):
        from src.api.deps import get_pg_store
        mock_pg = MagicMock()
        mock_pg.fetch_decisions.return_value = [
            {"id": 42, "tick_time": "2026-06-05T10:00:00+00:00",
             "symbol": "NVDA", "score": 0.55, "decision": "BUY", "order_id": "order-1",
             "news_log_id": 99}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[require_api_key] = lambda: "test-key"

        tc = TestClient(app)
        resp = tc.get("/api/decisions?decision_id=42")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json()[0]["id"] == 42
        mock_pg.fetch_decisions.assert_called_once_with(symbol=None, decision_id=42, limit=20)

    @pytest.mark.require_auth
    def test_trades_requires_auth(self):
        from src.api.deps import get_pg_store
        # Override pg_store so DB connection doesn't mask the auth error.
        app.dependency_overrides[get_pg_store] = lambda: MagicMock()
        tc = TestClient(app)
        resp = tc.get("/api/trades")
        app.dependency_overrides.clear()
        assert resp.status_code == 403


class TestAnalyticsRoutes:
    def setup_method(self):
        app.dependency_overrides[require_api_key] = lambda: "test-key"

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_analytics_requires_auth(self):
        """Analytics endpoints must reject unauthenticated requests with 403."""
        # Clear setup_method's auth override so the real auth check runs.
        app.dependency_overrides.clear()
        app.dependency_overrides[get_pg_store] = lambda: MagicMock()
        tc = TestClient(app)
        resp = tc.get("/api/trades/analytics/by-symbol")
        app.dependency_overrides.clear()
        assert resp.status_code == 403

    def test_get_analytics_by_symbol(self):
        mock_pg = MagicMock()
        mock_pg.fetch_analytics_by_symbol.return_value = [
            {"label": "NVDA", "trade_count": 3, "win_rate": 0.67,
             "avg_net_pnl": 12.5, "total_net_pnl": 37.5}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/analytics/by-symbol?days=90")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["label"] == "NVDA"

    def test_get_analytics_by_dimension_regime(self):
        mock_pg = MagicMock()
        mock_pg.fetch_analytics_by_regime.return_value = [
            {"label": "neutral", "trade_count": 2, "win_rate": 0.5,
             "avg_net_pnl": 5.0, "total_net_pnl": 10.0}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/analytics/by-dimension?dim=regime")
        assert resp.status_code == 200
        assert resp.json()[0]["label"] == "neutral"

    def test_get_analytics_by_dimension_invalid_dim(self):
        app.dependency_overrides[get_pg_store] = lambda: MagicMock()

        tc = TestClient(app)
        resp = tc.get("/api/trades/analytics/by-dimension?dim=unknown")
        assert resp.status_code == 422

    def test_get_postmortem_returns_trade_dict(self):
        from datetime import datetime, timezone
        now = datetime(2026, 6, 5, 15, tzinfo=timezone.utc)
        mock_pg = MagicMock()
        mock_pg.fetch_trade_with_signal.return_value = {
            "id": 7, "symbol": "NVDA", "net_pnl": -5.0,
            "postmortem_diagnosis": "low_confidence_passed",
            "entry_time": now, "exit_time": now, "signal_generated_at": now,
        }
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/postmortem/7")
        assert resp.status_code == 200
        assert resp.json()["postmortem_diagnosis"] == "low_confidence_passed"

    def test_get_postmortem_404_when_not_found(self):
        mock_pg = MagicMock()
        mock_pg.fetch_trade_with_signal.return_value = None
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/postmortem/999")
        assert resp.status_code == 404


def test_get_orders_origin_strategy():
    """origin_strategy is derived from the trace: 'S4' when a sentiment signal is
    linked, 'S1' when the portfolio path traced the order without a signal
    (momentum orders have no news), None when the order has no local trace."""
    from datetime import datetime, timezone

    def _mk(order_id, symbol):
        o = MagicMock()
        o.id = order_id
        o.symbol = symbol
        o.side.value = "buy"
        o.qty = "10"
        o.filled_avg_price = "100.0"
        o.status.value = "filled"
        o.filled_at = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
        o.submitted_at = datetime(2026, 7, 10, 13, 55, tzinfo=timezone.utc)
        return o

    mock_client = MagicMock()
    mock_client.get_orders.return_value = [
        _mk("ord-news", "PFE"), _mk("ord-momentum", "AAPL"), _mk("ord-untraced", "MSFT"),
    ]
    mock_pg = MagicMock()
    mock_pg.fetch_order_trace.return_value = {
        "ord-news": {"signal_id": 7, "decision_id": 11, "news_log_id": 3, "trade_id": 1},
        "ord-momentum": {"signal_id": None, "decision_id": 12, "news_log_id": None, "trade_id": 2},
    }
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth

    tc = TestClient(app)
    resp = tc.get("/api/orders")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    by_id = {r["id"]: r for r in resp.json()}
    assert by_id["ord-news"]["origin_strategy"] == "S4"
    assert by_id["ord-momentum"]["origin_strategy"] == "S1"
    assert by_id["ord-untraced"]["origin_strategy"] is None
