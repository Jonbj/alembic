"""Test per #191: il ratchet di loss_feedback alza autonomamente il gate S4
sopra il baseline di design (0,30 → 0,45) e scarta il 93-97% dei segnali.
Per la durata della finestra di osservazione (#171) il tetto della leva deve
restare ancorato al baseline.

Perimetro: solo il ramo di innalzamento del threshold. Non si tocca
threshold_step, consecutive_loss_trigger, decay, regime_scale.

Copre anche la protezione del denominatore alla riga 458
(_format_feedback_stall_section): threshold_max == threshold_baseline non deve
sollevare ZeroDivisionError nel calcolo del signal_filter_pct.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.workers.performance import (
    _load_loss_feedback_config,
    _format_feedback_stall_section,
    run_loss_feedback_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(
    net_pnl: float,
    *,
    signal_id: int | None = None,
    exit_reason: str = "stop_loss",
    trade_id: int | None = None,
) -> dict:
    trade = {
        "net_pnl": net_pnl,
        "symbol": "AAPL",
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal_id,
        "entry_notional": 1000.0,
        "stop_d_init": 0.02,
        "exit_reason": exit_reason,
    }
    if trade_id is not None:
        trade["id"] = trade_id
    return trade


def _make_s4_triggering_trades(n_losses: int = 3) -> list[dict]:
    """Most-recent first: n_losses S4 losses then 2 wins."""
    losses = [_make_trade(-5, signal_id=123, trade_id=100 + i) for i in range(n_losses)]
    wins = [_make_trade(8, signal_id=123, trade_id=80 + i) for i in range(2)]
    return losses + wins


def _default_cfg() -> dict:
    return {
        "enabled": True,
        "consecutive_loss_trigger": 3,
        "threshold_step": 0.05,
        "threshold_max": 0.60,
        "threshold_baseline": 0.30,
        "threshold_decay_hours": 24,
        "regime_scale_factor": 0.80,
        "regime_min_scale": 0.20,
        "cooldown_hours": 4,
        "recovery_win_streak": 3,
        "feedback_ttl_hours": 48,
    }


def _patched_run(
    trades: list[dict],
    *,
    redis_threshold: float | None = 0.30,
    redis_scale: float | None = 1.0,
    redis_state: dict | None = None,
    cfg_override: dict | None = None,
    ttl_refresh_existed: bool = True,
):
    """Helper identico a quello in tests/workers/test_loss_feedback.py."""
    cfg = {**_default_cfg(), **(cfg_override or {})}

    mock_redis = MagicMock()
    mock_redis.get_feedback_entry_threshold.return_value = redis_threshold
    mock_redis.get_feedback_regime_scale.return_value = redis_scale
    mock_redis.get_feedback_state.return_value = redis_state
    mock_redis.refresh_feedback_ttl.return_value = ttl_refresh_existed

    mock_pg = MagicMock()
    mock_pg.fetch_trades.return_value = trades

    with (
        patch("src.workers.performance._load_loss_feedback_config", return_value=cfg),
        patch("src.workers.performance.RedisStore", return_value=mock_redis),
        patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg),
        patch("src.workers.performance.TelegramNotifier"),
        patch("src.workers.performance.run_async"),
    ):
        result = run_loss_feedback_check()

    return result, mock_redis


# ---------------------------------------------------------------------------
# Test 1: tetto del ratchet congelato al baseline (issue #191)
# ---------------------------------------------------------------------------

class TestThresholdRatchetFreeze:
    """Con `threshold_ratchet_enabled: false`, il ratchet non alza più
    l'entry threshold sopra il baseline di design."""

    def test_does_not_raise_above_baseline_after_multiple_triggers(self):
        """Tre trigger consecutivi in giorni separati: il threshold deve
        restare ancorato al baseline (0.30), NON salire a 0.35/0.40/0.45.

        Lo scenario è: trades che triggerano il ratchet, con cooldown già
        passato e nuovo evidence trade id (cioè tutto il resto del gate è
        verde). Senza il fix #191, il threshold salirebbe di threshold_step
        ad ogni trigger.
        """
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        trades = _make_s4_triggering_trades(n_losses=3)
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_scale=1.0,
            redis_state={
                "last_adjustment_ts": old_ts,
                "last_trigger_evidence_trade_id": 50,  # diverso da 100 -> non bloccato da stale-evidence
            },
            cfg_override={"threshold_ratchet_enabled": False},
        )

        s4 = result["per_strategy"]["S4"]
        # Il feedback ratchet NON si è applicato (flag spento).
        assert s4["adjusted"] is False, (
            "Con threshold_ratchet_enabled=false il ratchet non deve scrivere "
            "il threshold sopra il baseline"
        )
        assert s4.get("ratchet_frozen") is True, (
            "Il result deve esporre ratchet_frozen=True per ispezione"
        )
        # E NON deve aver chiamato Redis per alzare il threshold.
        for call in mock_redis.set_feedback_entry_threshold.call_args_list:
            # Se capita una scrittura, deve essere al baseline, non sopra.
            assert call.args[0] == pytest.approx(0.30), (
                f"Scrittura inattesa sopra il baseline: {call.args[0]}"
            )

    def test_flag_default_true_keeps_current_behavior(self):
        """Senza il flag (default True, retrocompatibilità) il ratchet
        continua ad alzare il threshold come prima — questo conferma che il
        fix è gated e non cambia il comportamento di default."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        trades = _make_s4_triggering_trades(n_losses=3)
        result, _ = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_scale=1.0,
            redis_state={
                "last_adjustment_ts": old_ts,
                "last_trigger_evidence_trade_id": 50,
            },
            # nessun cfg_override: threshold_ratchet_enabled resta al default
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["adjusted"] is True, (
            "Senza il flag il comportamento deve restare quello di prima"
        )
        assert s4["new_threshold"] == pytest.approx(0.35)

    def test_load_loss_feedback_config_default_is_true(self):
        """Il default del nuovo flag deve essere True per retrocompatibilità:
        chi non lo imposta in YAML continua a vedere il ratchet attivo."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            cfg = _load_loss_feedback_config()
        assert cfg.get("threshold_ratchet_enabled") is True, (
            "default retrocompatibile: ratchet attivo se non diversamente "
            "specificato in trading.yaml"
        )


# ---------------------------------------------------------------------------
# Test 2: protezione divisione riga 458 (display Telegram)
# ---------------------------------------------------------------------------

class TestSignalFilterPctDivisionGuard:
    """Quando threshold_max == threshold_baseline, il calcolo del signal_filter_pct
    in _format_feedback_stall_section (riga 458) non deve sollevare
    ZeroDivisionError."""

    def test_no_zero_division_when_max_equals_baseline(self):
        mock_redis = MagicMock()
        mock_redis.get_feedback_entry_threshold.return_value = 0.30
        mock_redis.get_feedback_regime_scale.return_value = 1.0
        mock_redis.get_feedback_state.return_value = {}

        # Patch il config di trading.yaml in modo che threshold_max == baseline
        cfg_yaml = {
            "loss_feedback": {
                "threshold_baseline": 0.30,
                "threshold_max": 0.30,  # == baseline (caso degenere)
                "recovery_win_streak": 3,
            }
        }
        with patch(
            "builtins.open",
            side_effect=lambda *a, **k: (_ for _ in ()).throw(
                FileNotFoundError if False else IOError("unused")
            ),
        ):
            # Patch più mirato: simuliamo la lettura YAML direttamente
            with patch("yaml.safe_load", return_value=cfg_yaml):
                section = _format_feedback_stall_section(mock_redis)

        # current_threshold == baseline => non si entra nel ramo 'is_elevated'
        assert "🔴" not in section
        assert "Normal" in section

    def test_no_zero_division_when_current_above_max_equals_baseline(self):
        """Caso specifico della issue: il display si attiva quando il current
        è elevato. Anche in quel caso, con max == baseline, niente
        ZeroDivisionError."""
        mock_redis = MagicMock()
        mock_redis.get_feedback_entry_threshold.return_value = 0.45  # sopra baseline
        mock_redis.get_feedback_regime_scale.return_value = 1.0
        mock_redis.get_feedback_state.return_value = {}

        cfg_yaml = {
            "loss_feedback": {
                "threshold_baseline": 0.30,
                "threshold_max": 0.30,  # == baseline
                "recovery_win_streak": 3,
            }
        }
        with patch("yaml.safe_load", return_value=cfg_yaml):
            section = _format_feedback_stall_section(mock_redis)

        # current è elevato ma la divisione satura a 100% (non explode)
        assert "🔴" in section
        assert "100%" in section
