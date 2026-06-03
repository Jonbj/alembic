"""PortfolioVolTargeter: EWMA vol estimation and order scaling for vol targeting overlay."""
from __future__ import annotations

import math

import pandas as pd

from src.portfolio.types import CombinedOrder
from src.backtest.engine.types import OrderSide

_CLAMP_LOW = 0.5
_CLAMP_HIGH = 2.0
_ANNUALIZE = 252.0


class PortfolioVolTargeter:
    """Scale BUY order quantities so the combined portfolio hits a target annualized volatility.

    Vol is estimated via EWMA variance on the average of strategy returns, then annualized.
    The resulting scale factor is clamped to [0.5, 2.0] to avoid extreme leverage.

    Args:
        target_vol: desired annualized portfolio volatility (default 10%)
        span:       EWMA span in bars (default 60)
    """

    def __init__(self, target_vol: float = 0.10, span: int = 60) -> None:
        self.target_vol = target_vol
        self.span = span

    def estimate_vol(self, strategy_returns: dict[str, list[float]]) -> float:
        """Return EWMA-estimated annualized portfolio vol from strategy returns.

        Combines strategies by equal-weight averaging, then computes EWMA variance
        on the resulting portfolio return series.
        """
        if not strategy_returns:
            return 0.0

        # Align all return series to the minimum length
        series = list(strategy_returns.values())
        n = min(len(s) for s in series)
        if n < 2:
            return 0.0

        avg_returns = [sum(s[i] for s in series) / len(series) for i in range(n)]
        ewma_var = pd.Series(avg_returns).ewm(span=self.span).var().iloc[-1]

        if not math.isfinite(ewma_var) or ewma_var <= 0.0:
            return 0.0

        return math.sqrt(ewma_var * _ANNUALIZE)

    def compute_scale(self, estimated_vol: float) -> float:
        """Return the vol-targeting scale factor, clamped to [0.5, 2.0]."""
        if estimated_vol <= 0.0:
            return 1.0  # unknown vol → no-op (neutral), not max leverage
        raw = self.target_vol / estimated_vol
        # Clamp scale to [0.5, 2.0] to prevent extreme de-leveraging or over-leveraging.
        # Without a floor, a vol spike could scale all orders to near-zero (fully
        # exiting all positions). Without a cap, a low-vol period could push leverage
        # to 2× or more, violating broker margin requirements.
        return max(_CLAMP_LOW, min(_CLAMP_HIGH, raw))

    def scale_orders(
        self, orders: list[CombinedOrder], scale: float
    ) -> list[CombinedOrder]:
        """Apply scale to all BUY order quantities; SELL orders are unchanged."""
        result: list[CombinedOrder] = []
        for order in orders:
            if order.side == OrderSide.BUY:
                result.append(order.with_quantity(order.quantity * scale))
            else:
                result.append(order)
        return result
