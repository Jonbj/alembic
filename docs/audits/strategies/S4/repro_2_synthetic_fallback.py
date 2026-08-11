"""S4 BUG-B regression: the synthetic fallback must be explicit.

The production loader must fail when PostgreSQL is unavailable or returns no
rows. RNG signals remain available only with allow_synthetic=True and carry
their provenance for the report writer.

Run: PYTHONPATH=. python docs/audits/strategies/S4/repro_2_synthetic_fallback.py
"""
from datetime import date
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from src.strategies.s4.backtest import _load_sentiment_signals

    print("=== S4 BUG-B regression: explicit synthetic fallback ===\n")

    # Build a minimal price frame like the backtest uses.
    dates = pd.bdate_range("2024-01-01", "2024-06-30")
    rng = np.random.default_rng(0)
    cols = ["SPY", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA"]
    prices = pd.DataFrame(
        {c: 100 + np.cumsum(rng.normal(0, 0.01, len(dates))) for c in cols},
        index=dates,
    )

    start, end = date(2024, 1, 1), date(2024, 6, 30)
    with patch(
        "src.store.pg_store.PostgreSQLStore",
        side_effect=ConnectionError("database offline"),
    ):
        try:
            _load_sentiment_signals(prices, start, end)
        except RuntimeError as exc:
            print(f"DB unavailable: correctly rejected ({exc})")
        else:
            raise AssertionError("DB failure still produced silent synthetic signals")

    store_type = MagicMock()
    store_type.return_value.__enter__.return_value.fetch_signals_for_backtest_batch.return_value = []
    with patch("src.store.pg_store.PostgreSQLStore", store_type):
        try:
            _load_sentiment_signals(prices, start, end)
        except RuntimeError as exc:
            print(f"empty DB window: correctly rejected ({exc})")
        else:
            raise AssertionError("empty DB window still produced silent synthetic signals")

    with patch("src.store.pg_store.PostgreSQLStore", store_type):
        signals = _load_sentiment_signals(
            prices,
            start,
            end,
            allow_synthetic=True,
        )
    assert signals.attrs.get("synthetic") is True
    assert set(signals["model_id"]) == {"synthetic"}
    print(f"explicit opt-in: generated {len(signals)} rows with synthetic=true")

    print()
    print("--- Verdict ---")
    print("NOT REPRODUCED: both silent fallback paths fail closed; synthetic data")
    print("requires allow_synthetic=True and carries explicit provenance.")


if __name__ == "__main__":
    main()
