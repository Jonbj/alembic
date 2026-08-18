"""Tests for deterministic Alpaca client order IDs."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from src.portfolio.order_id import build_client_order_id


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
    assert len(coid) <= 1024


def test_output_uses_only_alpaca_charset():
    coid = build_client_order_id("buy now", "BRK.B", CYCLE_TS, signal_id="news/42")
    assert re.fullmatch(r"[a-zA-Z0-9_-]+", coid)
