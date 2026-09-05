"""#185: the live path honours the declared rebalance_frequency.

The gate lives in the strategy (`should_rebalance`) and the orchestrator already
consulted it, but the scheduler rebuilds every strategy instance from scratch each
cycle: a fresh instance has `_last_rebalance = None`, so the gate answered True at
every one of the ~26 daily cycles. S1 declares MONTHLY and the backtest honours it;
the live path re-decided the whole book every 15 minutes.

These tests pin the clock that closes that hole, and — most importantly — pin that
live and backtest ask the *same* predicate, so they cannot silently diverge again.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.backtest.engine.types import RebalanceFrequency
from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum


def _s1(frequency=RebalanceFrequency.MONTHLY) -> TimeSeriesMomentum:
    dates = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")
    rng = np.random.default_rng(42)
    prices = pd.DataFrame(
        {sym: 100.0 + np.cumsum(rng.normal(0.05, 1.0, 300)) for sym in ("AAPL", "MSFT")},
        index=dates,
    )
    return TimeSeriesMomentum(prices=prices, config=S1Config(rebalance_frequency=frequency))


# ── the clock survives the per-cycle instance rebuild ─────────────────────────


def test_fresh_instance_has_no_memory_so_its_gate_is_always_open():
    """The defect, stated as a test: this is why S1 rebalanced every 15 minutes."""
    assert _s1().should_rebalance(datetime(2026, 8, 5, 14, 7, tzinfo=timezone.utc)) is True
    assert _s1().should_rebalance(datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc)) is True


def test_seeded_instance_refuses_a_second_rebalance_in_the_same_month():
    from src.workers.portfolio_scheduler import _seed_rebalance_clock

    instances = {"S1": _s1()}
    _seed_rebalance_clock(
        instances,
        {"S1": {"last_rebalance": "2026-08-05T14:07:00+00:00", "target_weights": {"AAPL": 0.012}}},
    )

    assert instances["S1"].should_rebalance(datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc)) is False
    assert instances["S1"].should_rebalance(datetime(2026, 8, 31, 19, 52, tzinfo=timezone.utc)) is False
    assert instances["S1"].should_rebalance(datetime(2026, 9, 1, 14, 7, tzinfo=timezone.utc)) is True


def test_seeding_is_scoped_to_the_strategies_the_fix_covers():
    """S4 is deliberately left un-seeded — see _REBALANCE_CLOCK_STRATEGIES."""
    from src.workers.portfolio_scheduler import _REBALANCE_CLOCK_STRATEGIES, _seed_rebalance_clock

    instance = MagicMock()
    instance._last_rebalance = None
    _seed_rebalance_clock(
        {"S9": instance},
        {"S9": {"last_rebalance": "2026-08-05T14:07:00+00:00", "target_weights": {}}},
    )

    assert "S9" not in _REBALANCE_CLOCK_STRATEGIES
    assert instance._last_rebalance is None


def test_unparseable_state_leaves_the_gate_open():
    """Fail-open: a corrupt key must not freeze the strategy forever."""
    from src.workers.portfolio_scheduler import _seed_rebalance_clock

    instances = {"S1": _s1()}
    _seed_rebalance_clock(instances, {"S1": {"last_rebalance": "not-a-date"}})

    assert instances["S1"].should_rebalance(datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc)) is True


# ── persistence ───────────────────────────────────────────────────────────────


def test_persist_writes_only_the_strategies_that_actually_rebalanced():
    from src.workers.portfolio_scheduler import _persist_rebalance_state

    result = MagicMock()
    result.target_weights_per_strategy = {"S1": {"AAPL": 0.012}}
    result.rebalance_skipped = ["S4"]

    redis_inst = MagicMock()
    ts = datetime(2026, 8, 5, 14, 7, tzinfo=timezone.utc)
    with patch("redis.Redis.from_url", return_value=redis_inst):
        _persist_rebalance_state(result, ts, "redis://localhost")

    assert redis_inst.set.call_count == 1
    key, raw = redis_inst.set.call_args[0][:2]
    assert key == "strategy:rebalance_state:S1"
    payload = json.loads(raw)
    assert payload["last_rebalance"] == ts.isoformat()
    assert payload["target_weights"] == {"AAPL": 0.012}


def test_persist_adds_s1_sizing_metrics_to_the_rebalance_state():
    from src.workers.portfolio_scheduler import _persist_rebalance_state

    result = MagicMock()
    result.target_weights_per_strategy = {"S1": {"AAPL": 0.012}}
    metrics = {
        "n_target": 46,
        "n_eff": 44.7,
        "cap_bound_share": 0.761,
        "spearman_signal_weight": -0.621,
    }

    redis_inst = MagicMock()
    ts = datetime(2026, 9, 1, 14, 7, tzinfo=timezone.utc)
    with patch("redis.Redis.from_url", return_value=redis_inst):
        _persist_rebalance_state(
            result,
            ts,
            "redis://localhost",
            sizing_metrics_by_strategy={"S1": metrics},
        )

    payload = json.loads(redis_inst.set.call_args[0][1])
    assert payload["sizing_metrics"] == metrics


def test_persist_ignores_strategies_outside_the_clock_scope():
    from src.workers.portfolio_scheduler import _persist_rebalance_state

    result = MagicMock()
    result.target_weights_per_strategy = {"S4": {"NVDA": 0.05}}
    result.rebalance_skipped = []

    redis_inst = MagicMock()
    with patch("redis.Redis.from_url", return_value=redis_inst):
        _persist_rebalance_state(result, datetime(2026, 8, 5, tzinfo=timezone.utc), "redis://x")

    redis_inst.set.assert_not_called()


# ── live and backtest must not diverge again ──────────────────────────────────


def test_live_gate_and_backtest_gate_are_the_same_predicate():
    """DoD of #185: one predicate, two call sites.

    The orchestrator (live) must not reimplement the cadence rule that
    `TimeSeriesMomentum.__call__` (backtest) applies — otherwise the two drift
    apart in silence, which is how this bug survived for months.
    """
    from src.portfolio.orchestrator import PortfolioOrchestrator

    live = _s1()
    backtest = _s1()
    seeded = datetime(2026, 8, 5, 14, 7, tzinfo=timezone.utc)
    live.mark_rebalanced(seeded)
    backtest.mark_rebalanced(seeded)

    for ts in (
        datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc),
        datetime(2026, 8, 20, 16, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 1, 14, 7, tzinfo=timezone.utc),
    ):
        assert PortfolioOrchestrator._gate_open(live, ts) == backtest._should_rebalance(ts)


def test_zero_weights_alert_ignores_a_strategy_that_is_merely_holding():
    """A gated sleeve reports 0 weights when it holds nothing — not a silent death."""
    from src.workers.portfolio_scheduler import (
        _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES,
        _check_strategy_zero_weights,
    )

    result = MagicMock()
    result.strategies_run = ["S1"]
    result.orders_per_strategy = {"S1": 0}
    result.rebalance_skipped = ["S1"]

    redis_inst = MagicMock()
    redis_inst.incr.side_effect = list(range(1, _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES + 1))

    with patch("redis.Redis.from_url", return_value=redis_inst), \
         patch("src.workers.portfolio_scheduler._fire_alert") as mock_fire:
        for _ in range(_STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES):
            _check_strategy_zero_weights(result, {"S1"}, "redis://localhost", MagicMock())

    mock_fire.assert_not_called()
