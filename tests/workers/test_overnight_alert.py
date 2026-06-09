"""Tests for _alert_overnight_positions in the execution worker."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, call


class TestAlertOvernightPositions:
    def _make_redis(self, already_alerted=False):
        redis = MagicMock()
        redis.is_overnight_alert_sent.return_value = already_alerted
        return redis

    def _make_pos(self, symbol, avg_entry=100.0, current=98.0, qty=10.0):
        pos = MagicMock()
        pos.avg_entry_price = avg_entry
        pos.current_price = current
        pos.qty = qty
        return pos

    def test_no_alert_when_no_open_positions(self):
        from src.workers.execution import _alert_overnight_positions
        notifier = MagicMock()
        redis = self._make_redis()
        tick = datetime(2026, 6, 5, 19, 45, tzinfo=timezone.utc)
        _alert_overnight_positions({}, 100_000.0, notifier, redis, tick)
        notifier.send_alert.assert_not_called()
        # No dedup key set when no positions
        redis._r.setex.assert_not_called()

    def test_alert_sent_for_open_positions(self):
        from src.workers.execution import _alert_overnight_positions
        notifier = MagicMock()
        redis = self._make_redis(already_alerted=False)
        tick = datetime(2026, 6, 5, 19, 45, tzinfo=timezone.utc)
        positions = {"AAPL": self._make_pos("AAPL", 150.0, 147.0, 5)}
        _alert_overnight_positions(positions, 100_000.0, notifier, redis, tick)
        # Dedup key was marked via public method
        redis.mark_overnight_alert_sent.assert_called_once_with("2026-06-05")

    def test_dedup_prevents_double_alert(self):
        from src.workers.execution import _alert_overnight_positions
        notifier = MagicMock()
        redis = self._make_redis(already_alerted=True)
        tick = datetime(2026, 6, 5, 19, 45, tzinfo=timezone.utc)
        positions = {"TSLA": self._make_pos("TSLA")}
        _alert_overnight_positions(positions, 100_000.0, notifier, redis, tick)
        # Dedup key already present — mark_overnight_alert_sent must not be called
        redis.mark_overnight_alert_sent.assert_not_called()

    def test_dedup_key_uses_date(self):
        from src.workers.execution import _alert_overnight_positions
        redis = self._make_redis(already_alerted=False)
        tick = datetime(2026, 6, 7, 19, 30, tzinfo=timezone.utc)
        positions = {"SPY": self._make_pos("SPY")}
        _alert_overnight_positions(positions, 50_000.0, None, redis, tick)
        date_arg = redis.mark_overnight_alert_sent.call_args[0][0]
        assert "2026-06-07" in date_arg
