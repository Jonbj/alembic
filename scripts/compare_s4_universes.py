#!/usr/bin/env python3
"""S4 universe comparison: watchlist-only vs watchlist + promoted symbols.

Usage:
    python scripts/compare_s4_universes.py \\
      --promoted CRDO ALAB \\
      --run-id alpaca-smallmid-2506 \\
      --days 90

Loads signals from backtest_signals for the given run_id.
Runs run_s4_backtest_from_prices_and_signals() twice:
  - Universe A: current watchlist only
  - Universe B: watchlist + promoted symbols
Prints comparison and writes reports/s4_universe_comparison.json.

NOTE: With only 90 days of signals, uses in_sample_days=45 / out_of_sample_days=45.
Results are directional, not statistically conclusive.
"""

import argparse
import json
import logging
from datetime import timedelta
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _fetch_prices(symbols: list[str], days: int) -> pd.DataFrame:
    """Fetch daily close prices from Alpaca for the last N days."""
    from datetime import datetime, timezone
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from src.config import config

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days * 2)  # extra buffer for weekends/holidays

    client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed=DataFeed.IEX,
        adjustment=Adjustment.ALL,
    )
    raw = client.get_stock_bars(request).df
    if raw.empty:
        return pd.DataFrame()
    raw = raw.reset_index()
    prices = raw.pivot(index="timestamp", columns="symbol", values="close")
    if len(prices) > days:
        prices = prices.iloc[-days:]
    return prices


def _load_signals_from_db(run_id_prefix: str) -> pd.DataFrame:
    """Load signals from backtest_signals for run_ids matching the prefix."""
    import psycopg2
    from src.config import config

    conn = psycopg2.connect(config.DATABASE_URL.replace("+asyncpg", ""))
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, score, confidence, 'unknown' AS reasoning,
                       model_id, 0.0 AS ensemble_std, fallback_used, generated_at
                FROM backtest_signals
                WHERE run_id LIKE %s
                  AND score IS NOT NULL
                ORDER BY generated_at
            """, (run_id_prefix + "%",))
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "symbol", "score", "confidence", "reasoning",
        "model_id", "ensemble_std", "fallback_used", "generated_at",
    ])
    df["generated_at"] = pd.to_datetime(df["generated_at"])
    if df["generated_at"].dt.tz is not None:
        df["generated_at"] = df["generated_at"].dt.tz_localize(None)
    return df


def _run_comparison(
    prices_a: pd.DataFrame,
    prices_b: pd.DataFrame,
    signals_a: pd.DataFrame,
    signals_b: pd.DataFrame,
    label_a: str,
    label_b: str,
) -> dict:
    """Run backtest for both universes and return comparison dict."""
    from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals
    from src.backtest.walkforward.runner import WalkForwardConfig

    # Short window config for 90-day signal window
    wf_cfg = WalkForwardConfig(in_sample_days=45, out_of_sample_days=45)

    log.info("Running backtest for %s (%d symbols, %d signals)...",
             label_a, len(prices_a.columns), len(signals_a))
    result_a = run_s4_backtest_from_prices_and_signals(
        prices=prices_a,
        signals_df=signals_a,
        output_dir=Path(f"reports/s4_{label_a.lower().replace(' ', '_').replace('(', '').replace(')', '')}"),
        wf_config=wf_cfg,
        run_robustness=False,
    )

    log.info("Running backtest for %s (%d symbols, %d signals)...",
             label_b, len(prices_b.columns), len(signals_b))
    result_b = run_s4_backtest_from_prices_and_signals(
        prices=prices_b,
        signals_df=signals_b,
        output_dir=Path(f"reports/s4_{label_b.lower().replace(' ', '_').replace('(', '').replace(')', '')}"),
        wf_config=wf_cfg,
        run_robustness=False,
    )

    return {"a": result_a, "b": result_b, "label_a": label_a, "label_b": label_b}


def _print_comparison(comp: dict, promoted: list[str]) -> None:
    """Print side-by-side comparison and recommendation."""
    a, b = comp["a"], comp["b"]
    la, lb = comp["label_a"], comp["label_b"]

    sharpe_a = a.get("oos_sharpe", 0.0) if isinstance(a, dict) else getattr(a, "oos_sharpe", 0.0)
    sharpe_b = b.get("oos_sharpe", 0.0) if isinstance(b, dict) else getattr(b, "oos_sharpe", 0.0)

    print("\n" + "=" * 60)
    print("S4 UNIVERSE COMPARISON")
    print("=" * 60)
    print(f"{'Metric':<25} {la:>15} {lb:>15}")
    print("-" * 60)
    print(f"{'OOS Sharpe':<25} {sharpe_a:>15.4f} {sharpe_b:>15.4f}")
    print("-" * 60)

    print("\nNOTE: 90-day signal window -- results are directional only.")
    print("    in_sample_days=45, out_of_sample_days=45 (not production config)\n")

    sharpe_improved = sharpe_b > sharpe_a
    label = "YES" if sharpe_improved else "NO"

    print(f"OOS Sharpe B > A: {label}  ({sharpe_b:.4f} vs {sharpe_a:.4f})")

    if sharpe_improved:
        print(f"\nRECOMMENDATION: add {', '.join(promoted)} to watchlist")
        print("  IC_24h >= 0.15         (verified in IC backtest)")
        print("  ICIR_24h >= 2.0        (verified in IC backtest)")
        print(f"  OOS Sharpe B > A       ({sharpe_b:.4f} vs {sharpe_a:.4f})")
        print("\nACTION REQUIRED: manually add symbols to config/trading.yaml")
    else:
        print("\nRECOMMENDATION: do NOT add symbols -- Sharpe did not improve.")
        print(f"  OOS Sharpe B ({sharpe_b:.4f}) <= Sharpe A ({sharpe_a:.4f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare S4 performance with/without promoted symbols")
    parser.add_argument("--promoted", nargs="+", required=True,
                        help="Promoted symbols from IC backtest gate (e.g. CRDO ALAB)")
    parser.add_argument("--run-id", required=True,
                        help="Run ID prefix used in backtest_smallmid_ic.py (e.g. alpaca-smallmid-2506)")
    parser.add_argument("--days", type=int, default=90,
                        help="Price history window in days (must match IC backtest, default 90)")
    args = parser.parse_args()

    from src.config import config

    watchlist = list(config.WATCHLIST_SYMBOLS or [])
    promoted = args.promoted
    expanded = list(dict.fromkeys(watchlist + promoted))  # dedup, preserve order

    log.info("Fetching prices for Universe A (%d symbols)...", len(watchlist))
    prices_a = _fetch_prices(watchlist, args.days)

    log.info("Fetching prices for Universe B (%d symbols)...", len(expanded))
    prices_b = _fetch_prices(expanded, args.days)

    if prices_a.empty or prices_b.empty:
        log.error("No price data returned -- check Alpaca credentials and symbols")
        raise SystemExit(1)

    log.info("Loading signals from DB (run_id prefix: %s)...", args.run_id)
    all_signals = _load_signals_from_db(args.run_id)
    if all_signals.empty:
        log.error("No signals found for run_id prefix '%s' -- run IC backtest first", args.run_id)
        raise SystemExit(1)

    signals_a = all_signals[all_signals["symbol"].isin(prices_a.columns)]
    signals_b = all_signals[all_signals["symbol"].isin(prices_b.columns)]

    log.info("Universe A: %d symbols, %d signals", len(prices_a.columns), len(signals_a))
    log.info("Universe B: %d symbols, %d signals", len(prices_b.columns), len(signals_b))

    comp = _run_comparison(
        prices_a=prices_a, prices_b=prices_b,
        signals_a=signals_a, signals_b=signals_b,
        label_a="Universe A (watchlist)",
        label_b="Universe B (watchlist+promoted)",
    )

    _print_comparison(comp, promoted)

    Path("reports").mkdir(exist_ok=True)
    out = {
        "promoted_symbols": promoted,
        "run_id": args.run_id,
        "universe_a": {"symbols": len(prices_a.columns), "result": comp["a"] if isinstance(comp["a"], dict) else vars(comp["a"])},
        "universe_b": {"symbols": len(prices_b.columns), "result": comp["b"] if isinstance(comp["b"], dict) else vars(comp["b"])},
    }
    out_path = Path("reports/s4_universe_comparison.json")
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nFull comparison saved to {out_path}")


if __name__ == "__main__":
    main()
