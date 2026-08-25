"""Contesto evento, mercato e microstruttura del dossier alpha-miss (#285).

Modulo puro: riceve dati gia' acquisiti e non tocca rete, DB o configurazione
live. Le categorie sono chiuse e la missingness resta esplicita; in particolare
l'assenza di un feed halt autorevole non viene trasformata in ``nessun halt``.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from typing import Iterable
from zoneinfo import ZoneInfo


CONTEXT_VERSION = "event_market_context_v1"
RETURN_MODEL = "beta_1_arithmetic_v1"

CATALYST_TYPES = (
    "EARNINGS",
    "GUIDANCE",
    "ANALYST",
    "M_AND_A",
    "MACRO",
    "CORPORATE_ACTION",
    "IDIOSYNCRATIC",
    "UNKNOWN",
)
REGIME_TYPES = ("BULL", "SIDEWAYS", "BEAR", "HIGH_VOL", "UNKNOWN")
THEME_TYPES = (
    "AI_SEMIS",
    "TECH",
    "FINANCIALS",
    "CONSUMER",
    "MEDIA",
    "HEALTHCARE",
    "ENERGY",
    "INDUSTRIALS",
    "MATERIALS",
    "TELECOM",
    "BROAD_MARKET",
    "UNKNOWN",
)

# Mapping dichiarativo, indipendente dall'universo negoziabile. Gli ETF possono
# essere caricati come soli benchmark senza entrare nella watchlist operativa.
SECTOR_ETF_BY_SECTOR = {
    "tech": "XLK",
    "semis": "SOXX",
    "financials": "XLF",
    "consumer": "XLY",
    "media": "XLC",
    "healthcare": "XLV",
    "energy": "XLE",
    "industrials": "XLI",
    "materials": "XLB",
    "telecom": "XLC",
    "etf_broad": "SPY",
}

THEME_BY_SECTOR = {
    "tech": "TECH",
    "semis": "AI_SEMIS",
    "financials": "FINANCIALS",
    "consumer": "CONSUMER",
    "media": "MEDIA",
    "healthcare": "HEALTHCARE",
    "energy": "ENERGY",
    "industrials": "INDUSTRIALS",
    "materials": "MATERIALS",
    "telecom": "TELECOM",
    "etf_broad": "BROAD_MARKET",
}

_CATALYST_PATTERNS = (
    ("GUIDANCE", re.compile(r"\b(guidance|outlook|forecast)\b", re.I)),
    ("EARNINGS", re.compile(r"\b(earnings|quarterly results?|eps|revenue beat|revenue miss)\b", re.I)),
    ("ANALYST", re.compile(r"\b(upgrade[sd]?|downgrade[sd]?|price target|analysts?|rating)\b", re.I)),
    ("M_AND_A", re.compile(r"\b(merger|acquisition|acquire[sd]?|buyout|takeover|m&a)\b", re.I)),
    ("MACRO", re.compile(r"\b(fed|inflation|cpi|jobs report|payrolls?|gdp|tariffs?|interest rates?)\b", re.I)),
)

_CORPORATE_CATALYST = {
    "earnings": "EARNINGS",
    "guidance": "GUIDANCE",
    "analyst": "ANALYST",
    "merger": "M_AND_A",
    "acquisition": "M_AND_A",
    "m&a": "M_AND_A",
    "dividend": "CORPORATE_ACTION",
    "split": "CORPORATE_ACTION",
    "spinoff": "CORPORATE_ACTION",
    "rights_distribution": "CORPORATE_ACTION",
}


def _daily_return(bar: dict | None) -> float | None:
    if not bar:
        return None
    previous = bar.get("close_prec")
    close = bar.get("close")
    if previous is None or close is None or float(previous) == 0.0:
        return None
    return float(close) / float(previous) - 1.0


def _iso(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


def _rows_for_symbol(rows: Iterable[dict], symbol: str) -> list[dict]:
    return [row for row in rows if str(row.get("ticker") or row.get("symbol") or "").upper() == symbol]


def _classify_catalyst(articles: list[dict], corporate_events: list[dict]) -> dict:
    if corporate_events:
        event = sorted(
            corporate_events,
            key=lambda row: (str(row.get("event_date") or ""), str(row.get("event_type") or "")),
        )[0]
        raw_type = str(event.get("event_type") or "").strip().casefold()
        mapped = _CORPORATE_CATALYST.get(raw_type, "CORPORATE_ACTION")
        return {
            "type": mapped,
            "source": "corporate_calendar",
            "evidence": str(event.get("source") or "unknown_corporate_source"),
        }

    if any(str(row.get("relevance") or "").upper() == "SECTOR_MACRO" for row in articles):
        ids = sorted({str(row.get("canonical_article_id")) for row in articles if row.get("canonical_article_id")})
        return {"type": "MACRO", "source": "article_relevance", "evidence": ids}

    combined = " ".join(str(row.get("title") or "") for row in articles)
    for catalyst, pattern in _CATALYST_PATTERNS:
        if pattern.search(combined):
            ids = sorted({str(row.get("canonical_article_id")) for row in articles if row.get("canonical_article_id")})
            return {"type": catalyst, "source": "deterministic_title_rules", "evidence": ids}
    if articles:
        ids = sorted({str(row.get("canonical_article_id")) for row in articles if row.get("canonical_article_id")})
        return {"type": "IDIOSYNCRATIC", "source": "issuer_article_present", "evidence": ids}
    return {"type": "UNKNOWN", "source": None, "evidence": None}


def _regime_context(observations: list[dict], vix_observation: dict | None) -> dict:
    if observations:
        latest = max(observations, key=lambda row: _iso(row.get("observed_at")) or "")
        multiplier = float(latest["multiplier"])
        if multiplier <= 0.3:
            label = "HIGH_VOL"
        elif multiplier <= 0.6:
            label = "BEAR"
        elif multiplier <= 0.9:
            label = "SIDEWAYS"
        else:
            label = "BULL"
        source = str(latest.get("source") or "execution_decisions.regime_mult")
        observed_at = _iso(latest.get("observed_at"))
    else:
        multiplier, label, source, observed_at = None, "UNKNOWN", None, None

    return {
        "type": label,
        "multiplier": multiplier,
        "observed_at": observed_at,
        "source": source,
        "mapping": "<=0.3 HIGH_VOL; <=0.6 BEAR; <=0.9 SIDEWAYS; >0.9 BULL",
        "vix": float(vix_observation["value"]) if vix_observation and vix_observation.get("value") is not None else None,
        "vix_observed_on": str(vix_observation.get("observed_on")) if vix_observation and vix_observation.get("observed_on") else None,
        "vix_source": str(vix_observation.get("source")) if vix_observation and vix_observation.get("source") else None,
    }


def _bar_microstructure(
    symbol: str, daily: dict | None, intraday: list[dict], data: str
) -> dict:
    target = date.fromisoformat(data)
    new_york = ZoneInfo("America/New_York")
    session_start = datetime.combine(target, time(4, 0), tzinfo=new_york).astimezone(timezone.utc)
    session_end = datetime.combine(target, time(20, 0), tzinfo=new_york).astimezone(timezone.utc)
    volumes = []
    for row in intraday:
        timestamp = row.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = None
        if isinstance(timestamp, datetime) and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if (
            row.get("volume") is not None
            and isinstance(timestamp, datetime)
            and session_start <= timestamp.astimezone(timezone.utc) < session_end
        ):
            volumes.append(int(row["volume"]))
    session_volume = sum(volumes) if volumes else (int(daily["volume"]) if daily and daily.get("volume") is not None else None)
    adv = float(daily["adv_20d"]) if daily and daily.get("adv_20d") is not None else None
    ratio = (
        session_volume / adv
        if session_volume is not None and adv is not None and adv != 0.0
        else None
    )
    missingness = []
    if session_volume is None:
        missingness.append("volume_missing")
    if adv is None:
        missingness.append("adv_20d_missing")
    return {
        "basis": "BAR_5MIN",
        "symbol": symbol,
        "session_volume": session_volume,
        "adv_20d": adv,
        "volume_adv_ratio": ratio,
        "volume_surprise": ratio - 1.0 if ratio is not None else None,
        "missingness": missingness,
        "provenance": {
            "source": "Alpaca Market Data API / SIP bars",
            "timeframe": "5Min",
            "adv_window": "20 preceding complete daily bars",
        },
    }


def _nbbo_microstructure(symbol: str, quote: dict | None) -> dict:
    if not quote:
        return {
            "basis": "NBBO",
            "symbol": symbol,
            "observed_at": None,
            "bid_price": None,
            "ask_price": None,
            "bid_size": None,
            "ask_size": None,
            "spread": None,
            "spread_bps": None,
            "missingness": ["nbbo_quote_missing"],
            "provenance": {"source": None, "feed": "SIP"},
        }
    bid = float(quote["bid_price"]) if quote.get("bid_price") is not None else None
    ask = float(quote["ask_price"]) if quote.get("ask_price") is not None else None
    if bid is not None and ask is not None and ask >= bid:
        spread = ask - bid
        mid = (ask + bid) / 2.0
    else:
        spread, mid = None, None
    return {
        "basis": "NBBO",
        "symbol": symbol,
        "observed_at": _iso(quote.get("timestamp")),
        "bid_price": bid,
        "ask_price": ask,
        "bid_size": quote.get("bid_size"),
        "ask_size": quote.get("ask_size"),
        "spread": spread,
        "spread_bps": spread / mid * 10_000 if spread is not None and mid else None,
        "missingness": [] if spread is not None else ["nbbo_bid_or_ask_missing"],
        "provenance": {"source": str(quote.get("source") or "Alpaca Market Data API / SIP quotes"), "feed": "SIP"},
    }


def _halt_context(events: list[dict]) -> dict:
    if not events:
        return {
            "status": "UNKNOWN",
            "events": [],
            "source": None,
            "missing_reason": "authoritative_halt_feed_unavailable",
        }
    return {
        "status": "OBSERVED",
        "events": events,
        "source": sorted({str(event.get("source") or "unknown") for event in events}),
        "missing_reason": None,
    }


def _cluster_key(row: dict, shared_article_ids: set[str]) -> tuple[str, str]:
    articles = row.pop("_articles")
    shared_ids = sorted({
        str(article.get("canonical_article_id"))
        for article in articles
        if article.get("canonical_article_id")
        and str(article.get("canonical_article_id")) in shared_article_ids
        and str(article.get("relevance") or "").upper() == "SECTOR_MACRO"
    })
    if shared_ids and row["theme"]["type"] != "UNKNOWN":
        return (
            f"article:{shared_ids[0]}|theme:{row['theme']['type']}",
            "shared_canonical_article_and_theme",
        )
    if row["catalyst"]["type"] == "MACRO" and row["theme"]["type"] != "UNKNOWN":
        symbol_return = row["returns"]["symbol"]
        direction = "UP" if symbol_return is not None and symbol_return > 0 else (
            "DOWN" if symbol_return is not None and symbol_return < 0 else "FLAT_OR_UNKNOWN"
        )
        return (
            f"theme:{row['theme']['type']}|catalyst:MACRO|direction:{direction}",
            "same_theme_macro_direction",
        )
    return f"symbol:{row['symbol']}", "symbol_specific_or_unresolved"


def build_event_market_context(
    *,
    data: str,
    candidates: list[dict],
    daily_bars: dict[str, dict],
    sector_by_ticker: dict[str, str],
    articles: list[dict],
    corporate_events: list[dict] | dict | None,
    regime_observations: list[dict],
    vix_observation: dict | None,
    intraday_bars: dict[str, list[dict]],
    nbbo_quotes: dict[str, dict],
    halt_events: list[dict],
) -> dict:
    """Costruisce contesto normalizzato e cluster di opportunita' correlate."""
    regime = _regime_context(regime_observations, vix_observation)
    per_symbol: dict[str, dict] = {}
    if isinstance(corporate_events, dict):
        calendar_events = list(corporate_events.get("events") or [])
        calendar_complete = bool(corporate_events.get("complete"))
        calendar_sources = list(corporate_events.get("sources_succeeded") or [])
        calendar_missingness = list(corporate_events.get("missingness") or [])
    elif corporate_events is not None:
        calendar_events = list(corporate_events)
        calendar_complete = True
        calendar_sources = sorted({
            str(event.get("source") or "UNKNOWN") for event in calendar_events
        })
        calendar_missingness = []
    else:
        calendar_events = []
        calendar_complete = False
        calendar_sources = []
        calendar_missingness = ["corporate_calendar_unavailable"]

    for candidate in candidates:
        symbol = str(candidate["symbol"]).upper()
        sector = sector_by_ticker.get(symbol)
        sector_etf = SECTOR_ETF_BY_SECTOR.get(sector or "")
        symbol_return = _daily_return(daily_bars.get(symbol))
        spy_return = _daily_return(daily_bars.get("SPY"))
        sector_return = _daily_return(daily_bars.get(sector_etf)) if sector_etf else None
        symbol_articles = _rows_for_symbol(articles, symbol)
        symbol_events = _rows_for_symbol(calendar_events, symbol)
        symbol_halts = _rows_for_symbol(halt_events, symbol)
        catalyst = _classify_catalyst(symbol_articles, symbol_events)
        theme = THEME_BY_SECTOR.get(sector or "", "UNKNOWN")
        missingness: list[str] = []
        if sector is None:
            missingness.append("sector_mapping_missing")
        if sector_etf is None:
            missingness.append("sector_etf_mapping_missing")
        elif sector_return is None:
            missingness.append("sector_etf_return_missing")
        if spy_return is None:
            missingness.append("spy_return_missing")
        if regime["type"] == "UNKNOWN":
            missingness.append("regime_observation_missing")
        if regime["vix"] is None:
            missingness.append("vix_missing")

        row = {
            "symbol": symbol,
            "sector": sector,
            "sector_etf": sector_etf,
            "returns": {
                "symbol": symbol_return,
                "spy": spy_return,
                "sector_etf": sector_return,
                "residual_vs_spy": symbol_return - spy_return if symbol_return is not None and spy_return is not None else None,
                "residual_vs_sector": symbol_return - sector_return if symbol_return is not None and sector_return is not None else None,
                "model": RETURN_MODEL,
                "formula": "r_symbol - r_benchmark; beta fixed at 1",
            },
            "catalyst": catalyst,
            "corporate_calendar": {
                "status": "OBSERVED" if symbol_events else ("NOT_OBSERVED" if calendar_complete else "UNKNOWN"),
                "events": symbol_events,
                "sources_succeeded": calendar_sources,
                "complete": calendar_complete,
                "missingness": calendar_missingness,
                "missing_reason": calendar_missingness[0] if calendar_missingness else None,
            },
            "regime": dict(regime),
            "theme": {"type": theme, "source": "config/trading.yaml sectors" if sector else None},
            "microstructure": {
                "bar_based": _bar_microstructure(
                    symbol, daily_bars.get(symbol), intraday_bars.get(symbol, []), data
                ),
                "nbbo": _nbbo_microstructure(symbol, nbbo_quotes.get(symbol)),
                "halt": _halt_context(symbol_halts),
            },
            "missingness": missingness,
            "_articles": symbol_articles,
        }
        per_symbol[symbol] = row

    macro_article_counts = Counter(
        str(article.get("canonical_article_id"))
        for row in per_symbol.values()
        for article in row.get("_articles") or []
        if article.get("canonical_article_id")
        and str(article.get("relevance") or "").upper() == "SECTOR_MACRO"
    )
    shared_article_ids = {
        canonical_id for canonical_id, count in macro_article_counts.items() if count >= 2
    }
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for symbol, row in per_symbol.items():
        grouped[_cluster_key(row, shared_article_ids)].append(symbol)
    clusters = [
        {
            "cluster_id": key[0],
            "member_symbols": sorted(symbols),
            "raw_opportunities": len(symbols),
            "independent_units": 1,
            "correlation_basis": key[1],
        }
        for key, symbols in sorted(grouped.items())
    ]

    return {
        "version": CONTEXT_VERSION,
        "data": data,
        "per_symbol": per_symbol,
        "clusters": clusters,
        "statistics": {
            "raw_opportunities": len(candidates),
            "independent_clusters": len(clusters),
            "counting_rule": "one independent unit per deterministic cluster",
        },
    }
