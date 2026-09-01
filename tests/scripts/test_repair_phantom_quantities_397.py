"""#397: the one-off repair script drives reconcile_open_positions for the three
known phantom-quantity symbols with a lookback wide enough to reach their
late-July entries (the daily 30-day window already misses them)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import scripts.repair_phantom_quantities_397 as repair


def test_main_invokes_reconcile_open_positions_for_the_three_symbols():
    pg = MagicMock()
    pg.fetch_trades.return_value = []
    tc = MagicMock()
    cfg = MagicMock()
    cfg.ALPACA_API_KEY = "x"
    cfg.ALPACA_SECRET_KEY = "x"
    cfg.ALPACA_PAPER_MODE = True

    with patch("src.store.pg_store.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.config.config", cfg):
        rc = repair.main()

    assert rc == 0
    pg.reconcile_open_positions.assert_called_once()
    _args, kwargs = pg.reconcile_open_positions.call_args
    assert set(kwargs["symbols"]) == {"NOK", "WDC", "MRVL"}
    assert kwargs["lookback_days"] >= 60  # reaches the late-July entries


def test_main_aborts_without_credentials():
    cfg = MagicMock()
    cfg.ALPACA_API_KEY = ""
    cfg.ALPACA_SECRET_KEY = "x"
    cfg.ALPACA_PAPER_MODE = True
    with patch("src.config.config", cfg):
        rc = repair.main()
    assert rc == 2