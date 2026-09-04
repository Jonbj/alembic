"""Misura dei catalizzatori alternativi sui ticker senza news (#409).

Il blocco e' solo osservazionale: rende confrontabili mover e non-mover a zero
righe ``news_log``, senza scegliere una soglia sul volume e senza produrre
segnali. Il volume giornaliero e' noto soltanto a fine seduta, quindi resta
esplicitamente non valido per valutare un backstop point-in-time.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Iterable


BACKSTOP_VERSION = "no_news_backstop_v1"
POST_HOC_EOD = "POST_HOC_EOD"


def _calendar(
    corporate_events: list[dict] | dict | None,
) -> dict[str, Any]:
    if isinstance(corporate_events, dict):
        return {
            "events": list(corporate_events.get("events") or []),
            "sources_succeeded": list(
                corporate_events.get("sources_succeeded") or []
            ),
            "complete": bool(corporate_events.get("complete")),
            "missingness": list(corporate_events.get("missingness") or []),
        }
    if corporate_events is not None:
        events = list(corporate_events)
        return {
            "events": events,
            "sources_succeeded": sorted(
                {
                    str(event.get("source") or "UNKNOWN")
                    for event in events
                }
            ),
            "complete": True,
            "missingness": [],
        }
    return {
        "events": [],
        "sources_succeeded": [],
        "complete": False,
        "missingness": ["corporate_calendar_unavailable"],
    }


def _events_for_symbol(events: Iterable[dict], symbol: str) -> list[dict]:
    return sorted(
        (
            dict(event)
            for event in events
            if str(event.get("symbol") or event.get("ticker") or "").upper()
            == symbol
        ),
        key=lambda event: (
            str(event.get("event_date") or ""),
            str(event.get("event_type") or ""),
            str(event.get("source") or ""),
        ),
    )


def _volume(bar: dict | None) -> dict:
    bar = bar or {}
    session_volume = bar.get("volume")
    adv_20d = bar.get("adv_20d")
    missingness = []
    if session_volume is None:
        missingness.append("session_volume_missing")
    if adv_20d is None:
        missingness.append("adv_20d_missing")
    if adv_20d is not None and float(adv_20d) == 0.0:
        missingness.append("adv_20d_zero")
    ratio = (
        float(session_volume) / float(adv_20d)
        if session_volume is not None
        and adv_20d is not None
        and float(adv_20d) != 0.0
        else None
    )
    return {
        "session_volume": int(session_volume) if session_volume is not None else None,
        "adv_20d": float(adv_20d) if adv_20d is not None else None,
        "adv_ratio": ratio,
        "surprise": ratio - 1.0 if ratio is not None else None,
        "observed_at": "session_close",
        "temporal_validity": POST_HOC_EOD,
        "missingness": missingness,
    }


def _rate(numerator: int, denominator: int, *, known: bool = True) -> float | None:
    if not known or denominator == 0:
        return None
    return numerator / denominator


def _median(rows: list[dict[str, Any]], *, mover: bool) -> float | None:
    values = [
        row["volume"]["surprise"]
        for row in rows
        if row["is_mover"] is mover and row["volume"]["surprise"] is not None
    ]
    return statistics.median(values) if values else None


def build_no_news_backstop(
    *,
    universe: list[str],
    returns: dict[str, float],
    news_counts: dict[str, int],
    sector_by_ticker: dict[str, str],
    daily_bars: dict[str, dict],
    corporate_events: list[dict] | dict | None,
    mover_threshold: float,
) -> dict:
    """Costruisce il pannello read-only dei ticker a zero righe news."""
    calendar = _calendar(corporate_events)
    rows: list[dict[str, Any]] = []
    for raw_symbol in sorted(set(universe)):
        symbol = str(raw_symbol).upper()
        if int(news_counts.get(symbol, 0) or 0) != 0:
            continue
        symbol_return = returns.get(symbol)
        is_mover = (
            abs(float(symbol_return)) >= mover_threshold
            if symbol_return is not None
            else None
        )
        events = _events_for_symbol(calendar["events"], symbol)
        if events:
            calendar_status = "OBSERVED"
        elif calendar["complete"]:
            calendar_status = "NOT_OBSERVED"
        else:
            calendar_status = "UNKNOWN"
        rows.append(
            {
                "symbol": symbol,
                "sector": sector_by_ticker.get(symbol, "UNKNOWN"),
                "return": float(symbol_return) if symbol_return is not None else None,
                "is_mover": is_mover,
                "observed_catalysts": ["CALENDAR"] if events else [],
                "calendar": {
                    "status": calendar_status,
                    "event_types": sorted(
                        {str(event.get("event_type") or "UNKNOWN") for event in events}
                    ),
                    "sources": sorted(
                        {str(event.get("source") or "UNKNOWN") for event in events}
                    ),
                    "events": events,
                    "sources_succeeded": calendar["sources_succeeded"],
                    "missingness": calendar["missingness"],
                },
                "volume": _volume(daily_bars.get(symbol)),
            }
        )

    movers = [row for row in rows if row["is_mover"] is True]
    non_movers = [row for row in rows if row["is_mover"] is False]
    missing_returns = [row for row in rows if row["is_mover"] is None]
    calendar_movers = sum(
        row["calendar"]["status"] == "OBSERVED" for row in movers
    )
    calendar_non_movers = sum(
        row["calendar"]["status"] == "OBSERVED" for row in non_movers
    )

    sector_rows: dict[str, list[str]] = defaultdict(list)
    for raw_symbol in sorted(set(universe)):
        symbol = str(raw_symbol).upper()
        sector_rows[sector_by_ticker.get(symbol, "UNKNOWN")].append(symbol)
    measured_by_symbol = {row["symbol"]: row for row in rows}
    per_sector: dict[str, dict[str, Any]] = {}
    for sector, members in sorted(sector_rows.items()):
        zero_news = [symbol for symbol in members if symbol in measured_by_symbol]
        per_sector[sector] = {
            "ticker_universe": len(members),
            "ticker_with_news": len(members) - len(zero_news),
            "ticker_zero_news": len(zero_news),
            "raw_news_coverage_rate": _rate(
                len(members) - len(zero_news), len(members)
            ),
            "zero_news_movers": sum(
                measured_by_symbol[symbol]["is_mover"] is True
                for symbol in zero_news
            ),
            "calendar_observed_zero_news": sum(
                measured_by_symbol[symbol]["calendar"]["status"] == "OBSERVED"
                for symbol in zero_news
            ),
        }

    return {
        "version": BACKSTOP_VERSION,
        "population": {
            "zero_news": len(rows),
            "movers": len(movers),
            "non_movers": len(non_movers),
            "return_missing": len(missing_returns),
        },
        "calendar_observation": {
            "mover_observed": calendar_movers,
            "mover_population": len(movers),
            "mover_rate": _rate(
                calendar_movers, len(movers), known=calendar["complete"]
            ),
            "non_mover_observed": calendar_non_movers,
            "non_mover_population": len(non_movers),
            "non_mover_rate": _rate(
                calendar_non_movers,
                len(non_movers),
                known=calendar["complete"],
            ),
        },
        "volume_observation": {
            "mover_observations": sum(
                row["volume"]["surprise"] is not None for row in movers
            ),
            "non_mover_observations": sum(
                row["volume"]["surprise"] is not None for row in non_movers
            ),
            "mover_median": _median(rows, mover=True),
            "non_mover_median": _median(rows, mover=False),
            "temporal_validity": POST_HOC_EOD,
            "valid_for_signal_evaluation": False,
            "reason": (
                "session volume and the EOD mover label are known only at close; "
                "an ex-ante threshold evaluation belongs to the pre-registered "
                "shadow study #451"
            ),
        },
        "per_sector": per_sector,
        "per_symbol": rows,
        "freeze": (
            "read-only measurement; no threshold, signal, gate, weight, flag, "
            "cooldown or order is changed"
        ),
    }
