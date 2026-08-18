"""Tests for the paper-only Alpaca client-order-ID probe."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.verify_alpaca_coid_dedup import probe_duplicate_submit


def _request():
    return SimpleNamespace(client_order_id="ambc-spike-AAPL-test")


def test_probe_confirms_same_order_returned():
    client = MagicMock()
    original = SimpleNamespace(id="order-1")
    client.submit_order.side_effect = [original, original]

    result = probe_duplicate_submit(client, _request(), pause_seconds=0)

    assert result.verdict == "dedup_confirmed"
    assert result.behavior == "returned_original"
    assert result.first_order_id == "order-1"


def test_probe_confirms_409_only_after_lookup_matches_original():
    client = MagicMock()
    client.submit_order.side_effect = [
        SimpleNamespace(id="order-1"),
        RuntimeError("409: client_order_id must be unique"),
    ]
    client.get_order_by_client_id.return_value = SimpleNamespace(id="order-1")

    result = probe_duplicate_submit(client, _request(), pause_seconds=0)

    assert result.verdict == "dedup_confirmed"
    assert result.behavior == "conflict_409"
    assert result.lookup_order_id == "order-1"


def test_probe_reports_duplicate_when_second_order_differs():
    client = MagicMock()
    client.submit_order.side_effect = [
        SimpleNamespace(id="order-1"),
        SimpleNamespace(id="order-2"),
    ]

    result = probe_duplicate_submit(client, _request(), pause_seconds=0)

    assert result.verdict == "no_dedup"
    assert result.behavior == "created_duplicate"
    assert result.second_order_id == "order-2"
