"""GDELT GKG v2 connector — live news ingestion with entity extraction."""

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
        url = record.get("V2DocumentIdentifier", "").strip()
        if not url:
            return None

        raw_date = record.get("date", "")
        try:
            ts = datetime.strptime(raw_date, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning("Invalid GKG timestamp %r, skipping %s", raw_date, url)
            return None

        raw_orgs = record.get("V2Organizations", "")
        org_names = [o.strip() for o in raw_orgs.split(";") if o.strip()]

        extras_str = record.get("extras", "{}")
        try:
            extras = json.loads(extras_str) if extras_str else {}
        except (json.JSONDecodeError, ValueError):
            extras = {}
        title = sanitize_text(extras.get("PageTitle", ""))

        return GKGNewsItem(
            id=url,
            source="gdelt_gkg",
            timestamp=ts,
            title=title,
            body=title,
            url=url,
            language="en",
            asset_tags=[],
            org_names=org_names,
        )
