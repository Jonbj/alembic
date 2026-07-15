"""Smoke tests for pg_store stop-loss helpers (requires live-like DB)."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg2
import pytest

from src.portfolio.stop_policy import FrozenStop, StopDecision
from src.store.pg_store import PostgreSQLStore


def _connect_or_skip() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set")
    try:
        return psycopg2.connect(url)
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Database unreachable: {exc}")


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_load_frozen_stop_round_trip() -> None:
    """open_trade with frozen_stop can be reloaded via load_frozen_stop."""
    store = PostgreSQLStore(use_pool=False)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    symbol = "TEST_STOP_1"
    frozen = FrozenStop(
        strategy="S4", mode="vol_scaled", vol_at_entry=0.025, sigma_eff=0.025,
        k=2.0, floor=0.03, cap=0.08, d_init=0.05, vol_source="bars_df",
    )
    try:
        store.open_trade(
            symbol=symbol, signal_id=123, decision_id=None,
            entry_order_id="test-order-1", entry_time=ts,
            entry_notional=1000.0, score=0.02, regime_mult=1.0,
            qty=10.0, signal_score=0.5, frozen_stop=frozen,
        )
        loaded = store.load_frozen_stop(symbol)
        assert loaded is not None
        assert loaded.strategy == "S4"
        assert loaded.mode == "vol_scaled"
        assert loaded.d_init == pytest.approx(0.05)
        assert loaded.vol_source == "bars_df"
    finally:
        # cleanup
        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM trades WHERE symbol = %s", (symbol,))
            conn.commit()
        conn.close()
        store.close()


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_fixed_mode_freezes_audit_fields() -> None:
    """Fixed mode still persists k/floor/cap/sigma on the trade row so the
    vol_scaled sizing gate has the full freeze-at-entry record later."""
    store = PostgreSQLStore(use_pool=False)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    symbol = "TEST_STOP_FIXED_AUDIT"
    frozen = FrozenStop(
        strategy="S1", mode="fixed", vol_at_entry=0.018, sigma_eff=0.018,
        k=3.5, floor=0.06, cap=0.12, d_init=0.02, vol_source="tier",
    )
    try:
        store.open_trade(
            symbol=symbol, signal_id=None, decision_id=None,
            entry_order_id="test-order-fixed-audit", entry_time=ts,
            entry_notional=1000.0, score=0.02, regime_mult=1.0,
            qty=10.0, signal_score=None, frozen_stop=frozen,
        )
        loaded = store.load_frozen_stop(symbol)
        assert loaded is not None
        assert loaded.mode == "fixed"
        assert loaded.d_init == pytest.approx(0.02)
        assert loaded.k == pytest.approx(3.5)
        assert loaded.floor == pytest.approx(0.06)
        assert loaded.cap == pytest.approx(0.12)
        assert loaded.vol_at_entry == pytest.approx(0.018)
        assert loaded.vol_source == "tier"
    finally:
        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM trades WHERE symbol = %s", (symbol,))
            conn.commit()
        conn.close()
        store.close()


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_save_frozen_stop_round_trip() -> None:
    """save_frozen_stop backfills frozen params on an existing open trade row."""
    store = PostgreSQLStore(use_pool=False)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    symbol = "TEST_STOP_3"
    try:
        store.open_trade(
            symbol=symbol, signal_id=123, decision_id=None,
            entry_order_id="test-order-3", entry_time=ts,
            entry_notional=1000.0, score=0.02, regime_mult=1.0,
            qty=10.0, signal_score=0.5, frozen_stop=None,
        )
        frozen = FrozenStop(
            strategy="S4", mode="vol_scaled", vol_at_entry=0.028, sigma_eff=0.028,
            k=2.2, floor=0.04, cap=0.10, d_init=0.0616, vol_source="last_good",
        )
        # Need trade_id; fetch it.
        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM trades WHERE symbol = %s AND exit_time IS NULL",
                (symbol,),
            )
            row = cur.fetchone()
            assert row is not None
            trade_id = int(row[0])
        conn.close()
        store.save_frozen_stop(trade_id, frozen)
        loaded = store.load_frozen_stop(symbol)
        assert loaded is not None
        assert loaded.mode == "vol_scaled"
        assert loaded.k == pytest.approx(2.2)
        assert loaded.vol_source == "last_good"
    finally:
        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM trades WHERE symbol = %s", (symbol,))
            conn.commit()
        conn.close()
        store.close()


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_insert_stop_decision_and_shadow() -> None:
    """insert_stop_decision and insert_stop_shadow persist rows."""
    store = PostgreSQLStore(use_pool=False)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    symbol = "TEST_STOP_2"
    frozen = FrozenStop(
        strategy="S1", mode="fixed", vol_at_entry=None, sigma_eff=None,
        k=None, floor=None, cap=None, d_init=0.02, vol_source=None,
    )
    decision = StopDecision(
        symbol=symbol, strategy="S1", mode="fixed",
        entry_price=100.0, observed_price=97.0, trigger_price=98.0,
        d_init=0.02, vol_at_entry=None, sigma_eff=None, k=None,
        floor=None, cap=None, price_source="market.prices",
        vol_source=None, breached=True, cycle_ts=ts,
    )
    try:
        store.open_trade(
            symbol=symbol, signal_id=None, decision_id=None,
            entry_order_id="test-order-2", entry_time=ts,
            entry_notional=1000.0, score=0.02, regime_mult=1.0,
            qty=10.0, signal_score=None, frozen_stop=frozen,
        )
        store.record_trade_exit(symbol, "test-exit-2", ts, "stop_loss")
        store.insert_stop_decision(decision, "test-exit-2")
        store.insert_stop_shadow([{
            "cycle_ts": ts, "symbol": symbol, "strategy": "S1",
            "entry_price": 100.0, "observed_price": 97.0,
            "vol_at_entry": None, "sigma_eff": None, "vol_source": None,
            "d_init_fixed": 0.02, "trigger_fixed": 98.0, "would_breach_fixed": True,
            "d_init_vol_scaled": 0.05, "trigger_vol_scaled": 95.0, "would_breach_vol_scaled": True,
        }])

        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stop_decisions WHERE symbol=%s", (symbol,))
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT COUNT(*) FROM stop_shadow_log WHERE symbol=%s", (symbol,))
            assert cur.fetchone()[0] == 1
        conn.close()
    finally:
        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stop_decisions WHERE symbol = %s", (symbol,))
            cur.execute("DELETE FROM stop_shadow_log WHERE symbol = %s", (symbol,))
            cur.execute("DELETE FROM trades WHERE symbol = %s", (symbol,))
            conn.commit()
        conn.close()
        store.close()
