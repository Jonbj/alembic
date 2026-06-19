"""Walk-forward runner: rolling window orchestration."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Callable

import pandas as pd

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator, BacktestResult

log = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    in_sample_days: int = 504        # ~2 trading years IS
    out_of_sample_days: int = 252    # ~1 trading year OOS
    step_days: int | None = None     # step size; defaults to out_of_sample_days (non-overlapping OOS)
    initial_capital: float = 100_000.0


@dataclass
class WindowResult:
    window_idx: int
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime
    oos_result: BacktestResult
    oos_metrics: dict = field(default_factory=dict)
    is_sharpe: float = 0.0


@dataclass
class WalkForwardResult:
    config: WalkForwardConfig
    windows: list[WindowResult]
    aggregate_metrics: dict = field(default_factory=dict)


class WalkForwardRunner:
    """Rolling walk-forward backtester.

    Each window:
    - IS period: strategy warms up using historical data via DataReplay
    - OOS period: performance is measured
    The strategy runs on the full IS+OOS window; only OOS snapshots feed metrics.
    """

    def __init__(
        self,
        wf_config: WalkForwardConfig | None = None,
        backtest_config: BacktestConfig | None = None,
        cost_model=None,
    ) -> None:
        self.wf_config = wf_config or WalkForwardConfig()
        self.backtest_config = backtest_config or BacktestConfig(
            initial_capital=self.wf_config.initial_capital
        )
        self.cost_model = cost_model

    def run(
        self,
        data_replay: DataReplay,
        strategy_callable: Callable,
    ) -> WalkForwardResult:
        """Generate windows, run backtest per window, collect OOS metrics."""
        cfg = self.wf_config
        step = cfg.step_days if cfg.step_days is not None else cfg.out_of_sample_days
        timesteps = data_replay.timesteps()
        n = len(timesteps)

        log.info(
            "Walk-forward: %d total timesteps, IS=%d OOS=%d step=%d",
            n, cfg.in_sample_days, cfg.out_of_sample_days, step,
        )

        windows: list[WindowResult] = []
        window_idx = 0
        is_start_idx = 0

        while True:
            is_end_idx = is_start_idx + cfg.in_sample_days - 1
            oos_start_idx = is_end_idx + 1
            oos_end_idx = oos_start_idx + cfg.out_of_sample_days - 1

            if oos_end_idx >= n:
                break

            is_start = timesteps[is_start_idx]
            is_end = timesteps[is_end_idx]
            oos_start = timesteps[oos_start_idx]
            oos_end = timesteps[oos_end_idx]

            log.debug(
                "Window %d: IS %s→%s | OOS %s→%s",
                window_idx, is_start.date(), is_end.date(), oos_start.date(), oos_end.date(),
            )

            # Slice data to IS+OOS window for this run
            prices_window = data_replay._prices.iloc[is_start_idx : oos_end_idx + 1]
            volumes_window = (
                data_replay._volumes.iloc[is_start_idx : oos_end_idx + 1]
                if data_replay._volumes is not None
                else None
            )
            window_replay = DataReplay(prices_window, volumes_window)

            orc = BacktestOrchestrator(self.backtest_config, self.cost_model)
            full_result = orc.run(window_replay, strategy_callable)

            # Only snapshots in OOS period feed the metrics
            oos_snapshots = [s for s in full_result.snapshots if s.timestamp >= oos_start]
            oos_metrics = _compute_window_metrics(oos_snapshots)

            # IS Sharpe: snapshots in IS period only
            is_snapshots = [s for s in full_result.snapshots if s.timestamp < oos_start]
            is_metrics = _compute_window_metrics(is_snapshots)
            is_sharpe = float(is_metrics.get("sharpe", 0.0))

            windows.append(WindowResult(
                window_idx=window_idx,
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
                oos_result=full_result,
                oos_metrics=oos_metrics,
                is_sharpe=is_sharpe,
            ))

            window_idx += 1
            is_start_idx += step

        if not windows:
            log.warning(
                "Walk-forward produced 0 windows — dataset too short "
                "(need >= %d timesteps, got %d)",
                cfg.in_sample_days + cfg.out_of_sample_days, n,
            )

        from src.backtest.walkforward.aggregator import WalkForwardAggregator
        aggregate_metrics = WalkForwardAggregator().aggregate(windows)

        return WalkForwardResult(config=cfg, windows=windows, aggregate_metrics=aggregate_metrics)


def _compute_window_metrics(snapshots) -> dict:
    """Compute performance metrics for a list of PortfolioSnapshot (OOS period)."""
    if len(snapshots) < 2:
        return {"error": "insufficient_data", "n_days": len(snapshots)}

    navs = pd.Series([s.total_nav for s in snapshots])
    returns = navs.pct_change().dropna()

    if returns.empty or returns.std() == 0:
        return {
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "n_days": len(snapshots),
            "start_nav": round(float(navs.iloc[0]), 2),
            "end_nav": round(float(navs.iloc[-1]), 2),
        }

    n_days = len(navs)
    total_return = float(navs.iloc[-1] / navs.iloc[0] - 1)
    annualized_return = float((1 + total_return) ** (252 / n_days) - 1)
    sharpe = float(returns.mean() / returns.std() * (252 ** 0.5))

    peak = navs.cummax()
    drawdown = (navs - peak) / peak
    max_drawdown = float(drawdown.min())

    calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    return {
        "annualized_return": round(annualized_return, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_drawdown, 4),
        "calmar": round(calmar, 4),
        "n_days": n_days,
        "start_nav": round(float(navs.iloc[0]), 2),
        "end_nav": round(float(navs.iloc[-1]), 2),
    }
