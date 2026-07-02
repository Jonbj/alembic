"""Earnings PEAD worker: structured surprise → S7 SurpriseSignal (unlocks S7)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.connectors.earnings_calendar import EarningsEvent
from src.workers import earnings_pead_worker as w


def _fake_config(key="k"):
    return SimpleNamespace(
        FINNHUB_API_KEY=key,
        WATCHLIST_SYMBOLS=["AAPL", "MSFT"],
        PEAD_SURPRISE_THRESHOLD=0.05,
        PEAD_MIN_CONFIDENCE=0.70,
        PEAD_HOLD_DAYS=20,
        PEAD_REDIS_TTL_SECONDS=100,
    )


class TestDirection:
    def test_beat_miss_inline_no_eps(self):
        assert w._to_llm_output(EarningsEvent("A", "d", 1.5, 1.0), 0.05).direction == "beat"
        assert w._to_llm_output(EarningsEvent("A", "d", 0.8, 1.0), 0.05).direction == "miss"
        assert w._to_llm_output(EarningsEvent("A", "d", 1.02, 1.0), 0.05).direction == "inline"
        assert w._to_llm_output(EarningsEvent("A", "d", None, 1.0), 0.05).direction == "no_eps"


def test_worker_writes_signal_only_for_watchlist_beat_above_threshold():
    events = [
        EarningsEvent("AAPL", "2026-07-01", 1.5, 1.0, "amc"),   # +50% beat, watchlist → signal
        EarningsEvent("ZZZZ", "2026-07-01", 1.5, 1.0, "amc"),   # not watchlist → skip
        EarningsEvent("MSFT", "2026-07-01", 1.01, 1.0, "amc"),  # +1% → below threshold → no signal
    ]
    mock_provider = MagicMock()
    mock_provider.fetch = AsyncMock(return_value=events)
    mock_redis = MagicMock()
    mock_redis.is_pead_processed.return_value = False

    with patch.object(w, "config", _fake_config()), \
         patch.object(w, "EarningsCalendarProvider", return_value=mock_provider), \
         patch.object(w, "RedisStore", return_value=mock_redis):
        stats = w.run_earnings_pead_worker()

    assert stats["signals_written"] == 1
    assert mock_redis.write_pead_signal.call_count == 1
    written = mock_redis.write_pead_signal.call_args[0][0]
    assert written.symbol == "AAPL" and written.direction == "beat"
    assert written.surprise_pct == 0.5


def test_worker_skips_without_key():
    with patch.object(w, "config", _fake_config(key="")):
        assert w.run_earnings_pead_worker()["skipped"] is True
