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