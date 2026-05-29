"""Main backtest orchestrator: event loop."""
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Callable

import pandas as pd

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.order_simulation import SimpleCostModel
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, MarketSnapshot, Order, PortfolioSnapshot


log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    spread_bps: float = 5.0
    commission_per_share: float = 0.0


@dataclass
class BacktestResult:
    config: BacktestConfig
    snapshots: tuple[PortfolioSnapshot, ...]
    fills: tuple[Fill, ...]

    def to_nav_series(self) -> pd.Series:
        return pd.Series(
            data=[s.total_nav for s in self.snapshots],
            index=[s.timestamp for s in self.snapshots],
        )

    def to_returns_series(self) -> pd.Series:
        nav = self.to_nav_series()
        return nav.pct_change().dropna()


# Strategy callable: receives context, returns list of orders for that timestep
StrategyCallable = Callable[
    [datetime, DataReplay, VirtualPortfolio, MarketSnapshot],
    list[Order],
]


class BacktestOrchestrator:
    """Main event loop for backtesting."""

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.cost_model = SimpleCostModel(
            spread_bps=config.spread_bps,
            commission_per_share=config.commission_per_share,
        )

    def run(
        self,
        data_replay: DataReplay,
        strategy_callable: Callable,
    ) -> BacktestResult:
        """Run backtest end-to-end."""
        portfolio = VirtualPortfolio(initial_cash=self.config.initial_capital)

        timesteps = data_replay.timesteps()
        log.info(
            "Running backtest on %d timesteps from %s to %s",
            len(timesteps),
            timesteps[0],
            timesteps[-1],
        )

        for ts in timesteps:
            try:
                market = data_replay.market_at(ts)
            except ValueError as e:
                log.warning("Skip timestep %s: %s", ts, e)
                continue

            orders: list[Order] = strategy_callable(ts, data_replay, portfolio, market)

            for order in orders:
                try:
                    fill = self.cost_model.simulate_fill(order, market)
                    portfolio.apply_fill(fill)
                except ValueError as e:
                    log.warning("Could not fill %s: %s", order, e)

            portfolio.mark_to_market(market)

        return BacktestResult(
            config=self.config,
            snapshots=portfolio.get_snapshots(),
            fills=portfolio.get_fills(),
        )
