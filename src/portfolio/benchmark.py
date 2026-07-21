"""Beta-scaled benchmark and alpha for the paper book.

The book runs at ~30% net-long exposure, so comparing its full return to SPY
outright is an unfair bar. The fair benchmark is ``exposure × SPY`` — i.e.
"hold `exposure` in SPY and the rest in cash". Alpha is the actual return minus
that benchmark: it isolates what the strategies add or subtract on top of the
market exposure they take. Answers "is Alembic losing more / gaining less than
its exposure explains?", which no prior metric captured.
"""
from __future__ import annotations


def _spy_on_or_before(spy_closes: dict, target_date: str) -> float | None:
    """SPY close on the latest available date <= target (handles weekends/holidays)."""
    candidates = [d for d in spy_closes if d <= target_date]
    if not candidates:
        return None
    return spy_closes[max(candidates)]


def compute_period_benchmark(
    nav_rows: list[dict],
    spy_closes: dict | None,
    from_date: str,
    to_date: str,
) -> dict:
    """Return {alembic_return, spy_return, avg_exposure, benchmark_return, alpha}.

    ``nav_rows`` are {date, nav, exposure} snapshots (may include a baseline
    buffer before ``from_date``, mirroring the MTM enrichment). The baseline is
    the last snapshot before ``from_date`` so the first in-range day's move
    counts; if none exists, the first in-range snapshot is used. Any field that
    cannot be computed (no SPY, no baseline) is None — fail-open, never raises.
    """
    out = {
        "alembic_return": None, "spy_return": None,
        "avg_exposure": None, "benchmark_return": None, "alpha": None,
    }
    rows = sorted((r for r in nav_rows if r.get("nav")), key=lambda r: r["date"])
    if not rows:
        return out

    before = [r for r in rows if r["date"] < from_date]
    in_range = [r for r in rows if from_date <= r["date"] <= to_date]
    baseline = before[-1] if before else (in_range[0] if in_range else None)
    end = in_range[-1] if in_range else rows[-1]
    if baseline is None or not baseline["nav"] or not end["nav"]:
        return out

    out["alembic_return"] = round(end["nav"] / baseline["nav"] - 1, 6)

    expos = [r["exposure"] for r in in_range if r.get("exposure") is not None]
    if expos:
        out["avg_exposure"] = round(sum(expos) / len(expos), 6)

    if spy_closes:
        spy_start = _spy_on_or_before(spy_closes, baseline["date"])
        spy_end = _spy_on_or_before(spy_closes, end["date"])
        if spy_start and spy_end:
            out["spy_return"] = round(spy_end / spy_start - 1, 6)
            if out["avg_exposure"] is not None:
                out["benchmark_return"] = round(out["avg_exposure"] * out["spy_return"], 6)
                out["alpha"] = round(out["alembic_return"] - out["benchmark_return"], 6)

    return out
