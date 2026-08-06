"""Tests that PortfolioOrchestrator respects strategy rebalance gates (CR-05)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, RebalanceFrequency
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.orchestrator import PortfolioOrchestrator
from src.strategies.registry import StrategyEntry, StrategyRegistry


def _make_registry(entry: StrategyEntry) -> StrategyRegistry:
    reg = StrategyRegistry(load_defaults=False)
    reg.register(entry)
    return reg


def _make_market(price: float = 150.0) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2025, 6, 2, tzinfo=timezone.utc),
        prices={"AAPL": price},
        volumes={"AAPL": 1_000_000.0},
        adv_20d={"AAPL": 1_000_000.0},
    )


def _make_data_replay() -> DataReplay:
    dates = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")
    prices = pd.DataFrame({"AAPL": np.ones(300) * 150.0}, index=dates)
    return DataReplay(prices)


class _GatedStrategy:
    """Strategy with public should_rebalance gate for testing."""

    def __init__(self, weights: dict[str, float]) -> None:
        self._weights = weights
        self._allow_rebalance = True
        self.compute_count = 0
        self.marked_ts = []

    def should_rebalance(self, ts: datetime) -> bool:
        return self._allow_rebalance

    def mark_rebalanced(self, ts: datetime) -> None:
        self.marked_ts.append(ts)

    def compute_target_weights(self, *args, **kwargs) -> dict[str, float]:
        self.compute_count += 1
        return self._weights


def test_orchestrator_skips_compute_when_should_rebalance_false():
    strategy = _GatedStrategy({"AAPL": 1.0})
    strategy._allow_rebalance = False

    entry = StrategyEntry(
        strategy_id="S1",
        strategy_class=_GatedStrategy,
        allocation_pct=0.5,
        schedule="30 14 * * 1-5",
        enabled=True,
    )
    registry = _make_registry(entry)
    orc = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )

    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    result = orc.run_cycle(ts, _make_data_replay(), portfolio, _make_market())

    assert strategy.compute_count == 0
    assert result.final_orders == []


def test_orchestrator_calls_compute_when_should_rebalance_true():
    strategy = _GatedStrategy({"AAPL": 1.0})
    strategy._allow_rebalance = True

    entry = StrategyEntry(
        strategy_id="S1",
        strategy_class=_GatedStrategy,
        allocation_pct=0.5,
        schedule="30 14 * * 1-5",
        enabled=True,
    )
    registry = _make_registry(entry)
    orc = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )

    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    result = orc.run_cycle(ts, _make_data_replay(), portfolio, _make_market())

    assert strategy.compute_count == 1


def test_orchestrator_calls_mark_rebalanced_after_compute():
    strategy = _GatedStrategy({"AAPL": 1.0})
    strategy._allow_rebalance = True

    entry = StrategyEntry(
        strategy_id="S1",
        strategy_class=_GatedStrategy,
        allocation_pct=0.5,
        schedule="30 14 * * 1-5",
        enabled=True,
    )
    registry = _make_registry(entry)
    orc = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )

    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    orc.run_cycle(ts, _make_data_replay(), portfolio, _make_market())

    assert len(strategy.marked_ts) == 1
    assert strategy.marked_ts[0] == ts


# ── #185: hold semantics while the rebalance gate is closed ───────────────────
#
# A blocked sleeve used to contribute {} to the merge, and the orchestrator reads
# "symbol absent from merged_weights" as "sell the whole position". Enforcing the
# declared cadence without these tests would liquidate the S1 book on the first
# gated cycle instead of holding it.


def _gated_setup(weights, allocation_pct=0.5, held_qty=None, price=150.0):
    """Build (orchestrator, portfolio, market) for a strategy with a closed gate."""
    strategy = _GatedStrategy(weights)
    strategy._allow_rebalance = False
    entry = StrategyEntry(
        strategy_id="S1",
        strategy_class=_GatedStrategy,
        allocation_pct=allocation_pct,
        schedule="30 14 * * 1-5",
        enabled=True,
    )
    orc = PortfolioOrchestrator(
        registry=_make_registry(entry),
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    if held_qty:
        portfolio.load_position("AAPL", held_qty, price)
    return strategy, orc, portfolio, _make_market(price)


def test_blocked_gate_does_not_liquidate_the_held_book():
    """The whole point of #185: no s1_weight_drop SELL between two rebalances."""
    _, orc, portfolio, market = _gated_setup({"AAPL": 1.0}, held_qty=100.0)

    result = orc.run_cycle(
        datetime(2025, 6, 20, tzinfo=timezone.utc),
        _make_data_replay(), portfolio, market,
        last_target_weights={"S1": {"AAPL": 1.0}},
    )

    assert result.final_orders == []
    assert "S1" in result.rebalance_skipped


def test_blocked_gate_does_not_drift_trim_after_a_price_move():
    """Holding means holding: a price move must not trigger a rebalance order."""
    # Position loaded at 150, marked at 180 — a 20% drift against a frozen 1.2%
    # target is far outside the orchestrator's 2% delta band.
    _, orc, portfolio, _ = _gated_setup({"AAPL": 1.0}, held_qty=100.0)
    market = _make_market(price=180.0)

    result = orc.run_cycle(
        datetime(2025, 6, 20, tzinfo=timezone.utc),
        _make_data_replay(), portfolio, market,
        last_target_weights={"S1": {"AAPL": 0.012}},
    )

    assert result.final_orders == []


def test_blocked_gate_does_not_re_enter_a_symbol_it_no_longer_holds():
    """A stop-out inside the window must not be undone by the frozen target."""
    _, orc, portfolio, market = _gated_setup({"AAPL": 1.0}, held_qty=None)

    result = orc.run_cycle(
        datetime(2025, 6, 20, tzinfo=timezone.utc),
        _make_data_replay(), portfolio, market,
        last_target_weights={"S1": {"AAPL": 1.0}},
    )

    assert result.final_orders == []


def test_open_gate_publishes_the_computed_weights_for_persistence():
    """The scheduler persists these to seed the next cycle's frozen target."""
    strategy = _GatedStrategy({"AAPL": 0.4})
    strategy._allow_rebalance = True
    entry = StrategyEntry(
        strategy_id="S1",
        strategy_class=_GatedStrategy,
        allocation_pct=0.5,
        schedule="30 14 * * 1-5",
        enabled=True,
    )
    orc = PortfolioOrchestrator(
        registry=_make_registry(entry),
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )

    result = orc.run_cycle(
        datetime(2025, 6, 2, tzinfo=timezone.utc),
        _make_data_replay(), VirtualPortfolio(initial_cash=100_000.0), _make_market(),
    )

    assert result.target_weights_per_strategy == {"S1": {"AAPL": 0.4}}
    assert result.rebalance_skipped == []
