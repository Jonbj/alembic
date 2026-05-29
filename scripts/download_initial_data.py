#!/usr/bin/env python3
"""Pre-download data for all tickers in the S1 universe.

Run once after setup to warm the cache.

Usage:
    uv run python scripts/download_initial_data.py [--start YYYY-MM-DD] [--universe s1]
"""
import argparse
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest.data.loader import DataLoader
from src.backtest.data.universe import load_universe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="1995-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--universe", default="s1", help="Universe id")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)

    universe = load_universe(args.universe)
    loader = DataLoader()

    print(f"Downloading {len(universe.assets)} tickers from {start_date}...")

    success = 0
    failed = 0
    for asset in universe.assets:
        try:
            actual_start = max(start_date, asset.inception_date)
            df = loader.download(asset.symbol, start=actual_start)
            print(
                f"  OK {asset.symbol}: {len(df)} rows "
                f"({df.index.min().date()} -> {df.index.max().date()})"
            )
            success += 1
        except Exception as e:
            print(f"  FAIL {asset.symbol}: {e}")
            failed += 1

    print(f"\nDone: {success} successful, {failed} failed")


if __name__ == "__main__":
    main()
