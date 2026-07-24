"""Authoritative market context for the mobile operational-state projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from src.mobile_monitoring.models import MarketPhase

MARKET_TIMEZONE = "America/New_York"
_ET = ZoneInfo(MARKET_TIMEZONE)


@dataclass(frozen=True)
class MarketContext:
    """Schedule context derived from the broker clock and calendar."""

    phase: MarketPhase
    pipeline_expected: bool
    next_activity_at: datetime | None


def _aware_datetime(
    value: datetime | time | None,
    session_date: date,
) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, time):
        result = datetime.combine(session_date, value)
    else:
        result = value
    if result.tzinfo is None:
        result = result.replace(tzinfo=_ET)
    return result


def resolve_market_context(
    *,
    as_of: datetime,
    clock: Any,
    sessions: Iterable[Any],
) -> MarketContext:
    """Resolve current phase without static weekday-only trading assumptions."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    next_open = getattr(clock, "next_open", None)
    if bool(getattr(clock, "is_open", False)):
        return MarketContext(
            phase=MarketPhase.OPEN,
            pipeline_expected=True,
            next_activity_at=getattr(clock, "next_close", None),
        )

    local_date = as_of.astimezone(_ET).date()
    session = next(
        (
            item
            for item in sessions
            if getattr(item, "date", local_date) == local_date
        ),
        None,
    )
    if session is None:
        phase = MarketPhase.HOLIDAY if local_date.weekday() < 5 else MarketPhase.CLOSED
        return MarketContext(
            phase=phase,
            pipeline_expected=False,
            next_activity_at=next_open,
        )

    session_date = getattr(session, "date", local_date)
    opened_at = _aware_datetime(getattr(session, "open", None), session_date)
    closed_at = _aware_datetime(getattr(session, "close", None), session_date)
    if opened_at is not None and as_of < opened_at:
        return MarketContext(
            phase=MarketPhase.PRE_MARKET,
            pipeline_expected=False,
            next_activity_at=opened_at,
        )
    if closed_at is not None and as_of >= closed_at:
        return MarketContext(
            phase=MarketPhase.AFTER_HOURS,
            pipeline_expected=False,
            next_activity_at=next_open,
        )
    return MarketContext(
        phase=MarketPhase.CLOSED,
        pipeline_expected=False,
        next_activity_at=next_open,
    )
