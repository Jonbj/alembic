"""Tests for T-307: S2 event filter (sentiment + economic calendar)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.strategies.s2.config import S2Config
from src.strategies.s2.event_filter import (
    EventFilterResult,
    check_event_filter,
    compute_nfp_date,
    is_fomc_day,
    is_near_fomc,
    is_near_nfp,
    is_nfp_day,
)

# ---------------------------------------------------------------------------
# EventFilterResult dataclass
# ---------------------------------------------------------------------------


class TestEventFilterResultDataclass:
    def test_allowed_true_with_empty_reasons(self) -> None:
        r = EventFilterResult(allowed=True, reasons=[])
        assert r.allowed is True
        assert r.reasons == []

    def test_allowed_false_with_reason(self) -> None:
        r = EventFilterResult(allowed=False, reasons=["blocked by sentiment"])
        assert r.allowed is False
        assert "blocked by sentiment" in r.reasons

    def test_reasons_defaults_to_empty_list(self) -> None:
        r = EventFilterResult(allowed=True)
        assert isinstance(r.reasons, list)
        assert r.reasons == []


# ---------------------------------------------------------------------------
# S2Config new event filter fields
# ---------------------------------------------------------------------------


class TestS2ConfigEventFilterFields:
    def test_sentiment_block_threshold_default(self) -> None:
        assert S2Config().sentiment_block_threshold == -0.5

    def test_pre_event_block_days_default(self) -> None:
        assert S2Config().pre_event_block_days == 1

    def test_event_filter_enabled_default(self) -> None:
        assert S2Config().event_filter_enabled is True


# ---------------------------------------------------------------------------
# compute_nfp_date — first Friday of month
# ---------------------------------------------------------------------------


class TestComputeNfpDate:
    def test_january_2024_first_friday_is_jan_5(self) -> None:
        # Jan 1 2024 = Monday → first Friday = Jan 5
        assert compute_nfp_date(2024, 1) == date(2024, 1, 5)

    def test_february_2024_first_friday_is_feb_2(self) -> None:
        # Feb 1 2024 = Thursday → first Friday = Feb 2
        assert compute_nfp_date(2024, 2) == date(2024, 2, 2)

    def test_march_2024_first_friday_is_mar_1(self) -> None:
        # Mar 1 2024 = Friday → first Friday = Mar 1
        assert compute_nfp_date(2024, 3) == date(2024, 3, 1)

    def test_may_2024_first_friday_is_may_3(self) -> None:
        # May 1 2024 = Wednesday → first Friday = May 3
        assert compute_nfp_date(2024, 5) == date(2024, 5, 3)

    def test_result_is_always_a_friday(self) -> None:
        for month in range(1, 13):
            d = compute_nfp_date(2024, month)
            assert d.weekday() == 4, f"Expected Friday for month {month}, got {d.strftime('%A')}"


# ---------------------------------------------------------------------------
# is_nfp_day
# ---------------------------------------------------------------------------


class TestIsNfpDay:
    def test_nfp_day_returns_true(self) -> None:
        assert is_nfp_day(date(2024, 1, 5)) is True

    def test_day_before_nfp_returns_false(self) -> None:
        assert is_nfp_day(date(2024, 1, 4)) is False

    def test_day_after_nfp_returns_false(self) -> None:
        assert is_nfp_day(date(2024, 1, 6)) is False


# ---------------------------------------------------------------------------
# is_fomc_day — 3rd Wednesday of FOMC months (Jan/Mar/May/Jun/Jul/Sep/Oct/Dec)
# ---------------------------------------------------------------------------


class TestIsFomcDay:
    def test_third_wednesday_of_january_2024(self) -> None:
        # Jan 1=Mon, first Wed=Jan 3, third Wed=Jan 17
        assert is_fomc_day(date(2024, 1, 17)) is True

    def test_third_wednesday_of_march_2024(self) -> None:
        # Mar 1=Fri, first Wed=Mar 6, third Wed=Mar 20
        assert is_fomc_day(date(2024, 3, 20)) is True

    def test_third_wednesday_of_june_2024(self) -> None:
        # Jun 1=Sat, first Wed=Jun 5, third Wed=Jun 19
        assert is_fomc_day(date(2024, 6, 19)) is True

    def test_non_fomc_day_of_fomc_month_returns_false(self) -> None:
        assert is_fomc_day(date(2024, 1, 16)) is False

    def test_non_fomc_month_returns_false(self) -> None:
        # February is not an FOMC month; even the 3rd Wednesday returns False
        assert is_fomc_day(date(2024, 2, 21)) is False


# ---------------------------------------------------------------------------
# is_near_nfp — within N days of (and including) NFP day
# ---------------------------------------------------------------------------


class TestIsNearNfp:
    def test_nfp_day_with_days_1_returns_true(self) -> None:
        nfp = date(2024, 1, 5)
        assert is_near_nfp(nfp, days=1) is True

    def test_one_day_before_nfp_with_days_1_returns_true(self) -> None:
        nfp = date(2024, 1, 5)
        assert is_near_nfp(nfp - timedelta(days=1), days=1) is True

    def test_two_days_before_nfp_with_days_1_returns_false(self) -> None:
        nfp = date(2024, 1, 5)
        assert is_near_nfp(nfp - timedelta(days=2), days=1) is False


# ---------------------------------------------------------------------------
# is_near_fomc — within N days of (and including) any FOMC date
# ---------------------------------------------------------------------------


class TestIsNearFomc:
    def test_fomc_day_with_days_1_returns_true(self) -> None:
        fomc = date(2024, 1, 17)
        assert is_near_fomc(fomc, days=1) is True

    def test_one_day_before_fomc_with_days_1_returns_true(self) -> None:
        fomc = date(2024, 1, 17)
        assert is_near_fomc(fomc - timedelta(days=1), days=1) is True

    def test_two_days_before_fomc_with_days_1_returns_false(self) -> None:
        fomc = date(2024, 1, 17)
        assert is_near_fomc(fomc - timedelta(days=2), days=1) is False


# ---------------------------------------------------------------------------
# check_event_filter — sentiment gating
# ---------------------------------------------------------------------------


class TestCheckEventFilterSentiment:
    # Jun 3 2024: FOMC=Jun 19, NFP=Jun 7 — safely clear of both events
    _CLEAR_DATE = date(2024, 6, 3)

    def test_sentiment_below_threshold_blocks(self) -> None:
        result = check_event_filter(self._CLEAR_DATE, spy_sentiment=-0.6)
        assert result.allowed is False

    def test_sentiment_above_threshold_allows(self) -> None:
        result = check_event_filter(self._CLEAR_DATE, spy_sentiment=0.1)
        assert result.allowed is True

    def test_sentiment_at_threshold_allows(self) -> None:
        # spec: < -0.5 blocks; >= -0.5 allows
        result = check_event_filter(self._CLEAR_DATE, spy_sentiment=-0.5)
        assert result.allowed is True

    def test_none_sentiment_does_not_block(self) -> None:
        result = check_event_filter(self._CLEAR_DATE, spy_sentiment=None)
        assert result.allowed is True

    def test_blocked_result_carries_reason(self) -> None:
        result = check_event_filter(self._CLEAR_DATE, spy_sentiment=-0.9)
        assert len(result.reasons) > 0

    def test_custom_threshold_respected(self) -> None:
        cfg = S2Config(sentiment_block_threshold=-0.3)
        result = check_event_filter(self._CLEAR_DATE, spy_sentiment=-0.4, config=cfg)
        assert result.allowed is False


# ---------------------------------------------------------------------------
# check_event_filter — economic calendar gating
# ---------------------------------------------------------------------------


class TestCheckEventFilterCalendar:
    def test_day_before_fomc_blocks(self) -> None:
        # Jan 17 2024 is FOMC → Jan 16 is 1 day before
        result = check_event_filter(date(2024, 1, 16))
        assert result.allowed is False

    def test_nfp_day_blocks(self) -> None:
        # Jan 5 2024 is the first Friday (NFP day)
        result = check_event_filter(date(2024, 1, 5))
        assert result.allowed is False

    def test_normal_day_allows(self) -> None:
        # Jun 3 2024: FOMC on Jun 19, NFP on Jun 7 — not near either
        result = check_event_filter(date(2024, 6, 3))
        assert result.allowed is True

    def test_calendar_block_carries_reason(self) -> None:
        result = check_event_filter(date(2024, 1, 16))
        assert len(result.reasons) > 0


# ---------------------------------------------------------------------------
# check_event_filter — disabled via config
# ---------------------------------------------------------------------------


class TestCheckEventFilterDisabled:
    def test_disabled_allows_when_sentiment_would_block(self) -> None:
        cfg = S2Config(event_filter_enabled=False)
        result = check_event_filter(date(2024, 6, 3), spy_sentiment=-0.9, config=cfg)
        assert result.allowed is True

    def test_disabled_allows_on_fomc_pre_window(self) -> None:
        cfg = S2Config(event_filter_enabled=False)
        result = check_event_filter(date(2024, 1, 16), config=cfg)
        assert result.allowed is True


# ---------------------------------------------------------------------------
# check_event_filter — multiple blocking conditions
# ---------------------------------------------------------------------------


class TestCheckEventFilterMultipleConditions:
    def test_both_sentiment_and_calendar_blocked_has_multiple_reasons(self) -> None:
        # Jan 4 2024: 1 day before NFP (Jan 5), plus bad sentiment
        result = check_event_filter(date(2024, 1, 4), spy_sentiment=-0.8)
        assert result.allowed is False
        assert len(result.reasons) >= 2

    def test_only_sentiment_blocked_has_exactly_one_reason(self) -> None:
        # Jun 3 2024: clear of events — only sentiment blocks
        result = check_event_filter(date(2024, 6, 3), spy_sentiment=-0.9)
        assert result.allowed is False
        assert len(result.reasons) == 1
