"""Deterministic Alpaca ``client_order_id`` construction."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime


_INVALID_CHARS = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_CLIENT_ORDER_ID_LENGTH = 128
_FORMAT_REJECTION_MARKERS = (
    "invalid format",
    "invalid character",
    "must match",
    "too long",
    "maximum length",
    "max length",
    "length must",
    "at most 128",
    "no more than 128",
)


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


def _is_format_rejection(exc: Exception) -> bool:
    message = str(exc).lower()
    return "client_order_id" in message and any(
        marker in message for marker in _FORMAT_REJECTION_MARKERS
    )


def submit_order_with_coid_fallback(trading_client, request, *, log=None, on_alert=None):
    """Submit once, omitting the ID only when Alpaca rejects its format.

    Duplicate-ID conflicts deliberately propagate: retrying those without the
    ID would defeat idempotency and could create a second order.
    """
    try:
        return trading_client.submit_order(request)
    except Exception as exc:
        client_order_id = getattr(request, "client_order_id", None)
        if client_order_id is None or not _is_format_rejection(exc):
            raise

        message = f"Alpaca rejected client_order_id={client_order_id!r}; retrying without it"
        if log is not None:
            log.warning("%s: %s", message, exc)
        if on_alert is not None:
            try:
                on_alert(message)
            except Exception:
                if log is not None:
                    log.warning("client_order_id fallback alert failed", exc_info=True)

        payload = request.model_dump(exclude_none=True)
        payload.pop("client_order_id", None)
        return trading_client.submit_order(type(request)(**payload))
