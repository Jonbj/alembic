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


# ---------------------------------------------------------------------------
# fetch()        (Task 3 — leave empty for now)
# fetch_historical() (Task 4 — leave empty for now)
# ---------------------------------------------------------------------------
