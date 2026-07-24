"""Market-aware operational context tests."""

from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.mobile_monitoring.builder import _pipeline_activity_component
from src.mobile_monitoring.models import Freshness, MarketPhase
from src.mobile_monitoring.state import resolve_market_context

ET = ZoneInfo("America/New_York")


def _clock(*, is_open=False, next_open=None, next_close=None):
    return SimpleNamespace(
        is_open=is_open,
        next_open=next_open,
        next_close=next_close,
    )


def _session(day: date, opened: time, closed: time):
    return SimpleNamespace(date=day, open=opened, close=closed)


@pytest.mark.parametrize(
    ("as_of", "sessions", "expected"),
    [
        (
            datetime(2026, 7, 25, 15, tzinfo=timezone.utc),
            [],
            MarketPhase.CLOSED,
        ),
        (
            datetime(2026, 7, 3, 15, tzinfo=timezone.utc),
            [],
            MarketPhase.HOLIDAY,
        ),
        (
            datetime(2026, 7, 2, 12, tzinfo=timezone.utc),
            [_session(date(2026, 7, 2), time(9, 30), time(13, 0))],
            MarketPhase.PRE_MARKET,
        ),
        (
            datetime(2026, 7, 2, 18, tzinfo=timezone.utc),
            [_session(date(2026, 7, 2), time(9, 30), time(13, 0))],
            MarketPhase.AFTER_HOURS,
        ),
    ],
)
def test_closed_phases_are_market_calendar_aware(as_of, sessions, expected) -> None:
    context = resolve_market_context(
        as_of=as_of,
        clock=_clock(next_open=datetime(2026, 7, 6, 13, 30, tzinfo=timezone.utc)),
        sessions=sessions,
    )

    assert context.phase == expected
    assert context.pipeline_expected is False


@pytest.mark.parametrize(
    "as_of",
    [
        datetime(2026, 3, 6, 15, tzinfo=timezone.utc),
        datetime(2026, 3, 9, 14, tzinfo=timezone.utc),
    ],
)
def test_open_clock_remains_authoritative_across_dst_transition(as_of) -> None:
    context = resolve_market_context(
        as_of=as_of,
        clock=_clock(
            is_open=True,
            next_close=as_of.astimezone(ET).replace(hour=16),
        ),
        sessions=[],
    )

    assert context.phase == MarketPhase.OPEN
    assert context.pipeline_expected is True


@pytest.mark.parametrize(
    ("age_seconds", "expected_status", "degraded"),
    [
        (900, Freshness.FRESH, False),
        (901, Freshness.AGING, True),
        (1380, Freshness.AGING, True),
        (1381, Freshness.STALE, True),
        (None, Freshness.UNKNOWN, True),
    ],
)
def test_expected_activity_uses_schedule_plus_eight_minute_grace(
    age_seconds,
    expected_status,
    degraded,
) -> None:
    degradations = []

    component = _pipeline_activity_component(
        component="signal",
        age_seconds=age_seconds,
        pipeline_expected=True,
        interval_seconds=900,
        grace_seconds=480,
        degradations=degradations,
    )

    assert component.status == expected_status
    assert component.freshness_budget_seconds == 900
    assert component.stale_after_seconds == 1380
    assert bool(degradations) is degraded
