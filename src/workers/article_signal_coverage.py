"""Classificazione osservazionale dell'articolo al momento dello scoring (#637).

Questo modulo non decide se uno score e' eleggibile: prepara esclusivamente la
riga additiva che permette di confrontare il flusso visto dal worker con il
dossier del giorno dopo. I classificatori semantici restano quelli del dossier.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from src.analysis.dossier.article_coverage import (
    canonical_article_id,
    classify_attribution,
    classify_relevance,
    classify_timing,
    content_empty_title_reason,
)
from src.connectors.deduplicator import compute_dedup_hash
from src.models.news import NewsItem
from src.models.signals import SentimentResult


log = logging.getLogger(__name__)
_NEW_YORK = ZoneInfo("America/New_York")
_CALENDAR_CACHE: dict[date, list["MarketSession"]] = {}
_CALENDAR_CACHE_MAX = 64


@dataclass(frozen=True)
class MarketSession:
    """Confini Alpaca di una seduta in UTC."""

    date: date
    open_at: datetime
    close_at: datetime


def _session_boundary(value, session_date: date) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, time):
        return datetime.combine(session_date, value, tzinfo=_NEW_YORK).astimezone(timezone.utc)
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_NEW_YORK)
    return parsed.astimezone(timezone.utc)


def load_actionable_sessions(published_at: datetime) -> list[MarketSession]:
    """Legge dal calendario Alpaca la seduta corrente e quelle immediatamente dopo.

    Senza calendario l'ancora resta sconosciuta: inventare un giorno feriale
    trasformerebbe una festivita' in una seduta misurata.
    """
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest
    from src.config import config

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        return []
    moment = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    start = moment.astimezone(_NEW_YORK).date()
    # Il sink chiama per ogni segnale, nel worker di inferenza a concorrenza 1:
    # una richiesta HTTP per segnale e' latenza e rate limit per nulla, il
    # calendario di un giorno non cambia. Si mette in cache solo il successo.
    cached = _CALENDAR_CACHE.get(start)
    if cached is not None:
        return cached
    try:
        client = TradingClient(
            config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        rows = client.get_calendar(GetCalendarRequest(
            start=start,
            end=(moment + timedelta(days=8)).astimezone(_NEW_YORK).date(),
        ))
        sessions = [
            MarketSession(
                date=row.date,
                open_at=_session_boundary(row.open, row.date),
                close_at=_session_boundary(row.close, row.date),
            )
            for row in rows
        ]
    except Exception as exc:
        log.warning("#637: calendario Alpaca non disponibile: %s", exc)
        return []
    if len(_CALENDAR_CACHE) >= _CALENDAR_CACHE_MAX:
        _CALENDAR_CACHE.clear()
    _CALENDAR_CACHE[start] = sessions
    return sessions


def _actionable_session(
    published_at: datetime, sessions: list[MarketSession]
) -> MarketSession | None:
    """Prima seduta in cui il worker avrebbe potuto agire sull'articolo."""
    for session in sorted(sessions, key=lambda value: value.open_at):
        if published_at <= session.close_at:
            return session
    return None


def build_signal_coverage(
    *,
    item: NewsItem,
    result: SentimentResult,
    issuer_terms: list[str],
    sessions: list[MarketSession],
) -> dict:
    """Costruisce una classificazione, senza alcun effetto sul segnale live."""
    ticker = result.symbol.strip().upper()
    tags = {str(value).strip().upper() for value in item.asset_tags if str(value).strip()}
    tags.add(ticker)
    fanout_degree = len(tags)
    try:
        content_hash = compute_dedup_hash(item)
    except Exception:
        content_hash = ""
    row = {
        "ticker": ticker,
        "title": item.title,
        # Lo scorer possiede il corpo intero; il campo input_scope dichiara la
        # differenza dal body_snippet a 500 caratteri che legge il dossier.
        "body_snippet": item.body,
        "content_hash": content_hash,
        "url": item.url,
        "source": item.source,
        "published_at": item.timestamp,
        "extraction_method": item.extraction_method,
        "issuer_terms": issuer_terms,
    }
    session = _actionable_session(item.timestamp, sessions)
    timing = (
        classify_timing(item.timestamp, session.open_at, session.close_at)
        if session is not None
        else "UNKNOWN"
    )
    relevance, subject_ticker = classify_relevance(row, fanout_degree)
    content_empty_reason = None
    if relevance == "ISSUER_SPECIFIC":
        content_empty_reason = content_empty_title_reason(item.title)
        if content_empty_reason is None and timing == "RETROSPECTIVE":
            content_empty_reason = "RETROSPECTIVE_TIMING"
    attribution = classify_attribution(relevance, fanout_degree)
    return {
        "symbol": ticker,
        "canonical_article_id": canonical_article_id(row),
        "timing_category": timing,
        "session_anchor": session.date if session is not None else None,
        "relevance": relevance,
        "attribution": attribution,
        "subject_ticker": subject_ticker,
        "content_empty_reason": content_empty_reason,
        "fanout_degree": fanout_degree,
        "score_own": result.score if attribution == "ISSUER_SPECIFIC" else None,
        "score_fanout": result.score if attribution == "FANOUT" else None,
        # La scrittura stabilisce il valore rispetto ai cluster gia' durevoli.
        "novelty_proxy": None if session is None else True,
        "input_scope": "full_article",
    }
