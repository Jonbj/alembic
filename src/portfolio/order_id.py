"""Deterministic Alpaca ``client_order_id`` construction and safe submission."""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime

from src.util.retry import retry_transient


_log = logging.getLogger(__name__)

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
# Alpaca rejects a re-used client_order_id with HTTP 422 + code 40010001
# ("client_order_id must be unique"). Measured on the paper account during the
# #201 spike (2026-08-20); the 409 the CLI guide documents is not what the
# Trading API returns.
_DUPLICATE_REJECTION_CODE = "40010001"
_DUPLICATE_REJECTION_MARKERS = ("must be unique",)

# Total submit attempts, matching the read-side default in src/util/retry.py.
_SUBMIT_MAX_ATTEMPTS = 4


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


def _is_duplicate_rejection(exc: Exception) -> bool:
    """True when Alpaca refused the submit because the ID is already taken."""
    message = str(exc).lower()
    if _DUPLICATE_REJECTION_CODE in message:
        return True
    return "client_order_id" in message and any(
        marker in message for marker in _DUPLICATE_REJECTION_MARKERS
    )


def _notify(on_alert, message: str) -> None:
    """Best-effort operator notification; a failing channel must not mask the order."""
    if on_alert is None:
        return
    try:
        on_alert(message)
    except Exception:
        _log.warning("submit alert callback failed", exc_info=True)


def _lookup_submitted_order(trading_client, client_order_id: str):
    """Fetch the order the broker says already exists, or None if unknowable."""
    getter = getattr(trading_client, "get_order_by_client_id", None)
    if getter is None:
        return None
    try:
        return retry_transient(lambda: getter(client_order_id))
    except Exception:
        _log.error(
            "duplicate client_order_id=%r but lookup failed; cannot confirm the order",
            client_order_id, exc_info=True,
        )
        return None


def submit_order_with_coid_fallback(
    trading_client,
    request,
    *,
    log=None,
    on_alert=None,
    max_attempts: int = _SUBMIT_MAX_ATTEMPTS,
):
    """Submit an order, retrying transient broker failures safely.

    A retried submit is only safe because every request carries a deterministic
    ``client_order_id``: the broker dedupes on it, so a retry yields one fill,
    not two. Requests without that key are submitted exactly once.

    When a retry comes back as a duplicate rejection, the earlier attempt did
    reach the broker despite the error it returned. That is "already sent", not
    "failed", so the existing order is resolved by ID and returned. A duplicate
    on the *first* attempt is not ours -- it belongs to an earlier cycle -- and
    propagates unchanged.

    The format fallback (submitting without the ID) stays a single attempt: it
    drops the idempotency key, so retrying it could create a second order.
    """
    logger = log if log is not None else _log
    client_order_id = getattr(request, "client_order_id", None)

    if client_order_id is None:
        # No idempotency key -> no safe retry.
        return trading_client.submit_order(request)

    state = {"attempts": 0}

    def _attempt():
        state["attempts"] += 1
        is_first = state["attempts"] == 1
        try:
            return trading_client.submit_order(request)
        except Exception as exc:
            if is_first or not _is_duplicate_rejection(exc):
                raise
            resolved = _lookup_submitted_order(trading_client, client_order_id)
            if resolved is None:
                raise
            message = (
                f"Submit retry hit a duplicate client_order_id={client_order_id!r}; "
                f"the original order {getattr(resolved, 'id', '?')} went through"
            )
            logger.warning(message)
            _notify(on_alert, message)
            return resolved

    try:
        return retry_transient(_attempt, max_attempts=max_attempts)
    except Exception as exc:
        if state["attempts"] > 1:
            message = (
                f"Submit failed after {state['attempts']} attempts for "
                f"client_order_id={client_order_id!r}: {exc}"
            )
            logger.error(message)
            _notify(on_alert, message)
            raise
        if not _is_format_rejection(exc):
            raise

        message = f"Alpaca rejected client_order_id={client_order_id!r}; retrying without it"
        logger.warning("%s: %s", message, exc)
        _notify(on_alert, message)

        payload = request.model_dump(exclude_none=True)
        payload.pop("client_order_id", None)
        return trading_client.submit_order(type(request)(**payload))
