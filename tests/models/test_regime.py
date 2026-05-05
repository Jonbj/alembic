"""Tests for regime Pydantic models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.regime import REGIME_DEFAULTS, MacroSnapshot, RegimeOutput, RegimeState


class TestRegimeOutput:
    def test_valid_bull(self):
        r = RegimeOutput(regime="bull", confidence=0.9, reasoning="uptrend")
        assert r.regime == "bull"
        assert r.data_quality == "complete"
        assert r.regime_secondary is None

    def test_invalid_regime_rejected(self):
        with pytest.raises(ValidationError):
            RegimeOutput(regime="crash", confidence=0.9, reasoning="bad")

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            RegimeOutput(regime="bull", confidence=1.5, reasoning="x")

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            RegimeOutput(regime="bear", confidence=-0.1, reasoning="x")

    def test_partial_data_quality_accepted(self):
        r = RegimeOutput(regime="sideways", confidence=0.5, reasoning="x", data_quality="partial")
        assert r.data_quality == "partial"

    def test_regime_secondary_optional(self):
        r = RegimeOutput(regime="bear", confidence=0.7, reasoning="x", regime_secondary="sideways")
        assert r.regime_secondary == "sideways"


class TestRegimeState:
    def _make_state(self, regime="bear"):
        return RegimeState(
            regime=regime,
            multiplier=0.4,
            macro_snapshot=MacroSnapshot(vix=28.4, yield_curve=-0.6, spy_momentum_20d=-7.1),
            llm_outputs=[{"regime": regime, "reasoning": "test"}],
            detected_at=datetime(2026, 5, 5, 7, 0, 0, tzinfo=timezone.utc),
        )

    def test_json_roundtrip(self):
        state = self._make_state()
        restored = RegimeState.model_validate_json(state.model_dump_json())
        assert restored.regime == "bear"
        assert restored.multiplier == 0.4
        assert restored.macro_snapshot.vix == pytest.approx(28.4)

    def test_disagreement_defaults_false(self):
        state = self._make_state()
        assert state.disagreement is False

    def test_macro_snapshot_fields(self):
        snap = MacroSnapshot(vix=18.4, yield_curve=0.3, spy_momentum_20d=4.2)
        assert snap.vix == pytest.approx(18.4)
        assert snap.yield_curve == pytest.approx(0.3)
        assert snap.spy_momentum_20d == pytest.approx(4.2)


class TestRegimeDefaults:
    def test_all_four_regimes_present(self):
        assert set(REGIME_DEFAULTS.keys()) == {"bull", "sideways", "bear", "high_vol"}

    def test_bull_highest_multiplier(self):
        assert REGIME_DEFAULTS["bull"] == max(REGIME_DEFAULTS.values())

    def test_high_vol_lowest_multiplier(self):
        assert REGIME_DEFAULTS["high_vol"] == min(REGIME_DEFAULTS.values())

    def test_multipliers_descending(self):
        order = ["bull", "sideways", "bear", "high_vol"]
        values = [REGIME_DEFAULTS[r] for r in order]
        assert values == sorted(values, reverse=True)
