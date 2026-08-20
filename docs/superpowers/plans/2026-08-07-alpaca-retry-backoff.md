# Centralized retry/backoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a centralized `retry_transient` utility that retries Alpaca API calls on transient HTTP errors (429/500-504) with exponential backoff, jitter, and `Retry-After` respect; wire all Alpaca read call sites to retry-then-degrade, and all `submit_order` call sites to retry-then-alert (gated on §3 `client_order_id` idempotency).

**Architecture:** A new `src/util/retry.py` exposes `retry_transient(fn, *, max_attempts=4, base=2.0, cap=30.0)` — a synchronous wrapper (the alpaca-py SDK is sync; async callers use `asyncio.to_thread(retry_transient, ...)`). It parses `alpaca.common.exceptions.APIError` for `status_code` and the `Retry-After` header, retries on `{429, 500, 502, 503, 504}`, and fails immediately on `400/403/422`. Read call sites keep their existing try/except degrade paths (now only entered after retries are exhausted). `submit_order` call sites retry only after §3 (`docs/superpowers/plans/2026-08-07-alpaca-client-order-id.md`) ships broker-side idempotency via `client_order_id`, which makes a retried submit safe (the broker dedupes by `client_order_id`).

**Tech Stack:** Python 3.11, `alpaca-py` SDK (`alpaca.common.exceptions.APIError`), `pytest`, `unittest.mock`. Modeled on `src/connectors/gdelt_base.py` (exponential backoff) and `src/llm/client.py` (retry loop).

**Dependency note:** This plan is `blocked_by` the §3 `client_order_id` plan (`docs/superpowers/plans/2026-08-07-alpaca-client-order-id.md`) **for the `submit_order` retry portion only (Task 6)**. Tasks 1-5 (the `retry_transient` util + read-retry wiring) can ship independently and before §3. Do NOT start Task 6 until §3 is merged and deployed. Classification: `freeze-ok` (tooling) — permitted during freeze #171.

**Verification grounding (confirmed by reading the code):**
- `alpaca-py` SDK retry: `DEFAULT_RETRY_ATTEMPTS=3`, `DEFAULT_RETRY_WAIT_SECONDS=3`, `DEFAULT_RETRY_EXCEPTION_CODES=[429, 504]` (`alpaca/common/constants.py:11-13`) → 3×3s fixed, only 429/504, no `Retry-After`, no 502/503. A sustained 429 loses the whole cycle.
- `APIError` (`alpaca/common/exceptions.py:4-39`): `.status_code` is a property returning `http_error.response.status_code` (int); `.response` is a property returning `http_error.response` (a `requests.Response` with `.headers`, a `CaseInsensitiveDict`). `Retry-After` is read via `error.response.headers.get("Retry-After")`. Raised at `alpaca/common/rest.py:207` as `APIError(error, http_error)` where `http_error` is the `requests.HTTPError` from `response.raise_for_status()`.
- Reusable pattern: `src/connectors/gdelt_base.py:32-34` — `_GDELT_BACKOFF_BASE=2.0`, `_GDELT_BACKOFF_MAX=60.0`, `_GDELT_MAX_RETRIES=5`; backoff loop at `:73-95` (`wait = min(BASE * 2**attempt, MAX)`).
- Alert helper: `_fire_alert(notifier, message, level)` at `src/workers/portfolio_scheduler.py:180` and `src/workers/execution.py:275`; `notifier.send_alert(message, level=level)` is the async send.

---

## File Structure

- **Create:** `src/util/__init__.py` — empty package marker for the new `util` package.
- **Create:** `src/util/retry.py` — `retry_transient`, `retry_read_or_degrade`, and private helpers (`_is_retryable`, `_parse_retry_after`, `_compute_backoff`). Single responsibility: retry transient Alpaca API errors.
- **Create:** `tests/util/__init__.py` — empty package marker.
- **Create:** `tests/util/test_retry.py` — unit tests for `retry_transient` and `retry_read_or_degrade` (backoff schedule, `Retry-After`, jitter, `max_attempts`, retryable vs non-retryable, degrade branch).
- **Modify:** `src/workers/portfolio_scheduler.py` — wrap `get_account` (:2053), `get_all_positions` (:730, :2213), `get_stock_bars` (:2095), `get_stock_snapshot` (:2144), `submit_order` (:2949, :3836, :3869, :3946).
- **Modify:** `src/workers/performance.py` — wrap `get_account` (:707), `get_all_positions` (:708), `get_stock_bars` (:1634, :2221).
- **Modify:** `src/workers/risk_monitor_task.py` — wrap `get_account` (:107), `get_all_positions` (:108, :165).
- **Modify:** `src/workers/execution.py` — wrap `get_stock_bars` (:254), `get_account` (:455), `get_all_positions` (:501), `submit_order` (:735).
- **Modify:** `src/mobile_monitoring/builder.py` — wrap `get_account` (:462), `get_all_positions` (:463) via `asyncio.to_thread(retry_transient, ...)`.
- **Modify:** `src/portfolio/fractional_stop_orders.py` — wrap `submit_order` (:192).
- **Create:** `tests/workers/test_retry_wiring.py` — spy/integration tests asserting each modified call site routes through `retry_transient`.

---

### Task 1: `retry_transient` util in `src/util/retry.py`

**Files:**
- Create: `src/util/__init__.py`
- Create: `src/util/retry.py`
- Create: `tests/util/__init__.py`
- Create: `tests/util/test_retry.py`

- [ ] **Step 1: Create the package markers**

Create `src/util/__init__.py`:

```python
```

Create `tests/util/__init__.py`:

```python
```

- [ ] **Step 2: Write the failing tests for `retry_transient`**

Create `tests/util/test_retry.py`:

```python
"""Unit tests for src.util.retry — centralized Alpaca retry/backoff.

Tests use a real APIError with a mocked http_error.response so the .status_code
and .response.headers properties exercise the production code path.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from alpaca.common.exceptions import APIError

from src.util.retry import (
    _compute_backoff,
    _is_retryable,
    _parse_retry_after,
    retry_transient,
)


def _make_api_error(
    status_code: int,
    retry_after: str | None = None,
    body: str = "{}",
) -> APIError:
    """Build a real APIError with a mocked http_error.response.

    APIError.status_code reads http_error.response.status_code; APIError.response
    reads http_error.response (a requests.Response-like object with .headers).
    """
    response = MagicMock()
    response.status_code = status_code
    response.headers = {}
    if retry_after is not None:
        response.headers["Retry-After"] = retry_after
    response.text = body
    http_error = MagicMock()
    http_error.response = response
    return APIError(body, http_error)


# --- _is_retryable / _parse_retry_after -------------------------------------

@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_is_retryable_transient(status):
    assert _is_retryable(_make_api_error(status)) is True


@pytest.mark.parametrize("status", [400, 403, 422, 401, 404])
def test_is_retryable_non_retryable(status):
    assert _is_retryable(_make_api_error(status)) is False


def test_parse_retry_after_seconds():
    assert _parse_retry_after(_make_api_error(429, retry_after="10")) == 10.0


def test_parse_retry_after_missing():
    assert _parse_retry_after(_make_api_error(429)) is None


def test_parse_retry_after_non_numeric():
    assert _parse_retry_after(_make_api_error(429, retry_after="Wed, 21 Oct 2026")) is None


# --- retry_transient: success / retry / exhaust -----------------------------

def test_success_first_try_no_sleep(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    fn = MagicMock(return_value="ok")
    result = retry_transient(fn)

    assert result == "ok"
    fn.assert_called_once_with()
    assert sleeps == []


def test_retries_on_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    fn = MagicMock(side_effect=[_make_api_error(429), "ok"])
    result = retry_transient(fn)

    assert result == "ok"
    assert fn.call_count == 2
    assert len(sleeps) == 1


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retries_on_each_transient_status(monkeypatch, status):
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: None)
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    fn = MagicMock(side_effect=[_make_api_error(status), "ok"])
    assert retry_transient(fn) == "ok"
    assert fn.call_count == 2


@pytest.mark.parametrize("status", [400, 403, 422])
def test_no_retry_on_non_retryable_raises_immediately(monkeypatch, status):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))

    err = _make_api_error(status)
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn)
    fn.assert_called_once_with()
    assert sleeps == []


def test_exhausts_max_attempts_then_raises(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(429)
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn, max_attempts=4)
    assert fn.call_count == 4
    assert len(sleeps) == 3  # 3 sleeps between 4 attempts


def test_max_attempts_one_no_retry(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))

    err = _make_api_error(429)
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn, max_attempts=1)
    fn.assert_called_once_with()
    assert sleeps == []


def test_non_api_error_propagates_no_retry(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))

    fn = MagicMock(side_effect=ValueError("network blip"))
    with pytest.raises(ValueError):
        retry_transient(fn)
    fn.assert_called_once_with()
    assert sleeps == []


# --- backoff schedule + cap + Retry-After -----------------------------------

def test_backoff_schedule_exponential(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))
    # No jitter: random.uniform returns its upper bound so wait == raw.
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(429)
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn, max_attempts=4, base=2.0, cap=30.0)
    # attempts 0,1,2 sleep min(2*2^0,30)=2, min(2*2^1,30)=4, min(2*2^2,30)=8
    assert sleeps == [2.0, 4.0, 8.0]


def test_backoff_capped_at_cap(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(503)
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn, max_attempts=6, base=2.0, cap=30.0)
    # 2,4,8,16,30,30 — but only 5 sleeps for 6 attempts
    assert sleeps == [2.0, 4.0, 8.0, 16.0, 30.0]


def test_respects_retry_after_as_floor(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(429, retry_after="10")
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn, max_attempts=2, base=2.0, cap=30.0)
    # attempt 0: raw=max(2, 10)=10 -> sleep 10
    assert sleeps == [10.0]


def test_retry_after_overrides_short_backoff(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(429, retry_after="15")
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn, max_attempts=3, base=2.0, cap=30.0)
    # attempt 0: max(2, 15)=15; attempt 1: max(4, 15)=15
    assert sleeps == [15.0, 15.0]


def test_jitter_within_bounds(monkeypatch):
    """Full jitter: wait is uniform in [0, raw_backoff]."""
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: None)
    captured: list[tuple[float, float]] = []
    monkeypatch.setattr(
        "src.util.retry.random.uniform",
        lambda a, b: captured.append((a, b)) or (a + b) / 2,
    )

    err = _make_api_error(429)
    fn = MagicMock(side_effect=err)
    with pytest.raises(APIError):
        retry_transient(fn, max_attempts=3, base=2.0, cap=30.0)
    # attempt 0: uniform(0, 2); attempt 1: uniform(0, 4)
    assert captured == [(0.0, 2.0), (0.0, 4.0)]


def test_compute_backoff_unit():
    assert _compute_backoff(0, 2.0, 30.0, None) <= 2.0
    assert _compute_backoff(3, 2.0, 30.0, None) <= 30.0
    assert _compute_backoff(0, 2.0, 30.0, 10.0) <= 10.0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/util/test_retry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.util.retry'` (collection error).

- [ ] **Step 4: Implement `src/util/retry.py`**

Create `src/util/retry.py`:

```python
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
    if retry_after is not None: raw = max(raw, retry_after)
    wait = random.uniform(0, raw)   # full jitter
    """
    raw = min(base * (2 ** attempt), cap)
    if retry_after is not None:
        raw = max(raw, retry_after)
    return random.uniform(0.0, raw)


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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/util/test_retry.py -v`
Expected: PASS (all 20+ tests green).

- [ ] **Step 6: Commit**

```bash
git add src/util/__init__.py src/util/retry.py tests/util/__init__.py tests/util/test_retry.py
git commit -m "feat(retry): add centralized retry_transient util for Alpaca API errors

Exponential backoff + full jitter + Retry-After respect. Retries 429/500-504,
fails immediately on 400/403/422. Modeled on src/connectors/gdelt_base.py.
Part of #21. freeze-ok."
```

---

### Task 2: `retry_read_or_degrade` wrapper + test

`retry_read_or_degrade` was implemented in Task 1's `src/util/retry.py` (it is a thin wrapper over `retry_transient`). This task adds dedicated tests for the degrade branch.

**Files:**
- Modify: `tests/util/test_retry.py` (append tests)
- Test: `tests/util/test_retry.py`

- [ ] **Step 1: Write the failing tests for `retry_read_or_degrade`**

Append to `tests/util/test_retry.py` (after the existing imports, add `retry_read_or_degrade` to the import block at the top of the file):

Update the import block (top of file) to:

```python
from src.util.retry import (
    _compute_backoff,
    _is_retryable,
    _parse_retry_after,
    retry_read_or_degrade,
    retry_transient,
)
```

Append these tests at the end of the file:

```python
# --- retry_read_or_degrade ---------------------------------------------------

def test_degrade_returns_result_on_success(monkeypatch):
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: None)
    fn = MagicMock(return_value={"equity": 100.0})
    result = retry_read_or_degrade(fn, label="get_account")
    assert result == {"equity": 100.0}


def test_degrade_returns_fallback_on_final_fail(monkeypatch):
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: None)
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(429)
    fn = MagicMock(side_effect=err)
    result = retry_read_or_degrade(fn, fallback=None, label="get_account", max_attempts=2)
    assert result is None
    assert fn.call_count == 2


def test_degrade_returns_custom_fallback(monkeypatch):
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: None)
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(503)
    fn = MagicMock(side_effect=err)
    stale = {"equity": 99.0, "stale": True}
    result = retry_read_or_degrade(fn, fallback=stale, label="get_account", max_attempts=2)
    assert result is stale


def test_degrade_logs_on_failure(monkeypatch, caplog):
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: None)
    monkeypatch.setattr("src.util.retry.random.uniform", lambda a, b: b)

    err = _make_api_error(429)
    fn = MagicMock(side_effect=err)
    with caplog.at_level(logging.WARNING, logger="src.util.retry"):
        retry_read_or_degrade(fn, fallback=None, label="get_account", max_attempts=2)
    assert any("get_account" in r.getMessage() and "degrading" in r.getMessage() for r in caplog.records)


def test_degrade_non_retryable_returns_fallback_fast(monkeypatch):
    """A 422 is non-retryable: retry_transient raises immediately, degrade returns fallback."""
    sleeps: list[float] = []
    monkeypatch.setattr("src.util.retry.time.sleep", lambda s: sleeps.append(s))

    err = _make_api_error(422)
    fn = MagicMock(side_effect=err)
    result = retry_read_or_degrade(fn, fallback=None, label="get_account")
    assert result is None
    fn.assert_called_once_with()
    assert sleeps == []
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/util/test_retry.py -v -k degrade`
Expected: PASS (5 degrade tests green; `retry_read_or_degrade` is already implemented in Task 1).

- [ ] **Step 3: Commit**

```bash
git add tests/util/test_retry.py
git commit -m "test(retry): cover retry_read_or_degrade success/fallback/log branches

Part of #21. freeze-ok."
```

---

### Task 3: Wire `get_account` reads

Wrap every `get_account` call site with `retry_transient`. The existing try/except at each site already degrades (returns error dict / None / 0.0 / stats); wrapping with `retry_transient` means the degrade path fires only after retries are exhausted. Use `retry_transient(trading_client.get_account)` (no-arg bound method).

**Files:**
- Modify: `src/workers/portfolio_scheduler.py:2053` (add import near top + wrap call)
- Modify: `src/workers/performance.py:707` (add import + wrap call)
- Modify: `src/workers/risk_monitor_task.py:107` (add import + wrap call)
- Modify: `src/workers/execution.py:455` (add import + wrap call)
- Modify: `src/mobile_monitoring/builder.py:462` (add import + wrap via `asyncio.to_thread`)
- Test: `tests/workers/test_retry_wiring.py` (Create)

- [ ] **Step 1: Write the failing wiring tests**

Create `tests/workers/test_retry_wiring.py`:

```python
"""Wiring tests: assert each Alpaca read call site routes through retry_transient.

These are spy tests: patch retry_transient in the target module to a recording
stub, invoke the function, and assert the stub was called with the broker read.
This verifies the wiring without a live Alpaca call.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _spy_retry(monkeypatch, module_path):
    """Patch retry_transient in module_path to a spy that delegates to fn()."""
    calls: list = []

    def spy(fn, **kwargs):
        calls.append((fn, kwargs))
        return fn()

    monkeypatch.setattr(module_path, "retry_transient", spy)
    return calls


# --- get_account wiring ------------------------------------------------------

def test_risk_monitor_get_account_uses_retry(monkeypatch):
    from src.workers import risk_monitor_task
    calls = _spy_retry(monkeypatch, "src.workers.risk_monitor_task")

    client = MagicMock()
    acct = MagicMock()
    acct.equity = "100000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []

    equity, exposure = risk_monitor_task._fetch_account_state(client)
    assert equity == 100000.0
    assert exposure == 0.0
    # retry_transient was invoked for get_account (and get_all_positions).
    assert any(c[0] == client.get_account for c in calls)


def test_execution_get_account_uses_retry(monkeypatch):
    from src.workers import execution
    calls = _spy_retry(monkeypatch, "src.workers.execution")

    client = MagicMock()
    acct = MagicMock()
    acct.portfolio_value = "100000"
    acct.last_equity = "99000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []

    redis = MagicMock()
    redis.is_killswitch_active.return_value = False
    redis.read_sentiment.return_value = None  # no signal -> skip symbol, clean return
    regime = MagicMock()
    regime.multiplier = 1.0
    redis.get_regime.return_value = regime
    redis.get_feedback_entry_threshold.return_value = None
    redis.get_feedback_regime_scale.return_value = None
    notifier = MagicMock()
    notifier.send_alert = MagicMock()

    client.get_orders.return_value = []
    stats = execution.run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock(), notifier=notifier)
    assert any(c[0] == client.get_account for c in calls)


def test_performance_broker_mtm_uses_retry(monkeypatch):
    from src.workers import performance
    calls = _spy_retry(monkeypatch, "src.workers.performance")

    client = MagicMock()
    acct = MagicMock()
    acct.equity = "100000"
    acct.last_equity = "99000"
    acct.portfolio_value = "100000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []
    client.get_portfolio_history.return_value = MagicMock(profit_loss=[])

    result = performance._broker_mtm_snapshot(client)
    assert any(c[0] == client.get_account for c in calls)


def test_mobile_snapshot_get_account_uses_retry(monkeypatch):
    """MobileSnapshotBuilder wraps get_account via asyncio.to_thread(retry_transient, ...)."""
    import asyncio
    from src.mobile_monitoring import builder
    calls = _spy_retry(monkeypatch, "src.mobile_monitoring.builder")

    # Bypass __init__ (needs pool/redis); set only the attribute _broker_snapshot reads.
    b = builder.MobileSnapshotBuilder.__new__(builder.MobileSnapshotBuilder)
    b.alpaca = MagicMock()
    b.alpaca.get_account.return_value = MagicMock(equity="100", last_equity="99", cash="10")
    b.alpaca.get_all_positions.return_value = []

    account, positions = asyncio.run(b._broker_snapshot([]))
    assert account is not None
    assert any(c[0] == b.alpaca.get_account for c in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/workers/test_retry_wiring.py -v -k get_account`
Expected: FAIL — `retry_transient` is not yet imported/used at the call sites, so the spy is never called (`assert any(...) is False`).

- [ ] **Step 3: Wire `get_account` in `src/workers/risk_monitor_task.py`**

Add the import. At the top of `src/workers/risk_monitor_task.py`, after the existing `from src.config import config` line inside `_fetch_account_state` (around line 99), the function already imports `TradingClient` and `config` locally. Add a module-level import near the existing top-of-file imports. Find the first `from src.` import line in the file and add after it:

```python
from src.util.retry import retry_transient
```

Modify `src/workers/risk_monitor_task.py:107` — replace:

```python
        equity = float(client.get_account().equity)
        gross = sum(abs(float(p.market_value)) for p in client.get_all_positions())
```

with:

```python
        equity = float(retry_transient(client.get_account).equity)
        gross = sum(abs(float(p.market_value)) for p in retry_transient(client.get_all_positions))
```

Modify `src/workers/risk_monitor_task.py:165` — replace:

```python
            p.symbol: abs(float(p.market_value)) for p in client.get_all_positions()
```

with:

```python
            p.symbol: abs(float(p.market_value)) for p in retry_transient(client.get_all_positions)
```

- [ ] **Step 4: Wire `get_account` in `src/workers/performance.py`**

Add at the top of `src/workers/performance.py`, after the first `from src.` import line:

```python
from src.util.retry import retry_transient
```

Modify `src/workers/performance.py:707` — replace:

```python
        acct = trading_client.get_account()
        positions = trading_client.get_all_positions()
```

with:

```python
        acct = retry_transient(trading_client.get_account)
        positions = retry_transient(trading_client.get_all_positions)
```

- [ ] **Step 5: Wire `get_account` in `src/workers/execution.py`**

Add at the top of `src/workers/execution.py`, after the first `from src.` import line:

```python
from src.util.retry import retry_transient
```

Modify `src/workers/execution.py:455` — replace:

```python
        account = trading_client.get_account()
```

with:

```python
        account = retry_transient(trading_client.get_account)
```

- [ ] **Step 6: Wire `get_account` in `src/workers/portfolio_scheduler.py`**

Add at the top of `src/workers/portfolio_scheduler.py`, after the `from src.notifications.base import AlertLevel` line (line 24):

```python
from src.util.retry import retry_transient
```

Modify `src/workers/portfolio_scheduler.py:2053` — replace:

```python
        account = trading_client.get_account()
```

with:

```python
        account = retry_transient(trading_client.get_account)
```

- [ ] **Step 7: Wire `get_account` in `src/mobile_monitoring/builder.py`**

Add at the top of `src/mobile_monitoring/builder.py`, after the first `from src.` import line:

```python
from src.util.retry import retry_transient
```

Modify `src/mobile_monitoring/builder.py:461-464` — replace:

```python
            account, positions = await asyncio.gather(
                asyncio.to_thread(self.alpaca.get_account),
                asyncio.to_thread(self.alpaca.get_all_positions),
            )
```

with:

```python
            account, positions = await asyncio.gather(
                asyncio.to_thread(retry_transient, self.alpaca.get_account),
                asyncio.to_thread(retry_transient, self.alpaca.get_all_positions),
            )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/workers/test_retry_wiring.py -v -k get_account`
Expected: PASS (4 tests green — each call site now routes through `retry_transient`).

Run the full retry suite to confirm no regression:
Run: `pytest tests/util/test_retry.py tests/workers/test_retry_wiring.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/workers/risk_monitor_task.py src/workers/performance.py src/workers/execution.py src/workers/portfolio_scheduler.py src/mobile_monitoring/builder.py tests/workers/test_retry_wiring.py
git commit -m "feat(retry): wrap get_account reads with retry_transient

get_account at portfolio_scheduler:2053, performance:707, risk_monitor_task:107,
execution:455, mobile_monitoring/builder:462 now retry on 429/500-504 before
the existing degrade path fires. Part of #21. freeze-ok."
```

---

### Task 4: Wire `get_all_positions` reads

Wrap every `get_all_positions` call site. Note: `risk_monitor_task.py:108` and `:165` were already wrapped in Task 3 Step 3 (they sit on the same lines as `get_account`); this task covers the remaining sites.

**Files:**
- Modify: `src/workers/portfolio_scheduler.py:730` and `:2213`
- Modify: `src/workers/execution.py:501`
- (performance.py:708 and mobile_monitoring/builder.py:463 already wired in Task 3)
- (risk_monitor_task.py:108, :165 already wired in Task 3)
- Test: `tests/workers/test_retry_wiring.py` (append)

- [ ] **Step 1: Write the failing wiring tests**

Append to `tests/workers/test_retry_wiring.py`:

```python
# --- get_all_positions wiring ------------------------------------------------

def test_portfolio_scheduler_positions_load_uses_retry(monkeypatch):
    """The protective-stop sync path (portfolio_scheduler:730) routes through retry_transient."""
    from src.workers import portfolio_scheduler
    calls = _spy_retry(monkeypatch, "src.workers.portfolio_scheduler")

    client = MagicMock()
    client.get_all_positions.return_value = []
    client.get_orders.return_value = []

    # Call the protective-stop sync helper directly.
    from src.portfolio.stop_policy import StopPolicy
    summary = portfolio_scheduler._sync_fractional_protective_stops(
        client, StopPolicy({"stop_loss_mode": "fixed", "stop_loss": 0.0,
                            "broker_disaster_stop": {"multiplier": 1.5, "sigma_multiple": 5.0,
                                                     "floor_pct": 0.12, "cap_pct": 0.20}}),
        cycle_ts=__import__("datetime").datetime(2026, 8, 7, 15, 0, tzinfo=__import__("datetime").timezone.utc),
    )
    assert any(c[0] == client.get_all_positions for c in calls)


def test_execution_get_all_positions_uses_retry(monkeypatch):
    from src.workers import execution
    calls = _spy_retry(monkeypatch, "src.workers.execution")

    client = MagicMock()
    acct = MagicMock()
    acct.portfolio_value = "100000"
    acct.last_equity = "99000"
    client.get_account.return_value = acct
    client.get_all_positions.return_value = []
    client.get_orders.return_value = []

    redis = MagicMock()
    redis.is_killswitch_active.return_value = False
    redis.read_sentiment.return_value = None  # no signal -> skip symbol, clean return
    regime = MagicMock()
    regime.multiplier = 1.0
    redis.get_regime.return_value = regime
    redis.get_feedback_entry_threshold.return_value = None
    redis.get_feedback_regime_scale.return_value = None
    notifier = MagicMock()
    notifier.send_alert = MagicMock()

    execution.run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock(), notifier=notifier)
    assert any(c[0] == client.get_all_positions for c in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/workers/test_retry_wiring.py -v -k get_all_positions`
Expected: FAIL — `get_all_positions` at `:730` and `:501` not yet wrapped.

- [ ] **Step 3: Wire `get_all_positions` in `src/workers/portfolio_scheduler.py:730`**

The import was added in Task 3 Step 6. Modify `src/workers/portfolio_scheduler.py:730` — replace:

```python
        positions = trading_client.get_all_positions()
```

with:

```python
        positions = retry_transient(trading_client.get_all_positions)
```

- [ ] **Step 4: Wire `get_all_positions` in `src/workers/portfolio_scheduler.py:2213`**

Modify `src/workers/portfolio_scheduler.py:2213` — replace:

```python
        alpaca_positions = trading_client.get_all_positions()
```

with:

```python
        alpaca_positions = retry_transient(trading_client.get_all_positions)
```

- [ ] **Step 5: Wire `get_all_positions` in `src/workers/execution.py:501`**

The import was added in Task 3 Step 5. Modify `src/workers/execution.py:500-502` — replace:

```python
        open_positions = {
            p.symbol: p for p in trading_client.get_all_positions()
        }
```

with:

```python
        open_positions = {
            p.symbol: p for p in retry_transient(trading_client.get_all_positions)
        }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/workers/test_retry_wiring.py -v -k get_all_positions`
Expected: PASS (2 new tests green; the risk_monitor_task and performance and mobile sites were covered in Task 3).

Run: `pytest tests/util/test_retry.py tests/workers/test_retry_wiring.py -v`
Expected: PASS (no regression).

- [ ] **Step 7: Commit**

```bash
git add src/workers/portfolio_scheduler.py src/workers/execution.py tests/workers/test_retry_wiring.py
git commit -m "feat(retry): wrap get_all_positions reads with retry_transient

get_all_positions at portfolio_scheduler:730,2213 and execution:501 now retry
on 429/500-504 before the existing degrade path fires. Part of #21. freeze-ok."
```

---

### Task 5: Wire `get_stock_bars` and `get_stock_snapshot` reads

Wrap every `get_stock_bars` and the `get_stock_snapshot` call site. These take a request argument, so use `retry_transient(lambda: data_client.get_stock_bars(request))`.

**Files:**
- Modify: `src/workers/portfolio_scheduler.py:2095` and `:2144`
- Modify: `src/workers/performance.py:1634` and `:2221`
- Modify: `src/workers/execution.py:254`
- Test: `tests/workers/test_retry_wiring.py` (append)

- [ ] **Step 1: Write the failing wiring tests**

Append to `tests/workers/test_retry_wiring.py`:

```python
# --- get_stock_bars / get_stock_snapshot wiring ------------------------------

def test_execution_build_market_cache_uses_retry(monkeypatch):
    """execution._build_market_cache (get_stock_bars at :254) routes through retry_transient."""
    from src.workers import execution
    calls = _spy_retry(monkeypatch, "src.workers.execution")

    data_client = MagicMock()
    bars_df = MagicMock()
    bars_df.empty = True
    data_client.get_stock_bars.return_value = MagicMock(df=bars_df)

    execution._build_market_cache(["AAPL"], data_client)
    assert any(callable(c[0]) for c in calls)
    data_client.get_stock_bars.assert_called()


def test_performance_forward_return_worker_uses_retry(monkeypatch):
    """run_forward_return_worker (get_stock_bars at :1634) routes through retry_transient.

    The worker's local imports (psycopg2, PostgreSQLStore, StockHistoricalDataClient)
    are patched at their source so the function reaches the bars fetch with one
    pending signal row, then the spy asserts retry_transient was invoked.
    """
    from datetime import datetime, timezone
    from src.workers import performance
    calls = _spy_retry(monkeypatch, "src.workers.performance")

    # Credential check: config.ALPACA_API_KEY / ALPACA_SECRET_KEY must be truthy.
    monkeypatch.setattr(performance.config, "ALPACA_API_KEY", "test-key")
    monkeypatch.setattr(performance.config, "ALPACA_SECRET_KEY", "test-secret")

    # psycopg2.connect -> mock connection; PostgreSQLStore -> mock with one pending row.
    monkeypatch.setattr("psycopg2.connect", lambda *a, **kw: MagicMock())
    pg_mock = MagicMock()
    pg_mock.fetch_signals_pending_forward_return.return_value = [
        (1, "AAPL", datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc))
    ]
    monkeypatch.setattr("src.store.pg_store.PostgreSQLStore", lambda **kw: pg_mock)

    # StockHistoricalDataClient -> mock returning an empty DataFrame (skip + return).
    data_client_mock = MagicMock()
    bars_df = MagicMock()
    bars_df.empty = True
    bars_df.index.get_level_values.return_value = []
    data_client_mock.get_stock_bars.return_value = MagicMock(df=bars_df)
    monkeypatch.setattr(
        "alpaca.data.historical.StockHistoricalDataClient", lambda **kw: data_client_mock
    )

    performance.run_forward_return_worker()
    assert any(callable(c[0]) for c in calls)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/workers/test_retry_wiring.py -v -k "stock_bars or market_cache or forward_returns"`
Expected: FAIL — `get_stock_bars` not yet wrapped.

- [ ] **Step 3: Wire `get_stock_bars` in `src/workers/portfolio_scheduler.py:2095`**

The import was added in Task 3 Step 6. Modify `src/workers/portfolio_scheduler.py:2095` — replace:

```python
        raw = data_client.get_stock_bars(request).df
```

with:

```python
        raw = retry_transient(lambda: data_client.get_stock_bars(request)).df
```

- [ ] **Step 4: Wire `get_stock_snapshot` in `src/workers/portfolio_scheduler.py:2144`**

Modify `src/workers/portfolio_scheduler.py:2144` — replace:

```python
        snapshots = data_client.get_stock_snapshot(snap_req)
```

with:

```python
        snapshots = retry_transient(lambda: data_client.get_stock_snapshot(snap_req))
```

- [ ] **Step 5: Wire `get_stock_bars` in `src/workers/performance.py:1634`**

The import was added in Task 3 Step 4. Modify `src/workers/performance.py:1634` — replace:

```python
                bars_df = data_client.get_stock_bars(req).df
```

with:

```python
                bars_df = retry_transient(lambda: data_client.get_stock_bars(req)).df
```

- [ ] **Step 6: Wire `get_stock_bars` in `src/workers/performance.py:2221`**

Modify `src/workers/performance.py:2221` — replace:

```python
                bars_df = data_client.get_stock_bars(req).df
```

with:

```python
                bars_df = retry_transient(lambda: data_client.get_stock_bars(req)).df
```

- [ ] **Step 7: Wire `get_stock_bars` in `src/workers/execution.py:254`**

The import was added in Task 3 Step 5. Modify `src/workers/execution.py:254` — replace:

```python
        bars_df = data_client.get_stock_bars(request).df
```

with:

```python
        bars_df = retry_transient(lambda: data_client.get_stock_bars(request)).df
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/workers/test_retry_wiring.py -v -k "stock_bars or market_cache or forward_returns"`
Expected: PASS (2 new tests green).

Run the full suite:
Run: `pytest tests/util/test_retry.py tests/workers/test_retry_wiring.py -v`
Expected: PASS (no regression).

- [ ] **Step 9: Commit**

```bash
git add src/workers/portfolio_scheduler.py src/workers/performance.py src/workers/execution.py tests/workers/test_retry_wiring.py
git commit -m "feat(retry): wrap get_stock_bars + get_stock_snapshot reads with retry_transient

get_stock_bars at portfolio_scheduler:2095, performance:1634,2221, execution:254
and get_stock_snapshot at portfolio_scheduler:2144 now retry on 429/500-504
before the existing degrade path fires. Part of #21. freeze-ok."
```

---

### Task 6 — SUPERSEDED 2026-08-20 (eseguito, ma non come scritto qui)

> **Questa task era stale al momento di eseguirla.** Il testo originale e' conservato
> in git (`git show 43c51aa:docs/superpowers/plans/2026-08-07-alpaca-retry-backoff.md`).
> Il gate `blocked_by #201` e' sciolto: lo spike sandbox del 2026-08-20 ha misurato
> `dedup_confirmed`. Sotto, cosa e' cambiato e cosa e' stato implementato davvero.

**Tre cose che il piano del 07-08 dava per assodate e che non reggevano piu':**

1. **I sei siti submit non chiamano piu' `trading_client.submit_order`.** Dopo #313
   (mergiata 2026-08-18) passano tutti da `submit_order_with_coid_fallback`
   (`src/portfolio/order_id.py`). Avvolgere i sei siti con `retry_transient`, come
   prescrivevano gli Step 3-8, avrebbe messo il retry al livello sbagliato: la
   sicurezza del retry dipende dal `client_order_id`, che solo il choke point conosce.

2. **Il rifiuto per duplicato e' 422, non 409, ed e' un esito da risolvere, non un
   errore.** Misura diretta dello spike #201: HTTP 422, codice Alpaca `40010001`
   `client_order_id must be unique`. `retry_transient` classifica 422 come fail-fast,
   che in generale e' corretto; ma un 422-dedup che arriva *dopo* un nostro tentativo
   significa "l'ordine e' gia' passato". Trattarlo come errore secco farebbe segnalare
   un fallimento su un ordine realmente eseguito.

3. **`notifier` non e' in scope ai siti scheduler.** Lo Step 9 affermava che
   "notifier, `_fire_alert` e `AlertLevel` sono tutti in scope" ai quattro siti:
   `_submit_portfolio_orders` e `_submit_reversal_force_sells` ricevono
   `_on_broker_reject` / `on_broker_reject`, non `notifier`. L'allarme di
   esaurimento tentativi passa quindi dall'hook `on_alert` gia' cablato dal choke
   point, che ai siti scheduler finisce sull'evento durevole mobile e in
   `execution.py` su Telegram.

**Implementato (commit `ecf360f`, `58a4f2d`):** il retry vive dentro
`submit_order_with_coid_fallback`, un solo posto per tutti e sei i siti.

- Retry solo se la richiesta porta un `client_order_id`. Senza chiave di idempotenza
  il submit resta a tentativo singolo: un retry potrebbe produrre due fill.
- 422/`40010001` **dopo** un nostro tentativo → `get_order_by_client_id` → si
  restituisce l'ordine esistente. Se la lookup non trova o non risponde, si rilancia
  l'errore originale: mai restituire un ordine non confermato.
- 422/`40010001` **al primo** tentativo → propaga invariato. Non l'abbiamo causato
  noi (e' un duplicato di un ciclo precedente), e cosi' il percorso senza retry —
  la quasi totalita' dei submit — ha esattamente il comportamento di oggi.
- Il fallback di formato (submit senza la chiave) resta a tentativo singolo: butta
  via l'idempotenza, ritentarlo creerebbe un secondo ordine.
- Esaurimento tentativi → log ERROR + `on_alert` + re-raise nei gestori esistenti.

**Test:** `tests/portfolio/test_order_id_submit_retry.py` (11), piu' i 16 di
`tests/portfolio/test_order_id.py` invariati. Un test blocca l'invariante del choke
point: nessun modulo di `src/` oltre `order_id.py` puo' chiamare `submit_order`.

**Fuori scope, con motivo:** il budget di attesa per ciclo (fino a ~14s per submit
con i default 4/2.0/30.0) non e' stato toccato — sarebbe una taratura, vietata dal
freeze #171.

### Task 7: Plan-level notes (no code)

**Files:** None (documentation only).

- [ ] **Step 1: Confirm freeze + dependency classification**

This plan is `freeze-ok` (tooling — no live-behavior tuning). It is permitted during freeze #171 (03/08 → 28/09).

- [ ] **Step 2: Confirm the `blocked_by` dependency is recorded**

The `submit_order` retry portion (Task 6) is `blocked_by` the §3 `client_order_id` plan (`docs/superpowers/plans/2026-08-07-alpaca-client-order-id.md`). Tasks 1-5 (read-retry) ship independently. The Wayfinder issue for this plan must carry `blocked_by` the §3 issue. Do not merge Task 6 until §3 is merged and deployed.

- [ ] **Step 3: Note the scope exclusion (non-Alpaca retry)**

Retry of non-Alpaca calls (LLM, GDELT) is out of scope — those already have their own backoff (`src/llm/client.py`, `src/connectors/gdelt_base.py`). Network errors (non-`APIError`) propagate immediately through `retry_transient`; the existing call-site degrade paths handle them. This is a deliberate YAGNI scope decision; if network-error retry is later needed, extend `_is_retryable` to also match `requests.exceptions.ConnectionError`/`Timeout` in a separate change.

---

## Self-Review

**1. Spec coverage (spec §4 + Cross-cutting):**
- "New `src/util/retry.py`: `retry_transient(fn, *, max_attempts=4, base=2.0, cap=30.0)` — exponential backoff + jitter + respect `Retry-After` header, retry on 429/500-504" → Task 1 (signature matches exactly; `_RETRYABLE_STATUS = {429, 500, 502, 503, 504}`; `_compute_backoff` does exponential + full jitter + Retry-After floor).
- "Wrap reads (`get_account`, `get_all_positions`, `get_stock_bars`, `get_snapshot`) → final failure: degrade gracefully (return None/stale + log), do NOT kill the cycle" → Tasks 3, 4, 5 (every read call site wrapped; existing try/except degrade paths preserved, now fire only after retries).
- "Wrap `submit_order` → retry ONLY after §3; final failure: fail the cycle + Telegram alert (never silent, never double-submit)" → Task 6 (gated on §3; final-fail `_fire_alert` + re-raise; no-double-submit guaranteed by §3 `client_order_id` dedup, asserted in `test_submit_order_retries_on_429_then_succeeds`).
- "`APIError` parsed for status + `Retry-After`; non-retryable (400/403/422) → fail immediately" → Task 1 (`_is_retryable`, `_parse_retry_after`; `test_no_retry_on_non_retryable_raises_immediately`).
- "Reusable patterns: `gdelt_base.py`, `llm/client.py`" → Task 1 modeled on `gdelt_base` backoff; `llm/client.py` retry loop pattern reflected in `retry_transient`.
- "Testing: unit test backoff schedule + `Retry-After` respect (mock `APIError`); test read-degrade vs submit-fail branches" → Tasks 1-2 (backoff schedule, Retry-After, jitter, max_attempts, retryable/non-retryable, degrade branch) + Task 6 (submit-fail branch, no-double-submit).
- "Dependency: §4 Wayfinder issue is `blocked_by` the §3 issue" → Header + Task 6 + Task 7.
- "Cross-cutting: `freeze-ok`" → Header + Task 7.

**2. Placeholder scan:** No "TBD"/"TODO"/"add error handling"/"similar to Task N" — every step has complete code, exact paths, line numbers, and commands. Every test is written in full.

**3. Type consistency:** `retry_transient(fn, *, max_attempts=4, base=2.0, cap=30.0)` — signature is identical in the implementation (Task 1 Step 4), the read-wrapping (Tasks 3-5 use `retry_transient(client.method)` / `retry_transient(lambda: ...)`), and the submit-wrapping (Task 6 uses `retry_transient(lambda: ...)`). `retry_read_or_degrade(fn, *, fallback=None, label="alpaca_read", max_attempts=4, base=2.0, cap=30.0)` is defined in Task 1 and tested in Task 2 with the same signature. `_make_api_error(status_code, retry_after, body)` is used consistently across Tasks 1, 2, and 6.