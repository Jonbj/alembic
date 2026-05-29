"""Bid-ask spread tier lookup by symbol."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class SpreadTier:
    name: str
    spread_bps: float
    is_default: bool = False


class SpreadTierLookup:
    """Maps a symbol to its spread tier."""

    def __init__(self, tiers: list[SpreadTier], symbol_to_tier: dict[str, str]) -> None:
        self._tiers: dict[str, SpreadTier] = {t.name: t for t in tiers}
        self._symbol_to_tier = symbol_to_tier
        defaults = [t for t in tiers if t.is_default]
        self._default = defaults[0] if defaults else SpreadTier("tier_d", 20.0, True)

    def get_spread_bps(self, symbol: str) -> float:
        tier_name = self._symbol_to_tier.get(symbol)
        if tier_name is None:
            return self._default.spread_bps
        tier = self._tiers.get(tier_name)
        return tier.spread_bps if tier else self._default.spread_bps

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
