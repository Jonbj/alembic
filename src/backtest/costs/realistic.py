"""Realistic cost model: tier-based spread + square-root market impact + regulatory fees."""
import uuid
from pathlib import Path

import yaml

from src.backtest.costs.impact_model import SquareRootImpactModel
from src.backtest.costs.spread_tiers import SpreadTierLookup
from src.backtest.engine.types import Fill, MarketSnapshot, Order, OrderSide


class RealisticCostModel:
    """Full-cost equity order simulation.

    Components:
    1. Tier-based half-spread (config/cost_model.yaml)
    2. Square-root market impact (Almgren-Chriss, k=10)
    3. Broker commission per share
    4. Regulatory fees on sells: SEC Section 31 + FINRA TAF
    """

    def __init__(
        self,
        config_path: Path = Path("config/cost_model.yaml"),
        spread_lookup: SpreadTierLookup | None = None,
        impact_model: SquareRootImpactModel | None = None,
    ) -> None:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        equity = cfg["equity"]
        self._spread = spread_lookup or SpreadTierLookup.from_config(config_path)
        self._impact = impact_model or SquareRootImpactModel(
            k=float(equity.get("impact_k", 10.0))
        )
        self._commission_per_share = float(equity.get("commission_per_share", 0.0))
        self._sec_fee = float(equity.get("sec_fee_per_share_sale", 0.0000229))
        self._finra_taf = float(equity.get("finra_taf_per_share_sale", 0.000145))

    def simulate_fill(self, order: Order, market: MarketSnapshot) -> Fill:
        mid_price = market.price_of(order.symbol)
        if mid_price is None:
            raise ValueError(f"No price for {order.symbol} at {market.timestamp}")

        # Tier-based half-spread
        spread_bps = self._spread.get_spread_bps(order.symbol)
        half_spread_bps = spread_bps / 2

        # Square-root market impact (adv_20d in shares; convert to USD for participation ratio)
        order_usd = order.quantity * mid_price
        adv_shares = market.adv_20d.get(order.symbol, 10_000_000.0)
        adv_usd = adv_shares * mid_price
        impact_bps = self._impact.impact_bps(order_usd, adv_usd)

        total_slippage_bps = half_spread_bps + impact_bps

        sign = 1 if order.side == OrderSide.BUY else -1
        fill_price = mid_price * (1 + sign * total_slippage_bps / 10_000)

        # Per-share broker commission
        commission = self._commission_per_share * order.quantity

        # Regulatory fees on sells only: SEC Section 31 + FINRA TAF
        if order.side == OrderSide.SELL:
            commission += self._sec_fee * order.quantity * fill_price
            commission += self._finra_taf * order.quantity

        return Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            timestamp=order.timestamp,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage_bps=total_slippage_bps,
            strategy_id=order.strategy_id,
        )
