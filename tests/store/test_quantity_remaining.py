"""#397: quantity_remaining — the live open position size for a trade row.

`trades.qty` is overloaded (entry fill qty on open rows, exit fill qty on
closed rows), so it can never represent "how much is still held" for a
partially-wind-down open trade. The 2026-08 alpha-miss review found three
symbols whose DB qty was 2.8×-74× the broker position because partial exits and
broker-side stop fills were never written back. These tests pin the pure
arithmetic that recomputes the live remaining quantity from authoritative
broker fills, plus the reconcile pass that writes it back.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.store.pg_store import PostgreSQLStore, remaining_after_exits


def test_no_exits_remaining_equals_entry():
    remaining, new_ids = remaining_after_exits(entry_qty=41.564, recorded_ids=[], fills=[])
    assert remaining == 41.564
    assert new_ids == []


def test_recorded_partial_exits_decrement_remaining_without_new_ids():
    """Hole 1: portfolio SELL tranches already in exit_order_ids must reduce the
    live quantity even though they were never written back to trades.qty."""
    fills = [("sell-A", 1.580640), ("sell-B", 0.065727)]  # both already recorded
    remaining, new_ids = remaining_after_exits(
        entry_qty=2.981064744, recorded_ids=["sell-A", "sell-B"], fills=fills,
    )
    assert new_ids == []  # nothing new to append
    assert round(remaining, 6) == round(2.981064744 - 1.580640 - 0.065727, 6)


def test_unrecorded_stop_fill_is_counted_and_flagged_for_append():
    """Hole 2: a broker-side STOP fill not yet in exit_order_ids still reduces the
    remaining quantity AND is returned as a new id to append."""
    fills = [
        ("sell-A", 1.580640),   # recorded portfolio tranche
        ("sell-B", 0.065727),   # recorded portfolio tranche
        ("stop-C", 1.0),        # protective stop fill, NOT yet recorded
    ]
    remaining, new_ids = remaining_after_exits(
        entry_qty=2.981064744, recorded_ids=["sell-A", "sell-B"], fills=fills,
    )
    assert new_ids == ["stop-C"]
    # 2.981064744 - 1.580640 - 0.065727 - 1.0 = 0.334697644 ≈ broker residual 0.334697
    assert round(remaining, 4) == round(0.334697644, 4)


def test_exhausted_position_remaining_clamps_to_zero():
    """When fills cover the whole entry, remaining is 0 (not negative)."""
    fills = [("sell-A", 3.0)]
    remaining, _ = remaining_after_exits(entry_qty=3.0, recorded_ids=[], fills=fills)
    assert remaining == 0.0


def test_overfill_clamps_to_zero_not_negative():
    remaining, _ = remaining_after_exits(
        entry_qty=1.0, recorded_ids=[], fills=[("s", 1.5)],
    )
    assert remaining == 0.0


def test_zero_or_missing_fill_qty_ignored():
    """A cancelled/replaced order with filled_qty 0 must not be treated as an exit
    nor flagged for append."""
    fills = [("cancelled", 0.0), ("real", 2.0)]
    remaining, new_ids = remaining_after_exits(
        entry_qty=5.0, recorded_ids=[], fills=fills,
    )
    assert new_ids == ["real"]  # the zero-qty cancelled order is skipped
    assert remaining == 3.0


def test_recorded_ids_treated_as_set_dedup():
    """A fill whose id is already recorded must not be re-appended, but its qty
    still counts toward the running total (idempotent recompute)."""
    fills = [("sell-A", 2.0), ("sell-A", 2.0)]  # duplicate fill record
    remaining, new_ids = remaining_after_exits(
        entry_qty=5.0, recorded_ids=["sell-A"], fills=fills,
    )
    # The duplicate is deduped against itself too: counted once.
    assert new_ids == []
    assert round(remaining, 6) == 3.0


def test_none_recorded_ids():
    """recorded_ids=None (fresh trade, exit_order_ids NULL) is treated as empty."""
    remaining, new_ids = remaining_after_exits(
        entry_qty=2.0, recorded_ids=None, fills=[("s", 0.5)],
    )
    assert new_ids == ["s"]
    assert remaining == 1.5

# ---------------------------------------------------------------------------
# reconcile_open_positions — writes quantity_remaining back to open trades
# from broker SELL fills (Hole 1: recorded tranches; Hole 2: stop fills).
# Mock-based: asserts on the UPDATE SQL/params, no live Postgres/broker.
# ---------------------------------------------------------------------------

def _mock_pg_store(open_rows):
    """Build a PostgreSQLStore backed by a mock connection.

    open_rows: list of tuples (id, symbol, qty, entry_time, exit_order_ids)
    returned by the open-trade SELECT.
    """
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    # First execute() is the open-trade SELECT -> returns open_rows; every
    # later execute() is an UPDATE (fetchone not used).
    mock_cur.fetchall.return_value = open_rows
    store = PostgreSQLStore(conn=mock_conn)
    return store, mock_conn, mock_cur


def _order(oid, filled_qty, *, side="sell", filled_at=None):
    o = MagicMock()
    o.id = oid
    o.side = MagicMock(value=side)
    o.filled_qty = filled_qty
    o.filled_at = filled_at
    return o


ENTRY = datetime(2026, 7, 21, 16, 0, tzinfo=timezone.utc)


def test_reconcile_open_positions_no_exits_no_write():
    """Fresh fully-held position (no exit_order_ids, no broker SELLs) -> no UPDATE."""
    store, _conn, cur = _mock_pg_store([(10, "AAA", 2.0, ENTRY, None)])
    tc = MagicMock()
    tc.get_orders.return_value = []  # no SELL fills

    updated = store.reconcile_open_positions(tc)

    assert updated == 0
    update_sqls = [str(c[0][0]) for c in cur.execute.call_args_list if "UPDATE" in str(c[0][0])]
    assert update_sqls == [], "fresh position with no exits must not be written"


def test_reconcile_open_positions_records_recorded_partial_tranches():
    """Hole 1: portfolio SELL tranches already in exit_order_ids recompute the
    live remaining (entry - recorded fills) and write it."""
    store, _conn, cur = _mock_pg_store([
        (373, "WDC", 2.981064744, ENTRY, ["sell-A", "sell-B"]),
    ])
    tc = MagicMock()
    tc.get_orders.return_value = [
        _order("sell-A", 1.580640, filled_at=ENTRY),
        _order("sell-B", 0.065727, filled_at=ENTRY),
    ]

    updated = store.reconcile_open_positions(tc)

    assert updated == 1
    update_call = next(c for c in cur.execute.call_args_list if "UPDATE" in str(c[0][0]))
    sql, params = update_call[0]
    assert "quantity_remaining" in sql
    assert "exit_time" not in sql  # not exhausted -> not closed
    # remaining = 2.981064744 - 1.580640 - 0.065727 = 1.334697744
    assert round(params[0], 6) == round(1.334697744, 6)
    assert params[1] == ["sell-A", "sell-B"]  # unchanged, no new ids


def test_reconcile_open_positions_ingests_unrecorded_stop_fill():
    """Hole 2: a protective-stop fill NOT in exit_order_ids is appended and
    counted; the row stays open because a residual remains."""
    store, _conn, cur = _mock_pg_store([
        (373, "WDC", 2.981064744, ENTRY, ["sell-A", "sell-B"]),
    ])
    tc = MagicMock()
    tc.get_orders.return_value = [
        _order("sell-A", 1.580640, filled_at=ENTRY),
        _order("sell-B", 0.065727, filled_at=ENTRY),
        _order("stop-C", 1.0, filled_at=datetime(2026, 7, 27, 18, tzinfo=timezone.utc)),
    ]

    updated = store.reconcile_open_positions(tc)

    assert updated == 1
    update_call = next(c for c in cur.execute.call_args_list if "UPDATE" in str(c[0][0]))
    sql, params = update_call[0]
    assert "exit_time" not in sql  # residual 0.334.. remains -> not closed
    # new stop id appended after the recorded tranches
    assert params[1] == ["sell-A", "sell-B", "stop-C"]
    assert round(params[0], 4) == round(0.334697744, 4)


def test_reconcile_open_positions_closes_when_stop_exhausts_position():
    """A stop fill that exhausts the position closes the trade (exit_time set)
    with the real order id linked so reconcile_trade_fills can price it."""
    store, _conn, cur = _mock_pg_store([
        (373, "WDC", 2.646368, ENTRY, ["sell-A", "sell-B"]),
    ])
    tc = MagicMock()
    # remaining after recorded tranches = 2.646368 - 1.580640 - 0.065727 - 1.0(stop)
    # = 0.000001 -> exhausted
    tc.get_orders.return_value = [
        _order("sell-A", 1.580640, filled_at=ENTRY),
        _order("sell-B", 0.065727, filled_at=ENTRY),
        _order("stop-C", 1.0, filled_at=datetime(2026, 7, 27, 18, tzinfo=timezone.utc)),
    ]

    updated = store.reconcile_open_positions(tc)

    assert updated == 1
    update_call = next(c for c in cur.execute.call_args_list if "UPDATE" in str(c[0][0]))
    sql, params = update_call[0]
    assert "exit_time" in sql
    assert "reconcile_close" in sql
    assert params[1] == ["sell-A", "sell-B", "stop-C"]


def test_reconcile_open_positions_ignores_buy_and_pre_entry_fills():
    """BUY fills and SELL fills that predate this trade's entry are not exits."""
    store, _conn, cur = _mock_pg_store([(10, "AAA", 3.0, ENTRY, [])])
    tc = MagicMock()
    tc.get_orders.return_value = [
        _order("buy-X", 3.0, side="buy", filled_at=ENTRY),       # entry BUY
        _order("old-sell", 3.0, filled_at=datetime(2026, 7, 20, tzinfo=timezone.utc)),  # before entry
    ]

    updated = store.reconcile_open_positions(tc)

    assert updated == 0  # only a BUY + a pre-entry sell -> no exits to record


def test_reconcile_open_positions_idempotent_rerun():
    """Second run with the same broker state writes nothing new (recompute)."""
    store, _conn, cur = _mock_pg_store([
        (373, "WDC", 2.981064744, ENTRY, ["sell-A", "sell-B", "stop-C"]),
    ])
    tc = MagicMock()
    tc.get_orders.return_value = [
        _order("sell-A", 1.580640, filled_at=ENTRY),
        _order("sell-B", 0.065727, filled_at=ENTRY),
        _order("stop-C", 1.0, filled_at=datetime(2026, 7, 27, 18, tzinfo=timezone.utc)),
    ]

    updated = store.reconcile_open_positions(tc)

    assert updated == 1
    update_call = next(c for c in cur.execute.call_args_list if "UPDATE" in str(c[0][0]))
    _sql, params = update_call[0]
    # All fills already recorded -> remaining unchanged, exit_order_ids unchanged.
    assert round(params[0], 4) == round(0.334697744, 4)
    assert params[1] == ["sell-A", "sell-B", "stop-C"]


def test_reconcile_open_positions_skips_symbol_on_broker_error():
    """A broker fetch failure for one trade is logged and skipped, not fatal."""
    store, _conn, cur = _mock_pg_store([
        (1, "AAA", 2.0, ENTRY, []),
        (2, "BBB", 2.0, ENTRY, []),
    ])
    tc = MagicMock()

    def get_orders(_req):
        if _req.symbols == ["BBB"]:
            raise RuntimeError("broker timeout")
        return [_order("sell-A", 1.0, filled_at=ENTRY)]

    tc.get_orders.side_effect = get_orders

    updated = store.reconcile_open_positions(tc)

    # AAA reconciled; BBB's failure swallowed. Only AAA written.
    assert updated == 1
    update_sqls = [str(c[0][0]) for c in cur.execute.call_args_list if "UPDATE" in str(c[0][0])]
    assert len(update_sqls) == 1
