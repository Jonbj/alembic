# Multi-Asset News-Driven Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static watchlist with a GDELT GKG-driven pipeline that automatically discovers tickers from financial news and routes them to the existing SentimentWorker.

**Architecture:** A new `GDELTGKGConnector` queries the GDELT GKG v2 API for broad financial news and extracts organisation names already disambiguated by GDELT. A `TickerExtractor` maps those names to tickers via a PostgreSQL lookup table. A new `NewsIngestionWorker` Celery task (every 15 min) orchestrates fetch → extract → deduplicate → enqueue. The existing `SentimentWorker` and downstream pipeline are unchanged.

**Tech Stack:** Python 3.11, aiohttp, psycopg2, Redis, Celery, Pydantic v2, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-05-13-multi-asset-news-driven-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `migrations/004_add_ticker_lookup.sql` | Create | ticker_lookup table + indexes |
| `data/sp500_tickers.csv` | Create | Seed data: S&P 500 + ETF company→ticker |
| `scripts/seed_ticker_lookup.py` | Create | One-time DB seed script |
| `src/models/news.py` | Modify | Add `GKGNewsItem` model |
| `src/connectors/deduplicator.py` | Modify | Add `is_duplicate_by_id` method |
| `src/config.py` | Modify | Add `WATCHLIST_SYMBOLS` field |
| `src/connectors/gdelt_base.py` | Create | `_GDELTBaseConnector` with shared backoff logic |
| `src/connectors/gdelt.py` | Modify | Inherit from `_GDELTBaseConnector` |
| `src/connectors/gdelt_gkg.py` | Create | `GDELTGKGConnector` |
| `src/connectors/ticker_extractor.py` | Create | `TickerExtractor` with normalize + PG lookup |
| `src/workers/ingestion.py` | Create | `run_news_ingestion_worker` Celery task |
| `src/workers/celery_app.py` | Modify | Add ingestion beat schedule |
| `src/workers/performance.py` | Modify | Replace hardcoded symbols with `config.WATCHLIST_SYMBOLS` |
| `tests/connectors/test_gdelt_gkg.py` | Create | GDELTGKGConnector unit tests |
| `tests/connectors/test_ticker_extractor.py` | Create | TickerExtractor unit tests |
| `tests/workers/test_ingestion_worker.py` | Create | NewsIngestionWorker integration tests |

---

## Task 1: DB Migration — ticker_lookup table

**Files:**
- Create: `migrations/004_add_ticker_lookup.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migrations/004_add_ticker_lookup.sql
-- Lookup table mapping GDELT organisation names to ticker symbols.
-- Used by TickerExtractor for news-driven ticker discovery.

CREATE TABLE IF NOT EXISTS ticker_lookup (
    id           SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    aliases      TEXT[] NOT NULL DEFAULT '{}',
    ticker       TEXT NOT NULL,
    source       TEXT NOT NULL  -- 'sp500', 'etf', 'manual'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ticker_lookup_name_ticker
    ON ticker_lookup (lower(company_name), ticker);
CREATE INDEX IF NOT EXISTS idx_ticker_lookup_name
    ON ticker_lookup (lower(company_name));
CREATE INDEX IF NOT EXISTS idx_ticker_lookup_aliases
    ON ticker_lookup USING GIN (aliases);
```

- [ ] **Step 2: Apply migration**

```bash
psql $DATABASE_URL -f migrations/004_add_ticker_lookup.sql
```

Expected output:
```
CREATE TABLE
CREATE INDEX
CREATE INDEX
CREATE INDEX
```

- [ ] **Step 3: Commit**

```bash
git add migrations/004_add_ticker_lookup.sql
git commit -m "feat: add ticker_lookup table migration"
```

---

## Task 2: Seed data — sp500_tickers.csv + seed script

**Files:**
- Create: `data/sp500_tickers.csv`
- Create: `scripts/seed_ticker_lookup.py`

- [ ] **Step 1: Create CSV seed file**

Create `data/sp500_tickers.csv` with this content (extend to full S&P 500 list from [Wikipedia](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies)):

```csv
company_name,ticker,source,aliases
Apple Inc,AAPL,sp500,Apple Computer|Apple Incorporated
Microsoft Corporation,MSFT,sp500,Microsoft Corp
Alphabet Inc,GOOGL,sp500,Google LLC|Google Inc
Amazon.com Inc,AMZN,sp500,Amazon Inc|Amazon.com
NVIDIA Corporation,NVDA,sp500,NVIDIA Corp
Meta Platforms Inc,META,sp500,Facebook Inc|Meta Platforms
Tesla Inc,TSLA,sp500,Tesla Motors
Berkshire Hathaway Inc,BRK.B,sp500,Berkshire Hathaway
JPMorgan Chase & Co,JPM,sp500,JPMorgan Chase
Johnson & Johnson,JNJ,sp500,
Visa Inc,V,sp500,Visa International
Mastercard Inc,MA,sp500,Mastercard International
Procter & Gamble Co,PG,sp500,Procter & Gamble
UnitedHealth Group Inc,UNH,sp500,UnitedHealth Group
Exxon Mobil Corporation,XOM,sp500,ExxonMobil|Exxon Mobil Corp
Chevron Corporation,CVX,sp500,Chevron Corp
Home Depot Inc,HD,sp500,The Home Depot
Merck & Co Inc,MRK,sp500,Merck & Co
AbbVie Inc,ABBV,sp500,
Pfizer Inc,PFE,sp500,
Costco Wholesale Corporation,COST,sp500,Costco Wholesale Corp
Salesforce Inc,CRM,sp500,Salesforce.com Inc
Adobe Inc,ADBE,sp500,Adobe Systems
Netflix Inc,NFLX,sp500,
Intel Corporation,INTC,sp500,Intel Corp
Broadcom Inc,AVGO,sp500,Broadcom Corporation
Qualcomm Inc,QCOM,sp500,QUALCOMM Inc
Texas Instruments Inc,TXN,sp500,Texas Instruments
Walmart Inc,WMT,sp500,Wal-Mart Stores
Walt Disney Co,DIS,sp500,The Walt Disney Company|Disney
Comcast Corporation,CMCSA,sp500,Comcast Corp
Cisco Systems Inc,CSCO,sp500,Cisco Systems
Oracle Corporation,ORCL,sp500,Oracle Corp
International Business Machines Corporation,IBM,sp500,IBM Corporation|IBM Corp
Goldman Sachs Group Inc,GS,sp500,Goldman Sachs
Bank of America Corporation,BAC,sp500,Bank of America Corp
Wells Fargo & Company,WFC,sp500,Wells Fargo Bank
Morgan Stanley,MS,sp500,
Citigroup Inc,C,sp500,Citibank|Citi
American Express Company,AXP,sp500,American Express
Boeing Co,BA,sp500,The Boeing Company|Boeing Company
Caterpillar Inc,CAT,sp500,Caterpillar
3M Co,MMM,sp500,3M Company|Minnesota Mining and Manufacturing
General Electric Co,GE,sp500,GE Aerospace
Ford Motor Company,F,sp500,Ford Motor Co
General Motors Company,GM,sp500,General Motors Corp
AT&T Inc,T,sp500,AT&T Corporation
Verizon Communications Inc,VZ,sp500,Verizon Communications
T-Mobile US Inc,TMUS,sp500,T-Mobile US
Starbucks Corporation,SBUX,sp500,Starbucks Corp
McDonald's Corporation,MCD,sp500,McDonald's Corp
Nike Inc,NKE,sp500,Nike
SPDR S&P 500 ETF Trust,SPY,etf,SPDR S&P 500 ETF
Invesco QQQ Trust,QQQ,etf,Invesco QQQ|PowerShares QQQ
iShares Russell 2000 ETF,IWM,etf,
Financial Select Sector SPDR Fund,XLF,etf,
Technology Select Sector SPDR Fund,XLK,etf,
```

- [ ] **Step 2: Create seed script**

```python
# scripts/seed_ticker_lookup.py
"""Seed the ticker_lookup table from data/sp500_tickers.csv.

Run once after applying migration 004:
    python scripts/seed_ticker_lookup.py
"""
import csv
import os
import sys
from pathlib import Path

import psycopg2

DATA_PATH = Path(__file__).parent.parent / "data" / "sp500_tickers.csv"


def seed(database_url: str) -> int:
    conn = psycopg2.connect(database_url)
    inserted = 0
    try:
        with conn.cursor() as cur:
            with DATA_PATH.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_aliases = row.get("aliases", "").strip()
                    aliases = [a.strip() for a in raw_aliases.split("|") if a.strip()]
                    cur.execute(
                        """
                        INSERT INTO ticker_lookup (company_name, ticker, source, aliases)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (lower(company_name), ticker) DO NOTHING
                        """,
                        (row["company_name"], row["ticker"], row["source"], aliases),
                    )
                    if cur.rowcount:
                        inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    n = seed(url)
    print(f"Inserted {n} rows into ticker_lookup")
```

- [ ] **Step 3: Verify script runs (dry run)**

```bash
python scripts/seed_ticker_lookup.py
```

Expected output:
```
Inserted 57 rows into ticker_lookup
```

- [ ] **Step 4: Commit**

```bash
git add data/sp500_tickers.csv scripts/seed_ticker_lookup.py
git commit -m "feat: add ticker_lookup seed data and seed script"
```

---

## Task 3: GKGNewsItem model + Deduplicator.is_duplicate_by_id

**Files:**
- Modify: `src/models/news.py`
- Modify: `src/connectors/deduplicator.py`
- Test (deduplicator): `tests/connectors/test_deduplicator.py`

- [ ] **Step 1: Write failing test for `is_duplicate_by_id`**

Add to `tests/connectors/test_deduplicator.py`:

```python
def test_is_duplicate_by_id_first_seen_returns_false():
    """First occurrence by ID returns False."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True
    dedup = Deduplicator(mock_redis)
    item = make_item("same title", "same body")
    assert dedup.is_duplicate_by_id(item) is False


def test_is_duplicate_by_id_second_seen_returns_true():
    """Second occurrence by ID returns True."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = None
    dedup = Deduplicator(mock_redis)
    item = make_item("same title", "same body")
    assert dedup.is_duplicate_by_id(item) is True


def test_same_content_different_id_not_duplicate():
    """Two items with same title/body but different IDs are not duplicates via is_duplicate_by_id."""
    calls = {}

    def fake_set(key, val, ex, nx):
        if key not in calls:
            calls[key] = True
            return True  # first time
        return None  # subsequent

    mock_redis = MagicMock()
    mock_redis.set.side_effect = fake_set
    dedup = Deduplicator(mock_redis)

    item_aapl = NewsItem(
        id="https://example.com/article:AAPL",
        source="test", timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        title="Apple and Microsoft earnings", body="Apple and Microsoft earnings",
        url="https://example.com/article", language="en", asset_tags=["AAPL"],
    )
    item_msft = NewsItem(
        id="https://example.com/article:MSFT",
        source="test", timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        title="Apple and Microsoft earnings", body="Apple and Microsoft earnings",
        url="https://example.com/article", language="en", asset_tags=["MSFT"],
    )
    assert dedup.is_duplicate_by_id(item_aapl) is False
    assert dedup.is_duplicate_by_id(item_msft) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/connectors/test_deduplicator.py::test_is_duplicate_by_id_first_seen_returns_false -v
```

Expected: `FAILED` with `AttributeError: 'Deduplicator' object has no attribute 'is_duplicate_by_id'`

- [ ] **Step 3: Add `GKGNewsItem` to `src/models/news.py`**

Add at end of `src/models/news.py`:

```python
class GKGNewsItem(NewsItem):
    """NewsItem enriched with GDELT GKG organisation names."""

    org_names: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Add `is_duplicate_by_id` to `src/connectors/deduplicator.py`**

Add after `is_duplicate`:

```python
def is_duplicate_by_id(self, item: NewsItem) -> bool:
    """Check if item is a duplicate by item.id.

    Used by the ingestion worker for multi-ticker deduplication:
    two items from the same article but different tickers have the
    same title+body hash but different IDs, so is_duplicate() would
    incorrectly drop the second. This method deduplicates by ID instead.
    """
    key = f"dedup:id:{hashlib.sha256(item.id.encode()).hexdigest()}"
    result = self._r.set(key, 1, ex=_DEDUP_TTL_SECONDS, nx=True)
    return result is None
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/connectors/test_deduplicator.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add src/models/news.py src/connectors/deduplicator.py tests/connectors/test_deduplicator.py
git commit -m "feat: add GKGNewsItem model and Deduplicator.is_duplicate_by_id"
```

---

## Task 4: WATCHLIST_SYMBOLS in config

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_config.py`:

```python
class TestWatchlistSymbols:
    def test_default_watchlist_is_populated(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        assert isinstance(cfg.WATCHLIST_SYMBOLS, list)
        assert len(cfg.WATCHLIST_SYMBOLS) > 0

    def test_default_watchlist_contains_expected_symbols(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        for symbol in ("AAPL", "MSFT", "GOOGL", "NVDA", "SPY", "QQQ"):
            assert symbol in cfg.WATCHLIST_SYMBOLS

    def test_watchlist_overridable(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
            WATCHLIST_SYMBOLS=["TSLA", "AMZN"],
        )
        assert cfg.WATCHLIST_SYMBOLS == ["TSLA", "AMZN"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py::TestWatchlistSymbols -v
```

Expected: `FAILED` with `ValidationError: ... WATCHLIST_SYMBOLS`

- [ ] **Step 3: Add `WATCHLIST_SYMBOLS` to `src/config.py`**

Add after `MAX_CONSECUTIVE_FALLBACKS` field (around line 79):

```python
    # Symbol universe for performance calculations and watchlist filtering
    WATCHLIST_SYMBOLS: list[str] = Field(
        default=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "SPY", "QQQ"]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add WATCHLIST_SYMBOLS to Config"
```

---

## Task 5: _GDELTBaseConnector refactor

**Files:**
- Create: `src/connectors/gdelt_base.py`
- Modify: `src/connectors/gdelt.py`

- [ ] **Step 1: Create `src/connectors/gdelt_base.py`**

```python
"""Shared base for GDELT connectors."""

import logging

import aiohttp

logger = logging.getLogger(__name__)

_GDELT_BACKOFF_BASE = 2.0
_GDELT_BACKOFF_MAX = 60.0
_GDELT_MAX_RETRIES = 5


class _GDELTBaseConnector:
    """Mixin providing exponential-backoff fetch for GDELT API endpoints."""

    async def _fetch_with_backoff(
        self,
        session: aiohttp.ClientSession,
        params: dict,
        url: str,
    ) -> dict | None:
        """Fetch a GDELT API URL with exponential backoff for HTTP 429."""
        import asyncio

        for attempt in range(_GDELT_MAX_RETRIES):
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 429:
                        wait_time = min(
                            _GDELT_BACKOFF_BASE * (2**attempt), _GDELT_BACKOFF_MAX
                        )
                        logger.warning(
                            "GDELT rate limited, waiting %.1fs before retry", wait_time
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and attempt < _GDELT_MAX_RETRIES - 1:
                    continue
                logger.warning("GDELT HTTP error %s: %s", e.status, e.message)
                return None
        logger.warning("GDELT: Max retries exceeded after rate limiting")
        return None
```

- [ ] **Step 2: Update `src/connectors/gdelt.py` to use the base class**

Replace the top of `src/connectors/gdelt.py`:

Old imports/constants block (lines 1-19):
```python
"""GDELT news connector."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

logger = logging.getLogger(__name__)

_GDELT_DOC2_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_GDELT_BACKOFF_BASE = 2.0  # seconds for exponential backoff
_GDELT_BACKOFF_MAX = 60.0  # max wait between retries
_GDELT_MAX_RETRIES = 5
```

New version:
```python
"""GDELT news connector (artlist mode) — used for historical backfill."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.connectors.gdelt_base import _GDELTBaseConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

logger = logging.getLogger(__name__)

_GDELT_DOC2_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
```

Change class declaration from:
```python
class GDELTConnector(NewsConnector):
```
to:
```python
class GDELTConnector(_GDELTBaseConnector, NewsConnector):
```

Update `_fetch_with_backoff` call in `fetch_historical` — find and replace:
```python
                    data = await self._fetch_with_backoff(session, params)
```
with:
```python
                    data = await self._fetch_with_backoff(session, params, url=_GDELT_DOC2_URL)
```

Delete the old `_fetch_with_backoff` method from `GDELTConnector` (lines 101-123 in the original file).

- [ ] **Step 3: Run existing GDELT tests to verify no regression**

```bash
pytest tests/connectors/test_gdelt.py tests/connectors/test_gdelt_historical.py -v
```

Expected: all tests `PASSED` (no behavioral change, only inheritance restructuring)

- [ ] **Step 4: Commit**

```bash
git add src/connectors/gdelt_base.py src/connectors/gdelt.py
git commit -m "refactor: extract _GDELTBaseConnector with shared backoff logic"
```

---

## Task 6: GDELTGKGConnector

**Files:**
- Create: `src/connectors/gdelt_gkg.py`
- Create: `tests/connectors/test_gdelt_gkg.py`

- [ ] **Step 1: Write failing tests**

Create `tests/connectors/test_gdelt_gkg.py`:

```python
"""Tests for GDELTGKGConnector."""

import json
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.models.news import GKGNewsItem


SAMPLE_GKG_RESPONSE = {
    "gkg": [
        {
            "date": "20260513140000",
            "V2Organizations": "Apple Inc;Microsoft Corporation;",
            "V2DocumentIdentifier": "https://reuters.com/article/tech-q2",
            "V2SourceCommonName": "Reuters",
            "extras": json.dumps({"PageTitle": "Apple and Microsoft report strong Q2 earnings"}),
        }
    ]
}

SAMPLE_GKG_RESPONSE_MISSING_URL = {
    "gkg": [
        {
            "date": "20260513140000",
            "V2Organizations": "Apple Inc",
            "V2DocumentIdentifier": "",
            "extras": json.dumps({"PageTitle": "Some article"}),
        }
    ]
}

SAMPLE_GKG_RESPONSE_INVALID_DATE = {
    "gkg": [
        {
            "date": "not-a-date",
            "V2Organizations": "Apple Inc",
            "V2DocumentIdentifier": "https://example.com/article",
            "extras": json.dumps({"PageTitle": "Some article"}),
        }
    ]
}


def make_mock_resp(response_data: dict) -> AsyncMock:
    resp = AsyncMock()
    resp.json = AsyncMock(return_value=response_data)
    resp.raise_for_status = MagicMock()
    resp.status = 200
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.mark.asyncio
async def test_gkg_yields_gkg_news_item():
    """Connector yields GKGNewsItem with org_names extracted from V2Organizations."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE)):
        items = [item async for item in connector.fetch()]

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, GKGNewsItem)
    assert "Apple Inc" in item.org_names
    assert "Microsoft Corporation" in item.org_names
    assert item.url == "https://reuters.com/article/tech-q2"
    assert item.source == "gdelt_gkg"
    assert item.asset_tags == []


@pytest.mark.asyncio
async def test_gkg_title_from_page_title():
    """Title is extracted from extras.PageTitle."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE)):
        items = [item async for item in connector.fetch()]

    assert items[0].title == "Apple and Microsoft report strong Q2 earnings"
    assert items[0].body == items[0].title


@pytest.mark.asyncio
async def test_gkg_missing_url_skipped():
    """Records with empty V2DocumentIdentifier are skipped."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE_MISSING_URL)):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gkg_invalid_date_skipped():
    """Records with unparseable date are skipped (look-ahead bias prevention)."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE_INVALID_DATE)):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gkg_empty_response():
    """Empty gkg list yields no items."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp({"gkg": []})):
        items = [item async for item in connector.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_gkg_org_names_split_and_stripped():
    """V2Organizations semicolon-split, whitespace stripped, empty strings removed."""
    connector = GDELTGKGConnector()
    resp_data = {
        "gkg": [
            {
                "date": "20260513140000",
                "V2Organizations": " Apple Inc ; Microsoft Corporation ; ; ",
                "V2DocumentIdentifier": "https://example.com/1",
                "extras": json.dumps({"PageTitle": "Tech news"}),
            }
        ]
    }
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(resp_data)):
        items = [item async for item in connector.fetch()]

    assert items[0].org_names == ["Apple Inc", "Microsoft Corporation"]


@pytest.mark.asyncio
async def test_gkg_timestamp_parsed_correctly():
    """date field parsed to UTC datetime."""
    connector = GDELTGKGConnector()
    with patch("aiohttp.ClientSession.get", return_value=make_mock_resp(SAMPLE_GKG_RESPONSE)):
        items = [item async for item in connector.fetch()]

    ts = items[0].timestamp
    assert ts.tzinfo == timezone.utc
    assert ts.year == 2026
    assert ts.month == 5
    assert ts.day == 13
    assert ts.hour == 14
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/connectors/test_gdelt_gkg.py -v
```

Expected: `FAILED` (multiple) with `ModuleNotFoundError: No module named 'src.connectors.gdelt_gkg'`

- [ ] **Step 3: Implement `src/connectors/gdelt_gkg.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/connectors/test_gdelt_gkg.py -v
```

Expected: all 7 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/connectors/gdelt_gkg.py tests/connectors/test_gdelt_gkg.py
git commit -m "feat: add GDELTGKGConnector for live news ingestion"
```

---

## Task 7: TickerExtractor

**Files:**
- Create: `src/connectors/ticker_extractor.py`
- Create: `tests/connectors/test_ticker_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/connectors/test_ticker_extractor.py`:

```python
"""Tests for TickerExtractor."""

from unittest.mock import MagicMock, call

import pytest

from src.connectors.ticker_extractor import TickerExtractor


def make_pg_conn(rows_by_query: dict) -> MagicMock:
    """Mock psycopg2 connection that returns rows based on query substring."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    def execute_side_effect(sql, params=None):
        cur._last_sql = sql
        cur._last_params = params

    def fetchall_side_effect():
        for key, rows in rows_by_query.items():
            if key in (cur._last_sql or ""):
                return rows
        return []

    cur.execute.side_effect = execute_side_effect
    cur.fetchall.side_effect = fetchall_side_effect

    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


def test_extract_exact_match():
    """Known org name maps to correct ticker."""
    conn = make_pg_conn({"lower(company_name)": [("AAPL",)]})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["Apple Inc"])
    assert "AAPL" in result


def test_extract_empty_org_names_returns_empty():
    """Empty input returns empty list without querying DB."""
    conn = MagicMock()
    extractor = TickerExtractor(conn)
    assert extractor.extract([]) == []
    conn.cursor.assert_not_called()


def test_extract_no_match_returns_empty():
    """Unknown org name returns empty list."""
    conn = make_pg_conn({"lower(company_name)": [], "aliases": []})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["UnknownCorp XYZ"])
    assert result == []


def test_extract_deduplicates_tickers():
    """Same ticker from multiple org names appears once."""
    conn = make_pg_conn({"lower(company_name)": [("AAPL",), ("AAPL",)]})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["Apple Inc", "Apple Incorporated"])
    assert result.count("AAPL") == 1


def test_extract_multiple_tickers():
    """Two different org names return two tickers."""
    conn = make_pg_conn({"lower(company_name)": [("AAPL",), ("MSFT",)]})
    extractor = TickerExtractor(conn)
    result = extractor.extract(["Apple Inc", "Microsoft Corporation"])
    assert "AAPL" in result
    assert "MSFT" in result


def test_normalize_strips_inc():
    assert TickerExtractor.normalize("Apple Inc") == "apple"


def test_normalize_strips_corporation():
    assert TickerExtractor.normalize("Microsoft Corporation") == "microsoft"


def test_normalize_strips_trailing_dot():
    assert TickerExtractor.normalize("Apple Inc.") == "apple"


def test_normalize_case_insensitive():
    assert TickerExtractor.normalize("APPLE INC") == "apple"


def test_normalize_preserves_ampersand_words():
    assert "johnson" in TickerExtractor.normalize("Johnson & Johnson")


def test_normalize_strips_ltd():
    assert TickerExtractor.normalize("Some Company Ltd") == "some company"


def test_normalize_empty_string():
    assert TickerExtractor.normalize("") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/connectors/test_ticker_extractor.py -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'src.connectors.ticker_extractor'`

- [ ] **Step 3: Implement `src/connectors/ticker_extractor.py`**

```python
"""Maps GDELT organisation names to ticker symbols via PostgreSQL lookup."""

import re

_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|corporation|corp|limited|ltd|llc|company|co|plc|"
    r"group|holdings|international|intl|s\.?p\.?a|n\.?v|b\.?v)\b\.?",
    re.IGNORECASE,
)


class TickerExtractor:
    """Maps a list of GDELT organisation names to ticker symbols.

    Primary lookup: normalised company_name match (case-insensitive, suffix-stripped).
    Fallback lookup: alias array match for historical name variants.
    No match → empty list → article is discarded by caller.
    """

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def extract(self, org_names: list[str]) -> list[str]:
        """Return deduplicated list of tickers for the given org names."""
        if not org_names:
            return []

        normalized = list({self.normalize(n) for n in org_names if self.normalize(n)})
        if not normalized:
            return []

        tickers: list[str] = []
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ticker FROM ticker_lookup WHERE lower(company_name) = ANY(%s)",
                (normalized,),
            )
            tickers.extend(row[0] for row in cur.fetchall())

            original_stripped = [n.strip() for n in org_names if n.strip()]
            if original_stripped:
                cur.execute(
                    "SELECT DISTINCT ticker FROM ticker_lookup WHERE aliases && %s::text[]",
                    (original_stripped,),
                )
                for row in cur.fetchall():
                    if row[0] not in tickers:
                        tickers.append(row[0])

        return list(dict.fromkeys(tickers))

    @staticmethod
    def normalize(name: str) -> str:
        """Lowercase, strip corporate suffixes and punctuation."""
        cleaned = _SUFFIX_RE.sub("", name.strip())
        cleaned = re.sub(r"[,.]", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip().lower()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/connectors/test_ticker_extractor.py -v
```

Expected: all 12 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/connectors/ticker_extractor.py tests/connectors/test_ticker_extractor.py
git commit -m "feat: add TickerExtractor with normalize and PG lookup"
```

---

## Task 8: NewsIngestionWorker

**Files:**
- Create: `src/workers/ingestion.py`
- Create: `tests/workers/test_ingestion_worker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/workers/test_ingestion_worker.py`:

```python
"""Tests for NewsIngestionWorker."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.news import GKGNewsItem, NewsItem


def make_gkg_item(url: str, org_names: list[str], title: str = "Tech news") -> GKGNewsItem:
    return GKGNewsItem(
        id=url,
        source="gdelt_gkg",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=title,
        url=url,
        language="en",
        asset_tags=[],
        org_names=org_names,
    )


@pytest.mark.asyncio
async def test_ingestion_worker_queues_item_with_ticker():
    """Article with known org name queues one NewsItem with ticker."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/1", ["Apple Inc"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL"]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["discarded"] == 0
    assert mock_redis.rpush.call_count == 1
    pushed_data = json.loads(mock_redis.rpush.call_args[0][1])
    assert pushed_data["asset_tags"] == ["AAPL"]
    assert pushed_data["id"] == "https://example.com/1:AAPL"


@pytest.mark.asyncio
async def test_ingestion_worker_discards_no_ticker():
    """Article with no known org name is discarded."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/2", ["Unknown Corp XYZ"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = []
    mock_dedup = MagicMock()
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["discarded"] == 1
    assert stats["queued"] == 0
    mock_redis.rpush.assert_not_called()


def test_ingestion_worker_multi_ticker_article():
    """Article mentioning two orgs creates two separate NewsItems."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [make_gkg_item("https://example.com/3", ["Apple Inc", "Microsoft Corporation"])]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL", "MSFT"]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["tickers_found"] == 2
    assert stats["queued"] == 2
    assert mock_redis.rpush.call_count == 2
    ids = [json.loads(c[0][1])["id"] for c in mock_redis.rpush.call_args_list]
    assert "https://example.com/3:AAPL" in ids
    assert "https://example.com/3:MSFT" in ids


def test_ingestion_worker_dedup_blocks_second():
    """Duplicate (url, ticker) combination is not queued twice."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [
        make_gkg_item("https://example.com/4", ["Apple Inc"]),
        make_gkg_item("https://example.com/4", ["Apple Inc"]),
    ]
    mock_extractor = MagicMock()
    mock_extractor.extract.return_value = ["AAPL"]

    call_count = {"n": 0}

    def dedup_side_effect(item):
        call_count["n"] += 1
        return call_count["n"] > 1  # first is False, subsequent True

    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.side_effect = dedup_side_effect
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["queued"] == 1
    assert stats["duplicates"] == 1


def test_ingestion_worker_returns_correct_stats():
    """Stats dict contains all expected keys with correct values."""
    from src.workers.ingestion import _process_gkg_items

    gkg_items = [
        make_gkg_item("https://a.com/1", ["Apple Inc"]),
        make_gkg_item("https://a.com/2", []),
    ]
    mock_extractor = MagicMock()
    mock_extractor.extract.side_effect = [["AAPL"], []]
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_redis = MagicMock()

    stats = _process_gkg_items(gkg_items, mock_extractor, mock_dedup, mock_redis)

    assert stats["fetched"] == 2
    assert stats["tickers_found"] == 1
    assert stats["discarded"] == 1
    assert stats["queued"] == 1
    assert stats["duplicates"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/workers/test_ingestion_worker.py -v
```

Expected: `FAILED` with `ModuleNotFoundError: No module named 'src.workers.ingestion'`

- [ ] **Step 3: Implement `src/workers/ingestion.py`**

```python
"""NewsIngestionWorker — fetches broad financial news, extracts tickers, enqueues."""

import asyncio
import logging

import psycopg2
from redis import Redis

from src.config import config
from src.connectors.deduplicator import Deduplicator
from src.connectors.gdelt_gkg import GDELTGKGConnector
from src.connectors.ticker_extractor import TickerExtractor
from src.models.news import GKGNewsItem, NewsItem
from src.workers.celery_app import app

log = logging.getLogger(__name__)


async def _fetch_gkg_items(connector: GDELTGKGConnector) -> list[GKGNewsItem]:
    return [item async for item in connector.fetch()]


def _process_gkg_items(
    gkg_items: list[GKGNewsItem],
    extractor: TickerExtractor,
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Extract tickers, deduplicate, and push annotated NewsItems to news:queue.

    Returns a stats dict with keys: fetched, tickers_found, discarded, queued, duplicates.
    """
    stats = {"fetched": 0, "tickers_found": 0, "discarded": 0, "queued": 0, "duplicates": 0}

    for gkg_item in gkg_items:
        stats["fetched"] += 1
        tickers = extractor.extract(gkg_item.org_names)
        if not tickers:
            stats["discarded"] += 1
            continue

        stats["tickers_found"] += len(tickers)
        for ticker in tickers:
            item = NewsItem(
                id=f"{gkg_item.url}:{ticker}",
                source=gkg_item.source,
                timestamp=gkg_item.timestamp,
                title=gkg_item.title,
                body=gkg_item.body,
                url=gkg_item.url,
                language=gkg_item.language,
                asset_tags=[ticker],
            )
            if deduplicator.is_duplicate_by_id(item):
                stats["duplicates"] += 1
                continue
            redis_client.rpush("news:queue", item.model_dump_json())
            stats["queued"] += 1

    return stats


@app.task(name="src.workers.ingestion.run_news_ingestion_worker")
def run_news_ingestion_worker() -> dict:
    """Celery entry-point for NewsIngestionWorker.

    Fetches broad financial news from GDELT GKG, extracts tickers via
    PostgreSQL lookup, deduplicates by (url, ticker), and pushes annotated
    NewsItems to news:queue for the SentimentWorker to consume.
    """
    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)

    try:
        connector = GDELTGKGConnector()
        extractor = TickerExtractor(pg_conn)
        deduplicator = Deduplicator(redis_client)

        gkg_items = asyncio.run(_fetch_gkg_items(connector))
        stats = _process_gkg_items(gkg_items, extractor, deduplicator, redis_client)

        log.info("Ingestion stats: %s", stats)
        return stats

    finally:
        pg_conn.close()
        redis_client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/workers/test_ingestion_worker.py -v
```

Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/workers/ingestion.py tests/workers/test_ingestion_worker.py
git commit -m "feat: add NewsIngestionWorker Celery task"
```

---

## Task 9: Wire up — celery_app.py + performance.py fix

**Files:**
- Modify: `src/workers/celery_app.py`
- Modify: `src/workers/performance.py`

- [ ] **Step 1: Add ingestion beat schedule to `src/workers/celery_app.py`**

Add after the `regime-detector` entry (before the closing `}`):

```python
    # News ingestion every 15 min Mon-Fri during market hours — feeds news:queue
    "run-news-ingestion": {
        "task": "src.workers.ingestion.run_news_ingestion_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
```

- [ ] **Step 2: Fix hardcoded symbols in `src/workers/performance.py`**

Find and replace lines 78-79:

Old:
```python
    symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "SPY", "QQQ"]
    all_rows = []
```

New:
```python
    symbols = config.WATCHLIST_SYMBOLS
    all_rows = []
```

Verify that `config` is already imported at the top of `performance.py` (it is — line 39: `from src.config import config`).

- [ ] **Step 3: Write test for performance.py fix**

Add to `tests/workers/test_performance_worker.py` (append to existing file):

```python
def test_fetch_all_signals_uses_watchlist_symbols():
    """_fetch_all_signals_for_ic uses config.WATCHLIST_SYMBOLS, not hardcoded list."""
    from src.workers.performance import _fetch_all_signals_for_ic
    from src.config import config

    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_ic.return_value = []

    _fetch_all_signals_for_ic(mock_pg, days=30)

    called_symbols = [call[0][0] for call in mock_pg.fetch_signals_for_ic.call_args_list]
    for symbol in config.WATCHLIST_SYMBOLS:
        assert symbol in called_symbols
```

- [ ] **Step 4: Run the new test**

```bash
pytest tests/workers/test_performance_worker.py::test_fetch_all_signals_uses_watchlist_symbols -v
```

Expected: `PASSED`

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
pytest --tb=short -q
```

Expected: all tests pass (433 existing + new tests added in this plan)

- [ ] **Step 6: Commit**

```bash
git add src/workers/celery_app.py src/workers/performance.py tests/workers/test_performance_worker.py
git commit -m "feat: wire ingestion worker to Celery beat and fix hardcoded symbols"
```

---

## Self-Review Checklist

- [x] DB migration creates `ticker_lookup` with correct indexes — Task 1
- [x] Seed CSV + script populate the table — Task 2
- [x] `GKGNewsItem` model defined — Task 3
- [x] `is_duplicate_by_id` handles multi-ticker dedup — Task 3
- [x] `WATCHLIST_SYMBOLS` in config, overridable — Task 4
- [x] `_GDELTBaseConnector` shared backoff, `GDELTConnector` unchanged externally — Task 5
- [x] `GDELTGKGConnector` parses V2Organizations, date, PageTitle; skips missing URL/bad date — Task 6
- [x] `TickerExtractor` normalizes suffixes, exact+alias match, deduplicates tickers — Task 7
- [x] `NewsIngestionWorker` multi-ticker expansion, discard-on-no-ticker, stats — Task 8
- [x] Beat schedule added for ingestion — Task 9
- [x] `performance.py` hardcoded symbols removed — Task 9
- [x] All tasks have real code (no placeholders)
- [x] Type names consistent: `GKGNewsItem`, `TickerExtractor`, `_process_gkg_items`, `is_duplicate_by_id`
