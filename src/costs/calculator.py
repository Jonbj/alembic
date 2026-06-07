"""Shared trade cost calculator — spread tiers, market impact, stop-loss per tier.

Consumed by pg_store (live net P&L), execution worker (stop-loss), and
backtest report builder (IC net-of-costs). Reads config/cost_model.yaml.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class CostBreakdown:
    spread_cost_bps: float       # full roundtrip half-spread × 2
    impact_cost_bps: float       # Almgren-Chriss √(order_usd / adv_usd)
    regulatory_cost_usd: float   # SEC Section 31 + FINRA TAF (sells only)
    total_cost_bps: float        # spread_cost_bps + impact_cost_bps
    total_cost_usd: float        # (total_cost_bps / 10_000 × notional) + regulatory


_DEFAULT_ADV_USD = 20_000_000_000.0  # fallback ADV (USD) when live data unavailable — ~20B/day (conservative liquid-market baseline)


class TradeCostCalculator:
    """Compute trade costs and tier-based stop-loss percentages from cost_model.yaml."""

    def __init__(self, config_path: Path = Path("config/cost_model.yaml")) -> None:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        equity = cfg["equity"]
        tiers = equity["spread_tiers"]

        # Build symbol → tier config lookup
        self._symbol_tier: dict[str, dict] = {}
        self._default_tier: dict = {}
        for tier_data in tiers.values():
            if tier_data.get("default"):
                self._default_tier = tier_data
            for sym in tier_data.get("symbols", []):
                self._symbol_tier[sym.upper()] = tier_data

        self._impact_k = float(equity.get("impact_k", 10.0))
        self._commission_per_share = float(equity.get("commission_per_share", 0.0))
        self._sec_fee = float(equity.get("sec_fee_per_share_sale", 0.0000229))
        self._finra_taf = float(equity.get("finra_taf_per_share_sale", 0.000145))

    def _tier(self, symbol: str) -> dict:
        return self._symbol_tier.get(symbol.upper(), self._default_tier)

    def stop_loss_pct(self, symbol: str) -> float:
        """Return stop-loss percentage for symbol based on liquidity tier."""
        return float(self._tier(symbol).get("stop_loss_pct", 0.02))

    def compute(
        self,
        symbol: str,
        notional: float,
        qty: float,
        fill_price: float,
        side: str,
        adv_usd: float | None = None,
    ) -> CostBreakdown:
        """Compute full cost breakdown for a trade."""
        tier = self._tier(symbol)
        spread_bps = float(tier.get("spread_bps", 20.0))

        if adv_usd is None or adv_usd <= 0:
            adv_usd = _DEFAULT_ADV_USD

        impact_bps = self._impact_k * math.sqrt(notional / adv_usd) * 100 if adv_usd > 0 else 0.0

        total_cost_bps = spread_bps + impact_bps

        regulatory = 0.0
        if side.upper() == "SELL":
            regulatory = (
                self._sec_fee * qty * fill_price
                + self._finra_taf * qty
                + self._commission_per_share * qty
            )

        total_cost_usd = (total_cost_bps / 10_000) * notional + regulatory

        return CostBreakdown(
            spread_cost_bps=spread_bps,
            impact_cost_bps=impact_bps,
            regulatory_cost_usd=regulatory,
            total_cost_bps=total_cost_bps,
            total_cost_usd=total_cost_usd,
        )
