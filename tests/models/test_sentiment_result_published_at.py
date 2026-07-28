"""FIX-03 part 1: SentimentResult carries the news publication time."""

import json
from datetime import datetime, timezone

from src.models.signals import SentimentResult


def _result(**kw) -> SentimentResult:
    base = dict(
        symbol="AAPL", score=0.5, confidence=0.8, reasoning="r",
        model_id="kimi-k2.6:cloud",
    )
    base.update(kw)
    return SentimentResult(**base)


def test_published_at_defaults_to_none():
    assert _result().published_at is None


def test_published_at_roundtrips_in_json():
    """The published_at instant must survive serialisation intact.

    We assert semantics (the datetime instant is preserved) rather than the
    string format — Pydantic uses ``Z`` suffix, which is semantically
    equivalent to ``+00:00`` for UTC, and consumers (Python fromisoformat,
    JS Date) parse both correctly.
    """
    ts = datetime(2026, 7, 3, 14, 30, tzinfo=timezone.utc)
    payload = json.loads(_result(published_at=ts).model_dump_json())
    assert datetime.fromisoformat(payload["published_at"]) == ts


def test_published_at_none_serialises_as_null():
    payload = json.loads(_result().model_dump_json())
    assert payload["published_at"] is None
