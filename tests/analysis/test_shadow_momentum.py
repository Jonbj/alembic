"""#451: momentum shadow sui miss NO_NEWS / THIN_NEUTRAL."""

import pytest

from src.analysis.shadow_momentum import (
    BOOTSTRAP_SEED,
    build_observations,
    summarize_observations,
)


def _dossier(day, returns, candidates=()):
    return {
        "data": day,
        "mercato": {"rendimenti": returns},
        "candidati_miss": list(candidates),
    }


def _candidate(symbol, cause, accessible, session_return=0.04):
    return {
        "symbol": symbol,
        "causa": cause,
        "return": session_return,
        "opportunity_v2": {"accessible_opportunity_usd": accessible},
    }


def test_segnale_usa_solo_le_cinque_sedute_precedenti_e_filtra_le_cause():
    dossiers = [
        _dossier("2026-08-10", {"AAA": 0.01}),
        _dossier("2026-08-11", {"AAA": 0.02}),
        _dossier("2026-08-12", {"AAA": -0.01}),
        _dossier("2026-08-13", {"AAA": 0.03}),
        _dossier("2026-08-14", {"AAA": 0.01}),
        _dossier(
            "2026-08-17",
            {"AAA": -0.90},  # outcome: non deve contaminare il segnale
            (
                _candidate("AAA", "NO_NEWS", 12.0),
                _candidate("BBB", "WRONG_SIGN", 50.0),
            ),
        ),
    ]

    observations = build_observations(dossiers, "2026-08-17", "2026-08-27")

    assert len(observations) == 1
    row = observations[0]
    expected = 1.01 * 1.02 * 0.99 * 1.03 * 1.01 - 1.0
    assert row["momentum_5d"] == pytest.approx(expected)
    assert row["intent_shadow"] == "LONG"
    assert row["history_dates"] == [
        "2026-08-10",
        "2026-08-11",
        "2026-08-12",
        "2026-08-13",
        "2026-08-14",
    ]


def test_storia_incompleta_non_viene_imputata_e_accessible_null_resta_missing():
    dossiers = [
        _dossier("2026-08-10", {"AAA": 0.01}),
        _dossier("2026-08-11", {"AAA": 0.02}),
        _dossier("2026-08-12", {}),
        _dossier("2026-08-13", {"AAA": 0.03}),
        _dossier("2026-08-14", {"AAA": 0.01}),
        _dossier(
            "2026-08-17",
            {"AAA": 0.04},
            (_candidate("AAA", "THIN_NEUTRAL", None),),
        ),
    ]

    row = build_observations(dossiers, "2026-08-17", "2026-08-27")[0]

    assert row["momentum_5d"] is None
    assert row["intent_shadow"] == "NOT_EVALUABLE"
    assert row["accessible_opportunity_usd"] is None
    assert row["positive_accessible_opportunity_usd"] is None
    assert row["missingness"] == [
        "momentum_history_incomplete",
        "accessible_opportunity_missing",
    ]


def test_momentum_nullo_o_negativo_produce_astensione():
    base = [
        _dossier("2026-08-10", {"ZERO": 0.0, "NEG": -0.01}),
        _dossier("2026-08-11", {"ZERO": 0.0, "NEG": 0.0}),
        _dossier("2026-08-12", {"ZERO": 0.0, "NEG": 0.0}),
        _dossier("2026-08-13", {"ZERO": 0.0, "NEG": 0.0}),
        _dossier("2026-08-14", {"ZERO": 0.0, "NEG": 0.0}),
        _dossier(
            "2026-08-17",
            {"ZERO": 0.04, "NEG": 0.04},
            (
                _candidate("ZERO", "NO_NEWS", 10.0),
                _candidate("NEG", "THIN_NEUTRAL", 20.0),
            ),
        ),
    ]

    rows = build_observations(base, "2026-08-17", "2026-08-27")

    assert [row["intent_shadow"] for row in rows] == ["ABSTAIN", "ABSTAIN"]


def test_manifest_usa_la_classificazione_dei_report_non_il_nome_nativo_dossier():
    history = [
        _dossier(f"2026-08-{day}", {"AAA": 0.01, "BBB": 0.01})
        for day in ("10", "11", "12", "13", "14")
    ]
    event = _dossier(
        "2026-08-17",
        {"AAA": 0.04, "BBB": 0.04},
        (
            _candidate("AAA", "BELOW_GATE", 25.0),
            _candidate("BBB", "BELOW_GATE", 30.0),
        ),
    )
    event["candidati_miss"][0]["opportunity_v2"].update(
        {
            "estimator_version": "2.0",
            "cutoff": "2026-08-17T20:00:00+00:00",
            "entry": {
                "timestamp": "2026-08-17T14:22:00+00:00",
                "bar_timestamp": "2026-08-17T14:25:00+00:00",
                "source": "intraday_open_at_first_eligible_bar",
                "eligible_cycle_source": "primo_ciclo_dopo_segnale",
            },
            "exit": {"source": "daily_close", "policy": "EOD_close"},
        }
    )
    manifest = [
        {
            "data": "2026-08-17",
            "symbol": "AAA",
            "causa": "THIN_NEUTRAL",
            "source": "docs/ALPHA_MISS_REPORT_2026-08-17.md",
        }
    ]

    rows = build_observations(
        [*history, event],
        "2026-08-17",
        "2026-08-27",
        sample_manifest=manifest,
    )

    assert len(rows) == 1
    assert rows[0]["causa"] == "THIN_NEUTRAL"
    assert rows[0]["dossier_causa"] == "BELOW_GATE"
    assert rows[0]["classification_source"].endswith("2026-08-17.md")
    assert rows[0]["opportunity_provenance"] == {
        "estimator_version": "2.0",
        "cutoff": "2026-08-17T20:00:00+00:00",
        "entry_timestamp": "2026-08-17T14:22:00+00:00",
        "entry_bar_timestamp": "2026-08-17T14:25:00+00:00",
        "entry_source": "intraday_open_at_first_eligible_bar",
        "eligible_cycle_source": "primo_ciclo_dopo_segnale",
        "exit_source": "daily_close",
        "exit_policy": "EOD_close",
    }


def test_manifest_con_riga_assente_dal_dossier_fallisce_esplicitamente():
    manifest = [
        {
            "data": "2026-08-17",
            "symbol": "MISSING",
            "causa": "NO_NEWS",
            "source": "report.md",
        }
    ]

    with pytest.raises(ValueError, match="manifest rows not found"):
        build_observations(
            [_dossier("2026-08-17", {}, ())],
            "2026-08-17",
            "2026-08-27",
            sample_manifest=manifest,
        )


def test_sintesi_separa_opportunita_catturabile_da_pnl_e_dichiara_n():
    observations = [
        {
            "data": "2026-08-17", "causa": "NO_NEWS", "intent_shadow": "LONG",
            "return": 0.04, "accessible_opportunity_usd": 10.0,
            "positive_accessible_opportunity_usd": 10.0,
        },
        {
            "data": "2026-08-17", "causa": "THIN_NEUTRAL", "intent_shadow": "ABSTAIN",
            "return": 0.05, "accessible_opportunity_usd": 30.0,
            "positive_accessible_opportunity_usd": 30.0,
        },
        {
            "data": "2026-08-18", "causa": "NO_NEWS", "intent_shadow": "LONG",
            "return": -0.04, "accessible_opportunity_usd": 0.0,
            "positive_accessible_opportunity_usd": 0.0,
        },
        {
            "data": "2026-08-18", "causa": "NO_NEWS", "intent_shadow": "NOT_EVALUABLE",
            "return": 0.06, "accessible_opportunity_usd": 20.0,
            "positive_accessible_opportunity_usd": 20.0,
        },
        {
            "data": "2026-08-19", "causa": "THIN_NEUTRAL", "intent_shadow": "LONG",
            "return": 0.03, "accessible_opportunity_usd": None,
            "positive_accessible_opportunity_usd": None,
        },
    ]

    out = summarize_observations(observations, n_bootstrap=200)

    assert out["counts"] == {
        "population": 5,
        "momentum_evaluable": 4,
        "long_intents": 3,
        "outcome_available": 4,
        "long_up_sessions": 2,
        "long_down_sessions": 1,
        "long_session_direction_missing": 0,
    }
    assert out["estimates"]["accessible_positive_total_usd"] == pytest.approx(60.0)
    assert out["estimates"]["accessible_positive_captured_usd"] == pytest.approx(10.0)
    assert out["estimates"]["capture_ratio"] == pytest.approx(1 / 6)
    assert out["estimates"]["captured_mean_usd_per_outcome_row"] == pytest.approx(2.5)
    assert out["interpretation"] == "opportunity_capture_not_strategy_pnl"
    assert out["bootstrap"]["seed"] == BOOTSTRAP_SEED
    assert out["bootstrap"]["cluster"] == "event_date"


def test_bootstrap_e_riproducibile_e_tiene_insieme_i_cluster_giornalieri():
    observations = [
        {
            "data": "2026-08-17", "intent_shadow": "LONG",
            "return": 0.04, "positive_accessible_opportunity_usd": 10.0,
        },
        {
            "data": "2026-08-17", "intent_shadow": "LONG",
            "return": 0.05, "positive_accessible_opportunity_usd": 10.0,
        },
        {
            "data": "2026-08-18", "intent_shadow": "ABSTAIN",
            "return": 0.04, "positive_accessible_opportunity_usd": 10.0,
        },
        {
            "data": "2026-08-18", "intent_shadow": "ABSTAIN",
            "return": 0.05, "positive_accessible_opportunity_usd": 10.0,
        },
    ]

    first = summarize_observations(observations, n_bootstrap=500)["bootstrap"]
    second = summarize_observations(observations, n_bootstrap=500)["bootstrap"]

    assert first == second
    assert first["n_clusters"] == 2
    assert first["n_resamples"] == 500
    assert first["capture_ratio_ci95"] == pytest.approx([0.0, 1.0])
    assert first["captured_mean_usd_per_outcome_row_ci95"] == pytest.approx([0.0, 10.0])
