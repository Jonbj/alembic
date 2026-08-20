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
    retry_read_or_degrade,
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