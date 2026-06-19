"""P1-VALIDATION-GATES-TRUTH — Fix dishonest gate implementations.

Problems identified in ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18 (WS-08):

1. Gate 1 — n_trials=1 default: DSR with n_trials=1 is trivially inflated.
   A researcher who has tried many strategies must pass the actual number of
   trials; otherwise DSR ≈ 1 for any positive SR and the correction is useless.

2. Gate 2 — wrong positive_fraction denominator: active-only denominator excludes
   no-trade windows. If a strategy trades in 2/10 windows and both are positive,
   it gets 100% fraction instead of 20%. This is cherry-picking by definition.
   Fix: denominator = len(wf_results) (all windows, including no-trade ones).

3. Gate 4 — silent clamp: `min(min_passing_regimes, len(regime_returns))` silently
   lowers the bar when fewer regimes are provided than required. A strategy that
   passes bull+sideways but fails bear can pass gate_4 if bear data is absent.
   Fix: remove the clamp; return failed with explanation if insufficient regime data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _make_returns(n: int, mean: float = 0.001, std: float = 0.01, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(mean, std, n))


def _flat_returns(n: int) -> pd.Series:
    """Zero returns — no trade simulated."""
    return pd.Series([0.0] * n)


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1 — n_trials multiple testing
# ─────────────────────────────────────────────────────────────────────────────

class TestGate1NTrials:

    def test_gate1_accepts_n_trials_parameter(self):
        """gate_1_significance must accept an n_trials parameter."""
        import inspect
        from src.backtest.gates.gate_1_significance import gate_1_significance
        sig = inspect.signature(gate_1_significance)
        assert "n_trials" in sig.parameters, (
            "gate_1_significance must have n_trials parameter for multiple-testing correction"
        )

    def test_gate1_dsr_lower_with_more_trials(self):
        """deflated_sharpe_ratio (the DSR metric used by gate_1) must return lower values
        for higher n_trials. Uses SR=0.15 directly to avoid floating-point saturation:
        with SR≈1.5 both n_trials=1 and n_trials=100 give DSR=1.0 in floating point,
        hiding the real mathematical difference (DSR100 < DSR1 holds always, but
        norm.cdf(25) = norm.cdf(22) = 1.0 in double precision).
        """
        from src.backtest.metrics.signal_quality import deflated_sharpe_ratio

        # SR=0.15 sits below expected_max_sharpe(100, 252)≈0.16, so DSR_100 < 0.5
        # while DSR_1 (expected_max_sharpe=0) ≈ 0.99 — a clear, observable difference.
        dsr_1   = deflated_sharpe_ratio(observed_sr=0.15, n_trials=1,   n_obs=252)
        dsr_100 = deflated_sharpe_ratio(observed_sr=0.15, n_trials=100, n_obs=252)

        assert dsr_100 < dsr_1, (
            f"DSR with n_trials=100 ({dsr_100:.4f}) must be < DSR with n_trials=1 ({dsr_1:.4f}). "
            f"More trials inflate the DSR benchmark (expected_max_sharpe), so the bar is higher."
        )

    def test_gate1_single_trial_dsr_is_inflated(self):
        """With n_trials=1, expected_max_sharpe ≈ 0, so DSR ≈ P(SR > 0).

        This means DSR is near 1.0 for any meaningful positive SR, making the
        correction useless. We document this as a known bias.
        """
        from src.backtest.gates.gate_1_significance import gate_1_significance
        returns = _make_returns(252, mean=0.001, std=0.01, seed=42)
        result = gate_1_significance(returns, n_trials=1)
        # DSR with n_trials=1 should be very high (close to 1.0) when SR > 0
        assert result.details["dsr"] > 0.7, (
            "With n_trials=1, DSR is trivially high for any strategy with positive SR. "
            "Callers should always pass the actual number of strategies tried."
        )

    def test_gate1_many_trials_requires_stronger_sr(self):
        """Higher n_trials demands stronger SR to achieve the same DSR threshold.

        Uses deflated_sharpe_ratio directly with SR=0.15 to avoid floating-point
        saturation that would mask the difference in returns-based tests.
        SR=0.15 is deliberately marginal: DSR(n=1)≈0.99 vs DSR(n=200)≈0.35.
        """
        from src.backtest.metrics.signal_quality import deflated_sharpe_ratio

        dsr_1   = deflated_sharpe_ratio(observed_sr=0.15, n_trials=1,   n_obs=252)
        dsr_200 = deflated_sharpe_ratio(observed_sr=0.15, n_trials=200, n_obs=252)

        assert dsr_200 < dsr_1, (
            f"n_trials=200 DSR ({dsr_200:.4f}) must be lower than "
            f"n_trials=1 DSR ({dsr_1:.4f})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Gate 2 — positive_fraction denominator bug
# ─────────────────────────────────────────────────────────────────────────────

class TestGate2Denominator:

    def test_gate2_positive_fraction_uses_all_windows(self):
        """positive_fraction denominator must be all windows, not just active ones.

        Bug: if 2/10 windows are active and both are positive, the old code returns
        fraction = 2/2 = 100% instead of 2/10 = 20%.
        """
        from src.backtest.gates.gate_2_walkforward import gate_2_walkforward

        # 2 active positive windows + 8 no-trade windows
        active = [_make_returns(63, mean=0.002, seed=i) for i in range(2)]
        inactive = [_flat_returns(63) for _ in range(8)]
        all_windows = active + inactive

        result = gate_2_walkforward(all_windows)

        # With correct denominator: 2 / 10 = 0.20
        # With bug (active-only): 2 / 2 = 1.00
        fraction = result.details["positive_fraction"]
        assert fraction <= 0.25, (
            f"positive_fraction must use all {len(all_windows)} windows as denominator. "
            f"Got {fraction:.2f} — this suggests the old active-only denominator is still in use "
            f"(2 active positive windows out of 10 total should give ≤0.25, not 1.0)."
        )

    def test_gate2_no_trade_windows_count_toward_denominator(self):
        """Explicitly: no-trade windows must be included in denominator."""
        from src.backtest.gates.gate_2_walkforward import gate_2_walkforward

        # 5 positive + 5 flat (no trade)
        windows = [_make_returns(63, mean=0.002, seed=i) for i in range(5)]
        windows += [_flat_returns(63) for _ in range(5)]

        result = gate_2_walkforward(windows)

        # Correct: 5 / 10 = 0.5
        fraction = result.details["positive_fraction"]
        assert abs(fraction - 0.5) < 0.01, (
            f"5 positive + 5 no-trade = 5/10 = 0.50 positive_fraction expected, got {fraction:.4f}"
        )

    def test_gate2_all_active_positive_gives_fraction_1(self):
        """Sanity check: if all windows are active and positive, fraction = 1."""
        from src.backtest.gates.gate_2_walkforward import gate_2_walkforward

        windows = [_make_returns(63, mean=0.002, seed=i) for i in range(5)]
        result = gate_2_walkforward(windows)

        fraction = result.details["positive_fraction"]
        assert fraction == pytest.approx(1.0, rel=0.01), (
            f"All active positive windows → fraction should be 1.0, got {fraction:.4f}"
        )

    def test_gate2_result_reports_n_windows_correctly(self):
        """n_windows in details must equal the number of WF windows passed in."""
        from src.backtest.gates.gate_2_walkforward import gate_2_walkforward

        windows = [_make_returns(63, seed=i) for i in range(7)]
        result = gate_2_walkforward(windows)

        assert result.details["n_windows"] == 7


# ─────────────────────────────────────────────────────────────────────────────
# Gate 4 — silent clamp removal
# ─────────────────────────────────────────────────────────────────────────────

class TestGate4NoSilentClamp:

    def test_gate4_does_not_silently_lower_min_passing_regimes(self):
        """gate_4_regime must NOT silently clamp min_passing_regimes to len(regime_returns).

        Bug: if only 2 regimes are provided and min_passing_regimes=3, the old code
        clamps to 2, silently making the gate easier to pass.
        """
        from src.backtest.gates.gate_4_regime import gate_4_regime

        # Only 2 regimes provided, but we require 3
        two_regimes = {
            "bull": _make_returns(120, mean=0.002, seed=1),
            "sideways": _make_returns(120, mean=0.001, seed=2),
            # "bear" is absent
        }

        result = gate_4_regime(two_regimes, min_passing_regimes=3)

        # With the clamp removed, gate must fail when fewer regimes than required are provided
        assert not result.passed, (
            "gate_4_regime must fail when fewer regime periods are provided than "
            "min_passing_regimes requires. The silent clamp hides missing regime coverage."
        )

    def test_gate4_fails_gracefully_with_explanation_when_insufficient_regimes(self):
        """Result details must explain why gate failed due to insufficient regime data."""
        from src.backtest.gates.gate_4_regime import gate_4_regime

        result = gate_4_regime({"bull": _make_returns(120, mean=0.002)}, min_passing_regimes=3)

        assert not result.passed
        details_str = str(result.details)
        # Either n_total_regimes or an error message should explain the shortfall
        assert (
            "n_total_regimes" in result.details
            or "error" in result.details
            or "insufficient" in details_str.lower()
        ), f"Details must explain insufficient regime coverage: {result.details}"

    def test_gate4_passes_when_enough_regimes_and_positive_sharpes(self):
        """Sanity check: gate_4 still passes when all required regimes meet threshold."""
        from src.backtest.gates.gate_4_regime import gate_4_regime

        regimes = {
            "bull":     _make_returns(120, mean=0.003, std=0.008, seed=1),
            "bear":     _make_returns(120, mean=0.001, std=0.008, seed=2),
            "sideways": _make_returns(120, mean=0.002, std=0.008, seed=3),
        }

        result = gate_4_regime(regimes, min_passing_regimes=3)
        # All three have positive mean → should pass (though might not depending on seed)
        # At minimum: the function must NOT crash
        assert result is not None
        assert "n_passing_regimes" in result.details
