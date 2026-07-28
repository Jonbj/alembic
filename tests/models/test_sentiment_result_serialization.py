"""#44: SentimentResult serialization — replace the hand-rolled model_dump_json
override with a dedicated to_redis_json() method using Pydantic native serialization.

Goals:
1. Remove the override that shadows Pydantic's API (TypeError on kwargs).
2. Ensure every model field is serialised — no silent drops when fields are added.
3. Maintain wire compatibility: existing Redis payloads stay readable.

Chosen path: (b) — keep a named method (to_redis_json) rather than overriding
model_dump_json. Reason: Pydantic v2's native datetime serialisation uses ``Z``
suffix for UTC while the original override used ``+00:00`` (isoformat). The string
difference would break existing tests without being a semantic change. A separate
named method keeps the wire format stable and leaves the Pydantic contract intact.
"""

import json
from datetime import datetime, timezone

import pytest

from src.models.signals import SentimentResult


def _result(**kw) -> SentimentResult:
    base = dict(
        symbol="AAPL", score=0.5, confidence=0.8, reasoning="test reasoning",
        model_id="glm52",
    )
    base.update(kw)
    return SentimentResult(**base)


# ── Test 1: Round-trip preserves all fields ──────────────────────────────────

def test_roundtrip_preserves_all_fields():
    """SentimentResult → JSON → dict → SentimentResult round-trips cleanly,
    including None values for optional fields and timezone-aware datetimes."""
    dt = datetime(2026, 7, 10, 14, 30, 0, tzinfo=timezone.utc)
    original = SentimentResult(
        symbol="AAPL",
        score=0.75,
        confidence=0.91,
        reasoning="strong bullish signal from earnings revision",
        model_id="glm52",
        ensemble_std=0.12,
        fallback_used=False,
        generated_at=dt,
        published_at=dt,
        signal_id=3771,
    )
    json_str = original.model_dump_json()
    loaded = json.loads(json_str)

    restored = SentimentResult(
        symbol=loaded["symbol"],
        score=loaded["score"],
        confidence=loaded["confidence"],
        reasoning=loaded["reasoning"],
        model_id=loaded["model_id"],
        ensemble_std=loaded["ensemble_std"],
        fallback_used=loaded["fallback_used"],
        generated_at=datetime.fromisoformat(loaded["generated_at"]),
        published_at=datetime.fromisoformat(loaded["published_at"]) if loaded["published_at"] else None,
        signal_id=loaded["signal_id"],
    )
    assert restored.symbol == original.symbol
    assert restored.score == original.score
    assert restored.confidence == original.confidence
    assert restored.reasoning == original.reasoning
    assert restored.model_id == original.model_id
    assert restored.ensemble_std == original.ensemble_std
    assert restored.fallback_used == original.fallback_used
    assert restored.generated_at == original.generated_at
    assert restored.published_at == original.published_at
    assert restored.signal_id == original.signal_id


def test_roundtrip_with_none_optionals():
    """None values for published_at and signal_id round-trip correctly."""
    original = _result(published_at=None, signal_id=None)
    json_str = original.model_dump_json()
    loaded = json.loads(json_str)
    assert loaded["published_at"] is None
    assert loaded["signal_id"] is None


# ── Test 2: Backward compatibility with existing Redis payload ─────────────────

LITERAL_OLD_FORMAT = (
    '{"symbol": "AAPL", "score": 0.5, "confidence": 0.8, '
    '"reasoning": "test reasoning", "model_id": "glm52", '
    '"ensemble_std": 0.1, "fallback_used": false, '
    '"generated_at": "2026-07-10T14:30:00+00:00", '
    '"published_at": null, "signal_id": null}'
)


def test_old_json_payload_deserialises():
    """A JSON string in the exact format written by the old override must
    deserialize to a valid SentimentResult. This is the payload already stored
    in Redis — it must stay readable after the override is removed."""
    loaded = json.loads(LITERAL_OLD_FORMAT)
    result = SentimentResult(
        symbol=loaded["symbol"],
        score=loaded["score"],
        confidence=loaded["confidence"],
        reasoning=loaded["reasoning"],
        model_id=loaded["model_id"],
        ensemble_std=loaded["ensemble_std"],
        fallback_used=loaded["fallback_used"],
        generated_at=datetime.fromisoformat(loaded["generated_at"]),
        published_at=datetime.fromisoformat(loaded["published_at"]) if loaded["published_at"] else None,
        signal_id=loaded["signal_id"],
    )
    assert result.symbol == "AAPL"
    assert result.score == 0.5
    assert result.generated_at == datetime(2026, 7, 10, 14, 30, 0, tzinfo=timezone.utc)


# ── Test 3: Anti-regression — all model fields must appear in output ─────────

def test_all_model_fields_present_in_json_output():
    """If a developer adds a field to SentimentResult but forgets to add it to
    the serialization, this test must fail — preventing silent data loss.

    The set of fields is derived from model_fields (not hardcoded), so this
    test itself cannot become stale the way the override was.
    """
    from src.models.signals import SentimentResult

    instance = _result()
    serialized = json.loads(instance.model_dump_json())

    # Derive the expected set from the model itself — not from a written list.
    model_field_names = set(SentimentResult.model_fields.keys())
    serialized_field_names = set(serialized.keys())

    missing = model_field_names - serialized_field_names
    assert not missing, (
        f"Fields in SentimentResult model but missing from JSON output: {missing}. "
        f"Add them to the serialization, or the next deploy will silently drop them."
    )

    extra = serialized_field_names - model_field_names
    assert not extra, (
        f"Fields in JSON output but not in SentimentResult model: {extra}. "
        f"These are phantom fields that should not be serialised."
    )


# ── Test 4: Native Pydantic API accepts standard kwargs ─────────────────────

def test_native_pydantic_api_accepts_indent_kwarg():
    """model_dump_json(indent=2) must not raise TypeError.

    The old override had signature model_dump_json(self) with no args, so any
    call that passed Pydantic-standard kwargs (indent, include, exclude, ...)
    would explode. The fixed version must forward those kwargs to Pydantic.
    """
    instance = _result()
    # This must not raise TypeError
    result = instance.model_dump_json(indent=2)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert parsed["symbol"] == "AAPL"


def test_native_pydantic_api_accepts_exclude_kwarg():
    """model_dump_json(exclude={"reasoning"}) must not raise TypeError."""
    instance = _result()
    result = instance.model_dump_json(exclude={"reasoning"})
    parsed = json.loads(result)
    assert "symbol" in parsed
    assert "reasoning" not in parsed


# ── Test 5: to_redis_json produces the exact old wire format ─────────────────

def test_to_redis_json_uses_plus_offset_not_z():
    """to_redis_json() must emit ``+00:00`` for UTC, not ``Z``.

    The original override used datetime.isoformat() which produces ``+00:00``.
    Pydantic v2 native uses ``Z``. The named method normalises to ``+00:00``
    so existing Redis payloads (written by the old override) stay readable and
    new payloads are byte-for-byte identical to what consumers expect.
    """
    dt = datetime(2026, 7, 10, 14, 30, 0, tzinfo=timezone.utc)
    instance = _result(generated_at=dt, published_at=dt)
    payload = json.loads(instance.to_redis_json())
    assert payload["generated_at"] == "2026-07-10T14:30:00+00:00"
    assert payload["published_at"] == "2026-07-10T14:30:00+00:00"
    # model_dump_json (native) uses Z — confirm they differ
    native_payload = json.loads(instance.model_dump_json())
    assert native_payload["generated_at"] == "2026-07-10T14:30:00Z"


def test_to_redis_json_preserves_all_fields():
    """to_redis_json() serialises every SentimentResult field."""
    instance = _result(signal_id=3771)
    payload = json.loads(instance.to_redis_json())
    assert set(payload.keys()) == set(SentimentResult.model_fields.keys())
    assert payload["signal_id"] == 3771


def test_old_redis_literal_remains_deserialisable():
    """A Redis payload in the old override's exact string format must still
    deserialize to a valid SentimentResult — proving backward compatibility."""
    old_literal = (
        '{"symbol": "AAPL", "score": 0.5, "confidence": 0.8, '
        '"reasoning": "test reasoning", "model_id": "glm52", '
        '"ensemble_std": 0.1, "fallback_used": false, '
        '"generated_at": "2026-07-10T14:30:00+00:00", '
        '"published_at": "2026-07-10T14:30:00+00:00", '
        '"signal_id": null}'
    )
    loaded = json.loads(old_literal)
    result = SentimentResult(
        symbol=loaded["symbol"],
        score=loaded["score"],
        confidence=loaded["confidence"],
        reasoning=loaded["reasoning"],
        model_id=loaded["model_id"],
        ensemble_std=loaded["ensemble_std"],
        fallback_used=loaded["fallback_used"],
        generated_at=datetime.fromisoformat(loaded["generated_at"]),
        published_at=(
            datetime.fromisoformat(loaded["published_at"])
            if loaded["published_at"] else None
        ),
        signal_id=loaded["signal_id"],
    )
    assert result.symbol == "AAPL"
    assert result.generated_at == datetime(2026, 7, 10, 14, 30, 0, tzinfo=timezone.utc)
