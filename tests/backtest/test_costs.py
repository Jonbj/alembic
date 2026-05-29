"""Tests for T-003: realistic cost model."""
import math
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.backtest.costs.impact_model import SquareRootImpactModel
from src.backtest.costs.realistic import RealisticCostModel
from src.backtest.costs.spread_tiers import SpreadTier, SpreadTierLookup
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide


@pytest.fixture
def cost_config(tmp_path: Path) -> Path:
    """Minimal cost_model.yaml for testing (no network, no file-system assumptions)."""
    config = {
        "equity": {
            "spread_tiers": {
                "tier_a": {
                    "description": "Very liquid ETF",
                    "symbols": ["SPY", "QQQ"],
                    "spread_bps": 1.5,
                },
                "tier_b": {
                    "description": "Large-cap",
                    "symbols": ["AAPL", "MSFT"],
                    "spread_bps": 3.5,
                },
                "tier_d": {
                    "description": "Default: illiquid",
                    "default": True,
                    "spread_bps": 20.0,
                },
            },
            "impact_k": 10.0,
            "commission_per_share": 0.0,
            "sec_fee_per_share_sale": 0.0000229,
            "finra_taf_per_share_sale": 0.000145,
        },
        "options": {
            "spread_pct_of_mid": 0.05,
            "commission_per_contract": 0.65,
            "exercise_fee": 0.0,
        },
    }
    path = tmp_path / "cost_model.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return path


@pytest.fixture
def spy_market() -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2024, 1, 1),
        prices={"SPY": 480.0},
        volumes={"SPY": 80_000_000.0},
        adv_20d={"SPY": 80_000_000.0},
    )


class TestSpreadTierLookup:
    def test_tier_a_spread(self, cost_config: Path) -> None:
        lookup = SpreadTierLookup.from_config(cost_config)
        assert lookup.get_spread_bps("SPY") == 1.5

    def test_tier_b_spread(self, cost_config: Path) -> None:
        lookup = SpreadTierLookup.from_config(cost_config)
        assert lookup.get_spread_bps("AAPL") == 3.5

    def test_unknown_symbol_gets_default(self, cost_config: Path) -> None:
        lookup = SpreadTierLookup.from_config(cost_config)
        assert lookup.get_spread_bps("UNKNOWN_TICKER") == 20.0

    def test_programmatic_construction(self) -> None:
        tiers = [
            SpreadTier("tier_a", 2.0),
            SpreadTier("tier_d", 25.0, is_default=True),
        ]
        lookup = SpreadTierLookup(tiers=tiers, symbol_to_tier={"AAPL": "tier_a"})
        assert lookup.get_spread_bps("AAPL") == 2.0
        assert lookup.get_spread_bps("SMALL_CAP") == 25.0


class TestSquareRootImpactModel:
    def test_zero_adv_returns_zero(self) -> None:
        model = SquareRootImpactModel(k=10.0)
        assert model.impact_bps(100_000.0, 0.0) == 0.0

    def test_impact_grows_with_order_size(self) -> None:
        model = SquareRootImpactModel(k=10.0)
        adv = 38_400_000_000.0
        small = model.impact_bps(50_000.0, adv)
        large = model.impact_bps(5_000_000.0, adv)
        assert large > small

    def test_impact_formula_correctness(self) -> None:
        model = SquareRootImpactModel(k=10.0)
        order_usd = 96_000.0
        adv_usd = 38_400_000_000.0
        expected = 10.0 * math.sqrt(order_usd / adv_usd) * 100
        assert abs(model.impact_bps(order_usd, adv_usd) - expected) < 1e-10

    def test_impact_scales_with_sqrt(self) -> None:
        model = SquareRootImpactModel(k=10.0)
        adv = 1_000_000_000.0
        impact_1x = model.impact_bps(1_000_000.0, adv)
        impact_4x = model.impact_bps(4_000_000.0, adv)
        # sqrt(4x) = 2x
        assert abs(impact_4x / impact_1x - 2.0) < 0.001


class TestRealisticCostModel:
    def test_buy_fill_price_above_mid(
        self, cost_config: Path, spy_market: MarketSnapshot
    ) -> None:
        model = RealisticCostModel(config_path=cost_config)
        order = Order.market_order(datetime(2024, 1, 1), "SPY", OrderSide.BUY, 200.0)
        fill = model.simulate_fill(order, spy_market)
        assert fill.fill_price > 480.0

    def test_sell_fill_price_below_mid(
        self, cost_config: Path, spy_market: MarketSnapshot
    ) -> None:
        model = RealisticCostModel(config_path=cost_config)
        order = Order.market_order(datetime(2024, 1, 1), "SPY", OrderSide.SELL, 200.0)
        fill = model.simulate_fill(order, spy_market)
        assert fill.fill_price < 480.0

    def test_spy_200_shares_slippage_under_5bps(
        self, cost_config: Path, spy_market: MarketSnapshot
    ) -> None:
        """Spec sanity check: liquid ETF, small order → total cost < 5 bps."""
        model = RealisticCostModel(config_path=cost_config)
        order = Order.market_order(datetime(2024, 1, 1), "SPY", OrderSide.BUY, 200.0)
        fill = model.simulate_fill(order, spy_market)
        slippage = (fill.fill_price - 480.0) / 480.0 * 10_000
        assert 0.5 < slippage < 5.0, f"Slippage {slippage:.2f} bps outside [0.5, 5.0]"

    def test_sell_has_regulatory_fees_buy_does_not(
        self, cost_config: Path, spy_market: MarketSnapshot
    ) -> None:
        model = RealisticCostModel(config_path=cost_config)
        buy = Order.market_order(datetime(2024, 1, 1), "SPY", OrderSide.BUY, 200.0)
        sell = Order.market_order(datetime(2024, 1, 1), "SPY", OrderSide.SELL, 200.0)
        buy_fill = model.simulate_fill(buy, spy_market)
        sell_fill = model.simulate_fill(sell, spy_market)
        # Sells pay SEC + FINRA TAF on top
        assert sell_fill.commission > buy_fill.commission

    def test_missing_price_raises(self, cost_config: Path) -> None:
        model = RealisticCostModel(config_path=cost_config)
        empty_market = MarketSnapshot(
            timestamp=datetime(2024, 1, 1),
            prices={},
            volumes={},
            adv_20d={},
        )
        order = Order.market_order(datetime(2024, 1, 1), "SPY", OrderSide.BUY, 100.0)
        with pytest.raises(ValueError, match="No price for SPY"):
            model.simulate_fill(order, empty_market)

    def test_fill_preserves_order_metadata(
        self, cost_config: Path, spy_market: MarketSnapshot
    ) -> None:
        model = RealisticCostModel(config_path=cost_config)
        order = Order.market_order(
            datetime(2024, 1, 1), "SPY", OrderSide.BUY, 200.0, "momentum_strat"
        )
        fill = model.simulate_fill(order, spy_market)
        assert fill.order_id == order.order_id
        assert fill.symbol == "SPY"
        assert fill.strategy_id == "momentum_strat"
        assert fill.quantity == 200.0
        assert fill.slippage_bps > 0

    def test_illiquid_stock_has_higher_slippage(self, cost_config: Path) -> None:
        """Unknown small-cap with low ADV gets default spread + high impact."""
        model = RealisticCostModel(config_path=cost_config)
        illiquid_market = MarketSnapshot(
            timestamp=datetime(2024, 1, 1),
            prices={"TINY": 10.0},
            volumes={"TINY": 50_000.0},
            adv_20d={"TINY": 50_000.0},  # tiny ADV → high impact
        )
        order = Order.market_order(datetime(2024, 1, 1), "TINY", OrderSide.BUY, 500.0)
        fill = model.simulate_fill(order, illiquid_market)
        slippage = (fill.fill_price - 10.0) / 10.0 * 10_000
        # tier_d half-spread (10 bps) + sqrt-impact >> 5 bps
        assert slippage > 15.0

    def test_slippage_bps_recorded_in_fill(
        self, cost_config: Path, spy_market: MarketSnapshot
    ) -> None:
        model = RealisticCostModel(config_path=cost_config)
        order = Order.market_order(datetime(2024, 1, 1), "SPY", OrderSide.BUY, 200.0)
        fill = model.simulate_fill(order, spy_market)
        # slippage_bps = half_spread + impact; verify it's consistent with fill_price
        implied_slippage = (fill.fill_price - 480.0) / 480.0 * 10_000
        assert abs(implied_slippage - fill.slippage_bps) < 0.01
