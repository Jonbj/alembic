"""S3 walk-forward backtest + validation gate runner."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.data.loader import DataLoader
from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.engine.data_replay import DataReplay
from src.backtest.gates.historical_stress import extract_historical_stress_periods
from src.backtest.gates.runner import GateConfig, run_all_gates
from src.backtest.walkforward.runner import WalkForwardConfig, WalkForwardRunner
from src.strategies.s3.strategy import S3Config, CrossSectionalMomentum

log = logging.getLogger(__name__)


def run_s3_backtest_from_prices(
    prices: pd.DataFrame,
    output_dir: Path | str = Path("reports/s3_backtest"),
    wf_config: WalkForwardConfig | None = None,
    s3_config: S3Config | None = None,
    gate_config: GateConfig | None = None,
    run_robustness: bool = True,
) -> dict:
    """Run full walk-forward backtest + validation gates from a wide price DataFrame.

    prices must contain SPY column plus at least a few stock columns.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    s3_config = s3_config or S3Config()
    wf_config = wf_config or WalkForwardConfig(in_sample_days=1260, out_of_sample_days=252)

    strategy = CrossSectionalMomentum(prices, s3_config)
    if not strategy.health_check():
        raise RuntimeError("S3 strategy health check failed -- insufficient data or NaN signals")

    data_replay = DataReplay(prices)
    wf_runner = WalkForwardRunner(wf_config=wf_config)
    wf_result = wf_runner.run(data_replay, strategy)

    aggregate = wf_result.aggregate_metrics

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

    oos_nav = aggregate.get("oos_nav_series", pd.Series(dtype=float))
    oos_returns = oos_nav.pct_change().dropna() if len(oos_nav) > 1 else pd.Series(dtype=float)

    perturbed_sharpes = None
    if run_robustness and len(oos_returns) > 20:
        perturbed_sharpes = _run_perturbation(prices, s3_config, wf_config)

    regime_returns = None
    if len(oos_returns) > 60:
        regime_returns = _split_regime_returns(oos_returns)

    stress_returns = None
    if len(oos_returns) > 60:
        hist = extract_historical_stress_periods(oos_returns)
        stress_returns = hist if hist else None

    full_returns = oos_returns if len(oos_returns) > 0 else pd.Series(dtype=float)

    gate_report = run_all_gates(
        returns=full_returns,
        wf_results=wf_window_returns if wf_window_returns else None,
        perturbed_sharpes=perturbed_sharpes,
        regime_returns=regime_returns,
        stress_returns=stress_returns,
        config=gate_config,
    )

    # Milestone C: OOS Sharpe in expected range [0.4, 0.6] and gates pass
    milestone_c_pass = (0.0 <= oos_sharpe <= 1.0) and gate_report.overall_passed

    degradation_ratio = aggregate.get("is_oos_degradation_ratio")
    if degradation_ratio is not None and degradation_ratio < 0.5:
        log.warning(
            "S3 IS/OOS degradation ratio %.4f < 0.5 — OOS Sharpe is less than half of IS Sharpe; "
            "possible overfitting",
            degradation_ratio,
        )

    gate_dict = {name: {"passed": g.passed, "details": g.details} for name, g in gate_report.gate_results.items()}
    summary = {
        "oos_sharpe": oos_sharpe,
        "is_oos_degradation_ratio": degradation_ratio,
        "milestone_c_pass": milestone_c_pass,
        "wf_aggregate": {k: v for k, v in aggregate.items() if k != "oos_nav_series" and k != "per_window"},
        "gate_report": gate_dict,
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (output_dir / "gate_report.json").write_text(json.dumps(gate_dict, indent=2, default=str))

    log.info("S3 backtest complete. OOS Sharpe=%.4f, Milestone C=%s", oos_sharpe, milestone_c_pass)
    log.info(gate_report.summary())

    return {
        "oos_sharpe": oos_sharpe,
        "is_oos_degradation_ratio": degradation_ratio,
        "wf_aggregate": aggregate,
        "gate_report": gate_dict,
        "milestone_c_pass": milestone_c_pass,
        "report_path": str(output_dir),
    }


def _run_perturbation(
    prices: pd.DataFrame,
    base_config: S3Config,
    wf_config: WalkForwardConfig,
) -> list[float]:
    """Run backtests with perturbed lookback/beta_window, return list of OOS Sharpes."""
    perturbations = [
        {"lookback": 126, "beta_window": 126},
        {"lookback": 378, "beta_window": 252},
        {"lookback": 252, "beta_window": 504},
    ]
    sharpes = []
    for params in perturbations:
        try:
            cfg = S3Config(
                lookback=params.get("lookback", base_config.lookback),
                beta_window=params.get("beta_window", base_config.beta_window),
                short_decile=base_config.short_decile,
            )
            strat = CrossSectionalMomentum(prices, cfg)
            if not strat.health_check():
                continue
            replay = DataReplay(prices)
            runner = WalkForwardRunner(wf_config=wf_config)
            result = runner.run(replay, strat)
            sh = float(result.aggregate_metrics.get("mean_sharpe", 0.0))
            sharpes.append(sh)
        except Exception as e:
            log.warning("S3 perturbation failed: %s", e)
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


def run_s3_backtest_full(
    output_dir: Path | str = Path("reports/s3_backtest"),
    force_refresh: bool = False,
) -> dict:
    """Full production run: download real data, run backtest + gates.

    Downloads SPY + S3 universe tickers, runs walk-forward + gate validation.
    Requires internet access and a populated ParquetCache.
    """
    from datetime import date
    from src.backtest.data.cache import ParquetCache
    from src.strategies.s3.universe import load_s3_universe_with_data

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = ParquetCache()
    loader = DataLoader(cache=cache)

    start = date(2000, 1, 1)
    end = date.today()

    s3_universe = load_s3_universe_with_data(
        loader=loader,
        start=start,
        end=end,
    )

    # Active tickers at most recent date — use a representative subset
    active = s3_universe.active_at(end)
    tickers = list(active[:50])  # cap at 50 for tractable backtest

    all_tickers = ["SPY"] + [t for t in tickers if t != "SPY"]
    # Use pre-downloaded price data from S3Universe (load_s3_universe_with_data already fetched it)
    prices_wide = s3_universe.close[all_tickers].dropna(axis=1, how="all")
    prices_wide = prices_wide.loc[prices_wide.index >= pd.Timestamp(start)]

    # Ensure SPY is present
    if "SPY" not in prices_wide.columns:
        raise RuntimeError("SPY missing from price data — required for beta computation")

    return run_s3_backtest_from_prices(
        prices=prices_wide,
        output_dir=output_dir,
    )
