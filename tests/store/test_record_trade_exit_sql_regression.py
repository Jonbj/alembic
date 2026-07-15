"""Real-Postgres regression test for record_trade_exit's exit_order_ids append.

Why this exists: the codebase's pg_store tests use MOCK cursors — they assert on
the SQL *string* but never EXECUTE it. That let a real SQL-semantics bug ship
(WS-5 fix-back, 2026-07-14): the exit_order_ids append used
`COALESCE(exit_order_ids, ARRAY[]::text[]) || %s`, and on this Postgres
`text[] || text` resolves to `array_cat`, which tries to cast the scalar string
to `text[]` and throws 'malformed array literal'. The first SELL on a fresh
position (exit_order_ids NULL) raised → (pre-B33) broke the whole trade-write
loop → 5 Alpaca fills unrecorded (2026-07-15 14:22 incident).

This test EXECUTES the exact append fragment against a live Postgres so the
bug cannot recur silently. It is side-effect-free (pure SELECT, no table
touched). Skips if no Postgres is reachable (CI without DB) — run on-demand
against the dev/live DB to verify SQL changes before deploying to the hot path:

    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
        .venv/bin/python -m pytest tests/store/test_record_trade_exit_sql_regression.py -v
"""
from __future__ import annotations

import pytest

try:
    import psycopg2  # noqa: F401
    _HAS_PSYCOPG2 = True
except Exception:
    _HAS_PSYCOPG2 = False


def _connect():
    """Try to connect to a real Postgres; return a connection or None."""
    if not _HAS_PSYCOPG2:
        return None
    import os
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        return psycopg2.connect(url)
    except Exception:
        return None


# The exact append fragment used by record_trade_exit (NULL exit_order_ids case
# — the one that threw). Uses array_append (the fix). Verifies it produces a
# valid text array, dedups, and appends a second tranche.
_APPEND_SQL = (
    "SELECT CASE "
    "  WHEN COALESCE(array_position(COALESCE(%s, ARRAY[]::text[]), %s), 0) = 0 "
    "  THEN array_append(COALESCE(%s, ARRAY[]::text[]), %s) "
    "  ELSE COALESCE(%s, ARRAY[]::text[]) "
    "END"
)


def test_exit_order_ids_append_first_tranche_null_array():
    """Fresh position (exit_order_ids NULL): append must yield a 1-element array.

    Pre-fix (`|| %s`) this raised 'malformed array literal' on real Postgres.
    """
    conn = _connect()
    if conn is None:
        pytest.skip("no live Postgres reachable (set DATABASE_URL to run)")
    try:
        with conn.cursor() as cur:
            cur.execute(_APPEND_SQL, (None, "oid-A", None, "oid-A", None))
            row = cur.fetchone()
        assert list(row[0]) == ["oid-A"], f"first tranche append wrong: {row[0]!r}"
    finally:
        conn.rollback()
        conn.close()


def test_exit_order_ids_append_second_tranche_and_dedup():
    """Second tranche appends a new id; repeating an existing id does not duplicate."""
    conn = _connect()
    if conn is None:
        pytest.skip("no live Postgres reachable (set DATABASE_URL to run)")
    try:
        with conn.cursor() as cur:
            # Existing ['oid-A'], append 'oid-B' → ['oid-A','oid-B']
            cur.execute(_APPEND_SQL, (["oid-A"], "oid-B", ["oid-A"], "oid-B", ["oid-A"]))
            assert list(cur.fetchone()[0]) == ["oid-A", "oid-B"]

            # Existing ['oid-A','oid-B'], append 'oid-A' again → dedup, unchanged
            cur.execute(
                _APPEND_SQL,
                (["oid-A", "oid-B"], "oid-A", ["oid-A", "oid-B"], "oid-A", ["oid-A", "oid-B"]),
            )
            assert list(cur.fetchone()[0]) == ["oid-A", "oid-B"], "dedup failed"
    finally:
        conn.rollback()
        conn.close()


def test_old_concat_form_reproduces_the_bug():
    """Guard: the OLD `text[] || text` form MUST raise on this Postgres.

    If this ever stops raising, the operator-resolution changed and the fix may
    need revisiting. Documents the bug concretely so it isn't re-introduced.
    """
    conn = _connect()
    if conn is None:
        pytest.skip("no live Postgres reachable (set DATABASE_URL to run)")
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InvalidTextRepresentation):
                cur.execute("SELECT COALESCE(NULL::text[], ARRAY[]::text[]) || %s", ("oid-A",))
    finally:
        conn.rollback()
        conn.close()