"""Gate runner: orchestrates all validation gates and produces GateReport."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.backtest.gates.gate_types import GateResult, GateReport
from src.backtest.gates.gate_1_significance import gate_1_significance
from src.backtest.gates.gate_2_walkforward import gate_2_walkforward
from src.backtest.gates.gate_3_robustness import gate_3_robustness
from src.backtest.gates.gate_4_regime import gate_4_regime
from src.backtest.gates.gate_5_stress import gate_5_stress


@dataclass
class GateConfig:
    """Configuration for gate thresholds."""
    # Gate 1
    n_trials: int = 1
    min_sharpe: float = 0.0
    max_pvalue: float = 0.05
    min_dsr: float = 0.5
    # Gate 2
    min_oos_sharpe: float = 0.0
    min_positive_fraction: float = 0.5
    # Gate 3
    max_cv: float = 0.5
    min_all_positive: bool = False
    # Gate 4
    min_regime_sharpe: float = 0.0
    min_passing_regimes: int = 3
    # Gate 5
    min_cumulative_return: float = -0.10
    max_drawdown_allowed: float = -0.30
    # Misc
    periods: int = 252


def run_all_gates(
    returns: pd.Series,
    wf_results: list[pd.Series] | None = None,
    perturbed_sharpes: list[float] | None = None,
    regime_returns: dict[str, pd.Series] | None = None,
    stress_returns: dict[str, pd.Series] | None = None,
    config: GateConfig | None = None,
) -> GateReport:
    """Run all 5 validation gates and return a GateReport.

    Parameters
    ----------
    returns : pd.Series
        Full in-sample daily returns (used for Gate 1).
    wf_results : list[pd.Series] or None
        Out-of-sample return series per walk-forward window (Gate 2).
    perturbed_sharpes : list[float] or None
        Sharpe ratios from perturbed parameter runs (Gate 3).
    regime_returns : dict[str, pd.Series] or None
        Regime name → daily returns (Gate 4).
    stress_returns : dict[str, pd.Series] or None
        Stress period name → daily returns (Gate 5).
    config : GateConfig or None
        Threshold configuration.

    """
    cfg = config or GateConfig()
    results: dict[str, GateResult] = {}

    # Gate 1 – always required
    results["gate_1_significance"] = gate_1_significance(
        returns=returns,
        n_trials=cfg.n_trials,
        periods=cfg.periods,
        min_sharpe=cfg.min_sharpe,
        max_pvalue=cfg.max_pvalue,
        min_dsr=cfg.min_dsr,
    )

    # Gate 2 – walk-forward
    if wf_results is not None:
        results["gate_2_walkforward"] = gate_2_walkforward(
            wf_results=wf_results,
            periods=cfg.periods,
            min_oos_sharpe=cfg.min_oos_sharpe,
            min_positive_fraction=cfg.min_positive_fraction,
        )
    else:
        results["gate_2_walkforward"] = GateResult(
            passed=False, details={"error": "no walk-forward data provided"}
        )

    # Gate 3 – robustness
    if perturbed_sharpes is not None:
        results["gate_3_robustness"] = gate_3_robustness(
            perturbed_sharpes=perturbed_sharpes,
            max_cv=cfg.max_cv,
            min_all_positive=cfg.min_all_positive,
        )
    else:
        results["gate_3_robustness"] = GateResult(
            passed=False, details={"error": "no perturbed sharpe data provided"}
        )

    # Gate 4 – regime
    if regime_returns is not None:
        results["gate_4_regime"] = gate_4_regime(
            regime_returns=regime_returns,
            periods=cfg.periods,
            min_regime_sharpe=cfg.min_regime_sharpe,
            min_passing_regimes=cfg.min_passing_regimes,
        )
    else:
        results["gate_4_regime"] = GateResult(
            passed=False, details={"error": "no regime data provided"}
        )

    # Gate 5 – stress
    if stress_returns is not None:
        results["gate_5_stress"] = gate_5_stress(
            stress_returns=stress_returns,
            periods=cfg.periods,
            min_cumulative_return=cfg.min_cumulative_return,
            max_drawdown_allowed=cfg.max_drawdown_allowed,
        )
    else:
        results["gate_5_stress"] = GateResult(
            passed=False, details={"error": "no stress period data provided"}
        )

    return GateReport(gate_results=results)
