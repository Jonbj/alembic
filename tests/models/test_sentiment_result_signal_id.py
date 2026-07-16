"""B33-follow-up: SentimentResult carries the DB signal id so downstream
consumers (ranker -> decision log -> idempotency) can pin the exact signal
used, instead of re-fetching "latest" later and racing a newer signal."""

import json

from src.models.signals import SentimentResult


def _result(**kw) -> SentimentResult:
    base = dict(
        symbol="AAPL", score=0.5, confidence=0.8, reasoning="r",
        model_id="kimi-k2.6:cloud",
    )
    base.update(kw)
    return SentimentResult(**base)


def test_signal_id_defaults_to_none():
    assert _result().signal_id is None


def test_signal_id_roundtrips_in_json():
    payload = json.loads(_result(signal_id=3770).model_dump_json())
    assert payload["signal_id"] == 3770


def test_signal_id_none_serialises_as_null():
    payload = json.loads(_result().model_dump_json())
    assert payload["signal_id"] is None
