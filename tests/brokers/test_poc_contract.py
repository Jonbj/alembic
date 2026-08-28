"""Test del contratto PoC secondo broker e del suo valutatore (#363).

Il valutatore esiste per una ragione sola: impedire che il verdetto venga
adattato a posteriori al broker preferito. I test sono quindi scritti come
tentativi di adattamento — un'evidenza non raccolta spacciata per successo, una
dimensione LIVE dichiarata provata in SIM, un paniere incompleto con il mapping
dichiarato `PASS` — e verificano che il contratto li rifiuti.
"""

from dataclasses import replace

import pytest

from src.brokers.poc_contract import (
    ENV_DOC,
    ENV_LIVE_ORDER,
    ENV_LIVE_READONLY,
    ENV_OPERATOR,
    ENV_SIM,
    KIND_BLOCKING,
    KIND_GRADED,
    RECOMMEND_ALPACA_ONLY,
    RECOMMEND_IBKR,
    RECOMMEND_NO_DECISION,
    RECOMMEND_SAXO,
    STATUS_FAIL,
    STATUS_NOT_TESTED,
    STATUS_PASS,
    VERDICT_CONDITIONAL_PASS,
    VERDICT_FAIL,
    VERDICT_PASS,
    DimensionOutcome,
    PocResult,
    compare_candidates,
    evaluate_broker,
    load_poc_contract,
)


@pytest.fixture(scope="module")
def contract():
    return load_poc_contract()


def _full_pass_result(contract, broker, **overrides):
    """Report che passa tutto: la base da cui i test rimuovono un pezzo alla volta."""
    outcomes = tuple(
        DimensionOutcome(
            dimension_id=dim_id,
            status=STATUS_PASS,
            environment=contract.dimensions[dim_id].verifiable_in[0],
            evidence_ref=f"poc/{broker}/{dim_id.lower()}.jsonl",
        )
        for dim_id in contract.dimensions
    )
    payload = {
        "broker": broker,
        "contract_version": contract.version,
        "contract_source_hash": contract.source_hash,
        "outcomes": outcomes,
        "kill_criteria_tripped": (),
        "resolved_slot_ids": tuple(s.id for s in contract.basket),
        "metrics": {tb.metric: tb.best_possible for tb in contract.tie_breakers},
    }
    payload.update(overrides)
    return PocResult(**payload)


# ── Il contratto congelato ───────────────────────────────────────────────────


def test_il_contratto_copre_i_mercati_richiesti_dalla_issue(contract):
    """Italia, Xetra, Euronext, LSE, USA e almeno un mercato APAC, obbligatori."""
    mandatory_mics = {s.mic for s in contract.basket if s.mandatory}
    assert {"XMIL", "XETR", "XPAR", "XLON"} <= mandatory_mics
    assert mandatory_mics & {"XNAS", "XNYS"}, "manca lo slot USA"
    assert mandatory_mics & {"XJPX", "XHKG"}, "manca il mercato APAC"


def test_ogni_slot_dichiara_asset_class_e_valuta(contract):
    for slot in contract.basket:
        assert slot.asset_class, slot.id
        assert slot.currency, slot.id


def test_lo_scenario_di_timeout_ambiguo_e_bloccante(contract):
    """`submit -> timeout ambiguo -> reconcile` non può essere una dimensione pesata."""
    ambiguous = contract.dimensions[contract.ambiguous_timeout_dimension]
    assert ambiguous.kind == KIND_BLOCKING
    assert ambiguous.feeds_final_gate


def test_il_contratto_non_ammette_nessun_ordine_live(contract):
    """Il vincolo «nessun ordine live» è nel contratto, non solo nella prosa."""
    for dim in contract.dimensions.values():
        assert ENV_LIVE_ORDER not in dim.verifiable_in, dim.id


def test_lo_stesso_contratto_si_applica_a_saxo_e_ibkr(contract):
    assert contract.brokers == ("saxo", "ibkr")
    # Nessuna dimensione è riservata a un solo candidato: sarebbe un contratto
    # diverso per broker, cioè esattamente ciò che la issue vuole impedire.
    assert contract.dimensions
    # I kill criteria, invece, sono per costruzione anche broker-specifici.
    scopes = {k.applies_to for k in contract.kill_criteria.values()}
    assert ("saxo", "ibkr") in scopes
    assert ("saxo",) in scopes
    assert ("ibkr",) in scopes


def test_ogni_dimensione_dichiara_se_alimenta_il_gate_finale(contract):
    assert contract.gate_evidence_ids()
    assert set(contract.gate_evidence_ids()) <= set(contract.dimensions)


def test_le_contingenze_sono_nominate_senza_poc_autorizzato(contract):
    """USA/locali nominate, ma nessuna promossa a PoC da questo documento."""
    assert contract.contingencies
    for name, contingency in contract.contingencies.items():
        assert contingency.trigger, name
        assert contingency.poc_authorized is False, name


def test_le_dimensioni_bloccanti_e_pesate_sono_disgiunte_e_complete(contract):
    blocking, graded = set(contract.blocking_ids()), set(contract.graded_ids())
    assert not blocking & graded
    assert blocking | graded == set(contract.dimensions)
    for dim in contract.dimensions.values():
        assert dim.kind in (KIND_BLOCKING, KIND_GRADED)


# ── Verdetto per singolo candidato ───────────────────────────────────────────


def test_report_completo_passa(contract):
    verdict = evaluate_broker(contract, _full_pass_result(contract, "saxo"))
    assert verdict.verdict == VERDICT_PASS
    assert verdict.residual_risks == ()


def test_un_hash_di_contratto_diverso_e_rifiutato(contract):
    """Un report prodotto su un contratto modificato non è confrontabile."""
    result = _full_pass_result(contract, "saxo", contract_source_hash="deadbeef")
    with pytest.raises(ValueError, match="contract_source_hash"):
        evaluate_broker(contract, result)


def test_una_versione_di_contratto_diversa_e_rifiutata(contract):
    result = _full_pass_result(contract, "saxo", contract_version="0.0.1")
    with pytest.raises(ValueError, match="contract_version"):
        evaluate_broker(contract, result)


def test_dimensione_bloccante_non_testata_e_un_fail_non_un_conditional(contract):
    """«Non l'abbiamo provato» non è un successo parziale: è un fallimento."""
    target = contract.blocking_ids()[0]
    base = _full_pass_result(contract, "saxo")
    outcomes = tuple(
        replace(o, status=STATUS_NOT_TESTED) if o.dimension_id == target else o
        for o in base.outcomes
    )
    verdict = evaluate_broker(contract, replace(base, outcomes=outcomes))
    assert verdict.verdict == VERDICT_FAIL
    assert target in verdict.not_tested


def test_dimensione_pesata_non_testata_e_rischio_residuo_mai_un_pass(contract):
    target = contract.graded_ids()[0]
    base = _full_pass_result(contract, "saxo")
    outcomes = tuple(
        replace(o, status=STATUS_NOT_TESTED) if o.dimension_id == target else o
        for o in base.outcomes
    )
    verdict = evaluate_broker(contract, replace(base, outcomes=outcomes))
    assert verdict.verdict == VERDICT_CONDITIONAL_PASS
    assert any(target in risk for risk in verdict.residual_risks)


def test_dimensione_assente_dal_report_diventa_non_testata(contract):
    """Omettere una dimensione non la fa sparire dal conteggio."""
    target = contract.blocking_ids()[-1]
    base = _full_pass_result(contract, "saxo")
    outcomes = tuple(o for o in base.outcomes if o.dimension_id != target)
    verdict = evaluate_broker(contract, replace(base, outcomes=outcomes))
    assert verdict.verdict == VERDICT_FAIL
    assert target in verdict.not_tested
    assert any("absent_from_report" in note for note in verdict.notes)


def test_dimensione_sconosciuta_nel_report_e_un_errore(contract):
    base = _full_pass_result(contract, "saxo")
    extra = DimensionOutcome("D-INVENTATA", STATUS_PASS, ENV_SIM)
    with pytest.raises(ValueError, match="D-INVENTATA"):
        evaluate_broker(contract, replace(base, outcomes=base.outcomes + (extra,)))


def test_dimensione_duplicata_nel_report_e_un_errore(contract):
    base = _full_pass_result(contract, "saxo")
    with pytest.raises(ValueError, match="duplicat"):
        evaluate_broker(
            contract, replace(base, outcomes=base.outcomes + (base.outcomes[0],))
        )


def test_un_fatto_operatore_dichiarato_provato_in_sim_non_conta(contract):
    """Il costo contrattuale italiano non si dimostra su SIM."""
    target = next(
        d.id
        for d in contract.dimensions.values()
        if ENV_SIM not in d.verifiable_in and ENV_OPERATOR in d.verifiable_in
    )
    base = _full_pass_result(contract, "saxo")
    outcomes = tuple(
        replace(o, environment=ENV_SIM) if o.dimension_id == target else o
        for o in base.outcomes
    )
    verdict = evaluate_broker(contract, replace(base, outcomes=outcomes))
    assert target in verdict.not_tested
    assert any("environment_not_admitted" in note for note in verdict.notes)


def test_paniere_incompleto_forza_il_fail_del_mapping(contract):
    """Uno slot obbligatorio non risolto non si compensa dichiarando `PASS`."""
    base = _full_pass_result(contract, "saxo")
    missing = contract.mandatory_slot_ids()[0]
    kept = tuple(s for s in base.resolved_slot_ids if s != missing)
    verdict = evaluate_broker(contract, replace(base, resolved_slot_ids=kept))
    assert verdict.verdict == VERDICT_FAIL
    assert contract.basket_gate_dimension in verdict.blocking_failed
    assert any(missing in note for note in verdict.notes)


def test_un_kill_criterion_scattato_annulla_ogni_altro_pass(contract):
    kill_id = next(
        k.id for k in contract.kill_criteria.values() if k.applies_to == ("saxo", "ibkr")
    )
    base = _full_pass_result(contract, "saxo", kill_criteria_tripped=(kill_id,))
    verdict = evaluate_broker(contract, base)
    assert verdict.verdict == VERDICT_FAIL
    assert verdict.kills_tripped == (kill_id,)


def test_un_kill_criterion_di_un_altro_broker_e_un_errore(contract):
    saxo_only = next(
        k.id for k in contract.kill_criteria.values() if k.applies_to == ("saxo",)
    )
    base = _full_pass_result(contract, "ibkr", kill_criteria_tripped=(saxo_only,))
    with pytest.raises(ValueError, match=saxo_only):
        evaluate_broker(contract, base)


def test_broker_fuori_contratto_e_un_errore(contract):
    base = replace(_full_pass_result(contract, "saxo"), broker="tradier")
    with pytest.raises(ValueError, match="tradier"):
        evaluate_broker(contract, base)


# ── Confronto fra candidati ──────────────────────────────────────────────────


def _conditional(contract, broker, graded_failed_count, metrics=None):
    """Report che passa tutto il bloccante e fallisce N dimensioni pesate."""
    base = _full_pass_result(contract, broker)
    to_fail = set(contract.graded_ids()[:graded_failed_count])
    outcomes = tuple(
        replace(o, status=STATUS_FAIL) if o.dimension_id in to_fail else o
        for o in base.outcomes
    )
    result = replace(base, outcomes=outcomes)
    if metrics is not None:
        result = replace(result, metrics={**base.metrics, **metrics})
    return evaluate_broker(contract, result)


def test_un_solo_candidato_passa_e_vince(contract):
    saxo = evaluate_broker(contract, _full_pass_result(contract, "saxo"))
    ibkr = _conditional(contract, "ibkr", 0)
    ibkr = replace(ibkr, verdict=VERDICT_FAIL)
    comparison = compare_candidates(contract, (saxo, ibkr))
    assert comparison.recommendation == RECOMMEND_SAXO


def test_se_nessun_candidato_passa_si_resta_su_alpaca(contract):
    saxo = replace(
        evaluate_broker(contract, _full_pass_result(contract, "saxo")),
        verdict=VERDICT_FAIL,
    )
    ibkr = replace(
        evaluate_broker(contract, _full_pass_result(contract, "ibkr")),
        verdict=VERDICT_FAIL,
    )
    comparison = compare_candidates(contract, (saxo, ibkr))
    assert comparison.recommendation == RECOMMEND_ALPACA_ONLY
    # Il gate non promuove da sé una contingenza: è una decisione dell'operatore.
    assert any("contingen" in r for r in comparison.rationale)


def test_due_conditional_si_ordinano_col_primo_tie_breaker_del_contratto(contract):
    saxo = _conditional(contract, "saxo", 2)
    ibkr = _conditional(contract, "ibkr", 1)
    comparison = compare_candidates(contract, (saxo, ibkr))
    assert comparison.recommendation == RECOMMEND_IBKR
    assert comparison.tie_breaker_used == contract.tie_breakers[0].metric


def test_due_conditional_identici_non_producono_un_vincitore(contract):
    """Un pareggio pieno è NO_DECISION: il valutatore non inventa un preferito."""
    saxo = _conditional(contract, "saxo", 1)
    ibkr = _conditional(contract, "ibkr", 1)
    comparison = compare_candidates(contract, (saxo, ibkr))
    assert comparison.recommendation == RECOMMEND_NO_DECISION
    assert comparison.winner is None


def test_una_metrica_di_tie_break_assente_conta_come_peggiore(contract):
    """Non misurare un tie-breaker non può essere un vantaggio."""
    later = contract.tie_breakers[-1]
    saxo = _conditional(contract, "saxo", 1)
    saxo = replace(saxo, metrics={k: v for k, v in saxo.metrics.items() if k != later.metric})
    ibkr = _conditional(contract, "ibkr", 1)
    comparison = compare_candidates(contract, (saxo, ibkr))
    assert comparison.recommendation == RECOMMEND_IBKR
    assert comparison.tie_breaker_used == later.metric


def test_il_confronto_rifiuta_verdetti_dello_stesso_broker(contract):
    saxo_a = _conditional(contract, "saxo", 1)
    saxo_b = _conditional(contract, "saxo", 2)
    with pytest.raises(ValueError, match="saxo"):
        compare_candidates(contract, (saxo_a, saxo_b))


def test_il_confronto_rifiuta_un_candidato_mancante(contract):
    saxo = _conditional(contract, "saxo", 1)
    with pytest.raises(ValueError, match="ibkr"):
        compare_candidates(contract, (saxo,))
