"""GDELT GKG v2 connector — news ingestion via bulk CSV downloads.

Why bulk CSV instead of the GDELT API?
  The GDELT GKG v2 data with V2.1Organizations (pre-disambiguated company names)
  is only accessible via the GDELT bulk CSV files published every 15 minutes at
  http://data.gdeltproject.org/gdeltv2/. The REST API endpoint previously used
  (api.gdeltproject.org/api/v2/gkg/gkg) does not exist.

Live ingestion (fetch()):
  Downloads the latest 15-minute GKG CSV discovered via lastupdate.txt.

Historical backfill (fetch_historical()):
  Downloads one CSV file per sample_interval_minutes across the requested range.
  Default: 1 file/hour (sample_interval_minutes=60) → ~840 files for 6 months
  of market hours.

CSV format: tab-separated, 27 columns. Key columns (0-indexed):
  1=DATE, 4=DocumentIdentifier, 7=V1Themes, 14=V2.1Organizations, 26=V2ExtrasXML
"""

import asyncio
import io
import logging
import re
import zipfile
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.connectors.gdelt_base import (
    _GDELTBaseConnector,
    _GDELT_BACKOFF_BASE,
    _GDELT_BACKOFF_MAX,
    _GDELT_MAX_RETRIES,
)
from src.models.news import GKGNewsItem
from src.text.sanitizer import sanitize_text

logger = logging.getLogger(__name__)

_GDELT_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
_GDELT_BULK_BASE = "http://data.gdeltproject.org/gdeltv2/"

_FINANCIAL_THEMES = frozenset([
    "ECON_STOCKMARKET",
    "COMPANY_EARNINGS",
    "ECON_MERGE",
    "ECON_BANKRUPTCY",
])

_COL_DATE = 1
_COL_URL = 4
_COL_V1THEMES = 7
_COL_ORGS = 14
_COL_EXTRAS = 26
_MIN_COLS = 27


class GDELTGKGConnector(_GDELTBaseConnector, NewsConnector):
    """Fetches financial news from GDELT GKG v2 bulk CSV files.

    Yields GKGNewsItem objects with org_names populated from the V2.1Organizations
    column — the same field the live pipeline uses for TickerExtractor input.
    asset_tags is always left empty; NewsIngestionWorker fills it via TickerExtractor.
    """

    def __init__(self, max_records: int = 250, timespan: str = "15min") -> None:
        self.max_records = max_records
        # timespan kept for interface compatibility; not used in CSV mode.
        self.timespan = timespan

    async def fetch(self) -> AsyncIterator[GKGNewsItem]:
        """Fetch the latest 15-minute GKG file and yield financial news items.

        Steps:
          1. Download lastupdate.txt to discover the latest GKG CSV URL.
          2. Download and decompress the CSV zip via _download_csv().
          3. Filter rows by _is_financial_row() (V1Themes).
          4. Parse and yield up to max_records GKGNewsItem objects.
        """
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(_GDELT_LASTUPDATE_URL) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
            except Exception as e:
                logger.warning("Failed to fetch GDELT lastupdate.txt: %s", e)
                return

            gkg_url = None
            for line in text.strip().splitlines():
                if ".gkg.csv.zip" in line:
                    gkg_url = line.strip().split()[-1]
                    break

            if not gkg_url:
                logger.warning("No GKG file URL found in lastupdate.txt")
                return

            rows = await self._download_csv(session, gkg_url)
            count = 0
            for row in rows:
                if count >= self.max_records:
                    break
                if not self._is_financial_row(row):
                    continue
                item = self._parse_csv_row(row)
                if item is not None:
                    count += 1
                    yield item

    async def fetch_historical(
        self,
        start_date: datetime,
        end_date: datetime,
        max_records_per_file: int = 250,
        sample_interval_minutes: int = 60,
    ) -> AsyncIterator[GKGNewsItem]:
        """Fetch historical GKG records from GDELT bulk CSV files.

        Snaps start_date to the nearest prior 15-minute boundary, then
        downloads one file every sample_interval_minutes until end_date.
        404 responses (holiday/gap) are silently skipped. Sleeps 0.5s
        between files to be polite to GDELT's data server.

        Args:
            start_date: Start of the date range (inclusive).
            end_date: End of the date range (inclusive).
            max_records_per_file: Max financial articles to yield per file.
            sample_interval_minutes: Minutes between file downloads.
                15 = every file, 60 = hourly (default), 120 = every 2h.
        """
        snapped = start_date.replace(
            minute=(start_date.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        step = timedelta(minutes=max(15, (sample_interval_minutes // 15) * 15))

        async with aiohttp.ClientSession() as session:
            current = snapped
            while current <= end_date:
                url = f"{_GDELT_BULK_BASE}{current.strftime('%Y%m%d%H%M%S')}.gkg.csv.zip"
                rows = await self._download_csv(session, url)
                count = 0
                for row in rows:
                    if count >= max_records_per_file:
                        break
                    if not self._is_financial_row(row):
                        continue
                    item = self._parse_csv_row(row)
                    if item is not None:
                        count += 1
                        yield item
                current += step
                await asyncio.sleep(0.5)

    def _is_financial_row(self, row: list[str]) -> bool:
        """Return True if V1Themes column (index 7) contains any financial theme."""
        if len(row) <= _COL_V1THEMES:
            return False
        themes = set(row[_COL_V1THEMES].split("|"))
        return bool(themes & _FINANCIAL_THEMES)

    def _parse_csv_row(self, row: list[str]) -> GKGNewsItem | None:
        """Parse a GDELT GKG v2 TSV row into a GKGNewsItem.

        Returns None and logs a warning for rows with missing URL or
        unparseable DATE (both would corrupt backtest signals).
        """
        if len(row) < _MIN_COLS:
            return None

        url = row[_COL_URL].strip()
        if not url:
            return None

        raw_date = row[_COL_DATE].strip()
        try:
            ts = datetime.strptime(raw_date, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning("Invalid GKG timestamp %r, skipping %s", raw_date, url)
            return None

        # V2.1Organizations: "ORGNAME,charOffset;ORGNAME2,charOffset2"
        raw_orgs = row[_COL_ORGS].strip()
        org_names = []
        for entry in raw_orgs.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            name = entry.rsplit(",", 1)[0].strip()
            if name:
                org_names.append(name)

        # Extract PageTitle from V2ExtrasXML: <PAGE_TITLE>...</PAGE_TITLE>
        extras_xml = row[_COL_EXTRAS].strip()
        match = re.search(r"<PAGE_TITLE>(.*?)</PAGE_TITLE>", extras_xml, re.IGNORECASE)
        title = sanitize_text(match.group(1).strip() if match else "")

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

    async def _download_csv(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ) -> list[list[str]]:
        """Download a GDELT GKG CSV zip file and return parsed TSV rows.

        Returns [] on 404 (holiday/gap in GDELT data) or after max retries.
        HTTP 429 triggers exponential backoff (same parameters as _fetch_with_backoff).
        """
        for attempt in range(_GDELT_MAX_RETRIES):
            try:
                async with session.get(url) as resp:
                    if resp.status == 429:
                        wait = min(_GDELT_BACKOFF_BASE * (2**attempt), _GDELT_BACKOFF_MAX)
                        logger.warning("GDELT rate limited on CSV, waiting %.1fs", wait)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status == 404:
                        return []
                    resp.raise_for_status()
                    data = await resp.read()
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and attempt < _GDELT_MAX_RETRIES - 1:
                    wait = min(_GDELT_BACKOFF_BASE * (2**attempt), _GDELT_BACKOFF_MAX)
                    await asyncio.sleep(wait)
                    continue
                logger.warning("GDELT CSV download error %s: %s", e.status, e.message)
                return []
            except Exception as e:
                logger.warning("GDELT CSV download failed: %s", e)
                return []

            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    csv_name = next(n for n in zf.namelist() if n.endswith(".csv"))
                    content = zf.read(csv_name).decode("utf-8", errors="replace")
                return [line.split("\t") for line in content.splitlines() if line]
            except Exception as e:
                logger.warning("Failed to parse GDELT CSV zip from %s: %s", url, e)
                return []

        logger.warning("GDELT: max retries exceeded for %s", url)
        return []
