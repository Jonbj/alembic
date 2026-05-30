"""S3 Cross-Sectional Residual Momentum strategy module."""
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
from src.strategies.s3.signal import generate_s3_signals


@dataclass
class S3Config:
    strategy_id: str = "S3"
    lookback: int = 252
    beta_window: int = 252
    n_deciles: int = 10
    target_vol: float = 0.10
    max_weight: float = 0.20
    long_decile: int = 10
    short_decile: Optional[int] = 1
    rebalance_frequency: RebalanceFrequency = RebalanceFrequency.MONTHLY

    @classmethod
    def from_yaml(cls, path: Path | str) -> "S3Config":
        with open(path) as f:
            data = yaml.safe_load(f)
        short_decile = data.get("short_decile", 1)
        return cls(
            strategy_id=data.get("strategy_id", "S3"),
            lookback=int(data.get("lookback", 252)),
            beta_window=int(data.get("beta_window", 252)),
            n_deciles=int(data.get("n_deciles", 10)),
            target_vol=float(data.get("target_vol", 0.10)),
            max_weight=float(data.get("max_weight", 0.20)),
            long_decile=int(data.get("long_decile", 10)),
            short_decile=int(short_decile) if short_decile is not None else None,
            rebalance_frequency=RebalanceFrequency(
                data.get("rebalance_frequency", "MONTHLY")
            ),
        )


class CrossSectionalMomentum:
    """S3: Cross-Sectional Residual Momentum strategy, compatible with BacktestOrchestrator.

    Long top decile, short bottom decile (or long-only if short_decile=None).
    Pre-computes signals at construction. Rebalances monthly by default.
    Requires SPY as market proxy in the prices DataFrame.
    """

    def __init__(self, prices: pd.DataFrame, config: S3Config) -> None:
        self._config = config
        self._signals = generate_s3_signals(
            prices,
            market_col="SPY",
            lookback=config.lookback,
            beta_window=config.beta_window,
            n_deciles=config.n_deciles,
        )

        if not self._signals.empty:
            self._rank_wide: pd.DataFrame = self._signals.pivot(
                index="as_of", columns="ticker", values="decile"
            )
            self._rm_wide: pd.DataFrame = self._signals.pivot(
                index="as_of", columns="ticker", values="residual_momentum"
            )
        else:
            self._rank_wide = pd.DataFrame()
            self._rm_wide = pd.DataFrame()

        # Precompute per-ticker volatility from prices (excluding SPY)
        stock_cols = [c for c in prices.columns if c != "SPY"]
        daily_rets = prices[stock_cols].pct_change()
        self._vol: pd.Series = daily_rets.rolling(config.beta_window).std().iloc[-1] * np.sqrt(252)

        self._last_rebalance: Optional[datetime] = None

    def compute_target_weights(self, prices_wide: pd.DataFrame) -> dict[str, float]:
        """Return {ticker: weight} for top decile (long) and bottom decile (short).

        Inverse-vol sizing capped at max_weight. Short positions have negative weights.
        """
        if self._rank_wide.empty:
            return {}

        as_of = prices_wide.index[-1]
        valid_dates = self._rank_wide.index[self._rank_wide.index <= as_of]
        if len(valid_dates) == 0:
            return {}
        lookup_date = valid_dates[-1]

        rank_row = self._rank_wide.loc[lookup_date]
        cfg = self._config

        long_tickers = [t for t in rank_row.index if pd.notna(rank_row[t]) and int(rank_row[t]) == cfg.long_decile]
        short_tickers: list[str] = []
        if cfg.short_decile is not None:
            short_tickers = [t for t in rank_row.index if pd.notna(rank_row[t]) and int(rank_row[t]) == cfg.short_decile]

        weights: dict[str, float] = {}

        for ticker in long_tickers:
            vol = self._vol.get(ticker, np.nan) if isinstance(self._vol, pd.Series) else np.nan
            if pd.isna(vol) or vol <= 0:
                raw_w = cfg.target_vol
            else:
                raw_w = cfg.target_vol / vol
            weights[ticker] = min(raw_w, cfg.max_weight)

        for ticker in short_tickers:
            vol = self._vol.get(ticker, np.nan) if isinstance(self._vol, pd.Series) else np.nan
            if pd.isna(vol) or vol <= 0:
                raw_w = cfg.target_vol
            else:
                raw_w = cfg.target_vol / vol
            weights[ticker] = -min(raw_w, cfg.max_weight)

        return weights

    def health_check(self) -> bool:
        """Return True when precomputed signals are non-empty, finite, and NaN-free."""
        if self._signals.empty:
            return False
        if self._signals["residual_momentum"].isna().any():
            return False
        if np.isinf(self._signals["residual_momentum"]).any():
            return False
        if self._signals["decile"].isna().any():
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
                if price is not None and pos.quantity != 0:
                    side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
                    orders.append(
                        Order.market_order(
                            ts=ts,
                            symbol=pos.symbol,
                            side=side,
                            qty=abs(pos.quantity),
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
