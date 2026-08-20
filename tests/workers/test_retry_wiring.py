"""Wiring tests: assert each Alpaca read call site routes through retry_transient.

These are spy tests: patch retry_transient in the target module to a recording
stub, invoke the function, and assert the stub was called with the broker read.
This verifies the wiring without a live Alpaca call.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _spy_retry(monkeypatch, module_path):
    """Patch retry_transient in module_path to a spy that delegates to fn()."""
    calls: list = []

    def spy(fn, **kwargs):
        calls.append((fn, kwargs))
        return fn()

    # Two-arg dotted form so pytest resolves module_path as an import path
    # (the three-arg form with a string target would getattr on the string).
    monkeypatch.setattr(f"{module_path}.retry_transient", spy)
    return calls


# --- get_account wiring ------------------------------------------------------

def test_risk_monitor_get_account_uses_retry(monkeypatch):
    """risk_monitor_task._fetch_account_state creates its own TradingClient, so
    patch the constructor to return a mock and assert get_account routes through
    retry_transient."""
    from src.workers import risk_monitor_task
    calls = _spy_retry(monkeypatch, "src.workers.risk_monitor_task")

    client = MagicMock()
    acct = MagicMock()
    acct.equity = "100000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []
    monkeypatch.setattr("alpaca.trading.client.TradingClient", lambda **kw: client)

    equity, exposure = risk_monitor_task._fetch_account_state()
    assert equity == 100000.0
    assert exposure == 0.0
    # retry_transient was invoked for get_account (and get_all_positions).
    assert any(c[0] == client.get_account for c in calls)


def test_execution_get_account_uses_retry(monkeypatch):
    from src.workers import execution
    calls = _spy_retry(monkeypatch, "src.workers.execution")

    client = MagicMock()
    acct = MagicMock()
    acct.portfolio_value = "100000"
    acct.last_equity = "99000"
    acct.buying_power = "100000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []
    client.get_orders.return_value = []

    redis = MagicMock()
    redis.is_killswitch_active.return_value = False
    redis.read_sentiment.return_value = None  # no signal -> skip symbol, clean return
    regime = MagicMock()
    regime.multiplier = 1.0
    redis.get_regime.return_value = regime
    redis.get_feedback_entry_threshold.return_value = None
    redis.get_feedback_regime_scale.return_value = None
    notifier = MagicMock()
    notifier.send_alert = MagicMock()

    stats = execution.run_execution_cycle(
        ["AAPL"], redis, client, data_client=MagicMock(), notifier=notifier
    )
    assert any(c[0] == client.get_account for c in calls)


def test_performance_broker_mtm_uses_retry(monkeypatch):
    from src.workers import performance
    calls = _spy_retry(monkeypatch, "src.workers.performance")

    client = MagicMock()
    acct = MagicMock()
    acct.equity = "100000"
    acct.last_equity = "99000"
    acct.portfolio_value = "100000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []
    client.get_portfolio_history.return_value = MagicMock(profit_loss=[])

    result = performance._broker_mtm_snapshot(client)
    assert result is not None
    assert any(c[0] == client.get_account for c in calls)


def test_mobile_snapshot_get_account_uses_retry(monkeypatch):
    """MobileSnapshotBuilder wraps get_account via asyncio.to_thread(retry_transient, ...)."""
    import asyncio
    from src.mobile_monitoring import builder
    calls = _spy_retry(monkeypatch, "src.mobile_monitoring.builder")

    # Bypass __init__ (needs pool/redis); set only the attribute _broker_snapshot reads.
    b = builder.MobileSnapshotBuilder.__new__(builder.MobileSnapshotBuilder)
    b.alpaca = MagicMock()
    b.alpaca.get_account.return_value = MagicMock(equity="100", last_equity="99", cash="10")
    b.alpaca.get_all_positions.return_value = []

    account, positions = asyncio.run(b._broker_snapshot([]))
    assert account is not None
    assert any(c[0] == b.alpaca.get_account for c in calls)

# --- get_all_positions wiring ------------------------------------------------

def test_portfolio_scheduler_positions_load_uses_retry(monkeypatch):
    """The protective-stop sync path (portfolio_scheduler get_all_positions) routes
    through retry_transient."""
    from datetime import datetime, timezone
    from src.workers import portfolio_scheduler
    calls = _spy_retry(monkeypatch, "src.workers.portfolio_scheduler")

    client = MagicMock()
    client.get_all_positions.return_value = []
    client.get_orders.return_value = []

    from src.portfolio.stop_policy import StopPolicy
    summary = portfolio_scheduler._sync_fractional_protective_stops(
        client,
        StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0,
                    "broker_disaster_stop": {"multiplier": 1.5, "sigma_multiple": 5.0,
                                             "floor_pct": 0.12, "cap_pct": 0.20}}),
        cycle_ts=datetime(2026, 8, 7, 15, 0, tzinfo=timezone.utc),
    )
    assert any(c[0] == client.get_all_positions for c in calls)


def test_execution_get_all_positions_uses_retry(monkeypatch):
    from src.workers import execution
    calls = _spy_retry(monkeypatch, "src.workers.execution")

    client = MagicMock()
    acct = MagicMock()
    acct.portfolio_value = "100000"
    acct.last_equity = "99000"
    acct.buying_power = "100000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []
    client.get_orders.return_value = []

    redis = MagicMock()
    redis.is_killswitch_active.return_value = False
    redis.read_sentiment.return_value = None  # no signal -> skip symbol, clean return
    regime = MagicMock()
    regime.multiplier = 1.0
    redis.get_regime.return_value = regime
    redis.get_feedback_entry_threshold.return_value = None
    redis.get_feedback_regime_scale.return_value = None
    notifier = MagicMock()
    notifier.send_alert = MagicMock()

    execution.run_execution_cycle(
        ["AAPL"], redis, client, data_client=MagicMock(), notifier=notifier
    )
    assert any(c[0] == client.get_all_positions for c in calls)


def test_performance_reconcile_get_all_positions_uses_retry(monkeypatch):
    """run_reconcile_positions (PR #318, post-plan) reads broker positions via
    get_all_positions; assert it routes through retry_transient."""
    from types import SimpleNamespace
    from src.workers import performance
    calls = _spy_retry(monkeypatch, "src.workers.performance")

    # config is a frozen pydantic model; swap the module name for a plain object
    # with just the attrs run_reconcile_positions reads.
    monkeypatch.setattr(
        "src.workers.performance.config",
        SimpleNamespace(
            ALPACA_API_KEY="test-key", ALPACA_SECRET_KEY="test-secret",
            ALPACA_PAPER_MODE=True, RECONCILE_AUTOCLOSE_ENABLED=False,
            RECONCILE_AUTOCLOSE_DRY_RUN=True,
        ),
    )

    client = MagicMock()
    client.get_all_positions.return_value = []
    monkeypatch.setattr("alpaca.trading.client.TradingClient", lambda **kw: client)

    pg_mock = MagicMock()
    pg_mock.fetch_trades.return_value = []
    monkeypatch.setattr("src.workers.performance.PostgreSQLStore", lambda *a, **kw: pg_mock)

    result = performance.run_reconcile_positions()
    assert "error" not in result  # did not hit the function-level degrade
    assert any(c[0] == client.get_all_positions for c in calls)


# --- get_stock_bars / get_stock_snapshot wiring ------------------------------

def test_execution_build_market_cache_uses_retry(monkeypatch):
    """execution._build_market_cache (get_stock_bars) routes through retry_transient."""
    from src.workers import execution
    calls = _spy_retry(monkeypatch, "src.workers.execution")

    data_client = MagicMock()
    bars_df = MagicMock()
    bars_df.empty = True
    data_client.get_stock_bars.return_value = MagicMock(df=bars_df)

    execution._build_market_cache(["AAPL"], data_client)
    assert any(callable(c[0]) for c in calls)
    data_client.get_stock_bars.assert_called()


def test_performance_forward_return_worker_uses_retry(monkeypatch):
    """run_forward_return_worker (get_stock_bars) routes through retry_transient."""
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from src.workers import performance
    calls = _spy_retry(monkeypatch, "src.workers.performance")

    monkeypatch.setattr(
        "src.workers.performance.config",
        SimpleNamespace(
            ALPACA_API_KEY="test-key", ALPACA_SECRET_KEY="test-secret",
            DATABASE_URL="postgresql://u:p@localhost:5432/db",
        ),
    )

    monkeypatch.setattr("psycopg2.connect", lambda *a, **kw: MagicMock())

    pg_mock = MagicMock()
    pg_mock.fetch_signals_pending_forward_return.return_value = [
        (1, "AAPL", datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc))
    ]
    monkeypatch.setattr("src.workers.performance.PostgreSQLStore", lambda **kw: pg_mock)

    data_client_mock = MagicMock()
    bars_df = MagicMock()
    bars_df.empty = True
    bars_df.index.get_level_values.return_value = []
    data_client_mock.get_stock_bars.return_value = MagicMock(df=bars_df)
    monkeypatch.setattr(
        "alpaca.data.historical.StockHistoricalDataClient", lambda **kw: data_client_mock
    )

    performance.run_forward_return_worker()
    assert any(callable(c[0]) for c in calls)
