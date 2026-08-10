"""Test per #191: il ratchet di loss_feedback alza autonomamente l'entry
threshold di S4 sopra il baseline di design (0,30 → 0,45) e scarta il 93-97%
dei segnali. Per la durata della finestra di osservazione (#171) l'innalzamento
della soglia deve essere congelabile, senza però spegnere il resto del ramo di
trigger (regime_scale, stato, S1).

Terzo tentativo. Le PR #205 e #215 furono entrambe respinte; la decisione
operatore del 2026-08-10 (commento alla issue) fissa il perimetro e vince sul
testo originale. I tre requisiti:

1. **Il flag congela solo l'innalzamento della soglia.** Non deve spegnere
   `regime_scale` (S4 e S1) né lo stato: #205 intercettava l'intero ramo di
   trigger.
2. **Una soglia già a 0,45 torna al baseline 0,30.** #205 non riscriveva 0,30
   e, sotto trigger persistente, nemmeno il decay interveniva — il log
   dichiarava "stays at baseline" mentre la produzione restava a 0,45. Il test
   di #205 partiva sempre dal baseline e non copriva il caso reale: qui i test
   partono da 0,45.
3. **Il flag è attivo alla consegna.** #215 spediva `threshold_ratchet_enabled:
   true` (= ratchet attivo): dopo il redeploy il ratchet continuava ad alzare.
   Il default in codice e il valore in `config/trading.yaml` devono entrambi
   risultare nello stato che **congela l'innalzamento**, senza richiedere azione
   manuale post-merge. È l'esecuzione della deroga al freeze #171 già
   approvata nel corpo della issue, non una nuova taratura.

Perimetro del flag: solo il ramo di innalzamento del threshold. Non si tocca
threshold_step, consecutive_loss_trigger, threshold_decay_hours, regime_scale_*
e il ramo regime_scale, che restano vivi. L'innalzamento resta disponibile come
opt-in esplicito (`threshold_ratchet_enabled: true`) — i regression test qui
sotto ne verificano il funzionamento storico.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.workers.performance import (
    _load_loss_feedback_config,
    run_loss_feedback_check,
)


# ---------------------------------------------------------------------------
# Helpers (allineati a tests/workers/test_loss_feedback.py)
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


def _s4_triggering_trades(n_losses: int = 3) -> list[dict]:
    """Most-recent first: n_losses S4 losses then 2 wins."""
    losses = [_make_trade(-5, signal_id=123, trade_id=100 + i) for i in range(n_losses)]
    wins = [_make_trade(8, signal_id=123, trade_id=80 + i) for i in range(2)]
    return losses + wins


def _default_cfg() -> dict:
    """Config senza il flag: modella lo stato di consegna (default congelato).
    Il codice risolve il flag mancante con il default False = congelato."""
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
):
    cfg = {**_default_cfg(), **(cfg_override or {})}

    mock_redis = MagicMock()
    mock_redis.get_feedback_entry_threshold.return_value = redis_threshold
    mock_redis.get_feedback_regime_scale.return_value = redis_scale
    mock_redis.get_feedback_state.return_value = redis_state
    mock_redis.refresh_feedback_ttl.return_value = True

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


def _old_state(evidence_id: int = 50) -> dict:
    """Modella il pre-freeze: la soglia era già stata alzata a 0,45 da un
    trigger precedente. last_adjustment_ts abbastanza vecchio da passare il
    cooldown, con un evidence trade id diverso da quello dei trade correnti
    (100+) così lo stale-evidence guard non blocca il trigger."""
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    return {
        "last_adjustment_ts": old_ts,
        "last_trigger_evidence_trade_id": evidence_id,
        "threshold_after": 0.45,
    }


# ---------------------------------------------------------------------------
# Requisito #2 + #3: soglia già a 0,45 torna al baseline, flag congelato
# ---------------------------------------------------------------------------

class TestFrozenPullsElevatedThresholdBackToBaseline:
    """Il caso reale della issue: Redis ha la soglia a 0,45 (innalzata prima del
    freeze), il flag è nello stato di consegna (congelato). Il worker deve
    riscrivere 0,30 — non lasciarla a 0,45 e nemmeno salire a 0,50."""

    def test_new_threshold_is_baseline_not_050(self):
        trades = _s4_triggering_trades(n_losses=3)
        result, _ = _patched_run(
            trades,
            redis_threshold=0.45,          # <-- parte da 0,45, non da 0,30
            redis_scale=0.80,
            redis_state=_old_state(),
            # nessun cfg_override: flag al default congelato
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["new_threshold"] == pytest.approx(0.30), (
            "Con il ratchet congelato la soglia deve tornare al baseline 0.30, "
            f"non restare a 0.45 né salire a 0.50 — ottenuto {s4['new_threshold']}"
        )

    def test_baseline_is_written_to_redis(self):
        """Il difetto #2: la produzione resta a 0,45 perché il worker non
        riscrive 0,30. Qui verifichiamo che set_feedback_entry_threshold viene
        chiamato con 0.30 (e strategy=S4)."""
        trades = _s4_triggering_trades(n_losses=3)
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.45,
            redis_scale=0.80,
            redis_state=_old_state(),
        )

        assert result["per_strategy"]["S4"]["adjusted"] is True, (
            "Il ramo di trigger deve comunque girare (riscrive la soglia al "
            "baseline e aggiorna lo scale); non è un no-op"
        )
        mock_redis.set_feedback_entry_threshold.assert_called_once()
        written_threshold = mock_redis.set_feedback_entry_threshold.call_args.args[0]
        assert written_threshold == pytest.approx(0.30), (
            f"Redis deve ricevere 0.30, non {written_threshold} — altrimenti la "
            "produzione resta bloccata al valore pre-freeze"
        )
        assert mock_redis.set_feedback_entry_threshold.call_args.kwargs.get("strategy") == "S4"

    def test_ratchet_frozen_marker_exposed(self):
        """Il result espone ratchet_frozen=True per ispezione (report/Telegram)."""
        trades = _s4_triggering_trades(n_losses=3)
        result, _ = _patched_run(
            trades,
            redis_threshold=0.45,
            redis_scale=0.80,
            redis_state=_old_state(),
        )
        assert result["per_strategy"]["S4"].get("ratchet_frozen") is True

    def test_threshold_does_not_re_raise_on_second_trigger(self):
        """Dopo il pullback al baseline, un ulteriore trigger non fa risalire la
        soglia finché il flag resta congelato: la finestra misura la strategia,
        non la leva."""
        trades = _s4_triggering_trades(n_losses=3)
        # Primo trigger: 0,45 → 0,30 (pullback).
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.45,
            redis_scale=0.80,
            redis_state=_old_state(),
        )
        assert result["per_strategy"]["S4"]["new_threshold"] == pytest.approx(0.30)

        # Secondo trigger partendo dal baseline appena scritto: resta a 0,30.
        result2, mock_redis2 = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_scale=0.80,
            redis_state=_old_state(),
        )
        assert result2["per_strategy"]["S4"]["new_threshold"] == pytest.approx(0.30), (
            "Con il ratchet congelato la soglia non deve risalire a 0,35"
        )


# ---------------------------------------------------------------------------
# Requisito #1: il flag non spegne regime_scale (S4 e S1)
# ---------------------------------------------------------------------------

class TestFrozenKeepsRegimeScaleLive:
    """Il flag congela SOLO l'innalzamento della soglia. regime_scale deve
    continuare a ratchettare verso il basso, altrimenti spegniamo un intero
    ramo di de-risking — il difetto che ha affossato #205."""

    def test_s4_scale_still_ratchets_down_when_frozen(self):
        trades = _s4_triggering_trades(n_losses=3)
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.45,
            redis_scale=1.0,               # scale non ancora toccato
            redis_state=_old_state(),
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["new_scale"] == pytest.approx(0.80), (
            "regime_scale deve ratchettare a 0.80 anche con il ratchet della "
            f"soglia congelato — ottenuto {s4['new_scale']}"
        )
        mock_redis.set_feedback_regime_scale.assert_called_once()
        assert mock_redis.set_feedback_regime_scale.call_args.args[0] == pytest.approx(0.80)

    def test_s1_scale_still_updates_and_threshold_stays_zero_when_frozen(self):
        """S1 non ha entry gate: il flag non deve spegnerne il regime_scale.
        La soglia di S1 resta 0.0 (sentinella 'nessun gate') come sempre."""
        # Most-recent first: tre loss S1, poi due win S4.
        trades = [
            _make_trade(-20, signal_id=None, trade_id=201),
            _make_trade(-30, signal_id=None, trade_id=202),
            _make_trade(-25, signal_id=None, trade_id=203),
            _make_trade(10, signal_id=999, trade_id=204),
            _make_trade(5, signal_id=999, trade_id=205),
        ]
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.45,
            redis_scale=1.0,
            redis_state=_old_state(),
        )

        s1 = result["per_strategy"]["S1"]
        assert s1["triggered"] is True
        assert s1["adjusted"] is True
        # S1 non ha gate: la soglia resta la sentinella 0.0.
        assert s1["new_threshold"] == pytest.approx(0.0)
        # ma il regime_scale di S1 ratchetta comunque (de-risking vivo).
        assert s1["new_scale"] == pytest.approx(0.80), (
            "Il regime_scale di S1 deve aggiornarsi anche con il ratchet "
            f"congelato — ottenuto {s1['new_scale']}"
        )
        mock_redis.set_feedback_regime_scale.assert_any_call(
            pytest.approx(0.80), ttl=pytest.approx(48 * 3600), strategy="S1"
        )


# ---------------------------------------------------------------------------
# Soglia già al baseline: resta al baseline, non sale
# ---------------------------------------------------------------------------

class TestFrozenKeepsBaselineSteady:
    def test_threshold_at_baseline_stays_at_baseline(self):
        """Con flag congelato e soglia già al baseline, un trigger non la alza."""
        trades = _s4_triggering_trades(n_losses=3)
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_scale=1.0,
            redis_state=_old_state(),
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["new_threshold"] == pytest.approx(0.30)
        # nessuna scrittura sopra il baseline
        for call in mock_redis.set_feedback_entry_threshold.call_args_list:
            assert call.args[0] == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# Regression guard: l'opt-in esplicito true mantiene il comportamento storico
# ---------------------------------------------------------------------------

class TestExplicitEnableRaises:
    """L'innalzamento resta disponibile come opt-in esplicito
    (`threshold_ratchet_enabled: true`). È il comportamento storico pre-freeze:
    questi test ne preservano la meccanica (raise by step, tetto al max)."""

    def test_explicit_true_raises_threshold_by_step(self):
        trades = _s4_triggering_trades(n_losses=3)
        result, _ = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_scale=1.0,
            redis_state=_old_state(),
            cfg_override={"threshold_ratchet_enabled": True},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["adjusted"] is True
        assert s4["new_threshold"] == pytest.approx(0.35)
        assert s4.get("ratchet_frozen") is not True

    def test_explicit_true_from_045_still_raises_to_050(self):
        """Con il flag esplicito true, partendo da 0,45 il ratchet storico
        sale a 0,50 — conferma che il freeze è opt-out (default) e l'opt-in
        non cambia la meccanica di innalzamento."""
        trades = _s4_triggering_trades(n_losses=3)
        result, _ = _patched_run(
            trades,
            redis_threshold=0.45,
            redis_scale=0.80,
            redis_state=_old_state(),
            cfg_override={"threshold_ratchet_enabled": True},
        )

        s4 = result["per_strategy"]["S4"]
        assert s4["new_threshold"] == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Requisito #3: il default in codice e il valore in trading.yaml sono congelati
# ---------------------------------------------------------------------------

class TestConfigDefaultFrozen:
    def test_load_loss_feedback_config_default_is_frozen(self):
        """Se trading.yaml manca, il flag defaulta a False (congelato): dopo un
        redeploy senza la chiave, il ratchet non alza la soglia."""
        with patch("builtins.open", side_effect=FileNotFoundError):
            cfg = _load_loss_feedback_config()
        assert cfg.get("threshold_ratchet_enabled") is False, (
            "il default del flag deve essere False (congelato) — decisione "
            "operatore 2026-08-10: il freeze è attivo alla consegna"
        )

    def test_trading_yaml_ships_flag_frozen(self):
        """Il config shipped deve avere il flag a False: il freeze è attivo alla
        consegna, senza richiedere azione manuale post-merge (deroga #171)."""
        cfg = _load_loss_feedback_config()  # legge il vero config/trading.yaml
        assert cfg.get("threshold_ratchet_enabled") is False, (
            "config/trading.yaml deve ship-pare threshold_ratchet_enabled: false "
            f"(freeze attivo alla consegna), ottenuto {cfg.get('threshold_ratchet_enabled')!r}"
        )