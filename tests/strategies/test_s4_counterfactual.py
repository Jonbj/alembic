"""#298: replacement e opportunity cost del trial exit S4.

Le due viste sono pure: consumano gli esiti per-policy gia' prodotti a monte
(#295 lifecycle, #296 baseline P0) e non conoscono broker, DB o universo live.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from src.costs.calculator import CostBreakdown
from src.strategies.s4.counterfactual import (
    EXIT_FAMILY_COUNTER_QUALIFIED,
    EXIT_FAMILY_REPLACEMENT,
    EXIT_FAMILY_RISK_CATASTROPHE,
    EXIT_FAMILY_TIME_STOP,
    FreedSlot,
    PolicyOutcome,
    SubstituteCandidate,
    active_policy_hierarchy,
    build_paired_comparison,
    build_portfolio_counterfactual,
    build_replacement_report,
    classify_exit_reason,
    outcome_from_p0_event,
    reconcile_views,
)
from src.strategies.s4.lifecycle import (
    BrokerOrderSnapshot,
    MarketSession,
    SubmittedIntent,
    reconcile_entry,
)
from src.strategies.s4.p0_baseline import (
    RuntimeExitObservation,
    load_p0_policy_snapshot,
    replay_p0,
)

ENTRY_AT = datetime(2026, 8, 25, 15, 7, 4, tzinfo=UTC)
TRIGGER_AT = datetime(2026, 8, 25, 17, 52, tzinfo=UTC)
EXIT_AT = TRIGGER_AT + timedelta(seconds=3)
D0 = date(2026, 8, 25)
CONTRACT_PATH = Path(__file__).resolve().parents[2] / "config" / "s4_exit_trial.yaml"


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


# ── Helper: un esito P0 reale, costruito dai moduli gia' in main ─────────────


def _p0_event():
    intent = SubmittedIntent(
        intent_id="34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
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
    lifecycle = reconcile_entry(
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
    runtime = RuntimeExitObservation(
        runtime_decision_id=901,
        runtime_order_id="exit-order-1",
        trigger_kind="target_weight_zero",
        exit_mechanism="expired",
        trigger_at=TRIGGER_AT,
        runtime_quantity=2.0,
        first_executable_at=EXIT_AT,
        first_executable_price=110.0,
        first_executable_price_source="alpaca_order.filled_avg_price",
        filled_at=EXIT_AT,
        filled_quantity=2.0,
        fill_price=110.0,
    )
    return replay_p0(lifecycle, runtime, load_p0_policy_snapshot(), _CostModel())


def _outcome(policy_id: str, **overrides) -> PolicyOutcome:
    values = {
        "intent_id": "intent-1",
        "policy_id": policy_id,
        "symbol": "AMD",
        "d0": D0,
        "entry_fill_id": "fill-1",
        "initial_notional": 1000.0,
        "status": "CLOSED",
        "exit_reason_code": "P0_TARGET_ZERO_EXPIRED",
        "exit_at": EXIT_AT,
        "virtual_exit_quantity": 2.0,
        "net_pnl": 10.0,
        "comparable": True,
    }
    values.update(overrides)
    return PolicyOutcome(**values)


def _candidate(**overrides) -> SubstituteCandidate:
    values = {
        "symbol": "NVDA",
        "signal_id": 5001,
        "rank": 2,
        "observed_at": EXIT_AT - timedelta(minutes=10),
        "universe_as_of": EXIT_AT - timedelta(minutes=10),
        "entry_price": 100.0,
        "exit_price": 104.0,
        "investable": True,
        "collides_with_s1": False,
    }
    values.update(overrides)
    return SubstituteCandidate(**values)


def _slot(**overrides) -> FreedSlot:
    values = {
        "intent_id": "intent-1",
        "symbol": "AMD",
        "policy_id": "P0",
        "freed_at": EXIT_AT,
        "freed_notional": 1000.0,
        "slot_closes_at": EXIT_AT + timedelta(days=2),
    }
    values.update(overrides)
    return FreedSlot(**values)


# ── Adattatore: il contratto degli esiti esiste gia' in main ─────────────────


def test_outcome_si_deriva_da_un_evento_p0_reale_senza_nuovo_contratto():
    event = _p0_event()

    outcome = outcome_from_p0_event(event)

    assert outcome.policy_id == "P0"
    assert outcome.intent_id == event.intent_id
    assert outcome.entry_fill_id == event.details["entry_fill_id"]
    assert outcome.initial_notional == pytest.approx(event.initial_notional)
    assert outcome.net_pnl == pytest.approx(event.net_pnl)
    assert outcome.exit_reason_code == event.reason_code
    assert outcome.d0 == event.d0


# ── Criterio 1: ingressi congelati, nessun reinvestimento ───────────────────


def test_paired_congela_gli_ingressi_e_calcola_il_delta_in_bps():
    baseline = [_outcome("P0", net_pnl=10.0)]
    challenger = [_outcome("P1", net_pnl=35.0, exit_reason_code="P1_TIME_DUE")]

    comparison = build_paired_comparison(baseline, challenger)

    assert comparison.new_trades_created == 0
    pair = comparison.pairs[0]
    assert pair.comparable is True
    assert pair.initial_notional == pytest.approx(1000.0)
    # 25 USD su 1000 di notional iniziale = 250 bps
    assert pair.delta_bps == pytest.approx(250.0)
    assert pair.delta_usd == pytest.approx(25.0)


def test_paired_scarta_la_coppia_se_il_notional_iniziale_differisce():
    baseline = [_outcome("P0")]
    challenger = [_outcome("P1", initial_notional=1200.0)]

    comparison = build_paired_comparison(baseline, challenger)

    pair = comparison.pairs[0]
    assert pair.comparable is False
    assert "PAIRED_NOTIONAL_MISMATCH" in pair.exclusion_reasons
    assert pair.delta_bps is None


def test_paired_scarta_la_coppia_se_il_fill_di_ingresso_differisce():
    baseline = [_outcome("P0", entry_fill_id="fill-1")]
    challenger = [_outcome("P1", entry_fill_id="fill-2")]

    comparison = build_paired_comparison(baseline, challenger)

    assert comparison.pairs[0].comparable is False
    assert "PAIRED_ENTRY_FILL_MISMATCH" in comparison.pairs[0].exclusion_reasons


def test_paired_segnala_un_intento_challenger_assente_dalla_baseline():
    """Il cash liberato non puo' creare trade: un intento nuovo e' una violazione."""
    baseline = [_outcome("P0")]
    challenger = [_outcome("P1"), _outcome("P1", intent_id="intent-nuovo")]

    comparison = build_paired_comparison(baseline, challenger)

    assert comparison.new_trades_created == 1
    unshared = [p for p in comparison.pairs if p.intent_id == "intent-nuovo"]
    assert unshared[0].comparable is False
    assert "PAIRED_UNSHARED_INTENT" in unshared[0].exclusion_reasons
    assert comparison.entries_frozen is False


def test_paired_dichiara_gli_ingressi_congelati_quando_gli_intenti_combaciano():
    baseline = [_outcome("P0"), _outcome("P0", intent_id="intent-2")]
    challenger = [_outcome("P1"), _outcome("P1", intent_id="intent-2")]

    comparison = build_paired_comparison(baseline, challenger)

    assert comparison.entries_frozen is True
    assert comparison.new_trades_created == 0


def test_paired_scarta_un_esito_non_comparabile_a_monte():
    baseline = [_outcome("P0", comparable=False)]
    challenger = [_outcome("P1")]

    comparison = build_paired_comparison(baseline, challenger)

    assert comparison.pairs[0].comparable is False
    assert "PAIRED_BASELINE_NOT_COMPARABLE" in comparison.pairs[0].exclusion_reasons


def test_paired_scarta_una_coppia_senza_pnl_netto():
    baseline = [_outcome("P0", net_pnl=None)]
    challenger = [_outcome("P1")]

    comparison = build_paired_comparison(baseline, challenger)

    assert "PAIRED_NET_PNL_MISSING" in comparison.pairs[0].exclusion_reasons


def test_paired_registra_il_challenger_mancante_senza_inventarlo():
    baseline = [_outcome("P0"), _outcome("P0", intent_id="intent-2")]
    challenger = [_outcome("P1")]

    comparison = build_paired_comparison(baseline, challenger)

    missing = [p for p in comparison.pairs if p.intent_id == "intent-2"]
    assert missing[0].comparable is False
    assert "PAIRED_CHALLENGER_MISSING" in missing[0].exclusion_reasons


# ── Criterio 2: replacement ha un reason code dedicato ──────────────────────


def test_replacement_e_distinto_da_time_stop_counter_e_rischio():
    assert classify_exit_reason("P1_TIME_DUE") == EXIT_FAMILY_TIME_STOP
    assert classify_exit_reason("P2_COUNTER_QUALIFIED") == EXIT_FAMILY_COUNTER_QUALIFIED
    assert classify_exit_reason("P0_D_HARD") == EXIT_FAMILY_RISK_CATASTROPHE
    assert (
        classify_exit_reason("REPLACEMENT_SLOT_REALLOCATED")
        == EXIT_FAMILY_REPLACEMENT
    )
    families = {
        classify_exit_reason(code)
        for code in (
            "P1_TIME_DUE",
            "P2_COUNTER_QUALIFIED",
            "P0_D_HARD",
            "REPLACEMENT_SLOT_REALLOCATED",
        )
    }
    assert len(families) == 4


def test_il_reversal_ordinario_non_viene_promosso_a_counter_qualificato():
    """P0 chiude su sentiment_reversal non qualificato: non e' il counter di P2."""
    assert classify_exit_reason("P0_SENTIMENT_REVERSAL") != (
        EXIT_FAMILY_COUNTER_QUALIFIED
    )


def test_le_uscite_per_freschezza_non_sono_una_thesis_exit_ne_un_replacement():
    for code in ("P0_TARGET_ZERO_EXPIRED", "P0_TARGET_ZERO_NO_SIGNAL"):
        assert classify_exit_reason(code) not in {
            EXIT_FAMILY_REPLACEMENT,
            EXIT_FAMILY_TIME_STOP,
            EXIT_FAMILY_COUNTER_QUALIFIED,
            EXIT_FAMILY_RISK_CATASTROPHE,
        }


# ── Gerarchia delle policy: P2 e' omitted dal contratto congelato ───────────


def test_la_gerarchia_esclude_p2_perche_omitted_a_n0():
    hierarchy = active_policy_hierarchy(CONTRACT_PATH)

    assert hierarchy == ("P0", "P1")


def test_un_esito_p2_non_entra_nel_paired_finche_p2_e_omitted():
    baseline = [_outcome("P0")]
    challenger = [_outcome("P2", exit_reason_code="P2_COUNTER_QUALIFIED")]

    comparison = build_paired_comparison(
        baseline, challenger, active_policies=active_policy_hierarchy(CONTRACT_PATH)
    )

    pair = comparison.pairs[0]
    assert pair.comparable is False
    assert "POLICY_OMITTED_BY_CONTRACT" in pair.exclusion_reasons


# ── Criteri 3 e 4: controfattuale portfolio-level, solo dati point-in-time ──


def test_il_controfattuale_registra_candidato_rank_slot_capitale_e_pnl():
    record = build_portfolio_counterfactual([_slot()], {"intent-1": [_candidate()]})[0]

    assert record.substitute_symbol == "NVDA"
    assert record.substitute_signal_id == 5001
    assert record.point_in_time_rank == 2
    assert record.slot_available is True
    # 1000 USD di notional per 2 giorni di slot
    assert record.capital_days == pytest.approx(2000.0)
    # +4% su 1000 USD di capitale liberato
    assert record.incremental_pnl == pytest.approx(40.0)
    assert record.reason_code == "REPLACEMENT_SLOT_REALLOCATED"


def test_nessun_candidato_lascia_il_capitale_inerte_senza_pnl_incrementale():
    record = build_portfolio_counterfactual([_slot()], {})[0]

    assert record.substitute_symbol is None
    assert record.slot_available is True
    assert record.incremental_pnl == pytest.approx(0.0)
    assert record.reason_code == "NO_SUBSTITUTE_AVAILABLE"
    # il capitale resta impegnato dallo slot anche se non investito
    assert record.capital_days == pytest.approx(2000.0)
    assert record.idle_capital_days == pytest.approx(2000.0)


def test_piu_candidati_selezionano_il_rank_migliore_e_registrano_gli_scartati():
    candidates = [
        _candidate(symbol="NVDA", rank=3, signal_id=1),
        _candidate(symbol="AVGO", rank=1, signal_id=2, exit_price=101.0),
    ]

    record = build_portfolio_counterfactual([_slot()], {"intent-1": candidates})[0]

    assert record.substitute_symbol == "AVGO"
    assert record.point_in_time_rank == 1
    assert record.candidates_considered == 2
    assert ("NVDA", "CANDIDATE_OUTRANKED") in record.rejected_candidates


def test_un_pari_rank_e_ambiguo_e_non_prende_il_percorso_favorevole():
    """Il contratto impone: caso ambiguo marcato, mai il percorso favorevole."""
    candidates = [
        _candidate(symbol="NVDA", rank=1, signal_id=1, exit_price=130.0),
        _candidate(symbol="AVGO", rank=1, signal_id=2, exit_price=101.0),
    ]

    record = build_portfolio_counterfactual([_slot()], {"intent-1": candidates})[0]

    assert record.reason_code == "AMBIGUOUS_SUBSTITUTE"
    assert record.substitute_symbol is None
    assert record.incremental_pnl == pytest.approx(0.0)


def test_un_candidato_osservato_dopo_la_decisione_e_lookahead():
    late = _candidate(observed_at=EXIT_AT + timedelta(hours=1))

    record = build_portfolio_counterfactual([_slot()], {"intent-1": [late]})[0]

    assert record.substitute_symbol is None
    assert ("NVDA", "CANDIDATE_LOOKAHEAD") in record.rejected_candidates
    assert record.reason_code == "NO_SUBSTITUTE_AVAILABLE"


def test_una_universe_non_point_in_time_squalifica_il_candidato():
    drifted = _candidate(universe_as_of=EXIT_AT + timedelta(minutes=1))

    record = build_portfolio_counterfactual([_slot()], {"intent-1": [drifted]})[0]

    assert record.substitute_symbol is None
    assert (
        "NVDA",
        "CANDIDATE_UNIVERSE_NOT_POINT_IN_TIME",
    ) in record.rejected_candidates


def test_la_collisione_s1_esclude_il_candidato():
    record = build_portfolio_counterfactual(
        [_slot()], {"intent-1": [_candidate(collides_with_s1=True)]}
    )[0]

    assert record.substitute_symbol is None
    assert ("NVDA", "CANDIDATE_S1_COLLISION") in record.rejected_candidates


def test_il_capitale_non_investibile_non_produce_un_sostituto():
    record = build_portfolio_counterfactual(
        [_slot()],
        {
            "intent-1": [
                _candidate(investable=False, investable_reason="sub_share_notional")
            ]
        },
    )[0]

    assert record.substitute_symbol is None
    assert (
        "NVDA",
        "CANDIDATE_CAPITAL_NOT_INVESTABLE",
    ) in record.rejected_candidates
    assert record.reason_code == "NO_SUBSTITUTE_AVAILABLE"


def test_uno_slot_gia_chiuso_non_e_disponibile_e_non_riceve_sostituti():
    closed = _slot(slot_closes_at=EXIT_AT)

    record = build_portfolio_counterfactual([closed], {"intent-1": [_candidate()]})[0]

    assert record.slot_available is False
    assert record.reason_code == "SLOT_NOT_AVAILABLE"
    assert record.substitute_symbol is None
    assert record.capital_days == pytest.approx(0.0)


def test_un_prezzo_di_uscita_mancante_censura_il_pnl_incrementale():
    record = build_portfolio_counterfactual(
        [_slot()], {"intent-1": [_candidate(exit_price=None)]}
    )[0]

    assert record.substitute_symbol is None
    assert ("NVDA", "CANDIDATE_EXIT_PRICE_MISSING") in record.rejected_candidates


def test_il_pnl_incrementale_e_netto_dei_costi_quando_il_cost_model_e_dato():
    record = build_portfolio_counterfactual(
        [_slot()], {"intent-1": [_candidate()]}, cost_model=_CostModel()
    )[0]

    # 40 USD lordi meno 1 di ingresso e 2 di uscita
    assert record.incremental_pnl == pytest.approx(37.0)
    assert record.cost_model_version == "cost-model:test-golden"


# ── Criterio 5: le due viste si riconciliano ────────────────────────────────


def test_il_paired_misura_i_capitale_giorni_occupati_da_ciascuna_policy():
    baseline = [_outcome("P0", exit_at=EXIT_AT)]
    challenger = [
        _outcome("P1", exit_at=EXIT_AT + timedelta(days=2), net_pnl=35.0)
    ]

    pair = build_paired_comparison(baseline, challenger).pairs[0]

    # P0 esce il giorno del fill, P1 alla scadenza D+2: 0 contro 2 sedute
    assert pair.baseline_capital_days == pytest.approx(0.0)
    assert pair.challenger_capital_days == pytest.approx(2000.0)


def test_la_riconciliazione_attribuisce_la_differenza_al_reinvestimento():
    comparison = build_paired_comparison(
        [_outcome("P0", net_pnl=10.0)],
        [_outcome("P1", net_pnl=35.0, exit_at=EXIT_AT + timedelta(days=2))],
    )
    records = build_portfolio_counterfactual([_slot()], {"intent-1": [_candidate()]})

    reconciliation = reconcile_views(comparison, records, policy_id="P1")

    assert reconciliation.trade_level_net_usd == pytest.approx(25.0)
    assert reconciliation.reinvestment_usd == pytest.approx(40.0)
    assert reconciliation.portfolio_level_net_usd == pytest.approx(65.0)
    assert reconciliation.unattributed_usd == pytest.approx(0.0)
    assert reconciliation.reconciled is True
    assert reconciliation.slot_occupancy_capital_days_delta == pytest.approx(2000.0)


def test_senza_sostituto_le_due_viste_coincidono():
    comparison = build_paired_comparison(
        [_outcome("P0", net_pnl=10.0)], [_outcome("P1", net_pnl=35.0)]
    )
    records = build_portfolio_counterfactual([_slot()], {})

    reconciliation = reconcile_views(comparison, records, policy_id="P1")

    assert reconciliation.reinvestment_usd == pytest.approx(0.0)
    assert reconciliation.portfolio_level_net_usd == pytest.approx(25.0)
    assert reconciliation.reconciled is True
    assert reconciliation.idle_capital_days == pytest.approx(2000.0)


def test_un_reinvestimento_nel_paired_impedisce_la_riconciliazione():
    """Se il cash liberato ha creato un trade, il test primario non e' valido."""
    comparison = build_paired_comparison(
        [_outcome("P0")], [_outcome("P1"), _outcome("P1", intent_id="intent-nuovo")]
    )
    records = build_portfolio_counterfactual([_slot()], {})

    reconciliation = reconcile_views(comparison, records, policy_id="P1")

    assert reconciliation.reconciled is False
    assert "ENTRIES_NOT_FROZEN" in reconciliation.blocking_reasons


def test_la_riconciliazione_non_perde_le_coppie_escluse():
    comparison = build_paired_comparison(
        [_outcome("P0"), _outcome("P0", intent_id="intent-2")],
        [_outcome("P1"), _outcome("P1", intent_id="intent-2", net_pnl=None)],
    )

    reconciliation = reconcile_views(comparison, (), policy_id="P1")

    assert reconciliation.pairs_excluded == 1
    assert reconciliation.excluded_by_reason["PAIRED_NET_PNL_MISSING"] == 1


# ── Criterio 6: il report copre i quattro casi limite ───────────────────────


def test_il_report_copre_assenza_piu_sostituti_collisione_s1_e_capitale():
    slots = [
        _slot(intent_id="intent-assente"),
        _slot(intent_id="intent-multi"),
        _slot(intent_id="intent-s1"),
        _slot(intent_id="intent-capitale"),
    ]
    candidates = {
        "intent-multi": [
            _candidate(symbol="NVDA", rank=3),
            _candidate(symbol="AVGO", rank=1),
        ],
        "intent-s1": [_candidate(collides_with_s1=True)],
        "intent-capitale": [
            _candidate(investable=False, investable_reason="sub_share_notional")
        ],
    }
    baseline = [_outcome("P0", intent_id=s.intent_id) for s in slots]
    challenger = [
        _outcome("P1", intent_id=s.intent_id, net_pnl=20.0, exit_reason_code="P1_TIME_DUE")
        for s in slots
    ]

    report = build_replacement_report(
        build_paired_comparison(baseline, challenger),
        build_portfolio_counterfactual(slots, candidates),
        policy_id="P1",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
    )

    assert report["slots"]["total"] == 4
    assert report["slots"]["by_reason"] == {
        "NO_SUBSTITUTE_AVAILABLE": 3,
        "REPLACEMENT_SLOT_REALLOCATED": 1,
    }
    assert report["slots"]["substitutes_selected"] == 1
    assert report["paired"]["comparable"] == 4
    assert report["paired"]["mean_delta_bps"] == pytest.approx(100.0)
    assert report["reconciliation"]["reconciled"] is True
    assert report["policy_hierarchy"] == ["P0", "P1"]
    assert report["p2_omitted_by_contract"] is True


def test_il_report_filtra_la_finestra_di_osservazione():
    baseline = [_outcome("P0", d0=date(2026, 7, 1))]
    challenger = [_outcome("P1", d0=date(2026, 7, 1), net_pnl=20.0)]

    report = build_replacement_report(
        build_paired_comparison(baseline, challenger),
        (),
        policy_id="P1",
        window_start=date(2026, 8, 1),
        window_end=date(2026, 8, 31),
    )

    assert report["paired"]["comparable"] == 0


def test_il_report_rifiuta_una_finestra_invertita():
    with pytest.raises(ValueError, match="window ends before it starts"):
        build_replacement_report(
            build_paired_comparison([], []),
            (),
            policy_id="P1",
            window_start=date(2026, 8, 31),
            window_end=date(2026, 8, 1),
        )


def test_un_sostituto_su_uno_slot_non_appaiato_resta_non_attribuito():
    """Un P&L di replacement che non tocca una coppia comparabile e' un residuo."""
    comparison = build_paired_comparison(
        [_outcome("P0", net_pnl=10.0)], [_outcome("P1", net_pnl=35.0)]
    )
    records = build_portfolio_counterfactual(
        [_slot(intent_id="intent-non-appaiato")],
        {"intent-non-appaiato": [_candidate()]},
    )

    reconciliation = reconcile_views(comparison, records, policy_id="P1")

    assert reconciliation.reinvestment_usd == pytest.approx(0.0)
    assert reconciliation.unattributed_usd == pytest.approx(40.0)
    assert reconciliation.reconciled is False
    assert "UNATTRIBUTED_RESIDUAL" in reconciliation.blocking_reasons
    # la vista portfolio-level continua a mostrare il totale, non lo nasconde
    assert reconciliation.portfolio_level_net_usd == pytest.approx(65.0)
