"""run_forward_return_worker: multi-horizon computation (1d/3d/5d trading days).

Both tests patch src.workers.performance.config with dummy ALPACA_API_KEY/
SECRET_KEY/DATABASE_URL (pattern from tests/workers/test_counterfactual.py):
run_forward_return_worker short-circuits with skipped_no_data=0/updated=0
when config.ALPACA_API_KEY is falsy, which it is in a bare test process (no
.env loading) — without this the test never reaches the code under test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from src.workers.performance import run_forward_return_worker


def _bars(dates_closes: list[tuple[str, float]]) -> MagicMock:
    idx = pd.to_datetime([d for d, _ in dates_closes], utc=True)
    df = pd.DataFrame({"close": [c for _, c in dates_closes]}, index=idx)
    resp = MagicMock()
    resp.df = df
    return resp


def test_worker_writes_three_horizons():
    # Signal on Mon 2026-06-01 10:00 UTC; bars Mon..Mon (6 trading days).
    signal_rows = [(7, "AAPL", datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc))]
    bars = _bars([
        ("2026-06-01", 100.0),  # T0
        ("2026-06-02", 101.0),  # T+1
        ("2026-06-03", 102.0),
        ("2026-06-04", 103.0),  # T+3
        ("2026-06-05", 104.0),
        ("2026-06-08", 105.0),  # T+5
    ])

    mock_pg = MagicMock()
    mock_pg.fetch_signals_pending_forward_return.return_value = signal_rows
    mock_pg.bulk_add_forward_returns.return_value = 1

    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value = bars

    with patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg), \
         patch("psycopg2.connect", return_value=MagicMock()), \
         patch("src.workers.performance.config") as mock_cfg, \
         patch("alpaca.data.historical.StockHistoricalDataClient", return_value=mock_client):
        mock_cfg.ALPACA_API_KEY = "key"
        mock_cfg.ALPACA_SECRET_KEY = "secret"
        mock_cfg.DATABASE_URL = "postgresql://test"
        stats = run_forward_return_worker()

    assert stats["updated"] == 1
    (updates,) = mock_pg.bulk_add_forward_returns.call_args[0]
    sid, f1, f3, f5 = updates[0]
    assert sid == 7
    assert abs(f1 - 0.01) < 1e-9          # 101/100 - 1
    assert abs(f3 - 0.03) < 1e-9          # 103/100 - 1
    assert abs(f5 - 0.05) < 1e-9          # 105/100 - 1


def test_worker_partial_horizons_when_future_bars_missing():
    # Only T0..T+2 available: 1d computable, 3d/5d stay None (row remains pending).
    signal_rows = [(9, "MSFT", datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc))]
    bars = _bars([("2026-06-01", 200.0), ("2026-06-02", 202.0), ("2026-06-03", 204.0)])

    mock_pg = MagicMock()
    mock_pg.fetch_signals_pending_forward_return.return_value = signal_rows
    mock_pg.bulk_add_forward_returns.return_value = 1
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value = bars

    with patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg), \
         patch("psycopg2.connect", return_value=MagicMock()), \
         patch("src.workers.performance.config") as mock_cfg, \
         patch("alpaca.data.historical.StockHistoricalDataClient", return_value=mock_client):
        mock_cfg.ALPACA_API_KEY = "key"
        mock_cfg.ALPACA_SECRET_KEY = "secret"
        mock_cfg.DATABASE_URL = "postgresql://test"
        run_forward_return_worker()

    (updates,) = mock_pg.bulk_add_forward_returns.call_args[0]
    sid, f1, f3, f5 = updates[0]
    assert abs(f1 - 0.01) < 1e-9
    assert f3 is None and f5 is None
