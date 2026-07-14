"""T-504: PortfolioVolTargeter tests."""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pytest
from unittest.mock import patch, mock_open

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.portfolio.combiner import PortfolioCombiner
from src.portfolio.types import CombinedOrder
from src.portfolio.vol_targeting import PortfolioVolTargeter


# ── helpers ──────────────────────────────────────────────────────────────────

def _order(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    qty: float = 100.0,
    strategy_id: str = "S1",
) -> CombinedOrder:
    o = Order.market_order(datetime(2023, 3, 15), symbol, side, qty, strategy_id)
    return CombinedOrder.from_order(o, allocation_weight=1.0)


def _returns(daily_std: float, n: int = 100, seed: int = 42) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, daily_std, n).tolist()


def _prices(symbols=("AAPL", "SPY"), n: int = 50):
    import pandas as pd

    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    data = {s: np.ones(n) * 100.0 for s in symbols}
    return pd.DataFrame(data, index=dates)


def _market(prices_dict: dict) -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2023, 3, 15),
        prices=prices_dict,
        volumes={k: 1_000_000.0 for k in prices_dict},
        adv_20d={k: 1_000_000.0 for k in prices_dict},
    )


# daily std ~2% → annualized vol ~31% — above the 10% target
HIGH_VOL_RETURNS = _returns(daily_std=0.02, n=120)
# daily std ~0.1% → annualized vol ~1.6% — below the 10% target
LOW_VOL_RETURNS = _returns(daily_std=0.001, n=120)


# ── Vol Estimation ────────────────────────────────────────────────────────────

class TestVolEstimation:
    def test_high_vol_returns_estimated_above_target(self):
        targeter = PortfolioVolTargeter(target_vol=0.10)
        vol = targeter.estimate_vol({"S1": HIGH_VOL_RETURNS})
        assert vol > 0.10

    def test_low_vol_returns_estimated_below_target(self):
        targeter = PortfolioVolTargeter(target_vol=0.10)
        vol = targeter.estimate_vol({"S1": LOW_VOL_RETURNS})
        assert vol < 0.10

    def test_zero_returns_handled_gracefully_returns_finite(self):
        targeter = PortfolioVolTargeter()
        vol = targeter.estimate_vol({"S1": [0.0] * 80})
        assert math.isfinite(vol)
        assert vol >= 0.0

    def test_single_bar_handled_gracefully(self):
        targeter = PortfolioVolTargeter()
        vol = targeter.estimate_vol({"S1": [0.01]})
        assert math.isfinite(vol)
        assert vol >= 0.0

    def test_empty_returns_handled_gracefully(self):
        targeter = PortfolioVolTargeter()
        vol = targeter.estimate_vol({})
        assert math.isfinite(vol)
        assert vol >= 0.0

    def test_multiple_strategies_combined_returns_finite_positive(self):
        targeter = PortfolioVolTargeter(target_vol=0.10)
        vol = targeter.estimate_vol({"S1": HIGH_VOL_RETURNS, "S2": LOW_VOL_RETURNS})
        assert math.isfinite(vol)
        assert vol > 0.0

    def test_vol_is_annualized(self):
        # returns with daily std exactly 1% → annualized vol ~= sqrt(252) * 1% ≈ 15.9%
        rng = np.random.default_rng(0)
        rets = rng.normal(0.0, 0.01, 300).tolist()
        targeter = PortfolioVolTargeter()
        vol = targeter.estimate_vol({"S1": rets})
        # should be in the annualized range (well above 1% daily)
        assert vol > 0.05  # at least 5% annualized


# ── Scale Factor ──────────────────────────────────────────────────────────────

class TestScaleFactor:
    def test_scale_down_when_vol_above_target(self):
        targeter = PortfolioVolTargeter(target_vol=0.10)
        scale = targeter.compute_scale(0.20)
        assert scale < 1.0

    def test_scale_up_when_vol_below_target(self):
        targeter = PortfolioVolTargeter(target_vol=0.10)
        scale = targeter.compute_scale(0.05)
        assert scale > 1.0

    def test_scale_equals_one_when_vol_equals_target(self):
        targeter = PortfolioVolTargeter(target_vol=0.10)
        scale = targeter.compute_scale(0.10)
        assert abs(scale - 1.0) < 1e-9

    def test_clamp_lower_bound_at_0_5(self):
        # target=0.10, vol=0.50 → raw=0.20, clamped to 0.5
        targeter = PortfolioVolTargeter(target_vol=0.10)
        scale = targeter.compute_scale(0.50)
        assert scale == pytest.approx(0.5)

    def test_clamp_upper_bound_at_2_0(self):
        # target=0.10, vol=0.01 → raw=10, clamped to 2.0
        targeter = PortfolioVolTargeter(target_vol=0.10)
        scale = targeter.compute_scale(0.01)
        assert scale == pytest.approx(2.0)

    def test_zero_vol_returns_neutral_scale(self):
        # Unknown vol → 1.0 (no-op), not 2.0 (max leverage)
        targeter = PortfolioVolTargeter(target_vol=0.10)
        scale = targeter.compute_scale(0.0)
        assert scale == pytest.approx(1.0)

    def test_custom_target_vol_scales_correctly(self):
        targeter = PortfolioVolTargeter(target_vol=0.15)
        scale = targeter.compute_scale(0.15)
        assert abs(scale - 1.0) < 1e-9

    def test_scale_within_bounds_unclamped(self):
        # target=0.10, vol=0.08 → raw=1.25, within [0.5, 2.0]
        targeter = PortfolioVolTargeter(target_vol=0.10)
        scale = targeter.compute_scale(0.08)
        assert 0.5 <= scale <= 2.0
        assert scale == pytest.approx(1.25)


# ── Scale Orders ──────────────────────────────────────────────────────────────

class TestScaleOrders:
    def test_buy_order_quantity_scaled(self):
        targeter = PortfolioVolTargeter()
        orders = [_order(qty=100.0)]
        scaled = targeter.scale_orders(orders, 0.8)
        assert scaled[0].quantity == pytest.approx(80.0)

    def test_sell_order_unchanged(self):
        targeter = PortfolioVolTargeter()
        sell = _order(symbol="MSFT", side=OrderSide.SELL, qty=50.0)
        scaled = targeter.scale_orders([sell], 0.5)
        assert scaled[0].quantity == pytest.approx(50.0)

    def test_buy_scaled_sell_unchanged_mixed(self):
        targeter = PortfolioVolTargeter()
        buy = _order(symbol="AAPL", side=OrderSide.BUY, qty=100.0)
        sell = _order(symbol="MSFT", side=OrderSide.SELL, qty=50.0)
        scaled = targeter.scale_orders([buy, sell], 0.5)
        buy_result = next(o for o in scaled if o.symbol == "AAPL")
        sell_result = next(o for o in scaled if o.symbol == "MSFT")
        assert buy_result.quantity == pytest.approx(50.0)
        assert sell_result.quantity == pytest.approx(50.0)

    def test_empty_order_list_returns_empty(self):
        targeter = PortfolioVolTargeter()
        assert targeter.scale_orders([], 1.5) == []

    def test_scale_of_one_does_not_change_quantities(self):
        targeter = PortfolioVolTargeter()
        orders = [_order(qty=100.0), _order(qty=200.0)]
        scaled = targeter.scale_orders(orders, 1.0)
        assert scaled[0].quantity == pytest.approx(100.0)
        assert scaled[1].quantity == pytest.approx(200.0)

    def test_returns_combined_orders_not_plain_orders(self):
        targeter = PortfolioVolTargeter()
        orders = [_order(qty=100.0)]
        scaled = targeter.scale_orders(orders, 0.8)
        assert isinstance(scaled[0], CombinedOrder)


# ── Default Config ────────────────────────────────────────────────────────────

class TestDefaultConfig:
    def test_default_target_vol_is_10_percent(self):
        targeter = PortfolioVolTargeter()
        assert targeter.target_vol == pytest.approx(0.10)

    def test_default_span_is_60(self):
        targeter = PortfolioVolTargeter()
        assert targeter.span == 60

    def test_default_clamp_is_0_5_to_2_0(self):
        """F6: default clamp must be the status-quo [0.5, 2.0] so making the
        clamp config-driven is zero behavior change."""
        targeter = PortfolioVolTargeter()
        assert targeter.clamp_low == pytest.approx(0.5)
        assert targeter.clamp_high == pytest.approx(2.0)


# ── Custom Clamp (F6: clamp is now config-driven) ───────────────────────────

class TestCustomClamp:
    def test_custom_clamp_low_binds_instead_of_default(self):
        """A lower clamp_low of 0.3 must let the scale fall to 0.3 where the
        default 0.5 floor would have stopped it at 0.5 (target=0.10, vol=0.50
        -> raw 0.20 -> clamped to clamp_low=0.3)."""
        targeter = PortfolioVolTargeter(target_vol=0.10, clamp_low=0.3, clamp_high=2.0)
        scale = targeter.compute_scale(0.50)
        assert scale == pytest.approx(0.3), (
            f"custom clamp_low=0.3 must bind at 0.3, got {scale} (default floor 0.5 would be wrong)"
        )

    def test_custom_clamp_high_binds_instead_of_default(self):
        """A lower clamp_high of 1.5 must cap the scale at 1.5 where the default
        2.0 cap would have allowed 2.0 (target=0.10, vol=0.01 -> raw 10)."""
        targeter = PortfolioVolTargeter(target_vol=0.10, clamp_low=0.5, clamp_high=1.5)
        scale = targeter.compute_scale(0.01)
        assert scale == pytest.approx(1.5), (
            f"custom clamp_high=1.5 must bind at 1.5, got {scale} (default cap 2.0 would be wrong)"
        )

    def test_default_clamp_preserves_status_quo_floor(self):
        """Regression guard: default construction still floors at 0.5."""
        targeter = PortfolioVolTargeter(target_vol=0.10)
        assert targeter.compute_scale(0.50) == pytest.approx(0.5)

    def test_default_clamp_preserves_status_quo_cap(self):
        """Regression guard: default construction still caps at 2.0."""
        targeter = PortfolioVolTargeter(target_vol=0.10)
        assert targeter.compute_scale(0.01) == pytest.approx(2.0)

    def test_clamp_attributes_stored(self):
        targeter = PortfolioVolTargeter(clamp_low=0.3, clamp_high=1.5)
        assert targeter.clamp_low == pytest.approx(0.3)
        assert targeter.clamp_high == pytest.approx(1.5)


# ── Config loader (F6: target_vol / clamp driven by trading.yaml) ───────────

class TestLoadVolTargetConfig:
    def test_defaults_on_missing_section(self):
        """When trading.yaml is absent, return status-quo defaults (zero
        behavior change)."""
        from src.portfolio.vol_targeting import load_vol_target_config
        with patch("builtins.open", side_effect=FileNotFoundError):
            cfg = load_vol_target_config()
        assert cfg["target_vol"] == pytest.approx(0.10)
        assert cfg["clamp_low"] == pytest.approx(0.5)
        assert cfg["clamp_high"] == pytest.approx(2.0)

    def test_trading_yaml_ships_status_quo(self):
        """The shipped config must keep vol_target at the calibrated status quo
        until an operator re-calibrates after a replay shadow — guards against an
        accidental live flip (measure-before-enforce, QX-01).

        target_vol was 0.10 until 2026-07-13, when the F6 (b) read-only replay
        (scripts/audit_vol_target_replay.py, 60-day window) justified flipping
        the shipped value to 0.12 (commit 237e660). This test pins the current
        shipped value so a future accidental edit is caught.
        """
        from src.portfolio.vol_targeting import load_vol_target_config
        cfg = load_vol_target_config()  # reads the real config/trading.yaml
        assert cfg["target_vol"] == pytest.approx(0.12), (
            "config/trading.yaml must ship target_vol: 0.12 (status quo since the "
            "2026-07-13 F6 replay flip) — re-calibration only after a read-only replay shadow"
        )
        assert cfg["clamp_low"] == pytest.approx(0.5)
        assert cfg["clamp_high"] == pytest.approx(2.0)

    def test_reads_custom_values_from_yaml(self):
        """When vol_target.target_vol is set in the yaml, the loader returns it
        (and a custom clamp), so the scheduler constructs the targeter from
        config, not from a hardcoded literal."""
        from src.portfolio.vol_targeting import load_vol_target_config
        custom_yaml = (
            "vol_target:\n"
            "  target_vol: 0.15\n"
            "  clamp_low: 0.4\n"
            "  clamp_high: 1.8\n"
        )
        with patch("builtins.open", mock_open(read_data=custom_yaml)):
            cfg = load_vol_target_config()
        assert cfg["target_vol"] == pytest.approx(0.15)
        assert cfg["clamp_low"] == pytest.approx(0.4)
        assert cfg["clamp_high"] == pytest.approx(1.8)

    def test_targeter_constructed_from_loader_dict(self):
        """PortfolioVolTargeter(**load_vol_target_config()) must work — the
        loader returns exactly the kwargs the constructor accepts."""
        from src.portfolio.vol_targeting import load_vol_target_config
        cfg = load_vol_target_config()
        targeter = PortfolioVolTargeter(**cfg)
        assert targeter.target_vol == pytest.approx(cfg["target_vol"])
        assert targeter.clamp_low == pytest.approx(cfg["clamp_low"])
        assert targeter.clamp_high == pytest.approx(cfg["clamp_high"])


# ── Scheduler wiring (F6: scheduler builds targeter from config) ────────────

class TestSchedulerWiring:
    def test_build_vol_targeter_reads_config_not_hardcoded(self):
        """_build_vol_targeter must construct the targeter from
        load_vol_target_config, so flipping trading.yaml changes the live
        targeter without a code change (F6)."""
        from src.workers.portfolio_scheduler import _build_vol_targeter
        with patch(
            "src.portfolio.vol_targeting.load_vol_target_config",
            return_value={"target_vol": 0.15, "clamp_low": 0.5, "clamp_high": 2.0},
        ):
            targeter, cfg = _build_vol_targeter()
        assert targeter.target_vol == pytest.approx(0.15), (
            "_build_vol_targeter must use the config value (0.15), not a hardcoded 0.10"
        )
        assert cfg["target_vol"] == pytest.approx(0.15)

    def test_no_hardcoded_target_vol_literal_in_scheduler(self):
        """Guard against a revert: the scheduler must not construct the vol
        targeter with a hardcoded target_vol=0.10 literal — it must go through
        _build_vol_targeter / load_vol_target_config."""
        import inspect
        import src.workers.portfolio_scheduler as ps
        src_text = inspect.getsource(ps)
        assert "PortfolioVolTargeter(target_vol=0.10)" not in src_text, (
            "scheduler must not hardcode PortfolioVolTargeter(target_vol=0.10) — "
            "F6: target_vol is config-driven via _build_vol_targeter()"
        )
        assert "_build_vol_targeter" in src_text, (
            "scheduler must wire the vol targeter through _build_vol_targeter() (F6)"
        )


# ── Integration with PortfolioCombiner ───────────────────────────────────────

class _FixedStrategy:
    def __init__(self, orders: list[Order]):
        self._orders = orders

    def __call__(self, ts, data_replay, portfolio, market) -> list[Order]:
        return self._orders


class TestPortfolioCombinerIntegration:
    @pytest.fixture
    def data_replay(self):
        return DataReplay(_prices())

    @pytest.fixture
    def portfolio(self):
        return VirtualPortfolio(initial_cash=100_000.0)

    @pytest.fixture
    def market(self):
        return _market({"AAPL": 150.0, "SPY": 400.0})

    @pytest.fixture
    def ts(self):
        return datetime(2023, 3, 15)

    def test_vol_targeting_mode_scales_buy_orders_when_vol_high(
        self, data_replay, portfolio, market, ts
    ):
        # HIGH_VOL_RETURNS → vol > target → scale < 1 → qty reduced
        raw_qty = 100.0
        s1 = _FixedStrategy([Order.market_order(ts, "AAPL", OrderSide.BUY, raw_qty, "S1")])
        targeter = PortfolioVolTargeter(target_vol=0.10)
        combiner = PortfolioCombiner(
            {"S1": (s1, 1.0)},
            vol_targeting_mode=True,
            vol_targeter=targeter,
            strategy_returns={"S1": HIGH_VOL_RETURNS},
        )
        orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
        assert len(orders) == 1
        assert orders[0].quantity < raw_qty

    def test_vol_targeting_mode_scales_buy_orders_when_vol_low(
        self, data_replay, portfolio, market, ts
    ):
        # LOW_VOL_RETURNS → vol < target → scale > 1 → qty increased (up to clamp=2.0)
        raw_qty = 100.0
        s1 = _FixedStrategy([Order.market_order(ts, "AAPL", OrderSide.BUY, raw_qty, "S1")])
        targeter = PortfolioVolTargeter(target_vol=0.10)
        combiner = PortfolioCombiner(
            {"S1": (s1, 1.0)},
            vol_targeting_mode=True,
            vol_targeter=targeter,
            strategy_returns={"S1": LOW_VOL_RETURNS},
        )
        orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
        assert len(orders) == 1
        assert orders[0].quantity > raw_qty

    def test_vol_targeting_disabled_leaves_quantities_unchanged(
        self, data_replay, portfolio, market, ts
    ):
        raw_qty = 100.0
        s1 = _FixedStrategy([Order.market_order(ts, "AAPL", OrderSide.BUY, raw_qty, "S1")])
        combiner = PortfolioCombiner({"S1": (s1, 1.0)}, vol_targeting_mode=False)
        orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
        assert orders[0].quantity == pytest.approx(raw_qty)

    def test_vol_targeting_without_targeter_does_not_crash(
        self, data_replay, portfolio, market, ts
    ):
        s1 = _FixedStrategy([Order.market_order(ts, "AAPL", OrderSide.BUY, 50.0, "S1")])
        combiner = PortfolioCombiner(
            {"S1": (s1, 1.0)},
            vol_targeting_mode=True,
            vol_targeter=None,
        )
        orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
        assert len(orders) == 1

    def test_vol_targeting_does_not_scale_sell_orders(
        self, data_replay, portfolio, market, ts
    ):
        raw_qty = 50.0
        s1 = _FixedStrategy([Order.market_order(ts, "AAPL", OrderSide.SELL, raw_qty, "S1")])
        targeter = PortfolioVolTargeter(target_vol=0.10)
        combiner = PortfolioCombiner(
            {"S1": (s1, 1.0)},
            vol_targeting_mode=True,
            vol_targeter=targeter,
            strategy_returns={"S1": HIGH_VOL_RETURNS},
        )
        orders, _ = combiner.aggregate(ts, data_replay, portfolio, market)
        assert orders[0].quantity == pytest.approx(raw_qty)
