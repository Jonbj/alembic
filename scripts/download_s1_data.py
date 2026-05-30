#!/usr/bin/env python3
"""Download and validate the full S1 universe data.

Usage:
    uv run scripts/download_s1_data.py [--start YYYY-MM-DD] [--force-refresh]

Downloads 30+ years of daily OHLCV for all 15 S1 ETFs, caches as parquet,
then validates each series for gaps, spikes, and NaN density.
"""
import argparse
import logging
import sys
from datetime import date
from pathlib import Path

# Make project root importable when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest.data.cache import ParquetCache
from src.backtest.data.loader import DataLoader
from src.backtest.data.universe import load_universe
from src.backtest.data.validator import validate_universe_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_START = date(1993, 1, 1)  # SPY's inception; earlier ETFs will return shorter history
CONFIG_PATH = Path("config/universe.yaml")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download S1 universe data")
    p.add_argument("--start", type=date.fromisoformat, default=DEFAULT_START)
    p.add_argument("--end", type=date.fromisoformat, default=None)
    p.add_argument("--force-refresh", action="store_true")
    p.add_argument("--cache-dir", type=Path, default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()

    universe = load_universe("s1", config_path=CONFIG_PATH)
    log.info("S1 universe: %d assets", len(universe.assets))

    cache = ParquetCache(cache_dir=args.cache_dir) if args.cache_dir else ParquetCache()
    loader = DataLoader(cache=cache)

    log.info("Downloading data from %s to %s...", args.start, args.end or "today")
    data = {}
    for asset in universe.assets:
        try:
            df = loader.download(
                asset.symbol,
                start=max(args.start, asset.inception_date),
                end=args.end,
                force_refresh=args.force_refresh,
            )
            data[asset.symbol] = df
            log.info(
                "  %-6s  %s → %s  (%d rows)",
                asset.symbol,
                df.index.min().date(),
                df.index.max().date(),
                len(df),
            )
        except Exception as exc:
            log.error("  %-6s  FAILED: %s", asset.symbol, exc)

    log.info("\nValidating %d series...", len(data))
    results = validate_universe_data(data)

    valid = sum(1 for r in results.values() if r.is_valid)
    invalid = len(results) - valid

    print(f"\n{'Symbol':<8} {'Days':>6} {'NaN%':>6} {'Gaps':>5} {'Spikes':>7} {'Valid':>6}")
    print("-" * 46)
    for sym, r in sorted(results.items()):
        print(
            f"{sym:<8} {r.trading_days:>6} {r.nan_fraction*100:>5.1f}%"
            f" {len(r.gaps):>5} {len(r.spikes):>7} {'YES' if r.is_valid else 'NO ':>6}"
        )

    print(f"\nSummary: {valid} valid / {len(results)} total  ({invalid} issues)")

    if invalid > 0:
        log.warning("%d assets have data quality issues", invalid)
        for sym, r in results.items():
            if not r.is_valid:
                if not r.has_adj_close:
                    log.warning("  %s: missing Adj Close", sym)
                for g in r.gaps:
                    log.warning("  %s: gap %s → %s", sym, g[0], g[1])
                for s in r.spikes:
                    log.warning("  %s: spike on %s", sym, s)

    screened = universe.screen(data, min_history_days=252, max_nan_fraction=0.02)
    dropped = set(universe.symbols()) - set(screened.symbols())
    if dropped:
        log.warning("Screening removed: %s", ", ".join(sorted(dropped)))
    log.info("Screened universe: %d assets pass quality gates", len(screened.assets))

    return 0 if invalid == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
