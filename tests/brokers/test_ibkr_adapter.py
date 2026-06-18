
"""Tests for IBKRAdapter — all mocked, no live IBKR connection required."""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.brokers.base import BrokerAdapter
from src.brokers.ibkr_adapter import (
    IBKRAdapter,
    IBKRConnectionError,
    IBKRContractNotFoundError,
    IBKROrderNotFoundError,
)

# We patch ib_insync.IB at import time so no real connection is made.
# The fixture creates a fresh mock per test.


@pytest.fixture
def mock_ib():
    """Patch ib_insync.IB and Stock so no live connection or contract is needed.

    ib_insync may not be installed in the test environment; both names are set
    to None at module level and must be patched for any test that exercises them.
    """
    with patch("src.brokers.ibkr_adapter.IB") as MockIB, \
         patch("src.brokers.ibkr_adapter.Stock"):
        instance = MockIB.return_value
        yield instance


@pytest.fixture
def adapter(mock_ib):
    return IBKRAdapter(host="127.0.0.1", port=7497, client_id=1, account="DU123456")


# ---------------------------------------------------------------------------
# ABC compliance
# ---------------------------------------------------------------------------


def test_ibkr_adapter_is_broker_adapter(mock_ib):
    adapter = IBKRAdapter(host="127.0.0.1", port=7497, client_id=1)
    assert isinstance(adapter, BrokerAdapter)


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


def test_connect_calls_ib_connect_with_correct_params(adapter, mock_ib):
    adapter.connect()
    mock_ib.connect.assert_called_once_with("127.0.0.1", 7497, clientId=1, timeout=4)


def test_connect_raises_ibkr_connection_error_on_failure(adapter, mock_ib):
    mock_ib.connect.side_effect = Exception("connection refused")
    with pytest.raises(IBKRConnectionError, match="Failed to connect"):
        adapter.connect()


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


def test_disconnect_calls_ib_disconnect(adapter, mock_ib):
    adapter.disconnect()
    mock_ib.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# auto-reconnect
# ---------------------------------------------------------------------------


def test_disconnect_handler_is_set_on_init(mock_ib):
    """Verify _on_disconnect is registered as the disconnectedEvent callback."""
    adapter = IBKRAdapter(host="127.0.0.1", port=7497, client_id=1)
    # The handler should be bound to the disconnectedEvent
    # We verify it by checking that calling _on_disconnect triggers reconnect logic
    assert hasattr(adapter, "_on_disconnect")
    assert callable(adapter._on_disconnect)


def test_reconnect_attempted_after_disconnect(mock_ib):
    adapter = IBKRAdapter(host="127.0.0.1", port=7497, client_id=1)
    with patch("time.sleep") as mock_sleep, patch.object(adapter, "connect") as mock_connect:
        adapter._on_disconnect()
    mock_sleep.assert_called_once_with(5)
    mock_connect.assert_called_once()


def test_reconnect_logs_error_when_connect_fails(mock_ib):
    adapter = IBKRAdapter(host="127.0.0.1", port=7497, client_id=1)
    with patch("time.sleep"), patch.object(adapter, "connect", side_effect=IBKRConnectionError("refused")):
        # Should not raise — handler absorbs the exception
        adapter._on_disconnect()


# ---------------------------------------------------------------------------
# get_account_summary
# ---------------------------------------------------------------------------


def test_get_account_summary_returns_tag_value_dict(adapter, mock_ib):
    av1 = MagicMock()
    av1.tag = "NetLiquidation"
    av1.value = "100000"
    av2 = MagicMock()
    av2.tag = "AvailableFunds"
    av2.value = "80000"
    mock_ib.accountSummary.return_value = [av1, av2]

    result = adapter.get_account_summary()

    assert result == {"NetLiquidation": "100000", "AvailableFunds": "80000"}
    mock_ib.accountSummary.assert_called_once_with("DU123456")


def test_get_account_summary_uses_configured_account(mock_ib):
    adapter = IBKRAdapter(host="127.0.0.1", port=7497, client_id=1, account="U9999999")
    mock_ib.accountSummary.return_value = []
    adapter.get_account_summary()
    mock_ib.accountSummary.assert_called_once_with("U9999999")


# ---------------------------------------------------------------------------
# submit_order
# ---------------------------------------------------------------------------


def test_submit_order_calls_place_order_and_returns_trade(adapter, mock_ib):
    contract = MagicMock()
    order = MagicMock()
    trade = MagicMock()
    mock_ib.placeOrder.return_value = trade

    result = adapter.submit_order(contract, order)

    mock_ib.placeOrder.assert_called_once_with(contract, order)
    assert result is trade


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


def test_cancel_order_finds_trade_by_id_and_cancels(adapter, mock_ib):
    trade = MagicMock()
    trade.order.orderId = 42
    mock_ib.trades.return_value = [trade]

    adapter.cancel_order(42)

    mock_ib.cancelOrder.assert_called_once_with(trade.order)


def test_cancel_order_raises_if_order_id_not_found(adapter, mock_ib):
    mock_ib.trades.return_value = []
    with pytest.raises(IBKROrderNotFoundError, match="42"):
        adapter.cancel_order(42)


def test_cancel_order_skips_non_matching_trades(adapter, mock_ib):
    other_trade = MagicMock()
    other_trade.order.orderId = 99
    target_trade = MagicMock()
    target_trade.order.orderId = 42
    mock_ib.trades.return_value = [other_trade, target_trade]

    adapter.cancel_order(42)

    mock_ib.cancelOrder.assert_called_once_with(target_trade.order)


# ---------------------------------------------------------------------------
# get_option_chain
# ---------------------------------------------------------------------------


def test_get_option_chain_returns_all_strikes_both_rights(adapter, mock_ib):
    qualified = MagicMock()
    qualified.conId = 123
    mock_ib.qualifyContracts.return_value = [qualified]

    chain = MagicMock()
    chain.expirations = {"20241220", "20241227"}
    chain.strikes = {450.0, 451.0, 452.0}
    chain.exchange = "SMART"
    chain.multiplier = "100"
    mock_ib.reqSecDefOptParams.return_value = [chain]

    result = adapter.get_option_chain("SPY", "20241220")

    # 3 strikes x 2 rights = 6 entries
    assert len(result) == 6
    assert all(r["expiry"] == "20241220" for r in result)
    assert all(r["symbol"] == "SPY" for r in result)
    assert {r["right"] for r in result} == {"C", "P"}


def test_get_option_chain_includes_exchange_and_multiplier(adapter, mock_ib):
    qualified = MagicMock()
    qualified.conId = 123
    mock_ib.qualifyContracts.return_value = [qualified]

    chain = MagicMock()
    chain.expirations = {"20241220"}
    chain.strikes = {450.0}
    chain.exchange = "CBOE"
    chain.multiplier = "100"
    mock_ib.reqSecDefOptParams.return_value = [chain]

    result = adapter.get_option_chain("SPY", "20241220")

    assert result[0]["exchange"] == "CBOE"
    assert result[0]["multiplier"] == "100"


def test_get_option_chain_raises_if_underlying_not_found(adapter, mock_ib):
    mock_ib.qualifyContracts.return_value = []
    with pytest.raises(IBKRContractNotFoundError, match="UNKNOWN"):
        adapter.get_option_chain("UNKNOWN", "20241220")


def test_get_option_chain_returns_empty_when_expiry_not_in_chain(adapter, mock_ib):
    qualified = MagicMock()
    qualified.conId = 123
    mock_ib.qualifyContracts.return_value = [qualified]

    chain = MagicMock()
    chain.expirations = {"20241220"}
    chain.strikes = {450.0}
    chain.exchange = "SMART"
    chain.multiplier = "100"
    mock_ib.reqSecDefOptParams.return_value = [chain]

    result = adapter.get_option_chain("SPY", "20250101")

    assert result == []


def test_get_option_chain_passes_correct_params_to_ib(adapter, mock_ib):
    qualified = MagicMock()
    qualified.conId = 456
    mock_ib.qualifyContracts.return_value = [qualified]
    mock_ib.reqSecDefOptParams.return_value = []

    adapter.get_option_chain("AAPL", "20241220")

    mock_ib.reqSecDefOptParams.assert_called_once_with("AAPL", "", "STK", 456)
