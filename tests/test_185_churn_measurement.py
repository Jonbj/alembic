"""#185: post-flip churn measurement — pure-function tests (no DB, no Redis).

The defect the operator defined is a *signature*, not a raw count: a
`#185: S1 target weight dropped to 0%` exit followed by a re-entry (BUY) on
the same symbol within 15-60 minutes at the same weight. Counting only the
drops (as the PR #188 verification query did, and on the wrong column to
boot) cannot tell a legitimate monthly liquidation from the churn it must
detect. These tests pin the classification logic that makes the operator's
falsification test — "if the churn doesn't stop, the diagnosis was
incomplete" — actually runnable.
"""
from datetime import datetime, timezone

from scripts.measure_185_churn import classify_drops, per_session


def _ts(day, hour, minute):
    return datetime(2026, 8, day, hour, minute, tzinfo=timezone.utc)


def _row(day, hour, minute, symbol, decision, exit_mechanism=None):
    return {
        "tick_time": _ts(day, hour, minute),
        "symbol": symbol,
        "decision": decision,
        "exit_mechanism": exit_mechanism,
    }


# --- classify_drops ------------------------------------------------------

def test_drop_followed_by_buy_same_symbol_within_60min_is_churn():
    # The BP case from the issue: 17:52 s1_weight_drop -> 18:07 re-BUY (15 min).
    rows = [
        _row(5, 17, 52, "BP", "SELL", "s1_weight_drop"),
        _row(5, 18, 7, "BP", "BUY"),
    ]
    out = classify_drops(rows)
    assert len(out) == 1
    assert out[0]["symbol"] == "BP"
    assert out[0]["reentry_time"] == _ts(5, 18, 7)
    assert out[0]["is_churn"] is True


def test_drop_with_no_reentry_is_definitive_not_churn():
    # A legitimate monthly liquidation: dropped once, never re-bought.
    rows = [_row(7, 14, 22, "BRK.B", "SELL", "s1_weight_drop")]
    out = classify_drops(rows)
    assert out[0]["reentry_time"] is None
    assert out[0]["is_churn"] is False


def test_buy_outside_the_60min_window_does_not_count_as_reentry():
    rows = [
        _row(5, 19, 52, "BP", "SELL", "s1_weight_drop"),
        _row(6, 9, 30, "BP", "BUY"),  # next session, ~14h later
    ]
    out = classify_drops(rows)
    assert out[0]["reentry_time"] is None
    assert out[0]["is_churn"] is False


def test_buy_on_a_different_symbol_does_not_count_as_reentry():
    rows = [
        _row(5, 17, 52, "BP", "SELL", "s1_weight_drop"),
        _row(5, 18, 7, "SNOW", "BUY"),
    ]
    out = classify_drops(rows)
    assert out[0]["reentry_time"] is None
    assert out[0]["is_churn"] is False


def test_only_s1_weight_drop_exits_are_classified():
    # S4 expired/whipsaw exits and unrelated SELLs are not the #185 defect.
    rows = [
        _row(5, 15, 52, "BP", "SELL", "expired"),
        _row(5, 16, 7, "BP", "BUY"),
        _row(5, 17, 52, "BP", "SELL", "s1_weight_drop"),
    ]
    out = classify_drops(rows)
    assert [d["symbol"] for d in out] == ["BP"]
    assert out[0]["tick_time"] == _ts(5, 17, 52)


def test_first_reentry_within_the_window_wins():
    # Two re-entries; the churn is measured against the earliest.
    rows = [
        _row(5, 17, 52, "BP", "SELL", "s1_weight_drop"),
        _row(5, 18, 7, "BP", "BUY"),
        _row(5, 18, 22, "BP", "BUY"),
    ]
    out = classify_drops(rows)
    assert out[0]["reentry_time"] == _ts(5, 18, 7)


def test_empty_rows_yield_no_drops():
    assert classify_drops([]) == []


# --- per_session ---------------------------------------------------------

def test_drops_aggregated_by_utc_date_and_split_around_deploy():
    deploy = _ts(7, 14, 7)  # first S1 rebalance after the #185 fix
    drops = [
        {"tick_time": _ts(5, 17, 52), "symbol": "BP", "reentry_time": _ts(5, 18, 7), "is_churn": True},
        {"tick_time": _ts(5, 19, 52), "symbol": "BP", "reentry_time": None, "is_churn": False},
        {"tick_time": _ts(7, 14, 22), "symbol": "BRK.B", "reentry_time": None, "is_churn": False},
    ]
    rows = per_session(drops, deploy_cutoff=deploy)
    by_date = {r["date"]: r for r in rows}
    assert by_date["2026-08-05"]["drops"] == 2
    assert by_date["2026-08-05"]["churn"] == 1
    assert by_date["2026-08-05"]["phase"] == "pre"
    assert by_date["2026-08-07"]["drops"] == 1
    assert by_date["2026-08-07"]["churn"] == 0
    assert by_date["2026-08-07"]["phase"] == "post"


def test_drop_exactly_at_deploy_cutoff_is_post():
    deploy = _ts(7, 14, 7)
    drops = [{"tick_time": _ts(7, 14, 7), "symbol": "X", "reentry_time": None, "is_churn": False}]
    rows = per_session(drops, deploy_cutoff=deploy)
    assert rows[0]["phase"] == "post"


def test_sessions_are_sorted_chronologically():
    deploy = _ts(7, 14, 7)
    drops = [
        {"tick_time": _ts(6, 10, 0), "symbol": "A", "reentry_time": None, "is_churn": False},
        {"tick_time": _ts(5, 10, 0), "symbol": "B", "reentry_time": None, "is_churn": False},
    ]
    rows = per_session(drops, deploy_cutoff=deploy)
    assert [r["date"] for r in rows] == ["2026-08-05", "2026-08-06"]