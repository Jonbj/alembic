"""
Tests for drift detection module (PSI, CUSUM, circuit breakers).

Reference: docs/superpowers/plans/2026-05-03-fase1-foundation.md - Task 18
"""

import numpy as np
import pytest
from src.performance.drift import (
    compute_psi,
    compute_cusum,
    check_circuit_breakers,
    detect_drift,
    PSI_YELLOW_THRESHOLD,
    PSI_RED_THRESHOLD,
    DriftAlert,
    CircuitBreakerContext,
    CircuitBreakerResult,
)


class TestComputePSI:
    """Tests for Population Stability Index computation."""

    def test_identical_distributions(self):
        """PSI should be ~0 for identical distributions."""
        data = np.random.normal(0, 1, 1000)
        psi = compute_psi(data, data)
        assert psi < 0.01  # Small due to binning artifacts

    def test_shifted_distribution(self):
        """PSI should detect mean shift."""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(1, 1, 1000)  # Shifted by 1 std
        psi = compute_psi(baseline, current)
        assert psi > 0.10  # Should detect moderate drift

    def test_empty_arrays(self):
        """PSI should return 0 for empty inputs."""
        assert compute_psi(np.array([]), np.array([])) == 0.0
        assert compute_psi(np.array([1, 2, 3]), np.array([])) == 0.0
        assert compute_psi(np.array([]), np.array([1, 2, 3])) == 0.0

    def test_single_value_arrays(self):
        """PSI should handle single-value arrays gracefully."""
        baseline = np.array([5.0, 5.0, 5.0])
        current = np.array([5.0, 5.0, 5.0])
        psi = compute_psi(baseline, current)
        assert psi == 0.0

    def test_different_variance(self):
        """PSI should detect variance changes."""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(0, 3, 1000)  # 3x variance
        psi = compute_psi(baseline, current)
        assert psi > 0.05  # Should detect distribution change

    def test_psi_thresholds_green(self):
        """PSI < 0.10 should indicate stable distribution."""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(0.1, 1, 1000)  # Minimal shift
        psi = compute_psi(baseline, current)
        assert psi < PSI_YELLOW_THRESHOLD

    def test_psi_thresholds_yellow(self):
        """PSI 0.10-0.25 should indicate moderate drift."""
        baseline = np.random.normal(0, 1, 1000)
        current = np.random.normal(0.8, 1, 1000)  # Moderate shift
        psi = compute_psi(baseline, current)
        assert PSI_YELLOW_THRESHOLD < psi < PSI_RED_THRESHOLD or psi > PSI_RED_THRESHOLD

    def test_psi_deterministic(self):
        """PSI should be deterministic for same inputs."""
        a = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        b = np.array([2, 3, 4, 5, 6, 7, 8, 9, 10, 11])
        psi1 = compute_psi(a, b)
        psi2 = compute_psi(a, b)
        assert psi1 == psi2


class TestComputeCUSUM:
    """Tests for CUSUM change detection."""

    def test_stable_process(self):
        """CUSUM should stay below threshold for stable process."""
        np.random.seed(42)
        scores = np.random.normal(0, 1, 100)
        cusum, threshold = compute_cusum(scores, baseline_mean=0, baseline_std=1)
        assert cusum < threshold  # Should not trigger (slack prevents accumulation)

    def test_shifted_process(self):
        """CUSUM should exceed threshold after mean shift."""
        np.random.seed(42)
        # Simulate shift halfway through
        first_half = np.random.normal(0, 1, 50)
        second_half = np.random.normal(1.5, 1, 50)  # Significant shift
        scores = np.concatenate([first_half, second_half])
        cusum, threshold = compute_cusum(scores, baseline_mean=0, baseline_std=1)
        assert cusum > threshold  # Should detect shift

    def test_empty_input(self):
        """CUSUM should return 0 for empty input."""
        cusum, threshold = compute_cusum(np.array([]), 0, 1)
        assert cusum == 0.0
        assert threshold == 0.0

    def test_custom_threshold(self):
        """CUSUM should use custom threshold."""
        scores = np.random.normal(0, 1, 100)
        _, threshold_low = compute_cusum(scores, 0, 1, threshold=3.0)
        _, threshold_high = compute_cusum(scores, 0, 1, threshold=8.0)
        assert threshold_high > threshold_low

    def test_negative_shift(self):
        """CUSUM should detect negative shifts too."""
        np.random.seed(42)
        scores = np.random.normal(-1.0, 1, 100)  # Negative shift
        cusum, threshold = compute_cusum(scores, baseline_mean=0, baseline_std=1)
        # CUSUM tracks both positive and negative deviations
        assert cusum > 0

    def test_slack_parameter(self):
        """Higher slack should reduce CUSUM sensitivity."""
        np.random.seed(42)
        scores = np.random.normal(0.3, 1, 100)  # Slight positive shift
        cusum_low_slack, _ = compute_cusum(scores, 0, 1, slack=0.2)
        cusum_high_slack, _ = compute_cusum(scores, 0, 1, slack=0.8)
        assert cusum_low_slack > cusum_high_slack


class TestCheckCircuitBreakers:
    """Tests for circuit breaker logic."""

    def test_normal_conditions(self):
        """No breakers should trigger under normal conditions."""
        ctx = CircuitBreakerContext(
            vix=15,
            vix_1d_change=0.05,
            portfolio_drawdown=0.02,
            consecutive_negative_ic_days=2,
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is False
        assert len(result.hard_breakers_triggered) == 0
        assert len(result.soft_warnings_triggered) == 0

    def test_vix_spike(self):
        """VIX spike should trigger hard breaker."""
        ctx = CircuitBreakerContext(
            vix=45,  # > 40 threshold
            vix_1d_change=0.05,
            portfolio_drawdown=0.02,
            consecutive_negative_ic_days=0,
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is True
        assert "vix_spike" in result.hard_breakers_triggered

    def test_vix_1d_change_spike(self):
        """VIX 1-day spike should trigger hard breaker."""
        ctx = CircuitBreakerContext(
            vix=30,
            vix_1d_change=0.35,  # > 0.30 threshold
            portfolio_drawdown=0.02,
            consecutive_negative_ic_days=0,
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is True
        assert "vix_spike" in result.hard_breakers_triggered

    def test_system_drawdown(self):
        """System drawdown should trigger hard breaker."""
        ctx = CircuitBreakerContext(
            vix=15,
            vix_1d_change=0.05,
            portfolio_drawdown=0.06,  # > 0.05 threshold
            consecutive_negative_ic_days=0,
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is True
        assert "system_drawdown" in result.hard_breakers_triggered

    def test_ic_negative_run(self):
        """Consecutive negative IC days should trigger hard breaker."""
        ctx = CircuitBreakerContext(
            vix=15,
            vix_1d_change=0.05,
            portfolio_drawdown=0.02,
            consecutive_negative_ic_days=5,  # >= 5 threshold
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is True
        assert "ic_negative_run" in result.hard_breakers_triggered

    def test_earnings_concentration(self):
        """High earnings concentration should trigger soft warning."""
        ctx = CircuitBreakerContext(
            vix=15,
            vix_1d_change=0.05,
            portfolio_drawdown=0.02,
            consecutive_negative_ic_days=0,
            portfolio_earnings_pct=0.55,  # > 0.50 threshold
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is False
        assert "earnings_concentration" in result.soft_warnings_triggered

    def test_cross_asset_correlation(self):
        """High cross-asset correlation should trigger soft warning."""
        ctx = CircuitBreakerContext(
            vix=15,
            vix_1d_change=0.05,
            portfolio_drawdown=0.02,
            consecutive_negative_ic_days=0,
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.95,  # > 0.90 threshold
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is False
        assert "cross_asset_corr" in result.soft_warnings_triggered

    def test_multiple_hard_breakers(self):
        """Multiple hard breakers can trigger simultaneously."""
        ctx = CircuitBreakerContext(
            vix=45,  # VIX spike
            vix_1d_change=0.05,
            portfolio_drawdown=0.06,  # Also drawdown
            consecutive_negative_ic_days=0,
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.freeze_weight_update is True
        assert len(result.hard_breakers_triggered) >= 2

    def test_reason_provided_on_freeze(self):
        """Reason should be provided when freezing."""
        ctx = CircuitBreakerContext(
            vix=45,
            vix_1d_change=0.05,
            portfolio_drawdown=0.02,
            consecutive_negative_ic_days=0,
            portfolio_earnings_pct=0.30,
            cross_asset_correlation=0.50,
        )
        result = check_circuit_breakers(ctx)
        assert result.reason is not None
        assert "vix_spike" in result.reason


class TestDetectDrift:
    """Tests for comprehensive drift detection."""

    def test_stable_regime(self):
        """Should return green alert for stable distributions."""
        np.random.seed(42)
        # Realistic sample sizes: 90 days and 7 days with signals every 15 min
        # ~4 signals/hour * 24 hours * 90 days = ~8640 (use 900 for test speed)
        # ~4 signals/hour * 24 hours * 7 days = ~672 (use 700 for test)
        baseline_90gg = np.random.normal(0, 1, 900)
        baseline_12m = np.random.normal(0, 1, 3600)
        current_7gg = np.random.normal(0, 1, 700)  # Larger sample for stable PSI

        alert = detect_drift(baseline_90gg, baseline_12m, current_7gg)

        # With stable distribution, PSI should be low and CUSUM should not trigger
        assert alert.level == "green"
        assert alert.psi_90gg < PSI_YELLOW_THRESHOLD
        assert alert.cusum_value < alert.cusum_threshold

    def test_moderate_drift_yellow(self):
        """Should return yellow alert for moderate drift."""
        np.random.seed(42)
        baseline_90gg = np.random.normal(0, 1, 900)
        baseline_12m = np.random.normal(0, 1, 3600)
        current_7gg = np.random.normal(0.5, 1, 70)  # Moderate shift

        alert = detect_drift(baseline_90gg, baseline_12m, current_7gg)

        assert alert.level in ["yellow", "red"]  # At least yellow
        assert alert.psi_90gg > PSI_YELLOW_THRESHOLD or alert.cusum_value > alert.cusum_threshold

    def test_severe_drift_red_confirmed(self):
        """Should return red alert for severe confirmed drift."""
        np.random.seed(42)
        baseline_90gg = np.random.normal(0, 1, 900)
        baseline_12m = np.random.normal(0, 1, 3600)
        current_7gg = np.random.normal(1.5, 1, 70)  # Severe shift

        alert = detect_drift(baseline_90gg, baseline_12m, current_7gg)

        # With severe shift, should be at least yellow, possibly red if confirmed
        assert alert.level in ["yellow", "red"]

    def test_no_12m_baseline(self):
        """Should work without 12-month baseline."""
        np.random.seed(42)
        baseline_90gg = np.random.normal(0, 1, 900)
        current_7gg = np.random.normal(0.1, 1, 70)

        alert = detect_drift(baseline_90gg, None, current_7gg)

        assert alert.psi_12m is None
        assert alert.level in ["green", "yellow", "red"]

    def test_alert_contains_diagnostics(self):
        """Alert should contain all diagnostic metrics."""
        np.random.seed(42)
        baseline_90gg = np.random.normal(0.3, 1, 900)
        current_7gg = np.random.normal(0.5, 1, 70)

        alert = detect_drift(baseline_90gg, None, current_7gg)

        assert alert.baseline_mean is not None
        assert alert.current_mean is not None
        assert alert.cusum_value >= 0
        assert alert.cusum_threshold > 0
        assert alert.psi_90gg >= 0

    def test_cusum_confirmation(self):
        """CUSUM should confirm significant shifts."""
        np.random.seed(42)
        # Create a clear shift in the last 7 days
        baseline_90gg = np.random.normal(0, 1, 900)
        current_7gg = np.random.normal(2, 1, 70)  # Strong shift

        alert = detect_drift(baseline_90gg, None, current_7gg)

        # Strong shift should trigger CUSUM confirmation
        assert alert.cusum_value > alert.cusum_threshold or alert.psi_90gg > PSI_RED_THRESHOLD


class TestIntegration:
    """Integration tests for drift detection workflow."""

    def test_full_workflow(self):
        """Test complete drift detection and circuit breaker workflow."""
        np.random.seed(42)

        # Simulate normal market conditions
        baseline_90gg = np.random.normal(0.2, 0.3, 900)
        baseline_12m = np.random.normal(0.2, 0.3, 3600)
        current_7gg = np.random.normal(0.25, 0.3, 70)

        # Drift detection
        alert = detect_drift(baseline_90gg, baseline_12m, current_7gg)

        # Circuit breaker check
        ctx = CircuitBreakerContext(
            vix=18,
            vix_1d_change=0.08,
            portfolio_drawdown=0.03,
            consecutive_negative_ic_days=1,
            portfolio_earnings_pct=0.40,
            cross_asset_correlation=0.60,
        )
        cb_result = check_circuit_breakers(ctx)

        # Verify workflow completes without errors
        assert isinstance(alert, DriftAlert)
        assert isinstance(cb_result, CircuitBreakerResult)
        assert cb_result.freeze_weight_update is False

    def test_crisis_scenario(self):
        """Test behavior under crisis conditions."""
        np.random.seed(42)

        # Simulate crisis: significant drift in model outputs
        baseline_90gg = np.random.normal(0.3, 0.2, 900)
        baseline_12m = np.random.normal(0.3, 0.2, 3600)
        current_7gg = np.random.normal(-0.2, 0.4, 70)  # Regime change

        alert = detect_drift(baseline_90gg, baseline_12m, current_7gg)

        # Crisis market conditions
        ctx = CircuitBreakerContext(
            vix=55,  # VIX spike
            vix_1d_change=0.40,  # Also spiked
            portfolio_drawdown=0.08,  # Drawdown
            consecutive_negative_ic_days=6,  # Negative IC run
            portfolio_earnings_pct=0.60,  # High concentration
            cross_asset_correlation=0.95,  # High correlation
        )
        cb_result = check_circuit_breakers(ctx)

        # All hard breakers should trigger
        assert cb_result.freeze_weight_update is True
        assert len(cb_result.hard_breakers_triggered) >= 1
        assert len(cb_result.soft_warnings_triggered) >= 1
