"""Tests for post-mortem trigger and diagnosis logic."""

from dataclasses import replace

import pytest

from src.performance.postmortem import (
    CONFIDENCE_THRESHOLD,
    DIVERGENCE_STD_THRESHOLD,
    SIGNAL_MAX_AGE_MIN,
    TradeContext,
    _is_regime_mismatch,
    _is_stop_too_tight,
    _is_threshold_boundary,
    diagnose_loss,
    should_trigger_postmortem,
)

_DEFAULT_CONTEXT = TradeContext(
    loss_pct=0.03,
    signal_score=0.5,
    signal_confidence=0.8,
    ensemble_std=0.1,
    regime="risk_on",
    reasoning_summary="Strong earnings beat, bullish outlook.",
    signal_age_minutes=10,
    drift_alert_active=False,
    cross_asset_corr=0.3,
    stop_loss_pct=0.02,
    asset_volatility=0.02,
    was_overnight_gap=False,
)


class TestShouldTriggerPostmortem:
    """Tests for should_trigger_postmortem() function."""

    def test_triggers_on_loss_gte_3pct(self):
        """Loss >= 3% always triggers post-mortem."""
        assert should_trigger_postmortem(loss_pct=0.03, score=0.1, ensemble_std=0.1) is True
        assert should_trigger_postmortem(loss_pct=0.05, score=0.1, ensemble_std=0.1) is True
        assert should_trigger_postmortem(loss_pct=0.10, score=0.1, ensemble_std=0.1) is True

    def test_no_trigger_on_loss_lt_2pct(self):
        """Loss < 2% never triggers regardless of score/std."""
        assert should_trigger_postmortem(loss_pct=0.019, score=0.9, ensemble_std=0.5) is False
        assert should_trigger_postmortem(loss_pct=0.01, score=0.9, ensemble_std=0.5) is False

    def test_triggers_on_loss_gte_2pct_with_high_conviction_score(self):
        """Loss >= 2% triggers if |score| >= 0.5."""
        # Positive high conviction
        assert should_trigger_postmortem(loss_pct=0.02, score=0.5, ensemble_std=0.1) is True
        assert should_trigger_postmortem(loss_pct=0.025, score=0.6, ensemble_std=0.1) is True
        # Negative high conviction
        assert should_trigger_postmortem(loss_pct=0.02, score=-0.5, ensemble_std=0.1) is True
        assert should_trigger_postmortem(loss_pct=0.025, score=-0.8, ensemble_std=0.1) is True

    def test_triggers_on_loss_gte_2pct_with_high_ensemble_std(self):
        """Loss >= 2% triggers if ensemble_std >= 0.3."""
        assert should_trigger_postmortem(loss_pct=0.02, score=0.1, ensemble_std=0.3) is True
        assert should_trigger_postmortem(loss_pct=0.025, score=0.1, ensemble_std=0.5) is True

    def test_boundary_conditions_score(self):
        """Test boundary at |score| = 0.5."""
        # Just below threshold - should NOT trigger (loss < 3%)
        assert should_trigger_postmortem(loss_pct=0.02, score=0.49, ensemble_std=0.1) is False
        assert should_trigger_postmortem(loss_pct=0.02, score=-0.49, ensemble_std=0.1) is False
        # At threshold - should trigger
        assert should_trigger_postmortem(loss_pct=0.02, score=0.5, ensemble_std=0.1) is True
        assert should_trigger_postmortem(loss_pct=0.02, score=-0.5, ensemble_std=0.1) is True

    def test_boundary_conditions_ensemble_std(self):
        """Test boundary at ensemble_std = 0.3."""
        # Just below threshold - should NOT trigger (loss < 3%)
        assert should_trigger_postmortem(loss_pct=0.02, score=0.1, ensemble_std=0.29) is False
        # At threshold - should trigger
        assert should_trigger_postmortem(loss_pct=0.02, score=0.1, ensemble_std=0.3) is True

    def test_no_trigger_small_loss_low_score_low_std(self):
        """Small loss with low conviction and low divergence - no trigger."""
        assert should_trigger_postmortem(loss_pct=0.02, score=0.2, ensemble_std=0.1) is False
        assert should_trigger_postmortem(loss_pct=0.015, score=0.3, ensemble_std=0.2) is False


class TestDiagnoseLoss:
    """Tests for diagnose_loss() function."""

    def make_context(self, **overrides) -> TradeContext:
        """Create a TradeContext with sensible defaults."""
        return replace(_DEFAULT_CONTEXT, **overrides)

    def test_market_gap_takes_priority(self):
        """Overnight gap events are classified as market_gap."""
        ctx = self.make_context(
            was_overnight_gap=True,
            drift_alert_active=True,  # Even with drift active
        )
        assert diagnose_loss(ctx) == "market_gap"

    def test_model_drift_active(self):
        """Drift alert active at trade time -> model_drift_active."""
        ctx = self.make_context(drift_alert_active=True)
        assert diagnose_loss(ctx) == "model_drift_active"

    def test_low_confidence_passed(self):
        """Confidence below threshold -> low_confidence_passed."""
        ctx = self.make_context(signal_confidence=CONFIDENCE_THRESHOLD - 0.01)
        assert diagnose_loss(ctx) == "low_confidence_passed"

    def test_ensemble_divergence_ignored(self):
        """High ensemble std -> ensemble_divergence_ignored."""
        ctx = self.make_context(ensemble_std=DIVERGENCE_STD_THRESHOLD)
        assert diagnose_loss(ctx) == "ensemble_divergence_ignored"

    def test_regime_mismatch_risk_off_bullish_signal(self):
        """Bullish signal in risk_off regime -> regime_mismatch."""
        ctx = self.make_context(regime="risk_off", signal_score=0.6)
        assert diagnose_loss(ctx) == "regime_mismatch"

    def test_regime_mismatch_risk_on_bearish_signal(self):
        """Bearish signal in risk_on regime -> regime_mismatch."""
        ctx = self.make_context(regime="risk_on", signal_score=-0.6)
        assert diagnose_loss(ctx) == "regime_mismatch"

    def test_regime_mismatch_uncertain_high_conviction(self):
        """High conviction in uncertain regime -> regime_mismatch."""
        ctx = self.make_context(regime="uncertain", signal_score=0.7)
        assert diagnose_loss(ctx) == "regime_mismatch"

    def test_regime_mismatch_high_vol_directional(self):
        """Directional signal in high_vol regime -> regime_mismatch."""
        ctx = self.make_context(regime="high_vol", signal_score=0.5)
        assert diagnose_loss(ctx) == "regime_mismatch"

    def test_news_staleness(self):
        """Signal older than max age -> news_staleness."""
        ctx = self.make_context(signal_age_minutes=SIGNAL_MAX_AGE_MIN + 1)
        assert diagnose_loss(ctx) == "news_staleness"

    def test_correlated_portfolio_loss(self):
        """High cross-asset correlation -> correlated_portfolio_loss."""
        ctx = self.make_context(cross_asset_corr=0.85)
        assert diagnose_loss(ctx) == "correlated_portfolio_loss"

    def test_stop_too_tight(self):
        """Stop too tight for asset volatility -> stop_too_tight."""
        # Asset vol is 5%, stop is 2% - stop is too tight
        ctx = self.make_context(
            stop_loss_pct=0.02,
            asset_volatility=0.05,
            loss_pct=0.025,  # Loss just beyond stop
        )
        assert diagnose_loss(ctx) == "stop_too_tight"

    def test_threshold_boundary(self):
        """Score in boundary zone [0.25, 0.35] -> threshold_boundary."""
        ctx = self.make_context(signal_score=0.30)
        assert diagnose_loss(ctx) == "threshold_boundary"

        ctx = self.make_context(signal_score=0.25)
        assert diagnose_loss(ctx) == "threshold_boundary"

        ctx = self.make_context(signal_score=0.35)
        assert diagnose_loss(ctx) == "threshold_boundary"

        # Negative boundary
        ctx = self.make_context(signal_score=-0.30)
        assert diagnose_loss(ctx) == "threshold_boundary"

    def test_unknown_fallback(self):
        """No identifiable cause -> unknown."""
        ctx = self.make_context(
            signal_age_minutes=5,
            cross_asset_corr=0.2,
        )
        assert diagnose_loss(ctx) == "unknown"

    def test_diagnosis_priority_order(self):
        """Verify diagnosis priority - first matching condition wins."""
        # Multiple conditions true - market_gap should win
        ctx = self.make_context(
            was_overnight_gap=True,
            signal_confidence=0.2,  # low confidence
            ensemble_std=0.4,  # divergence
        )
        assert diagnose_loss(ctx) == "market_gap"

        # Drift active beats low confidence
        ctx = self.make_context(
            drift_alert_active=True,
            signal_confidence=0.2,
        )
        assert diagnose_loss(ctx) == "model_drift_active"


class TestIsRegimeMismatch:
    """Tests for _is_regime_mismatch() helper."""

    def test_risk_off_with_bullish_signal(self):
        """Risk-off + bullish signal > 0.5 is mismatch."""
        assert _is_regime_mismatch("risk_off", 0.51) is True
        assert _is_regime_mismatch("risk_off", 0.5) is False
        assert _is_regime_mismatch("risk_off", 0.4) is False

    def test_risk_on_with_bearish_signal(self):
        """Risk-on + bearish signal < -0.5 is mismatch."""
        assert _is_regime_mismatch("risk_on", -0.51) is True
        assert _is_regime_mismatch("risk_on", -0.5) is False
        assert _is_regime_mismatch("risk_on", -0.4) is False

    def test_uncertain_with_high_conviction(self):
        """Uncertain + |score| > 0.6 is mismatch."""
        assert _is_regime_mismatch("uncertain", 0.61) is True
        assert _is_regime_mismatch("uncertain", -0.61) is True
        assert _is_regime_mismatch("uncertain", 0.6) is False
        assert _is_regime_mismatch("uncertain", 0.3) is False

    def test_high_vol_with_directional_signal(self):
        """High-vol + |score| > 0.4 is mismatch."""
        assert _is_regime_mismatch("high_vol", 0.41) is True
        assert _is_regime_mismatch("high_vol", -0.41) is True
        assert _is_regime_mismatch("high_vol", 0.4) is False
        assert _is_regime_mismatch("high_vol", 0.2) is False

    def test_trending_ranging_no_mismatch(self):
        """Trending/ranging regimes don't cause mismatches."""
        assert _is_regime_mismatch("trending", 0.8) is False
        assert _is_regime_mismatch("ranging", 0.8) is False


class TestIsStopTooTight:
    """Tests for _is_stop_too_tight() helper."""

    def test_volatility_gt_2x_stop(self):
        """Asset vol > 2x stop and loss near stop -> too tight."""
        # 5% vol, 2% stop -> stop is too tight
        assert _is_stop_too_tight(0.02, 0.05, 0.025) is True

    def test_volatility_lt_2x_stop(self):
        """Asset vol < 2x stop -> not too tight."""
        # 3% vol, 2% stop -> stop is reasonable
        assert _is_stop_too_tight(0.02, 0.03, 0.025) is False

    def test_loss_much_larger_than_stop(self):
        """Loss >> stop -> not a tight stop issue."""
        # 5% vol, 2% stop, but loss is 10% -> major move, not tight stop
        assert _is_stop_too_tight(0.02, 0.05, 0.10) is False

    def test_zero_volatility(self):
        """Zero volatility -> never too tight."""
        assert _is_stop_too_tight(0.02, 0.0, 0.025) is False


class TestIsThresholdBoundary:
    """Tests for _is_threshold_boundary() helper."""

    def test_in_boundary_zone(self):
        """Scores in [0.25, 0.35] are boundary."""
        assert _is_threshold_boundary(0.25) is True
        assert _is_threshold_boundary(0.30) is True
        assert _is_threshold_boundary(0.35) is True
        assert _is_threshold_boundary(-0.25) is True
        assert _is_threshold_boundary(-0.30) is True
        assert _is_threshold_boundary(-0.35) is True

    def test_below_boundary(self):
        """Scores < 0.25 are below boundary."""
        assert _is_threshold_boundary(0.24) is False
        assert _is_threshold_boundary(0.1) is False
        assert _is_threshold_boundary(0.0) is False

    def test_above_boundary(self):
        """Scores > 0.35 are above boundary."""
        assert _is_threshold_boundary(0.36) is False
        assert _is_threshold_boundary(0.5) is False
        assert _is_threshold_boundary(0.8) is False
