"""#121: read-only classifier distinguishing legit co-held residuals from
genuinely-stuck orphan trades. Pure-function tests (no DB, no broker)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from scripts.reconcile_open_trades_vs_broker import classify_positions, summarize


def _trade(tid, symbol, qty, strategy="S4", entry_days_ago=5):
    entry = datetime(2026, 7, 22, 16, 0, tzinfo=timezone.utc)
    return {"id": tid, "symbol": symbol, "qty": qty, "entry_time": entry,
            "stop_strategy": strategy}


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


def _one(records, symbol):
    return next(r for r in records if r["symbol"] == symbol)


def test_fully_held():
    recs = classify_positions([_trade(1, "AAA", 2.0)], {"AAA": 2.0}, now=NOW)
    assert _one(recs, "AAA")["category"] == "fully_held"
    assert _one(recs, "AAA")["sold_qty"] == 0.0


def test_partial_wind_down_coheld_is_not_orphan():
    # WDC case: entered 2.981, broker still holds 1.334.
    recs = classify_positions([_trade(373, "WDC", 2.981064744, strategy="S1")],
                              {"WDC": 1.334697164}, now=NOW)
    r = _one(recs, "WDC")
    assert r["category"] == "partially_wound_down_coheld"
    assert r["strategy"] == "S1"
    assert round(r["sold_qty"], 4) == round(2.981064744 - 1.334697164, 4)
    assert r["days_open"] == 5


def test_genuinely_orphan_when_broker_holds_nothing():
    recs = classify_positions([_trade(9, "BBB", 3.0)], {}, now=NOW)  # BBB absent = 0 held
    assert _one(recs, "BBB")["category"] == "genuinely_orphan"


def test_over_held_when_broker_exceeds_entry():
    recs = classify_positions([_trade(2, "CCC", 1.0)], {"CCC": 3.0}, now=NOW)
    assert _one(recs, "CCC")["category"] == "over_held"


def test_untracked_position_has_no_trade_row():
    recs = classify_positions([_trade(1, "AAA", 2.0)], {"AAA": 2.0, "ZZZ": 5.0}, now=NOW)
    z = _one(recs, "ZZZ")
    assert z["category"] == "untracked_position"
    assert z["trade_id"] is None
    assert z["db_qty"] == 0.0


def test_entry_time_accepts_iso_string():
    t = _trade(1, "AAA", 2.0)
    t["entry_time"] = "2026-07-25T16:00:00+00:00"
    recs = classify_positions([t], {"AAA": 2.0}, now=NOW)
    assert _one(recs, "AAA")["days_open"] == 2


# ---------------------------------------------------------------------------
# #397: quantity_remaining-aware classification. When the live DB view
# (quantity_remaining, set by reconcile_open_positions) is present it is the
# basis for "does DB agree with the broker?"; entry qty is the fallback.
# ---------------------------------------------------------------------------

def _trade_with_remaining(tid, symbol, qty, remaining, strategy="S4"):
    t = _trade(tid, symbol, qty, strategy=strategy)
    t["quantity_remaining"] = remaining
    return t


def test_remaining_matches_held_is_fully_held_not_divergence():
    """A correctly-tracked residual (remaining ≈ held) is consistent, not an anomaly."""
    # entry 2.981, reconciled remaining 1.334, broker holds 1.334.
    recs = classify_positions(
        [_trade_with_remaining(373, "WDC", 2.981064744, 1.334697164, strategy="S1")],
        {"WDC": 1.334697164}, now=NOW,
    )
    r = _one(recs, "WDC")
    assert r["category"] == "fully_held"
    assert r["entry_qty"] == 2.981064744
    assert round(r["db_qty"], 4) == round(1.334697164, 4)  # db_qty is the live remaining


def test_quantity_divergence_when_remaining_exceeds_held():
    """#397 signature: DB remaining 41.564 vs broker 0.564 — exits not written back
    that reconcile could not fix -> quantity_divergence anomaly."""
    recs = classify_positions(
        [_trade_with_remaining(5, "NOK", 41.564, 41.564)],
        {"NOK": 0.564}, now=NOW,
    )
    r = _one(recs, "NOK")
    assert r["category"] == "quantity_divergence"
    assert round(r["db_qty"], 3) == 41.564
    assert round(r["held_qty"], 3) == 0.564


def test_live_quantity_two_percent_below_broker_is_divergence():
    """Every live DB/broker mismatch beyond rounding epsilon is an anomaly."""
    recs = classify_positions(
        [_trade_with_remaining(5, "NOK", 100.0, 100.0)],
        {"NOK": 98.0}, now=NOW,
    )
    assert _one(recs, "NOK")["category"] == "quantity_divergence"


def test_live_quantity_excess_beyond_epsilon_is_over_held():
    """The broker side of the same invariant is alerted as over_held."""
    recs = classify_positions(
        [_trade_with_remaining(5, "NOK", 100.0, 100.0)],
        {"NOK": 100.0002}, now=NOW,
    )
    assert _one(recs, "NOK")["category"] == "over_held"


def test_live_quantity_difference_within_epsilon_is_fully_held():
    """Only float/rounding noise at or below epsilon is accepted as a match."""
    recs = classify_positions(
        [_trade_with_remaining(5, "NOK", 100.0, 100.0)],
        {"NOK": 99.99995}, now=NOW,
    )
    assert _one(recs, "NOK")["category"] == "fully_held"


def test_quantity_divergence_not_fired_when_remaining_absent():
    """Without quantity_remaining the pre-#397 logic holds: entry qty > broker is
    partially_wound_down_coheld (informational), never quantity_divergence."""
    recs = classify_positions([_trade(5, "NOK", 41.564)], {"NOK": 0.564}, now=NOW)
    assert _one(recs, "NOK")["category"] == "partially_wound_down_coheld"


def test_over_held_uses_remaining_when_present():
    """Broker holds MORE than the DB live view -> over_held (untracked buy)."""
    recs = classify_positions(
        [_trade_with_remaining(2, "CCC", 3.0, 1.0)], {"CCC": 3.0}, now=NOW,
    )
    assert _one(recs, "CCC")["category"] == "over_held"


def test_genuinely_orphan_with_remaining_still_orphan():
    """Broker holds nothing but DB still shows an open remaining -> orphan."""
    recs = classify_positions(
        [_trade_with_remaining(9, "BBB", 3.0, 3.0)], {}, now=NOW,
    )
    assert _one(recs, "BBB")["category"] == "genuinely_orphan"


def test_summarize_counts_by_category():
    recs = classify_positions(
        [_trade(1, "AAA", 2.0), _trade(9, "BBB", 3.0), _trade(373, "WDC", 2.98, strategy="S1")],
        {"AAA": 2.0, "WDC": 1.33, "ZZZ": 5.0},
        now=NOW,
    )
    counts = summarize(recs)
    assert counts["fully_held"] == 1
    assert counts["genuinely_orphan"] == 1
    assert counts["partially_wound_down_coheld"] == 1
    assert counts["untracked_position"] == 1


# ---------------------------------------------------------------------------
# force_close_orphans — pure coordinator over record_trade_exit (spec §2)
# ---------------------------------------------------------------------------

def test_force_close_orphans_dry_run_writes_nothing():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    orphans = [
        {"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"},
        {"trade_id": 11, "symbol": "DDD", "category": "genuinely_orphan"},
    ]
    results = force_close_orphans(
        orphans, writer=writer, dry_run=True,
        now=datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc),
    )
    assert len(results) == 2
    assert all(r["dry_run"] is True and r["closed"] is False for r in results)
    assert all(r["exit_reason"] == "orphan_reconcile" for r in results)
    assert results[0]["exit_order_id"] == "orphan_reconcile:9"
    writer.assert_not_called()


def test_force_close_orphans_calls_writer_with_orphan_reconcile_reason():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    orphans = [{"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"}]
    now = datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc)
    results = force_close_orphans(orphans, writer=writer, dry_run=False, now=now)
    assert len(results) == 1
    r = results[0]
    assert r["closed"] is True
    assert r["dry_run"] is False
    assert r["exit_reason"] == "orphan_reconcile"
    assert r["exit_order_id"] == "orphan_reconcile:9"
    writer.assert_called_once_with(
        symbol="BBB",
        exit_order_id="orphan_reconcile:9",
        exit_time=now,
        exit_reason="orphan_reconcile",
        trade_id=9,
    )


def test_force_close_orphans_uses_record_exit_order_id_when_present():
    """If the caller enriched the record with a real broker order id (recovered
    by the Celery task), force_close_orphans must use it, not the synthetic id."""
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    orphans = [{"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan",
                "exit_order_id": "real-sell-123"}]
    force_close_orphans(orphans, writer=writer, dry_run=False,
                        now=datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc))
    _, kwargs = writer.call_args
    assert kwargs["exit_order_id"] == "real-sell-123"


def test_force_close_orphans_ignores_non_orphan_categories():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    records = [
        {"trade_id": 1, "symbol": "AAA", "category": "fully_held"},
        {"trade_id": 2, "symbol": "CCC", "category": "over_held"},
        {"symbol": "ZZZ", "category": "untracked_position", "trade_id": None},
        {"trade_id": 3, "symbol": "WDC", "category": "partially_wound_down_coheld"},
    ]
    results = force_close_orphans(records, writer=writer, dry_run=False)
    assert results == []
    writer.assert_not_called()


def test_force_close_orphans_idempotent_rerun_is_noop():
    """Re-run with the same records: the writer (record_trade_exit) is idempotent
    via COALESCE — first write wins, the second call does not overwrite
    exit_time. The closed set after the second call equals the first."""
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    closed_times: dict[int, datetime] = {}

    def writer(*, symbol, exit_order_id, exit_time, exit_reason, trade_id):
        # Simulate record_trade_exit's COALESCE(exit_time, %s): first write wins.
        if trade_id not in closed_times:
            closed_times[trade_id] = exit_time
        return trade_id

    orphans = [{"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"}]
    now1 = datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc)
    force_close_orphans(orphans, writer=writer, dry_run=False, now=now1)
    now2 = datetime(2026, 7, 28, 21, 35, tzinfo=timezone.utc)
    force_close_orphans(orphans, writer=writer, dry_run=False, now=now2)
    # First-write-wins: the second call did not overwrite exit_time.
    assert closed_times[9] == now1


def test_force_close_orphans_continues_on_per_trade_error():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans

    def writer(*, symbol, exit_order_id, exit_time, exit_reason, trade_id):
        if trade_id == 9:
            raise RuntimeError("db error")
        return trade_id

    orphans = [
        {"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"},
        {"trade_id": 11, "symbol": "DDD", "category": "genuinely_orphan"},
    ]
    results = force_close_orphans(orphans, writer=writer, dry_run=False)
    assert results[0]["closed"] is False
    assert "db error" in results[0]["error"]
    assert results[1]["closed"] is True
