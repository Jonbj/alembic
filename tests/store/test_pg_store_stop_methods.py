"""Smoke tests for pg_store stop-loss helpers (requires live-like DB)."""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone

import psycopg2
import pytest

from src.portfolio.stop_policy import FrozenStop, StopDecision
from src.store.pg_store import PostgreSQLStore


# ── Guard: no test symbol may exceed the VARCHAR(20) column width ────────────
# This runs at import/collection time — no DB, no network. It breaks before any
# live-DB test fires if a new symbol that is too long is introduced.
_TRADE_SYMBOL_MAX = 20  # trades.symbol VARCHAR(20)


def _guard_symbol_lengths() -> None:
    """Fail at import if any `symbol = "..."` in THIS file exceeds the column.

    The symbols are read out of the module's own source, not listed by hand.
    A hand-kept list would be a second copy of the truth: it drifts silently,
    and — the point of the guard — it does not see a symbol written inline in a
    test added tomorrow, which is exactly how #112 happened. Deriving them means
    a new over-long symbol breaks collection with no DB and no discipline
    required from whoever writes the test.
    """
    import ast

    source = pathlib.Path(__file__).read_text()
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "symbol" for t in node.targets
        ):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            found.append(node.value.value)

    assert found, "guard found no `symbol = \"...\"` assignments — has the file moved?"
    violations = sorted({s for s in found if len(s) > _TRADE_SYMBOL_MAX})
    assert not violations, (
        f"Symbol(s) exceed trades.symbol VARCHAR({_TRADE_SYMBOL_MAX}): "
        f"{violations} — shorten or the DB will reject the row with "
        f"StringDataRightTruncation (cf. #112)"
    )


_guard_symbol_lengths()  # run immediately on import; raises if violated


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
    symbol = "TEST_STOP_FIXED_AUD"  # max 20 chars — trades.symbol is VARCHAR(20)
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


@pytest.mark.skipif(os.environ.get("SKIP_DB_TESTS"), reason="SKIP_DB_TESTS set")
def test_insert_f8_shadow_persists_rows() -> None:
    """insert_f8_shadow persists per-strategy F8 regime_scale shadow rows (#32)."""
    store = PostgreSQLStore(use_pool=False)
    ts = datetime(2026, 7, 21, 14, 0, tzinfo=timezone.utc)
    try:
        store.insert_f8_shadow([
            {"cycle_ts": ts, "strategy": "TEST_S1", "scale": 0.512,
             "unscaled_weight": 0.5, "scaled_weight": 0.256, "applied": False},
            {"cycle_ts": ts, "strategy": "TEST_S4", "scale": 0.80,
             "unscaled_weight": 0.1, "scaled_weight": 0.08, "applied": False},
        ])
        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT scale, applied FROM f8_regime_scale_shadow "
                "WHERE strategy=%s AND cycle_ts=%s",
                ("TEST_S1", ts),
            )
            row = cur.fetchone()
            assert row is not None
            assert abs(row[0] - 0.512) < 1e-9
            assert row[1] is False
        conn.close()
    finally:
        conn = _connect_or_skip()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM f8_regime_scale_shadow WHERE strategy IN ('TEST_S1','TEST_S4')"
            )
            conn.commit()
        conn.close()
        store.close()
