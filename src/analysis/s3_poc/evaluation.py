"""Valutazione standalone delle varianti A/B del POC S3 (#84).

Riusa i componenti di produzione senza rilassamenti: GateConfig dallo
snapshot congelato nel manifest, regimi come 4 fette sovrapposte (trend
SMA200 e vol 60 contro mediana), stress storici di produzione piu' i
momentum crash del manifest, DSR con il numero vero di trial del
registry. L'attribuzione quantifica beta vs mercato, concentrazione
settore, turnover, esposizione lorda e cassa media.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.analysis.s3_poc.dataset import PitDataset
from src.analysis.s3_poc.engine import SleeveResult, run_sleeve, run_walk_forward
from src.analysis.s3_poc.manifest import S3PocManifest, manifest_with_overrides
from src.backtest.gates.historical_stress import extract_historical_stress_periods
from src.backtest.gates.runner import GateConfig, GateReport, run_all_gates
from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.metrics.risk import expected_shortfall, max_drawdown
from src.backtest.metrics.signal_quality import deflated_sharpe_ratio

_TRADING_DAYS = 252


@dataclass(frozen=True)
class VariantEvaluation:
    """Valutazione standalone di una variante su un periodo."""

    variant: str
    metrics: dict[str, float]
    windows: list[dict[str, Any]]
    gates: GateReport
    dsr: dict[str, float]
    regimes: dict[str, dict[str, float]]
    stress: dict[str, dict[str, float]]
    attribution: dict[str, float]
    coverage: dict[str, Any]
    cost_multiplier: float
    decision_grade: bool
    unresolved_delistings: tuple[dict, ...]
    # serie dei rendimenti esposta per il bootstrap paired del combinato
    returns: pd.Series = field(default_factory=pd.Series)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "metrics": self.metrics,
            "windows": self.windows,
            "gates": {
                name: {"passed": r.passed, "details": r.details}
                for name, r in self.gates.gate_results.items()
            },
            "dsr": self.dsr,
            "regimes": self.regimes,
            "stress": self.stress,
            "attribution": self.attribution,
            "coverage": self.coverage,
            "cost_multiplier": self.cost_multiplier,
            "decision_grade": self.decision_grade,
            "unresolved_delistings": list(self.unresolved_delistings),
        }


def gate_config_from_manifest(manifest: S3PocManifest) -> GateConfig:
    """GateConfig dallo snapshot congelato: stesse soglie di produzione."""
    g = manifest.gates
    return GateConfig(
        n_trials=g.n_trials,
        min_sharpe=g.min_sharpe,
        max_pvalue=g.max_pvalue,
        min_dsr=g.min_dsr,
        min_oos_sharpe=g.min_oos_sharpe,
        min_positive_fraction=g.min_positive_fraction,
        max_cv=g.max_cv,
        min_all_positive=g.min_all_positive,
        min_regime_sharpe=g.min_regime_sharpe,
        min_passing_regimes=g.min_passing_regimes,
        min_cumulative_return=g.min_cumulative_return,
        max_drawdown_allowed=g.max_drawdown_allowed,
        periods=g.periods,
    )


def regime_slices(
    ds: PitDataset, manifest: S3PocManifest, returns: pd.Series
) -> dict[str, pd.Series]:
    """4 fette sovrapposte: bull/bear su SMA200 del mercato, high/low vol
    sulla vol 60 sedute contro la mediana del periodo di valutazione."""
    rcfg = manifest.regimes
    market = ds.market
    sma = market.rolling(rcfg.trend_ma_sessions).mean()
    vol = market.pct_change().rolling(rcfg.vol_window_sessions).std()

    idx = returns.index
    trend = sma.reindex(idx)
    price = market.reindex(idx)
    vol60 = vol.reindex(idx)

    regime: dict[str, pd.Series] = {}
    definizioni = {
        "bull": price >= trend,
        "bear": price < trend,
        "high_vol": vol60 > vol60.median(),
        "low_vol": vol60 <= vol60.median(),
    }
    for name in rcfg.definitions:
        mask = definizioni[name].fillna(False)
        sl = returns[mask]
        if not sl.empty:
            regime[name] = sl
    return regime


def stress_slices(returns: pd.Series, manifest: S3PocManifest) -> dict[str, pd.Series]:
    """Stress storici di produzione + momentum crash congelati nel manifest.
    Solo i periodi che intersecano il periodo valutato."""
    out = dict(extract_historical_stress_periods(returns))
    for name, (start, end) in manifest.stress.momentum_crash_periods.items():
        sl = returns.loc[pd.Timestamp(start):pd.Timestamp(end)]
        if not sl.empty:
            out[name] = sl
    return out


def robustness_sharpes(
    ds: PitDataset,
    manifest: S3PocManifest,
    variant: str,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    cost_multiplier: float = 1.0,
) -> list[float]:
    """Sharpe della griglia di robustezza congelata (non-trial dichiarato):
    prodotto cartesiano skip x vol, centro = taratura di produzione."""
    sharpes: list[float] = []
    for skip in manifest.robustness.skip_sessions_grid:
        for vol_window in manifest.robustness.vol_window_grid:
            perturbato = manifest_with_overrides(manifest, {
                "signal": {"skip_sessions": skip},
                "portfolio": {"vol_window_sessions": vol_window},
            })
            res = run_sleeve(ds, perturbato, variant, period_start, period_end, cost_multiplier)
            sharpes.append(sharpe_ratio(res.returns, periods=manifest.gates.periods))
    return sharpes


def _metrics(returns: pd.Series, periods: int) -> dict[str, float]:
    anni = len(returns) / periods
    cumulative = float((1.0 + returns).prod())
    return {
        "sharpe": sharpe_ratio(returns, periods=periods),
        "max_drawdown": max_drawdown(returns),
        "expected_shortfall": expected_shortfall(returns),
        "annualized_return": cumulative ** (1.0 / anni) - 1.0 if anni > 0 else 0.0,
        "annualized_vol": float(returns.std(ddof=1) * np.sqrt(periods)),
        "n_sessions": float(len(returns)),
        "final_nav": float((1.0 + returns).prod()),
    }


def _dsr(returns: pd.Series, n_trials: int, periods: int) -> dict[str, float]:
    observed = sharpe_ratio(returns, periods=periods)
    # lo Sharpe annualizzato va in termini per-seduta per il DSR
    observed_per_period = observed / np.sqrt(periods)
    dsr = deflated_sharpe_ratio(
        observed_sr=observed_per_period,
        n_trials=n_trials,
        n_obs=len(returns),
        skew=float(returns.skew()),
        excess_kurt=float(returns.kurt()),
    )
    return {
        "dsr": float(dsr),
        "observed_sharpe_annualized": observed,
        "n_trials": float(n_trials),
        "n_obs": float(len(returns)),
    }


def _sector_map(ds: PitDataset) -> dict[str, str]:
    m = ds.security_master
    return dict(zip(m["security_id"], m["sector"]))


def _attribution(
    ds: PitDataset,
    sleeve: SleeveResult,
    market: pd.Series,
) -> dict[str, float]:
    returns = sleeve.returns
    mkt_ret = market.pct_change().reindex(returns.index)
    pair = pd.concat([returns, mkt_ret], axis=1, keys=["r", "m"]).dropna()
    if len(pair) > 1 and float(pair["m"].var()) > 0:
        beta = float(pair["r"].cov(pair["m"]) / pair["m"].var())
    else:
        beta = float("nan")

    sector = _sector_map(ds)
    hhis = []
    gross = []
    for r in sleeve.rebalances:
        by_sector: dict[str, float] = {}
        for sec, w in r.weights.items():
            by_sector[sector.get(sec, "UNKNOWN")] = by_sector.get(sector.get(sec, "UNKNOWN"), 0.0) + w
        hhis.append(sum(v * v for v in by_sector.values()))
        gross.append(sum(r.weights.values()))

    anni = len(returns) / _TRADING_DAYS
    total_notional = sum(r.traded_notional_usd for r in sleeve.rebalances)
    mean_nav = float(sleeve.nav.mean())
    total_cost_usd = float(sum(r.cost_usd for r in sleeve.rebalances))
    # costi annualizzati in basis point sul NAV medio di manica
    annualized_cost_bps = (
        (total_cost_usd / mean_nav / anni * 1e4) if anni > 0 and mean_nav > 0 else 0.0
    )
    return {
        "beta_vs_market": beta,
        "sector_hhi_avg": float(np.mean(hhis)) if hhis else 0.0,
        "annualized_turnover": (total_notional / mean_nav / anni) if anni > 0 else 0.0,
        "avg_gross_exposure": float(np.mean(gross)) if gross else 0.0,
        "avg_cash_weight": 1.0 - (float(np.mean(gross)) if gross else 0.0),
        "total_cost_usd": total_cost_usd,
        "annualized_cost_bps": annualized_cost_bps,
    }


def evaluate_variant(
    ds: PitDataset,
    manifest: S3PocManifest,
    variant: str,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    cost_multiplier: float = 1.0,
) -> VariantEvaluation:
    period_start, period_end = pd.Timestamp(period_start), pd.Timestamp(period_end)
    periods = manifest.gates.periods

    full = run_sleeve(ds, manifest, variant, period_start, period_end, cost_multiplier)
    wf = run_walk_forward(ds, manifest, variant, period_start, period_end, cost_multiplier)

    metrics = _metrics(full.returns, periods)
    regimes = regime_slices(ds, manifest, full.returns)
    stress = stress_slices(full.returns, manifest)
    perturbed = robustness_sharpes(ds, manifest, variant, period_start, period_end, cost_multiplier)

    gates = run_all_gates(
        returns=full.returns,
        wf_results=[w.returns for w in wf],
        perturbed_sharpes=perturbed,
        regime_returns=regimes,
        stress_returns=stress,
        config=gate_config_from_manifest(manifest),
    )

    windows = [
        {
            "start": w.start.isoformat(),
            "end": w.end.isoformat(),
            "sharpe": sharpe_ratio(w.returns, periods=periods),
            "cumulative": float((1.0 + w.returns).prod()),
            "n_sessions": len(w.returns),
        }
        for w in wf
    ]

    unresolved = full.unresolved_delistings + tuple(
        u for w in wf for u in w.unresolved_delistings
    )

    return VariantEvaluation(
        variant=variant,
        metrics=metrics,
        windows=windows,
        gates=gates,
        dsr=_dsr(full.returns, manifest.trial_registry.n_trials_for_dsr, periods),
        regimes={
            name: {
                "sharpe": sharpe_ratio(sl, periods=periods),
                "n_obs": float(len(sl)),
            }
            for name, sl in regimes.items()
        },
        stress={
            name: {
                "cumulative": float((1.0 + sl).prod() - 1.0),
                "max_drawdown": max_drawdown(sl),
                "n_obs": float(len(sl)),
            }
            for name, sl in stress.items()
        },
        attribution=_attribution(ds, full, ds.market),
        coverage={
            "n_sessions": int(len(full.returns)),
            "start": full.returns.index.min().isoformat(),
            "end": full.returns.index.max().isoformat(),
            "n_rebalances": len(full.rebalances),
            "months_in_cash": full.months_in_cash,
        },
        cost_multiplier=cost_multiplier,
        decision_grade=all(w.decision_grade for w in (full, *wf)),
        unresolved_delistings=unresolved,
        returns=full.returns,
    )
