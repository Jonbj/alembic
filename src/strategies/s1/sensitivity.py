"""S1 parameter sensitivity analysis."""
from __future__ import annotations

import json
import logging
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.walkforward.runner import WalkForwardConfig, WalkForwardRunner
from src.backtest.engine.data_replay import DataReplay
from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum

log = logging.getLogger(__name__)

# Default grids
LOOKBACK_LONG_GRID = (126, 189, 252, 378, 504)
VOL_WINDOW_GRID = (20, 30, 60, 90)
THRESHOLD_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def run_sensitivity_grid(
    prices: pd.DataFrame,
    lookback_longs: tuple[int, ...] = LOOKBACK_LONG_GRID,
    vol_windows: tuple[int, ...] = VOL_WINDOW_GRID,
    thresholds: tuple[float, ...] = THRESHOLD_GRID,
    wf_config: WalkForwardConfig | None = None,
    output_dir: Path | str | None = None,
) -> dict:
    """Run grid search over S1 parameters, return sensitivity results.

    For each combination, runs a walk-forward backtest and records OOS Sharpe.
    Returns dict with:
      - surface_lookback_vol: DataFrame (lookback_long x vol_window) of OOS Sharpe
      - surface_threshold_vol: DataFrame (threshold x vol_window) of OOS Sharpe
      - all_results: list of dicts with all parameter combos + Sharpe
      - base_sharpe: OOS Sharpe for base parameters
    """
    wf_config = wf_config or WalkForwardConfig(in_sample_days=400, out_of_sample_days=150)

    # Base case
    base_config = S1Config()
    base_sharpe = _run_single(prices, base_config, wf_config)
    log.info("Base parameters OOS Sharpe: %.4f", base_sharpe)

    # Grid 1: lookback_long x vol_window (threshold=0.0)
    lv_rows = []
    for lb_long, vw in product(lookback_longs, vol_windows):
        cfg = S1Config(
            lookbacks=(21, 63, 126, lb_long),
            vol_window_signal=vw,
            vol_window_sizing=vw,
            signal_threshold=0.0,
        )
        sharpe = _run_single(prices, cfg, wf_config)
        lv_rows.append({
            "lookback_long": lb_long,
            "vol_window": vw,
            "oos_sharpe": sharpe,
        })

    surface_lv = pd.DataFrame(lv_rows).pivot_table(
        index="lookback_long", columns="vol_window", values="oos_sharpe"
    )

    # Grid 2: threshold x vol_window (lookbacks=default)
    tv_rows = []
    for thresh, vw in product(thresholds, vol_windows):
        cfg = S1Config(
            lookbacks=base_config.lookbacks,
            vol_window_signal=vw,
            vol_window_sizing=vw,
            signal_threshold=thresh,
        )
        sharpe = _run_single(prices, cfg, wf_config)
        tv_rows.append({
            "threshold": thresh,
            "vol_window": vw,
            "oos_sharpe": sharpe,
        })

    surface_tv = pd.DataFrame(tv_rows).pivot_table(
        index="threshold", columns="vol_window", values="oos_sharpe"
    )

    all_results = lv_rows + tv_rows

    result = {
        "surface_lookback_vol": surface_lv,
        "surface_threshold_vol": surface_tv,
        "all_results": all_results,
        "base_sharpe": base_sharpe,
    }

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        _save_report(result, output_dir)

    return result


def _run_single(
    prices: pd.DataFrame,
    config: S1Config,
    wf_config: WalkForwardConfig,
) -> float:
    """Run single walk-forward backtest, return OOS Sharpe."""
    try:
        strat = TimeSeriesMomentum(prices, config)
        if not strat.health_check():
            return float("nan")
        replay = DataReplay(prices)
        runner = WalkForwardRunner(wf_config=wf_config)
        result = runner.run(replay, strat)
        return float(result.aggregate_metrics.get("mean_sharpe", 0.0))
    except Exception as e:
        log.warning("Sensitivity run failed: %s", e)
        return float("nan")


def _save_report(result: dict, output_dir: Path) -> None:
    """Save sensitivity report as JSON and simple text summary."""
    # Serialize surfaces
    lv = result["surface_lookback_vol"]
    tv = result["surface_threshold_vol"]

    report = {
        "base_sharpe": result["base_sharpe"],
        "surface_lookback_vol": lv.to_dict(),
        "surface_threshold_vol": tv.to_dict(),
        "all_results": result["all_results"],
    }

    (output_dir / "sensitivity.json").write_text(
        json.dumps(report, indent=2, default=str)
    )

    # Text summary
    lines = ["=== S1 Sensitivity Analysis ===", ""]
    lines.append(f"Base OOS Sharpe: {result['base_sharpe']:.4f}")
    lines.append("")
    lines.append("OOS Sharpe by lookback_long x vol_window:")
    lines.append(lv.to_string())
    lines.append("")
    lines.append("OOS Sharpe by threshold x vol_window:")
    lines.append(tv.to_string())
    lines.append("")

    # Check: is base near-optimum?
    if not lv.empty:
        max_sharpe = float(lv.max().max())
        base_diff = abs(max_sharpe - result["base_sharpe"])
        lines.append(f"Best lookback-vol Sharpe: {max_sharpe:.4f} (diff from base: {base_diff:.4f})")
        if base_diff < 0.1:
            lines.append("=> Base parameters are NEAR-OPTIMUM (within 0.1 Sharpe of best)")
        else:
            lines.append("=> Base parameters are NOT near-optimum - consider tuning")

    (output_dir / "sensitivity_report.txt").write_text("\n".join(lines))
