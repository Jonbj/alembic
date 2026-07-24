"""Public cursor-contract tests for the mobile event feed."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.mobile_monitoring.events import CursorError, decode_cursor, encode_cursor


def test_event_cursor_round_trip_is_opaque_and_signed() -> None:
    occurred_at = datetime(2026, 7, 23, 14, 0, tzinfo=timezone.utc)
    event_id = uuid4()

    cursor = encode_cursor(occurred_at, event_id)

    assert str(event_id) not in cursor
    assert decode_cursor(cursor) == (occurred_at, event_id)


def test_event_cursor_rejects_tampering() -> None:
    cursor = encode_cursor(datetime.now(timezone.utc), uuid4())
    index = len(cursor) // 2
    replacement = "A" if cursor[index] != "A" else "B"

    with pytest.raises(CursorError, match="signature"):
        decode_cursor(cursor[:index] + replacement + cursor[index + 1 :])
