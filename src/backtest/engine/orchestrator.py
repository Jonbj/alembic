"""Main backtest orchestrator: event loop."""
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
from typing import Callable, Protocol

import pandas as pd

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import Fill, MarketSnapshot, Order, PortfolioSnapshot


class CostModel(Protocol):
    def simulate_fill(self, order: Order, market: MarketSnapshot) -> Fill: ...


log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    spread_bps: float = 5.0            # used only when cost_model is SimpleCostModel
    commission_per_share: float = 0.0  # used only when cost_model is SimpleCostModel
    cost_model_path: Path = Path("config/cost_model.yaml")


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

    def __init__(
        self,
        config: BacktestConfig,
        cost_model: CostModel | None = None,
    ) -> None:
        self.config = config
        if cost_model is not None:
            self.cost_model: CostModel = cost_model
        else:
            from src.backtest.costs.realistic import RealisticCostModel
            self.cost_model = RealisticCostModel(config_path=config.cost_model_path)

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
