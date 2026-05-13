# GDELT GKG Bulk CSV Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken GDELT GKG API endpoint (which does not exist) with GDELT bulk CSV downloads so that `GDELTGKGConnector.fetch()` and `fetch_historical()` work with real data.

**Architecture:** The GDELT project publishes a new GKG v2 CSV file every 15 minutes at `http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.gkg.csv.zip`. For live ingestion, `fetch()` downloads the latest file via `lastupdate.txt`. For historical backtest, `fetch_historical()` downloads one file per `sample_interval_minutes` across the requested date range. The V2.1Organizations column (index 14, TSV) is the source of `org_names`, identical to the broken API's `V2Organizations` field. Existing `GDELTConnector` (artlist mode) and `_GDELTBaseConnector` are not changed.

**Tech Stack:** Python asyncio, aiohttp (HTTP), zipfile + io (in-memory decompression), re (PAGE_TITLE extraction), `src.connectors.gdelt_base._GDELT_BACKOFF_*` constants (reused for rate-limit backoff).

---

## File Map

| File | Action |
|------|--------|
| `src/connectors/gdelt_gkg.py` | Rewrite — new CSV-based implementation |
| `tests/connectors/test_gdelt_gkg.py` | Rewrite — all 11 tests replaced with CSV-based tests |

`src/connectors/gdelt_base.py` and `src/connectors/gdelt.py` are **not modified**.

---

## Background: GDELT GKG v2 CSV Format

Each file is a **tab-separated** CSV with 27 columns (0-indexed):

| Index | Field | Notes |
|-------|-------|-------|
| 1 | DATE | `YYYYMMDDHHMMSS` |
| 4 | DocumentIdentifier | Article URL |
| 7 | V1Themes | Pipe-separated themes e.g. `ECON_STOCKMARKET\|POLITICS` |
| 14 | V2.1Organizations | `ORGNAME,charOffset;ORGNAME2,charOffset2` |
| 26 | V2ExtrasXML | XML fragment containing `<PAGE_TITLE>title</PAGE_TITLE>` |

`lastupdate.txt` format — 3 lines, one per file type:
```
<size> <md5> http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.export.CSV.zip
<size> <md5> http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.mentions.CSV.zip
<size> <md5> http://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.gkg.csv.zip
```
The GKG URL is the line that contains `.gkg.csv.zip`.

---

## Task 1: CSV Parsing Helpers

**Files:**
- Modify: `src/connectors/gdelt_gkg.py`
- Modify: `tests/connectors/test_gdelt_gkg.py`

This task adds `_parse_csv_row()` and `_is_financial_row()` — the two pure parsing helpers. Existing code is left in place; the old `_parse_record()` and its tests are removed in Task 3.

- [ ] **Step 1: Add test fixtures and `make_csv_row` helper, write failing tests**

Replace the entire contents of `tests/connectors/test_gdelt_gkg.py` with:

```python
"""Tests for GDELTGKGConnector — bulk CSV mode."""

import asyncio
import io
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.models.news import GKGNewsItem


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_csv_row(
    date: str = "20251101140000",
    url: str = "https://reuters.com/article/1",
    v1themes: str = "ECON_STOCKMARKET",
    orgs: str = "APPLE INC,123;MICROSOFT CORPORATION,456",
    extras_xml: str = "<PAGE_TITLE>Apple and Microsoft report strong earnings</PAGE_TITLE>",
) -> list[str]:
    """Build a 27-column GDELT GKG v2 TSV row for testing."""
    row = [""] * 27
    row[1] = date       # DATE
    row[4] = url        # DocumentIdentifier
    row[7] = v1themes   # V1Themes
    row[14] = orgs      # V2.1Organizations
    row[26] = extras_xml  # V2ExtrasXML
    return row


def make_zip_bytes(rows: list[list[str]], filename: str = "20251101140000.gkg.csv") -> bytes:
    """Create an in-memory zip containing a GKG CSV with the given TSV rows."""
    csv_content = "\n".join("\t".join(row) for row in rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, csv_content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# _parse_csv_row
# ---------------------------------------------------------------------------

def test_parse_csv_row_yields_gkg_news_item():
    """Valid TSV row produces GKGNewsItem with correct org_names, url, source."""
    connector = GDELTGKGConnector()
    row = make_csv_row()
    item = connector._parse_csv_row(row)

    assert isinstance(item, GKGNewsItem)
    assert item.url == "https://reuters.com/article/1"
    assert item.source == "gdelt_gkg"
    assert item.asset_tags == []
    assert "APPLE INC" in item.org_names
    assert "MICROSOFT CORPORATION" in item.org_names


def test_parse_csv_row_missing_url_returns_none():
    """Row with empty DocumentIdentifier (index 4) → None."""
    connector = GDELTGKGConnector()
    row = make_csv_row(url="")
    assert connector._parse_csv_row(row) is None


def test_parse_csv_row_invalid_date_returns_none():
    """Row with unparseable DATE → None (look-ahead bias prevention)."""
    connector = GDELTGKGConnector()
    row = make_csv_row(date="not-a-date")
    assert connector._parse_csv_row(row) is None


def test_parse_csv_row_too_few_columns_returns_none():
    """Row with fewer than 27 columns → None."""
    connector = GDELTGKGConnector()
    assert connector._parse_csv_row(["col"] * 10) is None


def test_parse_csv_row_org_names_parsed_from_v2orgs():
    """V2.1Organizations 'NAME,offset;NAME2,offset2' → ['NAME', 'NAME2']."""
    connector = GDELTGKGConnector()
    row = make_csv_row(orgs="APPLE INC,123;MICROSOFT CORPORATION,456;")
    item = connector._parse_csv_row(row)

    assert item is not None
    assert item.org_names == ["APPLE INC", "MICROSOFT CORPORATION"]


def test_parse_csv_row_title_from_page_title():
    """Title extracted from V2ExtrasXML <PAGE_TITLE> tag."""
    connector = GDELTGKGConnector()
    row = make_csv_row(extras_xml="<PAGE_TITLE>Apple Q2 Earnings Beat</PAGE_TITLE>")
    item = connector._parse_csv_row(row)

    assert item is not None
    assert item.title == "Apple Q2 Earnings Beat"
    assert item.body == item.title


def test_parse_csv_row_empty_title_when_no_page_title():
    """Title is empty string when V2ExtrasXML has no PAGE_TITLE tag."""
    connector = GDELTGKGConnector()
    row = make_csv_row(extras_xml="<SOME_OTHER_TAG>stuff</SOME_OTHER_TAG>")
    item = connector._parse_csv_row(row)

    assert item is not None
    assert item.title == ""


def test_parse_csv_row_timestamp_utc():
    """DATE field '20251101140000' → datetime(2025, 11, 1, 14, 0, tzinfo=UTC)."""
    connector = GDELTGKGConnector()
    row = make_csv_row(date="20251101140000")
    item = connector._parse_csv_row(row)

    assert item is not None
    assert item.timestamp == datetime(2025, 11, 1, 14, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _is_financial_row
# ---------------------------------------------------------------------------

def test_is_financial_row_true_for_stockmarket():
    """Row with ECON_STOCKMARKET in V1Themes → True."""
    connector = GDELTGKGConnector()
    row = make_csv_row(v1themes="ECON_STOCKMARKET|POLITICS")
    assert connector._is_financial_row(row) is True


def test_is_financial_row_true_for_earnings():
    """Row with COMPANY_EARNINGS in V1Themes → True."""
    connector = GDELTGKGConnector()
    row = make_csv_row(v1themes="COMPANY_EARNINGS")
    assert connector._is_financial_row(row) is True


def test_is_financial_row_false_for_non_financial():
    """Row without any financial theme → False."""
    connector = GDELTGKGConnector()
    row = make_csv_row(v1themes="POLITICS|CRIME|WEATHER")
    assert connector._is_financial_row(row) is False


def test_is_financial_row_false_for_short_row():
    """Row with fewer than 8 columns → False (no V1Themes column)."""
    connector = GDELTGKGConnector()
    assert connector._is_financial_row(["col"] * 5) is False


# ---------------------------------------------------------------------------
# _download_csv  (Task 2 — leave empty for now)
# fetch()        (Task 3 — leave empty for now)
# fetch_historical() (Task 4 — leave empty for now)
# ---------------------------------------------------------------------------
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest tests/connectors/test_gdelt_gkg.py::test_parse_csv_row_yields_gkg_news_item \
    tests/connectors/test_gdelt_gkg.py::test_is_financial_row_true_for_stockmarket -v
```

Expected: `FAILED` — `AttributeError: 'GDELTGKGConnector' object has no attribute '_parse_csv_row'`

- [ ] **Step 3: Replace `gdelt_gkg.py` with the new CSV-based implementation**

Write the full file `src/connectors/gdelt_gkg.py`:

```python
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
```

- [ ] **Step 4: Run the parsing helper tests**

```bash
PYTHONPATH=. pytest tests/connectors/test_gdelt_gkg.py -k "parse_csv_row or is_financial_row" -v
```

Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add src/connectors/gdelt_gkg.py tests/connectors/test_gdelt_gkg.py
git commit -m "feat: add CSV parsing helpers to GDELTGKGConnector (_parse_csv_row, _is_financial_row)"
```

---

## Task 2: `_download_csv` Tests

**Files:**
- Modify: `tests/connectors/test_gdelt_gkg.py`

- [ ] **Step 1: Add `_download_csv` tests — append to the test file**

Add these tests after the `_is_financial_row` tests:

```python
# ---------------------------------------------------------------------------
# _download_csv
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_download_csv_returns_parsed_rows():
    """HTTP 200 with valid zip → list of TSV row lists."""
    connector = GDELTGKGConnector()
    rows = [make_csv_row(), make_csv_row(url="https://reuters.com/article/2")]
    zip_bytes = make_zip_bytes(rows)

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.read = AsyncMock(return_value=zip_bytes)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    result = await connector._download_csv(mock_session, "http://data.gdeltproject.org/gdeltv2/test.gkg.csv.zip")
    assert len(result) == 2
    assert result[0][4] == "https://reuters.com/article/1"


@pytest.mark.asyncio
async def test_download_csv_returns_empty_on_404():
    """HTTP 404 (holiday/gap) → empty list, no exception."""
    connector = GDELTGKGConnector()

    mock_resp = AsyncMock()
    mock_resp.status = 404
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    result = await connector._download_csv(mock_session, "http://data.gdeltproject.org/gdeltv2/missing.gkg.csv.zip")
    assert result == []


@pytest.mark.asyncio
async def test_download_csv_retries_on_429():
    """HTTP 429 on first attempt → sleeps → succeeds on second attempt."""
    connector = GDELTGKGConnector()
    rows = [make_csv_row()]
    zip_bytes = make_zip_bytes(rows)

    rate_limited = AsyncMock()
    rate_limited.status = 429
    rate_limited.__aenter__ = AsyncMock(return_value=rate_limited)
    rate_limited.__aexit__ = AsyncMock(return_value=None)

    ok_resp = AsyncMock()
    ok_resp.status = 200
    ok_resp.raise_for_status = MagicMock()
    ok_resp.read = AsyncMock(return_value=zip_bytes)
    ok_resp.__aenter__ = AsyncMock(return_value=ok_resp)
    ok_resp.__aexit__ = AsyncMock(return_value=None)

    call_count = [0]
    def side_effect(*args, **kwargs):
        call_count[0] += 1
        return rate_limited if call_count[0] == 1 else ok_resp

    mock_session = MagicMock()
    mock_session.get.side_effect = side_effect

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await connector._download_csv(mock_session, "http://data.gdeltproject.org/gdeltv2/test.gkg.csv.zip")

    assert len(result) == 1
    assert call_count[0] == 2
```

- [ ] **Step 2: Run `_download_csv` tests**

```bash
PYTHONPATH=. pytest tests/connectors/test_gdelt_gkg.py -k "download_csv" -v
```

Expected: `3 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/connectors/test_gdelt_gkg.py
git commit -m "test: add _download_csv tests for GDELT GKG bulk CSV connector"
```

---

## Task 3: `fetch()` Tests

**Files:**
- Modify: `tests/connectors/test_gdelt_gkg.py`

- [ ] **Step 1: Add `fetch()` tests — append to test file**

```python
# ---------------------------------------------------------------------------
# fetch()
# ---------------------------------------------------------------------------

LASTUPDATE_TXT = (
    "12345 abc123 http://data.gdeltproject.org/gdeltv2/20251101140000.export.CSV.zip\n"
    "23456 def456 http://data.gdeltproject.org/gdeltv2/20251101140000.mentions.CSV.zip\n"
    "34567 ghi789 http://data.gdeltproject.org/gdeltv2/20251101140000.gkg.csv.zip\n"
)


@pytest.mark.asyncio
async def test_fetch_yields_financial_items():
    """fetch() yields GKGNewsItem objects for rows with financial themes."""
    connector = GDELTGKGConnector()
    financial_row = make_csv_row()
    zip_bytes = make_zip_bytes([financial_row])

    async def mock_get(url, **kwargs):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        if "lastupdate" in url:
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.text = AsyncMock(return_value=LASTUPDATE_TXT)
        else:
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.read = AsyncMock(return_value=zip_bytes)
        return resp

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    assert items[0].url == "https://reuters.com/article/1"
    assert "APPLE INC" in items[0].org_names


@pytest.mark.asyncio
async def test_fetch_skips_non_financial_rows():
    """fetch() skips rows where V1Themes has no financial theme."""
    connector = GDELTGKGConnector()
    non_financial = make_csv_row(v1themes="POLITICS|CRIME")
    zip_bytes = make_zip_bytes([non_financial])

    async def mock_get(url, **kwargs):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        if "lastupdate" in url:
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.text = AsyncMock(return_value=LASTUPDATE_TXT)
        else:
            resp.status = 200
            resp.raise_for_status = MagicMock()
            resp.read = AsyncMock(return_value=zip_bytes)
        return resp

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_on_lastupdate_error():
    """fetch() yields nothing when lastupdate.txt download fails."""
    connector = GDELTGKGConnector()

    async def mock_get(url, **kwargs):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        resp.raise_for_status.side_effect = aiohttp.ClientResponseError(
            MagicMock(), MagicMock(), status=500
        )
        return resp

    import aiohttp as _aiohttp
    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_fetch_returns_empty_when_no_gkg_in_lastupdate():
    """fetch() yields nothing when lastupdate.txt contains no .gkg.csv.zip line."""
    connector = GDELTGKGConnector()

    async def mock_get(url, **kwargs):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=None)
        resp.status = 200
        resp.raise_for_status = MagicMock()
        resp.text = AsyncMock(return_value="12345 abc http://example.com/events.zip\n")
        return resp

    with patch("aiohttp.ClientSession.get", side_effect=mock_get):
        items = [item async for item in connector.fetch()]

    assert items == []
```

- [ ] **Step 2: Run `fetch()` tests**

```bash
PYTHONPATH=. pytest tests/connectors/test_gdelt_gkg.py -k "test_fetch_" -v
```

Expected: `4 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/connectors/test_gdelt_gkg.py
git commit -m "test: add fetch() tests for GDELT GKG bulk CSV connector"
```

---

## Task 4: `fetch_historical()` Tests + Full Suite Verification

**Files:**
- Modify: `tests/connectors/test_gdelt_gkg.py`

- [ ] **Step 1: Add `fetch_historical()` tests — append to test file**

```python
# ---------------------------------------------------------------------------
# fetch_historical()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_historical_downloads_at_sample_interval():
    """fetch_historical with 60-min interval over 2h range → 2 CSV downloads."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 11, 1, 14, 0, tzinfo=timezone.utc)
    end   = datetime(2025, 11, 1, 15, 0, tzinfo=timezone.utc)

    downloaded_urls = []

    async def mock_download(session, url):
        downloaded_urls.append(url)
        return [make_csv_row()]

    with patch.object(connector, "_download_csv", side_effect=mock_download):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(
                start, end, sample_interval_minutes=60
            )]

    assert len(downloaded_urls) == 2
    assert "20251101140000" in downloaded_urls[0]
    assert "20251101150000" in downloaded_urls[1]
    assert len(items) == 2


@pytest.mark.asyncio
async def test_fetch_historical_snaps_start_to_15min_boundary():
    """start_date 14:07 UTC → snapped to 14:00 UTC for the first file URL."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 11, 1, 14, 7, tzinfo=timezone.utc)
    end   = datetime(2025, 11, 1, 14, 7, tzinfo=timezone.utc)

    downloaded_urls = []

    async def mock_download(session, url):
        downloaded_urls.append(url)
        return []

    with patch.object(connector, "_download_csv", side_effect=mock_download):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            _ = [item async for item in connector.fetch_historical(start, end)]

    assert len(downloaded_urls) == 1
    assert "20251101140000" in downloaded_urls[0]


@pytest.mark.asyncio
async def test_fetch_historical_skips_404_files():
    """404 from _download_csv (empty list) → no items yielded, loop continues."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 11, 1, 14, 0, tzinfo=timezone.utc)
    end   = datetime(2025, 11, 1, 15, 0, tzinfo=timezone.utc)

    responses = [[], [make_csv_row()]]
    call_idx = [0]

    async def mock_download(session, url):
        r = responses[call_idx[0]]
        call_idx[0] += 1
        return r

    with patch.object(connector, "_download_csv", side_effect=mock_download):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            items = [item async for item in connector.fetch_historical(
                start, end, sample_interval_minutes=60
            )]

    assert len(items) == 1


@pytest.mark.asyncio
async def test_fetch_historical_sleeps_between_files():
    """fetch_historical sleeps 0.5s after each file download."""
    connector = GDELTGKGConnector()
    start = datetime(2025, 11, 1, 14, 0, tzinfo=timezone.utc)
    end   = datetime(2025, 11, 1, 15, 0, tzinfo=timezone.utc)

    sleep_calls = []

    async def mock_sleep(seconds):
        sleep_calls.append(seconds)

    with patch.object(connector, "_download_csv", return_value=[]):
        with patch("asyncio.sleep", side_effect=mock_sleep):
            _ = [item async for item in connector.fetch_historical(
                start, end, sample_interval_minutes=60
            )]

    assert len(sleep_calls) == 2
    assert all(s == 0.5 for s in sleep_calls)
```

- [ ] **Step 2: Run `fetch_historical()` tests**

```bash
PYTHONPATH=. pytest tests/connectors/test_gdelt_gkg.py -k "fetch_historical" -v
```

Expected: `4 passed`

- [ ] **Step 3: Run the complete `test_gdelt_gkg.py` file**

```bash
PYTHONPATH=. pytest tests/connectors/test_gdelt_gkg.py -v
```

Expected: `23 passed`  (12 parse/filter + 3 download + 4 fetch + 4 fetch_historical)

- [ ] **Step 4: Run the full test suite**

```bash
PYTHONPATH=. pytest --tb=short -q
```

Expected: `≥494 passed, 0 failed`  
(494 pre-existing + ~12 net new tests from this feature)

If any pre-existing tests fail, investigate before proceeding. Common cause: an import was broken in `gdelt_gkg.py`.

- [ ] **Step 5: Commit**

```bash
git add tests/connectors/test_gdelt_gkg.py
git commit -m "test: add fetch_historical() tests for GDELT GKG bulk CSV connector"
```

- [ ] **Step 6: Verify backtest dry-run with the new connector**

```bash
DATABASE_URL="postgresql://trading:trading@localhost:5432/trading" \
PYTHONPATH=. python scripts/run_backtest.py \
  --start 2025-11-01 \
  --end   2025-11-30 \
  --run-id dry-nov25-csv \
  --dry-run \
  --max-per-chunk 50 2>&1 | head -30
```

Expected: Phase 1 fetches real records from GDELT (> 0), Phase 2 dry-run fills scores, report shows signals_with_returns > 0.

If Phase 1 still shows 0 records, check that `asyncio.sleep(0.5)` is not being hit too fast and that the GDELT data server is reachable (`curl http://data.gdeltproject.org/gdeltv2/lastupdate.txt`).

- [ ] **Step 7: Final commit**

```bash
git add -p  # review any remaining changes
git commit -m "fix: replace broken GDELT GKG API endpoint with bulk CSV downloads"
```
