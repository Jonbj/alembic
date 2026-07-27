"""#121: read-only classifier distinguishing legit co-held residuals from
genuinely-stuck orphan trades. Pure-function tests (no DB, no broker)."""
from datetime import datetime, timezone

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
