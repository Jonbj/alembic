"""Universe management: load, filter, point-in-time queries."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class UniverseAsset:
    symbol: str
    asset_class: str
    inception_date: date

    @classmethod
    def from_dict(cls, d: dict) -> "UniverseAsset":
        return cls(
            symbol=d["symbol"],
            asset_class=d["asset_class"],
            inception_date=datetime.strptime(d["inception"], "%Y-%m-%d").date(),
        )


@dataclass(frozen=True)
class Universe:
    universe_id: str
    description: str
    assets: tuple["UniverseAsset", ...]

    def active_at(self, as_of: date) -> tuple["UniverseAsset", ...]:
        """Returns assets that existed as of given date (point-in-time correct)."""
        return tuple(a for a in self.assets if a.inception_date <= as_of)

    def symbols(self) -> tuple[str, ...]:
        return tuple(a.symbol for a in self.assets)

    def by_symbol(self, symbol: str) -> Optional["UniverseAsset"]:
        for a in self.assets:
            if a.symbol == symbol:
                return a
        return None

    def screen(
        self,
        data: dict[str, "pd.DataFrame"],
        min_history_days: int = 252,
        max_nan_fraction: float = 0.05,
    ) -> "Universe":
        """Return a new Universe keeping only assets that pass data quality thresholds.

        Assets not present in `data` or with fewer than `min_history_days` trading
        rows or NaN density above `max_nan_fraction` are excluded.
        """
        passing = []
        for asset in self.assets:
            if asset.symbol not in data:
                continue
            df = data[asset.symbol]
            if len(df) < min_history_days:
                continue
            price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
            if df[price_col].isna().mean() > max_nan_fraction:
                continue
            passing.append(asset)

        return Universe(self.universe_id, self.description, tuple(passing))


def load_universe(
    universe_id: str,
    config_path: Path = Path("config/universe.yaml"),
) -> Universe:
    with open(config_path) as f:
        config = yaml.safe_load(f)

    universe_key = f"{universe_id}_universe"
    if universe_key not in config:
        raise ValueError(f"Universe '{universe_id}' not found in {config_path}")

    universe_config = config[universe_key]
    assets = tuple(UniverseAsset.from_dict(d) for d in universe_config["tickers"])

    return Universe(
        universe_id=universe_id,
        description=universe_config["description"],
        assets=assets,
    )
