"""#299: dai delta appaiati delle viste agli input del valutatore.

Il ponte e' l'unico punto in cui una vista descrittiva diventa una statistica
decisionale: se sbaglia il cluster o lascia passare una coppia non comparabile,
l'intervallo si stringe senza che nessuno se ne accorga.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from src.strategies.s4.counterfactual import PairedDelta
from src.strategies.s4.evaluator_bridge import (
    load_evaluation_settings,
    observations_from_pairs,
    run_evaluation,
)
from src.strategies.s4.paired_evaluator import (
    OUTCOME_NOT_TESTED,
    OUTCOME_PROMOTE,
    BootstrapScheme,
)

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "config" / "s4_exit_trial.yaml"
SCHEME = BootstrapScheme(kind="block", block_length=2, resamples=500, seed=20260827)
D0 = date(2026, 8, 25)


_UNSET = object()


def _pair(
    index: int,
    *,
    d0=_UNSET,
    delta_usd: float | None = 10.0,
    comparable: bool = True,
    reasons: tuple[str, ...] = (),
    baseline_exit_cost_usd: float | None = None,
    challenger_exit_cost_usd: float | None = None,
) -> PairedDelta:
    notional = 1000.0
    return PairedDelta(
        intent_id=f"intent-{index}",
        symbol="AMD",
        # Sentinella, non `or`: `d0=None` e' un caso da testare, non un default
        # da rimpiazzare.
        d0=(D0 + timedelta(days=index)) if d0 is _UNSET else d0,
        policy_id="P1",
        baseline_policy_id="P0",
        initial_notional=notional,
        baseline_net_pnl=0.0,
        challenger_net_pnl=delta_usd,
        delta_usd=delta_usd,
        delta_bps=None if delta_usd is None else delta_usd / notional * 10_000.0,
        baseline_exit_family="freshness_or_silence",
        challenger_exit_family="time_stop",
        baseline_capital_days=1000.0,
        challenger_capital_days=2000.0,
        comparable=comparable,
        exclusion_reasons=reasons,
        baseline_exit_cost_usd=baseline_exit_cost_usd,
        challenger_exit_cost_usd=challenger_exit_cost_usd,
    )


# ── Solo cio' che e' misurabile entra nella statistica ──────────────────────


def test_solo_le_coppie_comparabili_diventano_osservazioni():
    """Una coppia esclusa non ha delta: contarla come zero sarebbe inventare."""
    pairs = (
        _pair(0),
        _pair(1, delta_usd=None, comparable=False, reasons=("PAIRED_NET_PNL_MISSING",)),
        _pair(2),
    )

    observations = observations_from_pairs(pairs, policy_id="P1")

    assert [obs.intent_id for obs in observations] == ["intent-0", "intent-2"]


def test_una_coppia_di_un_altra_policy_non_entra_nel_confronto():
    altra = _pair(3)
    object.__setattr__(altra, "policy_id", "P2")

    assert observations_from_pairs((altra,), policy_id="P1") == ()


def test_una_coppia_senza_d0_non_ha_un_cluster_e_resta_fuori():
    """Senza event-day non si sa a quale shock appartiene: non e' assegnabile."""
    observations = observations_from_pairs((_pair(0, d0=None),), policy_id="P1")

    assert observations == ()


def test_il_delta_e_i_capitale_giorni_arrivano_intatti():
    [observation] = observations_from_pairs((_pair(0, delta_usd=25.0),), policy_id="P1")

    assert observation.delta_bps == pytest.approx(250.0)
    assert observation.delta_usd == pytest.approx(25.0)
    assert observation.initial_notional == pytest.approx(1000.0)
    # Capitale-giorni della challenger: e' la sua occupazione a essere misurata
    assert observation.capital_days == pytest.approx(2000.0)


def test_il_costo_di_uscita_arriva_alla_coppia_come_delta():
    """I costi d'ingresso sono condivisi per contratto: il delta dei costi e'
    tutto nella gamba d'uscita, che il ponte espone invece di tenerla scontata
    dentro `net_pnl`."""
    pairs = (
        _pair(0, baseline_exit_cost_usd=2.0, challenger_exit_cost_usd=3.5),
        _pair(1),
    )

    observations = observations_from_pairs(pairs, policy_id="P1")

    assert observations[0].exit_cost_delta_usd == pytest.approx(1.5)
    # Un costo mancante resta un ignoto, non uno zero
    assert observations[1].exit_cost_delta_usd is None


# ── Il cluster e' l'event-day, con il suo limite dichiarato ────────────────


def test_intenti_dello_stesso_d0_finiscono_nello_stesso_cluster():
    pairs = (_pair(0, d0=D0), _pair(1, d0=D0), _pair(2, d0=D0 + timedelta(days=1)))

    observations = observations_from_pairs(pairs, policy_id="P1")
    giorni = {obs.event_day for obs in observations}

    assert len(observations) == 3
    assert len(giorni) == 2


def test_il_proxy_event_day_e_dichiarato_nel_risultato():
    """`d0` e' la seduta del fill, non l'evento: il report deve ammetterlo."""
    result = run_evaluation(
        (_pair(i) for i in range(6)),
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=4,
    )

    assert result["cluster_unit"] == "d0_session"
    assert "proxy" in result["cluster_caveat"]


# ── Senza N_cluster non esiste una decisione ───────────────────────────────


def test_un_n_cluster_non_ancora_derivato_non_produce_un_esito():
    """`N_cluster: null` nel contratto: la raccolta non ha ancora un traguardo."""
    result = run_evaluation(
        (_pair(i) for i in range(6)),
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=None,
    )

    assert result["decision_due"] is False
    assert result["steps"][0]["outcome"] == OUTCOME_NOT_TESTED
    assert "N_cluster_not_derived" in result["steps"][0]["notes"]
    assert result["promoted_policy_id"] is None


def test_raggiunto_n_cluster_l_esito_compare():
    result = run_evaluation(
        (_pair(i, delta_usd=100.0) for i in range(30)),
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=30,
    )

    assert result["decision_due"] is True
    assert result["steps"][0]["outcome"] == OUTCOME_PROMOTE


def test_una_finestra_senza_osservazioni_non_e_una_decisione():
    result = run_evaluation((), policy_id="P1", mde_time_bps=25.0, scheme=SCHEME, n_cluster=30)

    assert result["observations"] == 0
    assert result["clusters_observed"] == 0
    assert result["steps"][0]["outcome"] == OUTCOME_NOT_TESTED
    assert "no_comparable_pairs" in result["steps"][0]["notes"]


# ── I parametri vengono dal contratto, non dal chiamante ───────────────────


def test_le_impostazioni_arrivano_dal_contratto_congelato():
    settings = load_evaluation_settings(CONTRACT_PATH)

    assert settings.mde_time_bps == 25.0
    assert settings.alpha == 0.05
    assert settings.power == 0.90
    # `N_cluster` fissato a 5816 il 2026-09-09 (#298, milestone
    # N_CLUSTER_PROPONIBILE). `MDE_counter` resta da fissare: segue P2,
    # ancora omitted.
    assert settings.n_cluster == 5816
    assert settings.mde_counter_bps is None
    assert settings.scheme.alpha == 0.05


def test_un_contratto_che_ammettesse_un_early_stop_e_rifiutato(tmp_path):
    import yaml

    payload = yaml.safe_load(CONTRACT_PATH.read_bytes())
    payload["stopping"]["early_efficacy_stop"] = True
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload))

    with pytest.raises(ValueError, match="early efficacy stop"):
        load_evaluation_settings(path)


def test_un_contratto_che_usasse_le_213_sedute_come_n_cluster_e_rifiutato(tmp_path):
    import yaml

    payload = yaml.safe_load(CONTRACT_PATH.read_bytes())
    payload["power"]["sessions_213_is_N_cluster"] = True
    path = tmp_path / "contract.yaml"
    path.write_text(yaml.safe_dump(payload))

    with pytest.raises(ValueError, match="213"):
        load_evaluation_settings(path)


def test_il_risultato_e_serializzabile_in_json():
    import json

    result = run_evaluation(
        (_pair(i) for i in range(6)),
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=4,
    )

    assert json.loads(json.dumps(result, default=str))["clusters_observed"] == 6


# ── Le metriche §8.3 accompagnano il verdetto sulla stessa coorte ──────────


def test_il_verdetto_riporta_le_metriche_sulla_stessa_coorte():
    """Il verdetto decide su `observations`; le metriche descrivono le stesse.

    Una coorte diversa fra intervallo e metriche pubblicherebbe due campioni
    con lo stesso nome.
    """
    pairs = tuple(_pair(i, delta_usd=25.0 * (-1) ** i) for i in range(6))

    result = run_evaluation(
        pairs,
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=4,
    )

    economic = result["metrics"]["economic"]
    risk = result["metrics"]["risk"]
    assert economic["trades"] == result["observations"]
    assert economic["denominator"] == "initial_notional"
    assert economic["mean_delta_bps"] == pytest.approx(0.0)
    assert risk["worst_trade_bps"] == pytest.approx(-250.0)
    assert "downside_deviation_bps" in risk
    assert "expected_shortfall_bps" in risk
    assert "max_drawdown_bps" in risk


def test_il_verdetto_riporta_il_costo_del_delta_con_la_sua_copertura():
    pairs = (
        _pair(0, baseline_exit_cost_usd=2.0, challenger_exit_cost_usd=3.0),
        _pair(1, baseline_exit_cost_usd=1.0, challenger_exit_cost_usd=1.0),
        _pair(2),
    )

    result = run_evaluation(
        pairs,
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=2,
    )

    economic = result["metrics"]["economic"]
    # La terza coppia non ha costi: la somma non la azzera, la dichiara parziale
    assert economic["cost_delta_usd"] == pytest.approx(1.0)
    assert economic["cost_trades"] == 2


def test_un_verdetto_bloccato_riporta_metriche_vuote_non_inventate():
    """Finestra senza coppie: le metriche esistono e dicono zero, senza
    valori fittizi che sembrerebbero una misura."""
    result = run_evaluation(
        (),
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=4,
    )

    assert result["metrics"]["economic"]["trades"] == 0
    assert result["metrics"]["risk"] == {}
    assert result["metrics"]["exit_quality"] == {}


# ── La qualita' dell'uscita entra nell'osservazione quando esiste ──────────


def _quality(intent: str, **overrides):
    from src.strategies.s4.exit_quality import PairedExitQuality

    values = {
        "overnight_pnl_usd": 4.0,
        "false_exit": True,
        "recovered_within_horizon": True,
        "giveback_from_mfe_bps": 30.0,
    }
    values.update(overrides)
    return intent, PairedExitQuality(**values)


def test_la_qualita_dell_uscita_arriva_alla_coppia_che_la_ha():
    """La qualita' nasce dal path di prezzo di un intento: entra solo nella
    coppia con lo stesso nome, mai come sfondo della coorte."""
    pairs = (_pair(0), _pair(1))

    observations = observations_from_pairs(
        pairs, policy_id="P1", exit_quality=dict([_quality("intent-0")])
    )

    prima, seconda = observations
    assert prima.overnight_pnl_usd == pytest.approx(4.0)
    assert prima.false_exit is True
    assert prima.recovered_within_horizon is True
    assert prima.giveback_from_mfe_bps == pytest.approx(30.0)
    # L'intento senza path resta ignoto su tutte le quattro: non azzera le
    # medie di qualita', ne' le allarga con un favore inventato
    assert seconda.overnight_pnl_usd is None
    assert seconda.false_exit is None
    assert seconda.recovered_within_horizon is None
    assert seconda.giveback_from_mfe_bps is None


def test_il_verdetto_pubblica_la_qualita_dell_uscita_della_coorte():
    pairs = (_pair(0), _pair(1, delta_usd=30.0), _pair(2, delta_usd=40.0))
    quality = dict(
        [
            _quality("intent-0"),
            _quality(
                "intent-1",
                overnight_pnl_usd=0.0,
                false_exit=True,
                recovered_within_horizon=False,
            ),
            _quality("intent-2", overnight_pnl_usd=0.0, false_exit=False),
        ]
    )

    result = run_evaluation(
        pairs,
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=3,
        exit_quality=quality,
    )

    qualita = result["metrics"]["exit_quality"]
    assert qualita["false_exit_rate"] == pytest.approx(2 / 3)
    assert qualita["recovery_within_horizon_rate"] == pytest.approx(0.5)
    assert result["metrics"]["economic"]["overnight_share"] == pytest.approx(
        4.0 / 80.0
    )


# ── Il trial ledger registra le varianti viste (criterio 5) ────────────────


def test_il_verdetto_registra_le_varianti_viste_nel_ledger():
    """Ogni gradino valutato e' una variante vista: senza registro, la
    molteplicita' esplorata si perde e una diagnostica puo' tornare come
    confirmatory su un campione che non e' piu' out-of-sample."""
    result = run_evaluation(
        (_pair(i) for i in range(6)),
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=4,
    )

    assert result["ledger"] == [
        {
            "variant": "delta1_P1_vs_P0",
            "role": "confirmatory",
            # 6 cluster su 4 richiesti: il gradino e' valutato (non
            # `below_n_cluster`), solo non promosso — e il ledger lo dice
            "notes": ["not_equivalence"],
        }
    ]


def test_un_verdetto_bloccato_non_ha_visto_nessuna_variante():
    """Senza osservazioni non c'e' niente da registrare: un ledger con righe
    inventate dichiarerebbe una molteplicita' che il trial non ha esplorato."""
    result = run_evaluation(
        (),
        policy_id="P1",
        mde_time_bps=25.0,
        scheme=SCHEME,
        n_cluster=4,
    )

    assert result["ledger"] == []
