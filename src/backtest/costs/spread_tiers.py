"""Bid-ask spread tier lookup by symbol."""
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SpreadTier:
    name: str
    spread_bps: float
    is_default: bool = False


class SpreadTierLookup:
    """Maps a symbol to its spread tier.

    Symbol matching is case-insensitive, the same semantics as the live
    ``TradeCostCalculator``: backtest and live accounting must resolve a ticker to the
    same tier regardless of how the caller cased it (#245). A symbol listed explicitly
    under *any* tier — including the default — is *covered*; only symbols listed nowhere
    fall back to the default.
    """

    def __init__(self, tiers: list[SpreadTier], symbol_to_tier: dict[str, str]) -> None:
        self._tiers: dict[str, SpreadTier] = {t.name: t for t in tiers}
        # Keys normalised to uppercase so lookup is case-insensitive.
        self._symbol_to_tier = {sym.upper(): tier_name for sym, tier_name in symbol_to_tier.items()}
        defaults = [t for t in tiers if t.is_default]
        self._default = defaults[0] if defaults else SpreadTier("tier_d", 20.0, True)

    def get_spread_bps(self, symbol: str) -> float:
        tier_name = self._symbol_to_tier.get(symbol.upper())
        if tier_name is None:
            return self._default.spread_bps
        tier = self._tiers.get(tier_name)
        return tier.spread_bps if tier else self._default.spread_bps

    def uncovered_symbols(self, symbols: Iterable[str]) -> list[str]:
        """Return the symbols that would fall back to the default tier.

        Mirrors ``TradeCostCalculator.uncovered_symbols`` so the same coverage contract
        runs on the backtest surface (#245). A symbol listed explicitly under the
        default tier is *covered* — it has been audited and found illiquid. Only symbols
        listed nowhere are reported. Case-insensitive, order preserved.
        """
        return [s for s in symbols if s.upper() not in self._symbol_to_tier]

    @classmethod
    def from_config(
        cls, config_path: Path = Path("config/cost_model.yaml")
    ) -> "SpreadTierLookup":
        with open(config_path) as f:
            config = yaml.safe_load(f)

        equity_cfg = config["equity"]
        tiers: list[SpreadTier] = []
        symbol_to_tier: dict[str, str] = {}

        for tier_name, tier_cfg in equity_cfg["spread_tiers"].items():
            is_default = tier_cfg.get("default", False)
            tier = SpreadTier(
                name=tier_name,
                spread_bps=float(tier_cfg["spread_bps"]),
                is_default=is_default,
            )
            tiers.append(tier)
            for sym in tier_cfg.get("symbols", []):
                symbol_to_tier[sym] = tier_name

        return cls(tiers=tiers, symbol_to_tier=symbol_to_tier)
