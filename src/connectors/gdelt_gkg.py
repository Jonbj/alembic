"""GDELT GKG v2 connector — live news ingestion with entity extraction.

This connector queries the GDELT Global Knowledge Graph (GKG) v2 API in "gkg"
mode, which returns structured records with pre-disambiguated organisation names
in the `V2Organizations` field. It is the **discovery engine** of the news-driven
pipeline: instead of receiving a fixed watchlist, it scans broad financial news
and extracts the companies mentioned, handing them off to `TickerExtractor` for
ticker resolution.

Why GKG instead of the legacy artlist endpoint?
  - artlist returns article titles only, with no entity metadata.
  - GKG returns `V2Organizations`, a semicolon-separated list of company names
    already normalised by GDELT (e.g. "Apple Inc;Microsoft Corporation").
    This avoids brittle NER in our own code and leverages GDELT's
    disambiguation pipeline.

Query scope:
  - English-only (`sourcelang:english`).
  - Financial themes: stock market, earnings, M&A, bankruptcy.
  - `timespan=15min` aligns with the Celery beat schedule so each run covers
    the gap since the previous run.

Output:
  - Yields `GKGNewsItem` instances with `org_names` populated.
  - `asset_tags` is intentionally left empty; `NewsIngestionWorker` fills it
    after ticker extraction so the connector remains decoupled from the DB.
"""

import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.connectors.gdelt_base import _GDELTBaseConnector
from src.models.news import GKGNewsItem
from src.text.sanitizer import sanitize_text

logger = logging.getLogger(__name__)

_GDELT_GKG_URL = "https://api.gdeltproject.org/api/v2/gkg/gkg"
_GDELT_GKG_QUERY = (
    "sourcelang:english "
    "(theme:ECON_STOCKMARKET OR theme:COMPANY_EARNINGS "
    "OR theme:ECON_MERGE OR theme:ECON_BANKRUPTCY)"
)


class GDELTGKGConnector(_GDELTBaseConnector, NewsConnector):
    """Fetches broad financial news from GDELT GKG v2 API.

    Returns GKGNewsItem objects with org_names populated from V2Organizations.
    asset_tags is left empty — caller (NewsIngestionWorker) fills it via TickerExtractor.
    """

    def __init__(self, max_records: int = 250, timespan: str = "15min") -> None:
        self.max_records = max_records
        self.timespan = timespan

    async def fetch(self) -> AsyncIterator[GKGNewsItem]:  # type: ignore[override]
        """Fetch recent GKG records and yield parsed GKGNewsItem objects.

        Steps:
          1. Build query parameters (mode=gkg, maxrecords, timespan).
          2. Open aiohttp session and call `_fetch_with_backoff` (inherited).
          3. Iterate over `data["gkg"]` and parse each record.
          4. Skip records with missing URL or unparseable timestamp
             (look-ahead bias prevention).

        Yields:
            GKGNewsItem instances, one per GDELT record.
        """
        params = {
            "query": _GDELT_GKG_QUERY,
            "mode": "gkg",
            "maxrecords": self.max_records,
            "format": "json",
            "timespan": self.timespan,
        }
        async with aiohttp.ClientSession() as session:
            data = await self._fetch_with_backoff(session, params, url=_GDELT_GKG_URL)

        if data is None:
            return

        for record in data.get("gkg", []):
            item = self._parse_record(record)
            if item is not None:
                yield item

    def _parse_record(self, record: dict) -> GKGNewsItem | None:
        """Parse a single raw GDELT GKG record into a GKGNewsItem.

        Fields consumed:
          - V2DocumentIdentifier → item.url (also item.id). Empty → skip.
          - date                → item.timestamp. Format "%Y%m%d%H%M%S".
                                  Invalid → skip (prevents look-ahead bias).
          - V2Organizations     → semicolon-split, stripped, empty removed.
          - extras.PageTitle    → item.title (sanitised). Fallback to empty.

        Returns:
            GKGNewsItem on success, None if the record should be discarded.
        """
        # --- URL validation --------------------------------------------------
        url = record.get("V2DocumentIdentifier", "").strip()
        if not url:
            # Without a URL we cannot build a stable item.id, and we cannot
            # deduplicate. Skip silently — GDELT occasionally returns records
            # with empty identifiers.
            return None

        # --- Timestamp parsing ----------------------------------------------
        raw_date = record.get("date", "")
        try:
            ts = datetime.strptime(raw_date, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            # Invalid timestamps would corrupt backtests (look-ahead bias).
            # We never guess or use datetime.now() as a fallback.
            logger.warning("Invalid GKG timestamp %r, skipping %s", raw_date, url)
            return None

        # --- Organisation extraction -----------------------------------------
        raw_orgs = record.get("V2Organizations", "")
        # GDELT separates organisations with ";". Empty tokens (trailing ";")
        # are filtered out to avoid downstream noise.
        org_names = [o.strip() for o in raw_orgs.split(";") if o.strip()]

        # --- Title extraction ------------------------------------------------
        extras_str = record.get("extras", "{}")
        try:
            extras = json.loads(extras_str) if extras_str else {}
        except (json.JSONDecodeError, ValueError):
            # Malformed JSON in extras is non-fatal; treat as empty dict.
            extras = {}
        # Sanitise before entering the pipeline (CLAUDE.md requirement).
        title = sanitize_text(extras.get("PageTitle", ""))

        # --- Build GKGNewsItem -----------------------------------------------
        return GKGNewsItem(
            id=url,
            source="gdelt_gkg",
            timestamp=ts,
            title=title,
            body=title,  # GKG mode has no article body; title is best proxy.
            url=url,
            language="en",
            asset_tags=[],  # Will be populated by NewsIngestionWorker → TickerExtractor.
            org_names=org_names,
        )
