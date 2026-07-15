"""Tests for the shared market-clock helper."""

from unittest.mock import MagicMock, patch

import pytest

from src.workers.market_clock import is_market_open


@pytest.fixture
def mock_config():
    """Patch Alpaca credentials so the helper attempts the API call."""
    with patch("src.workers.market_clock.config") as cfg:
        cfg.ALPACA_API_KEY = "test-key"
        cfg.ALPACA_SECRET_KEY = "test-secret"
        cfg.ALPACA_PAPER_MODE = True
        yield cfg


def test_market_open_when_alpaca_says_open(mock_config):
    """is_market_open returns True when Alpaca clock.is_open is True."""
    with patch(
        "src.workers.market_clock.TradingClient"
    ) as mock_tc:
        mock_tc.return_value.get_clock.return_value = MagicMock(is_open=True)
        assert is_market_open() is True


def test_market_closed_when_alpaca_says_closed(mock_config):
    """is_market_open returns False when Alpaca clock.is_open is False."""
    with patch(
        "src.workers.market_clock.TradingClient"
    ) as mock_tc:
        mock_tc.return_value.get_clock.return_value = MagicMock(is_open=False)
        assert is_market_open() is False


def test_market_closed_on_clock_error(mock_config):
    """is_market_open is fail-closed: an exception is treated as closed."""
    with patch(
        "src.workers.market_clock.TradingClient",
        side_effect=Exception("network outage"),
    ):
        assert is_market_open() is False


def test_market_closed_when_credentials_missing():
    """Missing Alpaca credentials make the helper return False."""
    with patch("src.workers.market_clock.config") as cfg:
        cfg.ALPACA_API_KEY = ""
        cfg.ALPACA_SECRET_KEY = ""
        assert is_market_open() is False
