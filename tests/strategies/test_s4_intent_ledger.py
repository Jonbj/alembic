"""#294: contratto del ledger point-in-time degli entry intent S4."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        _DECISION_AT + timedelta(minutes=6), _versions()
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
        "content_hash": "not_available_at_decision",
        "first_seen_at": "not_available_at_decision",
        "published_at": "not_available_at_decision",
        "resolver": "not_available_at_decision",
    }


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

