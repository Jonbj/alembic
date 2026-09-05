"""#294: contratto del ledger point-in-time degli entry intent S4."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.models.signals import SentimentResult
from src.strategies.s4.config import S4Config
from src.strategies.s4.intent_ledger import (
    REQUIRED_VERSION_COMPONENTS,
    S4IntentLedger,
    build_component_versions,
)

_DECISION_AT = datetime(2026, 8, 24, 14, 7, 31, tzinfo=timezone.utc)


def _signal(signal_id: int = 7001, **overrides) -> SentimentResult:
    values = {
        "symbol": "AMD",
        "score": 0.62,
        "confidence": 0.88,
        "reasoning": "guidance raised",
        "model_id": "ensemble:glm52+gptoss",
        "generated_at": _DECISION_AT - timedelta(minutes=3),
        "published_at": _DECISION_AT - timedelta(minutes=11),
        "signal_id": signal_id,
        "news_log_id": 901,
        "first_seen_at": _DECISION_AT - timedelta(minutes=8),
        "news_source": "alpaca",
        "content_hash": "a" * 64,
        "extraction_method": "source_metadata",
        "resolver_decision": "RESOLVED",
        "resolver_method": "source_metadata",
    }
    values.update(overrides)
    return SentimentResult(**values)


def _versions() -> dict:
    return build_component_versions(
        config=S4Config(),
        risk_config={"s4_fixed_slot_sizing_enabled": True},
        code_version="abc1234",
        config_hash="deadbeef",
        policy_version="s4-exit-trial:v1",
    )


def test_intent_id_e_stabile_nella_stessa_finestra_decisionale():
    first = S4IntentLedger(_DECISION_AT, _versions()).capture([_signal()])[0]
    retry = S4IntentLedger(
        _DECISION_AT + timedelta(minutes=10), _versions()
    ).capture([_signal()])[0]

    assert first.intent_id == retry.intent_id
    assert first.event_id == retry.event_id
    assert first.causal_event_id == "news:901"


def test_nuova_finestra_o_nuovo_segnale_producono_intent_distinti():
    baseline = S4IntentLedger(_DECISION_AT, _versions()).capture([_signal()])[0]
    next_slot = S4IntentLedger(
        _DECISION_AT + timedelta(minutes=15), _versions()
    ).capture([_signal()])[0]
    other_signal = S4IntentLedger(_DECISION_AT, _versions()).capture(
        [_signal(signal_id=7002)]
    )[0]

    assert len({baseline.intent_id, next_slot.intent_id, other_signal.intent_id}) == 3


def test_candidate_conserva_tempi_versioni_concorrenti_e_missingness():
    missing = _signal(
        published_at=None,
        first_seen_at=None,
        content_hash=None,
        resolver_decision=None,
        resolver_method=None,
    )
    event = S4IntentLedger(_DECISION_AT, _versions()).capture(
        [missing, _signal(signal_id=7002, symbol="NVDA")]
    )[0]

    assert event.event_type == "candidate"
    assert event.model_generated_at == missing.generated_at
    assert event.decision_at == _DECISION_AT
    assert event.published_at is None
    assert event.first_seen_at is None
    assert set(event.versions) == REQUIRED_VERSION_COMPONENTS
    assert event.competing_candidates == ("AMD", "NVDA")
    assert event.reason_code == "CANDIDATE_OBSERVED"
    assert event.s1_state == {
        "status": "missing",
        "reason": "not_evaluated_before_rank",
    }
    assert event.missingness == {
        "active_feedback_threshold": "evaluated_after_candidate_capture",
        "content_hash": "not_available_at_decision",
        "first_seen_at": "not_available_at_decision",
        "held_at_rank": "open_positions_unavailable_at_capture",
        "published_at": "not_available_at_decision",
        "ranking_score": "not_recorded_at_capture",
        "resolver": "not_available_at_decision",
    }


def test_candidate_misura_posizione_aperta_ed_eta_al_decision_slot():
    signal = _signal(generated_at=_DECISION_AT - timedelta(hours=5))

    [event] = S4IntentLedger(_DECISION_AT, _versions()).capture(
        [signal],
        open_symbols={"AMD"},
    )

    assert event.held_at_rank is True
    assert event.signal_age_at_slot == event.decision_slot - signal.generated_at


def test_candidate_non_dichiara_non_detenuto_se_lo_snapshot_posizioni_manca():
    [event] = S4IntentLedger(_DECISION_AT, _versions()).capture([_signal()])

    assert event.held_at_rank is None
    assert event.missingness["held_at_rank"] == "open_positions_unavailable_at_capture"


def test_disposition_aggiunge_il_gate_effettivamente_osservato_senza_mutare_candidate():
    ledger = S4IntentLedger(_DECISION_AT, _versions())
    [candidate] = ledger.capture([_signal()])
    ledger.update_component_for_disposition(
        "gate",
        active_feedback_threshold=0.30,
        signal_velocity_threshold=0.15,
        signal_velocity_boost=1.2,
    )
    [disposition] = ledger.disposition_events(default_reason="SKIP_NOT_SELECTED")

    assert candidate.versions["gate"]["active_feedback_threshold"] is None
    assert disposition.versions["gate"]["active_feedback_threshold"] == 0.30
    assert "active_feedback_threshold" not in disposition.missingness


def test_disposition_riconcilia_rank_collisione_e_guard_con_il_candidate():
    ledger = S4IntentLedger(_DECISION_AT, _versions())
    candidate = ledger.capture([_signal(), _signal(signal_id=7002, symbol="NVDA")])[0]
    ledger.set_disposition(
        signal_id=7001,
        reason_code="SKIP_PYRAMIDING",
        rank=1,
        is_tradable=False,
        s1_state={"held": True, "targeted": True},
        anti_pyramiding=True,
    )
    dispositions = ledger.disposition_events(default_reason="SKIP_NOT_SELECTED")
    disposition = next(event for event in dispositions if event.signal_id == 7001)

    assert disposition.event_type == "disposition"
    assert disposition.intent_id == candidate.intent_id
    assert disposition.rank == 1
    assert disposition.reason_code == "SKIP_PYRAMIDING"
    assert disposition.is_tradable is False
    assert disposition.anti_pyramiding is True
    assert disposition.s1_state == {"held": True, "targeted": True}


def test_migrazione_impone_append_only_idempotenza_e_due_popolazioni():
    migration = (
        Path(__file__).resolve().parents[2] / "migrations" / "050_s4_entry_intent_ledger.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS s4_intent_events" in migration
    assert "UNIQUE (intent_id, event_type)" in migration
    assert "prevent_s4_intent_event_mutation" in migration
    assert "CREATE VIEW s4_candidate_population" in migration
    assert "CREATE VIEW s4_tradable_intent_population" in migration
    assert "intent_id" in migration


# --- #401: il rank nel ledger deve riflettere il punteggio di ranking, non il
# raw `signal.score`. Il ranker moltiplica per il velocity multiplier prima di
# ordinare — quel punteggio (effective_strength) deve arrivare al candidate in
# modo atomico, non dopo un re-read.


def test_candidate_puo_registrare_il_punteggio_di_ranking_atomico_al_raw():
    ledger = S4IntentLedger(_DECISION_AT, _versions())
    [event] = ledger.capture(
        [_signal(score=0.40)],
        ranking_scores={7001: 0.48},
    )

    assert event.snapshot["score"] == pytest.approx(0.40)
    assert event.snapshot["ranking_score"] == pytest.approx(0.48)


def test_candidate_senza_ranking_score_lo_marca_nel_missingness():
    """Retro-compat: prima del fix il ledger non aveva `ranking_score`; i candidate
    che non ne hanno uno devono dichiararlo esplicitamente nel missingness, non
    restare silenti (altrimenti il dossier non sa di non saperlo)."""
    ledger = S4IntentLedger(_DECISION_AT, _versions())
    [event] = ledger.capture([_signal()])

    assert "ranking_score" not in event.snapshot
    assert event.missingness.get("ranking_score") == "not_recorded_at_capture"


def test_dossier_invariante_rank_strettamente_decrescente_in_ranking_score():
    """#401: per ogni decision_slot, la mappa (symbol -> (rank, ranking_score))
    deve soddisfare rank_i < rank_j iff ranking_score_i > ranking_score_j
    (confronto fra simboli co-ranghi ammesso per la tie rule)."""
    ledger = S4IntentLedger(_DECISION_AT, _versions())
    raw = [
        _signal(signal_id=11, symbol="MRVL", score=0.3578),
        _signal(signal_id=12, symbol="CSCO", score=0.3199),
        _signal(signal_id=13, symbol="SOXX", score=0.3600),
    ]
    ledger.capture(
        raw,
        ranking_scores={11: 0.3578, 12: 0.3199, 13: 0.3600},
    )
    from src.strategies.s4.config import S4Config
    from src.strategies.s4.ranking import CrossSectionalRanker

    ranker = CrossSectionalRanker(S4Config(n_top=5, min_stocks=3))
    result = ranker.rank(raw, as_of=_DECISION_AT)

    for diagnostic in result.diagnostics:
        if diagnostic.signal_id is None or diagnostic.rank is None:
            continue
        candidate = next(
            e for e in ledger._states.values() if e.candidate.signal_id == diagnostic.signal_id
        )
        ranking_score = candidate.candidate.snapshot.get("ranking_score")
        # L'invariante richiede che il punteggio persistito sia la chiave
        # usata dal ranker per assegnare quel rank: devono coincidere.
        assert ranking_score == pytest.approx(
            next(
                r.effective_strength for r in result.rankings
                if r.signal_id == diagnostic.signal_id
            )
        )

    by_symbol = {
        d.ticker: (d.rank, next(
            e.candidate.snapshot.get("ranking_score") for e in ledger._states.values()
            if e.candidate.signal_id == d.signal_id
        ))
        for d in result.diagnostics if d.rank is not None and d.signal_id is not None
    }
    sorted_by_score = sorted(by_symbol.items(), key=lambda kv: kv[1][1], reverse=True)
    assert [t for t, _ in sorted_by_score] == [t for t, _ in sorted(
        by_symbol.items(), key=lambda kv: kv[1][0]
    )]
