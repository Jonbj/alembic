"""EOD position reconciliation task (spec §2): alert on anomalies + flag-gated
auto-close of genuinely_orphan trades. Mirrors run_reconcile_fills_intraday's
credential guard + try/except shape."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.workers.performance import run_reconcile_positions


def _mock_pg(open_trades):
    pg = MagicMock()
    pg.fetch_trades.return_value = open_trades
    pg.record_trade_exit.return_value = 1
    return pg


def _mock_tc(held_positions, orders=None):
    tc = MagicMock()
    tc.get_all_positions.return_value = held_positions
    tc.get_orders.return_value = orders or []
    return tc


def _cfg(enabled=False, dry_run=True):
    cfg = MagicMock()
    cfg.ALPACA_API_KEY = "xxx"
    cfg.ALPACA_SECRET_KEY = "xxx"
    cfg.ALPACA_PAPER_MODE = True
    cfg.RECONCILE_AUTOCLOSE_ENABLED = enabled
    cfg.RECONCILE_AUTOCLOSE_DRY_RUN = dry_run
    return cfg


def _trade(tid, symbol, qty):
    return {"id": tid, "symbol": symbol, "qty": qty,
            "entry_time": "2026-07-22T16:00:00+00:00", "stop_strategy": "S4"}


def test_skips_when_no_credentials():
    cfg = _cfg()
    cfg.ALPACA_API_KEY = ""
    with patch("src.workers.performance.config", cfg):
        result = run_reconcile_positions()
    assert result["skipped"] is True
    assert result["reason"] == "no_credentials"


def test_alerts_on_genuinely_orphan_anomaly():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    tc = _mock_tc([])  # broker holds nothing -> BBB is genuinely_orphan
    with patch("src.workers.performance.config", _cfg(enabled=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["counts"]["genuinely_orphan"] == 1
    assert result["anomalies"] == 1
    tn.assert_called_once()
    msg = tn.return_value.send_alert.call_args.args[0]
    assert "genuinely_orphan" in msg
    pg.record_trade_exit.assert_not_called()  # autoclose disabled


def test_no_anomalies_sends_no_alert():
    pg = _mock_pg([_trade(1, "AAA", 2.0)])
    held = [MagicMock(symbol="AAA", qty="2.0")]  # fully_held -> not an anomaly
    tc = _mock_tc(held)
    with patch("src.workers.performance.config", _cfg(enabled=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["anomalies"] == 0
    tn.assert_not_called()


def test_autoclose_dry_run_does_not_write():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    tc = _mock_tc([])
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=True)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["autoclose"]["dry_run"] is True
    assert result["autoclose"]["planned"] == 1
    assert result["autoclose"]["closed"] == 0
    pg.record_trade_exit.assert_not_called()


def test_autoclose_live_calls_record_trade_exit_with_synthetic_id():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    tc = _mock_tc([])  # no broker SELL orders found -> synthetic id
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["autoclose"]["dry_run"] is False
    assert result["autoclose"]["closed"] == 1
    pg.record_trade_exit.assert_called_once()
    _, kwargs = pg.record_trade_exit.call_args
    assert kwargs["exit_reason"] == "orphan_reconcile"
    assert kwargs["trade_id"] == 9
    assert kwargs["symbol"] == "BBB"
    assert kwargs["exit_order_id"] == "orphan_reconcile:9"
    assert isinstance(kwargs["exit_time"], datetime)


def test_autoclose_does_not_attach_an_unlinked_broker_sell():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    order = MagicMock()
    order.id = "historical-sell-123"
    order.status = MagicMock(value="filled")
    order.filled_avg_price = "150.00"
    tc = _mock_tc([], orders=[order])
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["autoclose"]["closed"] == 1
    _, kwargs = pg.record_trade_exit.call_args
    assert kwargs["exit_order_id"] == "orphan_reconcile:9"
    tc.get_orders.assert_not_called()


def test_over_held_and_untracked_are_alerted_not_closed():
    """over_held + untracked_position -> alerted only, never force-closed
    (auto-closing those = broker orders = out of scope)."""
    pg = _mock_pg([_trade(2, "CCC", 1.0)])
    # CCC over_held (broker holds 3.0 > 1.0) + ZZZ untracked (no DB trade)
    held = [MagicMock(symbol="CCC", qty="3.0"), MagicMock(symbol="ZZZ", qty="5.0")]
    tc = _mock_tc(held)
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["counts"]["over_held"] == 1
    assert result["counts"]["untracked_position"] == 1
    assert result["anomalies"] == 2
    # No genuinely_orphan -> nothing to close.
    assert result["autoclose"]["closed"] == 0
    pg.record_trade_exit.assert_not_called()


def test_classify_error_never_crashes_worker_and_alerts():
    """spec §2: a classify error -> alert (best-effort), never crash the worker."""
    pg = _mock_pg([])
    pg.fetch_trades.side_effect = RuntimeError("db down")
    with patch("src.workers.performance.config", _cfg(enabled=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=MagicMock()), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert "error" in result
    assert "db down" in result["error"]
    tn.assert_called_once()  # failure alert sent
