"""Tests for performance models."""

import pytest
from datetime import date, datetime, timezone
from uuid import uuid4

from src.models.performance import PostMortem, PerformanceReport, VALID_DIAGNOSES


class TestPostMortem:
    """Tests for PostMortem model."""

    def test_valid_postmortem_creation(self):
        """Test creating a valid PostMortem instance."""
        pm = PostMortem(
            trade_id=uuid4(),
            symbol="AAPL",
            loss_pct=0.035,
            signal_score=0.65,
            signal_confidence=0.8,
            ensemble_std=0.1,
            regime_at_trade="risk_on",
            reasoning_summary="Bull case cited strong iPhone demand and services growth.",
            diagnosis="low_confidence_passed",
        )
        assert pm.diagnosis in VALID_DIAGNOSES
        assert pm.symbol == "AAPL"
        assert pm.loss_pct == 0.035

    def test_all_valid_diagnoses(self):
        """Test that all valid diagnoses can be used."""
        valid_diagnoses = [
            "low_confidence_passed",
            "ensemble_divergence_ignored",
            "regime_mismatch",
            "news_staleness",
            "market_gap",
            "stop_too_tight",
            "correlated_portfolio_loss",
            "model_drift_active",
            "threshold_boundary",
            "unknown",
        ]
        for diag in valid_diagnoses:
            pm = PostMortem(
                trade_id=uuid4(),
                symbol="TEST",
                loss_pct=0.03,
                signal_score=0.5,
                signal_confidence=0.7,
                ensemble_std=0.1,
                regime_at_trade="risk_on",
                reasoning_summary="Test reasoning",
                diagnosis=diag,
            )
            assert pm.diagnosis == diag

    def test_invalid_diagnosis_raises(self):
        """Test that invalid diagnosis raises ValueError."""
        with pytest.raises(ValueError, match="diagnosis must be one of"):
            PostMortem(
                trade_id=uuid4(),
                symbol="AAPL",
                loss_pct=0.03,
                signal_score=0.5,
                signal_confidence=0.7,
                ensemble_std=0.1,
                regime_at_trade="risk_on",
                reasoning_summary="Test",
                diagnosis="invalid_diagnosis",
            )

    def test_reasoning_truncation(self):
        """Test that reasoning_summary is truncated to 200 chars."""
        long_reasoning = "A" * 300
        pm = PostMortem(
            trade_id=uuid4(),
            symbol="AAPL",
            loss_pct=0.03,
            signal_score=0.5,
            signal_confidence=0.7,
            ensemble_std=0.1,
            regime_at_trade="risk_on",
            reasoning_summary=long_reasoning,
            diagnosis="unknown",
        )
        assert len(pm.reasoning_summary) == 200
        assert pm.reasoning_summary == "A" * 200

    def test_reasoning_no_truncation_needed(self):
        """Test that short reasoning is not modified."""
        short_reasoning = "Short reasoning."
        pm = PostMortem(
            trade_id=uuid4(),
            symbol="AAPL",
            loss_pct=0.03,
            signal_score=0.5,
            signal_confidence=0.7,
            ensemble_std=0.1,
            regime_at_trade="risk_on",
            reasoning_summary=short_reasoning,
            diagnosis="unknown",
        )
        assert pm.reasoning_summary == short_reasoning

    def test_signal_score_bounds(self):
        """Test signal_score validation."""
        # Valid score
        pm = PostMortem(
            trade_id=uuid4(),
            symbol="AAPL",
            loss_pct=0.03,
            signal_score=1.0,
            signal_confidence=0.7,
            ensemble_std=0.1,
            regime_at_trade="risk_on",
            reasoning_summary="Test",
            diagnosis="unknown",
        )
        assert pm.signal_score == 1.0

        # Out of bounds should fail
        with pytest.raises(ValueError):
            PostMortem(
                trade_id=uuid4(),
                symbol="AAPL",
                loss_pct=0.03,
                signal_score=1.5,  # Out of bounds
                signal_confidence=0.7,
                ensemble_std=0.1,
                regime_at_trade="risk_on",
                reasoning_summary="Test",
                diagnosis="unknown",
            )

    def test_confidence_bounds(self):
        """Test signal_confidence validation."""
        # Valid confidence
        pm = PostMortem(
            trade_id=uuid4(),
            symbol="AAPL",
            loss_pct=0.03,
            signal_score=0.5,
            signal_confidence=1.0,
            ensemble_std=0.1,
            regime_at_trade="risk_on",
            reasoning_summary="Test",
            diagnosis="unknown",
        )
        assert pm.signal_confidence == 1.0

        # Out of bounds should fail
        with pytest.raises(ValueError):
            PostMortem(
                trade_id=uuid4(),
                symbol="AAPL",
                loss_pct=0.03,
                signal_score=0.5,
                signal_confidence=1.5,  # Out of bounds
                ensemble_std=0.1,
                regime_at_trade="risk_on",
                reasoning_summary="Test",
                diagnosis="unknown",
            )

    def test_loss_pct_non_negative(self):
        """Test loss_pct must be non-negative."""
        with pytest.raises(ValueError):
            PostMortem(
                trade_id=uuid4(),
                symbol="AAPL",
                loss_pct=-0.01,  # Negative not allowed
                signal_score=0.5,
                signal_confidence=0.7,
                ensemble_std=0.1,
                regime_at_trade="risk_on",
                reasoning_summary="Test",
                diagnosis="unknown",
            )


class TestPerformanceReport:
    """Tests for PerformanceReport model."""

    def _make_valid_report(self, **overrides) -> PerformanceReport:
        """Helper to create a valid PerformanceReport."""
        base = {
            "period_start": date(2026, 5, 1),
            "period_end": date(2026, 5, 3),
            "overall_ic": 0.14,
            "icir": 0.82,
            "hit_rate": 0.583,
            "model_ic": {"opus": 0.18, "qwen35": 0.14, "deepseek": 0.09},
            "model_icir": {"opus": 0.9, "qwen35": 0.7, "deepseek": 0.5},
            "recommended_weights": {"opus": 0.42, "qwen35": 0.33, "deepseek": 0.25},
            "weight_change_applied": False,
            "threshold_analysis": {"0.2-0.3": 0.05, "0.3-0.4": 0.12, "0.4-0.6": 0.18},
            "threshold_suggestion": None,
            "drift_alerts": [],
            "post_mortems": [],
            "report_version": "1.0",
        }
        base.update(overrides)
        return PerformanceReport(**base)

    def test_valid_report_creation(self):
        """Test creating a valid PerformanceReport."""
        report = self._make_valid_report()
        assert report.overall_ic == 0.14
        assert report.icir == 0.82
        assert report.hit_rate == 0.583
        assert report.report_version == "1.0"

    def test_hit_rate_bounds(self):
        """Test hit_rate must be between 0 and 1."""
        # Valid hit rates
        report = self._make_valid_report(hit_rate=0.0)
        assert report.hit_rate == 0.0

        report = self._make_valid_report(hit_rate=1.0)
        assert report.hit_rate == 1.0

        # Out of bounds should fail
        with pytest.raises(ValueError, match="hit_rate must be between 0 and 1"):
            self._make_valid_report(hit_rate=1.5)

        with pytest.raises(ValueError, match="hit_rate must be between 0 and 1"):
            self._make_valid_report(hit_rate=-0.1)

    def test_overall_ic_bounds(self):
        """Test overall_ic must be between -1 and 1."""
        # Valid IC
        report = self._make_valid_report(overall_ic=-0.5)
        assert report.overall_ic == -0.5

        report = self._make_valid_report(overall_ic=0.5)
        assert report.overall_ic == 0.5

        # Out of bounds should fail
        with pytest.raises(ValueError, match="overall_ic must be between -1 and 1"):
            self._make_valid_report(overall_ic=1.5)

        with pytest.raises(ValueError, match="overall_ic must be between -1 and 1"):
            self._make_valid_report(overall_ic=-1.5)

    def test_icir_any_real_number(self):
        """Test icir can be any real number (including negative)."""
        # Positive ICIR
        report = self._make_valid_report(icir=2.5)
        assert report.icir == 2.5

        # Negative ICIR (negative IC)
        report = self._make_valid_report(icir=-1.2)
        assert report.icir == -1.2

        # Zero ICIR
        report = self._make_valid_report(icir=0.0)
        assert report.icir == 0.0

    def test_weights_must_sum_to_one(self):
        """Test recommended_weights must sum to approximately 1."""
        # Valid weights
        report = self._make_valid_report(
            recommended_weights={"opus": 0.4, "qwen35": 0.35, "deepseek": 0.25}
        )
        assert sum(report.recommended_weights.values()) == pytest.approx(1.0)

        # Weights don't sum to 1
        with pytest.raises(ValueError, match="Weights must sum to 1"):
            self._make_valid_report(
                recommended_weights={"opus": 0.5, "qwen35": 0.5, "deepseek": 0.5}
            )

        # Empty weights (sum = 0)
        with pytest.raises(ValueError, match="Weights must sum to 1"):
            self._make_valid_report(recommended_weights={})

    def test_weights_individual_bounds(self):
        """Test each weight must be between 0 and 1."""
        # Weight > 1
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            self._make_valid_report(
                recommended_weights={"opus": 1.5, "qwen35": -0.3, "deepseek": 0.3}
            )

        # Negative weight
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            self._make_valid_report(
                recommended_weights={"opus": 0.8, "qwen35": -0.1, "deepseek": 0.3}
            )

    def test_threshold_suggestion_optional(self):
        """Test threshold_suggestion can be None or a float."""
        # None is valid
        report = self._make_valid_report(threshold_suggestion=None)
        assert report.threshold_suggestion is None

        # Float is valid
        report = self._make_valid_report(threshold_suggestion=0.35)
        assert report.threshold_suggestion == 0.35

    def test_drift_alerts_default_empty(self):
        """Test drift_alerts defaults to empty list."""
        report = self._make_valid_report()
        assert report.drift_alerts == []

        # Can have alerts
        report = self._make_valid_report(
            drift_alerts=["deepseek-v4: PSI_90gg=0.13"]
        )
        assert len(report.drift_alerts) == 1

    def test_post_mortems_default_empty(self):
        """Test post_mortems defaults to empty list."""
        report = self._make_valid_report()
        assert report.post_mortems == []

        # Can have post-mortems
        pm = PostMortem(
            trade_id=uuid4(),
            symbol="AAPL",
            loss_pct=0.04,
            signal_score=0.7,
            signal_confidence=0.85,
            ensemble_std=0.12,
            regime_at_trade="risk_on",
            reasoning_summary="Strong bull case ignored bear risks.",
            diagnosis="ensemble_divergence_ignored",
        )
        report = self._make_valid_report(post_mortems=[pm])
        assert len(report.post_mortems) == 1
        assert report.post_mortems[0].symbol == "AAPL"

    def test_generated_at_is_utc(self):
        """Test generated_at is set to current UTC time."""
        before = datetime.now(timezone.utc)
        report = self._make_valid_report()
        after = datetime.now(timezone.utc)

        assert before <= report.generated_at <= after
        assert report.generated_at.tzinfo == timezone.utc

    def test_full_report_with_postmortem(self):
        """Test a complete report with post-mortem analysis."""
        pm = PostMortem(
            trade_id=uuid4(),
            symbol="MSFT",
            loss_pct=0.035,
            signal_score=0.62,
            signal_confidence=0.78,
            ensemble_std=0.28,
            regime_at_trade="risk_on",
            reasoning_summary="Cloud growth acceleration expected.",
            diagnosis="threshold_boundary",
        )

        report = self._make_valid_report(
            overall_ic=0.12,
            icir=0.65,
            hit_rate=0.55,
            drift_alerts=["deepseek-v4: PSI_90gg=0.15"],
            post_mortems=[pm],
            threshold_suggestion=0.33,
        )

        assert report.overall_ic == 0.12
        assert len(report.post_mortems) == 1
        assert report.post_mortems[0].diagnosis == "threshold_boundary"
        assert report.drift_alerts[0] == "deepseek-v4: PSI_90gg=0.15"
        assert report.threshold_suggestion == 0.33
