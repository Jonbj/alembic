"""S7 PEAD (Post-Earnings Announcement Drift) strategy tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.models.pead import EarningsLLMOutput, SurpriseSignal
from src.strategies.s7.signal import EarningsSurpriseClassifier
from src.strategies.s7.strategy import PEADStrategy, PEADConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 10, 15, 0, 0, tzinfo=timezone.utc)


def _beat_signal(
    symbol: str = "AAPL",
    surprise_pct: float = 0.08,
    confidence: float = 0.85,
    days_old: int = 0,
) -> SurpriseSignal:
    detected = _NOW - timedelta(days=days_old)
    return SurpriseSignal(
        symbol=symbol,
        direction="beat",
        surprise_pct=surprise_pct,
        confidence=confidence,
        filing_id=f"edgar-{symbol}-001",
        detected_at=detected,
        hold_until=detected + timedelta(days=20),
    )


def _miss_signal(symbol: str = "TSLA") -> SurpriseSignal:
    return SurpriseSignal(
        symbol=symbol,
        direction="miss",
        surprise_pct=-0.10,
        confidence=0.80,
        filing_id=f"edgar-{symbol}-001",
        detected_at=_NOW,
        hold_until=_NOW + timedelta(days=20),
    )


# ---------------------------------------------------------------------------
# SurpriseSignal model
# ---------------------------------------------------------------------------


class TestSurpriseSignalModel:
    def test_valid_beat_signal(self) -> None:
        sig = _beat_signal()
        assert sig.direction == "beat"
        assert sig.surprise_pct == pytest.approx(0.08)
        assert sig.hold_until == sig.detected_at + timedelta(days=20)

    def test_valid_miss_signal(self) -> None:
        sig = _miss_signal()
        assert sig.direction == "miss"
        assert sig.surprise_pct < 0

    def test_confidence_clamped(self) -> None:
        with pytest.raises(Exception):
            SurpriseSignal(
                symbol="X",
                direction="beat",
                surprise_pct=0.05,
                confidence=1.5,  # > 1.0 → validation error
                filing_id="id",
                detected_at=_NOW,
                hold_until=_NOW + timedelta(days=20),
            )

    def test_is_active_within_hold_period(self) -> None:
        sig = _beat_signal(days_old=10)
        assert sig.is_active(as_of=_NOW) is True

    def test_is_not_active_past_hold_period(self) -> None:
        sig = _beat_signal(days_old=21)
        assert sig.is_active(as_of=_NOW) is False

    def test_is_active_exactly_at_hold_until(self) -> None:
        sig = _beat_signal(days_old=20)
        # hold_until == detected_at + 20d == _NOW exactly → still active
        assert sig.is_active(as_of=_NOW) is True


# ---------------------------------------------------------------------------
# EarningsLLMOutput model
# ---------------------------------------------------------------------------


class TestEarningsLLMOutput:
    def test_valid_output(self) -> None:
        out = EarningsLLMOutput(
            ticker="AAPL",
            filing_type="earnings_8k",
            eps_actual=1.52,
            eps_consensus=1.45,
            surprise_pct=0.048,
            direction="beat",
            guidance="revised-up",
            confidence=0.85,
            reasoning="Beat on EPS and raised guidance",
        )
        assert out.ticker == "AAPL"
        assert out.direction == "beat"

    def test_no_eps_direction_allowed(self) -> None:
        out = EarningsLLMOutput(
            ticker="XYZ",
            filing_type="other",
            direction="no_eps",
            guidance="no-guidance",
            confidence=0.50,
            reasoning="No EPS data found",
        )
        assert out.direction == "no_eps"


# ---------------------------------------------------------------------------
# EarningsSurpriseClassifier — signal derivation from LLM output
# ---------------------------------------------------------------------------


class TestEarningsSurpriseClassifier:
    def setup_method(self) -> None:
        self.classifier = EarningsSurpriseClassifier(
            surprise_threshold=0.05,
            min_confidence=0.70,
        )

    def test_beat_produces_signal(self) -> None:
        llm_out = EarningsLLMOutput(
            ticker="AAPL",
            filing_type="earnings_8k",
            eps_actual=1.52,
            eps_consensus=1.40,
            surprise_pct=0.086,
            direction="beat",
            guidance="revised-up",
            confidence=0.85,
            reasoning="Strong beat",
        )
        sig = self.classifier.to_signal(llm_out, filing_id="id-001", detected_at=_NOW)
        assert sig is not None
        assert sig.symbol == "AAPL"
        assert sig.direction == "beat"
        assert sig.surprise_pct == pytest.approx(0.086)

    def test_miss_produces_signal(self) -> None:
        llm_out = EarningsLLMOutput(
            ticker="TSLA",
            filing_type="earnings_8k",
            eps_actual=0.45,
            eps_consensus=0.55,
            surprise_pct=-0.182,
            direction="miss",
            guidance="revised-down",
            confidence=0.80,
            reasoning="Miss on EPS",
        )
        sig = self.classifier.to_signal(llm_out, filing_id="id-002", detected_at=_NOW)
        assert sig is not None
        assert sig.direction == "miss"

    def test_low_confidence_returns_none(self) -> None:
        llm_out = EarningsLLMOutput(
            ticker="NVDA",
            filing_type="earnings_8k",
            surprise_pct=0.06,
            direction="beat",
            guidance="no-guidance",
            confidence=0.50,  # below min_confidence=0.70
            reasoning="Uncertain",
        )
        sig = self.classifier.to_signal(llm_out, filing_id="id-003", detected_at=_NOW)
        assert sig is None

    def test_no_eps_returns_none(self) -> None:
        llm_out = EarningsLLMOutput(
            ticker="META",
            filing_type="other",
            direction="no_eps",
            guidance="no-guidance",
            confidence=0.90,
            reasoning="No EPS data",
        )
        sig = self.classifier.to_signal(llm_out, filing_id="id-004", detected_at=_NOW)
        assert sig is None

    def test_surprise_below_threshold_returns_inline(self) -> None:
        llm_out = EarningsLLMOutput(
            ticker="GOOG",
            filing_type="earnings_8k",
            eps_actual=1.02,
            eps_consensus=1.00,
            surprise_pct=0.02,  # below 0.05 threshold
            direction="beat",  # LLM says beat but magnitude too small
            guidance="maintained",
            confidence=0.80,
            reasoning="Marginal beat",
        )
        sig = self.classifier.to_signal(llm_out, filing_id="id-005", detected_at=_NOW)
        # Small positive beat below threshold → treated as inline, no signal
        assert sig is None

    def test_hold_until_set_to_20_days(self) -> None:
        llm_out = EarningsLLMOutput(
            ticker="MSFT",
            filing_type="earnings_8k",
            surprise_pct=0.07,
            direction="beat",
            guidance="maintained",
            confidence=0.75,
            reasoning="Beat",
        )
        sig = self.classifier.to_signal(llm_out, filing_id="id-006", detected_at=_NOW)
        assert sig is not None
        assert sig.hold_until == _NOW + timedelta(days=20)


# ---------------------------------------------------------------------------
# PEADStrategy — compute_target_weights
# ---------------------------------------------------------------------------


class TestPEADStrategyWeights:
    def setup_method(self) -> None:
        self.cfg = PEADConfig(
            max_position_pct=0.05,
            max_sleeve_pct=0.25,
            min_confidence=0.70,
            surprise_threshold=0.05,
            hold_days=20,
        )
        self.strategy = PEADStrategy(self.cfg)

    def test_single_beat_produces_weight(self) -> None:
        signals = [_beat_signal("AAPL")]
        weights = self.strategy.compute_target_weights(signals, as_of=_NOW)
        assert "AAPL" in weights
        assert weights["AAPL"] == pytest.approx(0.05)

    def test_miss_signal_excluded(self) -> None:
        signals = [_miss_signal("TSLA")]
        weights = self.strategy.compute_target_weights(signals, as_of=_NOW)
        assert "TSLA" not in weights

    def test_max_position_capped(self) -> None:
        # 10 beat signals: each would want 5%, sleeve cap = 25% → 5 positions at 5%
        signals = [_beat_signal(f"T{i:02d}") for i in range(10)]
        weights = self.strategy.compute_target_weights(signals, as_of=_NOW)
        total = sum(weights.values())
        assert total <= self.cfg.max_sleeve_pct + 1e-9
        for w in weights.values():
            assert w <= self.cfg.max_position_pct + 1e-9

    def test_expired_signal_excluded(self) -> None:
        # Signal from 21 days ago → hold_until passed
        old_signal = _beat_signal("OLD", days_old=21)
        weights = self.strategy.compute_target_weights([old_signal], as_of=_NOW)
        assert "OLD" not in weights

    def test_low_confidence_excluded(self) -> None:
        sig = _beat_signal("LOW", confidence=0.60)
        weights = self.strategy.compute_target_weights([sig], as_of=_NOW)
        assert "LOW" not in weights

    def test_empty_signals_returns_empty(self) -> None:
        weights = self.strategy.compute_target_weights([], as_of=_NOW)
        assert weights == {}

    def test_weights_are_positive_floats(self) -> None:
        signals = [_beat_signal(f"T{i:02d}") for i in range(3)]
        weights = self.strategy.compute_target_weights(signals, as_of=_NOW)
        for w in weights.values():
            assert isinstance(w, float)
            assert w > 0


# ---------------------------------------------------------------------------
# PEADStrategy — exit logic (miss on held position)
# ---------------------------------------------------------------------------


class TestPEADStrategyExitOnMiss:
    def setup_method(self) -> None:
        self.cfg = PEADConfig(
            max_position_pct=0.05,
            max_sleeve_pct=0.25,
            min_confidence=0.70,
            surprise_threshold=0.05,
            hold_days=20,
        )
        self.strategy = PEADStrategy(self.cfg)

    def test_miss_on_held_ticker_produces_zero_weight(self) -> None:
        miss = _miss_signal("TSLA")
        weights = self.strategy.compute_target_weights([miss], as_of=_NOW)
        # Miss → weight 0.0 (signal that a held position should be closed)
        assert weights.get("TSLA", 0.0) == 0.0

    def test_beat_plus_miss_only_beat_appears(self) -> None:
        signals = [_beat_signal("AAPL"), _miss_signal("TSLA")]
        weights = self.strategy.compute_target_weights(signals, as_of=_NOW)
        assert "AAPL" in weights
        assert "TSLA" not in weights
