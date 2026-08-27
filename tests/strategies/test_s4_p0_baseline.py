"""#296: baseline P0 shadow riproducibile per il trial exit S4."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from src.costs.calculator import CostBreakdown
from src.strategies.s4.lifecycle import (
    BrokerOrderSnapshot,
    MarketSession,
    SubmittedIntent,
    reconcile_entry,
)
from src.strategies.s4.p0_baseline import (
    RuntimeExitObservation,
    build_p0_replay_report,
    compare_p0_to_runtime,
    load_p0_policy_snapshot,
    observe_p0_open,
    replay_p0,
)

ENTRY_AT = datetime(2026, 8, 25, 15, 7, 4, tzinfo=UTC)
TRIGGER_AT = datetime(2026, 8, 25, 17, 52, tzinfo=UTC)
EXIT_AT = TRIGGER_AT + timedelta(seconds=3)


class _CostModel:
    version = "cost-model:test-golden"

    def compute(self, *, symbol, notional, qty, fill_price, side):
        cost = 1.0 if side == "BUY" else 2.0
        return CostBreakdown(
            spread_cost_bps=10.0,
            impact_cost_bps=0.0,
            regulatory_cost_usd=0.0,
            total_cost_bps=10.0,
            total_cost_usd=cost,
        )


def _entry(intent_id: str = "34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0"):
    intent = SubmittedIntent(
        intent_id=intent_id,
        symbol="AMD",
        order_id="entry-order-1",
        submitted_at=ENTRY_AT - timedelta(seconds=4),
        requested_quantity=2.0,
        requested_notional=210.0,
        first_executable_price=105.0,
        first_executable_price_source="alpaca_snapshot.latest_trade",
        policy_version="s4-exit-trial:1.0.0",
        sleeve_contributions={"S4": 1.0},
    )
    sessions = [
        MarketSession(
            session_date=date(2026, 8, day),
            open_at=datetime(2026, 8, day, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, day, 20, 0, tzinfo=UTC),
        )
        for day in (25, 26, 27)
    ]
    return reconcile_entry(
        intent,
        BrokerOrderSnapshot(
            order_id="entry-order-1",
            status="filled",
            filled_at=ENTRY_AT,
            filled_quantity=2.0,
            filled_avg_price=105.25,
        ),
        sessions,
        ENTRY_AT + timedelta(minutes=5),
        broker_position_quantity=2.0,
    )


def _runtime(**overrides) -> RuntimeExitObservation:
    values = {
        "runtime_decision_id": 901,
        "runtime_order_id": "exit-order-1",
        "trigger_kind": "target_weight_zero",
        "exit_mechanism": "expired",
        "trigger_at": TRIGGER_AT,
        "runtime_quantity": 2.0,
        "first_executable_at": EXIT_AT,
        "first_executable_price": 110.0,
        "first_executable_price_source": "alpaca_order.filled_avg_price",
        "filled_at": EXIT_AT,
        "filled_quantity": 2.0,
        "fill_price": 110.0,
        "raw_reason": "[expired] signal discarded for age",
    }
    values.update(overrides)
    return RuntimeExitObservation(**values)


def test_snapshot_p0_legge_il_contratto_congelato_senza_parametri_live():
    snapshot = load_p0_policy_snapshot()

    assert snapshot.version == "s4-exit-trial:1.0.0"
    assert snapshot.scope == "shadow_only"
    assert snapshot.d_hard_enabled is True
    assert snapshot.take_profit_enabled is False
    assert snapshot.trailing_enabled is False
    assert snapshot.scale_out_enabled is False


def test_snapshot_rifiuta_un_dhard_non_comune_alle_policy(tmp_path):
    contract_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "s4_exit_trial.yaml"
    )
    payload = yaml.safe_load(contract_path.read_text())
    payload["risk_overlay"]["d_hard"]["identical_across_policies"] = False
    drifted = tmp_path / "s4_exit_trial.yaml"
    drifted.write_text(yaml.safe_dump(payload))

    with pytest.raises(ValueError, match="identical across policies"):
        load_p0_policy_snapshot(drifted)


def test_golden_replay_riproduce_trigger_quantita_tempo_prezzo_costi_e_outcome():
    runtime = _runtime()
    event = replay_p0(_entry(), runtime, load_p0_policy_snapshot(), _CostModel())

    assert event.policy_id == "P0"
    assert event.status == "CLOSED"
    assert event.reason_code == "P0_TARGET_ZERO_EXPIRED"
    assert event.trigger_at == runtime.trigger_at
    assert event.virtual_exit_quantity == runtime.runtime_quantity
    assert event.first_executable_at == runtime.first_executable_at
    assert event.first_executable_price == runtime.first_executable_price
    assert event.fill_price == 110.0
    assert event.initial_notional == pytest.approx(210.5)
    assert event.gross_pnl == pytest.approx(9.5)
    assert event.entry_cost_usd == 1.0
    assert event.exit_cost_usd == 2.0
    assert event.net_pnl == pytest.approx(6.5)
    assert event.cost_model_version == "cost-model:test-golden"
    assert event.shadow_order_id is None
    assert event.comparable is True
    assert compare_p0_to_runtime(event, runtime) == ()


def test_lifecycle_runtime_ancora_aperto_entra_nel_denominatore_come_comparabile():
    event = observe_p0_open(
        _entry(),
        load_p0_policy_snapshot(),
        _CostModel(),
        runtime_trade_id=77,
    )

    assert event.event_type == "P0_OPEN_SNAPSHOT"
    assert event.status == "OPEN"
    assert event.reason_code == "P0_RUNTIME_OPEN"
    assert event.virtual_exit_quantity == 0.0
    assert event.runtime_order_id is None
    assert event.shadow_order_id is None
    assert event.comparable is True


def test_runtime_trade_mancante_e_un_residuo_non_un_lifecycle_omesso():
    event = observe_p0_open(
        _entry(),
        load_p0_policy_snapshot(),
        _CostModel(),
        runtime_trade_id=None,
    )

    assert event.status == "CENSORED"
    assert event.reason_code == "P0_RUNTIME_TRADE_MISSING"
    assert event.comparable is False
    assert event.divergence_reasons == ("RUNTIME_TRADE_MISSING",)


def test_versione_policy_diversa_dallo_snapshot_rende_il_replay_non_comparabile():
    lifecycle = replace(_entry(), policy_version="s4-exit-trial:0.9.0")

    event = replay_p0(
        lifecycle,
        _runtime(),
        load_p0_policy_snapshot(),
        _CostModel(),
    )

    assert event.comparable is False
    assert event.divergence_reasons == ("POLICY_VERSION_MISMATCH",)


@pytest.mark.parametrize(
    ("trigger_kind", "mechanism", "reason_code"),
    [
        ("target_weight_zero", "no_signal", "P0_TARGET_ZERO_NO_SIGNAL"),
        ("target_weight_zero", "expired", "P0_TARGET_ZERO_EXPIRED"),
        ("target_weight_zero", "whipsaw", "P0_TARGET_ZERO_WHIPSAW"),
        ("target_weight_zero", "unknown", "P0_TARGET_ZERO_UNKNOWN"),
        ("target_weight_zero", "below_entry_gate", "P0_TARGET_ZERO_BELOW_ENTRY_GATE"),
        ("target_weight_zero", "fallback_filtered", "P0_TARGET_ZERO_FALLBACK_FILTERED"),
        (
            "target_weight_zero",
            "entry_freshness_filtered",
            "P0_TARGET_ZERO_ENTRY_FRESHNESS_FILTERED",
        ),
        ("sentiment_reversal", None, "P0_SENTIMENT_REVERSAL"),
        ("d_hard", None, "P0_D_HARD"),
    ],
)
def test_ogni_trigger_e0_rilevante_ha_un_reason_code_esplicito(
    trigger_kind, mechanism, reason_code
):
    event = replay_p0(
        _entry(),
        _runtime(trigger_kind=trigger_kind, exit_mechanism=mechanism),
        load_p0_policy_snapshot(),
        _CostModel(),
    )

    assert event.reason_code == reason_code
    assert event.status == ("RISK_EXITED" if trigger_kind == "d_hard" else "CLOSED")
    assert event.comparable is True


@pytest.mark.parametrize(
    ("trigger_kind", "reason_code"),
    [
        ("take_profit", "P0_TAKE_PROFIT_DISABLED"),
        ("trailing", "P0_TRAILING_DISABLED"),
        ("scale_out", "P0_SCALE_OUT_DISABLED"),
        ("tight_stop", "P0_TIGHT_STOP_DISABLED"),
    ],
)
def test_overlay_esclusi_dal_contratto_sono_censurati_non_assorbiti(
    trigger_kind, reason_code
):
    event = replay_p0(
        _entry(),
        _runtime(trigger_kind=trigger_kind, exit_mechanism=None),
        load_p0_policy_snapshot(),
        _CostModel(),
    )

    assert event.status == "CENSORED"
    assert event.reason_code == reason_code
    assert event.virtual_exit_quantity == 0.0
    assert event.comparable is False


def test_fill_mancante_resta_triggered_e_classificato():
    event = replay_p0(
        _entry(),
        _runtime(
            filled_at=None,
            filled_quantity=0.0,
            fill_price=None,
            first_executable_at=None,
            first_executable_price=None,
        ),
        load_p0_policy_snapshot(),
        _CostModel(),
    )

    assert event.status == "TRIGGERED"
    assert event.reason_code == "P0_EXIT_FILL_MISSING"
    assert event.comparable is False
    assert event.divergence_reasons == ("EXIT_FILL_MISSING",)


def test_idempotenza_e_golden_classificano_ogni_divergenza():
    runtime = _runtime()
    first = replay_p0(_entry(), runtime, load_p0_policy_snapshot(), _CostModel())
    retry = replay_p0(_entry(), runtime, load_p0_policy_snapshot(), _CostModel())
    changed = replace(
        first,
        reason_code="P0_TARGET_ZERO_WHIPSAW",
        trigger_at=first.trigger_at + timedelta(seconds=1),
        virtual_exit_quantity=1.5,
        first_executable_price=109.0,
    )

    assert retry.event_id == first.event_id
    assert compare_p0_to_runtime(changed, runtime) == (
        "TRIGGER_MISMATCH",
        "QUANTITY_MISMATCH",
        "TRIGGER_TIME_MISMATCH",
        "FIRST_EXECUTABLE_PRICE_MISMATCH",
    )


def test_report_validation_window_applica_il_95_percento_e_classifica_residui():
    baseline = replay_p0(
        _entry(), _runtime(), load_p0_policy_snapshot(), _CostModel()
    )
    events = [
        replace(
            baseline,
            event_id=f"00000000-0000-0000-0000-{index:012d}",
            intent_id=f"10000000-0000-0000-0000-{index:012d}",
        )
        for index in range(95)
    ]
    events.extend(
        replace(
            baseline,
            event_id=f"20000000-0000-0000-0000-{index:012d}",
            intent_id=f"30000000-0000-0000-0000-{index:012d}",
            status="TRIGGERED",
            reason_code="P0_EXIT_FILL_MISSING",
            comparable=False,
            divergence_reasons=("EXIT_FILL_MISSING",),
        )
        for index in range(5)
    )

    report = build_p0_replay_report(
        events,
        window_start=date(2026, 8, 25),
        window_end=date(2026, 8, 25),
    )

    assert report["total"] == 100
    assert report["comparable"] == 95
    assert report["coverage"] == pytest.approx(0.95)
    assert report["meets_minimum"] is True
    assert report["residual_by_reason"] == {"P0_EXIT_FILL_MISSING": 5}


def test_una_proiezione_di_un_lifecycle_corretto_e_un_evento_distinto():
    """Senza questo, `ON CONFLICT DO NOTHING` scarta ogni correzione a monte.

    La riga P0 e' la *proiezione* di una precisa osservazione di lifecycle. Se
    quell'osservazione viene corretta — un ingresso prima non ricostruibile che
    lo diventa — la proiezione vecchia resta valida come storia ma non come
    stato corrente, e per poter essere riscritta in una tabella append-only
    deve avere un `event_id` proprio.
    """
    runtime = _runtime()
    snapshot = load_p0_policy_snapshot()
    non_ricostruibile = replace(_entry(), reconstructible=False, event_id="lc-vecchio")
    ricostruibile = replace(_entry(), reconstructible=True, event_id="lc-corretto")

    prima = replay_p0(non_ricostruibile, runtime, snapshot, _CostModel())
    dopo = replay_p0(ricostruibile, runtime, snapshot, _CostModel())

    assert prima.comparable is False
    assert "ENTRY_NOT_RECONSTRUCTIBLE" in prima.divergence_reasons
    assert dopo.comparable is True
    assert dopo.event_id != prima.event_id


def test_la_proiezione_dichiara_da_quale_osservazione_di_lifecycle_nasce():
    """Il consumatore deve poter dire se la proiezione e' ferma a un'osservazione vecchia."""
    entry = _entry()

    event = replay_p0(entry, _runtime(), load_p0_policy_snapshot(), _CostModel())

    assert event.details["entry_lifecycle_event_id"] == entry.event_id


def test_lo_snapshot_aperto_segue_la_stessa_regola():
    snapshot = load_p0_policy_snapshot()
    vecchio = replace(_entry(), reconstructible=False, event_id="lc-vecchio")
    corretto = replace(_entry(), reconstructible=True, event_id="lc-corretto")

    prima = observe_p0_open(vecchio, snapshot, _CostModel(), runtime_trade_id=7)
    dopo = observe_p0_open(corretto, snapshot, _CostModel(), runtime_trade_id=7)

    assert prima.event_id != dopo.event_id
    assert dopo.details["entry_lifecycle_event_id"] == "lc-corretto"


def test_riproiettare_la_stessa_osservazione_resta_idempotente():
    """La correzione non deve trasformarsi in una riga nuova a ogni ciclo."""
    entry = _entry()
    runtime = _runtime()
    snapshot = load_p0_policy_snapshot()

    assert (
        replay_p0(entry, runtime, snapshot, _CostModel()).event_id
        == replay_p0(entry, runtime, snapshot, _CostModel()).event_id
    )
