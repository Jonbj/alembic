"""Regole di decisione pre-registrate per il POC S3 (#84).

Questo modulo traduce le soglie del manifest in un esito riproducibile. Non
modifica le soglie e non autorizza alcuna promozione operativa: un esito
``SELECT_*`` identifica soltanto la candidata per il decision brief offline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.analysis.s3_poc.evaluation import VariantEvaluation
from src.analysis.s3_poc.manifest import S3PocManifest

_TRADING_DAYS = 252


@dataclass(frozen=True)
class VariantSelection:
    """Esito della scelta fra A e B, con i criteri che lo hanno prodotto."""

    outcome: str
    selected_variant: str | None
    replication_required: bool
    bootstrap_probability: float | None
    criteria: dict[str, bool]
    comparison: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "selected_variant": self.selected_variant,
            "replication_required": self.replication_required,
            "bootstrap_probability": self.bootstrap_probability,
            "criteria": self.criteria,
            "comparison": self.comparison,
        }


def bootstrap_sharpe_probability(
    candidate: pd.Series,
    baseline: pd.Series,
    draws: int,
    seed: int,
    chunk: int = 1000,
) -> float:
    """Probabilita' bootstrap paired che lo Sharpe della candidata sia maggiore.

    Le serie vengono allineate prima del ricampionamento: ogni estrazione
    conserva quindi la coppia osservata A/B e non inventa date mancanti.
    """
    paired = pd.concat([candidate.rename("candidate"), baseline.rename("baseline")], axis=1).dropna()
    if len(paired) < 2:
        return 0.0

    rng = np.random.default_rng(seed)
    values = paired["candidate"].to_numpy()
    base = paired["baseline"].to_numpy()
    n = len(values)

    def sharpes(sample: np.ndarray) -> np.ndarray:
        mean = sample.mean(axis=1)
        std = sample.std(axis=1, ddof=1)
        return np.divide(mean, std, out=np.zeros_like(mean), where=std >= 1e-14) * np.sqrt(_TRADING_DAYS)

    wins = 0
    drawn = 0
    while drawn < draws:
        count = min(chunk, draws - drawn)
        picks = rng.integers(0, n, size=(count, n))
        wins += int((sharpes(values[picks]) > sharpes(base[picks])).sum())
        drawn += count
    return wins / draws


def _standalone_passes(evaluation: VariantEvaluation) -> bool:
    gates = evaluation.gates.gate_results
    return bool(gates) and evaluation.decision_grade and all(result.passed for result in gates.values())


def _risk_improvement(candidate: float, baseline: float) -> float:
    """Riduzione relativa della severita' di una perdita (MaxDD o ES)."""
    severity = abs(baseline)
    if severity == 0.0:
        return 0.0 if candidate == 0.0 else -float("inf")
    return (severity - abs(candidate)) / severity


def _cost_deterioration(candidate: float, baseline: float) -> float:
    if baseline == 0.0:
        return 0.0 if candidate == 0.0 else float("inf")
    return (candidate - baseline) / baseline


def select_variant(
    variant_a: VariantEvaluation,
    variant_b: VariantEvaluation,
    manifest: S3PocManifest,
) -> VariantSelection:
    """Applica le regole A/B della #84 al campione OOS congelato.

    B e' il default semplice. A lo sostituisce soltanto se i gate standalone
    passano e aggiunge valore economico materiale, confermato dal bootstrap,
    senza un deterioramento materiale dei costi. Se B fallisce, A non viene
    bloccata: rimane candidata con replica aggiuntiva obbligatoria.
    """
    if variant_a.variant != "A" or variant_b.variant != "B":
        raise ValueError("select_variant richiede VariantEvaluation A e B nell'ordine corretto")

    rules = manifest.selection_rules
    a_passes = _standalone_passes(variant_a)
    b_passes = _standalone_passes(variant_b)
    sharpe_delta = variant_a.metrics["sharpe"] - variant_b.metrics["sharpe"]
    dd_improvement = _risk_improvement(
        variant_a.metrics["max_drawdown"], variant_b.metrics["max_drawdown"]
    )
    es_improvement = _risk_improvement(
        variant_a.metrics["expected_shortfall"], variant_b.metrics["expected_shortfall"]
    )
    cost_deterioration = _cost_deterioration(
        variant_a.attribution["average_cost_per_rebalance_bps"],
        variant_b.attribution["average_cost_per_rebalance_bps"],
    )
    probability = bootstrap_sharpe_probability(
        variant_a.returns,
        variant_b.returns,
        manifest.combined_rules.bootstrap_draws,
        manifest.combined_rules.bootstrap_seed,
    )
    material_sharpe = sharpe_delta >= rules.sharpe_margin
    material_risk = (
        dd_improvement >= rules.risk_improvement_min
        or es_improvement >= rules.risk_improvement_min
    ) and sharpe_delta >= -rules.sharpe_tolerance
    bootstrap_passes = probability >= rules.bootstrap_min_prob
    no_cost_deterioration = cost_deterioration <= rules.material_cost_deterioration
    material_value = (material_sharpe or material_risk) and bootstrap_passes and no_cost_deterioration
    criteria = {
        "a_standalone": a_passes,
        "b_standalone": b_passes,
        "material_sharpe_gain": material_sharpe,
        "material_risk_improvement": material_risk,
        "bootstrap": bootstrap_passes,
        "no_material_cost_deterioration": no_cost_deterioration,
        "a_adds_material_value": material_value,
    }
    comparison = {
        "sharpe_delta": sharpe_delta,
        "max_drawdown_improvement": dd_improvement,
        "expected_shortfall_improvement": es_improvement,
        "cost_deterioration": cost_deterioration,
    }

    if not a_passes and not b_passes:
        return VariantSelection("ARCHIVE_S3", None, False, probability, criteria, comparison)
    if a_passes and not b_passes:
        return VariantSelection(
            "SELECT_A_REPLICATION_REQUIRED", "A", True, probability, criteria, comparison
        )
    if not a_passes and b_passes:
        return VariantSelection("SELECT_B", "B", False, probability, criteria, comparison)
    if material_value:
        return VariantSelection("SELECT_A", "A", False, probability, criteria, comparison)

    # Una quasi-soglia non diventa una scelta discrezionale: resta NO-GO
    # temporaneo finche' non esiste una nuova ipotesi pre-registrata.
    lower_prob, _ = manifest.ambiguity.bootstrap_prob_band
    near_margin = manifest.ambiguity.margin_band
    ambiguous = (
        lower_prob <= probability < rules.bootstrap_min_prob
        or abs(sharpe_delta - rules.sharpe_margin) <= near_margin
        or abs(dd_improvement - rules.risk_improvement_min) <= near_margin
        or abs(es_improvement - rules.risk_improvement_min) <= near_margin
        or abs(cost_deterioration - rules.material_cost_deterioration) <= near_margin
    )
    if ambiguous:
        return VariantSelection("TEMPORARY_NO_GO", None, False, probability, criteria, comparison)
    return VariantSelection("SELECT_B", "B", False, probability, criteria, comparison)
