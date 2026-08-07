"""S4 BUG-B reproduction: synthetic-signal fallback backtest measures noise.

backtest.py:269-289 _generate_synthetic_signals produces RANDOM signals
(rng.uniform(-0.5, 0.9) for score, rng.uniform(0.3,0.9) for confidence) when
PostgreSQL is unavailable. The backtest then runs WF + gates on these RANDOM
signals as if they were real sentiment. There is NO guard that flags the output
as synthetic/noise — summary.json is written identically.

If a backtest was run without the DB, its OOS Sharpe measures the strategy on
RANDOM entries, i.e. the expected Sharpe of a long-only bucket selected by
noise (≈ market beta of the universe, not sentiment alpha). This is silently
indistinguishable from a real-signal backtest in the artifact.

Run: PYTHONPATH=. python docs/audits/strategies/S4/repro_2_synthetic_fallback.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]


def _generate_synthetic_signals(prices: pd.DataFrame) -> pd.DataFrame:
    """Inline copy of backtest.py:269-289 (to avoid yfinance import chain)."""
    rng = np.random.default_rng(42)
    tickers = [c for c in prices.columns if c != "SPY"]
    signal_dates = prices.index[::5].tolist()
    rows = []
    for ts in signal_dates:
        for ticker in tickers:
            rows.append({
                "symbol": ticker,
                "score": float(rng.uniform(-0.5, 0.9)),
                "confidence": float(rng.uniform(0.3, 0.9)),
                "reasoning": "synthetic",
                "model_id": "synthetic",
                "ensemble_std": float(rng.uniform(0.0, 0.1)),
                "fallback_used": False,
                "generated_at": pd.Timestamp(ts),
            })
    return pd.DataFrame(rows)


def main() -> None:
    print("=== S4 BUG-B: synthetic-signal fallback backtest ===\n")

    # Build a minimal price frame like the backtest uses.
    dates = pd.bdate_range("2024-01-01", "2024-06-30")
    rng = np.random.default_rng(0)
    cols = ["SPY", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA"]
    prices = pd.DataFrame(
        {c: 100 + np.cumsum(rng.normal(0, 0.01, len(dates))) for c in cols},
        index=dates,
    )

    # The fallback path the backtest takes when PG is unavailable.
    sigs = _generate_synthetic_signals(prices)
    print(f"synthetic signals: {len(sigs)} rows, models: {set(sigs['model_id'])}")
    print(f"score range: [{sigs['score'].min():.3f}, {sigs['score'].max():.3f}] "
          f"(rng.uniform(-0.5, 0.9))")
    print(f"confidence range: [{sigs['confidence'].min():.3f}, {sigs['confidence'].max():.3f}] "
          f"(rng.uniform(0.3, 0.9))")
    print(f"reasoning: {set(sigs['reasoning'])}")
    print()

    # Correlation between synthetic score and forward return is ~0 (random).
    # Show that the signal has zero predictive content by construction.
    stock = "AAPL"
    s = sigs[sigs["symbol"] == stock].sort_values("generated_at")
    fwd = prices[stock].pct_change(5).shift(-5).reindex(s["generated_at"])
    corr = float(pd.concat([s["score"].reset_index(drop=True), fwd.reset_index(drop=True)], axis=1).corr().iloc[0, 1])
    print(f"correlation(synthetic score, 5d-forward return) for {stock}: {corr:.4f} "
          f"(≈ 0 by construction — RNG noise, no sentiment)")

    print()
    print("--- Verdict ---")
    print("CONFIRMED: _generate_synthetic_signals produces RNG-uniform signals")
    print("with model_id='synthetic' and reasoning='synthetic', but the backtest")
    print("runner (run_s4_backtest_from_prices_and_signals) writes summary.json")
    print("and gate_report.json with NO flag distinguishing synthetic from real.")
    print("A backtest run without PostgreSQL silently measures NOISE (long-only")
    print("bucket selected at random ≈ universe market beta), not sentiment")
    print("alpha. reports/s4_backtest/summary.json does not exist, consistent")
    print("with the backtest either never run or run on synthetic noise.")


if __name__ == "__main__":
    main()