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
    # `N_cluster` e `MDE_counter` sono ancora da fissare: il contratto lo dice
    assert settings.n_cluster is None
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
