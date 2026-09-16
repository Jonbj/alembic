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

import numpy as np
import pandas as pd

from src.analysis.s3_poc.manifest import S3PocManifest
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
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluability": self.evaluability,
            "primary_allocation": self.primary_allocation,
            "allocations": self.allocations,
            "overlap": self.overlap,
            "bootstrap_draws": self.bootstrap_draws,
            "bootstrap_seed": self.bootstrap_seed,
            "reason": self.reason,
        }


def _bootstrap_prob(
    combined: pd.Series,
    baseline: pd.Series,
    draws: int,
    seed: int,
    chunk: int = 1000,
) -> float:
    """P(Sharpe(r_comb) > Sharpe(r_S1)) sotto bootstrap iid paired.

    Lo Sharpe di ogni estrazione usa la stessa formula dell'helper di
    produzione (media/std ddof=1 x sqrt(252), 0 sui campioni degeneri),
    calcolata in numpy perche' 10000 estrazioni x 3 allocazioni non
    stanno nel ciclo python.
    """
    rng = np.random.default_rng(seed)
    values = combined.to_numpy()
    base = baseline.to_numpy()
    n = len(values)

    def _sharpe_righe(mat: np.ndarray) -> np.ndarray:
        mu = mat.mean(axis=1)
        sd = mat.std(axis=1, ddof=1)
        safe = np.divide(mu, sd, out=np.zeros_like(mu), where=sd >= 1e-14)
        return safe * np.sqrt(_TRADING_DAYS)

    wins = 0
    estratti = 0
    while estratti < draws:
        quanti = min(chunk, draws - estratti)
        pick = rng.integers(0, n, size=(quanti, n))
        delta = _sharpe_righe(values[pick]) - _sharpe_righe(base[pick])
        wins += int((delta > 0).sum())
        estratti += quanti
    return wins / draws


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
        allocations.append({
            "allocation": w,
            "diagnostic_only": w != rules.primary_allocation,
            "sharpe": sharpe_w,
            "sharpe_delta": sharpe_w - sharpe_s1,
            "max_drawdown": max_drawdown(combinata),
            "dd_delta": max_drawdown(combinata) - dd_s1,
            "expected_shortfall": expected_shortfall(combinata),
            "es_delta": expected_shortfall(combinata) - es_s1,
            "bootstrap_prob": _bootstrap_prob(
                combinata, r1, rules.bootstrap_draws, rules.bootstrap_seed
            ),
        })

    return CombinedReport(
        evaluability=True,
        primary_allocation=rules.primary_allocation,
        allocations=allocations,
        overlap=overlap,
        bootstrap_draws=rules.bootstrap_draws,
        bootstrap_seed=rules.bootstrap_seed,
    )
