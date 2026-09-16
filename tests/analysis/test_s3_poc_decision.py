"""Regole di esito eseguibili del POC S3 (#84).

Le soglie sono quelle del manifest congelato: questi test verificano che il
runner non si limiti a riportarle, ma produca un esito A/B e combinato.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.analysis.s3_poc.manifest import load_manifest
from tests.analysis.s3_poc_util import write_manifest_override


@pytest.fixture
def manifest(tmp_path):
    return load_manifest(write_manifest_override(tmp_path, {
        "combined_rules": {"bootstrap_draws": 300, "bootstrap_seed": 17},
    }))


def evaluation(
    variant: str,
    returns: pd.Series,
    *,
    sharpe: float,
    max_drawdown: float = -0.10,
    expected_shortfall: float = -0.02,
    annualized_cost_bps: float = 10.0,
    average_cost_per_rebalance_bps: float = 10.0,
    gates_passed: bool = True,
):
    """Doppio minimale del contratto pubblico VariantEvaluation."""
    return SimpleNamespace(
        variant=variant,
        returns=returns,
        metrics={
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "expected_shortfall": expected_shortfall,
        },
        attribution={
            "annualized_cost_bps": annualized_cost_bps,
            "average_cost_per_rebalance_bps": average_cost_per_rebalance_bps,
        },
        gates=SimpleNamespace(gate_results={
            "gate": SimpleNamespace(passed=gates_passed),
        }),
        decision_grade=True,
    )


def returns(mean: float, seed: int) -> pd.Series:
    idx = pd.bdate_range("2020-01-01", periods=260)
    return pd.Series(np.random.default_rng(seed).normal(mean, 0.001, len(idx)), index=idx)


class TestSelezioneVarianti:
    def test_seleziona_a_solo_con_valore_materiale_e_bootstrap(self, manifest) -> None:
        from src.analysis.s3_poc.decision import select_variant

        a = evaluation("A", returns(0.002, 1), sharpe=1.20)
        b = evaluation("B", returns(0.0002, 2), sharpe=0.80)

        result = select_variant(a, b, manifest)

        assert result.outcome == "SELECT_A"
        assert result.selected_variant == "A"
        assert result.bootstrap_probability >= manifest.selection_rules.bootstrap_min_prob
        assert result.criteria["material_sharpe_gain"] is True
        assert result.criteria["no_material_cost_deterioration"] is True

    def test_b_e_il_default_quando_a_non_aggiunge_valore_materiale(self, manifest) -> None:
        from src.analysis.s3_poc.decision import select_variant

        a = evaluation("A", returns(0.0004, 3), sharpe=0.84)
        b = evaluation("B", returns(0.0004, 4), sharpe=0.80)

        result = select_variant(a, b, manifest)

        assert result.outcome == "SELECT_B"
        assert result.selected_variant == "B"
        assert result.criteria["material_sharpe_gain"] is False

    def test_a_non_supera_b_con_costo_medio_per_ribilancio_materialmente_peggiore(self, manifest) -> None:
        from src.analysis.s3_poc.decision import select_variant

        a = evaluation(
            "A", returns(0.002, 12), sharpe=1.20,
            average_cost_per_rebalance_bps=12.0,
        )
        b = evaluation("B", returns(0.0002, 13), sharpe=0.80)

        result = select_variant(a, b, manifest)

        assert result.outcome == "SELECT_B"
        assert result.criteria["no_material_cost_deterioration"] is False

    def test_a_resta_candidata_con_replica_aggiuntiva_se_b_fallisce(self, manifest) -> None:
        from src.analysis.s3_poc.decision import select_variant

        a = evaluation("A", returns(0.001, 5), sharpe=1.0)
        b = evaluation("B", returns(-0.001, 6), sharpe=-1.0, gates_passed=False)

        result = select_variant(a, b, manifest)

        assert result.outcome == "SELECT_A_REPLICATION_REQUIRED"
        assert result.selected_variant == "A"
        assert result.replication_required is True

    def test_due_varianti_non_idonee_archiviano_s3(self, manifest) -> None:
        from src.analysis.s3_poc.decision import select_variant

        a = evaluation("A", returns(-0.001, 7), sharpe=-1.0, gates_passed=False)
        b = evaluation("B", returns(-0.001, 8), sharpe=-1.0, gates_passed=False)

        result = select_variant(a, b, manifest)

        assert result.outcome == "ARCHIVE_S3"
        assert result.selected_variant is None


class TestDecisioneCombinata:
    def test_applica_le_soglie_alla_sola_allocazione_primaria(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        baseline = returns(0.0001, 9)
        sleeve = returns(0.002, 10)

        result = evaluate_combined(baseline, sleeve, manifest)

        assert result.decision_outcome == "PASS"
        assert result.decision["allocation"] == manifest.combined_rules.primary_allocation
        assert result.decision["diagnostic_only"] is False
        assert result.decision["criteria"]["bootstrap"] is True

    def test_esito_non_valutabile_non_puo_essere_un_pass(self, manifest) -> None:
        from src.analysis.s3_poc.combined import evaluate_combined

        result = evaluate_combined(None, returns(0.002, 11), manifest)

        assert result.decision_outcome == "NOT_EVALUABLE"
        assert result.decision is None
