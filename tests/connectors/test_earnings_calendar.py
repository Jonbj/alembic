"""EarningsCalendarProvider: structured actual-vs-consensus EPS from Finnhub."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.earnings_calendar import EarningsCalendarProvider, EarningsEvent


class TestSurprisePct:
    def test_beat(self):
        assert EarningsEvent("AAPL", "2026-07-01", 1.5, 1.0).surprise_pct == 0.5

    def test_miss(self):
        assert EarningsEvent("X", "d", 0.9, 1.0).surprise_pct == pytest.approx(-0.1)

    def test_none_when_missing_or_zero(self):
        assert EarningsEvent("X", "d", None, 1.0).surprise_pct is None
        assert EarningsEvent("X", "d", 1.0, None).surprise_pct is None
        assert EarningsEvent("X", "d", 1.0, 0.0).surprise_pct is None  # zero estimate → no div


def test_parse_row_coerces_types_and_uppercases():
    ev = EarningsCalendarProvider._parse(
        {"symbol": "nvda", "date": "2026-07-01", "epsActual": "1.2", "epsEstimate": "1.0", "hour": "amc"}
    )
    assert ev.symbol == "NVDA"
    assert ev.eps_actual == 1.2 and ev.eps_estimate == 1.0
    assert ev.hour == "amc"


@pytest.mark.asyncio
async def test_fetch_parses_calendar():
    payload = {"earningsCalendar": [
        {"symbol": "AAPL", "date": "2026-07-01", "epsActual": 1.5, "epsEstimate": 1.0, "hour": "amc"},
        {"symbol": "", "date": "2026-07-01"},  # no symbol → dropped
    ]}
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=payload)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("src.connectors.earnings_calendar.aiohttp.ClientSession", return_value=mock_session):
        events = await EarningsCalendarProvider("k").fetch("2026-06-30", "2026-07-02")

    assert len(events) == 1
    assert events[0].symbol == "AAPL" and events[0].surprise_pct == 0.5


@pytest.mark.asyncio
async def test_fetch_fail_open_on_error():
    with patch("src.connectors.earnings_calendar.aiohttp.ClientSession", side_effect=RuntimeError("net")):
        assert await EarningsCalendarProvider("k").fetch("2026-06-30", "2026-07-02") == []
