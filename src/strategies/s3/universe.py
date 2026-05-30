"""S3 universe: dynamic point-in-time liquidity filter for cross-sectional equity."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiquidityFilter:
    min_adv_usd: float = 10_000_000
    min_price_usd: float = 5.0
    min_history_days: int = 252
    adv_window_days: int = 63


@dataclass(frozen=True)
class S3Universe:
    """Point-in-time filtered universe backed by OHLCV price/volume data.

    close and volume are wide DataFrames: index=date, columns=tickers.
    active_at() applies the liquidity filter at the requested date without
    look-ahead bias.
    """

    tickers: tuple[str, ...]
    close: pd.DataFrame
    volume: pd.DataFrame
    liq_filter: LiquidityFilter

    def active_at(self, as_of: date) -> tuple[str, ...]:
        """Return tickers passing the liquidity filter as of `as_of`.

        Point-in-time rules:
        - Only rows up to (and including) as_of are visible.
        - Ticker must have at least min_history_days of non-NaN close prices.
        - ADV (close * volume) over trailing adv_window_days must meet threshold.
        - Close price on as_of must meet min_price_usd.
        """
        as_of_ts = pd.Timestamp(as_of)
        close_pit = self.close.loc[self.close.index <= as_of_ts]
        volume_pit = self.volume.loc[self.volume.index <= as_of_ts]

        if close_pit.empty:
            return ()

        passing: list[str] = []
        f = self.liq_filter

        for ticker in self.tickers:
            if ticker not in close_pit.columns:
                continue

            prices = close_pit[ticker].dropna()
            if len(prices) < f.min_history_days:
                continue

            last_price = prices.iloc[-1]
            if last_price < f.min_price_usd:
                continue

            if ticker not in volume_pit.columns:
                continue
            vols = volume_pit[ticker].dropna()

            # Align trailing window to shared price/volume dates
            window_prices = prices.iloc[-f.adv_window_days:]
            window_vols = vols.reindex(window_prices.index).fillna(0)
            adv = (window_prices * window_vols).mean()

            if adv < f.min_adv_usd:
                continue

            passing.append(ticker)

        return tuple(passing)

    def symbols(self) -> tuple[str, ...]:
        return self.tickers


def _load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_s3_universe(
    config_path: Path = Path("config/universe.yaml"),
    csv_path: Optional[Path] = None,
    close: Optional[pd.DataFrame] = None,
    volume: Optional[pd.DataFrame] = None,
    liq_filter: Optional[LiquidityFilter] = None,
) -> S3Universe:
    """Load S3 universe from config, CSV, and optional pre-built price data.

    If `close`/`volume` are not provided the caller is responsible for
    downloading them via DataLoader before calling active_at().  In tests,
    pass synthetic DataFrames directly.

    Args:
        config_path: path to universe.yaml containing s3_universe section
        csv_path: override for the CSV ticker list (defaults to config source)
        close: wide DataFrame of adjusted close prices (index=date, cols=tickers)
        volume: wide DataFrame of daily volume (index=date, cols=tickers)
        liq_filter: override filter params (defaults to values from config)

    Returns:
        S3Universe ready for point-in-time queries.
    """
    cfg = _load_config(config_path)
    s3_cfg = cfg.get("s3_universe", {})
    filters_cfg = s3_cfg.get("filters", {})

    if liq_filter is None:
        liq_filter = LiquidityFilter(
            min_adv_usd=float(filters_cfg.get("min_adv_usd", 10_000_000)),
            min_price_usd=float(filters_cfg.get("min_price_usd", 5.0)),
        )

    if csv_path is None:
        source = s3_cfg.get("source", "data/sp500_tickers.csv")
        csv_path = Path(source) if not Path(source).is_absolute() else Path(source)
        if not csv_path.is_absolute():
            csv_path = config_path.parent.parent / csv_path

    ticker_df = pd.read_csv(csv_path)
    tickers = tuple(ticker_df["ticker"].dropna().str.strip().tolist())

    if close is None:
        close = pd.DataFrame(columns=list(tickers))
    if volume is None:
        volume = pd.DataFrame(columns=list(tickers))

    return S3Universe(
        tickers=tickers,
        close=close,
        volume=volume,
        liq_filter=liq_filter,
    )


def load_s3_universe_with_data(
    loader,
    start: date,
    end: Optional[date] = None,
    config_path: Path = Path("config/universe.yaml"),
    csv_path: Optional[Path] = None,
    liq_filter: Optional[LiquidityFilter] = None,
) -> S3Universe:
    """Load S3 universe and download price/volume data via DataLoader.

    Args:
        loader: DataLoader instance (src.backtest.data.loader.DataLoader)
        start: earliest date to fetch data from
        end: latest date (default: today)
        config_path: path to universe.yaml
        csv_path: override for ticker CSV
        liq_filter: override liquidity filter thresholds

    Returns:
        S3Universe with price/volume data loaded and ready for active_at().
    """
    base = load_s3_universe(
        config_path=config_path,
        csv_path=csv_path,
        liq_filter=liq_filter,
    )

    end = end or date.today()
    close_frames: dict[str, pd.Series] = {}
    volume_frames: dict[str, pd.Series] = {}

    for ticker in base.tickers:
        try:
            df = loader.download(ticker, start=start, end=end)
            price_col = "Adj Close" if "Adj Close" in df.columns else "Close"
            close_frames[ticker] = df[price_col]
            volume_frames[ticker] = df["Volume"]
        except Exception as exc:
            log.warning("Skipping %s: %s", ticker, exc)

    close_df = pd.DataFrame(close_frames)
    volume_df = pd.DataFrame(volume_frames)

    return S3Universe(
        tickers=base.tickers,
        close=close_df,
        volume=volume_df,
        liq_filter=base.liq_filter,
    )
