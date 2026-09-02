"""#406 — `execution_decisions.signal_id` fill rate per `reason_code`.

Before this module existed, the only signal that "we lost the key back to the
signal that caused the decision" appeared was the dossier operator opening the
prompt alpha-miner and counting rows by hand. On 2026-08-27 that hand-count
found 17/513 execution_decisions rows with a non-NULL ``signal_id`` — every
SELL was missing it, 487 SKIP_THRESHOLD rows were missing it, 12/14
SKIP_PYRAMIDING rows had it, and 4/4 SKIP_FALLBACK rows were missing it.

This panel makes the rate observable from the dossier, per session, so a
regression surfaces without a human in the loop. It is pure: takes the
``execution_decisions`` rows already loaded by the dossier builder, returns
a structured dict. The dossier builder is the only caller.

Freeze (#171): read-only measurement. Publishes ``signal_id_fill_by_reason``
alongside the existing panels. Does NOT mutate the source rows, the dossier,
or any DB.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

SCHEMA_VERSION = "1.0"

# Reason codes where a signal is by definition known at write time. If any of
# these buckets falls below 100% fill rate, the bug is in the writer that lost
# the signal_id — there is no execution path that legitimately lacks it.
REQUIRES_SIGNAL_ID = frozenset({
    "BUY",
    "SELL",
    "SKIP_THRESHOLD",
    "SKIP_PYRAMIDING",
    "SKIP_FALLBACK",
    "SKIP_STALE",
    "SKIP_EMA",
    "SKIP_CAP",
    "SKIP_ENTRY_GATE",
})

# Reason codes where NULL signal_id is structurally legitimate — exits driven
# by time/weight/stop-loss policy rather than a fresh LLM read. These are
# surfaced separately so "missing key" and "no signal involved" stay
# distinguishable, per issue #406 point 2.
STRUCTURALLY_NULL_OK = frozenset({
    "STOP_LOSS",
    "EOD_CLOSE",
    "REBALANCE",
    "KILL_SWITCH",
})


def _has_signal_id(value: Any) -> bool:
    """A signal_id is present iff it is set and not the Python/pandas sentry for
    missing. JSON loader returns int|None; this keeps the contract explicit."""
    if value is None:
        return False
    if isinstance(value, float):
        # NaN never equals itself — the same idiom used in _record_gate_drops.
        return value == value
    return True


def build_signal_id_coverage(rows: list[dict]) -> dict:
    """Bucket ``execution_decisions`` rows by ``reason_code`` and report the
    ``signal_id`` fill rate per bucket.

    Args:
        rows: each dict must carry at least ``reason_code`` (str) and
            ``signal_id`` (int|None). Other fields are ignored.

    Returns:
        {
            "schema_version": "1.0",
            "total_rows": int,
            "totals_with_signal_id": int,
            "totals_without_signal_id": int,
            "totals_fill_rate": float | None,
            "by_reason_code": {
                "<reason_code>": {
                    "rows": int,
                    "with_signal_id": int,
                    "without_signal_id": int,
                    "fill_rate": float | None,
                    "expected_fill_rate": "must_be_full" | "may_be_null",
                },
                ...
            },
            "regressions": [<reason_code>, ...],  # must_be_full buckets < 100%
        }
    """
    buckets: dict[str, list[bool]] = defaultdict(list)
    for row in rows or []:
        reason = str(row.get("reason_code") or "")
        buckets[reason].append(_has_signal_id(row.get("signal_id")))

    by_reason: dict[str, dict] = {}
    regressions: list[str] = []
    total = 0
    with_id = 0
    for reason, present_list in sorted(buckets.items()):
        n = len(present_list)
        n_with = sum(1 for v in present_list if v)
        n_without = n - n_with
        rate = (n_with / n) if n else None
        expected = "must_be_full" if reason in REQUIRES_SIGNAL_ID else "may_be_null"
        if expected == "must_be_full" and n > 0 and n_with < n:
            regressions.append(reason)
        by_reason[reason] = {
            "rows": n,
            "with_signal_id": n_with,
            "without_signal_id": n_without,
            "fill_rate": rate,
            "expected_fill_rate": expected,
        }
        total += n
        with_id += n_with

    return {
        "schema_version": SCHEMA_VERSION,
        "total_rows": total,
        "totals_with_signal_id": with_id,
        "totals_without_signal_id": total - with_id,
        "totals_fill_rate": (with_id / total) if total else None,
        "by_reason_code": by_reason,
        "regressions": regressions,
    }