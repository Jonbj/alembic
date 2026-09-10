"""F-056: fetch_signals_for_cycle must not let a stale ensemble signal
permanently shadow a fresher, stronger fallback signal within the S4 96h
lookback window. See docs/ALPHA_MISS_REPORT_2026-08-13.md §3/§8."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from src.store.pg_store import PostgreSQLStore


# ── Unit tests (mocked cursor): SQL structure and parameter wiring ──────────


def test_ensemble_priority_hours_defaults_to_hours_when_not_passed():
    """None (unset) must reproduce the pre-fix behavior: the ensemble-priority
    bucket spans the entire lookback window, i.e. ensemble_priority_hours == hours.
    Existing callers that don't pass the new kwarg must be unaffected."""
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.fetch_signals_for_cycle(hours=96, symbols=["NFLX"])
    params = cursor.execute.call_args[0][1]
    # 4th positional param is ensemble_priority_hours; must equal hours (96).
    assert params[3] == "96"


def test_ensemble_priority_hours_explicit_value_is_passed_through():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.fetch_signals_for_cycle(
            hours=96, symbols=["NFLX"], ensemble_priority_hours=4,
        )
    params = cursor.execute.call_args[0][1]
    assert params[3] == "4"


def test_query_order_by_uses_time_bounded_ensemble_priority():
    query = PostgreSQLStore._FETCH_SIGNALS_FOR_CYCLE
    assert "ss.fallback_used = FALSE" in query
    assert "ss.generated_at >= NOW() - (%s || ' hours')::interval) DESC" in query
    # the OLD unconditional form must be gone
    assert "fallback_used ASC" not in query


# ── Integration tests (real DB): verify actual row-selection behavior ───────
#
# DISTINCT ON row selection happens inside Postgres, not in Python — a mocked
# cursor cannot verify which row a given ORDER BY actually picks. These tests
# insert real rows into sentiment_signals against DATABASE_URL and assert on
# what fetch_signals_for_cycle returns.


def _connect_or_skip() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    try:
        return psycopg2.connect(url)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Database unreachable: {exc}")


def _insert_signal(
    cur, symbol: str, score: float, fallback_used: bool, model_id: str,
    generated_at: datetime,
) -> None:
    cur.execute(
        """
        INSERT INTO sentiment_signals
            (symbol, score, confidence, model_id, fallback_used, generated_at)
        VALUES (%s, %s, 0.9, %s, %s, %s)
        ON CONFLICT (symbol, generated_at) DO UPDATE SET score = EXCLUDED.score
        """,
        (symbol, score, model_id, fallback_used, generated_at),
    )


def _cleanup(cur, symbol: str) -> None:
    cur.execute("DELETE FROM sentiment_signals WHERE symbol = %s", (symbol,))


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_fresh_ensemble_still_beats_fresh_fallback_amkr_case():
    """Regression guard for 10c7836: an ensemble signal followed 32 minutes
    later by a weak fallback must still win, as long as both are within
    ensemble_priority_hours. This is the ORIGINAL bug 10c7836 fixed — this
    fix must not reintroduce it."""
    conn = _connect_or_skip()
    symbol = "TEST_F056_AMKR"
    now = datetime.now(timezone.utc)
    ensemble_at = now - timedelta(hours=1)
    fallback_at = ensemble_at + timedelta(minutes=32)
    try:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            _insert_signal(cur, symbol, 0.638, False, "ensemble:test", ensemble_at)
            _insert_signal(cur, symbol, 0.009, True, "finbert", fallback_at)
            conn.commit()

        store = PostgreSQLStore(use_pool=False)
        results = store.fetch_signals_for_cycle(
            hours=96, symbols=[symbol], ensemble_priority_hours=4,
        )
        assert len(results) == 1
        assert results[0].score == pytest.approx(0.638)
        assert results[0].fallback_used is False
    finally:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            conn.commit()
        conn.close()


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_stale_ensemble_no_longer_shadows_fresh_strong_fallback():
    """F-056: an ensemble signal older than ensemble_priority_hours must NOT
    block a fresher fallback signal, even though it is still inside the wider
    `hours` lookback window (96h). Reproduces the NFLX 2026-08-13 case: weak
    ensemble ~5h before the fetch, strong fallback ~1h before the fetch."""
    conn = _connect_or_skip()
    symbol = "TEST_F056_NFLX"
    now = datetime.now(timezone.utc)
    ensemble_at = now - timedelta(hours=5)  # older than ensemble_priority_hours=4
    fallback_at = now - timedelta(hours=1)  # fresh, and after the ensemble signal
    try:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            _insert_signal(cur, symbol, 0.138, False, "ensemble:test", ensemble_at)
            _insert_signal(
                cur, symbol, 0.36, True, "single:glm-5.2:cloud", fallback_at,
            )
            conn.commit()

        store = PostgreSQLStore(use_pool=False)
        results = store.fetch_signals_for_cycle(
            hours=96, symbols=[symbol], ensemble_priority_hours=4,
        )
        assert len(results) == 1
        assert results[0].score == pytest.approx(0.36)
        assert results[0].fallback_used is True
    finally:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            conn.commit()
        conn.close()


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_without_ensemble_priority_hours_old_behavior_is_unchanged():
    """Backward-compatibility guard: a caller that does NOT pass
    ensemble_priority_hours (i.e. every caller except the S4 entry path) must
    still get the pre-fix behavior — the old, weak ensemble signal wins
    regardless of how much fresher/stronger the fallback is. This is the same
    data as test_stale_ensemble_no_longer_shadows_fresh_strong_fallback above,
    but WITHOUT the new kwarg — the assertion is intentionally the opposite."""
    conn = _connect_or_skip()
    symbol = "TEST_F056_COMPAT"
    now = datetime.now(timezone.utc)
    ensemble_at = now - timedelta(hours=5)
    fallback_at = now - timedelta(hours=1)
    try:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            _insert_signal(cur, symbol, 0.138, False, "ensemble:test", ensemble_at)
            _insert_signal(
                cur, symbol, 0.36, True, "single:glm-5.2:cloud", fallback_at,
            )
            conn.commit()

        store = PostgreSQLStore(use_pool=False)
        results = store.fetch_signals_for_cycle(hours=96, symbols=[symbol])
        assert len(results) == 1
        assert results[0].score == pytest.approx(0.138)
        assert results[0].fallback_used is False
    finally:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            conn.commit()
        conn.close()


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_two_fallback_signals_recency_wins():
    """Edge case 1: neither row is non-fallback, so the priority bucket is
    FALSE for both — plain recency tie-break, unaffected by this fix."""
    conn = _connect_or_skip()
    symbol = "TEST_F056_2FB"
    now = datetime.now(timezone.utc)
    older_at = now - timedelta(hours=2)
    newer_at = now - timedelta(hours=1)
    try:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            _insert_signal(cur, symbol, 0.50, True, "finbert", older_at)
            _insert_signal(cur, symbol, -0.10, True, "single:gpt-oss:20b-cloud", newer_at)
            conn.commit()

        store = PostgreSQLStore(use_pool=False)
        results = store.fetch_signals_for_cycle(
            hours=96, symbols=[symbol], ensemble_priority_hours=4,
        )
        assert len(results) == 1
        assert results[0].score == pytest.approx(-0.10)
    finally:
        with conn.cursor() as cur:
            _cleanup(cur, symbol)
            conn.commit()
        conn.close()