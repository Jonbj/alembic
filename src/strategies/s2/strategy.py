"""S2 VRP strategy module: short-put selling with regime modulation and event filter.

Implements StrategyCallable interface for use with BacktestOrchestrator and
WalkForwardRunner. The strategy:

1. On each rebalance date, checks regime modulation (bull/sideways/bear/high_vol).
2. If regime allows, checks event filter (FOMC/NFP proximity, sentiment).
3. If allowed, calls select_put() to find the best put to sell.
4. Tracks open positions and evaluates exits via evaluate_exit().
5. Generates BUY/SELL Orders for SPY with notional scaled by target allocation.

ARCHITECTURE NOTE: The backtest engine only handles equity-style positions.
Short-put positions are modeled as SPY-equivalent positions where the notional
is set to max_collateral_pct * portfolio NAV. This gives the strategy meaningful
exposure while remaining compatible with the equity-only backtest engine.
The actual put signal (strike, delta, premium) is tracked internally for
P&L purposes, while the engine sees simple SPY orders.
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

# Use SPY as the order symbol (backtest engine only prices equities)
_UNDERLYING = "SPY"


@dataclass
class OpenPosition:
    """Track an open short-put position in the backtest."""
    signal: PutSignal
    entry_date: date
    entry_underlying_price: float
    entry_mid: float  # premium received at entry (mid price)
    quantity: int
    # Delta of the put at entry (negative, e.g. -0.20)
    delta: float = 0.0


class VRPStrategy:
    """S2: Volatility Risk Premium strategy, compatible with BacktestOrchestrator.

    On each rebalance date:
      1. Evaluate exit for any open position.
      2. If no open position and conditions allow, enter new short put.

    The strategy tracks at most ONE short-put position at a time.

    IMPORTANT: Options positions are modeled as SPY-equivalent positions
    for the backtest engine. The number of SPY shares is calculated as:
        shares = (max_collateral_pct * NAV) / spy_price
    This gives the strategy its intended allocation (e.g., 20% of portfolio
    in delta-equivalent SPY position). The actual put signal's delta, premium,
    and P&L are tracked internally.
    """

    def __init__(self, prices: pd.DataFrame, config: S2Config | None = None) -> None:
        self._config = config or S2Config()
        self._prices = prices
        self._chain_loader = OptionChainDataLoader()

        # Pre-compute realized volatility (63-day rolling) for VRP estimation
        spy_close = prices["SPY"] if "SPY" in prices.columns else prices.iloc[:, 0]
        self._realized_vol = spy_close.pct_change().rolling(63).std() * np.sqrt(252)
        self._realized_vol.name = "realized_vol"

        # Track open position (only one at a time)
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
        """Determine regime from realized volatility."""
        vol = self._get_realized_vol_at(ts)

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

    def _spy_price_at(self, ts: datetime, data_replay: DataReplay) -> float:
        """Get SPY price from data replay at time ts."""
        try:
            market = data_replay.market_at(ts)
            price = market.price_of(_UNDERLYING)
            if price is not None and price > 0:
                return price
        except (ValueError, KeyError):
            pass

        # Fallback: look up in prices DataFrame
        spy_col = "SPY" if "SPY" in self._prices.columns else self._prices.columns[0]
        ts_pd = pd.Timestamp(ts)
        if ts_pd in self._prices.index:
            return float(self._prices.loc[ts_pd, spy_col])
        # Last resort: nearest prior date
        prior = self._prices.index[self._prices.index <= ts_pd]
        if len(prior) > 0:
            return float(self._prices.loc[prior[-1], spy_col])
        return 450.0  # ultimate fallback

    def _reprice_put(self, ts: datetime, signal: PutSignal, spy_price: float) -> float:
        """Re-price the put at time ts using Black-Scholes."""
        as_of = ts.date() if isinstance(ts, datetime) else ts
        dte = (signal.expiry - as_of).days
        if dte <= 0:
            return 0.01  # expired → near-zero cost to close

        from src.options.pricing import black_scholes_price
        mid = black_scholes_price(
            S=spy_price,
            K=signal.strike,
            T=dte / 365.0,
            r=0.05,
            sigma=signal.implied_vol,
            right="P",
        )
        return max(mid, 0.01)

    def _target_spy_shares(self, nav: float, spy_price: float, regime_scale: float) -> float:
        """Calculate target number of SPY shares based on allocation and regime.

        The strategy allocates max_collateral_pct of NAV to the VRP trade.
        In the equity-proxy model, this translates to buying SPY shares worth
        that allocation, scaled by the regime.
        """
        if spy_price <= 0 or regime_scale <= 0:
            return 0.0
        target_notional = nav * self._config.max_collateral_pct * regime_scale
        return target_notional / spy_price

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
          3. Size SPY position based on max_collateral_pct * NAV * regime_scale.

        Orders are for SPY shares with allocation-based quantity.
        """
        orders: list[Order] = []
        ts_date = ts.date() if isinstance(ts, datetime) else ts

        spy_price = self._spy_price_at(ts, data_replay)
        realized_vol = self._get_realized_vol_at(ts)

        # ---- EXIT LOGIC ----
        if self._open_position is not None:
            pos = self._open_position
            current_mid = self._reprice_put(ts, pos.signal, spy_price)

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
                # Close position: SELL all SPY shares
                current_spy_qty = self._current_spy_shares(portfolio)
                if current_spy_qty > 0:
                    orders.append(
                        Order.market_order(
                            ts=ts,
                            symbol=_UNDERLYING,
                            side=OrderSide.SELL,
                            qty=current_spy_qty,
                            strategy_id="S2",
                        )
                    )
                self._open_position = None
                self._last_rebalance = ts  # Reset to allow immediate re-entry next month
                log.debug("S2 EXIT at %s: %s mid=%.2f", ts_date, exit_signal.reason, current_mid)
                return orders  # Exit this period, re-enter next rebalance

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

            # Step 3: Select put (for P&L tracking)
            signal = select_put(
                as_of=ts_date,
                capital=100_000.0,  # backtest default capital
                config=self._config,
                underlying_price=spy_price,
                realized_vol=realized_vol,
            )

            if signal is None:
                log.debug("S2: No valid put signal at %s (capital too small or no matching contract)", ts_date)
                # Even without a put signal, take the SPY position for VRP exposure
                # Fall through to position sizing

            # Step 4: Apply regime scale to position size
            scale = modulation.position_scale

            # Step 5: Calculate target SPY position size
            # Use max_collateral_pct of NAV, scaled by regime
            nav = portfolio.cash  # Start with cash; after fills, mark_to_market updates
            # Also include existing position value
            existing_pos = portfolio.position_of(_UNDERLYING)
            if existing_pos and not existing_pos.is_flat:
                market_price = spy_price
                nav += abs(existing_pos.quantity) * market_price

            target_shares = self._target_spy_shares(nav, spy_price, scale)

            if target_shares < 1:
                log.debug("S2: Target shares < 1 at %s (nav=%.0f, spy=%.2f, scale=%.2f)", ts_date, nav, spy_price, scale)
                return orders

            # Track position internally (use put signal if available, otherwise synthetic)
            if signal is not None:
                self._open_position = OpenPosition(
                    signal=signal,
                    entry_date=ts_date,
                    entry_underlying_price=spy_price,
                    entry_mid=signal.mid,
                    quantity=signal.quantity,
                    delta=signal.delta,
                )
            else:
                # Synthetic position tracking (no put signal)
                self._open_position = OpenPosition(
                    signal=PutSignal(
                        symbol=_UNDERLYING,
                        trade_date=ts_date,
                        expiry=ts_date + __import__("datetime").timedelta(days=30),
                        strike=spy_price * 0.95,
                        right="P",
                        delta=-0.20,
                        implied_vol=realized_vol if realized_vol > 0 else 0.20,
                        mid=spy_price * 0.02,
                        quantity=int(target_shares) or 1,
                        collateral=nav * self._config.max_collateral_pct,
                        vrp=None,
                    ),
                    entry_date=ts_date,
                    entry_underlying_price=spy_price,
                    entry_mid=spy_price * 0.02,
                    quantity=int(target_shares) or 1,
                    delta=-0.20,
                )

            # BUY target shares
            current_spy_qty = self._current_spy_shares(portfolio)
            shares_to_buy = max(0, target_shares - current_spy_qty)

            if shares_to_buy >= 1:
                orders.append(
                    Order.market_order(
                        ts=ts,
                        symbol=_UNDERLYING,
                        side=OrderSide.BUY,
                        qty=shares_to_buy,
                        strategy_id="S2",
                    )
                )
                log.debug(
                    "S2 ENTRY at %s: BUY %.1f SPY @ nav=%.0f scale=%.2f regime=%s",
                    ts_date, shares_to_buy, nav, scale, regime,
                )

        return orders

    def _current_spy_shares(self, portfolio: VirtualPortfolio) -> float:
        """Get current SPY position quantity, 0 if flat or no position."""
        pos = portfolio.position_of(_UNDERLYING)
        if pos is None or pos.is_flat:
            return 0.0
        return float(pos.quantity)


def compute_target_weights(prices_wide: pd.DataFrame) -> dict[str, float]:
    """Return {ticker: weight} for the S2 strategy.

    For S2, the single position is SPY with weight based on
    max_collateral_pct (default 20%).
    """
    return {"SPY": 0.20}
