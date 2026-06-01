"""T-306: S2 regime modulation overlay."""
from __future__ import annotations

from datetime import date, timedelta
from math import floor
from typing import Optional

import pytest

from src.strategies.s2.config import S2Config
from src.strategies.s2.regime import RegimeModulation, apply_regime_scale, modulate_by_regime
from src.strategies.s2.signal import PutSignal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRADE_DATE = date(2023, 3, 20)
_EXPIRY = _TRADE_DATE + timedelta(days=35)
_STRIKE = 430.0
_MID = 5.0


def _signal(quantity: int = 4) -> PutSignal:
    return PutSignal(
        symbol="SPY",
        trade_date=_TRADE_DATE,
        expiry=_EXPIRY,
        strike=_STRIKE,
        right="P",
        delta=-0.20,
        implied_vol=0.18,
        mid=_MID,
        quantity=quantity,
        collateral=_STRIKE * quantity * 100,
        vrp=0.03,
    )


# ---------------------------------------------------------------------------
# RegimeModulation dataclass
# ---------------------------------------------------------------------------


class TestRegimeModulationDataclass:
    def test_has_regime_field(self) -> None:
        m = RegimeModulation(regime="bull", position_scale=1.0, reason="test")
        assert m.regime == "bull"

    def test_has_position_scale_field(self) -> None:
        m = RegimeModulation(regime="sideways", position_scale=0.75, reason="test")
        assert m.position_scale == 0.75

    def test_has_reason_field(self) -> None:
        m = RegimeModulation(regime="bear", position_scale=0.25, reason="high risk")
        assert m.reason == "high risk"


# ---------------------------------------------------------------------------
# S2Config regime_scales defaults
# ---------------------------------------------------------------------------


class TestS2ConfigRegimeScalesDefaults:
    def test_default_bull_scale(self) -> None:
        assert S2Config().regime_scales["bull"] == 1.0

    def test_default_sideways_scale(self) -> None:
        assert S2Config().regime_scales["sideways"] == 0.75

    def test_default_bear_scale(self) -> None:
        assert S2Config().regime_scales["bear"] == 0.25

    def test_default_high_vol_scale(self) -> None:
        assert S2Config().regime_scales["high_vol"] == 0.0


# ---------------------------------------------------------------------------
# modulate_by_regime — default scales
# ---------------------------------------------------------------------------


class TestModulateByRegimeDefaults:
    def test_bull_returns_regime_modulation(self) -> None:
        result = modulate_by_regime("bull")
        assert isinstance(result, RegimeModulation)

    def test_bull_scale_is_one(self) -> None:
        result = modulate_by_regime("bull")
        assert result.position_scale == 1.0

    def test_sideways_scale_is_0_75(self) -> None:
        result = modulate_by_regime("sideways")
        assert result.position_scale == 0.75

    def test_bear_scale_is_0_25(self) -> None:
        result = modulate_by_regime("bear")
        assert result.position_scale == 0.25

    def test_high_vol_scale_is_zero(self) -> None:
        result = modulate_by_regime("high_vol")
        assert result.position_scale == 0.0

    def test_bull_regime_label_preserved(self) -> None:
        result = modulate_by_regime("bull")
        assert result.regime == "bull"

    def test_bear_regime_label_preserved(self) -> None:
        result = modulate_by_regime("bear")
        assert result.regime == "bear"

    def test_all_regimes_have_nonempty_reason(self) -> None:
        for regime in ("bull", "sideways", "bear", "high_vol"):
            result = modulate_by_regime(regime)  # type: ignore[arg-type]
            assert result.reason, f"Empty reason for regime={regime}"


# ---------------------------------------------------------------------------
# modulate_by_regime — custom config overrides defaults
# ---------------------------------------------------------------------------


class TestModulateByRegimeCustomConfig:
    def test_custom_bull_scale_overrides_default(self) -> None:
        cfg = S2Config(regime_scales={"bull": 0.80, "sideways": 0.75, "bear": 0.25, "high_vol": 0.0})
        result = modulate_by_regime("bull", config=cfg)
        assert result.position_scale == 0.80

    def test_custom_sideways_scale_overrides_default(self) -> None:
        cfg = S2Config(regime_scales={"bull": 1.0, "sideways": 0.50, "bear": 0.25, "high_vol": 0.0})
        result = modulate_by_regime("sideways", config=cfg)
        assert result.position_scale == 0.50

    def test_custom_bear_scale_overrides_default(self) -> None:
        cfg = S2Config(regime_scales={"bull": 1.0, "sideways": 0.75, "bear": 0.10, "high_vol": 0.0})
        result = modulate_by_regime("bear", config=cfg)
        assert result.position_scale == 0.10

    def test_custom_high_vol_scale_overrides_default(self) -> None:
        cfg = S2Config(regime_scales={"bull": 1.0, "sideways": 0.75, "bear": 0.25, "high_vol": 0.50})
        result = modulate_by_regime("high_vol", config=cfg)
        assert result.position_scale == 0.50


# ---------------------------------------------------------------------------
# apply_regime_scale
# ---------------------------------------------------------------------------


class TestApplyRegimeScaleHighVol:
    def test_returns_none_when_scale_is_zero(self) -> None:
        sig = _signal(quantity=10)
        mod = modulate_by_regime("high_vol")
        assert apply_regime_scale(sig, mod) is None

    def test_returns_none_regardless_of_quantity_when_scale_zero(self) -> None:
        sig = _signal(quantity=100)
        mod = RegimeModulation(regime="high_vol", position_scale=0.0, reason="test")
        assert apply_regime_scale(sig, mod) is None


class TestApplyRegimeScaleBull:
    def test_bull_full_scale_preserves_quantity(self) -> None:
        sig = _signal(quantity=4)
        mod = modulate_by_regime("bull")
        result = apply_regime_scale(sig, mod)
        assert result is not None
        assert result.quantity == 4

    def test_bull_full_scale_returns_put_signal(self) -> None:
        sig = _signal(quantity=3)
        mod = modulate_by_regime("bull")
        result = apply_regime_scale(sig, mod)
        assert isinstance(result, PutSignal)

    def test_bull_preserves_non_quantity_fields(self) -> None:
        sig = _signal(quantity=2)
        mod = modulate_by_regime("bull")
        result = apply_regime_scale(sig, mod)
        assert result is not None
        assert result.symbol == sig.symbol
        assert result.strike == sig.strike
        assert result.delta == sig.delta
        assert result.mid == sig.mid


class TestApplyRegimeScaleSideways:
    def test_sideways_reduces_quantity_proportionally(self) -> None:
        sig = _signal(quantity=4)
        mod = modulate_by_regime("sideways")  # scale=0.75
        result = apply_regime_scale(sig, mod)
        assert result is not None
        assert result.quantity == floor(4 * 0.75)  # 3

    def test_sideways_qty_1_returns_signal_quantity_1(self) -> None:
        sig = _signal(quantity=1)
        mod = modulate_by_regime("sideways")  # floor(1 * 0.75) = 0 → None
        result = apply_regime_scale(sig, mod)
        assert result is None

    def test_sideways_qty_4_collateral_updated(self) -> None:
        sig = _signal(quantity=4)
        mod = modulate_by_regime("sideways")
        result = apply_regime_scale(sig, mod)
        assert result is not None
        expected_qty = floor(4 * 0.75)
        assert abs(result.collateral - _STRIKE * expected_qty * 100) < 1e-6


class TestApplyRegimeScaleBear:
    def test_bear_reduces_quantity_proportionally(self) -> None:
        sig = _signal(quantity=8)
        mod = modulate_by_regime("bear")  # scale=0.25
        result = apply_regime_scale(sig, mod)
        assert result is not None
        assert result.quantity == floor(8 * 0.25)  # 2

    def test_bear_qty_1_returns_none_scaled_below_1(self) -> None:
        sig = _signal(quantity=1)
        mod = modulate_by_regime("bear")  # floor(1*0.25)=0 → None
        result = apply_regime_scale(sig, mod)
        assert result is None

    def test_bear_qty_3_returns_none_scaled_below_1(self) -> None:
        sig = _signal(quantity=3)
        mod = modulate_by_regime("bear")  # floor(3*0.25)=0 → None
        result = apply_regime_scale(sig, mod)
        assert result is None

    def test_bear_qty_4_returns_signal(self) -> None:
        sig = _signal(quantity=4)
        mod = modulate_by_regime("bear")  # floor(4*0.25)=1
        result = apply_regime_scale(sig, mod)
        assert result is not None
        assert result.quantity == 1


class TestApplyRegimeScaleEdgeCases:
    def test_scaled_quantity_below_one_returns_none(self) -> None:
        sig = _signal(quantity=1)
        mod = RegimeModulation(regime="bear", position_scale=0.25, reason="test")
        result = apply_regime_scale(sig, mod)
        assert result is None

    def test_scaled_quantity_exactly_one_returns_signal(self) -> None:
        sig = _signal(quantity=4)
        mod = RegimeModulation(regime="bear", position_scale=0.25, reason="test")
        result = apply_regime_scale(sig, mod)
        assert result is not None
        assert result.quantity == 1

    def test_floor_applied_to_scaled_quantity(self) -> None:
        """scale=0.5, qty=3 → floor(1.5)=1 (not 2)."""
        sig = _signal(quantity=3)
        mod = RegimeModulation(regime="sideways", position_scale=0.5, reason="test")
        result = apply_regime_scale(sig, mod)
        assert result is not None
        assert result.quantity == 1
