"""S4 walk-forward backtest + validation gate runner."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtest.metrics.performance import sharpe_ratio
from src.backtest.engine.data_replay import DataReplay
from src.backtest.gates.historical_stress import extract_historical_stress_periods
from src.backtest.gates.runner import GateConfig, run_all_gates
from src.backtest.walkforward.runner import WalkForwardConfig, WalkForwardRunner
from src.strategies.s4.config import S4Config
from src.strategies.s4.strategy import NewsDrivenTactical

log = logging.getLogger(__name__)


def run_s4_backtest_from_prices_and_signals(
    prices: pd.DataFrame,
    signals_df: pd.DataFrame,
    output_dir: Path | str = Path("reports/s4_backtest"),
    wf_config: WalkForwardConfig | None = None,
    s4_config: S4Config | None = None,
    gate_config: GateConfig | None = None,
    run_robustness: bool = True,
) -> dict:
    """Run full walk-forward backtest + validation gates for S4.

    prices must contain at least a few stock columns (SPY optional but expected).
    signals_df must have columns: symbol, score, confidence, generated_at.
    Optional columns: reasoning, model_id, ensemble_std, fallback_used.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    s4_config = s4_config or S4Config()
    wf_config = wf_config or WalkForwardConfig(in_sample_days=1260, out_of_sample_days=252)

    # Normalize generated_at to tz-naive to match price index timestamps
    if not signals_df.empty and "generated_at" in signals_df.columns:
        signals_df = signals_df.copy()
        if hasattr(signals_df["generated_at"].dtype, "tz") and signals_df["generated_at"].dt.tz is not None:
            signals_df["generated_at"] = signals_df["generated_at"].dt.tz_localize(None)

    strategy = NewsDrivenTactical(s4_config, signals=signals_df)

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
        all_oos = pd.concat(wf_window_returns).sort_index()
        if all_oos.std() > 0:
            oos_sharpe = float(sharpe_ratio(all_oos, periods=252))
        else:
            oos_sharpe = 0.0
    else:
        oos_sharpe = float(aggregate.get("mean_sharpe", 0.0))

    oos_nav = aggregate.get("oos_nav_series", pd.Series(dtype=float))
    oos_returns = oos_nav.pct_change().dropna() if len(oos_nav) > 1 else pd.Series(dtype=float)

    perturbed_sharpes = None
    if run_robustness and len(oos_returns) > 20:
        perturbed_sharpes = _run_perturbation(prices, signals_df, s4_config, wf_config)

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

    # Hard gates for S4: gate 1 (significance) and gate 5 (stress)
    g1 = gate_report.gate_results.get("gate_1_significance")
    g5 = gate_report.gate_results.get("gate_5_stress")
    hard_gates_pass = bool(g1 and g1.passed and g5 and g5.passed)

    degradation_ratio = aggregate.get("is_oos_degradation_ratio")
    if degradation_ratio is not None and degradation_ratio < 0.5:
        log.warning(
            "S4 IS/OOS degradation ratio %.4f < 0.5 — OOS Sharpe is less than half of IS Sharpe; "
            "possible overfitting",
            degradation_ratio,
        )

    gate_dict = {
        name: {"passed": g.passed, "details": g.details}
        for name, g in gate_report.gate_results.items()
    }
    summary = {
        "oos_sharpe": oos_sharpe,
        "is_oos_degradation_ratio": degradation_ratio,
        "hard_gates_pass": hard_gates_pass,
        "all_gates_pass": gate_report.overall_passed,
        "wf_aggregate": {
            k: v
            for k, v in aggregate.items()
            if k not in ("oos_nav_series", "per_window")
        },
        "gate_report": gate_dict,
        "note": "S4 enters portfolio at 10% R&D sleeve regardless of gate results",
    }

    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (output_dir / "gate_report.json").write_text(json.dumps(gate_dict, indent=2, default=str))

    log.info(
        "S4 backtest complete. OOS Sharpe=%.4f, Hard gates=%s, All gates=%s",
        oos_sharpe, hard_gates_pass, gate_report.overall_passed,
    )
    log.info(gate_report.summary())

    gate_report_id = f"s4-gate-{date.today().isoformat()}"
    (output_dir / "gate_report_id.txt").write_text(gate_report_id)

    return {
        "oos_sharpe": oos_sharpe,
        "is_oos_degradation_ratio": degradation_ratio,
        "wf_aggregate": aggregate,
        "gate_report": gate_dict,
        "hard_gates_pass": hard_gates_pass,
        "all_gates_pass": gate_report.overall_passed,
        "report_path": str(output_dir),
        "gate_report_id": gate_report_id,
    }


def _run_perturbation(
    prices: pd.DataFrame,
    signals_df: pd.DataFrame,
    base_config: S4Config,
    wf_config: WalkForwardConfig,
) -> list[float]:
    """Run backtests with perturbed n_top and bucket_pct; return list of OOS Sharpes."""
    perturbations = [
        {"n_top": 3, "bucket_pct": 0.08},
        {"n_top": 5, "bucket_pct": 0.10},
        {"n_top": 7, "bucket_pct": 0.12},
        {"n_top": 3, "bucket_pct": 0.12},
        {"n_top": 7, "bucket_pct": 0.08},
    ]
    sharpes: list[float] = []
    for params in perturbations:
        try:
            n_top = params["n_top"]
            cfg = S4Config(
                n_top=n_top,
                bucket_pct=params["bucket_pct"],
                min_confidence=base_config.min_confidence,
                min_score=base_config.min_score,
                min_stocks=min(n_top, base_config.min_stocks),
                rebalance_frequency=base_config.rebalance_frequency,
            )
            strat = NewsDrivenTactical(cfg, signals=signals_df)
            replay = DataReplay(prices)
            runner = WalkForwardRunner(wf_config=wf_config)
            result = runner.run(replay, strat)
            sh = float(result.aggregate_metrics.get("mean_sharpe", 0.0))
            sharpes.append(sh)
        except Exception as exc:
            log.warning("S4 perturbation failed: %s", exc)
    return sharpes


def _split_regime_returns(oos_returns: pd.Series) -> dict[str, pd.Series]:
    """Split OOS returns into high-vol and low-vol regimes."""
    rolling_vol = oos_returns.rolling(63).std() * np.sqrt(252)
    median_vol = rolling_vol.median()

    high_vol_mask = rolling_vol > median_vol
    low_vol_mask = rolling_vol <= median_vol

    regimes: dict[str, pd.Series] = {}
    if high_vol_mask.any():
        regimes["high_vol"] = oos_returns[high_vol_mask.fillna(False)]
    if low_vol_mask.any():
        regimes["low_vol"] = oos_returns[low_vol_mask.fillna(False)]
    return regimes


def run_s4_backtest_full(
    output_dir: Path | str = Path("reports/s4_backtest"),
) -> dict:
    """Full production run: load price data + sentiment signals, then run backtest + gates.

    Loads prices from DataLoader and sentiment signals from PostgreSQL.
    Falls back to synthetic signals if PostgreSQL is unavailable.
    """
    from datetime import date
    from src.backtest.data.cache import ParquetCache
    from src.backtest.data.loader import DataLoader
    from src.backtest.data.universe import load_universe

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cache = ParquetCache()
    loader = DataLoader(cache=cache)

    universe = load_universe("s1")
    start = date(2010, 1, 1)
    prices_wide = loader.get_aligned_prices(universe, start=start, end=date.today())

    signals_df = _load_sentiment_signals(prices_wide, start=start, end=date.today())

    return run_s4_backtest_from_prices_and_signals(
        prices=prices_wide,
        signals_df=signals_df,
        output_dir=output_dir,
    )


def _load_sentiment_signals(prices: pd.DataFrame, start, end) -> pd.DataFrame:
    """Load historical sentiment signals from PostgreSQL; fall back to synthetic."""
    try:
        from src.store.pg_store import PostgreSQLStore

        with PostgreSQLStore() as store:
            tickers = [c for c in prices.columns if c != "SPY"]
            rows: list[dict] = store.fetch_signals_for_backtest_batch(tickers, str(start), str(end))
        if rows:
            df = pd.DataFrame(rows)
            if "generated_at" not in df.columns:
                df["generated_at"] = pd.Timestamp(start)
            df["generated_at"] = pd.to_datetime(df["generated_at"])
            if df["generated_at"].dt.tz is not None:
                df["generated_at"] = df["generated_at"].dt.tz_localize(None)
            return df
    except Exception as exc:
        log.warning("PostgreSQL signals unavailable (%s); generating synthetic signals", exc)

    return _generate_synthetic_signals(prices)


def _generate_synthetic_signals(prices: pd.DataFrame) -> pd.DataFrame:
    """Generate synthetic sentiment signals aligned to price dates."""
    rng = np.random.default_rng(42)
    tickers = [c for c in prices.columns if c != "SPY"]
    signal_dates = prices.index[::5].tolist()  # ~weekly cadence

    rows = []
    for ts in signal_dates:
        for ticker in tickers:
            rows.append({
                "symbol": ticker,
                "score": float(rng.uniform(-0.5, 0.9)),
                "confidence": float(rng.uniform(0.3, 0.9)),
                "reasoning": "synthetic",
                "model_id": "synthetic",
                "ensemble_std": float(rng.uniform(0.0, 0.1)),
                "fallback_used": False,
                "generated_at": pd.Timestamp(ts),
            })

    return pd.DataFrame(rows)
