"""Data replay: serve market data point-in-time during backtest.

CRITICAL: this module enforces anti-look-ahead.
Every data access is filtered to as_of <= current_timestep.
"""
import logging
from datetime import datetime

import pandas as pd

from src.backtest.engine.types import MarketSnapshot


log = logging.getLogger(__name__)


class DataReplay:
    """Wraps a multi-asset price DataFrame and serves data point-in-time.

    Usage:
        replay = DataReplay(prices_df, volumes_df)
        for ts in replay.timesteps():
            market = replay.market_at(ts)
            history = replay.prices_until(ts)
    """

    def __init__(
        self,
        prices: pd.DataFrame,
        volumes: pd.DataFrame | None = None,
    ) -> None:
        if not isinstance(prices.index, pd.DatetimeIndex):
            raise ValueError("prices must have DatetimeIndex")

        self._prices = prices.sort_index()
        self._volumes = volumes.sort_index() if volumes is not None else None

        if self._volumes is not None:
            self._adv_20d = self._volumes.rolling(20).mean()
        else:
            self._adv_20d = pd.DataFrame(
                10_000_000.0,
                index=self._prices.index,
                columns=self._prices.columns,
            )

    def timesteps(self) -> list[datetime]:
        return list(self._prices.index)

    def first_timestep(self) -> datetime:
        return self._prices.index[0]

    def last_timestep(self) -> datetime:
        return self._prices.index[-1]

    def market_at(self, as_of: datetime) -> MarketSnapshot:
        """Returns market snapshot AT as_of (uses close of that day)."""
        if as_of not in self._prices.index:
            valid = self._prices.index[self._prices.index <= as_of]
            if len(valid) == 0:
                raise ValueError(f"No data available before {as_of}")
            as_of = valid[-1]

        row = self._prices.loc[as_of]
        prices = {sym: float(row[sym]) for sym in row.index if pd.notna(row[sym])}

        if self._volumes is not None:
            vol_row = self._volumes.loc[as_of]
            volumes = {
                sym: float(vol_row[sym]) for sym in vol_row.index if pd.notna(vol_row[sym])
            }
        else:
            volumes = {sym: 0.0 for sym in prices}

        adv_row = self._adv_20d.loc[as_of]
        adv_20d = {
            sym: float(adv_row[sym]) if pd.notna(adv_row[sym]) else 10_000_000.0
            for sym in prices
        }

        return MarketSnapshot(
            timestamp=as_of,
            prices=prices,
            volumes=volumes,
            adv_20d=adv_20d,
        )

    def prices_until(self, as_of: datetime) -> pd.DataFrame:
        """ANTI-LOOK-AHEAD: returns ONLY prices with index <= as_of."""
        return self._prices[self._prices.index <= as_of]

    def returns_until(self, as_of: datetime) -> pd.DataFrame:
        """Daily returns up to as_of."""
        prices = self.prices_until(as_of)
        return prices.pct_change().dropna()
