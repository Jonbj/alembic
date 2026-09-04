"""Observed disposition of an S4 signal within one portfolio cycle → exit_mechanism (#184).

#60 introduced `exit_mechanism` as a structured tag for weight-0 SELL exits, but
`_classify_zero_weight_exit` derived it from the AGE of the last signal row in the
DB, not from anything the pipeline had actually done. That reads as a fact and is a
guess: on 2026-08-05 four positions whose stale signals FIX-D had *explicitly
re-admitted* in that very cycle (MCD/NVO/PFE/PLTR) were sold with the reason
"S4 signal expired ... no counter-signal found" — a sentence describing exactly the
condition FIX-D uses to NOT close a position.

The fix is to record what the pipeline does to a signal at the point where it does
it (the "disposition"), carry it to the decision log, and map it to the label. A
classifier that cannot know must say `unknown` rather than consult the clock.

Asymmetry worth stating: FRESH → "whipsaw" and STALE_PRESERVED → "unknown" describe
the same shape of observation ("the signal reached the portfolio engine and the
weight is still 0"). "whipsaw" keeps its #60 meaning — a *fresh* weak re-signal —
because #61's damper counts it and its definition matches what is observed. A
preserved stale signal is not a fresh re-signal, so it gets `unknown`: why those
weights were zeroed is a separate investigation, deliberately out of #184's scope.
"""
from __future__ import annotations

import math

# ─── Dispositions: what the S4 pipeline did to the signal, recorded where it did it ───
FRESH = "fresh"
"""Passed every gate and was handed to the portfolio engine as a fresh signal."""

STALE_PRESERVED = "stale_preserved"
"""Older than max_signal_age_hours but re-admitted by FIX-D (open position, no counter-signal)."""

STALE_DROPPED = "stale_dropped"
"""Older than max_signal_age_hours and NOT preserved — discarded for age."""

FALLBACK_FILTERED = "fallback_filtered"
"""Dropped from the ranking because it came from the FinBERT fallback (#108)."""

ENTRY_FRESHNESS_FILTERED = "entry_freshness_filtered"
"""Dropped by the news-freshness entry gate (#150) — symbols with no open position only."""

BELOW_ENTRY_GATE = "below_entry_gate"
"""Dropped because |score| was under the active feedback:entry_threshold."""

# ─── Decisions: the value written to execution_decisions.decision for a SKIP ───
# S4's skip paths persist a row in execution_decisions so a no-trade symbol is
# distinguishable from NO_NEWS (issue #151). Each drop the ranking applies has a
# matching decision label; FALLBACK_FILTERED (the in-memory disposition, per cycle)
# and SKIP_FALLBACK (the persisted decision, cross-cycle) are two names for the same
# concept at two levels — kept here together so the concept has one source of truth
# and the scheduler imports the string instead of retyping it.
DECISION_SKIP_FALLBACK = "SKIP_FALLBACK"
"""execution_decisions.decision for a signal _filter_fallback_signals (#108) dropped
from BUY ranking. The drop is correct policy (post-SPCX); the row only makes it
visible so a fallback-only symbol (ERIC/AMAT, 2026-07-27) is not indistinguishable
from NO_NEWS. See issue #151 and docs/ALPHA_MISS_REPORT_2026-07-27.md §7."""

# ─── Mechanisms: the value written to execution_decisions.exit_mechanism ───
MECHANISM_NO_SIGNAL = "no_signal"
MECHANISM_EXPIRED = "expired"
MECHANISM_WHIPSAW = "whipsaw"
MECHANISM_UNKNOWN = "unknown"

# Reason diagnostico del ledger trades (#430). Non e' un nuovo percorso di
# uscita: descrive soltanto una portfolio_sell avvenuta al primo beat in cui la
# posizione non era piu' protetta dal hold minimum.
REASON_HOLD_MINIMUM_EXPIRY = "hold_minimum_expiry"


def reason_for_hold_minimum_expiry(
    exit_reason: str,
    holding_seconds: float | None,
    hold_minimum_minutes: int,
    *,
    cycle_seconds: int = 900,
    tolerance_seconds: int = 60,
) -> str:
    """Distingui il primo beat post-hold dalle altre ``portfolio_sell``.

    Il filtro considera ancora recente una posizione esattamente sul confine;
    il primo beat eleggibile e' quindi il multiplo di ciclo strettamente
    successivo al hold. La tolleranza assorbe soltanto il jitter dei timestamp
    di worker/fill e non partecipa ad alcuna decisione di trading.
    """
    if exit_reason != "portfolio_sell" or holding_seconds is None:
        return exit_reason
    hold_seconds = hold_minimum_minutes * 60
    first_eligible_cycle = (
        math.floor(hold_seconds / cycle_seconds) + 1
    ) * cycle_seconds
    if abs(holding_seconds - first_eligible_cycle) <= tolerance_seconds:
        return REASON_HOLD_MINIMUM_EXPIRY
    return exit_reason


_MECHANISM_BY_DISPOSITION = {
    FRESH: MECHANISM_WHIPSAW,
    STALE_PRESERVED: MECHANISM_UNKNOWN,
    STALE_DROPPED: MECHANISM_EXPIRED,
    FALLBACK_FILTERED: "fallback_filtered",
    ENTRY_FRESHNESS_FILTERED: "entry_freshness_filtered",
    BELOW_ENTRY_GATE: "below_entry_gate",
}

_DESCRIPTION_BY_DISPOSITION = {
    FRESH: (
        "S4 signal reached the portfolio engine fresh and is not driving a position "
        "— rank cutoff, min_score or a portfolio constraint"
    ),
    STALE_PRESERVED: (
        "S4 signal was stale but FIX-D re-admitted it this cycle — open position, no "
        "counter-signal — and the weight is 0 anyway: the mechanism that zeroed it is "
        "not recorded, so this exit is NOT a signal expiry, see #184"
    ),
    STALE_DROPPED: "S4 signal discarded for age this cycle — FIX-D did not preserve it",
    FALLBACK_FILTERED: "S4 signal excluded from the ranking as FinBERT fallback, #108",
    ENTRY_FRESHNESS_FILTERED: "S4 signal excluded by the news-freshness entry gate, #150",
    BELOW_ENTRY_GATE: "S4 signal fell below the active feedback entry threshold",
}

_NO_OBSERVATION = (
    "the S4 cycle recorded no disposition for this symbol — strategy inactive, symbol "
    "outside the S4 universe, or signal load failed"
)


def mechanism_for_disposition(disposition: str | None) -> str:
    """Map an observed disposition to the exit_mechanism label.

    Unknown or missing disposition → MECHANISM_UNKNOWN. Never infers from a clock.
    """
    if disposition is None:
        return MECHANISM_UNKNOWN
    return _MECHANISM_BY_DISPOSITION.get(disposition, MECHANISM_UNKNOWN)


def describe_disposition(disposition: str | None) -> str:
    """Human-readable clause for the decision-log reason text."""
    if disposition is None:
        return _NO_OBSERVATION
    return _DESCRIPTION_BY_DISPOSITION.get(disposition, _NO_OBSERVATION)
