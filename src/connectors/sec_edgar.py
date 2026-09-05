"""SEC EDGAR Latest Filings connector."""

import asyncio
import html
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from xml.etree import ElementTree

import aiohttp

from src.connectors.base import NewsConnector
from src.connectors.ticker_resolver_providers import SecCompanyTickers
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

_EDGAR_LATEST_FILINGS_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
_MATERIAL_FORM_TYPES = ("8-K", "6-K")
_ATOM = "{http://www.w3.org/2005/Atom}"
_CIK_RE = re.compile(r"\((\d{10})\)\s+\(Filer\)")
_ACCESSION_RE = re.compile(r"accession-number=([\d-]+)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


class SECEdgarConnector(NewsConnector):
    """SEC EDGAR API connector for filing ingestion.

    Fetches material current reports from the global Latest Filings Atom feed,
    maps each filing's CIK through SEC company_tickers, and yields sanitized
    NewsItem objects. No per-symbol polling is performed.
    """

    def __init__(
        self,
        form_types: list[str] | None = None,
        max_results: int = 20,
        *,
        user_agent: str,
        company_tickers: SecCompanyTickers | None = None,
    ):
        """Initialize SEC EDGAR connector.

        Args:
            form_types: Material current-report forms (default: ["8-K", "6-K"])
            max_results: Maximum number of filings yielded across both feeds
            user_agent: SEC-compliant application name and contact
            company_tickers: Injectable cached SEC CIK-to-ticker lookup
        """
        self.form_types = form_types or list(_MATERIAL_FORM_TYPES)
        unsupported = set(self.form_types) - set(_MATERIAL_FORM_TYPES)
        if unsupported:
            forms = ", ".join(sorted(unsupported))
            raise ValueError(f"SEC EDGAR connector only accepts 8-K/6-K, got: {forms}")
        self.max_results = max_results
        self.user_agent = user_agent
        self.company_tickers = company_tickers or SecCompanyTickers(user_agent)

    async def fetch(self) -> AsyncIterator[NewsItem]:
        """Fetch and yield sanitized NewsItem objects from EDGAR API.

        Yields:
            NewsItem objects with sanitized title and body

        Note:
            - Skips items where sanitization fails
            - Falls back to now() if date parsing fails
            - Includes ticker in asset_tags if available
        """
        await asyncio.to_thread(self.company_tickers.load)
        items: list[NewsItem] = []
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/atom+xml",
        }
        async with aiohttp.ClientSession() as session:
            for form_type in self.form_types:
                params = {
                    "action": "getcurrent",
                    "type": form_type,
                    "owner": "exclude",
                    "count": self.max_results,
                    "output": "atom",
                }
                async with session.get(
                    _EDGAR_LATEST_FILINGS_URL,
                    params=params,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    items.extend(self._parse_feed(await resp.read()))

        items.sort(key=lambda item: item.timestamp, reverse=True)
        for item in items[: self.max_results]:
            yield item

    def _parse_feed(self, payload: bytes) -> list[NewsItem]:
        """Parse SEC's Atom format and attach tickers through the filing CIK."""
        root = ElementTree.fromstring(payload)
        items: list[NewsItem] = []
        for entry in root.findall(f"{_ATOM}entry"):
            raw_title = entry.findtext(f"{_ATOM}title", default="")
            cik_match = _CIK_RE.search(raw_title)
            if cik_match is None:
                continue

            category = entry.find(f"{_ATOM}category")
            form_type = category.get("term", "") if category is not None else ""
            if form_type not in self.form_types:
                continue

            link = entry.find(f"{_ATOM}link[@rel='alternate']")
            url = link.get("href", "") if link is not None else ""
            raw_id = entry.findtext(f"{_ATOM}id", default="")
            accession_match = _ACCESSION_RE.search(raw_id)
            item_id = accession_match.group(1) if accession_match else raw_id

            raw_summary = entry.findtext(f"{_ATOM}summary", default="")
            body = _HTML_BREAK_RE.sub("\n", raw_summary)
            body = html.unescape(_HTML_TAG_RE.sub("", body))
            body = "\n".join(line.strip() for line in body.splitlines() if line.strip())

            raw_updated = entry.findtext(f"{_ATOM}updated", default="")
            try:
                timestamp = datetime.fromisoformat(raw_updated.replace("Z", "+00:00"))
            except (TypeError, ValueError):
                timestamp = datetime.now(timezone.utc)

            try:
                clean_title = sanitize_text(raw_title)
                clean_body = sanitize_text(body or raw_title)
            except ValueError:
                continue

            cik = cik_match.group(1)
            items.append(
                NewsItem(
                    id=item_id,
                    source="sec_edgar",
                    timestamp=timestamp,
                    title=clean_title,
                    body=clean_body,
                    url=url,
                    language="en",
                    asset_tags=self.company_tickers.tickers_for_cik(cik),
                    extraction_method="source_metadata",
                )
            )
        return items
