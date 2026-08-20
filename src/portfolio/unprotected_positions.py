"""Which held positions carry no broker-side stop, and which ones *cannot* (#161).

Alpaca accepts a stop order only on at least 1 whole share, so a position below
1 share is unprotectable **by construction** — no reconciliation cycle will ever
give it a floor. Until #161 the system did not represent that distinction
anywhere: a sub-1-share position looked exactly like a protected one, and on
2026-07-28 the whole of the book's red P&L (-$452 against +$660) sat in the 13
positions on the wrong side of that line, unseen.

This module only *classifies* and *formats*. It changes no order, no size and no
gate: it is instrumentation for the surveillance decided by the operator on
2026-08-06 (option 3 of #161). The structural fix — a minimum entry size of 1
share — is tuning and stays frozen until 2026-09-28 (issue #171).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

# Plan actions that leave the symbol without a live broker stop after the cycle's
# reconciliation, mapped to the status reported for it.
_UNPROTECTED_ACTIONS = {
    "skip_no_whole_share": "sub_one_share",
    "skip_insufficient_qty": "stop_pending_qty",
}


@dataclass(frozen=True)
class PositionProtection:
    """Protection state of one held position after this cycle's stop sync.

    protectable — a broker stop is possible at all (qty >= 1 whole share)
    protected   — a stop order is live (or was just created/replaced) for it
    """

    symbol: str
    qty: float
    protectable: bool
    protected: bool
    status: str  # "protected" | "sub_one_share" | "stop_pending_qty" | "stop_sync_failed"
    loss_pct: float | None  # unrealized return as a fraction; negative = loss
    market_value: float | None = None  # broker figure, None when not reported
    unrealized_pl: float | None = None  # broker figure, in dollars


def _num(value) -> float | None:
    """Alpaca returns numbers as str/Decimal — coerce, tolerating None/garbage."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _loss_pct(position) -> float | None:
    """Unrealized return of the position, preferring the broker's own figure."""
    plpc = _num(getattr(position, "unrealized_plpc", None))
    if plpc is not None:
        return plpc
    entry = _num(getattr(position, "avg_entry_price", None))
    price = _num(getattr(position, "current_price", None))
    if entry is None or price is None or entry <= 0:
        return None
    return price / entry - 1.0


def classify_protection(
    positions: Sequence,
    plans: Sequence,
    failed_symbols: Iterable[str] = (),
) -> list[PositionProtection]:
    """Classify each held position against the stop plans just executed for it.

    `plans` are the ProtectiveStopPlan objects from build_protective_stop_plans
    and `failed_symbols` the symbols whose broker call errored in
    execute_protective_stop_plans — a created/replaced stop that the broker
    rejected leaves the position unprotected, so it must not be reported as safe.

    Plans without a matching position (cancel_orphan) are ignored: they describe
    a position that no longer exists.
    """
    failed = set(failed_symbols)
    action_by_symbol = {p.symbol: p.action for p in plans}
    rows: list[PositionProtection] = []

    for position in positions:
        symbol = getattr(position, "symbol", None)
        if symbol is None:
            continue
        qty = abs(_num(getattr(position, "qty", None)) or 0.0)
        # Fall back to the qty when no plan covers the symbol: a missing plan must
        # not turn an unprotectable position into a silently "protected" one.
        action = action_by_symbol.get(symbol, "skip_no_whole_share" if qty < 1 else "noop")

        if action in _UNPROTECTED_ACTIONS:
            status = _UNPROTECTED_ACTIONS[action]
        elif symbol in failed:
            status = "stop_sync_failed"
        else:
            status = "protected"

        rows.append(
            PositionProtection(
                symbol=symbol,
                qty=qty,
                protectable=qty >= 1.0,
                protected=status == "protected",
                status=status,
                loss_pct=_loss_pct(position),
                market_value=_num(getattr(position, "market_value", None)),
                unrealized_pl=_num(getattr(position, "unrealized_pl", None)),
            )
        )
    return rows


def select_unprotected_alerts(
    rows: Sequence[PositionProtection], loss_threshold_pct: float
) -> list[PositionProtection]:
    """Unprotected positions whose loss is at or past the threshold, worst first.

    A position with no usable price information is never selected: an alert
    without a measured loss would be noise, not surveillance.
    """
    selected = [
        r
        for r in rows
        if not r.protected and r.loss_pct is not None and r.loss_pct <= -abs(loss_threshold_pct)
    ]
    return sorted(selected, key=lambda r: r.loss_pct)


def format_unprotected_alert(row: PositionProtection, loss_threshold_pct: float) -> str:
    """Telegram message for one unprotected position past the threshold."""
    if row.status == "sub_one_share":
        why = "sub-1-share position (qty < 1) — a broker stop is impossible here (#161)"
    elif row.status == "stop_pending_qty":
        why = "qty >= 1 but the shares are reserved by another open order — stop retried next cycle (#161)"
    else:
        why = "qty >= 1 and a stop was expected: stop sync failed, position currently unprotected (#161)"
    return (
        f"⚠️ Unprotected position past -{abs(loss_threshold_pct):.0%}: "
        f"{row.symbol} {row.loss_pct:.1%} (qty {row.qty:.4f}) — {why}"
    )


@dataclass(frozen=True)
class SleeveTotals:
    """How much of the book sits on one side of the 1-share line."""

    n: int
    market_value: float
    unrealized_pl: float


@dataclass(frozen=True)
class ProtectionSummary:
    """The book split in two sleeves, protectable and not.

    `unprotectable_value_share` is None on an empty book rather than 0.0: no
    position at all is not the same statement as "no unprotectable exposure".
    """

    protectable: SleeveTotals
    unprotectable: SleeveTotals
    unprotectable_value_share: float | None


def _totals(rows: Sequence[PositionProtection]) -> SleeveTotals:
    return SleeveTotals(
        n=len(rows),
        market_value=sum(r.market_value or 0.0 for r in rows),
        unrealized_pl=sum(r.unrealized_pl or 0.0 for r in rows),
    )


def summarize_protection(rows: Sequence[PositionProtection]) -> ProtectionSummary:
    """Aggregate the classified book into the protectable / unprotectable sleeves.

    The per-symbol alert answers "is this position bleeding past -15% with no
    floor under it". It cannot answer the question the operator's 2026-08-06
    decision on #161 actually reserved the right to reopen on — whether the red
    in the unprotectable sleeve *as a whole* is widening — because that is a
    statement about a sum, not about any one symbol. This computes that sum.

    A position the broker reported without market_value or unrealized_pl counts
    as zero in the totals instead of raising: a missing figure must not cost the
    whole measurement, and the position is still counted in `n`.
    """
    protectable = [r for r in rows if r.protectable]
    unprotectable = [r for r in rows if not r.protectable]
    prot, unprot = _totals(protectable), _totals(unprotectable)

    total_value = prot.market_value + unprot.market_value
    share = unprot.market_value / total_value if total_value else None

    return ProtectionSummary(
        protectable=prot, unprotectable=unprot, unprotectable_value_share=share
    )
