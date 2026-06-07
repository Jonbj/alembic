"""Tests for tier-based stop-loss in execution worker."""
import pytest
from src.costs.calculator import TradeCostCalculator


class TestTierBasedStopLoss:
    def test_tier_a_uses_2pct_stop(self):
        """SPY (tier_a) stop-loss should be 2%."""
        calc = TradeCostCalculator()
        assert calc.stop_loss_pct("SPY") == pytest.approx(0.020)

    def test_tier_b_uses_3_5pct_stop(self):
        """INTC (tier_b) stop-loss should be 3.5%."""
        calc = TradeCostCalculator()
        assert calc.stop_loss_pct("INTC") == pytest.approx(0.035)

    def test_tier_d_uses_5pct_stop(self):
        """Unknown symbol (tier_d default) stop-loss should be 5%."""
        calc = TradeCostCalculator()
        assert calc.stop_loss_pct("UNKNOWN_TICKER") == pytest.approx(0.050)

    def test_run_execution_cycle_accepts_cost_calc(self):
        """run_execution_cycle must accept a cost_calc parameter."""
        import inspect
        from src.workers.execution import run_execution_cycle
        sig = inspect.signature(run_execution_cycle)
        assert "cost_calc" in sig.parameters
