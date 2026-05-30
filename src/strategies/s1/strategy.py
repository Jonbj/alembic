"""S1 Time-Series Momentum strategy module."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import (
    MarketSnapshot,
    Order,
    OrderSide,
    RebalanceFrequency,
)
from src.strategies.s1.signal import generate_signals


@dataclass
class S1Config:
    strategy_id: str = "S1"
    lookbacks: tuple[int, ...] = (21, 63, 126, 252)
    vol_window_signal: int = 63
    vol_window_sizing: int = 60
    target_vol: float = 0.10
    max_weight: float = 0.20
    signal_threshold: float = 0.0
    rebalance_frequency: RebalanceFrequency = RebalanceFrequency.MONTHLY

    @classmethod
    def from_yaml(cls, path: Path | str) -> "S1Config":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(
            strategy_id=data.get("strategy_id", "S1"),
            lookbacks=tuple(int(x) for x in data.get("lookbacks", [21, 63, 126, 252])),
            vol_window_signal=int(data.get("vol_window_signal", 63)),
            vol_window_sizing=int(data.get("vol_window_sizing", 60)),
            target_vol=float(data.get("target_vol", 0.10)),
            max_weight=float(data.get("max_weight", 0.20)),
            signal_threshold=float(data.get("signal_threshold", 0.0)),
            rebalance_frequency=RebalanceFrequency(
                data.get("rebalance_frequency", "MONTHLY")
            ),
        )


class TimeSeriesMomentum:
    """S1: Time-Series Momentum strategy, compatible with BacktestOrchestrator.

    Pre-computes signals and weights at construction time from the full price
    history. Each __call__ invocation looks up the nearest precomputed date,
    eliminating per-tick recomputation.
    """

    def __init__(self, prices: pd.DataFrame, config: S1Config) -> None:
        self._config = config
        self._combined = generate_signals(
            prices,
            lookbacks=config.lookbacks,
            vol_window_signal=config.vol_window_signal,
            vol_window_sizing=config.vol_window_sizing,
            target_vol=config.target_vol,
            max_weight=config.max_weight,
        )
        if not self._combined.empty:
            self._signal_wide: pd.DataFrame = self._combined.pivot(
                index="as_of", columns="ticker", values="signal"
            )
            self._weight_wide: pd.DataFrame = self._combined.pivot(
                index="as_of", columns="ticker", values="weight"
            )
        else:
            self._signal_wide = pd.DataFrame()
            self._weight_wide = pd.DataFrame()
        self._last_rebalance: Optional[datetime] = None

    def compute_target_weights(self, prices_wide: pd.DataFrame) -> dict[str, float]:
        """Return {ticker: weight} for tickers with signal > threshold at latest date.

        Looks up the closest precomputed signal date <= prices_wide.index[-1].
        Returns empty dict if no valid signal is available.
        """
        if self._signal_wide.empty or self._weight_wide.empty:
            return {}

        as_of = prices_wide.index[-1]
        valid_dates = self._signal_wide.index[self._signal_wide.index <= as_of]
        if len(valid_dates) == 0:
            return {}
        lookup_date = valid_dates[-1]

        signals_row = self._signal_wide.loc[lookup_date]
        weights_row = self._weight_wide.loc[lookup_date]
        threshold = self._config.signal_threshold

        return {
            ticker: float(weights_row[ticker])
            for ticker in signals_row.index
            if (
                pd.notna(signals_row[ticker])
                and pd.notna(weights_row[ticker])
                and signals_row[ticker] > threshold
            )
        }

    def health_check(self) -> bool:
        """Return True when precomputed signals are non-empty, finite, and NaN-free."""
        if self._combined.empty:
            return False
        if self._combined["signal"].isna().any():
            return False
        if self._combined["weight"].isna().any():
            return False
        if np.isinf(self._combined["signal"]).any():
            return False
        if np.isinf(self._combined["weight"]).any():
            return False
        return True

    def _should_rebalance(self, ts: datetime) -> bool:
        if self._config.rebalance_frequency == RebalanceFrequency.DAILY:
            return True
        if self._last_rebalance is None:
            return True
        if self._config.rebalance_frequency == RebalanceFrequency.WEEKLY:
            return (
                ts.isocalendar().week != self._last_rebalance.isocalendar().week
                or ts.year != self._last_rebalance.year
            )
        # MONTHLY
        return (
            ts.month != self._last_rebalance.month
            or ts.year != self._last_rebalance.year
        )

    def _nav(self, portfolio: VirtualPortfolio, market: MarketSnapshot) -> float:
        nav = portfolio.cash
        for pos in portfolio.all_positions():
            price = market.price_of(pos.symbol)
            if price is not None:
                nav += pos.market_value(price)
        return nav

    def __call__(
        self,
        ts: datetime,
        data_replay: DataReplay,
        portfolio: VirtualPortfolio,
        market: MarketSnapshot,
    ) -> list[Order]:
        if not self._should_rebalance(ts):
            return []

        self._last_rebalance = ts
        target_weights = self.compute_target_weights(data_replay.prices_until(ts))
        nav = self._nav(portfolio, market)
        orders: list[Order] = []

        # Exit: close positions absent from target
        for pos in portfolio.all_positions():
            if pos.symbol not in target_weights:
                price = market.price_of(pos.symbol)
                if price is not None and pos.quantity > 0:
                    orders.append(
                        Order.market_order(
                            ts=ts,
                            symbol=pos.symbol,
                            side=OrderSide.SELL,
                            qty=pos.quantity,
                            strategy_id=self._config.strategy_id,
                        )
                    )

        # Entry / rebalance: move toward target weights
        for ticker, target_wt in target_weights.items():
            price = market.price_of(ticker)
            if price is None or price <= 0:
                continue
            target_qty = (nav * target_wt) / price
            current_pos = portfolio.position_of(ticker)
            current_qty = current_pos.quantity if current_pos is not None else 0.0
            delta = target_qty - current_qty

            if abs(delta) < 1e-4:
                continue

            if delta > 0:
                orders.append(
                    Order.market_order(
                        ts=ts,
                        symbol=ticker,
                        side=OrderSide.BUY,
                        qty=delta,
                        strategy_id=self._config.strategy_id,
                    )
                )
            else:
                orders.append(
                    Order.market_order(
                        ts=ts,
                        symbol=ticker,
                        side=OrderSide.SELL,
                        qty=-delta,
                        strategy_id=self._config.strategy_id,
                    )
                )

        return orders
