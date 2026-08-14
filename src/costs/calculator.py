"""Shared trade cost calculator — spread tiers, market impact, stop-loss per tier.

Consumed by pg_store (live net P&L), execution worker (stop-loss), and
backtest report builder (IC net-of-costs). Reads config/cost_model.yaml.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
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


# Conservative ADV fallback (~$20B/day, realistic for large liquid markets).
# At this scale, impact on typical position sizes ($10k-$50k) is 1-2 bps — small
# but non-zero. For IC normalization (notional=1.0) impact is effectively zero,
# which is the intended behaviour for cost-adjusted IC computation.
# Callers with real ADV data should always pass adv_usd explicitly.
_DEFAULT_ADV_USD = 20_000_000_000.0


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

    def uncovered_symbols(self, symbols: Iterable[str]) -> list[str]:
        """Return the symbols that would fall back to the default tier.

        The default tier is meant for genuinely unknown symbols. A symbol we
        deliberately put in the watchlist reaching it is a configuration gap, not a
        fallback: the modelled cost is subtracted from ``trades.net_pnl``, so pricing
        a large-cap as "small-cap, illiquid" (20 bps) distorts the economic series the
        observation period judges the strategies on (#245).

        A symbol listed explicitly under the default tier is *covered* — it has been
        audited and found illiquid. Only symbols listed nowhere are reported.

        Args:
            symbols: Ticker symbols to check. Case-insensitive, order preserved.

        Returns:
            The uncovered symbols, in input order. Empty means full coverage.
        """
        return [s for s in symbols if s.upper() not in self._symbol_tier]

    def stop_loss_pct(self, symbol: str) -> float:
        """Return stop-loss percentage for symbol based on liquidity tier."""
        return float(self._tier(symbol).get("stop_loss_pct", 0.05))

    def compute(
        self,
        symbol: str,
        notional: float,
        qty: float,
        fill_price: float,
        side: str,
        adv_usd: float | None = None,
    ) -> CostBreakdown:
        """Compute full cost breakdown for a trade.

        Args:
            symbol:     Ticker symbol (case-insensitive tier lookup).
            notional:   Trade notional in USD (qty × price).
            qty:        Number of shares.
            fill_price: Execution price per share.
            side:       "BUY" or "SELL". Regulatory fees only apply to SELL.
            adv_usd:    20-day average daily volume in USD. Pass None to use
                        the conservative default (_DEFAULT_ADV_USD ≈ 20B),
                        which makes impact negligible — correct for IC
                        normalization (notional=1.0) but underestimates
                        impact for real trades. Pass actual ADV when available.
        """
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
