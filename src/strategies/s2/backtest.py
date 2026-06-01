"""S2 walk-forward backtest + validation gate runner."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.backtest.data.loader import DataLoader
from src.backtest.data.cache import ParquetCache
from src.backtest.data.universe import load_universe
from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig
from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.gates.gate_types import GateReport
from src.backtest.gates.runner import GateConfig, run_all_gates
from src.backtest.walkforward.runner import WalkForwardConfig, WalkForwardRunner
from src.strategies.s2.config import S2Config
from src.strategies.s2.strategy import VRPStrategy

log = logging.getLogger(__name__)


def run_s2_backtest_from_prices(
    prices: pd.DataFrame,
    output_dir: Path | str = Path("reports/s2_backtest"),
    wf_config: WalkForwardConfig | None = None,
    s2_config: S2Config | None = None,
    gate_config: GateConfig | None = None,
    run_robustness: bool = True,
) -> dict:
    """Run full walk-forward backtest + validation gates from a wide price DataFrame.

    Parameters
    ----------
    prices : pd.DataFrame
        Wide DataFrame with DatetimeIndex and columns per ticker (must include SPY).
    output_dir : Path or str
        Directory for saving summary and gate reports.
    wf_config : WalkForwardConfig or None
        Walk-forward window configuration.
    s2_config : S2Config or None
        S2 strategy configuration.
    gate_config : GateConfig or None
        Gate threshold configuration.

    Returns
    -------
    dict with keys: oos_sharpe, wf_aggregate, gate_report, milestone_d_pass
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    s2_config = s2_config or S2Config()
    wf_config = wf_config or WalkForwardConfig(in_sample_days=1260, out_of_sample_days=252)

    # Instantiate strategy
    strategy = VRPStrategy(prices, s2_config)
    if not strategy.health_check():
        raise RuntimeError("S2 strategy health check failed -- insufficient data or NaN signals")

    data_replay = DataReplay(prices)
    wf_runner = WalkForwardRunner(wf_config=wf_config)
    wf_result = wf_runner.run(data_replay, strategy)

    aggregate = wf_result.aggregate_metrics

    # Collect OOS returns from each window
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

    # OOS Sharpe from concatenated window returns
    if wf_window_returns:
        all_oos = pd.concat(wf_window_returns, ignore_index=True)
        oos_sharpe = float(sharpe_ratio(all_oos, periods=252))
    else:
        oos_sharpe = float(aggregate.get("mean_sharpe", 0.0))

    # Perturbed sharpes for robustness gate
    perturbed_sharpes = None
    if run_robustness and len(oos_returns) > 20:
        perturbed_sharpes = _run_perturbation(prices, s2_config, wf_config)

    # Regime returns for regime gate
    regime_returns = None
    if len(oos_returns) > 60:
        regime_returns = _split_regime_returns(oos_returns)

    # Stress returns for stress gate
    stress_returns = None
    if len(oos_returns) > 60:
        stress_returns = _extract_stress_periods(oos_returns)

    full_returns = oos_returns if len(oos_returns) > 0 else pd.Series(dtype=float)

    # Run all 5 validation gates
    gate_report = run_all_gates(
        returns=full_returns,
        wf_results=wf_window_returns if wf_window_returns else None,
        perturbed_sharpes=perturbed_sharpes,
        regime_returns=regime_returns,
        stress_returns=stress_returns,
        config=gate_config,
    )

    # Milestone D: S2 passes all gates AND OOS Sharpe >= 0.5
    milestone_d_pass = oos_sharpe >= 0.5 and gate_report.overall_passed

    gate_dict = {
        name: {"passed": g.passed, "details": g.details}
        for name, g in gate_report.gate_results.items()
    }

    summary = {
        "oos_sharpe": oos_sharpe,
        "milestone_d_pass": milestone_d_pass,
        "wf_aggregate": {
            k: v for k, v in aggregate.items()
            if k not in ("oos_nav_series", "per_window")
        },
        "gate_report": gate_dict,
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (output_dir / "gate_report.json").write_text(json.dumps(gate_dict, indent=2, default=str))

    log.info(
        "S2 backtest complete. OOS Sharpe=%.4f, Milestone D=%s",
        oos_sharpe, milestone_d_pass,
    )
    log.info(gate_report.summary())

    return {
        "oos_sharpe": oos_sharpe,
        "wf_aggregate": aggregate,
        "gate_report": gate_dict,
        "milestone_d_pass": milestone_d_pass,
        "report_path": str(output_dir),
    }


def _run_perturbation(
    prices: pd.DataFrame,
    base_config: S2Config,
    wf_config: WalkForwardConfig,
) -> list[float]:
    """Run backtests with perturbed parameters, return list of OOS Sharpes."""
    perturbations = [
        {"target_delta": -0.15, "max_dte": 50},
        {"target_delta": -0.25, "max_dte": 35},
        {"target_delta": -0.20, "max_dte": 60, "min_dte": 25},
        {"profit_target_pct": 0.60, "stop_loss_multiplier": 2.5},
        {"profit_target_pct": 0.40, "stop_loss_multiplier": 1.5},
    ]
    sharpes = []
    for params in perturbations:
        try:
            cfg = S2Config(**{k: v for k, v in params.items() if k in S2Config.__dataclass_fields__})
            strat = VRPStrategy(prices, cfg)
            if not strat.health_check():
                continue
            replay = DataReplay(prices)
            runner = WalkForwardRunner(wf_config=wf_config)
            result = runner.run(replay, strat)
            sh = float(result.aggregate_metrics.get("mean_sharpe", 0.0))
            sharpes.append(sh)
        except Exception as e:
            log.warning("S2 perturbation failed: %s", e)
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

    # Also split into bull/bear by cumulative return direction
    cum_return = (1 + oos_returns).cumprod()
    # Forward-looking: if the next 21-day return is positive → bull, else → bear
    fwd_21d = cum_return.shift(-21) / cum_return - 1
    bull_mask = fwd_21d > 0
    bear_mask = fwd_21d <= 0

    if bull_mask.any():
        regimes["bull"] = oos_returns[bull_mask.dropna().reindex(oos_returns.index).fillna(False)]
    if bear_mask.any():
        regimes["bear"] = oos_returns[bear_mask.dropna().reindex(oos_returns.index).fillna(False)]

    return regimes


def _extract_stress_periods(oos_returns: pd.Series) -> dict[str, pd.Series]:
    """Extract worst drawdown period + known stress dates (Mar 2020, etc.)."""
    results = {}

    # Worst drawdown window
    if len(oos_returns) >= 63:
        cum_return = (1 + oos_returns).cumprod()
        peak = cum_return.cummax()
        drawdown = (cum_return - peak) / peak

        worst_dd_idx = drawdown.idxmin()
        start = max(worst_dd_idx - pd.Timedelta(days=15), oos_returns.index[0])
        end = min(worst_dd_idx + pd.Timedelta(days=15), oos_returns.index[-1])
        stress_mask = (oos_returns.index >= start) & (oos_returns.index <= end)
        if stress_mask.any():
            results["worst_drawdown"] = oos_returns[stress_mask]

    # Known stress periods: March 2020 COVID crash
    covid_mask = (oos_returns.index >= pd.Timestamp("2020-02-20")) & (
        oos_returns.index <= pd.Timestamp("2020-04-15")
    )
    if covid_mask.any():
        results["covid_2020"] = oos_returns[covid_mask]

    # 2018 Feb VIX event
    vix_2018_mask = (oos_returns.index >= pd.Timestamp("2018-02-01")) & (
        oos_returns.index <= pd.Timestamp("2018-02-14")
    )
    if vix_2018_mask.any():
        results["vix_2018"] = oos_returns[vix_2018_mask]

    # 2022 rate hike selloff
    rate_2022_mask = (oos_returns.index >= pd.Timestamp("2022-01-01")) & (
        oos_returns.index <= pd.Timestamp("2022-06-30")
    )
    if rate_2022_mask.any():
        results["rate_2022"] = oos_returns[rate_2022_mask]

    return results


def run_s2_backtest_full(
    output_dir: Path | str = Path("reports/s2_backtest"),
    force_refresh: bool = False,
) -> dict:
    """Full production run: download real SPY data, run S2 backtest + gates.

    Uses S1 universe (which includes SPY) as the price source.
    The S2 strategy trades SPY with delta-equivalent position sizing.
    """
    from datetime import date

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    universe = load_universe("s1")
    cache = ParquetCache()
    loader = DataLoader(cache=cache)

    start = date(2007, 1, 1)  # Start from 2007 to capture 2008 crash
    prices_wide = loader.get_aligned_prices(universe, start=start, end=date.today())

    # Ensure SPY is in the universe
    if "SPY" not in prices_wide.columns:
        raise RuntimeError("SPY not found in price data — required for S2 backtest")

    return run_s2_backtest_from_prices(
        prices=prices_wide,
        output_dir=output_dir,
    )
