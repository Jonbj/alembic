"""Tests for TwelveDataPressReleasesConnector (PoC shadow, #458)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.twelve_data_press_releases import (
    TwelveDataPressReleasesConnector,
    TwelveDataAuthError,
    TwelveDataRateLimitError,
    TwelveDataInvalidSymbolError,
)
from src.models.news import NewsItem


async def _drain(conn) -> list:
    out = []
    async for it in conn.fetch():
        out.append(it)
    return out


# --- skeleton ---

def test_connector_instantiates():
    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["AAPL"])
    assert conn is not None


def test_auth_error_is_defined():
    with pytest.raises(TwelveDataAuthError):
        raise TwelveDataAuthError("bad creds")


def test_rate_limit_error_is_defined():
    with pytest.raises(TwelveDataRateLimitError):
        raise TwelveDataRateLimitError("out of credits")


def test_invalid_symbol_error_is_defined():
    with pytest.raises(TwelveDataInvalidSymbolError):
        raise TwelveDataInvalidSymbolError("ZZZZZZZ")


# --- schema reale verificato via Passo 0 (chiave reale, AAPL, 2026-09-07) ---
_FIXTURE_AAPL = {
    "status": "ok",
    "pagination": {"current_page": 1, "per_page": 2},
    "press_releases": [
        {
            "id": "20260528C4858",
            "datetime": "2026-05-28T13:45:00Z",
            "title": "The Rare Earth Race Has a New Front-Runner",
            "body": "<p><b>FN Media Group</b></p><p>NEW YORK, May 28, 2026 /CNW/ -- text</p>",
            "style": ".legendSpanClass { font-weight: bold; }",
            "language": ["en"],
        },
        {
            "id": "20260514GE59609",
            "datetime": "2026-05-14T08:00:00Z",
            "title": "Bayer: Strategische \xad Entscheidung",
            "body": "<p>M\xfcnchen, 14. Mai 2026</p>",
            "style": "",
            "language": ["de"],
        },
    ],
}


def _mock_session_for(payloads: list) -> AsyncMock:
    """Sessione aiohttp mockata che serve `payloads` in sequenza (uno per simbolo)."""
    call = {"i": 0}

    def get_next(url, params=None, **kw):
        idx = min(call["i"], len(payloads) - 1)
        call["i"] += 1
        mock_resp = AsyncMock()
        if isinstance(payloads[idx], Exception):
            mock_resp.status = payloads[idx].status_code if hasattr(payloads[idx], "status_code") else 200
        else:
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=payloads[idx])
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=get_next)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.mark.asyncio
async def test_fetch_symbol_exposes_raw_response_for_the_script():
    """Lo script PoC persiste `raw_response` in news_poc_samples: il connettore
    deve esporre la risposta grezza dell'ultimo simbolo fetchato."""
    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["AAPL"])

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession",
               return_value=_mock_session_for([_FIXTURE_AAPL])):
        items = [item async for item in conn.fetch_symbol("AAPL")]

    assert len(items) == 2
    # last_response e' la risposta completa, non ricostruita
    assert conn.last_response == _FIXTURE_AAPL


@pytest.mark.asyncio
async def test_body_code_429_maps_to_rate_limit_error():
    """Il fornitore puo' servire errori logici con HTTP 200: il code 429 nel body
    va mappato su TwelveDataRateLimitError, non ingoiato come warning."""
    payload = {"code": 429, "status": "error", "message": "9 credits used, current limit 8"}
    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["AAPL"])

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession",
               return_value=_mock_session_for([payload])):
        with pytest.raises(TwelveDataRateLimitError):
            async for _ in conn.fetch_symbol("AAPL"):
                pass


@pytest.mark.asyncio
async def test_fetch_yields_news_items_with_html_stripped_body():
    """Connector produce NewsItem; body ha l'HTML rimosso (altrimenti misura boilerplate)."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=_FIXTURE_AAPL)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["AAPL"])

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch()]

    assert len(items) == 2
    first = items[0]
    assert isinstance(first, NewsItem)
    # id e' il campo id del fornitore (no url nella risposta -> niente fallback).
    assert first.id == "td:20260528C4858"
    # title preservato.
    assert first.title == "The Rare Earth Race Has a New Front-Runner"
    # body senza tag HTML (la fixture contiene <p>, <b>).
    assert "<p>" not in first.body and "<b>" not in first.body
    assert "FN Media Group" in first.body
    # language dal payload.
    assert first.language == "en"
    # asset_tags contiene il simbolo richiesto (source_metadata).
    assert first.asset_tags == ["AAPL"]
    assert first.extraction_method == "source_metadata"
    # timestamp ISO-Z.
    assert first.timestamp == datetime(2026, 5, 28, 13, 45, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fetch_preserves_non_ascii_in_titles_and_body():
    """Le risposte reali contengono caratteri non-ASCII (ß, ä, ‑): devono sopravvivere
    a sanitize_text senza alterare il significato (no omoglifi per semantica)."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=_FIXTURE_AAPL)
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["AAPL"])

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch()]

    de = items[1]
    # ß/ä/ö/ü sopravvivono (sono tedesco, non omoglifi).
    assert "Strategische" in de.title
    assert "M\xfcnchen" in de.body or "München" in de.body


@pytest.mark.asyncio
async def test_fetch_silently_skips_invalid_symbol_but_continues_others():
    """Simbolo invalido non blocca gli altri: la fetch() lo logga e prosegue."""
    err_payload = {
        "code": 404,
        "message": "**symbol** or **figi** parameter is missing or invalid.",
        "status": "error",
    }
    ok_payload = {
        "status": "ok",
        "pagination": {"current_page": 1, "per_page": 1},
        "press_releases": [
            {
                "id": "X",
                "datetime": "2026-05-28T13:45:00Z",
                "title": "ok",
                "body": "<p>body</p>",
                "style": "",
                "language": ["en"],
            }
        ],
    }

    responses = [err_payload, ok_payload]
    session_call = {"i": 0}

    def get_next(url, params=None, **kw):
        idx = session_call["i"]
        session_call["i"] += 1
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=responses[idx])
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    mock_session = AsyncMock()
    mock_session.get = MagicMock(side_effect=get_next)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["ZZZZZZZ", "AAPL"])

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession", return_value=mock_session):
        items = await _drain(conn)

    # Lo script PoC riceve un item valido dal secondo simbolo: niente crash,
    # niente blocco degli altri.
    assert len(items) == 1
    assert items[0].asset_tags == ["AAPL"]


@pytest.mark.asyncio
async def test_fetch_handles_429_with_specific_error():
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["AAPL"])

    async def drain() -> None:
        async for _ in conn.fetch():
            pass

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(TwelveDataRateLimitError):
            await drain()


@pytest.mark.asyncio
async def test_fetch_handles_401_as_auth_error():
    mock_resp = AsyncMock()
    mock_resp.status = 401
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = TwelveDataPressReleasesConnector(api_key="bad", symbols=["AAPL"])

    async def drain() -> None:
        async for _ in conn.fetch():
            pass

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession", return_value=mock_session):
        with pytest.raises(TwelveDataAuthError):
            await drain()


@pytest.mark.asyncio
async def test_fetch_yields_nothing_on_empty_list():
    """simbolo valido senza PR recenti: press_releases=[], non errore."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"status": "ok", "pagination": {"current_page": 1, "per_page": 0}, "press_releases": []})
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["SMALLCAP"])

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession", return_value=mock_session):
        items = [item async for item in conn.fetch()]

    assert items == []


@pytest.mark.asyncio
async def test_fetch_swallows_malformed_json_without_crashing():
    """Risposta non-JSON (pagina HTML di errore): eccezione di parsing gestita, no crash."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(side_effect=ValueError("not json"))
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.get = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    conn = TwelveDataPressReleasesConnector(api_key="key", symbols=["AAPL"])

    with patch("src.connectors.twelve_data_press_releases.aiohttp.ClientSession", return_value=mock_session):
        # yield senza eccezione: l'errore di parsing non deve propagare
        items = [item async for item in conn.fetch()]

    assert items == []