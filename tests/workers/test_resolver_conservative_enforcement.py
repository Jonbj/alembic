"""Conservative resolver enforcement (FUNCTIONAL_REVIEW_2026-07-03 §3.2):
items whose resolver verdict is NO_TRADE_NOT_TRADABLE are dropped BEFORE
LLM inference. Everything else passes. Any resolver error → fail-open."""

import os
from unittest.mock import patch

from src.models.news import NewsItem


def _item(ticker: str) -> NewsItem:
    return NewsItem(id=f"u:{ticker}", title="t", body="b", asset_tags=[ticker])


def test_not_tradable_items_are_filtered():
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("AAPL"), _item("XLF")]
    verdicts = {"u:AAPL": "RESOLVED", "u:XLF": "NO_TRADE_NOT_TRADABLE"}
    kept, dropped = _filter_enforced_items(items, verdicts)
    assert [i.id for i in kept] == ["u:AAPL"]
    assert dropped == 1


def test_not_tradable_drop_records_fix06_reason():
    from src.workers.sentiment import _filter_enforced_items

    rows = []
    kept, dropped = _filter_enforced_items(
        [_item("XLF")],
        {"u:XLF": "NO_TRADE_NOT_TRADABLE"},
        discard_rows=rows,
    )

    assert kept == []
    assert dropped == 1
    assert rows[0]["discarded_reason"] == "not_tradable"
    assert rows[0]["discard_stage"] == "sentiment"


def test_unknown_verdict_passes():
    """Only the hard NOT_TRADABLE verdict blocks; low-conf/ambiguous verdicts
    stay observational until QX-01 calibration."""
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("AAPL")]
    verdicts = {"u:AAPL": "NO_TRADE_LOW_CONF"}
    kept, dropped = _filter_enforced_items(items, verdicts)
    assert len(kept) == 1 and dropped == 0


def test_missing_verdict_passes():
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("AAPL")]
    kept, dropped = _filter_enforced_items(items, {})
    assert len(kept) == 1 and dropped == 0


def test_enforcement_disabled_by_env():
    from src.workers.sentiment import _filter_enforced_items
    items = [_item("XLF")]
    verdicts = {"u:XLF": "NO_TRADE_NOT_TRADABLE"}
    with patch.dict(os.environ, {"RESOLVER_ENFORCE_NOT_TRADABLE": "0"}):
        kept, dropped = _filter_enforced_items(items, verdicts)
    assert len(kept) == 1 and dropped == 0
