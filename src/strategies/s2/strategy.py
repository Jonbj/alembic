"""S2 VRP strategy module: short-put selling with regime modulation and event filter.

Implements StrategyCallable interface for use with BacktestOrchestrator and
WalkForwardRunner. The strategy:

1. On each rebalance date, checks regime modulation (bull/sideways/bear/high_vol).
2. If regime allows, checks event filter (FOMC/NFP proximity, sentiment).
3. If allowed, calls select_put() to find the best put to sell.
4. Tracks open positions and evaluates exits via evaluate_exit().
5. Generates BUY/SELL Orders for the backtest engine.

For synthetic backtesting, short put is modeled as:
  - SELL order at entry (collect premium * qty * 100)
  - BUY order at exit (pay premium * qty * 100 to close)
  - Symbol: "SPY_PUT" to distinguish from SPY equity
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import (
    MarketSnapshot,
    Order,
    OrderSide,
    RebalanceFrequency,
)
from src.data.options.ingestion import OptionChainDataLoader
from src.models.regime import RegimeLabel
from src.strategies.s2.config import S2Config
from src.strategies.s2.event_filter import check_event_filter
from src.strategies.s2.exit import ExitReason, evaluate_exit, compute_pnl
from src.strategies.s2.regime import modulate_by_regime, apply_regime_scale
from src.strategies.s2.signal import PutSignal, select_put

log = logging.getLogger(__name__)

# Symbol used in backtest orders for short-put positions
_PUT_SYMBOL = "SPY_PUT"


@dataclass
class OpenPosition:
    """Track an open short-put position in the backtest."""
    signal: PutSignal
    entry_date: date
    entry_underlying_price: float
    entry_mid: float  # premium received at entry (mid price)
    quantity: int
    # Current mid price tracking for exit evaluation — set on each call
    current_mid: float = 0.0
    current_underlying_price: float = 0.0
    current_implied_vol: float | None = None


class VRPStrategy:
    """S2: Volatility Risk Premium strategy, compatible with BacktestOrchestrator.

    On each rebalance date:
      1. Evaluate exit for any open position.
      2. If no open position and conditions allow, enter new short put.

    The strategy tracks at most ONE open short-put position at a time
    (consistent with the max_collateral_pct constraint).
    """

    def __init__(self, prices: pd.DataFrame, config: S2Config | None = None) -> None:
        self._config = config or S2Config()
        self._prices = prices
        self._chain_loader = OptionChainDataLoader()

        # Pre-compute realized volatility (63-day rolling) for VRP estimation
        spy_close = prices["SPY"] if "SPY" in prices.columns else prices.iloc[:, 0]
        self._realized_vol = spy_close.pct_change().rolling(63).std() * np.sqrt(252)
        self._realized_vol.name = "realized_vol"

        # Track open position
        self._open_position: Optional[OpenPosition] = None
        self._last_rebalance: Optional[datetime] = None

    def health_check(self) -> bool:
        """Verify enough data and configuration are valid."""
        if self._prices.empty:
            return False
        if len(self._prices) < 252:
            return False
        if self._realized_vol.dropna().empty:
            return False
        return True

    def _should_rebalance(self, ts: datetime) -> bool:
        """Rebalance monthly (consistent with option DTE cycle)."""
        if self._last_rebalance is None:
            return True
        return (
            ts.month != self._last_rebalance.month
            or ts.year != self._last_rebalance.year
        )

    def _get_regime(self, ts: datetime) -> RegimeLabel:
        """Determine regime from realized volatility.

        Simple vol-based classification:
          - realized_vol < 0.12 → bull
          - 0.12 <= realized_vol < 0.20 → sideways
          - 0.20 <= realized_vol < 0.35 → bear
          - realized_vol >= 0.35 → high_vol
        """
        ts_date = ts.date() if isinstance(ts, datetime) else ts
        vol = self._realized_vol.get(ts, None) if ts in self._realized_vol.index else None

        if vol is None:
            # Look for nearest prior date
            prior = self._realized_vol.index[self._realized_vol.index <= pd.Timestamp(ts)]
            if len(prior) > 0:
                vol = float(self._realized_vol.loc[prior[-1]])
            else:
                vol = 0.15  # fallback

        if vol < 0.12:
            return "bull"
        elif vol < 0.20:
            return "sideways"
        elif vol < 0.35:
            return "bear"
        else:
            return "high_vol"

    def _get_realized_vol_at(self, ts: datetime) -> float:
        """Get realized volatility at or before ts."""
        ts_pd = pd.Timestamp(ts)
        if ts_pd in self._realized_vol.index:
            return float(self._realized_vol.loc[ts_pd])
        prior = self._realized_vol.index[self._realized_vol.index <= ts_pd]
        if len(prior) > 0:
            return float(self._realized_vol.loc[prior[-1]])
        return 0.15  # fallback

    def _spy_price_at(self, ts: datetime, market: MarketSnapshot) -> float:
        """Get SPY price from market snapshot."""
        price = market.price_of("SPY")
        if price is not None:
            return price
        # Fallback to prices DataFrame
        ts_pd = pd.Timestamp(ts)
        if ts_pd in self._prices.index:
            spy_col = "SPY" if "SPY" in self._prices.columns else self._prices.columns[0]
            return float(self._prices.loc[ts_pd, spy_col])
        # Last resort
        return 450.0

    def _mid_at(self, ts: datetime, signal: PutSignal) -> float:
        """Re-price the put at time ts using synthetic chain."""
        as_of = ts.date() if isinstance(ts, datetime) else ts
        dte = (signal.expiry - as_of).days
        if dte <= 0:
            # Expired or at expiry — full premium captured
            return 0.01  # near-zero cost to close

        # Get current SPY price for synthetic pricing
        spy_price = self._spy_price_at(ts, MarketSnapshot(
            timestamp=ts, prices={"SPY": self._prices.loc[pd.Timestamp(ts), "SPY"] if pd.Timestamp(ts) in self._prices.index else 450.0},
            volumes={}, adv_20d={},
        )) if ts in self._prices.index else signal.strike  # fallback

        # Use Black-Scholes to re-price
        from src.options.pricing import black_scholes_price
        iv = signal.implied_vol
        mid = black_scholes_price(
            S=spy_price,
            K=signal.strike,
            T=dte / 365.0,
            r=0.05,
            sigma=iv,
            right="P",
        )
        return max(mid, 0.01)

    def __call__(
        self,
        ts: datetime,
        data_replay: DataReplay,
        portfolio: VirtualPortfolio,
        market: MarketSnapshot,
    ) -> list[Order]:
        """Generate orders for this timestep.

        On each rebalance:
          1. If there's an open position, check exit conditions.
          2. If exited or no position, check entry conditions.
        """
        orders: list[Order] = []
        ts_date = ts.date() if isinstance(ts, datetime) else ts
        capital = portfolio.cash + sum(
            pos.market_value(market.price_of(pos.symbol) or 0)
            for pos in portfolio.all_positions()
        )
        capital = max(capital, 1.0)  # floor to avoid negative/zero capital

        # ---- EXIT LOGIC ----
        if self._open_position is not None:
            pos = self._open_position
            # Re-price the option at current time
            spy_price = self._spy_price_at(ts, market)
            current_mid = self._mid_at(ts, pos.signal)
            realized_vol = self._get_realized_vol_at(ts)

            exit_signal = evaluate_exit(
                signal=pos.signal,
                current_price=spy_price,
                current_date=ts_date,
                current_mid=current_mid,
                implied_vol=pos.signal.implied_vol,
                realized_vol=realized_vol,
                entry_price=pos.entry_underlying_price,
                config=self._config,
            )

            if exit_signal is not None:
                # Close the position via BUY order (buying back the put)
                orders.append(
                    Order.market_order(
                        ts=ts,
                        symbol=_PUT_SYMBOL,
                        side=OrderSide.BUY,
                        qty=float(pos.quantity),
                        strategy_id="S2",
                    )
                )
                self._open_position = None
                log.debug("S2 EXIT at %s: %s P&L=%.2f", ts_date, exit_signal.reason, exit_signal.pnl)

        # ---- ENTRY LOGIC ----
        if self._open_position is None and self._should_rebalance(ts):
            self._last_rebalance = ts

            # Step 1: Regime modulation
            regime = self._get_regime(ts)
            modulation = modulate_by_regime(regime, self._config)

            if modulation.position_scale <= 0.0:
                log.debug("S2: Regime %s blocks entry at %s", regime, ts_date)
                return orders

            # Step 2: Event filter
            spy_sentiment = None  # Not available in backtest; skip sentiment check
            event_filter = check_event_filter(ts_date, spy_sentiment=spy_sentiment, config=self._config)

            if not event_filter.allowed:
                log.debug("S2: Event filter blocks entry at %s: %s", ts_date, event_filter.reasons)
                return orders

            # Step 3: Select put
            spy_price = self._spy_price_at(ts, market)
            realized_vol = self._get_realized_vol_at(ts)

            signal = select_put(
                as_of=ts_date,
                capital=capital,
                config=self._config,
                underlying_price=spy_price,
                realized_vol=realized_vol,
            )

            if signal is None:
                log.debug("S2: No valid put signal at %s", ts_date)
                return orders

            # Step 4: Apply regime scale
            signal = apply_regime_scale(signal, modulation)
            if signal is None:
                log.debug("S2: Regime scale eliminates position at %s", ts_date)
                return orders

            # Step 5: Enter position via SELL order (selling the put)
            self._open_position = OpenPosition(
                signal=signal,
                entry_date=ts_date,
                entry_underlying_price=spy_price,
                entry_mid=signal.mid,
                quantity=signal.quantity,
            )

            orders.append(
                Order.market_order(
                    ts=ts,
                    symbol=_PUT_SYMBOL,
                    side=OrderSide.SELL,
                    qty=float(signal.quantity),
                    strategy_id="S2",
                )
            )
            log.debug(
                "S2 ENTRY at %s: PUT K=%.1f exp=%s qty=%d premium=%.2f",
                ts_date, signal.strike, signal.expiry, signal.quantity, signal.mid,
            )

        return orders


def compute_target_weights(prices_wide: pd.DataFrame) -> dict[str, float]:
    """Return {ticker: weight} for the S2 strategy.

    For S2, the single position is "SPY_PUT" with weight based on
    collateral requirement vs portfolio value. This is a simplified
    interface for compatibility with the backtest engine.
    """
    return {"SPY_PUT": 0.20}  # max_collateral_pct default
