"""#242 — characterization of the wall-clock semantics of `_filter_stale_signals`.

These tests do NOT assert what the exit rule *should* be. They pin the behaviour
**as it is today**, so that the flip to the D+2 shadow horizon (trial exit S4,
#293) cannot happen silently: the day someone changes the clock, these tests go
red and force an explicit decision.

The fact being pinned — F-024 in `docs/evidence/findings.json`:

    age_seconds = (now_utc - sig.generated_at).total_seconds()
    if age_seconds > max_age_hours * 3600:   # max_signal_age_hours = 4

is a **solar-hours** comparison. For a late-session entry the four nominal hours
of signal life are consumed almost entirely by the overnight close, so the
position is liquidated at the first useful cycle of the next day without ever
having lived a second of open market. Reference case IBM (issue #242):
entry 2026-08-11 19:07 UTC, first cycle of the next session 2026-08-12 14:22 UTC,
age 19.25h > 4h → stale (realised −26.47 $, then +13.71 $ left on the table).

The counterpart test — the one that must FAIL until the session clock lands —
belongs to #297, not here. Nothing in this file may be turned into that test.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.models.signals import SentimentResult
from src.workers.portfolio_scheduler import _filter_stale_signals

MAX_AGE_HOURS = 4


def _signal_at(symbol: str, generated_at: datetime, score: float = 0.5) -> SentimentResult:
    """A SentimentResult pinned to an absolute generated_at (no `now` involved)."""
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=0.8,
        reasoning="characterization #242",
        model_id="ensemble",
        ensemble_std=0.0,
        fallback_used=False,
        generated_at=generated_at,
    )


class TestWallClockStalenessIsCharacterized:
    """`_filter_stale_signals` measures solar hours, and the overnight counts."""

    def test_ibm_case_is_stale_at_the_first_cycle_of_the_next_session(self):
        """Entry 19:07 UTC, first cycle 14:22 UTC next day: age 19.25h > 4h → stale."""
        entry = datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc)
        first_cycle_next_day = datetime(2026, 8, 12, 14, 22, tzinfo=timezone.utc)

        age_hours = (first_cycle_next_day - entry).total_seconds() / 3600.0
        assert age_hours == 19.25, "the IBM case is 19h15m of solar time"

        sig = _signal_at("IBM", entry)
        fresh, stale = _filter_stale_signals(
            [sig], max_age_hours=MAX_AGE_HOURS, now_utc=first_cycle_next_day
        )

        assert sig in stale, (
            "as-is behaviour: the signal is stale at the first cycle of the next "
            "session. Changing this is the #297 session-clock flip, not a bugfix."
        )
        assert fresh == []

    def test_market_was_open_for_less_than_one_of_the_four_nominal_hours(self):
        """Of the 4h of signal life, a 19:07 UTC entry gets <1h of open market.

        RTH close is 20:00 UTC (21:00 UTC on a US winter date; August is DST, so
        20:00). The signal nominally expires at 23:07 UTC — three of its four
        hours are burnt with the market shut.
        """
        entry = datetime(2026, 8, 11, 19, 7, tzinfo=timezone.utc)
        rth_close = datetime(2026, 8, 11, 20, 0, tzinfo=timezone.utc)
        nominal_expiry = entry + timedelta(hours=MAX_AGE_HOURS)

        open_market_life = (rth_close - entry).total_seconds() / 3600.0
        assert open_market_life < 1.0, "less than one hour of open market"
        assert nominal_expiry > rth_close, "the signal outlives the session it was born in"

        # And at 23:07 UTC — market shut — it is already exactly at the boundary.
        sig = _signal_at("IBM", entry)
        fresh, _ = _filter_stale_signals(
            [sig], max_age_hours=MAX_AGE_HOURS, now_utc=nominal_expiry
        )
        assert fresh == [sig], "at exactly max_age the signal is still fresh (`>`, not `>=`)"

    def test_a_weekend_ages_a_friday_signal_with_zero_sessions_elapsed(self):
        """Friday 19:07 → Monday 14:22 is 91.25h of nothing: no session in between."""
        friday = datetime(2026, 8, 7, 19, 7, tzinfo=timezone.utc)
        monday_first_cycle = datetime(2026, 8, 10, 14, 22, tzinfo=timezone.utc)

        sig = _signal_at("SONY", friday)
        _, stale = _filter_stale_signals(
            [sig], max_age_hours=MAX_AGE_HOURS, now_utc=monday_first_cycle
        )
        assert sig in stale, "the weekend alone is enough to expire the thesis"

    def test_the_gate_ignores_score_so_a_still_positive_thesis_expires(self):
        """Staleness is purely temporal: a +0.35 score expires like a −0.9 one.

        This is the HOOD case observed on 2026-08-20 (age=22.4h, score=+0.350,
        no counter-signal): the thesis was never contradicted, only unrepeated.
        """
        generated = datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc)
        now = generated + timedelta(hours=22.4)

        strong = _signal_at("HOOD", generated, score=+0.350)
        weak = _signal_at("HOOD2", generated, score=-0.900)
        fresh, stale = _filter_stale_signals(
            [strong, weak], max_age_hours=MAX_AGE_HOURS, now_utc=now
        )

        assert fresh == [], "the gate reads no score at all"
        assert strong in stale and weak in stale

    def test_clock_skew_into_the_future_is_not_stale(self):
        """A slightly-future generated_at is age<=0, hence fresh — not an error."""
        now = datetime(2026, 8, 12, 14, 22, tzinfo=timezone.utc)
        sig = _signal_at("AAPL", now + timedelta(minutes=3))
        fresh, stale = _filter_stale_signals([sig], max_age_hours=MAX_AGE_HOURS, now_utc=now)
        assert fresh == [sig] and stale == []
