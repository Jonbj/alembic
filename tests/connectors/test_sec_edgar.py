"""SEC EDGAR Latest Filings connector tests."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.connectors.sec_edgar import SECEdgarConnector

# Entry captured from the official Latest Filings Atom feed on 2026-09-05.
_LIVE_8K_ATOM = b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings - Sat, 05 Sep 2026 15:02:08 EDT</title>
<entry>
<title>8-K - PDS Biotechnology Corp (0001472091) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1472091/000114036126035809/0001140361-26-035809-index.htm"/>
<summary type="html">
 &lt;b&gt;Filed:&lt;/b&gt; 2026-09-04 &lt;b&gt;AccNo:&lt;/b&gt; 0001140361-26-035809 &lt;b&gt;Size:&lt;/b&gt; 199 KB
&lt;br&gt;Item 1.01: Entry into a Material Definitive Agreement
</summary>
<updated>2026-09-04T17:25:28-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0001140361-26-035809</id>
</entry>
</feed>
"""

_EMPTY_ATOM = b"""<?xml version="1.0" encoding="ISO-8859-1" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Latest Filings</title>
</feed>
"""


def _response(payload: bytes):
    response = MagicMock()
    response.status = 200
    response.read = AsyncMock(return_value=payload)
    response.raise_for_status = MagicMock()
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


def test_fetch_uses_latest_filings_and_maps_cik_from_real_payload():
    company_tickers = MagicMock()
    company_tickers.tickers_for_cik.return_value = ["PDSB"]
    requests = []

    def get(url, *, params, headers):
        requests.append((url, params, headers))
        payload = _LIVE_8K_ATOM if params["type"] == "8-K" else _EMPTY_ATOM
        return _response(payload)

    session = AsyncMock()
    session.get = get
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    connector = SECEdgarConnector(
        company_tickers=company_tickers,
        user_agent="Alembic test ops@example.com",
    )

    async def fetch_all():
        return [item async for item in connector.fetch()]

    with patch("src.connectors.sec_edgar.aiohttp.ClientSession", return_value=session):
        items = asyncio.run(fetch_all())

    assert len(items) == 1
    assert items[0].id == "0001140361-26-035809"
    assert items[0].asset_tags == ["PDSB"]
    assert items[0].extraction_method == "source_metadata"
    assert items[0].source == "sec_edgar"
    assert items[0].timestamp.isoformat() == "2026-09-04T17:25:28-04:00"
    assert "Item 1.01: Entry into a Material Definitive Agreement" in items[0].body
    assert items[0].url.endswith("0001140361-26-035809-index.htm")

    assert [params["type"] for _, params, _ in requests] == ["8-K", "6-K"]
    assert all("CIK" not in params and "company" not in params for _, params, _ in requests)
    assert all(headers["User-Agent"] == "Alembic test ops@example.com" for _, _, headers in requests)
    company_tickers.tickers_for_cik.assert_called_once_with("0001472091")


def test_defaults_are_limited_to_material_current_reports():
    connector = SECEdgarConnector(company_tickers=MagicMock(), user_agent="ua")
    assert connector.form_types == ["8-K", "6-K"]
