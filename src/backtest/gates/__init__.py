"""Validation gates for strategy QA (T-007).

Five gates must pass before a strategy enters the combined portfolio:
  Gate 1 — Statistical Significance (Sharpe t-test, p-value, DSR)
  Gate 2 — Walk-Forward Consistency (OOS Sharpe positive, >=50% windows)
  Gate 3 — Parameter Robustness (Sharpe stable under perturbation)
  Gate 4 — Regime Consistency (resilient in bull/bear/sideways)
  Gate 5 — Stress Testing (survives 2008, 2020, 2022 stress periods)
"""
from src.backtest.gates.gate_types import GateResult, GateReport
from src.backtest.gates.runner import run_all_gates, GateConfig

__all__ = [
    "GateResult",
    "GateReport",
    "GateConfig",
    "run_all_gates",
]
