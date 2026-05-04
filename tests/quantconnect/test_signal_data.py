"""
Tests for QuantConnect LLMSignalData feed.

These tests mock the QuantConnect runtime and Redis to verify:
1. Signal parsing from JSON
2. Freshness checks
3. Signal data field access
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Import the signal data module
from quantconnect.signal_data import LLMSignalData, SIGNAL_MAX_AGE_MIN


class MockConfig:
    """Mock QuantConnect subscription config."""
    def __init__(self, symbol_value: str):
        self.Symbol = MagicMock()
        self.Symbol.Value = symbol_value


class TestLLMSignalData:
    """Tests for LLMSignalData custom feed."""

    def test_reader_parses_valid_json(self):
        """Test that Reader correctly parses valid JSON signal."""
        signal_data = LLMSignalData()
        config = MockConfig("AAPL")

        json_line = '''{
            "score": 0.45,
            "confidence": 0.85,
            "regime_multiplier": 1.2,
            "fallback_used": false,
            "generated_at": "2026-05-04T10:30:00Z"
        }'''

        date = datetime(2026, 5, 4, 10, 30, 0, tzinfo=timezone.utc)
        result = signal_data.Reader(config, json_line, date, isLive=False)

        assert result is not None
        assert result.Symbol.Value == "AAPL"
        assert result.Value == 0.45
        assert result.get("sentiment_score") == 0.45
        assert result.get("confidence") == 0.85
        assert result.get("regime_multiplier") == 1.2
        assert result.get("fallback_used") is False
        assert result.get("generated_at") == "2026-05-04T10:30:00Z"

    def test_reader_returns_none_on_empty_line(self):
        """Test that Reader returns None for empty input."""
        signal_data = LLMSignalData()
        config = MockConfig("AAPL")
        date = datetime(2026, 5, 4, 10, 30, 0, tzinfo=timezone.utc)

        assert signal_data.Reader(config, "", date, isLive=False) is None
        assert signal_data.Reader(config, "   \n  ", date, isLive=False) is None

    def test_reader_returns_none_on_invalid_json(self):
        """Test that Reader returns None for malformed JSON."""
        signal_data = LLMSignalData()
        config = MockConfig("AAPL")
        date = datetime(2026, 5, 4, 10, 30, 0, tzinfo=timezone.utc)

        assert signal_data.Reader(config, "not json", date, isLive=False) is None
        assert signal_data.Reader(config, "{incomplete", date, isLive=False) is None

    def test_reader_handles_missing_optional_fields(self):
        """Test that Reader uses defaults for missing optional fields."""
        signal_data = LLMSignalData()
        config = MockConfig("MSFT")

        # Minimal valid JSON with only required field
        json_line = '{"generated_at": "2026-05-04T10:30:00Z"}'
        date = datetime(2026, 5, 4, 10, 30, 0, tzinfo=timezone.utc)
        result = signal_data.Reader(config, json_line, date, isLive=False)

        assert result is not None
        assert result.Value == 0.0  # default
        assert result.get("sentiment_score") == 0.0  # default
        assert result.get("regime_multiplier") == 1.0  # default
        assert result.get("confidence") == 0.0  # default
        assert result.get("fallback_used") is False  # default

    def test_getSource_returns_correct_url_live(self):
        """Test GetSource returns correct URL for live mode.

        Note: SubscriptionDataSource is only available in QC runtime.
        This test verifies the URL string construction logic.
        """
        signal_data = LLMSignalData()
        config = MockConfig("AAPL")
        date = datetime(2026, 5, 4, 10, 30, 0)

        # GetSource returns a string URL when SubscriptionDataSource is not available
        # In QC runtime, this would be wrapped in SubscriptionDataSource
        result = signal_data.GetSource(config, date, isLive=True)
        # The URL should contain the correct endpoint
        assert "localhost:8000/api/signals/AAPL" in str(result)

    def test_getSource_returns_correct_url_backtest(self):
        """Test GetSource returns correct URL for backtest mode.

        Note: SubscriptionDataSource is only available in QC runtime.
        This test verifies the URL string construction logic.
        """
        signal_data = LLMSignalData()
        config = MockConfig("GOOGL")
        date = datetime(2026, 5, 4, 10, 30, 0)

        result = signal_data.GetSource(config, date, isLive=False)
        assert "localhost:8000/api/signals/history" in str(result)
        assert "symbol=GOOGL" in str(result)
        assert "date=2026-05-04" in str(result)


class TestLLMSignalDataFreshness:
    """Tests for LLMSignalData.is_fresh() static method."""

    def test_fresh_signal_within_threshold(self):
        """Test that fresh signals pass freshness check."""
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        signal = LLMSignalData()
        signal._data = {
            "generated_at": (now - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
        }

        assert LLMSignalData.is_fresh(signal, now) is True

    def test_stale_signal_beyond_threshold(self):
        """Test that stale signals fail freshness check."""
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        signal = LLMSignalData()
        # Signal older than SIGNAL_MAX_AGE_MIN (30 minutes)
        signal._data = {
            "generated_at": (now - timedelta(minutes=45)).isoformat().replace("+00:00", "Z")
        }

        assert LLMSignalData.is_fresh(signal, now) is False

    def test_freshness_at_exact_threshold(self):
        """Test signal at exact threshold boundary."""
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        signal = LLMSignalData()
        signal._data = {
            "generated_at": (now - timedelta(minutes=SIGNAL_MAX_AGE_MIN)).isoformat().replace("+00:00", "Z")
        }

        assert LLMSignalData.is_fresh(signal, now) is True

    def test_missing_generated_at_returns_false(self):
        """Test that missing generated_at field returns False."""
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        signal = LLMSignalData()
        signal._data = {}  # No generated_at

        assert LLMSignalData.is_fresh(signal, now) is False

    def test_invalid_date_format_returns_false(self):
        """Test that invalid date format returns False."""
        now = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        signal = LLMSignalData()
        signal._data = {"generated_at": "not-a-date"}

        assert LLMSignalData.is_fresh(signal, now) is False

    def test_handles_timezone_naive_algorithm_time(self):
        """Test freshness check with timezone-naive algorithm time."""
        # Algorithm time without timezone (common in backtesting)
        now_naive = datetime(2026, 5, 4, 12, 0, 0)
        signal = LLMSignalData()
        signal._data = {
            "generated_at": "2026-05-04T11:45:00Z"  # 15 minutes before
        }

        # Should not raise, should return True
        assert LLMSignalData.is_fresh(signal, now_naive) is True


class TestLLMSignalDataIntegration:
    """Integration-style tests for signal data."""

    def test_signal_data_full_flow(self):
        """Test complete signal data flow from JSON to access."""
        # Create signal data
        signal = LLMSignalData()
        config = MockConfig("AAPL")
        json_line = '''{
            "score": 0.5,
            "confidence": 0.9,
            "regime_multiplier": 1.0,
            "fallback_used": false,
            "generated_at": "2026-05-04T12:00:00Z"
        }'''
        date = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        result = signal.Reader(config, json_line, date, isLive=False)

        assert result is not None
        assert result.get("sentiment_score") == 0.5
        assert result.get("confidence") == 0.9
        assert result.get("regime_multiplier") == 1.0
        assert result.get("fallback_used") is False

        # Test freshness
        now = datetime(2026, 5, 4, 12, 15, 0, tzinfo=timezone.utc)  # 15 min later
        assert LLMSignalData.is_fresh(result, now) is True

    def test_signal_score_access_patterns(self):
        """Test various ways to access signal data."""
        signal = LLMSignalData()
        config = MockConfig("NVDA")
        json_line = '''{
            "score": 0.75,
            "confidence": 0.88,
            "regime_multiplier": 1.5,
            "fallback_used": true,
            "generated_at": "2026-05-04T12:00:00Z"
        }'''
        date = datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        result = signal.Reader(config, json_line, date, isLive=False)

        # Test bracket access
        assert result["sentiment_score"] == 0.75
        assert result["regime_multiplier"] == 1.5
        assert result["fallback_used"] is True

        # Test .get() with default
        assert result.get("nonexistent", "default") == "default"
        assert result.get("confidence", 0.0) == 0.88
