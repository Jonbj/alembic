"""Tests for deterministic Alpaca client order IDs."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.portfolio.order_id import build_client_order_id, submit_order_with_coid_fallback


CYCLE_TS = datetime(2026, 8, 7, 14, 52, tzinfo=timezone.utc)


def test_default_format_uses_cycle_timestamp():
    assert build_client_order_id("buy", "AAPL", CYCLE_TS) == "ambc-buy-AAPL-20260807T1452"


def test_signal_id_replaces_cycle_timestamp():
    assert build_client_order_id("buy", "AAPL", CYCLE_TS, signal_id=4427) == "ambc-buy-AAPL-4427"


def test_none_signal_id_uses_cycle_timestamp():
    assert build_client_order_id("sell", "SPY", CYCLE_TS, signal_id=None) == "ambc-sell-SPY-20260807T1452"


def test_string_signal_id_is_preserved():
    assert build_client_order_id("buy", "AAPL", CYCLE_TS, signal_id="sig_42") == "ambc-buy-AAPL-sig_42"


def test_invalid_symbol_characters_are_replaced():
    assert build_client_order_id("buy", "BRK.B", CYCLE_TS) == "ambc-buy-BRK-B-20260807T1452"


def test_invalid_purpose_characters_are_replaced():
    assert build_client_order_id("stop loss", "AAPL", CYCLE_TS) == "ambc-stop-loss-AAPL-20260807T1452"


def test_invalid_signal_id_characters_are_replaced():
    assert build_client_order_id("buy", "AAPL", CYCLE_TS, signal_id="news/42") == "ambc-buy-AAPL-news-42"


def test_same_inputs_are_deterministic():
    assert build_client_order_id("buy", "AAPL", CYCLE_TS, 4427) == build_client_order_id(
        "buy", "AAPL", CYCLE_TS, 4427
    )


def test_different_purposes_are_distinct():
    assert build_client_order_id("buy", "AAPL", CYCLE_TS) != build_client_order_id(
        "sell", "AAPL", CYCLE_TS
    )


def test_different_symbols_are_distinct():
    assert build_client_order_id("buy", "AAPL", CYCLE_TS) != build_client_order_id(
        "buy", "MSFT", CYCLE_TS
    )


def test_very_long_tokens_stay_within_alpaca_limit():
    coid = build_client_order_id("purpose" * 300, "symbol" * 300, CYCLE_TS)
    assert len(coid) <= 48


def test_output_uses_only_alpaca_charset():
    coid = build_client_order_id("buy now", "BRK.B", CYCLE_TS, signal_id="news/42")
    assert re.fullmatch(r"[a-zA-Z0-9_-]+", coid)


def _request_with_coid(coid="ambc-buy-AAPL-20260807T1452"):
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    return MarketOrderRequest(
        symbol="AAPL",
        qty=10,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=coid,
    )


def test_format_rejection_retries_without_client_order_id_and_alerts():
    trading_client = MagicMock()
    retry_response = MagicMock(id="retry")
    trading_client.submit_order.side_effect = [
        RuntimeError("client_order_id has invalid format"),
        retry_response,
    ]
    logger = MagicMock()
    on_alert = MagicMock()

    result = submit_order_with_coid_fallback(
        trading_client,
        _request_with_coid(),
        log=logger,
        on_alert=on_alert,
    )

    assert result is retry_response
    assert trading_client.submit_order.call_count == 2
    retry_request = trading_client.submit_order.call_args_list[1].args[0]
    assert retry_request.client_order_id is None
    assert retry_request.symbol == "AAPL"
    logger.warning.assert_called_once()
    on_alert.assert_called_once()


def test_duplicate_client_order_id_conflict_never_retries_without_id():
    trading_client = MagicMock()
    error = RuntimeError("409: client_order_id must be unique")
    trading_client.submit_order.side_effect = error

    with pytest.raises(RuntimeError, match="must be unique"):
        submit_order_with_coid_fallback(trading_client, _request_with_coid())

    trading_client.submit_order.assert_called_once()


def test_non_client_order_id_error_is_reraised():
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = RuntimeError("insufficient buying power")

    with pytest.raises(RuntimeError, match="insufficient buying power"):
        submit_order_with_coid_fallback(trading_client, _request_with_coid())

    trading_client.submit_order.assert_called_once()


def test_request_without_client_order_id_is_not_retried():
    trading_client = MagicMock()
    trading_client.submit_order.side_effect = RuntimeError("client_order_id has invalid format")

    with pytest.raises(RuntimeError, match="invalid format"):
        submit_order_with_coid_fallback(trading_client, _request_with_coid(None))

    trading_client.submit_order.assert_called_once()


def test_successful_submit_is_returned_without_alert():
    trading_client = MagicMock()
    response = MagicMock(id="ok")
    trading_client.submit_order.return_value = response
    on_alert = MagicMock()

    result = submit_order_with_coid_fallback(
        trading_client,
        _request_with_coid(),
        on_alert=on_alert,
    )

    assert result is response
    trading_client.submit_order.assert_called_once()
    on_alert.assert_not_called()
