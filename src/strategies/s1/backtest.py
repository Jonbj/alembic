"""S1 walk-forward backtest + validation gate runner."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.backtest.data.loader import DataLoader
from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.data.universe import load_universe
from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig
from src.backtest.gates.gate_types import GateReport
from src.backtest.gates.runner import GateConfig, run_all_gates
from src.backtest.walkforward.runner import WalkForwardConfig, WalkForwardRunner
from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum

log = logging.getLogger(__name__)


def run_s1_backtest_from_prices(
    prices: pd.DataFrame,
    output_dir: Path | str = Path("reports/s1_backtest"),
    wf_config: WalkForwardConfig | None = None,
    s1_config: S1Config | None = None,
    gate_config: GateConfig | None = None,
    run_robustness: bool = True,
) -> dict:
    """Run full walk-forward backtest + validation gates from a wide price DataFrame."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    s1_config = s1_config or S1Config()
    wf_config = wf_config or WalkForwardConfig(in_sample_days=1260, out_of_sample_days=252)

    strategy = TimeSeriesMomentum(prices, s1_config)
    if not strategy.health_check():
        raise RuntimeError("S1 strategy health check failed -- insufficient data or NaN signals")

    data_replay = DataReplay(prices)
    wf_runner = WalkForwardRunner(wf_config=wf_config)
    wf_result = wf_runner.run(data_replay, strategy)

    aggregate = wf_result.aggregate_metrics

    oos_nav = aggregate.get("oos_nav_series", pd.Series(dtype=float))
    oos_returns = oos_nav.pct_change().dropna() if len(oos_nav) > 1 else pd.Series(dtype=float)

    wf_window_returns = []
    for w in wf_result.windows:
        if "error" in w.oos_metrics:
            continue
        oos_snaps = [s for s in w.oos_result.snapshots if s.timestamp >= w.oos_start]
        if len(oos_snaps) > 1:
            window_nav = pd.Series(
                data=[s.total_nav for s in oos_snaps],
                index=[s.timestamp for s in oos_snaps],
            )
            wf_window_returns.append(window_nav.pct_change().dropna())

    # OOS Sharpe from concatenated window returns — unbiased vs mean of per-window Sharpes,
    # which is skewed when early no-trade windows (Sharpe=0) lower the arithmetic mean.
    if wf_window_returns:
        all_oos = pd.concat(wf_window_returns, ignore_index=True)
        oos_sharpe = float(sharpe_ratio(all_oos, periods=252))
    else:
        oos_sharpe = float(aggregate.get("mean_sharpe", 0.0))

    perturbed_sharpes = None
    if run_robustness and len(oos_returns) > 20:
        perturbed_sharpes = _run_perturbation(prices, s1_config, wf_config)

    regime_returns = None
    if len(oos_returns) > 60:
        regime_returns = _split_regime_returns(oos_returns)

    stress_returns = None
    if len(oos_returns) > 60:
        stress_returns = _extract_stress_periods(oos_returns)

    full_returns = oos_returns if len(oos_returns) > 0 else pd.Series(dtype=float)

    gate_report = run_all_gates(
        returns=full_returns,
        wf_results=wf_window_returns if wf_window_returns else None,
        perturbed_sharpes=perturbed_sharpes,
        regime_returns=regime_returns,
        stress_returns=stress_returns,
        config=gate_config,
    )

    milestone_b_pass = oos_sharpe >= 0.5 and gate_report.overall_passed

    gate_dict = {name: {"passed": g.passed, "details": g.details} for name, g in gate_report.gate_results.items()}
    summary = {
        "oos_sharpe": oos_sharpe,
        "milestone_b_pass": milestone_b_pass,
        "wf_aggregate": {k: v for k, v in aggregate.items() if k != "oos_nav_series" and k != "per_window"},
        "gate_report": gate_dict,
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (output_dir / "gate_report.json").write_text(json.dumps(gate_dict, indent=2, default=str))

    if len(oos_returns) > 0 and oos_returns.index.dtype != object:
        cum = (1 + oos_returns).cumprod() - 1
        peak = (1 + cum).cummax()
        dd = ((1 + cum) - peak) / peak
        equity_curve = [
            {
                "date": str(ts.date()),
                "cumulative_return": round(float(cum[ts]), 6),
                "drawdown": round(float(dd[ts]), 6),
            }
            for ts in oos_returns.index
        ]
        (output_dir / "equity_curve.json").write_text(json.dumps(equity_curve))
        log.info("Saved equity curve: %d data points to %s", len(equity_curve), output_dir / "equity_curve.json")

    log.info("S1 backtest complete. OOS Sharpe=%.4f, Milestone B=%s", oos_sharpe, milestone_b_pass)
    log.info(gate_report.summary())

    return {
        "oos_sharpe": oos_sharpe,
        "wf_aggregate": aggregate,
        "gate_report": gate_dict,
        "milestone_b_pass": milestone_b_pass,
        "report_path": str(output_dir),
    }


def _run_perturbation(
    prices: pd.DataFrame,
    base_config: S1Config,
    wf_config: WalkForwardConfig,
) -> list[float]:
    """Run backtests with perturbed parameters, return list of OOS Sharpes."""
    perturbations = [
        {"lookbacks": (42, 126, 252, 504), "vol_window_signal": 42},
        {"lookbacks": (21, 63, 126, 252), "vol_window_signal": 84},
        {"lookbacks": (21, 63, 189, 378), "vol_window_signal": 63},
    ]
    sharpes = []
    for params in perturbations:
        try:
            cfg = S1Config(
                lookbacks=params.get("lookbacks", base_config.lookbacks),
                vol_window_signal=params.get("vol_window_signal", base_config.vol_window_signal),
            )
            strat = TimeSeriesMomentum(prices, cfg)
            if not strat.health_check():
                continue
            replay = DataReplay(prices)
            runner = WalkForwardRunner(wf_config=wf_config)
            result = runner.run(replay, strat)
            sh = float(result.aggregate_metrics.get("mean_sharpe", 0.0))
            sharpes.append(sh)
        except Exception as e:
            log.warning("Perturbation failed: %s", e)
    return sharpes


def _split_regime_returns(oos_returns: pd.Series) -> dict[str, pd.Series]:
    """Split OOS returns into high-vol and low-vol regimes."""
    rolling_vol = oos_returns.rolling(63).std() * np.sqrt(252)
    median_vol = rolling_vol.median()

    high_vol_mask = rolling_vol > median_vol
    low_vol_mask = rolling_vol <= median_vol

    regimes = {}
    if high_vol_mask.any():
        regimes["high_vol"] = oos_returns[high_vol_mask.fillna(False)]
    if low_vol_mask.any():
        regimes["low_vol"] = oos_returns[low_vol_mask.fillna(False)]
    return regimes


def _extract_stress_periods(oos_returns: pd.Series) -> dict[str, pd.Series]:
    """Extract worst drawdown period."""
    if len(oos_returns) < 63:
        return {}

    cum_return = (1 + oos_returns).cumprod()
    peak = cum_return.cummax()
    drawdown = (cum_return - peak) / peak

    worst_dd_idx = drawdown.idxmin()
    start = max(worst_dd_idx - pd.Timedelta(days=15), oos_returns.index[0])
    end = min(worst_dd_idx + pd.Timedelta(days=15), oos_returns.index[-1])
    stress_mask = (oos_returns.index >= start) & (oos_returns.index <= end)

    return {"worst_drawdown": oos_returns[stress_mask]}


def run_s1_backtest_full(
    output_dir: Path | str = Path("reports/s1_backtest"),
    force_refresh: bool = False,
) -> dict:
    """Full production run: download real data, run backtest + gates."""
    from src.backtest.data.cache import ParquetCache
    from datetime import date

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    universe = load_universe("s1")
    cache = ParquetCache()
    loader = DataLoader(cache=cache)

    start = date(1993, 1, 1)
    prices_wide = loader.get_aligned_prices(universe, start=start, end=date.today())

    return run_s1_backtest_from_prices(
        prices=prices_wide,
        output_dir=output_dir,
    )
