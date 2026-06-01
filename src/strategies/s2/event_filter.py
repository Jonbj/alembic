"""S2 strategy: event risk filter.

Blocks new positions when:
  - SPY sentiment is very bearish (< sentiment_block_threshold)
  - as_of is within pre_event_block_days of a major macro event (FOMC or NFP)

FOMC dates are approximated as the 3rd Wednesday of Jan/Mar/May/Jun/Jul/Sep/Oct/Dec.
NFP dates are the first Friday of each month.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from src.strategies.s2.config import S2Config

_FOMC_MONTHS = frozenset({1, 3, 5, 6, 7, 9, 10, 12})


def compute_nfp_date(year: int, month: int) -> date:
    """Return the first Friday of the given month (NFP release day)."""
    d = date(year, month, 1)
    days_ahead = 4 - d.weekday()  # Friday = weekday 4
    if days_ahead < 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


def _compute_fomc_date(year: int, month: int) -> date:
    """Return the 3rd Wednesday of the given month (approximate FOMC date)."""
    d = date(year, month, 1)
    days_ahead = 2 - d.weekday()  # Wednesday = weekday 2
    if days_ahead < 0:
        days_ahead += 7
    first_wed = d + timedelta(days=days_ahead)
    return first_wed + timedelta(weeks=2)


def is_nfp_day(d: date) -> bool:
    """Return True if d is the NFP release day (first Friday of its month)."""
    return d == compute_nfp_date(d.year, d.month)


def is_fomc_day(d: date) -> bool:
    """Return True if d is an approximate FOMC date (3rd Wed of FOMC months)."""
    if d.month not in _FOMC_MONTHS:
        return False
    return d == _compute_fomc_date(d.year, d.month)


def is_near_nfp(d: date, days: int = 1) -> bool:
    """Return True if d is within `days` days of (and including) the NFP day."""
    for delta in range(0, days + 1):
        if is_nfp_day(d + timedelta(days=delta)):
            return True
    return False


def is_near_fomc(d: date, days: int = 1) -> bool:
    """Return True if d is within `days` days of (and including) any FOMC date."""
    for delta in range(0, days + 1):
        if is_fomc_day(d + timedelta(days=delta)):
            return True
    return False


@dataclass
class EventFilterResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def check_event_filter(
    as_of: date,
    spy_sentiment: Optional[float] = None,
    config: Optional[S2Config] = None,
) -> EventFilterResult:
    """Return whether a new position is allowed given event risk.

    Blocks when:
      - event_filter_enabled is True (default), AND
      - SPY sentiment < sentiment_block_threshold, OR as_of is near FOMC/NFP
    """
    cfg = config or S2Config()

    if not cfg.event_filter_enabled:
        return EventFilterResult(allowed=True)

    reasons: list[str] = []

    if spy_sentiment is not None and spy_sentiment < cfg.sentiment_block_threshold:
        reasons.append(
            f"SPY sentiment {spy_sentiment:.2f} below threshold {cfg.sentiment_block_threshold}"
        )

    if is_near_fomc(as_of, cfg.pre_event_block_days):
        reasons.append(f"Within {cfg.pre_event_block_days}d of FOMC (as_of={as_of})")

    if is_near_nfp(as_of, cfg.pre_event_block_days):
        reasons.append(f"Within {cfg.pre_event_block_days}d of NFP (as_of={as_of})")

    return EventFilterResult(allowed=len(reasons) == 0, reasons=reasons)
