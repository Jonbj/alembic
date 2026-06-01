"""T-305: S2 exit logic — target profit, stop loss, time decay, signal flip."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pytest

from src.strategies.s2.config import S2Config
from src.strategies.s2.exit import (
    ExitReason,
    ExitSignal,
    compute_pnl,
    evaluate_exit,
)
from src.strategies.s2.signal import PutSignal

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_TRADE_DATE = date(2023, 3, 20)
_EXPIRY_30 = _TRADE_DATE + timedelta(days=30)
_STRIKE = 430.0
_MID = 5.0
_QTY = 1
_IV = 0.18
_RV = 0.15


def _signal(
    *,
    trade_date: date = _TRADE_DATE,
    expiry: date = _EXPIRY_30,
    strike: float = _STRIKE,
    mid: float = _MID,
    quantity: int = _QTY,
    implied_vol: float = _IV,
    vrp: Optional[float] = 0.03,
) -> PutSignal:
    return PutSignal(
        symbol="SPY",
        trade_date=trade_date,
        expiry=expiry,
        strike=strike,
        right="P",
        delta=-0.20,
        implied_vol=implied_vol,
        mid=mid,
        quantity=quantity,
        collateral=strike * quantity * 100,
        vrp=vrp,
    )


# ---------------------------------------------------------------------------
# ExitReason enum
# ---------------------------------------------------------------------------


class TestExitReasonEnum:
    def test_has_target_profit(self) -> None:
        assert ExitReason.TARGET_PROFIT is not None

    def test_has_stop_loss(self) -> None:
        assert ExitReason.STOP_LOSS is not None

    def test_has_time_decay(self) -> None:
        assert ExitReason.TIME_DECAY is not None

    def test_has_signal_flip(self) -> None:
        assert ExitReason.SIGNAL_FLIP is not None

    def test_has_expiry(self) -> None:
        assert ExitReason.EXPIRY is not None

    def test_all_reasons_distinct(self) -> None:
        reasons = [
            ExitReason.TARGET_PROFIT,
            ExitReason.STOP_LOSS,
            ExitReason.TIME_DECAY,
            ExitReason.SIGNAL_FLIP,
            ExitReason.EXPIRY,
        ]
        assert len(set(reasons)) == 5


# ---------------------------------------------------------------------------
# ExitSignal dataclass
# ---------------------------------------------------------------------------


class TestExitSignalDataclass:
    def test_has_required_fields(self) -> None:
        es = ExitSignal(
            reason=ExitReason.TARGET_PROFIT,
            exit_date=date(2023, 4, 1),
            pnl=250.0,
        )
        assert es.reason == ExitReason.TARGET_PROFIT
        assert es.exit_date == date(2023, 4, 1)
        assert es.pnl == 250.0

    def test_reason_is_exit_reason_enum(self) -> None:
        es = ExitSignal(reason=ExitReason.STOP_LOSS, exit_date=date(2023, 4, 1), pnl=-300.0)
        assert isinstance(es.reason, ExitReason)


# ---------------------------------------------------------------------------
# compute_pnl
# ---------------------------------------------------------------------------


class TestComputePnl:
    def test_profit_when_premium_decays(self) -> None:
        """Sold at 5.0, now at 2.5 → 50% of premium captured."""
        sig = _signal(mid=5.0, quantity=1)
        assert abs(compute_pnl(sig, current_mid=2.5) - 250.0) < 1e-6

    def test_loss_when_premium_expands(self) -> None:
        """Sold at 5.0, now at 15.0 → 2× loss."""
        sig = _signal(mid=5.0, quantity=1)
        assert abs(compute_pnl(sig, current_mid=15.0) - (-1000.0)) < 1e-6

    def test_breakeven_when_mid_unchanged(self) -> None:
        sig = _signal(mid=5.0, quantity=1)
        assert abs(compute_pnl(sig, current_mid=5.0)) < 1e-6

    def test_scales_with_quantity(self) -> None:
        sig1 = _signal(mid=5.0, quantity=1)
        sig2 = _signal(mid=5.0, quantity=2)
        pnl1 = compute_pnl(sig1, current_mid=2.5)
        pnl2 = compute_pnl(sig2, current_mid=2.5)
        assert abs(pnl2 - 2 * pnl1) < 1e-6

    def test_zero_current_mid_full_premium_captured(self) -> None:
        sig = _signal(mid=5.0, quantity=1)
        assert abs(compute_pnl(sig, current_mid=0.0) - 500.0) < 1e-6

    def test_uses_multiplier_100(self) -> None:
        sig = _signal(mid=1.0, quantity=1)
        assert abs(compute_pnl(sig, current_mid=0.0) - 100.0) < 1e-6


# ---------------------------------------------------------------------------
# S2Config exit-related defaults
# ---------------------------------------------------------------------------


class TestS2ConfigExitDefaults:
    def test_default_profit_target_pct(self) -> None:
        assert S2Config().profit_target_pct == 0.50

    def test_default_stop_loss_multiplier(self) -> None:
        assert S2Config().stop_loss_multiplier == 2.0

    def test_default_underlying_stop_loss_pct(self) -> None:
        assert S2Config().underlying_stop_loss_pct == 0.05

    def test_default_min_dte_exit(self) -> None:
        assert S2Config().min_dte_exit == 7

    def test_default_force_close_dte(self) -> None:
        assert S2Config().force_close_dte == 2


# ---------------------------------------------------------------------------
# evaluate_exit — no exit
# ---------------------------------------------------------------------------


class TestEvaluateExitNoExit:
    def test_returns_none_when_no_condition_met(self) -> None:
        """DTE=20, 20% captured, VRP positive: no exit."""
        sig = _signal(expiry=_TRADE_DATE + timedelta(days=20), mid=5.0)
        # current_date → DTE=8: > force_close=2, ≥ min_dte=7
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=12),
            current_mid=4.0,  # 20% captured < 50%
            implied_vol=0.18,
            realized_vol=0.15,
        )
        assert result is None

    def test_returns_none_type_with_default_config(self) -> None:
        sig = _signal(expiry=_TRADE_DATE + timedelta(days=30))
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=5),
            current_mid=4.0,
            implied_vol=0.18,
            realized_vol=0.15,
        )
        assert result is None


# ---------------------------------------------------------------------------
# evaluate_exit — forced expiry (DTE <= force_close_dte)
# ---------------------------------------------------------------------------


class TestForcedExpiryExit:
    def test_fires_when_dte_equals_force_close_dte(self) -> None:
        expiry = _TRADE_DATE + timedelta(days=15)
        current_date = expiry - timedelta(days=2)  # DTE=2
        result = evaluate_exit(
            signal=_signal(expiry=expiry),
            current_price=450.0,
            current_date=current_date,
            current_mid=1.0,
        )
        assert result is not None
        assert result.reason == ExitReason.EXPIRY

    def test_fires_when_dte_below_force_close_dte(self) -> None:
        expiry = _TRADE_DATE + timedelta(days=15)
        current_date = expiry - timedelta(days=1)  # DTE=1 < 2
        result = evaluate_exit(
            signal=_signal(expiry=expiry),
            current_price=450.0,
            current_date=current_date,
            current_mid=1.0,
        )
        assert result is not None
        assert result.reason == ExitReason.EXPIRY

    def test_does_not_fire_when_dte_above_force_close_dte(self) -> None:
        expiry = _TRADE_DATE + timedelta(days=30)
        # DTE=27: above force_close=2, so EXPIRY does not fire
        result = evaluate_exit(
            signal=_signal(expiry=expiry),
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=3),
            current_mid=4.5,  # 10% captured
            implied_vol=0.18,
            realized_vol=0.15,
        )
        if result is not None:
            assert result.reason != ExitReason.EXPIRY

    def test_expiry_exit_returns_exit_signal_instance(self) -> None:
        expiry = _TRADE_DATE + timedelta(days=10)
        current_date = expiry - timedelta(days=2)
        result = evaluate_exit(
            signal=_signal(expiry=expiry),
            current_price=450.0,
            current_date=current_date,
            current_mid=1.0,
        )
        assert isinstance(result, ExitSignal)
        assert result.exit_date == current_date

    def test_expiry_exit_pnl_correct(self) -> None:
        expiry = _TRADE_DATE + timedelta(days=10)
        current_date = expiry - timedelta(days=1)
        sig = _signal(expiry=expiry, mid=5.0, quantity=1)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=1.0,
        )
        assert result is not None
        # P&L = (5.0 - 1.0) * 1 * 100 = 400
        assert abs(result.pnl - 400.0) < 1e-6


# ---------------------------------------------------------------------------
# evaluate_exit — stop loss
# ---------------------------------------------------------------------------


class TestStopLossExit:
    def test_fires_when_loss_exceeds_2x_premium(self) -> None:
        """Loss > 2× initial premium → STOP_LOSS."""
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        # current_mid=15.01 → pnl=-1001 < -2*500=-1000
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=5),
            current_mid=15.01,
        )
        assert result is not None
        assert result.reason == ExitReason.STOP_LOSS

    def test_no_stop_loss_when_loss_exactly_2x(self) -> None:
        """Exactly at 2× boundary: must NOT trigger (strict > comparison)."""
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        # pnl=-1000.0, threshold=-1000.0 → not strictly less than
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=5),
            current_mid=15.0,
        )
        if result is not None:
            assert result.reason != ExitReason.STOP_LOSS

    def test_fires_when_underlying_drops_more_than_5pct(self) -> None:
        """6% underlying drop with entry_price provided → STOP_LOSS."""
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        entry_price = 450.0
        result = evaluate_exit(
            signal=sig,
            current_price=entry_price * 0.94,  # 6% drop
            current_date=_TRADE_DATE + timedelta(days=5),
            current_mid=6.0,
            entry_price=entry_price,
        )
        assert result is not None
        assert result.reason == ExitReason.STOP_LOSS

    def test_no_stop_loss_when_underlying_drop_is_small(self) -> None:
        """2% drop → below 5% threshold, no stop loss."""
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        entry_price = 450.0
        result = evaluate_exit(
            signal=sig,
            current_price=entry_price * 0.98,  # 2% drop
            current_date=_TRADE_DATE + timedelta(days=5),
            current_mid=5.5,
            entry_price=entry_price,
        )
        assert result is None

    def test_stop_loss_pnl_is_negative(self) -> None:
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=5),
            current_mid=15.01,
        )
        assert result is not None
        assert result.pnl < 0

    def test_stop_loss_exit_date_is_current_date(self) -> None:
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        current_date = _TRADE_DATE + timedelta(days=5)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=15.01,
        )
        assert result is not None
        assert result.exit_date == current_date


# ---------------------------------------------------------------------------
# evaluate_exit — target profit
# ---------------------------------------------------------------------------


class TestTargetProfitExit:
    def test_fires_when_50_pct_of_premium_captured(self) -> None:
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        # current_mid=2.5 → (5.0-2.5)/5.0 = 0.5 = 50%
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=2.5,
        )
        assert result is not None
        assert result.reason == ExitReason.TARGET_PROFIT

    def test_fires_when_more_than_50_pct_captured(self) -> None:
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=1.0,  # 80% captured
        )
        assert result is not None
        assert result.reason == ExitReason.TARGET_PROFIT

    def test_no_target_profit_when_below_threshold(self) -> None:
        """49% captured → no target profit exit."""
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        # (5.0-2.55)/5.0 = 0.49
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=2.55,
        )
        if result is not None:
            assert result.reason != ExitReason.TARGET_PROFIT

    def test_target_profit_pnl_positive(self) -> None:
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=2.5,
        )
        assert result is not None
        assert result.pnl > 0

    def test_target_profit_exit_date_is_current_date(self) -> None:
        sig = _signal(mid=5.0, quantity=1, expiry=_TRADE_DATE + timedelta(days=30))
        current_date = _TRADE_DATE + timedelta(days=10)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=2.5,
        )
        assert result is not None
        assert result.exit_date == current_date


# ---------------------------------------------------------------------------
# evaluate_exit — time decay (DTE < min_dte_exit)
# ---------------------------------------------------------------------------


class TestTimeDecayExit:
    def test_fires_when_dte_below_min_dte_exit(self) -> None:
        """DTE=6 < min_dte_exit=7 → TIME_DECAY."""
        expiry = _TRADE_DATE + timedelta(days=20)
        current_date = expiry - timedelta(days=6)  # DTE=6
        sig = _signal(expiry=expiry, mid=5.0, quantity=1)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=4.0,  # 20% captured, not 50%
        )
        assert result is not None
        assert result.reason == ExitReason.TIME_DECAY

    def test_no_time_decay_at_boundary(self) -> None:
        """DTE = min_dte_exit=7: strict < comparison, boundary does NOT fire."""
        expiry = _TRADE_DATE + timedelta(days=20)
        current_date = expiry - timedelta(days=7)  # DTE=7
        sig = _signal(expiry=expiry, mid=5.0)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=4.5,  # 10% captured
            implied_vol=0.18,
            realized_vol=0.15,
        )
        if result is not None:
            assert result.reason != ExitReason.TIME_DECAY

    def test_no_time_decay_far_from_expiry(self) -> None:
        """DTE=20 → no time decay."""
        expiry = _TRADE_DATE + timedelta(days=40)
        sig = _signal(expiry=expiry, mid=5.0)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=20),  # DTE=20
            current_mid=4.5,
        )
        assert result is None


# ---------------------------------------------------------------------------
# evaluate_exit — signal flip (VRP < 0)
# ---------------------------------------------------------------------------


class TestSignalFlipExit:
    def test_fires_when_vrp_negative(self) -> None:
        """implied_vol < realized_vol → VRP < 0 → SIGNAL_FLIP."""
        sig = _signal(expiry=_TRADE_DATE + timedelta(days=30), mid=5.0)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=4.5,
            implied_vol=0.15,
            realized_vol=0.20,  # realized > implied
        )
        assert result is not None
        assert result.reason == ExitReason.SIGNAL_FLIP

    def test_no_signal_flip_when_vrp_positive(self) -> None:
        sig = _signal(expiry=_TRADE_DATE + timedelta(days=30), mid=5.0)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=4.5,
            implied_vol=0.20,
            realized_vol=0.15,
        )
        assert result is None

    def test_no_signal_flip_when_vrp_zero(self) -> None:
        sig = _signal(expiry=_TRADE_DATE + timedelta(days=30), mid=5.0)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=4.5,
            implied_vol=0.18,
            realized_vol=0.18,
        )
        assert result is None

    def test_no_signal_flip_when_realized_vol_not_provided(self) -> None:
        """Without realized_vol the VRP check is skipped."""
        sig = _signal(expiry=_TRADE_DATE + timedelta(days=30), mid=5.0)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=4.5,
            implied_vol=0.10,
            realized_vol=None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# evaluate_exit — priority: EXPIRY > STOP_LOSS > TARGET_PROFIT > TIME_DECAY > SIGNAL_FLIP
# ---------------------------------------------------------------------------


class TestExitPriority:
    def test_forced_expiry_beats_stop_loss(self) -> None:
        expiry = _TRADE_DATE + timedelta(days=10)
        current_date = expiry - timedelta(days=1)  # DTE=1 → EXPIRY
        sig = _signal(expiry=expiry, mid=5.0, quantity=1)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=15.01,  # also triggers STOP_LOSS
        )
        assert result is not None
        assert result.reason == ExitReason.EXPIRY

    def test_forced_expiry_beats_target_profit(self) -> None:
        expiry = _TRADE_DATE + timedelta(days=10)
        current_date = expiry - timedelta(days=1)  # DTE=1 → EXPIRY
        sig = _signal(expiry=expiry, mid=5.0, quantity=1)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=2.5,  # also triggers TARGET_PROFIT
        )
        assert result is not None
        assert result.reason == ExitReason.EXPIRY

    def test_stop_loss_beats_target_profit(self) -> None:
        """Underlying drop (STOP_LOSS) + 50% captured (TARGET_PROFIT): STOP_LOSS wins."""
        expiry = _TRADE_DATE + timedelta(days=30)
        sig = _signal(expiry=expiry, mid=5.0, quantity=1)
        entry_price = 450.0
        result = evaluate_exit(
            signal=sig,
            current_price=entry_price * 0.94,  # 6% drop → STOP_LOSS
            current_date=_TRADE_DATE + timedelta(days=5),
            current_mid=2.5,  # also TARGET_PROFIT
            entry_price=entry_price,
        )
        assert result is not None
        assert result.reason == ExitReason.STOP_LOSS

    def test_target_profit_beats_time_decay(self) -> None:
        """DTE=6 (<7) + 50% captured: TARGET_PROFIT wins."""
        expiry = _TRADE_DATE + timedelta(days=20)
        current_date = expiry - timedelta(days=6)  # DTE=6 → TIME_DECAY
        sig = _signal(expiry=expiry, mid=5.0, quantity=1)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=2.5,  # also TARGET_PROFIT
        )
        assert result is not None
        assert result.reason == ExitReason.TARGET_PROFIT

    def test_time_decay_beats_signal_flip(self) -> None:
        """DTE=6 (<7) + VRP<0: TIME_DECAY wins."""
        expiry = _TRADE_DATE + timedelta(days=20)
        current_date = expiry - timedelta(days=6)  # DTE=6 → TIME_DECAY
        sig = _signal(expiry=expiry, mid=5.0, quantity=1)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=current_date,
            current_mid=4.5,  # 10% captured, no target profit
            implied_vol=0.15,
            realized_vol=0.20,  # also SIGNAL_FLIP
        )
        assert result is not None
        assert result.reason == ExitReason.TIME_DECAY

    def test_signal_flip_fires_last_when_only_condition(self) -> None:
        """Signal flip fires when it is the only condition met."""
        sig = _signal(expiry=_TRADE_DATE + timedelta(days=30), mid=5.0, quantity=1)
        result = evaluate_exit(
            signal=sig,
            current_price=450.0,
            current_date=_TRADE_DATE + timedelta(days=10),
            current_mid=4.5,  # only 10% captured
            implied_vol=0.14,
            realized_vol=0.20,
        )
        assert result is not None
        assert result.reason == ExitReason.SIGNAL_FLIP
