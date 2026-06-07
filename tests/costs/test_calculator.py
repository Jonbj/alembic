"""Unit tests for TradeCostCalculator."""
import pytest
from pathlib import Path
from src.costs.calculator import TradeCostCalculator, CostBreakdown

CONFIG = Path("config/cost_model.yaml")


@pytest.fixture
def calc():
    return TradeCostCalculator(config_path=CONFIG)


class TestStopLossPct:
    def test_tier_a_symbol(self, calc):
        assert calc.stop_loss_pct("SPY") == pytest.approx(0.020)

    def test_tier_a_megacap(self, calc):
        assert calc.stop_loss_pct("NVDA") == pytest.approx(0.020)

    def test_tier_b_symbol(self, calc):
        assert calc.stop_loss_pct("INTC") == pytest.approx(0.035)

    def test_tier_d_default(self, calc):
        # Symbol not in any explicit tier → default (tier_d)
        assert calc.stop_loss_pct("UNKNOWN_TICKER") == pytest.approx(0.050)


class TestComputeCosts:
    def test_buy_tier_a_no_regulatory_fees(self, calc):
        result = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        assert isinstance(result, CostBreakdown)
        assert result.regulatory_cost_usd == pytest.approx(0.0)
        # spread_cost_bps = 1.5 bps (tier_a full roundtrip)
        assert result.spread_cost_bps == pytest.approx(1.5)
        assert result.total_cost_bps > 0

    def test_sell_has_regulatory_fees(self, calc):
        result = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="SELL")
        # SEC fee: 0.0000229 * 50 * 200 = 0.229
        # FINRA TAF: 0.000145 * 50 = 0.00725
        expected_reg = 0.0000229 * 50 * 200 + 0.000145 * 50
        assert result.regulatory_cost_usd == pytest.approx(expected_reg, rel=1e-4)

    def test_tier_d_higher_cost_than_tier_a(self, calc):
        tier_a = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        tier_d = calc.compute("UNKNOWN", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        assert tier_d.spread_cost_bps > tier_a.spread_cost_bps

    def test_total_cost_usd_formula(self, calc):
        result = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        expected_usd = (result.total_cost_bps / 10_000) * 10_000 + result.regulatory_cost_usd
        assert result.total_cost_usd == pytest.approx(expected_usd, rel=1e-6)

    def test_unit_notional_for_ic(self, calc):
        # notional=1.0 for IC adjustment: impact is negligible, result ≈ spread_bps
        result = calc.compute("INTC", notional=1.0, qty=1.0, fill_price=1.0, side="SELL")
        # spread for tier_b = 5.0 bps; impact negligible at this scale
        assert result.spread_cost_bps == pytest.approx(5.0)
        assert result.impact_cost_bps < 0.01  # near zero
