"""#299: valutatore confirmatory appaiato del trial exit S4.

Il valutatore va costruito e testato **prima** di leggere gli esiti forward:
per questo tutto qui gira su dati sintetici e su boundary espliciti, non su una
finestra reale.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.strategies.s4.paired_evaluator import (
    OUTCOME_INCONCLUSIVE,
    OUTCOME_NOT_TESTED,
    OUTCOME_PROMOTE,
    OUTCOME_REJECT,
    BootstrapScheme,
    PairedObservation,
    TrialLedger,
    bootstrap_paired_delta,
    derive_n_cluster,
    economic_metrics,
    evaluate_hierarchy,
    exit_quality,
    risk_metrics,
    safety_halt,
)

SCHEME = BootstrapScheme(kind="block", block_length=2, resamples=2000, seed=20260827)
D0 = date(2026, 9, 1)


def _obs(
    index: int,
    delta_bps: float,
    *,
    event_day: date | None = None,
    **overrides,
) -> PairedObservation:
    values = {
        "intent_id": f"intent-{index}",
        "event_day": event_day or (D0 + timedelta(days=index)),
        "challenger_policy_id": "P1",
        "baseline_policy_id": "P0",
        "delta_bps": delta_bps,
        "delta_usd": delta_bps / 10_000.0 * 1000.0,
        "initial_notional": 1000.0,
    }
    values.update(overrides)
    return PairedObservation(**values)


def _sample(deltas, **overrides):
    return tuple(_obs(i, d, **overrides) for i, d in enumerate(deltas))


# ── Criterio 2: bootstrap a blocchi su cluster event-day ───────────────────


def test_il_bootstrap_ricampiona_cluster_event_day_non_singoli_intenti():
    """Due intenti dello stesso evento non sono due repliche indipendenti."""
    stesso_evento = (
        _obs(0, 40.0, event_day=D0),
        _obs(1, 40.0, event_day=D0),
        _obs(2, 40.0, event_day=D0),
        _obs(3, -10.0, event_day=D0 + timedelta(days=1)),
    )

    interval = bootstrap_paired_delta(stesso_evento, SCHEME)

    assert interval.clusters == 2
    assert interval.observations == 4


def test_lo_stesso_schema_e_seed_danno_lo_stesso_intervallo():
    """Schema e seed sono congelati ex ante: il risultato non puo' variare."""
    campione = _sample([12.0, 40.0, -5.0, 33.0, 18.0, 27.0, -2.0, 51.0])

    primo = bootstrap_paired_delta(campione, SCHEME)
    secondo = bootstrap_paired_delta(campione, SCHEME)

    assert primo.lcb == pytest.approx(secondo.lcb)
    assert primo.ucb == pytest.approx(secondo.ucb)


def test_l_intervallo_e_unilaterale_al_95_percento():
    campione = _sample([12.0, 40.0, -5.0, 33.0, 18.0, 27.0, -2.0, 51.0])

    interval = bootstrap_paired_delta(campione, SCHEME)

    assert interval.alpha == pytest.approx(0.05)
    assert interval.tail == "one_sided"
    assert interval.lcb < interval.point < interval.ucb


def test_la_copertura_del_bootstrap_e_verificata_su_dati_sintetici():
    """Coverage empirica del limite inferiore su un vero positivo noto."""
    import random

    rng = random.Random(7)
    vero = 30.0
    coperti = 0
    prove = 200
    for _ in range(prove):
        campione = tuple(
            _obs(i, rng.gauss(vero, 20.0)) for i in range(40)
        )
        interval = bootstrap_paired_delta(
            campione,
            BootstrapScheme(
                kind="block", block_length=2, resamples=400, seed=rng.randrange(10**6)
            ),
        )
        if interval.lcb <= vero <= interval.ucb:
            coperti += 1

    # Nominale 95% per lato; con n=40 cluster la copertura empirica non deve
    # collassare. La soglia e' larga apposta: qui si cerca un errore di
    # costruzione, non la seconda cifra decimale.
    assert coperti / prove > 0.85


def test_un_campione_senza_cluster_non_produce_un_intervallo():
    with pytest.raises(ValueError, match="at least one event-day cluster"):
        bootstrap_paired_delta((), SCHEME)


# ── Criterio 3: N_cluster derivato, mai le 213 sedute ──────────────────────


def test_n_cluster_deriva_da_mde_varianza_potenza_e_dipendenza():
    n = derive_n_cluster(
        mde_bps=25.0,
        sigma_delta_bps=60.0,
        alpha=0.05,
        power=0.90,
        dependence_inflation=1.3,
        missingness_rate=0.10,
    )

    # ((1.6449 + 1.2816) × 60 / 25)² ≈ 49.3 → 50, × 1.3 = 65, / 0.9 ≈ 72.3 → 73
    assert n == 73


def test_una_varianza_piu_alta_richiede_piu_cluster():
    base = dict(mde_bps=25.0, alpha=0.05, power=0.90, dependence_inflation=1.0, missingness_rate=0.0)

    assert derive_n_cluster(sigma_delta_bps=90.0, **base) > derive_n_cluster(
        sigma_delta_bps=60.0, **base
    )


def test_n_cluster_rifiuta_un_mde_non_positivo():
    with pytest.raises(ValueError, match="MDE"):
        derive_n_cluster(
            mde_bps=0.0,
            sigma_delta_bps=60.0,
            alpha=0.05,
            power=0.90,
            dependence_inflation=1.0,
            missingness_rate=0.0,
        )


def test_le_213_sedute_non_sono_un_n_cluster():
    """Sono una stima di numerosita' per l'IC: il paired delta ha varianza propria."""
    n = derive_n_cluster(
        mde_bps=25.0,
        sigma_delta_bps=60.0,
        alpha=0.05,
        power=0.90,
        dependence_inflation=1.0,
        missingness_rate=0.0,
    )

    assert n != 213


# ── Criterio 6: boundary di PROMOTE, REJECT e INCONCLUSIVE ─────────────────


def test_promote_richiede_lcb_strettamente_sopra_l_mde():
    """`LCB95 > MDE`: l'uguaglianza non promuove."""
    risultato = evaluate_hierarchy(
        _sample([60.0] * 40),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
    )

    assert risultato.steps[0].outcome == OUTCOME_PROMOTE
    assert risultato.steps[0].interval.lcb > 25.0


def test_reject_quando_l_ucb_non_supera_l_mde():
    risultato = evaluate_hierarchy(
        _sample([-40.0] * 40),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
    )

    assert risultato.steps[0].outcome == OUTCOME_REJECT
    assert risultato.steps[0].interval.ucb <= 25.0


def test_inconclusive_quando_l_intervallo_attraversa_l_mde():
    risultato = evaluate_hierarchy(
        _sample([10.0, 60.0, -30.0, 80.0, 5.0, 45.0, -20.0, 70.0] * 5),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
    )

    step = risultato.steps[0]
    assert step.outcome == OUTCOME_INCONCLUSIVE
    assert step.interval.lcb <= 25.0 <= step.interval.ucb


def test_inconclusive_non_e_equivalenza_ne_autorizzazione():
    risultato = evaluate_hierarchy(
        _sample([10.0, 60.0, -30.0, 80.0, 5.0, 45.0, -20.0, 70.0] * 5),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
    )

    assert risultato.promoted_policy_id is None
    assert risultato.steps[0].equivalence_declared is False
    assert "not_equivalence" in risultato.steps[0].notes


@pytest.mark.parametrize(
    "lcb_target,ucb_atteso",
    [(25.0, OUTCOME_INCONCLUSIVE)],
)
def test_lcb_esattamente_sull_mde_non_promuove(lcb_target, ucb_atteso):
    """Boundary golden: `LCB == MDE` e' inconclusive, non promote."""
    from src.strategies.s4.paired_evaluator import classify_outcome

    assert classify_outcome(lcb=25.0, ucb=90.0, mde=25.0) == ucb_atteso
    assert classify_outcome(lcb=25.0001, ucb=90.0, mde=25.0) == OUTCOME_PROMOTE


def test_ucb_esattamente_sull_mde_e_reject():
    """Boundary golden: `UCB <= MDE` e' reject, l'uguaglianza include."""
    from src.strategies.s4.paired_evaluator import classify_outcome

    assert classify_outcome(lcb=-40.0, ucb=25.0, mde=25.0) == OUTCOME_REJECT
    assert classify_outcome(lcb=-40.0, ucb=25.0001, mde=25.0) == OUTCOME_INCONCLUSIVE


# ── Criterio 4: gerarchia chiusa ───────────────────────────────────────────


def test_p2_non_viene_testata_se_p1_non_supera_il_gate():
    risultato = evaluate_hierarchy(
        _sample([-40.0] * 40),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
        counter_observations=_sample([80.0] * 40, challenger_policy_id="P2", baseline_policy_id="P1"),
        mde_counter_bps=0.0,
    )

    assert risultato.steps[0].outcome == OUTCOME_REJECT
    assert risultato.steps[1].outcome == OUTCOME_NOT_TESTED
    assert "P1_did_not_pass" in risultato.steps[1].notes
    assert risultato.promoted_policy_id is None


def test_p2_viene_testata_solo_dopo_una_p1_promossa():
    risultato = evaluate_hierarchy(
        _sample([60.0] * 40),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
        counter_observations=_sample([80.0] * 40, challenger_policy_id="P2", baseline_policy_id="P1"),
        mde_counter_bps=0.0,
    )

    assert risultato.steps[0].outcome == OUTCOME_PROMOTE
    assert risultato.steps[1].outcome == OUTCOME_PROMOTE
    assert risultato.promoted_policy_id == "P2"


def test_senza_mde_counter_fissato_p2_non_e_testabile():
    """`MDE_counter` e' null nel contratto finche' P2 resta omitted."""
    risultato = evaluate_hierarchy(
        _sample([60.0] * 40),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
        counter_observations=_sample([80.0] * 40, challenger_policy_id="P2", baseline_policy_id="P1"),
        mde_counter_bps=None,
    )

    assert risultato.steps[1].outcome == OUTCOME_NOT_TESTED
    assert "MDE_counter_not_fixed" in risultato.steps[1].notes
    assert risultato.promoted_policy_id == "P1"


# ── Criterio 7: nessuna promozione anticipata, safety halt distinto ────────


def test_sotto_n_cluster_non_esiste_una_decisione():
    """Nessun early efficacy stop: l'analisi decisionale avviene una volta sola."""
    risultato = evaluate_hierarchy(
        _sample([200.0] * 10),
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=40,
    )

    assert risultato.decision_due is False
    assert risultato.steps[0].outcome == OUTCOME_NOT_TESTED
    assert "below_n_cluster" in risultato.steps[0].notes
    assert risultato.promoted_policy_id is None


def test_un_safety_halt_e_distinto_da_un_reject_ed_e_motivato():
    halt = safety_halt(reason="broker outage 2026-09-03", documented_at=D0)

    assert halt.outcome != OUTCOME_REJECT
    assert halt.is_safety_halt is True
    assert halt.reason == "broker outage 2026-09-03"


def test_un_safety_halt_senza_motivo_e_rifiutato():
    with pytest.raises(ValueError, match="documented reason"):
        safety_halt(reason="   ", documented_at=D0)


# ── Criterio 5: trial ledger append-only ───────────────────────────────────


def test_il_ledger_registra_ogni_variante_vista():
    ledger = TrialLedger()
    ledger.record("delta1_P1_vs_P0", role="confirmatory")
    ledger.record("D+1", role="diagnostic")
    ledger.record("D+3", role="diagnostic")

    assert [entry.name for entry in ledger.entries] == [
        "delta1_P1_vs_P0",
        "D+1",
        "D+3",
    ]


def test_una_diagnostica_non_diventa_confirmatory_per_rinomina():
    ledger = TrialLedger()

    with pytest.raises(ValueError, match="diagnostic"):
        ledger.record("D+1", role="confirmatory")
    with pytest.raises(ValueError, match="diagnostic"):
        ledger.record("decomposizione intraday/overnight", role="confirmatory")


def test_il_ledger_e_append_only():
    ledger = TrialLedger()
    ledger.record("delta1_P1_vs_P0", role="confirmatory")

    with pytest.raises(TypeError):
        ledger.entries[0] = None  # type: ignore[index]


# ── Criterio 1: metriche con denominatori congelati ────────────────────────


def test_le_metriche_economiche_usano_il_notional_iniziale_come_denominatore():
    campione = (
        _obs(0, 100.0, delta_usd=10.0, initial_notional=1000.0),
        _obs(1, -50.0, delta_usd=-10.0, initial_notional=2000.0),
    )

    metriche = economic_metrics(campione)

    assert metriche["mean_delta_bps"] == pytest.approx(25.0)
    assert metriche["net_delta_usd"] == pytest.approx(0.0)
    assert metriche["hit_rate"] == pytest.approx(0.5)
    assert metriche["denominator"] == "initial_notional"


def test_le_metriche_di_rischio_riportano_downside_es_e_drawdown():
    campione = _sample([50.0, -80.0, 30.0, -120.0, 10.0, 60.0, -40.0, 20.0])

    metriche = risk_metrics(campione, es_level=0.25)

    assert metriche["downside_deviation_bps"] > 0
    assert metriche["expected_shortfall_bps"] < 0
    assert metriche["max_drawdown_bps"] > 0
    assert metriche["worst_trade_bps"] == pytest.approx(-120.0)


def test_l_expected_shortfall_e_la_media_della_coda_non_il_minimo():
    campione = _sample([-100.0, -60.0, 10.0, 20.0])

    metriche = risk_metrics(campione, es_level=0.5)

    assert metriche["expected_shortfall_bps"] == pytest.approx(-80.0)


def test_la_qualita_dell_uscita_separa_false_exit_e_recovery():
    campione = (
        _obs(0, 10.0, false_exit=True, recovered_within_horizon=True, giveback_from_mfe_bps=30.0),
        _obs(1, 20.0, false_exit=True, recovered_within_horizon=False, giveback_from_mfe_bps=10.0),
        _obs(2, 30.0, false_exit=False, recovered_within_horizon=False, giveback_from_mfe_bps=0.0),
        _obs(3, 40.0, false_exit=False, recovered_within_horizon=False, giveback_from_mfe_bps=5.0),
    )

    metriche = exit_quality(campione)

    assert metriche["false_exit_rate"] == pytest.approx(0.5)
    assert metriche["recovery_within_horizon_rate"] == pytest.approx(0.5)
    assert metriche["mean_giveback_from_mfe_bps"] == pytest.approx(11.25)


def test_i_capitale_giorni_e_la_quota_overnight_restano_riportati_a_parte():
    campione = (
        _obs(0, 10.0, capital_days=2000.0, overnight_pnl_usd=4.0, delta_usd=10.0),
        _obs(1, 20.0, capital_days=1000.0, overnight_pnl_usd=-1.0, delta_usd=20.0),
    )

    metriche = economic_metrics(campione)

    assert metriche["capital_days"] == pytest.approx(3000.0)
    assert metriche["return_on_occupied_capital_bps"] is not None
    assert metriche["overnight_share"] == pytest.approx(0.1)
