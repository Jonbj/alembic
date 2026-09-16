"""Test combinato del POC S3 (#84): S1 invariato + punti di cassa sostituiti.

r_comb = r_S1 + w x (r_S3_net - cash_return_giornaliero), con w = 10%
primario e 5%/15% solo diagnostici. I delta si misurano contro S1
standalone sulle metriche di produzione; la probabilita' bootstrap e'
paired iid sulla differenza giornaliera dei rendimenti (numero di
estrazioni e seed congelati nel manifest).

Fail-closed: senza serie S1 o senza intersezione di date il test non e'
valutabile e non produce numeri.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.analysis.s3_poc.manifest import S3PocManifest
from src.analysis.s3_poc.decision import bootstrap_sharpe_probability
from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.metrics.risk import expected_shortfall, max_drawdown

_TRADING_DAYS = 252


@dataclass(frozen=True)
class CombinedReport:
    """Esito del test combinato per ogni allocazione."""

    evaluability: bool
    primary_allocation: float
    allocations: list[dict[str, Any]]
    overlap: dict[str, Any]
    bootstrap_draws: int
    bootstrap_seed: int
    decision_outcome: str
    decision: dict[str, Any] | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluability": self.evaluability,
            "primary_allocation": self.primary_allocation,
            "allocations": self.allocations,
            "overlap": self.overlap,
            "bootstrap_draws": self.bootstrap_draws,
            "bootstrap_seed": self.bootstrap_seed,
            "decision_outcome": self.decision_outcome,
            "decision": self.decision,
            "reason": self.reason,
        }


def _risk_worsening(candidate: float, baseline: float) -> float:
    """Aumento relativo della severita' della perdita (positivo = peggio)."""
    severity = abs(baseline)
    if severity == 0.0:
        return 0.0 if candidate == 0.0 else float("inf")
    return (abs(candidate) - severity) / severity


def _decision_for_primary(primary: dict[str, Any], manifest: S3PocManifest) -> tuple[str, dict[str, Any]]:
    """Applica le due braccia economiche della #84, esclusivamente al 10%."""
    rules = manifest.combined_rules
    sharpe_arm = (
        primary["sharpe_delta"] >= rules.sharpe_gain_min
        and primary["max_drawdown_worsening"] <= rules.dd_es_worsening_max
        and primary["expected_shortfall_worsening"] <= rules.dd_es_worsening_max
    )
    risk_arm = (
        primary["max_drawdown_improvement"] >= rules.dd_es_improvement_min
        or primary["expected_shortfall_improvement"] >= rules.dd_es_improvement_min
    ) and primary["sharpe_delta"] >= -rules.sharpe_reduction_max
    bootstrap = primary["bootstrap_prob"] >= rules.bootstrap_min_prob
    criteria = {"sharpe_arm": sharpe_arm, "risk_arm": risk_arm, "bootstrap": bootstrap}
    decision = {**primary, "criteria": criteria}
    if (sharpe_arm or risk_arm) and bootstrap:
        return "PASS", decision

    lower_prob, _ = manifest.ambiguity.bootstrap_prob_band
    near = (
        lower_prob <= primary["bootstrap_prob"] < rules.bootstrap_min_prob
        or abs(primary["sharpe_delta"] - rules.sharpe_gain_min) <= manifest.ambiguity.margin_band
        or abs(primary["max_drawdown_improvement"] - rules.dd_es_improvement_min)
        <= manifest.ambiguity.margin_band
        or abs(primary["expected_shortfall_improvement"] - rules.dd_es_improvement_min)
        <= manifest.ambiguity.margin_band
    )
    return ("TEMPORARY_NO_GO" if near else "NO_GO"), decision


def evaluate_combined(
    s1_returns: pd.Series | None,
    s3_returns: pd.Series,
    manifest: S3PocManifest,
) -> CombinedReport:
    rules = manifest.combined_rules

    def non_valutabile(reason: str) -> CombinedReport:
        return CombinedReport(
            evaluability=False,
            primary_allocation=rules.primary_allocation,
            allocations=[],
            overlap={"n_obs": 0},
            bootstrap_draws=rules.bootstrap_draws,
            bootstrap_seed=rules.bootstrap_seed,
            decision_outcome="NOT_EVALUABLE",
            decision=None,
            reason=reason,
        )

    if s1_returns is None or len(s1_returns) == 0:
        return non_valutabile("serie S1 assente")
    if s3_returns is None or len(s3_returns) == 0:
        return non_valutabile("serie S3 assente")

    insieme = pd.concat([s1_returns.rename("s1"), s3_returns.rename("s3")], axis=1, join="inner")
    insieme = insieme.dropna()
    if insieme.empty:
        return non_valutabile("nessuna intersezione di date fra S1 e S3")

    r1 = insieme["s1"]
    r3 = insieme["s3"]
    overlap = {
        "n_obs": int(len(insieme)),
        "start": insieme.index.min().isoformat(),
        "end": insieme.index.max().isoformat(),
    }

    cash_daily = rules.cash_return / _TRADING_DAYS  # cash_return e' annuo
    sharpe_s1 = sharpe_ratio(r1, periods=_TRADING_DAYS)
    dd_s1 = max_drawdown(r1)
    es_s1 = expected_shortfall(r1)

    allocations: list[dict[str, Any]] = []
    pesi = [rules.primary_allocation, *rules.diagnostic_allocations]
    for w in pesi:
        combinata = r1 + w * (r3 - cash_daily)
        sharpe_w = sharpe_ratio(combinata, periods=_TRADING_DAYS)
        dd = max_drawdown(combinata)
        es = expected_shortfall(combinata)
        dd_worsening = _risk_worsening(dd, dd_s1)
        es_worsening = _risk_worsening(es, es_s1)
        allocations.append({
            "allocation": w,
            "diagnostic_only": w != rules.primary_allocation,
            "sharpe": sharpe_w,
            "sharpe_delta": sharpe_w - sharpe_s1,
            "max_drawdown": dd,
            "dd_delta": dd - dd_s1,
            "max_drawdown_worsening": dd_worsening,
            "max_drawdown_improvement": -dd_worsening,
            "expected_shortfall": es,
            "es_delta": es - es_s1,
            "expected_shortfall_worsening": es_worsening,
            "expected_shortfall_improvement": -es_worsening,
            "bootstrap_prob": bootstrap_sharpe_probability(
                combinata, r1, rules.bootstrap_draws, rules.bootstrap_seed
            ),
        })

    outcome, decision = _decision_for_primary(allocations[0], manifest)

    return CombinedReport(
        evaluability=True,
        primary_allocation=rules.primary_allocation,
        allocations=allocations,
        overlap=overlap,
        bootstrap_draws=rules.bootstrap_draws,
        bootstrap_seed=rules.bootstrap_seed,
        decision_outcome=outcome,
        decision=decision,
    )
