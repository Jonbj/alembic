"""GDELT A/B test: GDELT+FinBERT strategy vs buy-and-hold baseline."""

import argparse
import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import numpy as np
import yfinance as yf

from src.analysis.backtest import run_ab_comparison
from src.llm.finbert import FinBERTClient
from src.connectors.gdelt import GDELTConnector

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run_ab_test(
    symbols: list[str],
    start: datetime,
    end: datetime,
    horizon: int = 1,
    threshold: float = 0.10,
    min_confidence: float = 0.3,
) -> dict[str, Any]:
    """Run the full GDELT A/B test for all symbols. Returns JSON-serializable dict."""
    symbol_results: dict[str, Any] = {}

    for symbol in symbols:
        logger.info("Processing %s ...", symbol)
        try:
            symbol_results[symbol] = await _process_symbol(
                symbol, start, end, horizon, min_confidence, threshold
            )
        except Exception as e:
            logger.error("Failed to process %s: %s", symbol, e)

    if not symbol_results:
        return {
            "run_date": datetime.now(timezone.utc).date().isoformat(),
            "period": {"start": start.date().isoformat(), "end": end.date().isoformat()},
            "config": {"horizon": horizon, "threshold": threshold, "min_confidence": min_confidence},
            "gate_passed_overall": False,
            "overall_delta_sharpe": 0.0,
            "symbols": {},
        }

    overall_delta = float(np.mean([r["delta_sharpe"] for r in symbol_results.values()]))
    return {
        "run_date": datetime.now(timezone.utc).date().isoformat(),
        "period": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "config": {"horizon": horizon, "threshold": threshold, "min_confidence": min_confidence},
        "gate_passed_overall": overall_delta >= threshold,
        "overall_delta_sharpe": round(overall_delta, 4),
        "symbols": symbol_results,
    }


async def _process_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    horizon: int,
    min_confidence: float,
    threshold: float,
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()

    # 1. Fetch GDELT articles
    connector = GDELTConnector(query=f'"{symbol}"', asset_tags=[symbol])
    articles = []
    async for item in connector.fetch_historical(start, end):
        articles.append(item)
    logger.info("  %s: %d articles fetched", symbol, len(articles))

    # 2. Score with FinBERT → list of (date, score)
    # CPU-bound operation: run in executor to avoid blocking event loop
    client = FinBERTClient()
    dated_scores = await loop.run_in_executor(
        None, client.score_articles, articles, min_confidence
    )

    # 3. Aggregate to daily mean scores
    daily: dict = defaultdict(list)
    for article_date, score in dated_scores:
        daily[article_date].append(score)
    daily_mean = {d: float(np.mean(scores)) for d, scores in daily.items()}

    # 4. Fetch prices (yfinance Ticker.history returns flat-column DataFrame)
    # I/O-bound operation: run in executor to avoid blocking event loop
    ticker = yf.Ticker(symbol)
    hist = await loop.run_in_executor(
        None,
        lambda: ticker.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,  # Deprecated in yfinance>=0.28, kept for backward compat
        )
    )
    if hist.empty:
        raise ValueError(f"No price data for {symbol}")

    closes = hist["Close"].values.astype(float)
    trading_dates = [d.date() for d in hist.index]

    # Validate sufficient data for horizon
    if len(closes) <= horizon:
        raise ValueError(f"Insufficient price data for {symbol}: need {horizon + 1} days, got {len(closes)}")

    # 5. Compute forward returns and align daily GDELT scores
    fwd_returns = []
    aligned_scores = []
    for i in range(len(closes) - horizon):
        # Skip NaN, Inf, and zero prices to avoid invalid returns
        if not np.isfinite(closes[i]) or closes[i] == 0:
            continue
        fwd_returns.append(float((closes[i + horizon] - closes[i]) / closes[i]))
        aligned_scores.append(daily_mean.get(trading_dates[i], 0.0))

    # 6. A/B comparison
    ab = run_ab_comparison(
        daily_scores=aligned_scores,
        fwd_returns=fwd_returns,
        n_articles=len(articles),
        threshold=threshold,
    )

    return {
        "sharpe_baseline": round(ab.sharpe_baseline, 4),
        "sharpe_gdelt":    round(ab.sharpe_gdelt, 4),
        "delta_sharpe":    round(ab.delta_sharpe, 4),
        "composite_ic":    round(ab.composite_ic, 4),
        "coverage_pct":    round(ab.coverage_pct, 1),
        "n_signals":       ab.n_signals,
        "n_trading_days":  ab.n_trading_days,
        "gate_passed":     ab.gate_passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GDELT A/B test: GDELT+FinBERT vs buy-and-hold"
    )
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--horizon", type=int, default=1,
                        help="Forward return horizon in trading days (default: 1)")
    parser.add_argument("--threshold", type=float, default=0.1,
                        help="Min delta_Sharpe for PASS (default: 0.1)")
    parser.add_argument("--min-confidence", type=float, default=0.3, dest="min_confidence",
                        help="Min FinBERT confidence to include article (default: 0.3)")
    parser.add_argument("--output", default=None, help="JSON output file (default: stdout)")
    args = parser.parse_args()

    # Validate symbols format
    import re
    for symbol in args.symbols:
        if not re.match(r'^[A-Z0-9.-]+$', symbol):
            raise ValueError(f"Invalid symbol format: {symbol}. Must be alphanumeric with dots/dashes.")

    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Validate inputs
    if start >= end:
        raise ValueError(f"start ({args.start}) must be before end ({args.end})")
    if args.horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {args.horizon}")
    if args.threshold < 0:
        raise ValueError(f"threshold must be >= 0, got {args.threshold}")
    if not 0 <= args.min_confidence <= 1:
        raise ValueError(f"min_confidence must be in [0, 1], got {args.min_confidence}")

    result = asyncio.run(run_ab_test(
        symbols=args.symbols,
        start=start,
        end=end,
        horizon=args.horizon,
        threshold=args.threshold,
        min_confidence=args.min_confidence,
    ))

    # Validate output path to prevent path traversal
    if args.output:
        from pathlib import Path
        output_path = Path(args.output).resolve()
        cwd = Path.cwd().resolve()
        if not str(output_path).startswith(str(cwd)):
            raise ValueError("Output path must be inside working directory")
        with open(output_path, "w") as f:
            f.write(json.dumps(result, indent=2, default=float))
        logger.info("Results written to %s", args.output)
    else:
        print(json.dumps(result, indent=2, default=float))


if __name__ == "__main__":
    main()
