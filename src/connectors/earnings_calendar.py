"""Earnings calendar/surprise provider — Finnhub /calendar/earnings.

This is the CORRECT source for the PEAD surprise number: an 8-K earnings filing reports
the ACTUAL EPS but not the analyst CONSENSUS, so the surprise cannot be extracted from
the filing text (which is why S7 was starved — surprise_pct came back None). Finnhub's
earnings calendar returns both actual and estimate EPS keyed by ticker + report date, so
we compute the surprise deterministically (no LLM needed for the number). Free tier.

Docs: https://finnhub.io/docs/api/earnings-calendar
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

_FINNHUB_EARNINGS_URL = "https://finnhub.io/api/v1/calendar/earnings"


def _to_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class EarningsEvent:
    """One reported (or upcoming) earnings event from the calendar."""
    symbol: str
    date: str                       # report date, YYYY-MM-DD
    eps_actual: float | None
    eps_estimate: float | None
    hour: str = ""                  # bmo | amc | dmh

    @property
    def surprise_pct(self) -> float | None:
        """(actual − estimate) / |estimate|. None if either side is missing/zero."""
        if self.eps_actual is None or not self.eps_estimate:
            return None
        return (self.eps_actual - self.eps_estimate) / abs(self.eps_estimate)


class EarningsCalendarProvider:
    """Fetch the earnings calendar (actual + estimate EPS) from Finnhub."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def fetch(self, from_date: str, to_date: str) -> list[EarningsEvent]:
        """Return earnings events between from_date and to_date (YYYY-MM-DD). Fail-open."""
        params = {"from": from_date, "to": to_date, "token": self._api_key}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(_FINNHUB_EARNINGS_URL, params=params) as resp:
                    if resp.status != 200:
                        logger.warning("Finnhub earnings calendar returned %d", resp.status)
                        return []
                    data = await resp.json()
        except Exception as exc:
            logger.warning("Finnhub earnings calendar fetch failed: %s", exc)
            return []
        return [
            self._parse(row)
            for row in (data.get("earningsCalendar") or [])
            if row.get("symbol")
        ]

    @staticmethod
    def _parse(row: dict) -> EarningsEvent:
        return EarningsEvent(
            symbol=str(row.get("symbol", "")).upper(),
            date=str(row.get("date", "")),
            eps_actual=_to_float(row.get("epsActual")),
            eps_estimate=_to_float(row.get("epsEstimate")),
            hour=str(row.get("hour", "")),
        )
