"""Deterministic Alpaca ``client_order_id`` construction."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime


_INVALID_CHARS = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_CLIENT_ORDER_ID_LENGTH = 1024


def _sanitize(token: str) -> str:
    return _INVALID_CHARS.sub("-", token)


def build_client_order_id(
    purpose: str,
    symbol: str,
    cycle_ts: datetime,
    signal_id: str | int | None = None,
) -> str:
    """Return a stable ID for one logical order submission.

    A signal-backed order uses the signal ID so reprocessing the same signal
    yields the same broker identifier. Other orders use the cycle timestamp.
    """
    suffix = str(signal_id) if signal_id is not None else cycle_ts.strftime("%Y%m%dT%H%M")
    value = "-".join(
        ("ambc", _sanitize(purpose), _sanitize(symbol), _sanitize(suffix))
    )
    if len(value) <= _MAX_CLIENT_ORDER_ID_LENGTH:
        return value

    digest = hashlib.sha256(value.encode("ascii")).hexdigest()[:16]
    prefix_length = _MAX_CLIENT_ORDER_ID_LENGTH - len(digest) - 1
    return f"{value[:prefix_length]}-{digest}"
