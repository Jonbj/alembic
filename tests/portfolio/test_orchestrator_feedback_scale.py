"""F8: PortfolioOrchestrator applies a per-strategy feedback regime scale to
each strategy's sleeve contribution BEFORE the weighted-sum merge.

The feedback:regime_scale:S* keys (written by performance.run_loss_feedback_check,
post Phase 5) are a symmetric de-risk/re-risk throttle: ×regime_scale_factor on a
loss trigger (floored at regime_min_scale), ÷regime_scale_factor on recovery/decay
(capped at 1.0). The orchestrator receives them as a `feedback_scales` dict
(strategy_id -> scale, default 1.0) injected by the scheduler, and multiplies each
strategy's `wt * alloc` by its own scale. This preserves the per-strategy decouple
(Phase 5): a loss in S1 shrinks only S1's contribution, not S4's.

Invariants tested:
  - feedback_scales={S:0.5} halves S's merged contribution (qty halves).
  - per-strategy isolation: scaling S4 does not touch S1's contribution.
  - feedback_scales=None (default) is identity — zero behavior change when the
    scheduler leaves the flag off.
"""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.orchestrator import PortfolioOrchestrator
from src.strategies.registry import StrategyEntry, StrategyRegistry


def _make_registry(entries):
    registry = StrategyRegistry(load_defaults=False)
    for e in entries:
        registry.register(e)
    return registry


def _make_market(symbols=("AAPL",), price=100.0):
    return MarketSnapshot(
        timestamp=datetime(2024, 1, 15),
        prices={s: price for s in symbols},
        volumes={s: 1_000_000.0 for s in symbols},
        adv_20d={s: 1_000_000.0 for s in symbols},
    )


def _make_data_replay(symbols=("AAPL",)):
    dates = pd.date_range("2023-01-01", periods=50, freq="B")
    prices = pd.DataFrame({s: np.ones(50) * 100.0 for s in symbols}, index=dates)
    return DataReplay(prices)


def _make_portfolio(cash=100_000.0):
    return VirtualPortfolio(initial_cash=cash)


def _buy_order(symbol="AAPL", qty=100.0, strategy_id="S1"):
    return Order.market_order(datetime(2024, 1, 15), symbol, OrderSide.BUY, qty, strategy_id)


class _FixedStrategy:
    def __init__(self, orders=None):
        self.orders = orders or []

    def __call__(self, ts, data_replay, portfolio, market):
        return self.orders


# ── feedback_scales multiplies a strategy's sleeve contribution ────────────────

def test_feedback_scale_halves_strategy_contribution():
    """feedback_scales={S4:0.5} halves S4's merged contribution.

    Baseline: 300 qty × $100 / $100k = 0.30 sleeve × 0.10 alloc → 3% → 30 shares.
    With scale 0.5: 30 × 0.5 = 15 shares.
    """
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entry = StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
        feedback_scales={"S4": 0.5},
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl) == 1
    assert aapl[0].quantity == pytest.approx(15.0, rel=0.01), (
        "feedback_scales=0.5 must halve the strategy's merged contribution"
    )


def test_feedback_scale_none_is_identity():
    """feedback_scales=None (default) leaves the contribution unchanged —
    zero behavior change when the scheduler flag is off."""
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entry = StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl) == 1
    # 30 shares, unscaled
    assert aapl[0].quantity == pytest.approx(30.0, rel=0.01)


def test_feedback_scale_missing_strategy_defaults_to_one():
    """A strategy not present in feedback_scales defaults to 1.0 (unscaled)."""
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entry = StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
        feedback_scales={"S1": 0.5},  # S4 not present → default 1.0
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert len(aapl) == 1
    assert aapl[0].quantity == pytest.approx(30.0, rel=0.01)


# ── per-strategy isolation: scaling one strategy does not touch the other ──────

def test_feedback_scale_isolates_strategies():
    """Scaling S4 must not change S1's contribution (Phase 5 decouple preserved).

    Two strategies both buying AAPL:
      S1 (alloc 0.50, 100 qty): sleeve 0.10 × 0.50 = 0.05 → 50 shares
      S4 (alloc 0.10, 300 qty): sleeve 0.30 × 0.10 = 0.03 → 30 shares
    Baseline merge = 80 shares.
    With feedback_scales={S4:0.5}: S1 unchanged (50) + S4 halved (15) = 65 shares.
    """
    s1 = _FixedStrategy([_buy_order("AAPL", qty=100.0, strategy_id="S1")])
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entries = [
        StrategyEntry("S1", _FixedStrategy, 0.50, "30 14 * * 1-5"),
        StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5"),
    ]
    registry = _make_registry(entries)
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S4": s4},
        constraint_enforcer=ConstraintEnforcer(max_single_asset_pct=0.30),
    )

    # Baseline (no scale)
    base = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
    )
    base_aapl = [o for o in base.final_orders if o.symbol == "AAPL"]
    assert base_aapl[0].quantity == pytest.approx(80.0, rel=0.01), (
        "baseline S1(50) + S4(30) = 80 shares"
    )

    # New portfolio instance for the scaled run (run_cycle mutates portfolio state)
    scaled = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
        feedback_scales={"S4": 0.5},
    )
    scaled_aapl = [o for o in scaled.final_orders if o.symbol == "AAPL"]
    assert scaled_aapl[0].quantity == pytest.approx(65.0, rel=0.01), (
        "S1 unchanged (50) + S4 halved (15) = 65 shares — S4's scale must not "
        "bleed into S1's contribution"
    )


def test_feedback_shadow_records_unscaled_and_scaled_weight():
    """F8 shadow: CycleResult.feedback_shadow records, per strategy with a
    non-identity scale, the unscaled vs scaled sleeve contribution so the
    scheduler can log the deployment delta without applying the scale live."""
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entry = StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
        feedback_scales={"S4": 0.5},
    )
    assert "S4" in result.feedback_shadow, "scaled strategy must appear in shadow"
    row = result.feedback_shadow["S4"]
    assert row["scale"] == pytest.approx(0.5)
    # sleeve weight 0.30 × alloc 0.10 = 0.03 unscaled; × 0.5 = 0.015 scaled
    assert row["unscaled_weight"] == pytest.approx(0.03, rel=0.01)
    assert row["scaled_weight"] == pytest.approx(0.015, rel=0.01)
    assert row["applied"] is True


def test_apply_feedback_scale_false_shadows_without_applying():
    """measure-before-enforce: apply_feedback_scale=False leaves weights unscaled
    (no behavior change) but still records the would-be delta in feedback_shadow."""
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entry = StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
        feedback_scales={"S4": 0.5},
        apply_feedback_scale=False,
    )
    # Weights NOT scaled — 30 shares (baseline), not 15
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert aapl[0].quantity == pytest.approx(30.0, rel=0.01), (
        "apply_feedback_scale=False must not change sizing"
    )
    # But the shadow records the would-be delta
    assert "S4" in result.feedback_shadow
    row = result.feedback_shadow["S4"]
    assert row["scale"] == pytest.approx(0.5)
    assert row["scaled_weight"] == pytest.approx(0.015, rel=0.01)
    assert row["applied"] is False


# ── per-strategy apply gate (#32): allowlist instead of a global bool ─────────

def _two_sleeve_orch():
    """S1 (alloc 0.50, 100 qty) + S4 (alloc 0.10, 300 qty), both buying AAPL."""
    s1 = _FixedStrategy([_buy_order("AAPL", qty=100.0, strategy_id="S1")])
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    registry = _make_registry([
        StrategyEntry("S1", _FixedStrategy, 0.50, "30 14 * * 1-5"),
        StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5"),
    ])
    return PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": s1, "S4": s4},
        constraint_enforcer=ConstraintEnforcer(max_single_asset_pct=0.30),
    )


def _run(orch, **kwargs):
    return orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
        **kwargs,
    )


def test_allowlist_applies_only_to_listed_strategy():
    """apply_feedback_scale=["S4"] applies S4's scale and leaves S1 in shadow.

    Both sleeves are de-risked to 0.5, but only S4's is enforced:
      S1 unscaled 50 + S4 halved 15 = 65 shares (S1's 0.5 must NOT bite).
    """
    result = _run(
        _two_sleeve_orch(),
        feedback_scales={"S1": 0.5, "S4": 0.5},
        apply_feedback_scale=["S4"],
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert aapl[0].quantity == pytest.approx(65.0, rel=0.01)


def test_allowlist_records_applied_per_strategy_in_shadow():
    """The shadow's `applied` flag is per strategy — it is persisted to
    f8_regime_scale_shadow, so a global value would misrecord the trajectory."""
    result = _run(
        _two_sleeve_orch(),
        feedback_scales={"S1": 0.5, "S4": 0.5},
        apply_feedback_scale=["S4"],
    )
    assert result.feedback_shadow["S4"]["applied"] is True
    assert result.feedback_shadow["S1"]["applied"] is False
    # Shadow still records the would-be delta for the un-applied sleeve.
    assert result.feedback_shadow["S1"]["scaled_weight"] == pytest.approx(
        result.feedback_shadow["S1"]["unscaled_weight"] * 0.5, rel=0.01
    )


def test_empty_allowlist_applies_nothing():
    result = _run(
        _two_sleeve_orch(),
        feedback_scales={"S1": 0.5, "S4": 0.5},
        apply_feedback_scale=[],
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert aapl[0].quantity == pytest.approx(80.0, rel=0.01), "baseline, nothing scaled"
    assert result.feedback_shadow["S4"]["applied"] is False


def test_allowlist_naming_an_absent_strategy_changes_nothing():
    result = _run(
        _two_sleeve_orch(),
        feedback_scales={"S1": 0.5, "S4": 0.5},
        apply_feedback_scale=["S9"],
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert aapl[0].quantity == pytest.approx(80.0, rel=0.01)


def test_bool_contract_still_holds():
    """The historical bool contract must keep working: True = every sleeve."""
    result = _run(
        _two_sleeve_orch(),
        feedback_scales={"S1": 0.5, "S4": 0.5},
        apply_feedback_scale=True,
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    # S1 halved (25) + S4 halved (15) = 40
    assert aapl[0].quantity == pytest.approx(40.0, rel=0.01)


def test_none_is_treated_as_shadow_not_as_apply_all():
    """Fail-safe: an unreadable/absent flag must never enable de-risking."""
    result = _run(
        _two_sleeve_orch(),
        feedback_scales={"S1": 0.5, "S4": 0.5},
        apply_feedback_scale=None,
    )
    aapl = [o for o in result.final_orders if o.symbol == "AAPL"]
    assert aapl[0].quantity == pytest.approx(80.0, rel=0.01)


def test_feedback_shadow_empty_when_no_scale():
    """No non-identity scale → feedback_shadow is empty (nothing to measure)."""
    s4 = _FixedStrategy([_buy_order("AAPL", qty=300.0, strategy_id="S4")])
    entry = StrategyEntry("S4", _FixedStrategy, 0.10, "30 14 * * 1-5")
    registry = _make_registry([entry])
    orch = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S4": s4},
        constraint_enforcer=ConstraintEnforcer(),
    )
    result = orch.run_cycle(
        ts=datetime(2024, 1, 15),
        data_replay=_make_data_replay(),
        portfolio=_make_portfolio(cash=100_000.0),
        market=_make_market(),
        feedback_scales={"S4": 1.0},  # identity
    )
    assert result.feedback_shadow == {}