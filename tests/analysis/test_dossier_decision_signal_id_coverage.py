"""#406 — Decision Log signal_id fill rate per reason_code."""

from src.analysis.dossier.decision_signal_id_coverage import (
    REQUIRES_SIGNAL_ID,
    STRUCTURALLY_NULL_OK,
    build_signal_id_coverage,
)


def _row(reason_code, signal_id):
    return {"reason_code": reason_code, "signal_id": signal_id}


def test_regression_table_matches_2026_08_27_measurement():
    """The headline finding of the issue was 17/513 = ~3% with the SELL bucket
    fully missing. Replay that distribution and confirm the panel flags the
    offending buckets and computes the totals faithfully."""
    rows = (
        [_row("SKIP_THRESHOLD", None) for _ in range(487)]
        + [_row("SKIP_PYRAMIDING", 1) for _ in range(12)]
        + [_row("SKIP_PYRAMIDING", None) for _ in range(2)]
        + [_row("BUY", 100 + i) for i in range(5)]
        + [_row("SKIP_FALLBACK", None) for _ in range(4)]
        + [_row("SELL", None) for _ in range(3)]
    )
    panel = build_signal_id_coverage(rows)
    assert panel["total_rows"] == 513
    assert panel["totals_with_signal_id"] == 17
    assert panel["totals_without_signal_id"] == 496
    # Four must_be_full buckets fell below 100% on 2026-08-27 — SKIP_PYRAMIDING
    # at 12/14 (86%) is also a regression, even though most rows were OK.
    assert set(panel["regressions"]) == {
        "SKIP_THRESHOLD", "SELL", "SKIP_FALLBACK", "SKIP_PYRAMIDING",
    }
    by_reason = panel["by_reason_code"]
    assert by_reason["SKIP_THRESHOLD"]["fill_rate"] == 0.0
    assert by_reason["SKIP_PYRAMIDING"]["fill_rate"] == 12 / 14
    assert by_reason["BUY"]["fill_rate"] == 1.0
    assert by_reason["SELL"]["fill_rate"] == 0.0
    assert by_reason["SKIP_FALLBACK"]["fill_rate"] == 0.0


def test_structurally_null_reasons_do_not_trigger_regression():
    """A STOP_LOSS / EOD_CLOSE / REBALANCE row with NULL signal_id is correct:
    that exit was driven by policy, not by a fresh LLM read. The panel must NOT
    flag these as regressions — distinguish 'lost the key' from 'no signal
    involved' (issue #406, point 2)."""
    rows = [
        _row("STOP_LOSS", None),
        _row("EOD_CLOSE", None),
        _row("REBALANCE", None),
        _row("BUY", 42),
    ]
    panel = build_signal_id_coverage(rows)
    assert panel["regressions"] == []
    for reason in ("STOP_LOSS", "EOD_CLOSE", "REBALANCE"):
        assert panel["by_reason_code"][reason]["expected_fill_rate"] == "may_be_null"
    assert panel["by_reason_code"]["BUY"]["expected_fill_rate"] == "must_be_full"


def test_passes_when_every_required_bucket_is_full():
    """A clean day: every reason that REQUIRES a signal has one. The panel
    reports 100% fill rate and an empty regression list."""
    rows = [
        _row("BUY", 1),
        _row("SELL", 2),
        _row("SKIP_THRESHOLD", 3),
        _row("SKIP_PYRAMIDING", 4),
        _row("SKIP_FALLBACK", 5),
        _row("SKIP_STALE", 6),
        _row("STOP_LOSS", None),
    ]
    panel = build_signal_id_coverage(rows)
    assert panel["regressions"] == []
    assert panel["totals_fill_rate"] == 6 / 7
    assert panel["totals_with_signal_id"] == 6


def test_empty_rows_yields_zero_rate_not_none():
    """A session with no decisions at all must NOT be reported as missing data:
    fill rate is 0/0 = undefined, but totals are zero. The contract is that
    the panel is always publishable, never 'incomplete' (matches opportunity.py
    and panels.py zero-row behaviour)."""
    panel = build_signal_id_coverage([])
    assert panel["total_rows"] == 0
    assert panel["totals_fill_rate"] is None
    assert panel["by_reason_code"] == {}
    assert panel["regressions"] == []


def test_nan_signal_id_treated_as_missing():
    """A pandas/JSON loader may surface NaN for a missing int column. The
    detector must NOT count NaN as 'present'. Mirror the NaN-safe idiom
    used in _record_gate_drops."""
    import math

    rows = [
        _row("SKIP_THRESHOLD", float("nan")),
        _row("BUY", 7),
    ]
    panel = build_signal_id_coverage(rows)
    assert panel["by_reason_code"]["SKIP_THRESHOLD"]["with_signal_id"] == 0
    assert math.isnan(float("nan"))  # sanity: the test setup itself
    assert panel["regressions"] == ["SKIP_THRESHOLD"]


def test_reason_code_sets_are_disjoint():
    """Guard: a future contributor adding a reason_code to REQUIRES_SIGNAL_ID
    that is already in STRUCTURALLY_NULL_OK would silently mislabel exits. Keep
    the contract locally testable rather than only at runtime."""
    assert REQUIRES_SIGNAL_ID.isdisjoint(STRUCTURALLY_NULL_OK)