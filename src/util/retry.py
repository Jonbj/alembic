"""Centralized retry/backoff for Alpaca API calls.

Alpaca's built-in SDK retry is 3x3s fixed, only 429/504, with no Retry-After
support and no 502/503 (alpaca/common/constants.py:11-13). A sustained 429
therefore loses the whole cycle (15 min to the next beat). This module provides
`retry_transient` -- exponential backoff + jitter + Retry-After respect --
modeled on src/connectors/gdelt_base.py.

Retry policy:
  - Retry on HTTP 429, 500, 502, 503, 504 (transient / server-side).
  - Fail immediately on 400, 403, 422 (client error -- retrying won't help).
  - Respect the `Retry-After` response header (seconds; HTTP-date form is not
    parsed -- Alpaca emits seconds).
  - Non-APIError exceptions (e.g. network) propagate immediately; the existing
    call-site degrade paths handle them.

Usage:
  account = retry_transient(trading_client.get_account)
  bars = retry_transient(lambda: data_client.get_stock_bars(request))
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from alpaca.common.exceptions import APIError

log = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP statuses that warrant a retry (transient / server-side).
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _is_retryable(error: APIError) -> bool:
    """True if the APIError's HTTP status is in the retryable set."""
    status = error.status_code
    return status is not None and status in _RETRYABLE_STATUS


def _parse_retry_after(error: APIError) -> float | None:
    """Extract the Retry-After wait in seconds from an APIError, or None.

    Alpaca emits Retry-After as an integer number of seconds. The HTTP-date
    form is not parsed (Alpaca does not use it); a non-numeric value returns None.
    """
    response = error.response
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _compute_backoff(
    attempt: int, base: float, cap: float, retry_after: float | None
) -> float:
    """Exponential backoff with full jitter, floored by Retry-After.

    raw = min(base * 2**attempt, cap)
    wait = random.uniform(0, raw)   # full jitter
    if retry_after is not None: wait = max(wait, retry_after)
    """
    raw = min(base * (2 ** attempt), cap)
    wait = random.uniform(0.0, raw)
    return max(wait, retry_after) if retry_after is not None else wait


def retry_transient(
    fn: Callable[[], T],
    *,
    max_attempts: int = 4,
    base: float = 2.0,
    cap: float = 30.0,
) -> T:
    """Call fn() with exponential backoff retry on transient Alpaca API errors.

    Args:
        fn: Zero-arg callable (curry args via lambda / functools.partial).
        max_attempts: Total attempts (1 = no retry). Default 4.
        base: Base backoff in seconds (first retry waits ~base). Default 2.0.
        cap: Maximum backoff in seconds. Default 30.0.

    Returns:
        fn()'s return value on success.

    Raises:
        APIError: The last APIError if all attempts are exhausted, or a
            non-retryable APIError (raised immediately, no retry). Other
            exceptions propagate immediately (no retry).
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except APIError as exc:
            if not _is_retryable(exc):
                log.warning(
                    "retry_transient: non-retryable APIError %s -- failing immediately",
                    exc.status_code,
                )
                raise
            if attempt == max_attempts - 1:
                log.error(
                    "retry_transient: exhausted %d attempts (last status=%s)",
                    max_attempts, exc.status_code,
                )
                raise
            retry_after = _parse_retry_after(exc)
            wait = _compute_backoff(attempt, base, cap, retry_after)
            log.warning(
                "retry_transient: attempt %d/%d failed (status=%s) -- retrying in %.1fs",
                attempt + 1, max_attempts, exc.status_code, wait,
            )
            time.sleep(wait)
    # Unreachable: every iteration either returns or raises.
    raise RuntimeError("retry_transient: unreachable")


def retry_read_or_degrade(
    fn: Callable[[], T],
    *,
    fallback: T | None = None,
    label: str = "alpaca_read",
    max_attempts: int = 4,
    base: float = 2.0,
    cap: float = 30.0,
) -> T | None:
    """Retry fn(); on final failure, log + return fallback (degrade gracefully).

    For read operations (get_account, get_all_positions, get_stock_bars,
    get_stock_snapshot): a final failure must NOT kill the cycle -- the caller
    proceeds with the fallback (None / stale value) and logs the degradation.
    """
    try:
        return retry_transient(fn, max_attempts=max_attempts, base=base, cap=cap)
    except Exception as exc:
        log.warning(
            "%s: final failure after %d attempts: %s -- degrading to fallback=%r",
            label, max_attempts, exc, fallback,
        )
        return fallback
