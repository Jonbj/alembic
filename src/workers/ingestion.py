"""NewsIngestionWorker — fetches broad financial news, extracts tickers, enqueues.

This is the **orchestrator** of the news-driven pipeline. It runs as a Celery
task every 15 minutes (Mon–Fri market hours) and performs three steps:

  1. **Fetch** — calls `GDELTGKGConnector.fetch()` to retrieve recent financial
     news with organisation names from GDELT GKG.
  2. **Extract** — passes org names to `TickerExtractor`, which queries the
     PostgreSQL `ticker_lookup` table and returns ticker symbols.
  3. **Enqueue** — for each ticker found, builds a `NewsItem` with
     `asset_tags=[ticker]`, deduplicates by `(url, ticker)` via
     `Deduplicator.is_duplicate_by_id`, and pushes to Redis `news:queue`.

Multi-ticker articles:
  - An article mentioning Apple + Microsoft generates **two** separate
    `NewsItem` objects, each with a distinct `id="{url}:{ticker}"`.
  - This allows the SentimentWorker (downstream) to process each ticker
    independently while sharing the same article content.

Stats returned:
  - The Celery task returns a dict with keys:
    `fetched`, `tickers_found`, `discarded`, `queued`, `duplicates`.
    Useful for monitoring dashboards and alerting on ingestion health.

Connection lifecycle:
  - Redis and PostgreSQL connections are opened once per task invocation
    and closed in a `finally` block to avoid resource leaks during retries.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

import psycopg2
from redis import Redis

from src.config import config

# Canonical ticker aliases: map non-watchlist symbols → watchlist symbol.
# MarketAux/Alpaca APIs may return GOOG (Class C shares) while our watchlist
# uses GOOGL (Class A). BRK.A → BRK.B for the same reason; FB retired 2021.
_TICKER_ALIASES: dict[str, str] = {
    "GOOG": "GOOGL",
    "BRK.A": "BRK.B",
    "FB": "META",
}
from src.connectors.alpaca_news import AlpacaNewsConnector
from src.connectors.finnhub_news import FinnhubNewsConnector
from src.connectors.deduplicator import Deduplicator
from src.connectors.gdelt_doc import GdeltDocConnector
from src.connectors.rss import RSSConnector
from src.connectors.sec_edgar import SECEdgarConnector
from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.connectors.marketaux import MarketAuxConnector
from src.connectors.ticker_extractor import TickerExtractor
from src.models.news import GKGNewsItem, MarketAuxNewsItem, NewsItem
from src.workers.celery_app import app
from src.workers.market_clock import is_market_open

log = logging.getLogger(__name__)


async def _fetch_gkg_items(connector: GDELTGKGConnector) -> list[GKGNewsItem]:
    """Drain the async GDELT GKG iterator into a concrete list.

    This wrapper exists because the Celery task body is synchronous
    (Celery worker threads), while the connector is async. We bridge
    the two worlds by calling `asyncio.run()` once in the task entry-point
    and collecting all items before entering the synchronous `_process_gkg_items`.
    """
    return [item async for item in connector.fetch()]


def _process_gkg_items(
    gkg_items: list[GKGNewsItem],
    extractor: TickerExtractor,
    deduplicator: Deduplicator,
    redis_client: Redis,
    watchlist: set | None = None,
) -> dict:
    """Extract tickers, deduplicate, and push annotated NewsItems to news:queue.

    This is a **pure function** (aside from Redis/Deduplicator I/O) to allow
    easy unit testing without a live Celery broker.

    Args:
        gkg_items: Raw GKG records from GDELT.
        extractor: TickerExtractor instance (with open PG connection).
        deduplicator: Deduplicator instance (with open Redis connection).
        redis_client: Redis client for LPUSH to news:queue.
        watchlist: Optional set of watchlist ticker symbols. When provided, only
            tickers in the watchlist are enqueued (~30% LLM quota saving for
            large ticker_lookup tables).

    Returns:
        Stats dict with keys:
          - fetched:            total GKG records processed
          - tickers_found:      total ticker symbols extracted (before watchlist filter)
          - watchlist_filtered: tickers dropped because not in watchlist
          - discarded:          articles with zero ticker matches
          - queued:             items actually pushed to Redis
          - duplicates:         items skipped because (url, ticker) already seen
    """
    stats = {"fetched": 0, "tickers_found": 0, "watchlist_filtered": 0, "discarded": 0, "queued": 0, "duplicates": 0}

    for gkg_item in gkg_items:
        stats["fetched"] += 1

        # Step 1: ticker extraction from organisation names
        tickers = extractor.extract(gkg_item.org_names)
        if not tickers:
            # No recognised company → article is irrelevant for trading signals.
            # Logged at DEBUG, not WARNING, because this is expected for many
            # generic financial news items (e.g. "Federal Reserve" has no ticker).
            stats["discarded"] += 1
            log.debug("No ticker found for %s (org_names=%s), discarding", gkg_item.url, gkg_item.org_names)
            continue

        stats["tickers_found"] += len(tickers)

        # Step 2: apply canonical aliases and watchlist filter
        normalised = [_TICKER_ALIASES.get(t, t) for t in tickers]
        if watchlist:
            before = len(normalised)
            normalised = [t for t in normalised if t in watchlist]
            stats["watchlist_filtered"] += before - len(normalised)
        if not normalised:
            stats["discarded"] += 1
            continue

        # Step 3: expand each ticker into a separate NewsItem
        for ticker in normalised:
            item = NewsItem(
                id=f"{gkg_item.url}:{ticker}",  # Composite ID for dedup by (url, ticker).
                source=gkg_item.source,
                timestamp=gkg_item.timestamp,
                title=gkg_item.title,
                body=gkg_item.body,
                url=gkg_item.url,
                language=gkg_item.language,
                asset_tags=[ticker],  # SentimentWorker consumes asset_tags[0].
                extraction_method="org_lookup",  # QT-03: GDELT org name → ticker_lookup
            )

            # Step 4: deduplication
            if deduplicator.is_duplicate_by_id(item) or deduplicator.is_duplicate_content_symbol(item):
                stats["duplicates"] += 1
                continue

            # Step 5: enqueue to Redis
            item.raw_ingested_at = datetime.now(timezone.utc)
            redis_client.rpush("news:queue", item.model_dump_json())
            stats["queued"] += 1

    return stats


async def _fetch_marketaux_items(connector: MarketAuxConnector) -> list[MarketAuxNewsItem]:
    """Drain the async MarketAux iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_marketaux_items(
    items: list[MarketAuxNewsItem],
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Expand per-ticker, deduplicate, and push MarketAuxNewsItems to news:queue.

    Why expand per-ticker?
      Same reason as GDELT: an article mentioning AAPL + MSFT generates two
      independent SentimentWorker jobs so each ticker gets its own score.
      Each per-ticker item carries the article-level marketaux_sentiment so
      the SentimentWorker can apply the neutral pre-filter independently.
    """
    stats = {"fetched": 0, "tickers_found": 0, "queued": 0, "duplicates": 0}

    for item in items:
        stats["fetched"] += 1

        if not item.asset_tags:
            continue

        stats["tickers_found"] += len(item.asset_tags)

        for ticker in item.asset_tags:
            ticker = _TICKER_ALIASES.get(ticker, ticker)
            per_ticker = MarketAuxNewsItem(
                id=f"{item.url}:{ticker}",
                source=item.source,
                timestamp=item.timestamp,
                title=item.title,
                body=item.body,
                url=item.url,
                language=item.language,
                asset_tags=[ticker],
                extraction_method=item.extraction_method,  # QT-03: carry provenance
                marketaux_sentiment=item.marketaux_sentiment,
            )

            if deduplicator.is_duplicate_by_id(per_ticker) or deduplicator.is_duplicate_content_symbol(per_ticker):
                stats["duplicates"] += 1
                continue

            per_ticker.raw_ingested_at = datetime.now(timezone.utc)
            redis_client.rpush("news:queue", per_ticker.model_dump_json())
            stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_marketaux_ingestion_worker")
def run_marketaux_ingestion_worker() -> dict:
    """Celery entry-point for MarketAux news ingestion.

    Fetches recent articles for WATCHLIST_SYMBOLS from MarketAux, expands
    per-ticker, deduplicates, and pushes MarketAuxNewsItems to news:queue.

    Scheduling:
      - Celery beat: every 15 min, Mon–Fri 14:00–21:00 UTC
      - 28 calls/market session — well within the 100 req/day free-tier limit.

    Returns:
        Stats dict: fetched, tickers_found, queued, duplicates.
        Returns {"skipped": True} if MARKETAUX_API_KEY is not configured.
    """
    if os.environ.get("MARKETAUX_INGESTION_ENABLED", "0") == "0":
        return {"skipped": True, "reason": "MARKETAUX_INGESTION_ENABLED=0 (FIX-01: net-negative source)"}

    redis_client = Redis.from_url(config.REDIS_URL)

    if not config.MARKETAUX_API_KEY:
        log.warning("MARKETAUX_API_KEY not configured — skipping MarketAux ingestion")
        redis_client.close()
        return {"skipped": True, "reason": "no_api_key"}

    try:
        connector = MarketAuxConnector(
            api_key=config.MARKETAUX_API_KEY,
            symbols=config.WATCHLIST_SYMBOLS or [],
        )
        deduplicator = Deduplicator(redis_client)

        items = asyncio.run(_fetch_marketaux_items(connector))
        stats = _process_marketaux_items(items, deduplicator, redis_client)

        log.info("MarketAux ingestion stats: %s", stats)
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as _pg:
                _pg.record_ingestion_stats("marketaux", stats)
        except Exception as _stats_exc:
            log.warning("Could not persist ingestion stats: %s", _stats_exc)
        return stats

    finally:
        redis_client.close()


async def _fetch_alpaca_items(connector: AlpacaNewsConnector) -> list[NewsItem]:
    """Drain the async Alpaca News iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_alpaca_items(
    items: list[NewsItem],
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Expand per-ticker, deduplicate, and push Alpaca NewsItems to news:queue.

    Alpaca articles already contain US ticker symbols in asset_tags (from
    Benzinga metadata). No TickerExtractor needed.
    """
    stats = {"fetched": 0, "tickers_found": 0, "queued": 0, "duplicates": 0}

    for item in items:
        stats["fetched"] += 1

        if not item.asset_tags:
            continue

        stats["tickers_found"] += len(item.asset_tags)

        for ticker in item.asset_tags:
            ticker = _TICKER_ALIASES.get(ticker, ticker)
            per_ticker = NewsItem(
                id=f"{item.id}:{ticker}",
                source=item.source,
                timestamp=item.timestamp,
                title=item.title,
                body=item.body,
                url=item.url,
                language=item.language,
                asset_tags=[ticker],
                extraction_method=item.extraction_method,  # QT-03: carry provenance
            )

            if deduplicator.is_duplicate_by_id(per_ticker) or deduplicator.is_duplicate_content_symbol(per_ticker):
                stats["duplicates"] += 1
                continue

            per_ticker.raw_ingested_at = datetime.now(timezone.utc)
            redis_client.rpush("news:queue", per_ticker.model_dump_json())
            stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_alpaca_ingestion_worker")
def run_alpaca_ingestion_worker() -> dict:
    """Celery entry-point for Alpaca/Benzinga news ingestion.

    Fetches recent Benzinga articles for WATCHLIST_SYMBOLS via Alpaca News API,
    expands per-ticker, deduplicates, and pushes NewsItems to news:queue.

    Scheduling:
      - Celery beat: every 15 min, Mon–Fri 14:00–21:00 UTC (aligned with
        GDELT and MarketAux ingestion tasks).

    Returns:
        Stats dict: fetched, tickers_found, queued, duplicates.
        Returns {"skipped": True} if Alpaca credentials are not configured.
    """
    redis_client = Redis.from_url(config.REDIS_URL)

    if not is_market_open():
        log.info("Market closed — skipping Alpaca ingestion")
        redis_client.close()
        return {"skipped": True, "reason": "market_closed"}

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("ALPACA_API_KEY/SECRET not configured — skipping Alpaca ingestion")
        redis_client.close()
        return {"skipped": True, "reason": "no_credentials"}

    try:
        connector = AlpacaNewsConnector(
            api_key=config.ALPACA_API_KEY,
            api_secret=config.ALPACA_SECRET_KEY,
            symbols=config.WATCHLIST_SYMBOLS or [],
        )
        deduplicator = Deduplicator(redis_client)

        items = asyncio.run(_fetch_alpaca_items(connector))
        stats = _process_alpaca_items(items, deduplicator, redis_client)

        log.info("Alpaca ingestion stats: %s", stats)
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as _pg:
                _pg.record_ingestion_stats("alpaca_benzinga", stats)
        except Exception as _stats_exc:
            log.warning("Could not persist ingestion stats: %s", _stats_exc)
        return stats

    finally:
        redis_client.close()


async def _fetch_finnhub_items(connector: FinnhubNewsConnector) -> list[NewsItem]:
    """Drain the async Finnhub News iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_finnhub_items(
    items: list[NewsItem],
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Deduplicate and push Finnhub NewsItems to news:queue.

    Finnhub articles already carry a single explicit ticker in asset_tags
    (extraction_method='source_metadata') — no TickerExtractor needed.
    """
    stats = {"fetched": 0, "tickers_found": 0, "queued": 0, "duplicates": 0}

    for item in items:
        stats["fetched"] += 1
        if not item.asset_tags:
            continue
        stats["tickers_found"] += len(item.asset_tags)
        for ticker in item.asset_tags:
            ticker = _TICKER_ALIASES.get(ticker, ticker)
            per_ticker = NewsItem(
                id=f"{item.id}:{ticker}",
                source=item.source,
                timestamp=item.timestamp,
                title=item.title,
                body=item.body,
                url=item.url,
                language=item.language,
                asset_tags=[ticker],
                extraction_method=item.extraction_method,
            )
            if deduplicator.is_duplicate_by_id(per_ticker) or deduplicator.is_duplicate_content_symbol(per_ticker):
                stats["duplicates"] += 1
                continue
            per_ticker.raw_ingested_at = datetime.now(timezone.utc)
            redis_client.rpush("news:queue", per_ticker.model_dump_json())
            stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_finnhub_ingestion_worker")
def run_finnhub_ingestion_worker() -> dict:
    """Celery entry-point for Finnhub company-news ingestion.

    Clean, explicitly-tagged US company news for WATCHLIST_SYMBOLS. Skips silently
    when FINNHUB_API_KEY is not configured.

    SHELVED (2026-07-01): OFF by default. A mini-spike found ~2115 articles/fetch
    (5.5× worker throughput → queue flood) with loose relevance (generic/listicle/
    competitor mentions tagged to the company). Re-enable with FINNHUB_INGESTION_ENABLED=1
    ONLY after adding a hard per-symbol cap + a relevance filter.
    """
    if os.environ.get("FINNHUB_INGESTION_ENABLED", "0") == "0":
        return {"skipped": True, "reason": "finnhub_ingestion_disabled"}

    redis_client = Redis.from_url(config.REDIS_URL)
    if not config.FINNHUB_API_KEY:
        log.warning("FINNHUB_API_KEY not configured — skipping Finnhub ingestion")
        redis_client.close()
        return {"skipped": True, "reason": "no_credentials"}
    try:
        connector = FinnhubNewsConnector(
            api_key=config.FINNHUB_API_KEY,
            symbols=config.WATCHLIST_SYMBOLS or [],
        )
        deduplicator = Deduplicator(redis_client)
        items = asyncio.run(_fetch_finnhub_items(connector))
        stats = _process_finnhub_items(items, deduplicator, redis_client)
        log.info("Finnhub ingestion stats: %s", stats)
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as _pg:
                _pg.record_ingestion_stats("finnhub", stats)
        except Exception as _stats_exc:
            log.warning("Could not persist ingestion stats: %s", _stats_exc)
        return stats
    finally:
        redis_client.close()


def _load_gdelt_doc_ticker_names(symbols: list[str]) -> dict[str, str]:
    """Resolve company names for symbols via SEC company_tickers.json. Fail-open.

    Returns ticker→raw-title dict (e.g. {"AAPL": "APPLE INC"}) for building
    precise GDELT queries. Skips silently on any network/parse error.
    """
    try:
        import httpx

        resp = httpx.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "Alembic/1.0 stefano.delgobbo@gmail.com"},
            timeout=10.0,
        )
        resp.raise_for_status()
        symbol_set = {s.upper() for s in symbols}
        result: dict[str, str] = {}
        for row in resp.json().values():
            t = str(row.get("ticker", "")).upper()
            if t in symbol_set:
                title = str(row.get("title", "")).strip()
                if title:
                    result[t] = title
        log.debug("GDELT DOC: resolved %d/%d ticker names from SEC", len(result), len(symbols))
        return result
    except Exception as exc:
        log.warning("GDELT DOC: SEC name lookup failed (%s) — using $TICKER cashtag fallback", exc)
        return {}


async def _fetch_gdelt_doc_items(connector: GdeltDocConnector) -> list[NewsItem]:
    """Drain the async GDELT DOC iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_gdelt_doc_items(
    items: list[NewsItem],
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Deduplicate and push GDELT DOC NewsItems to news:queue.

    Articles are pre-tagged to a specific symbol (extraction_method='gdelt_doc') —
    no TickerExtractor needed. Mirrors _process_finnhub_items.
    """
    stats = {"fetched": 0, "queued": 0, "duplicates": 0}

    for item in items:
        stats["fetched"] += 1
        if not item.asset_tags:
            continue
        ticker = _TICKER_ALIASES.get(item.asset_tags[0], item.asset_tags[0])
        per_ticker = NewsItem(
            id=item.id,
            source=item.source,
            timestamp=item.timestamp,
            title=item.title,
            body=item.body,
            url=item.url,
            language=item.language,
            asset_tags=[ticker],
            extraction_method=item.extraction_method,
        )
        if deduplicator.is_duplicate_by_id(per_ticker) or deduplicator.is_duplicate_content_symbol(per_ticker):
            stats["duplicates"] += 1
            continue
        per_ticker.raw_ingested_at = datetime.now(timezone.utc)
        redis_client.rpush("news:queue", per_ticker.model_dump_json())
        stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_gdelt_doc_ingestion_worker")
def run_gdelt_doc_ingestion_worker() -> dict:
    """Celery entry-point for GDELT DOC 2.0 news ingestion.

    Queries the GDELT DOC 2.0 API per-ticker for recent English news (timespan=12h),
    tags each article explicitly to the queried ticker (extraction_method='gdelt_doc'),
    deduplicates, and pushes to news:queue.

    OFF by default — enable with GDELT_DOC_INGESTION_ENABLED=1 after confirming
    volume and relevance via mini-spike. No beat schedule added yet.

    Volume control: maxrecords=5 per ticker (96 tickers → ≤480 raw articles/fetch,
    minus dedup → typically <<100 new items). Lesson from Finnhub: keep this LOW.
    """
    if os.environ.get("GDELT_DOC_INGESTION_ENABLED", "0") == "0":
        return {"skipped": True, "reason": "gdelt_doc_ingestion_disabled"}

    redis_client = Redis.from_url(config.REDIS_URL)
    try:
        symbols = config.WATCHLIST_SYMBOLS or []
        ticker_names = _load_gdelt_doc_ticker_names(symbols)
        connector = GdeltDocConnector(
            symbols=symbols,
            ticker_names=ticker_names,
            timespan="12h",
            maxrecords=5,
        )
        deduplicator = Deduplicator(redis_client)
        items = asyncio.run(_fetch_gdelt_doc_items(connector))
        stats = _process_gdelt_doc_items(items, deduplicator, redis_client)
        log.info("GDELT DOC ingestion stats: %s", stats)
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as _pg:
                _pg.record_ingestion_stats("gdelt", stats)
        except Exception as _stats_exc:
            log.warning("Could not persist ingestion stats: %s", _stats_exc)
        return stats
    finally:
        redis_client.close()


async def _fetch_sec_edgar_items(connector) -> list:
    """Drain the async SEC EDGAR iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_sec_edgar_items(
    items: list,
    watchlist: set,
    deduplicator,
    redis_client,
) -> dict:
    """Filter by watchlist, deduplicate, and push EDGAR NewsItems to news:queue."""
    stats = {"fetched": 0, "queued": 0, "filtered": 0, "duplicates": 0}
    for item in items:
        stats["fetched"] += 1
        ticker = item.asset_tags[0] if item.asset_tags else None
        if not ticker or ticker not in watchlist:
            stats["filtered"] += 1
            continue
        if deduplicator.is_duplicate_by_id(item) or deduplicator.is_duplicate_content_symbol(item):
            stats["duplicates"] += 1
            continue
        item.raw_ingested_at = datetime.now(timezone.utc)
        redis_client.rpush("news:queue", item.model_dump_json())
        stats["queued"] += 1
    return stats


@app.task(name="src.workers.ingestion.run_sec_edgar_ingestion_worker")
def run_sec_edgar_ingestion_worker() -> dict:
    """Celery entry-point: fetch SEC 8-K/10-Q/10-K filings, push to news:queue.

    DISABLED (2026-07-02): OFF by default. Never produced a signal — the connector read
    a non-existent `ticker_symbol` field (EDGAR filings use CIK / display_names), so every
    item got empty asset_tags and was dropped downstream. Also redundant with S7 PEAD's
    8-K pipeline. Re-enable with SEC_EDGAR_INGESTION_ENABLED=1 ONLY after fixing the
    CIK→ticker attribution (e.g. via SecCompanyTickers) and enriching the body (8-K item).
    """
    if os.environ.get("SEC_EDGAR_INGESTION_ENABLED", "0") == "0":
        return {"skipped": True, "reason": "sec_edgar_ingestion_disabled"}

    redis_client = Redis.from_url(config.REDIS_URL)
    try:
        connector = SECEdgarConnector(form_types=["8-K", "10-Q", "10-K"])
        watchlist = set(config.WATCHLIST_SYMBOLS or [])
        deduplicator = Deduplicator(redis_client)

        items = asyncio.run(_fetch_sec_edgar_items(connector))
        stats = _process_sec_edgar_items(items, watchlist, deduplicator, redis_client)

        log.info("SEC EDGAR ingestion stats: %s", stats)
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as _pg:
                _pg.record_ingestion_stats("sec_edgar", stats)
        except Exception as _stats_exc:
            log.warning("Could not persist ingestion stats: %s", _stats_exc)
        return stats
    except Exception as exc:
        log.error("SEC EDGAR ingestion failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        redis_client.close()


# RSS feeds: stable public URLs, no API key required.
_RSS_FEEDS = [
    ("https://feeds.reuters.com/reuters/businessNews", "reuters"),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "cnbc"),
]


# Ticker-resolution safety (design: docs/Alembic_ticker_sentiment_design.docx §3, §11.1).
# A wrong ticker triggers an order on an unrelated stock — qualitatively worse than
# missing a news item — so the bare-text path must minimise false_positive_ticker_rate.
# Short tickers (F, T, C, GS, MA…) and tickers that are also common English words
# (CAT, ON, META, ALL…) match constantly in prose ("F-150 sales", "Plan C",
# "the ON switch", "GM" = general manager). In the RSS text path they are accepted
# ONLY via an explicit cashtag ($F). The reliable sources — GKG org-name lookup and
# MarketAux/Alpaca ticker metadata — still resolve these tickers, so recall is retained.
_AMBIGUOUS_WORD_TICKERS = frozenset({
    "ALL", "KEY", "CAT", "ON", "ARE", "NOW", "NEW", "REAL", "OPEN", "META",
    "ANY", "OUT", "ONE", "TWO", "BIG", "FOR", "CEO", "USA", "EPS", "IPO",
})
_MIN_BARE_TICKER_LEN = 3  # tickers shorter than this need a cashtag in free text
_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


def _extract_tickers_from_text(text: str, watchlist: set) -> list:
    """Find watchlist tickers in text, minimising false-positive ticker matches.

    Two match modes:
      1. Cashtag ($AAPL, $F): explicit, high-confidence — always accepted.
      2. Bare word (AAPL): accepted only for unambiguous tickers — length >= 3 and
         not a common English word. Short tickers (F, T, C, GS) and word-tickers
         (CAT, ON, META) are NOT matched bare ("F-150", "Plan C", "the ON switch");
         they require a cashtag.

    Word-boundary regex still applies: 'APPS' does not match 'APP'. The GKG
    (org-name) and MarketAux/Alpaca (metadata) paths resolve the excluded tickers
    reliably, so this only tightens the lowest-confidence (bare RSS text) path.
    """
    cashtags = {m.group(1) for m in _CASHTAG_RE.finditer(text)}
    bare_words = set(re.findall(r"\b[A-Z]{1,5}\b", text))
    out: list[str] = []
    for t in watchlist:
        if t in cashtags:
            out.append(t)
        elif (
            t in bare_words
            and len(t) >= _MIN_BARE_TICKER_LEN
            and t not in _AMBIGUOUS_WORD_TICKERS
        ):
            out.append(t)
    return out


async def _fetch_rss_items(connector) -> list:
    """Drain the async RSS iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_rss_items(
    items: list,
    watchlist: set,
    deduplicator,
    redis_client,
    source_name: str,
) -> dict:
    """Extract tickers, expand per-ticker, deduplicate, push to news:queue."""
    stats = {"fetched": 0, "queued": 0, "filtered": 0, "duplicates": 0}
    for item in items:
        stats["fetched"] += 1
        search_text = f"{item.title} {item.body}"
        tickers = _extract_tickers_from_text(search_text, watchlist)
        if not tickers:
            stats["filtered"] += 1
            continue
        for ticker in tickers:
            per_ticker = NewsItem(
                id=f"{item.id}:{ticker}",
                source=source_name,
                timestamp=item.timestamp,
                title=item.title,
                body=item.body,
                url=item.url,
                language=item.language,
                asset_tags=[ticker],
                extraction_method="regex",  # QT-03: RSS bare-word watchlist match
            )
            if deduplicator.is_duplicate_by_id(per_ticker) or deduplicator.is_duplicate_content_symbol(per_ticker):
                stats["duplicates"] += 1
                continue
            per_ticker.raw_ingested_at = datetime.now(timezone.utc)
            redis_client.rpush("news:queue", per_ticker.model_dump_json())
            stats["queued"] += 1
    return stats


@app.task(name="src.workers.ingestion.run_rss_ingestion_worker")
def run_rss_ingestion_worker() -> dict:
    """Celery entry-point: fetch RSS feeds, push ticker-tagged articles to news:queue.

    Fetches Reuters + CNBC RSS, extracts watchlist ticker mentions via regex,
    expands per-ticker, deduplicates, and pushes to news:queue.

    Schedule: every 15 min, Mon-Fri 14:00-21:00 UTC.
    """
    if os.environ.get("RSS_INGESTION_ENABLED", "0") == "0":
        return {"skipped": True, "reason": "RSS_INGESTION_ENABLED=0 (FIX-02: dead feeds, 0 news in 17d)"}

    redis_client = Redis.from_url(config.REDIS_URL)
    try:
        watchlist = set(config.WATCHLIST_SYMBOLS or [])
        deduplicator = Deduplicator(redis_client)
        total_stats: dict = {"fetched": 0, "queued": 0, "filtered": 0, "duplicates": 0}

        for feed_url, source_name in _RSS_FEEDS:
            try:
                connector = RSSConnector(
                    feed_url=feed_url,
                    source_name=source_name,
                    asset_tags=[],  # asset_tags handled by _process_rss_items per-ticker
                )
                items = asyncio.run(_fetch_rss_items(connector))
                stats = _process_rss_items(items, watchlist, deduplicator, redis_client, source_name)
                for k, v in stats.items():
                    total_stats[k] = total_stats.get(k, 0) + v
                log.info("RSS [%s] stats: %s", source_name, stats)
                try:
                    from src.store.pg_store import PostgreSQLStore
                    with PostgreSQLStore() as _pg:
                        _pg.record_ingestion_stats(source_name, stats)
                except Exception as _stats_exc:
                    log.warning("Could not persist ingestion stats: %s", _stats_exc)
            except Exception as exc:
                log.warning("RSS feed [%s] failed: %s — skipping", source_name, exc)

        log.info("RSS total ingestion stats: %s", total_stats)
        return total_stats
    finally:
        redis_client.close()


@app.task(name="src.workers.ingestion.run_news_ingestion_worker")
def run_news_ingestion_worker() -> dict:
    """Celery entry-point for NewsIngestionWorker.

    Fetches broad financial news from GDELT GKG, extracts tickers via
    PostgreSQL lookup, deduplicates by (url, ticker), and pushes annotated
    NewsItems to news:queue for the SentimentWorker to consume.

    Scheduling:
      - Celery beat: every 15 min, Mon–Fri 14:00–21:00 UTC
        (configured in src/workers/celery_app.py).

    Returns:
        Stats dict (see `_process_gkg_items`).
    """
    if not is_market_open():
        log.info("Market closed — skipping GDELT ingestion")
        return {"skipped": True, "reason": "market_closed"}

    # Open connections once per task. Closed in finally to avoid leaks.
    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)

    try:
        connector = GDELTGKGConnector()
        extractor = TickerExtractor(pg_conn)
        deduplicator = Deduplicator(redis_client)

        # Bridge async fetch into sync Celery task
        gkg_items = asyncio.run(_fetch_gkg_items(connector))
        watchlist = set(config.WATCHLIST_SYMBOLS or [])
        stats = _process_gkg_items(gkg_items, extractor, deduplicator, redis_client, watchlist=watchlist)

        log.info("Ingestion stats: %s", stats)
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as _pg:
                _pg.record_ingestion_stats("gdelt_gkg", stats)
        except Exception as _stats_exc:
            log.warning("Could not persist ingestion stats: %s", _stats_exc)
        return stats

    finally:
        pg_conn.close()
        redis_client.close()
