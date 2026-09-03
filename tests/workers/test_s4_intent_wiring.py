"""#294: wiring freeze-safe del ledger nel path live S4."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.backtest.engine.types import MarketSnapshot, OrderSide
from src.models.signals import SentimentResult
from src.portfolio.types import CombinedOrder
from src.strategies.s4.config import S4Config
from src.strategies.s4.intent_ledger import S4IntentLedger, build_component_versions
from src.strategies.s4.strategy import NewsDrivenTactical
from src.workers.portfolio_scheduler import (
    _build_strategy_instance,
    _finalize_s4_intent_ledger,
    _s4_sleeve_contributions,
    _s4_intent_provenance,
    _submit_portfolio_orders,
    _write_s4_intent_events_fail_open,
)

_TS = datetime(2026, 8, 24, 14, 7, tzinfo=timezone.utc)


def _versions():
    return build_component_versions(
        config=S4Config(n_top=1),
        risk_config={"s4_fixed_slot_sizing_enabled": True},
        code_version="abc1234",
        config_hash="deadbeef",
        policy_version="s4-exit-trial:v1",
    )


def _signal(symbol: str, signal_id: int, score: float):
    return SentimentResult(
        symbol=symbol,
        signal_id=signal_id,
        score=score,
        confidence=0.9,
        reasoning="test",
        model_id="ensemble:test",
        generated_at=_TS,
    )


def _buy(symbol: str, qty: float):
    return CombinedOrder(
        order_id=f"order-{symbol}",
        timestamp=_TS,
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        order_type="MARKET",
        limit_price=None,
        strategy_id="merged",
        allocation_weight=0.02,
    )


def test_strategy_trasferisce_i_diagnostics_del_ranker_al_ledger():
    ledger = S4IntentLedger(_TS, _versions())
    signals = [_signal("AMD", 1, 0.8), _signal("NVDA", 2, 0.7)]
    ledger.capture(signals)
    strategy = NewsDrivenTactical(
        config=S4Config(n_top=1, min_stocks=1),
        intent_ledger=ledger,
    )

    assert strategy.compute_target_weights(signals, as_of=_TS) == {"AMD": 1.0}
    dispositions = {event.signal_id: event for event in ledger.disposition_events(
        default_reason="UNCLASSIFIED"
    )}

    assert (dispositions[1].rank, dispositions[1].reason_code) == (1, "RANK_SELECTED")
    assert dispositions[1].is_tradable is True
    assert dispositions[2].is_tradable is False
    assert (dispositions[2].rank, dispositions[2].reason_code) == (
        2,
        "RANK_OUTSIDE_TOP_N",
    )


def test_writer_intenti_fail_open_non_interrompe_il_path_live():
    store = MagicMock()
    store.write_s4_intent_events.side_effect = RuntimeError("db down")

    assert _write_s4_intent_events_fail_open(store, [MagicMock()], phase="candidate") is False


def test_builder_scrive_i_candidate_prima_della_valutazione(mocker):
    signal = _signal("AMD", 1, 0.8)
    store = MagicMock()
    store.fetch_signals_for_cycle.return_value = [signal]
    store.fetch_trades.return_value = []
    mocker.patch("src.store.pg_store.PostgreSQLStore", return_value=store)
    mocker.patch(
        "src.workers.portfolio_scheduler._load_risk_config",
        return_value={"s4_fixed_slot_sizing_enabled": True},
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._get_feedback_threshold", return_value=0.0
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._compute_signal_velocity", return_value=1.0
    )
    redis = MagicMock()
    mocker.patch("redis.Redis.from_url", return_value=redis)
    entry = MagicMock(strategy_id="S4")
    bars = pd.DataFrame(
        {"AMD": [100.0, 101.0]},
        index=pd.date_range("2026-08-21", periods=2, freq="B"),
    )

    strategy = _build_strategy_instance(entry, bars, decision_at=_TS)

    written = store.write_s4_intent_events.call_args.args[0]
    assert [event.event_type for event in written] == ["candidate"]
    assert written[0].signal_id == 1
    # #401: il candidato porta il punteggio di ranking (qui == raw perché
    # velocity e' mockato a 1.0) accanto al raw score.
    assert written[0].snapshot["score"] == pytest.approx(0.8)
    assert written[0].snapshot["ranking_score"] == pytest.approx(0.8)
    assert "ranking_score" not in written[0].missingness
    assert written[0].held_at_rank is False
    assert strategy._intent_ledger is not None


def test_builder_cattura_held_at_rank_dallo_snapshot_posizioni_aperte(mocker):
    signal = _signal("AMD", 1, 0.8)
    store = MagicMock()
    store.fetch_signals_for_cycle.return_value = [signal]
    store.fetch_trades.return_value = [{"symbol": "AMD"}]
    mocker.patch("src.store.pg_store.PostgreSQLStore", return_value=store)
    mocker.patch(
        "src.workers.portfolio_scheduler._load_risk_config",
        return_value={"s4_fixed_slot_sizing_enabled": True},
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._get_feedback_threshold", return_value=0.0
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._compute_signal_velocity", return_value=1.0
    )
    mocker.patch("redis.Redis.from_url", return_value=MagicMock())
    entry = MagicMock(strategy_id="S4")
    bars = pd.DataFrame(
        {"AMD": [100.0, 101.0]},
        index=pd.date_range("2026-08-21", periods=2, freq="B"),
    )

    _build_strategy_instance(entry, bars, decision_at=_TS)

    [candidate] = store.write_s4_intent_events.call_args.args[0]
    assert candidate.held_at_rank is True


def test_builder_candidate_ranking_score_riflette_velocity_multiplier(mocker):
    """#401: con boost=1.2, ranking_score = raw * 1.2 = 0.96."""
    signal = _signal("AMD", 1, 0.8)
    store = MagicMock()
    store.fetch_signals_for_cycle.return_value = [signal]
    store.fetch_trades.return_value = []
    mocker.patch("src.store.pg_store.PostgreSQLStore", return_value=store)
    mocker.patch(
        "src.workers.portfolio_scheduler._load_risk_config",
        return_value={"s4_fixed_slot_sizing_enabled": True},
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._get_feedback_threshold", return_value=0.0
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._compute_signal_velocity", return_value=1.2
    )
    redis = MagicMock()
    mocker.patch("redis.Redis.from_url", return_value=redis)
    entry = MagicMock(strategy_id="S4")
    bars = pd.DataFrame(
        {"AMD": [100.0, 101.0]},
        index=pd.date_range("2026-08-21", periods=2, freq="B"),
    )

    _build_strategy_instance(entry, bars, decision_at=_TS)

    [candidate] = store.write_s4_intent_events.call_args.args[0]
    assert candidate.snapshot["score"] == pytest.approx(0.8)  # raw intoccato
    assert candidate.snapshot["ranking_score"] == pytest.approx(0.96)  # post-velocity


def test_rank_score_atomici_dal_capture_al_disposition(mocker):
    """#401: il punteggio di ranking nel candidate DEVE essere lo stesso che
    il ranker vede. Se diverge, la selezione non e' ricostruibile.

    Setup: due segnali con score raw distinti, velocity multiplier diversi.
    Il ranking_score atteso nel candidate (raw * mult) deve combaciare con
    l'effective_strength della RankedTicker corrispondente.
    """
    recent = _TS - timedelta(minutes=10)
    sig_a = SentimentResult(
        symbol="AMD", signal_id=10, score=0.40, confidence=0.9,
        reasoning="r", model_id="m", generated_at=recent,
    )
    sig_b = SentimentResult(
        symbol="NVDA", signal_id=11, score=0.50, confidence=0.9,
        reasoning="r", model_id="m", generated_at=recent,
    )
    store = MagicMock()
    store.fetch_signals_for_cycle.return_value = [sig_a, sig_b]
    store.fetch_trades.return_value = []
    mocker.patch("src.store.pg_store.PostgreSQLStore", return_value=store)
    mocker.patch(
        "src.workers.portfolio_scheduler._load_risk_config",
        return_value={"s4_fixed_slot_sizing_enabled": True},
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._get_feedback_threshold", return_value=0.0
    )
    # Velocity diversi per simbolo: AMD=1.5, NVDA=1.0. Catturati prima del
    # signals_df build, quindi il candidate snapshot li vede gia' moltiplicati.
    mocker.patch(
        "src.workers.portfolio_scheduler._compute_signal_velocity",
        side_effect=lambda sym, *a, **kw: {"AMD": 1.5, "NVDA": 1.0}[sym],
    )
    redis = MagicMock()
    mocker.patch("redis.Redis.from_url", return_value=redis)
    entry = MagicMock(strategy_id="S4")
    bars = pd.DataFrame(
        {"AMD": [100.0], "NVDA": [200.0]},
        index=pd.date_range("2026-08-21", periods=1, freq="B"),
    )
    # Il test fissa _TS nel 2026-08; il wall clock reale e' mesi dopo, quindi
    # la freshness/stale check li filtra tutti. Forza il passthrough.
    mocker.patch(
        "src.workers.portfolio_scheduler._apply_entry_freshness_gate",
        side_effect=lambda signals, *args, **kwargs: list(signals),
    )
    mocker.patch(
        "src.workers.portfolio_scheduler._filter_stale_signals",
        side_effect=lambda signals, *args, **kwargs: (list(signals), []),
    )

    strategy = _build_strategy_instance(entry, bars, decision_at=_TS)

    # Candidate events persistiti: lo snapshot deve portare entrambi gli score.
    [cand_a, cand_b] = store.write_s4_intent_events.call_args.args[0]
    by_signal = {c.signal_id: c for c in (cand_a, cand_b)}
    assert by_signal[10].snapshot["score"] == pytest.approx(0.40)
    assert by_signal[10].snapshot["ranking_score"] == pytest.approx(0.60)  # 0.40 * 1.5
    assert by_signal[11].snapshot["score"] == pytest.approx(0.50)
    assert by_signal[11].snapshot["ranking_score"] == pytest.approx(0.50)  # 0.50 * 1.0

    # Simula il ranker con i valori post-velocity (raw * mult) — e' quello che
    # la strategy vede quando costruisce i SentimentResult da signals_df. Deve
    # vincere AMD (0.60) su NVDA (0.50), anche se il raw score diceva il
    # contrario. La firma del #401 era esattamente questa divergenza.
    sig_a_post = sig_a.model_copy(update={"score": 0.60})
    sig_b_post = sig_b.model_copy(update={"score": 0.50})
    weights = strategy.compute_target_weights([sig_a_post, sig_b_post], as_of=_TS)
    provenance = strategy.last_signal_provenance
    # Default config: fixed_slot_sizing=True, n_top=5 -> ogni vincitore 1/5.
    assert weights == {"AMD": pytest.approx(0.2), "NVDA": pytest.approx(0.2)}
    assert provenance["AMD"]["score"] == pytest.approx(0.60)
    assert provenance["NVDA"]["score"] == pytest.approx(0.50)

    # Per ogni candidato persistito, il ranking_score nel snapshot e' lo
    # stesso effective_strength che il ranker ha usato per assegnargli il
    # rank: ora coincidono per costruzione.
    for sig_id, candidate in by_signal.items():
        ticker = candidate.symbol
        ranking_score_seen_by_ranker = provenance[ticker]["score"]
        assert candidate.snapshot["ranking_score"] == pytest.approx(
            ranking_score_seen_by_ranker
        )


def test_finalizer_scrive_disposition_riconciliata_con_s1_e_pyramiding():
    ledger = S4IntentLedger(_TS, _versions())
    ledger.capture([_signal("AMD", 1, 0.8)])
    ledger.set_disposition(
        signal_id=1,
        reason_code="RANK_SELECTED",
        rank=1,
        is_tradable=True,
    )
    store = MagicMock()

    assert _finalize_s4_intent_ledger(
        ledger,
        store=store,
        symbol_signal_provenance={"AMD": {"signal_id": 1}},
        symbol_strategies={"AMD": ["S1", "S4"]},
        open_db_symbols={"AMD"},
        open_trade_origin={"AMD": "S1"},
        order_dispositions={"AMD": ("SKIP_PYRAMIDING", {})},
    ) is True

    [event] = store.write_s4_intent_events.call_args.args[0]
    assert event.event_type == "disposition"
    assert event.reason_code == "SKIP_PYRAMIDING"
    assert event.rank == 1
    assert event.anti_pyramiding is True
    assert event.s1_state == {
        "held_by_s1": True,
        "origin": "S1",
        "position_present": True,
        "targeted": True,
    }
    assert event.snapshot["disposition"]["ranked_signal"] == {
        "model_id": None,
        "score": None,
    }
    # La popolazione post-gate resta distinta dalla disposizione operativa:
    # anti-pyramiding censura un intento che aveva superato gate e ranking.
    assert event.is_tradable is True


def test_provenance_intenti_sopravvive_alla_ricostruzione_del_risultato():
    strategy = MagicMock()
    strategy.last_signal_provenance = {
        "AMD": {"signal_id": 1, "score": 0.8, "model_id": "ensemble:test"}
    }

    observed = _s4_intent_provenance(strategy, live_provenance={})

    assert observed == strategy.last_signal_provenance
    assert observed is not strategy.last_signal_provenance


def test_callback_disposition_non_modifica_gli_ordini_inviati():
    orders = [_buy("AMD", 1.0), _buy("NVDA", 0.01)]
    market = MarketSnapshot(
        timestamp=_TS,
        prices={"AMD": 100.0, "NVDA": 100.0},
        volumes={},
        adv_20d={},
    )
    submit = MagicMock()

    baseline = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=submit,
        regime_mult=1.0,
    )
    dispositions = []
    instrumented = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=submit,
        regime_mult=1.0,
        _on_disposition=lambda symbol, reason, details: dispositions.append(
            (symbol, reason, details)
        ),
    )

    assert instrumented == baseline
    assert [(symbol, reason) for symbol, reason, _ in dispositions] == [
        ("AMD", "SUBMITTED"),
        ("NVDA", "SKIP_MIN_NOTIONAL"),
    ]


def test_callback_disposition_guasta_non_modifica_gli_ordini():
    order = _buy("AMD", 1.0)
    market = MarketSnapshot(
        timestamp=_TS,
        prices={"AMD": 100.0},
        volumes={},
        adv_20d={},
    )

    submitted = _submit_portfolio_orders(
        [order],
        MagicMock(),
        market,
        _submit_fn=MagicMock(),
        _on_disposition=MagicMock(side_effect=RuntimeError("telemetry down")),
    )

    assert [row["symbol"] for row in submitted] == ["AMD"]


def test_submit_conserva_prezzo_quantita_e_contributi_sleeve_nella_disposition():
    order = _buy("AMD", 2.0)
    market = MarketSnapshot(
        timestamp=_TS,
        prices={"AMD": 105.0},
        volumes={},
        adv_20d={},
    )
    dispositions = []

    _submit_portfolio_orders(
        [order],
        MagicMock(),
        market,
        _submit_fn=MagicMock(),
        sleeve_contributions={"AMD": {"S1": 0.05, "S4": 0.01}},
        _on_disposition=lambda symbol, reason, details: dispositions.append(
            (symbol, reason, details)
        ),
    )

    assert dispositions == [("AMD", "SUBMITTED", {
        "order_id": "test-AMD-buy",
        "notional": 210.0,
        "requested_quantity": 2.0,
        "first_executable_price": 105.0,
        "first_executable_price_source": "portfolio_market_snapshot.latest_price",
        "sleeve_contributions": {"S1": 0.05, "S4": 0.01},
    })]


def test_contributi_sleeve_derivano_dai_target_point_in_time_e_allocazioni():
    result = MagicMock()
    result.target_weights_per_strategy = {
        "S1": {"AMD": 0.10},
        "S4": {"AMD": 0.20, "NVDA": 0.30},
    }
    registry = MagicMock()
    registry.get_active_strategies.return_value = [
        MagicMock(strategy_id="S1", allocation_pct=0.50),
        MagicMock(strategy_id="S4", allocation_pct=0.10),
    ]

    contributions = _s4_sleeve_contributions(result, registry)

    assert contributions["AMD"] == pytest.approx({"S1": 0.05, "S4": 0.02})
    assert contributions["NVDA"] == pytest.approx({"S4": 0.03})


def test_reject_al_submit_conserva_i_dati_del_broker_boundary():
    order = _buy("AMD", 2.0)
    market = MarketSnapshot(
        timestamp=_TS,
        prices={"AMD": 105.0},
        volumes={},
        adv_20d={},
    )
    dispositions = []

    _submit_portfolio_orders(
        [order],
        MagicMock(),
        market,
        _submit_fn=MagicMock(side_effect=RuntimeError("broker rejected")),
        sleeve_contributions={"AMD": {"S4": 0.01}},
        _on_disposition=lambda symbol, reason, details: dispositions.append(
            (symbol, reason, details)
        ),
    )

    assert dispositions == [("AMD", "BROKER_REJECT", {
        "error_type": "RuntimeError",
        "notional": 210.0,
        "requested_quantity": 2.0,
        "first_executable_price": 105.0,
        "first_executable_price_source": "portfolio_market_snapshot.latest_price",
        "sleeve_contributions": {"S4": 0.01},
    })]


# --- #355: la strumentazione delle sleeve non deve poter rompere il ciclo ---


def test_contributi_sleeve_registry_guasto_non_propaga():
    """Un registry che solleva degrada a {}, non interrompe il ciclo."""
    result = MagicMock()
    result.target_weights_per_strategy = {"S4": {"AMD": 0.20}}
    registry = MagicMock()
    registry.get_active_strategies.side_effect = RuntimeError("registry down")

    assert _s4_sleeve_contributions(result, registry) == {}


def test_contributi_sleeve_allocazione_mancante_non_propaga():
    """Una strategia priva di allocation_pct degrada a {} invece di sollevare."""

    class _SenzaAllocazione:
        strategy_id = "S1"

    result = MagicMock()
    result.target_weights_per_strategy = {"S4": {"AMD": 0.20}}
    registry = MagicMock()
    registry.get_active_strategies.return_value = [_SenzaAllocazione()]

    assert _s4_sleeve_contributions(result, registry) == {}


def test_contributi_sleeve_peso_non_numerico_non_propaga():
    """Un peso non convertibile degrada a {} invece di sollevare."""
    result = MagicMock()
    result.target_weights_per_strategy = {"S4": {"AMD": "non-un-numero"}}
    registry = MagicMock()
    registry.get_active_strategies.return_value = [
        MagicMock(strategy_id="S4", allocation_pct=0.10),
    ]

    assert _s4_sleeve_contributions(result, registry) == {}


def test_submit_con_contributi_vuoti_invia_comunque_l_ordine():
    """Il fallback {} arriva fino alla disposition senza bloccare il submit."""
    order = _buy("AMD", 2.0)
    market = MarketSnapshot(
        timestamp=_TS,
        prices={"AMD": 105.0},
        volumes={},
        adv_20d={},
    )
    dispositions = []

    submitted = _submit_portfolio_orders(
        [order],
        MagicMock(),
        market,
        _submit_fn=MagicMock(),
        sleeve_contributions={},
        _on_disposition=lambda symbol, reason, details: dispositions.append(
            (symbol, reason, details)
        ),
    )

    assert [row["symbol"] for row in submitted] == ["AMD"]
    assert dispositions[0][1] == "SUBMITTED"
    assert dispositions[0][2]["sleeve_contributions"] == {}
