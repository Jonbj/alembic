"""SEC EDGAR news connector."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"


class SECEdgarConnector(NewsConnector):
    """SEC EDGAR API connector for filing ingestion.

    Fetches recent SEC filings (8-K, 10-Q, 10-K) from the EDGAR API,
    sanitizes content, and yields NewsItem objects asynchronously.
    """

    def __init__(
        self,
        form_types: list[str] | None = None,
        max_results: int = 20,
    ):
        """Initialize SEC EDGAR connector.

        Args:
            form_types: List of form types to fetch (default: ["8-K", "10-Q", "10-K"])
            max_results: Maximum number of filings to fetch (default 20)
        """
        self.form_types = form_types or ["8-K", "10-Q", "10-K"]
        self.max_results = max_results

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Fetch and yield sanitized NewsItem objects from EDGAR API.

        Yields:
            NewsItem objects with sanitized title and body

        Note:
            - Skips items where sanitization fails
            - Falls back to now() if date parsing fails
            - Includes ticker in asset_tags if available
        """
        # Build query: "8-K" OR "10-Q" OR "10-K"
        forms_q = " OR ".join(f'"{f}"' for f in self.form_types)

        params = {
            "q": forms_q,
            "dateRange": "custom",
            "startdt": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "hits.hits.total.value": self.max_results,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(_EDGAR_SEARCH_URL, params=params) as resp:
                if resp.status != 200:
                    return
                data = await resp.json(content_type=None)

        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})

            # Build title and body
            display_names = src.get("display_names", [])
            form_type = src.get("form_type", "")
            title = f"{display_names[0] if display_names else ''} — {form_type}"

            period_of_report = src.get("period_of_report", "")
            entity_name = src.get("entity_name", "")
            body = f"{period_of_report} {entity_name}"

            # Sanitize title and body
            try:
                clean_title = sanitize_text(title)
                clean_body = sanitize_text(body)
            except ValueError:
                # Homoglyph attack detected — skip item
                continue

            # Parse filing date (format: YYYY-MM-DD)
            raw_date = src.get("file_date", "")
            try:
                ts = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                # Fallback to now() if parsing fails
                ts = datetime.now(timezone.utc)

            # Extract ticker symbol
            ticker = src.get("ticker_symbol", "")

            yield NewsItem(
                id=src.get("id", ""),
                source="sec_edgar",
                timestamp=ts,
                title=clean_title,
                body=clean_body,
                url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={src.get('entity_id', '')}",
                language="en",
                asset_tags=[ticker] if ticker else [],
            )
