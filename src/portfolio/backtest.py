"""MultiStrategyBacktester: walk-forward backtest over multiple strategies with portfolio combiner.

T-505: Runs walk-forward windows, aggregating orders from multiple strategies
via PortfolioCombiner, then enforcing constraints, feeding into VirtualPortfolio
to track combined portfolio performance. Computes per-strategy metrics and
measures diversification ratio.
"""
from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, MarketSnapshot, Order, OrderSide, PortfolioSnapshot
from src.backtest.walkforward.runner import WalkForwardConfig, WalkForwardRunner
from src.portfolio.combiner import PortfolioCombiner
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.types import CombinedOrder

log = logging.getLogger(__name__)

# Strategy callable type: (timestamp, data_replay, portfolio, market) -> list[Order]
StrategyCallable = Callable[[datetime, DataReplay, VirtualPortfolio, MarketSnapshot], list[Order]]


@dataclass
class MultiStrategyBacktestConfig:
    """Configuration for multi-strategy walk-forward backtest."""
    in_sample_days: int = 252
    out_of_sample_days: int = 126
    step_days: int | None = None  # defaults to out_of_sample_days (non-overlapping)
    initial_capital: float = 100_000.0
    max_single_asset_pct: float = 0.10
    max_portfolio_exposure: float = 0.50
    max_strategy_overshoot: float = 1.50


@dataclass
class MultiStrategyWindowResult:
    """Result from one walk-forward window of the multi-strategy backtest."""
    window_idx: int
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime
    combined_metrics: dict = field(default_factory=dict)
    individual_metrics: dict[str, dict] = field(default_factory=dict)


@dataclass
class MultiStrategyBacktestResult:
    """Aggregated result of a multi-strategy walk-forward backtest."""
    config: MultiStrategyBacktestConfig
    windows: list[MultiStrategyWindowResult]
    combined_oos_sharpe: float = 0.0
    combined_max_dd: float = 0.0
    combined_calmar: float = 0.0
    diversification_ratio: float = 1.0
    individual_sharpes: dict[str, float] = field(default_factory=dict)
    aggregate_metrics: dict = field(default_factory=dict)


def _try_copy_strategies(
    strategies: dict[str, tuple[StrategyCallable, float]]
) -> dict[str, tuple[StrategyCallable, float]]:
    """Deep-copy strategies to reset internal state for a fresh window run."""
    result = {}
    for sid, (fn, alloc) in strategies.items():
        try:
            result[sid] = (copy.deepcopy(fn), alloc)
        except (TypeError, copy.Error):
            result[sid] = (fn, alloc)
    return result


def _apply_single_strategy_constraints(
    orders: list[Order],
    market: MarketSnapshot,
    nav: float,
    alloc_pct: float,
    max_single_asset_pct: float,
    max_portfolio_exposure: float,
) -> list[Order]:
    """Apply simplified constraints to a single strategy's orders.

    This ensures individual strategy tracking has comparable position sizing
    to the combined run, so diversification ratio is meaningful.
    """
    if nav <= 0 or not orders:
        return orders

    max_notional = max_portfolio_exposure * alloc_pct * nav
    single_asset_cap = max_single_asset_pct * nav

    # Group BUY orders by symbol for max_single_asset check
    buy_by_symbol: dict[str, list[int]] = {}
    for i, o in enumerate(orders):
        if o.side == OrderSide.BUY:
            buy_by_symbol.setdefault(o.symbol, []).append(i)

    result = list(orders)

    # Enforce max_single_asset_pct
    for symbol, idxs in buy_by_symbol.items():
        price = market.price_of(symbol)
        if price is None or price <= 0:
            continue
        total_notional = sum(result[i].quantity * price for i in idxs)
        cap = single_asset_cap
        if total_notional > cap and total_notional > 0:
            scale = cap / total_notional
            for i in idxs:
                result[i] = Order(
                    order_id=result[i].order_id,
                    timestamp=result[i].timestamp,
                    symbol=result[i].symbol,
                    side=result[i].side,
                    quantity=int(result[i].quantity * scale),
                    order_type=result[i].order_type,
                    limit_price=result[i].limit_price,
                    strategy_id=result[i].strategy_id,
                )

    # Enforce max_portfolio_exposure * alloc_pct
    total_buy_notional = 0.0
    for o in result:
        if o.side == OrderSide.BUY:
            price = market.price_of(o.symbol)
            if price is not None:
                total_buy_notional += o.quantity * price

    if total_buy_notional > max_notional and total_buy_notional > 0:
        scale = max_notional / total_buy_notional
        new_result = []
        for o in result:
            if o.side == OrderSide.BUY:
                new_result.append(Order(
                    order_id=o.order_id,
                    timestamp=o.timestamp,
                    symbol=o.symbol,
                    side=o.side,
                    quantity=int(o.quantity * scale),
                    order_type=o.order_type,
                    limit_price=o.limit_price,
                    strategy_id=o.strategy_id,
                ))
            else:
                new_result.append(o)
        result = new_result

    return result


class MultiStrategyBacktester:
    """Walk-forward backtester that runs multiple strategies simultaneously.

    For each walk-forward window:
    1. Deep-copies strategies for combined run and for individual tracking
    2. Combined run: aggregate orders via PortfolioCombiner + ConstraintEnforcer
    3. Individual run: each strategy on its own portfolio (proportional capital)
       with comparable constraint enforcement
    4. Track per-strategy NAV for individual Sharpe computation
    5. Compute diversification ratio = combined_sharpe / weighted_avg_individual_sharpe
    """

    def __init__(
        self,
        strategies: dict[str, tuple[StrategyCallable, float]],
        config: MultiStrategyBacktestConfig | None = None,
    ) -> None:
        self._strategies = strategies
        self._config = config or MultiStrategyBacktestConfig()

    def run(self, data_replay: DataReplay) -> MultiStrategyBacktestResult:
        """Run walk-forward backtest across all strategies."""
        cfg = self._config
        step = cfg.step_days if cfg.step_days is not None else cfg.out_of_sample_days
        timesteps = data_replay.timesteps()
        n = len(timesteps)

        windows: list[MultiStrategyWindowResult] = []
        window_idx = 0
        is_start_idx = 0

        # Load cost model once
        from src.backtest.costs.realistic import RealisticCostModel
        backtest_config = BacktestConfig(initial_capital=cfg.initial_capital)
        cost_model = RealisticCostModel(config_path=backtest_config.cost_model_path)

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

            # Slice data for this window
            prices_window = data_replay._prices.iloc[is_start_idx: oos_end_idx + 1]
            volumes_window = (
                data_replay._volumes.iloc[is_start_idx: oos_end_idx + 1]
                if data_replay._volumes is not None
                else None
            )
            window_replay = DataReplay(prices_window, volumes_window)
            window_timesteps = window_replay.timesteps()

            # Deep-copy strategies for both combined and individual runs
            combined_strategies = _try_copy_strategies(self._strategies)
            individual_strategies = _try_copy_strategies(self._strategies)

            # --- Combined portfolio setup ---
            combined_portfolio = VirtualPortfolio(initial_cash=cfg.initial_capital)
            allocation_map = {sid: alloc for sid, (_, alloc) in combined_strategies.items()}
            combiner = PortfolioCombiner(strategies=combined_strategies)
            enforcer = ConstraintEnforcer(
                max_single_asset_pct=cfg.max_single_asset_pct,
                max_portfolio_exposure=cfg.max_portfolio_exposure,
                max_strategy_overshoot=cfg.max_strategy_overshoot,
            )

            # --- Per-strategy portfolio setup ---
            per_strategy_portfolios: dict[str, VirtualPortfolio] = {}
            for sid, (_, alloc_pct) in individual_strategies.items():
                # Individual strategy starts with its proportional allocation
                per_strategy_portfolios[sid] = VirtualPortfolio(
                    initial_cash=cfg.initial_capital * alloc_pct
                )

            # Track OOS snapshots
            combined_oos_snapshots: list[PortfolioSnapshot] = []
            individual_oos_snapshots: dict[str, list[PortfolioSnapshot]] = {
                sid: [] for sid in individual_strategies
            }

            for ts in window_timesteps:
                try:
                    market = window_replay.market_at(ts)
                except ValueError:
                    continue

                # --- Combined: aggregate, constrain, fill ---
                combined_orders, combined_state = combiner.aggregate(
                    ts, window_replay, combined_portfolio, market
                )
                enforced_orders, _ = enforcer.enforce(
                    combined_orders, market, combined_state.nav, allocation_map
                )
                plain_orders = [
                    Order(
                        order_id=o.order_id,
                        timestamp=o.timestamp,
                        symbol=o.symbol,
                        side=o.side,
                        quantity=o.quantity,
                        order_type=o.order_type,
                        limit_price=o.limit_price,
                        strategy_id=o.strategy_id,
                    )
                    for o in enforced_orders
                ]
                for order in plain_orders:
                    try:
                        fill = cost_model.simulate_fill(order, market)
                        combined_portfolio.apply_fill(fill)
                    except (ValueError, ZeroDivisionError):
                        pass
                combined_portfolio.mark_to_market(market)
                combined_snap = combined_portfolio.get_snapshots()[-1]
                if ts >= oos_start:
                    combined_oos_snapshots.append(combined_snap)

                # --- Per-strategy individual tracking ---
                for sid, (strategy_fn, alloc_pct) in individual_strategies.items():
                    strat_port = per_strategy_portfolios[sid]
                    strat_orders = strategy_fn(ts, window_replay, strat_port, market)

                    # Apply comparable constraints to individual strategy
                    strat_orders = _apply_single_strategy_constraints(
                        strat_orders, market, strat_port.cash + sum(
                            pos.quantity * (market.price_of(pos.symbol) or 0)
                            for pos in strat_port.all_positions()
                            if market.price_of(pos.symbol) is not None
                        ) if strat_port.all_positions() else strat_port.cash,
                        alloc_pct,
                        cfg.max_single_asset_pct,
                        cfg.max_portfolio_exposure,
                    )

                    for order in strat_orders:
                        try:
                            fill = cost_model.simulate_fill(order, market)
                            strat_port.apply_fill(fill)
                        except (ValueError, ZeroDivisionError):
                            pass
                    strat_port.mark_to_market(market)
                    if ts >= oos_start:
                        individual_oos_snapshots[sid].append(strat_port.get_snapshots()[-1])

            # --- Compute window metrics ---
            combined_window_metrics = _compute_window_metrics(combined_oos_snapshots)
            individual_window_metrics: dict[str, dict] = {}
            for sid in individual_strategies:
                individual_window_metrics[sid] = _compute_window_metrics(
                    individual_oos_snapshots[sid]
                )

            windows.append(MultiStrategyWindowResult(
                window_idx=window_idx,
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
                combined_metrics=combined_window_metrics,
                individual_metrics=individual_window_metrics,
            ))

            window_idx += 1
            is_start_idx += step

        if not windows:
            return MultiStrategyBacktestResult(
                config=self._config,
                windows=[],
                combined_oos_sharpe=0.0,
                combined_max_dd=0.0,
                combined_calmar=0.0,
                diversification_ratio=1.0,
                individual_sharpes={},
                aggregate_metrics={"n_windows": 0},
            )

        # --- Aggregate ---
        combined_sharpes: list[float] = []
        individual_sharpes_by_strategy: dict[str, list[float]] = {
            sid: [] for sid in self._strategies
        }
        max_dd_across_windows = 0.0
        calmar_values: list[float] = []

        for w in windows:
            cm = w.combined_metrics
            combined_sharpes.append(cm.get("sharpe", 0.0))
            max_dd_across_windows = min(max_dd_across_windows, cm.get("max_drawdown", 0.0))
            calmar_values.append(cm.get("calmar", 0.0))
            for sid in self._strategies:
                im = w.individual_metrics.get(sid, {})
                individual_sharpes_by_strategy[sid].append(im.get("sharpe", 0.0))

        combined_oos_sharpe = _safe_mean(combined_sharpes)
        individual_sharpes = {
            sid: _safe_mean(sharpes)
            for sid, sharpes in individual_sharpes_by_strategy.items()
        }
        combined_calmar = _safe_mean(calmar_values)
        diversification_ratio = _compute_diversification_ratio(
            individual_sharpes, combined_oos_sharpe, self._strategies
        )

        aggregate_metrics = {
            "combined_oos_sharpe": round(combined_oos_sharpe, 4),
            "combined_max_dd": round(max_dd_across_windows, 4),
            "combined_calmar": round(combined_calmar, 4),
            "diversification_ratio": round(diversification_ratio, 4),
            "n_windows": len(windows),
        }
        for sid, sharpe in individual_sharpes.items():
            aggregate_metrics[f"individual_sharpe_{sid}"] = round(sharpe, 4)

        return MultiStrategyBacktestResult(
            config=self._config,
            windows=windows,
            combined_oos_sharpe=combined_oos_sharpe,
            combined_max_dd=max_dd_across_windows,
            combined_calmar=combined_calmar,
            diversification_ratio=diversification_ratio,
            individual_sharpes=individual_sharpes,
            aggregate_metrics=aggregate_metrics,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(np.mean(values))


def _compute_window_metrics(snapshots: list[PortfolioSnapshot]) -> dict:
    """Compute performance metrics from a list of PortfolioSnapshot."""
    if len(snapshots) < 2:
        return {
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "n_days": len(snapshots),
            "start_nav": snapshots[0].total_nav if snapshots else 0.0,
            "end_nav": snapshots[-1].total_nav if snapshots else 0.0,
        }

    navs = pd.Series([s.total_nav for s in snapshots])
    returns = navs.pct_change().dropna()

    n_days = len(navs)

    if returns.empty or returns.std() == 0:
        total_ret = float(navs.iloc[-1] / navs.iloc[0] - 1) if navs.iloc[0] != 0 else 0.0
        return {
            "annualized_return": 0.0 if total_ret == 0 else float((1 + total_ret) ** (252 / max(n_days, 1)) - 1),
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "n_days": n_days,
            "start_nav": round(float(navs.iloc[0]), 2),
            "end_nav": round(float(navs.iloc[-1]), 2),
        }

    total_return = float(navs.iloc[-1] / navs.iloc[0] - 1)
    annualized_return = float((1 + total_return) ** (252 / n_days) - 1)
    sharpe = float(returns.mean() / returns.std() * (252 ** 0.5))

    peak = navs.cummax()
    drawdown = (navs - peak) / peak
    max_drawdown = float(drawdown.min())

    if max_drawdown == 0:
        max_drawdown = -0.0001

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


def _compute_diversification_ratio(
    individual_sharpes: dict[str, float],
    combined_sharpe: float,
    strategies: dict[str, tuple],
) -> float:
    """Compute diversification ratio.

    diversification_ratio = combined_sharpe / weighted_avg_individual_sharpe
    """
    total_alloc = sum(alloc for _, alloc in strategies.values())
    if total_alloc == 0 or not individual_sharpes:
        return 1.0

    weights = {sid: alloc / total_alloc for sid, (_, alloc) in strategies.items()}
    weighted_avg = sum(
        individual_sharpes.get(sid, 0.0) * weights[sid]
        for sid in weights
    )

    if abs(weighted_avg) < 1e-10:
        if abs(combined_sharpe) < 1e-10:
            return 1.0
        return 1.0

    ratio = combined_sharpe / weighted_avg
    if ratio < 0:
        return 1.0

    return ratio
