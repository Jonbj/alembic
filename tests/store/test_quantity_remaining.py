"""#397: quantity_remaining — the live open position size for a trade row.

`trades.qty` is overloaded (entry fill qty on open rows, exit fill qty on
closed rows), so it can never represent "how much is still held" for a
partially-wound-down open trade. The 2026-08 alpha-miss review found three
symbols whose DB qty was 2.8×-74× the broker position because partial exits and
broker-side stop fills were never written back. These tests pin the pure
arithmetic that recomputes the live remaining quantity from authoritative
broker fills.
"""
from __future__ import annotations

from src.store.pg_store import remaining_after_exits


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