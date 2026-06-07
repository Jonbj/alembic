"""Tests for postmortem wiring in the execution worker."""
from unittest.mock import MagicMock
from datetime import datetime, timezone


def _make_signal(score=0.45, confidence=0.55, ensemble_std=0.05,
                 generated_at="2026-06-05T14:00:00+00:00"):
    return {
        "score": score,
        "confidence": confidence,
        "ensemble_std": ensemble_std,
        "fallback_used": False,
        "generated_at": generated_at,
        "signal_id": 7,
    }


class TestMaybePostmortem:
    """_maybe_postmortem writes diagnosis when loss exceeds trigger threshold."""

    def test_writes_diagnosis_on_qualifying_loss(self):
        from src.workers.execution import _maybe_postmortem

        mock_pg = MagicMock()
        signal = _make_signal(score=0.55, confidence=0.35, ensemble_std=0.05)

        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=7,
            signal=signal,
            score=0.55,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=96.0,   # 4% loss — triggers postmortem
            tick_time=datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc),
        )

        mock_pg.write_postmortem.assert_called_once()
        call_args = mock_pg.write_postmortem.call_args[0]
        assert call_args[0] == 7                    # trade_id
        assert isinstance(call_args[1], str)        # diagnosis string

    def test_skips_diagnosis_on_small_loss(self):
        from src.workers.execution import _maybe_postmortem

        mock_pg = MagicMock()
        signal = _make_signal(score=0.45, confidence=0.6, ensemble_std=0.05)

        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=8,
            signal=signal,
            score=0.45,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=99.5,  # 0.5% loss — below all thresholds
            tick_time=datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc),
        )

        mock_pg.write_postmortem.assert_not_called()

    def test_handles_write_postmortem_exception_silently(self):
        from src.workers.execution import _maybe_postmortem

        mock_pg = MagicMock()
        mock_pg.write_postmortem.side_effect = Exception("DB error")
        signal = _make_signal(score=0.55, confidence=0.35)

        # Must not raise
        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=9,
            signal=signal,
            score=0.55,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=96.0,
            tick_time=datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc),
        )

    def test_overnight_gap_detected_when_entry_time_yesterday(self):
        from src.workers.execution import _maybe_postmortem
        from src.performance.postmortem import TradeContext

        mock_pg = MagicMock()
        signal = _make_signal(score=0.55, confidence=0.35, ensemble_std=0.05)

        entry_time = datetime(2026, 6, 4, 19, 0, tzinfo=timezone.utc)   # yesterday
        tick_time = datetime(2026, 6, 5, 14, 15, tzinfo=timezone.utc)   # today (next morning)

        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=10,
            signal=signal,
            score=0.55,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=92.0,   # 8% gap — triggers postmortem
            tick_time=tick_time,
            entry_time=entry_time,
        )

        mock_pg.write_postmortem.assert_called_once()
        trade_id_arg, diagnosis_str = mock_pg.write_postmortem.call_args[0]
        # was_overnight_gap=True should route to "market_gap" diagnosis
        assert "market_gap" in diagnosis_str

    def test_overnight_gap_not_set_for_same_day_trade(self):
        from src.workers.execution import _maybe_postmortem

        mock_pg = MagicMock()
        signal = _make_signal(score=0.55, confidence=0.35, ensemble_std=0.05)

        entry_time = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)   # same day
        tick_time = datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc)   # same day

        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=11,
            signal=signal,
            score=0.55,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=96.0,
            tick_time=tick_time,
            entry_time=entry_time,
        )

        mock_pg.write_postmortem.assert_called_once()
        _, diagnosis_str = mock_pg.write_postmortem.call_args[0]
        # Same-day trade must NOT be diagnosed as market_gap
        assert "market_gap" not in diagnosis_str


class TestRegimeLabel:
    def test_regime_label_mapping(self):
        from src.workers.execution import _regime_label
        assert _regime_label(0.2) == "high_vol"
        assert _regime_label(0.3) == "high_vol"   # boundary
        assert _regime_label(0.5) == "risk_off"
        assert _regime_label(0.6) == "risk_off"   # boundary
        assert _regime_label(0.75) == "uncertain"
        assert _regime_label(0.9) == "uncertain"  # boundary
        assert _regime_label(1.0) == "risk_on"
        assert _regime_label(1.2) == "risk_on"
        assert _regime_label(1.5) == "risk_on"
