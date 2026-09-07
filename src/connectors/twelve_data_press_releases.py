"""Twelve Data press_releases connector (PoC shadow, #458).

Free tier: 8 credits/min, 800/day.
License: personal/internal/non-commercial use; agent/LLM use explicitly
promoted by the public terms (https://twelvedata.com/terms).

End-point: GET https://api.twelvedata.com/press_releases?symbol=AAPL&apikey=...
Schema reale verificato il 2026-09-07 (chiave reale): record = `id`,
`datetime` (ISO-Z), `title`, `body` (HTML), `style` (CSS), `language` (list).
Non esistono campi `url` ne' `source` — il dedup si fa su `id`.
"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiohttp

from src.connectors.base import NewsConnector
from src.models.news import NewsItem
from src.text.sanitizer import sanitize_text

logger = logging.getLogger(__name__)

_TWELVE_PR_URL = "https://api.twelvedata.com/press_releases"

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(body: str) -> str:
    """Rimuove tag HTML e collassa gli spazi. Twelve Data serve `body` in HTML grezzo
    con tanto CSS inline (256+ tag per articolo); misurare i `body_chars` cosi' sarebbe
    rumore, non testo utile."""
    if not body:
        return ""
    text = _HTML_TAG_RE.sub(" ", body)
    text = _WS_RE.sub(" ", text)
    return text.strip()


class TwelveDataAuthError(Exception):
    """HTTP 401/403 — chiave Twelve Data mancante o invalida."""


class TwelveDataRateLimitError(Exception):
    """HTTP 429 — esauriti i crediti del piano Basic (8/min)."""


class TwelveDataInvalidSymbolError(Exception):
    """Risposta `status='error'` con codice 404 — simbolo non valido o non coperto."""


class TwelveDataPressReleasesConnector(NewsConnector):
    """Connettore Twelve Data press_releases.

    Un simbolo per chiamata (multi-symbol NON supportato dal fornitore —
    verificato 2026-09-07: `symbol=AAPL,MSFT` ritorna il solo primo).
    Filtraggio temporale via `start_date`/`end_date` (formato YYYY-MM-DD),
    paginazione via `outputsize`/`page`.
    """

    def __init__(
        self,
        api_key: str,
        symbols: list[str] | None = None,
        outputsize: int = 50,
        timeout_s: float = 10.0,
    ):
        self._api_key = api_key
        self._symbols = symbols or []
        # outputsize e' interpretato dal fornitore come per_page; teniamolo conservativo.
        self._outputsize = max(1, min(outputsize, 50))
        self._timeout_s = timeout_s

    def _params_for(self, symbol: str) -> dict[str, str]:
        return {
            "symbol": symbol,
            "apikey": self._api_key,
            "outputsize": str(self._outputsize),
            "page": "1",
        }

    async def fetch(self) -> AsyncIterator[NewsItem]:
        for symbol in self._symbols:
            try:
                async for item in self._fetch_one(symbol):
                    yield item
            except (TwelveDataRateLimitError, TwelveDataAuthError):
                # propaghiamo: lo script PoC (scripts/poc_twelve_data_shadow.py)
                # decide se fare backoff o abortire; per il connettore e'
                # importante che l'errore sia visibile al chiamante e non
                # ingoiato silenziosamente (sennò il caller non sa di essere
                # in rate limit).
                raise
            except TwelveDataInvalidSymbolError:
                # simbolo non valido: log, vai al prossimo (non blocca gli altri)
                logger.warning("Twelve Data invalid symbol %s — skipping", symbol)
                continue

    async def _fetch_one(self, symbol: str) -> AsyncIterator[NewsItem]:
        timeout = aiohttp.ClientTimeout(total=self._timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_TWELVE_PR_URL, params=self._params_for(symbol)) as resp:
                if resp.status == 401 or resp.status == 403:
                    raise TwelveDataAuthError(
                        f"Twelve Data returned {resp.status} — check TWELVE_DATA_API_KEY"
                    )
                if resp.status == 429:
                    raise TwelveDataRateLimitError(
                        f"Twelve Data 429 — credit/min exhausted ({symbol})"
                    )
                if resp.status >= 500:
                    logger.warning("Twelve Data server error %d — skipping %s", resp.status, symbol)
                    return
                try:
                    data = await resp.json()
                except (ValueError, aiohttp.ContentTypeError) as exc:
                    logger.warning("Twelve Data non-JSON response for %s: %s", symbol, exc)
                    return

        # Status nel body (Twelve Data usa HTTP 200 + status='error' per i 404 logici).
        if not isinstance(data, dict) or data.get("status") != "ok":
            code = data.get("code") if isinstance(data, dict) else None
            if code == 404:
                raise TwelveDataInvalidSymbolError(
                    f"Twelve Data: invalid symbol {symbol} (code=404)"
                )
            logger.warning("Twelve Data non-ok status for %s: %s", symbol, data)
            return

        for raw in data.get("press_releases", []) or []:
            item = self._parse(symbol, raw)
            if item is not None:
                yield item

    def _parse(self, symbol: str, raw: dict) -> NewsItem | None:
        ext_id = raw.get("id")
        if not ext_id:
            return None
        title_raw = (raw.get("title") or "").strip()
        body_raw = raw.get("body") or ""
        body_clean = _strip_html(body_raw)
        if not title_raw and not body_clean:
            return None

        try:
            ts = datetime.fromisoformat(raw["datetime"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError):
            ts = datetime.now(timezone.utc)

        # language: Twelve Data ritorna lista, il modello NewsItem si aspetta stringa.
        lang_list = raw.get("language") or []
        language = lang_list[0] if lang_list else ""

        # Sanitize come da CLAUDE.md: titolo e body passano per sanitize_text.
        title = sanitize_text(title_raw)
        body = sanitize_text(body_clean) if body_clean else title

        return NewsItem(
            id=f"td:{ext_id}",
            body=body,
            title=title,
            url="",  # schema reale: nessun campo url
            timestamp=ts,
            source="twelvedata_press_releases",
            asset_tags=[symbol],          # fonte monoticker, tagging by symbol richiesto
            extraction_method="source_metadata",
            language=language,
        )