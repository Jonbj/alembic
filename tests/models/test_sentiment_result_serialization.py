"""#44: SentimentResult serialization — remove the hand-rolled model_dump_json
override and use Pydantic native serialization.

Goals:
1. Remove the override that shadows Pydantic's API (TypeError on kwargs).
2. Ensure every model field is serialised — no silent drops when fields are added.
3. Maintain semantic compatibility: datetime instants survive serialisation;
   Python fromisoformat (3.11) and JS Date accept both Z and +00:00.

Chosen path: (a) — remove override entirely, rely on Pydantic native.

Wire format change: new Redis writes use ``Z`` suffix (Pydantic native) instead
of ``+00:00`` (old override). This is safe because:
- _stale_signal_key (portfolio_scheduler:2824) uses datetime.isoformat() on the
  parsed object — string format is irrelevant.
- Python fromisoformat on 3.11 accepts both Z and +00:00.
- Frontend uses new Date() which accepts both.
- No consumer compares raw strings.
- TTL means old +00:00 payloads expire naturally.
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


# ── Test 5: native datetime serialisation round-trips ─────────────────────────

def test_datetime_roundtrips_via_fromisoformat():
    """A UTC datetime serialised by Pydantic (Z suffix) must deserialise back
    to the same instant via datetime.fromisoformat().

    The invariant being tested is the instant, not the string format — Pydantic
    uses Z which is semantically identical to +00:00 for UTC.
    """
    dt = datetime(2026, 7, 10, 14, 30, 0, tzinfo=timezone.utc)
    instance = _result(generated_at=dt, published_at=dt)
    payload = json.loads(instance.model_dump_json())
    # Both fields round-trip via fromisoformat (Python 3.11 accepts Z and +00:00)
    assert datetime.fromisoformat(payload["generated_at"]) == dt
    assert datetime.fromisoformat(payload["published_at"]) == dt


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
