"""T-502: RiskParityAllocator tests."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.combiner import PortfolioCombiner
from src.portfolio.risk_parity import RiskParityAllocator


# ── Helpers ────────────────────────────────────────────────────────────────────


def _alt_series(vol: float, n: int = 200) -> pd.Series:
    """Alternating +/-vol series: realized std = vol * sqrt(n/(n-1)) ≈ vol."""
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    vals = np.where(np.arange(n) % 2 == 0, vol, -vol).astype(float)
    return pd.Series(vals, index=dates)


def _flat_series(n: int = 200) -> pd.Series:
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.Series(0.0, index=dates)


def _prices_df(symbols=("SPY", "AAPL"), n: int = 50) -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame({s: np.ones(n) * 100.0 for s in symbols}, index=dates)


def _market(prices_dict: dict) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2023, 3, 15),
        prices=prices_dict,
        volumes={k: 1_000_000.0 for k in prices_dict},
        adv_20d={k: 1_000_000.0 for k in prices_dict},
    )


def _order(symbol: str, strategy_id: str) -> Order:
    return Order.market_order(datetime(2023, 3, 15), symbol, OrderSide.BUY, 10.0, strategy_id)


class _FixedStrategy:
    def __init__(self, orders: list[Order]) -> None:
        self._orders = orders

    def __call__(self, ts, data_replay, portfolio, market) -> list[Order]:
        return self._orders


# ── Basic inverse-vol weights ──────────────────────────────────────────────────


def test_equal_vol_strategies_get_equal_weights():
    s = _alt_series(0.02)
    alloc = RiskParityAllocator({"S1": s.copy(), "S2": s.copy()})
    weights = alloc.compute_weights()
    assert weights["S1"] == pytest.approx(weights["S2"])


def test_higher_vol_strategy_gets_lower_weight():
    # vol(S1)=0.04, vol(S2)=0.02 → w(S1) < w(S2)
    alloc = RiskParityAllocator({"S1": _alt_series(0.04), "S2": _alt_series(0.02)})
    weights = alloc.compute_weights()
    assert weights["S1"] < weights["S2"]


def test_weights_sum_to_one():
    alloc = RiskParityAllocator({
        "S1": _alt_series(0.03),
        "S2": _alt_series(0.02),
        "S4": _alt_series(0.01),
    })
    weights = alloc.compute_weights()
    assert sum(weights.values()) == pytest.approx(1.0)


def test_three_strategies_weight_ordering_matches_inverse_vol():
    # S1 highest vol → lowest weight; S4 lowest vol → highest weight
    alloc = RiskParityAllocator({
        "S1": _alt_series(0.04),
        "S2": _alt_series(0.02),
        "S4": _alt_series(0.01),
    })
    weights = alloc.compute_weights()
    assert weights["S1"] < weights["S2"] < weights["S4"]


def test_rolling_window_used_not_full_series():
    n, window = 200, 60
    dates = pd.date_range("2022-01-01", periods=n, freq="B")
    # S1: high vol in old history, near-zero in recent 60 bars
    s1_vals = np.concatenate([np.tile([0.10, -0.10], (n - window) // 2), np.zeros(window)])
    # S2: uniform small vol throughout
    s2_vals = np.tile([0.01, -0.01], n // 2)
    returns = {
        "S1": pd.Series(s1_vals.astype(float), index=dates),
        "S2": pd.Series(s2_vals.astype(float), index=dates),
    }
    alloc = RiskParityAllocator(returns, window=window)
    weights = alloc.compute_weights()
    # S1's recent vol ≈ 0 → equal-weight fallback or S1 >> S2 weight
    # Either fallback (S1.vol < MIN_VOL) or S1 wins big. Either way, S1 ≥ S2.
    assert weights["S1"] >= weights["S2"]


# ── Constraint enforcement ─────────────────────────────────────────────────────


def test_min_weight_enforced_when_unconstrained_weight_too_small():
    # vol(S1)=0.50, vol(S2)=0.002 → raw w(S1) << 0.10
    alloc = RiskParityAllocator({"S1": _alt_series(0.50), "S2": _alt_series(0.002)})
    weights = alloc.compute_weights()
    assert weights["S1"] >= 0.10 - 1e-9


def test_max_weight_enforced_when_unconstrained_weight_too_large():
    # vol(S2) very low → raw w(S2) >> 0.60
    alloc = RiskParityAllocator({"S1": _alt_series(0.50), "S2": _alt_series(0.002)})
    weights = alloc.compute_weights()
    assert weights["S2"] <= 0.60 + 1e-9


def test_constrained_weights_still_sum_to_one():
    alloc = RiskParityAllocator({
        "S1": _alt_series(0.50),
        "S2": _alt_series(0.001),
        "S4": _alt_series(0.02),
    })
    weights = alloc.compute_weights()
    assert sum(weights.values()) == pytest.approx(1.0)


def test_all_weights_within_default_min_max():
    alloc = RiskParityAllocator({
        "S1": _alt_series(0.50),
        "S2": _alt_series(0.001),
        "S4": _alt_series(0.02),
    })
    weights = alloc.compute_weights()
    assert all(0.10 - 1e-9 <= w <= 0.60 + 1e-9 for w in weights.values())


def test_custom_min_max_weights_respected():
    alloc = RiskParityAllocator(
        {"S1": _alt_series(0.50), "S2": _alt_series(0.001)},
        min_weight=0.20,
        max_weight=0.80,
    )
    weights = alloc.compute_weights()
    assert all(0.20 - 1e-9 <= w <= 0.80 + 1e-9 for w in weights.values())
    assert sum(weights.values()) == pytest.approx(1.0)


def test_unconstrained_weights_not_clipped_when_within_bounds():
    # vol ratio 4:3 → raw weights 3/7 ≈ 0.429 and 4/7 ≈ 0.571, both in [0.10, 0.60]
    alloc = RiskParityAllocator(
        {"S1": _alt_series(0.04), "S2": _alt_series(0.03)},
        min_weight=0.10,
        max_weight=0.60,
    )
    weights = alloc.compute_weights()
    assert weights["S1"] == pytest.approx(3 / 7, rel=0.01)
    assert weights["S2"] == pytest.approx(4 / 7, rel=0.01)


# ── Zero / near-zero vol fallback ──────────────────────────────────────────────


def test_zero_vol_strategy_triggers_equal_weight_fallback():
    alloc = RiskParityAllocator({"S1": _flat_series(), "S2": _alt_series(0.02)})
    weights = alloc.compute_weights()
    assert weights["S1"] == pytest.approx(weights["S2"])


def test_near_zero_vol_triggers_equal_weight_fallback():
    alloc = RiskParityAllocator({"S1": _alt_series(1e-11), "S2": _alt_series(0.02)})
    weights = alloc.compute_weights()
    assert weights["S1"] == pytest.approx(weights["S2"])


def test_equal_weight_fallback_value_for_three_strategies():
    alloc = RiskParityAllocator({
        "S1": _flat_series(),
        "S2": _alt_series(0.02),
        "S4": _alt_series(0.03),
    })
    weights = alloc.compute_weights()
    assert all(w == pytest.approx(1 / 3) for w in weights.values())


# ── compare_vs_equal ───────────────────────────────────────────────────────────


def test_compare_vs_equal_returns_dataframe():
    alloc = RiskParityAllocator({"S1": _alt_series(0.02), "S2": _alt_series(0.03)})
    result = alloc.compare_vs_equal()
    assert isinstance(result, pd.DataFrame)


def test_compare_vs_equal_has_capital_allocation_column():
    alloc = RiskParityAllocator({"S1": _alt_series(0.02), "S2": _alt_series(0.03)})
    assert "capital_allocation" in alloc.compare_vs_equal().columns


def test_compare_vs_equal_has_risk_contribution_column():
    alloc = RiskParityAllocator({"S1": _alt_series(0.02), "S2": _alt_series(0.03)})
    assert "risk_contribution" in alloc.compare_vs_equal().columns


def test_compare_vs_equal_has_row_per_strategy():
    alloc = RiskParityAllocator({
        "S1": _alt_series(0.02),
        "S2": _alt_series(0.03),
        "S4": _alt_series(0.04),
    })
    result = alloc.compare_vs_equal()
    assert len(result) == 3
    assert set(result.index) == {"S1", "S2", "S4"}


def test_compare_vs_equal_capital_allocation_matches_compute_weights():
    alloc = RiskParityAllocator({"S1": _alt_series(0.02), "S2": _alt_series(0.03)})
    weights = alloc.compute_weights()
    result = alloc.compare_vs_equal()
    for sid, w in weights.items():
        assert result.loc[sid, "capital_allocation"] == pytest.approx(w)


def test_compare_vs_equal_risk_contribution_sums_to_one():
    alloc = RiskParityAllocator({
        "S1": _alt_series(0.02),
        "S2": _alt_series(0.03),
        "S4": _alt_series(0.04),
    })
    result = alloc.compare_vs_equal()
    assert result["risk_contribution"].sum() == pytest.approx(1.0)


def test_compare_vs_equal_equal_risk_contribution_for_unconstrained_case():
    # Inverse-vol weighting → equal risk contributions when no constraints bind.
    # vol ratio 2:3, raw weights 0.6:0.4, both within (0, 1) unconstrained.
    alloc = RiskParityAllocator(
        {"S1": _alt_series(0.02), "S2": _alt_series(0.03)},
        min_weight=0.0,
        max_weight=1.0,
    )
    result = alloc.compare_vs_equal()
    assert result.loc["S1", "risk_contribution"] == pytest.approx(
        result.loc["S2", "risk_contribution"], rel=0.01
    )


# ── PortfolioCombiner integration ─────────────────────────────────────────────


@pytest.fixture
def data_replay() -> DataReplay:
    return DataReplay(_prices_df())


@pytest.fixture
def portfolio() -> VirtualPortfolio:
    return VirtualPortfolio(initial_cash=100_000.0)


@pytest.fixture
def market() -> MarketSnapshot:
    return _market({"SPY": 400.0, "AAPL": 150.0})


@pytest.fixture
def ts() -> datetime:
    return datetime(2023, 3, 15)


def test_combiner_risk_parity_mode_defaults_to_false():
    combiner = PortfolioCombiner({"S1": (lambda *a: [], 0.5)})
    assert combiner._risk_parity_mode is False


def test_combiner_without_risk_parity_uses_fixed_weights(data_replay, portfolio, market, ts):
    s1 = _FixedStrategy([_order("AAPL", "S1")])
    s2 = _FixedStrategy([_order("SPY", "S2")])
    combiner = PortfolioCombiner({"S1": (s1, 0.5), "S2": (s2, 0.2)}, risk_parity_mode=False)
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    s1_order = next(o for o in orders if o.strategy_id == "S1")
    s2_order = next(o for o in orders if o.strategy_id == "S2")
    assert s1_order.allocation_weight == pytest.approx(0.5)
    assert s2_order.allocation_weight == pytest.approx(0.2)


def test_combiner_risk_parity_mode_uses_allocator_weights(data_replay, portfolio, market, ts):
    returns = {"S1": _alt_series(0.04), "S2": _alt_series(0.01)}
    allocator = RiskParityAllocator(returns)
    expected = allocator.compute_weights()

    s1 = _FixedStrategy([_order("AAPL", "S1")])
    s2 = _FixedStrategy([_order("SPY", "S2")])
    combiner = PortfolioCombiner(
        {"S1": (s1, 0.5), "S2": (s2, 0.2)},
        risk_parity_mode=True,
        risk_parity_allocator=allocator,
    )
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    s1_order = next(o for o in orders if o.strategy_id == "S1")
    s2_order = next(o for o in orders if o.strategy_id == "S2")
    assert s1_order.allocation_weight == pytest.approx(expected["S1"])
    assert s2_order.allocation_weight == pytest.approx(expected["S2"])


def test_combiner_risk_parity_weights_differ_from_fixed(data_replay, portfolio, market, ts):
    # S1 has higher vol → risk parity lowers its weight below fixed 0.5
    returns = {"S1": _alt_series(0.04), "S2": _alt_series(0.01)}
    allocator = RiskParityAllocator(returns)

    s1 = _FixedStrategy([_order("AAPL", "S1")])
    s2 = _FixedStrategy([_order("SPY", "S2")])
    combiner = PortfolioCombiner(
        {"S1": (s1, 0.5), "S2": (s2, 0.2)},
        risk_parity_mode=True,
        risk_parity_allocator=allocator,
    )
    orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
    s1_order = next(o for o in orders if o.strategy_id == "S1")
    # S1 has 4× higher vol, so risk parity gives it lower weight (≤ 0.5)
    assert s1_order.allocation_weight < 0.5
