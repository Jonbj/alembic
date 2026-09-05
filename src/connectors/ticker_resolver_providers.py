"""External evidence providers for the deterministic ticker resolver (design §4).

Each provider gathers one kind of evidence — internal alias table, broker tradability,
OpenFIGI, SEC company_tickers — and ``gather_evidence`` assembles them into the
``ResolutionEvidence`` consumed by ``ticker_resolver.resolve()``. All network I/O lives
here (and is cached); the decision logic in ``ticker_resolver`` stays pure.

Every provider is **fail-open**: on any error it returns "no evidence" (False / None),
never a false "confirmed". A transient OpenFIGI/SEC outage therefore lowers a candidate's
resolution_confidence (more conservative), it never fabricates a match.
"""
from __future__ import annotations

import logging
import re

import httpx

from src.connectors.ticker_resolver import ResolutionEvidence

log = logging.getLogger(__name__)

_OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_HTTP_TIMEOUT = 10.0
# OpenFIGI security types we accept as a tradable equity (excludes warrants, rights…).
_EQUITY_TYPES = frozenset({"Common Stock", "ADR", "REIT", "Depositary Receipt"})

_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|corporation|corp|limited|ltd|llc|company|co|plc|"
    r"group|holdings|holding|international|intl)\b",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str:
    """Lowercase, strip corporate suffixes/punctuation — for name equality checks."""
    cleaned = _SUFFIX_RE.sub("", name or "")
    cleaned = re.sub(r"[,.&]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


class OpenFigiClient:
    """Validate a ticker via OpenFIGI ``/v3/mapping`` → FIGI, exchange, security type.

    In-process cache keyed by (ticker, exch). The API key is optional but raises rate
    limits (passed as ``X-OPENFIGI-APIKEY``). Returns None on any error (fail-open).
    """

    def __init__(self, api_key: str = "", timeout: float = _HTTP_TIMEOUT) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._cache: dict[tuple[str, str], dict | None] = {}

    def lookup(self, ticker: str, exch: str = "US") -> dict | None:
        key = (ticker.upper(), exch)
        if key in self._cache:
            return self._cache[key]
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-OPENFIGI-APIKEY"] = self._api_key
        body = [{"idType": "TICKER", "idValue": ticker.upper(), "exchCode": exch}]
        result: dict | None = None
        try:
            resp = httpx.post(_OPENFIGI_URL, headers=headers, json=body, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data and isinstance(data[0], dict) and data[0].get("data"):
                d0 = data[0]["data"][0]
                result = {
                    "figi": d0.get("figi"),
                    "name": d0.get("name"),
                    "exchCode": d0.get("exchCode"),
                    "securityType": d0.get("securityType"),
                }
        except Exception as exc:
            log.warning("OpenFIGI lookup failed for %s: %s", ticker, exc)
        self._cache[key] = result
        return result


class SecCompanyTickers:
    """SEC ``company_tickers.json`` → name↔ticker maps for US issuers (free, no key).

    SEC requires a User-Agent with contact info. Loaded once and cached in-process
    (~10k issuers). Fail-open: on error the maps stay empty (no SEC evidence).
    """

    def __init__(self, user_agent: str, timeout: float = _HTTP_TIMEOUT) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        self._name_to_ticker: dict[str, str] = {}
        self._ticker_to_name: dict[str, str] = {}
        self._cik_to_tickers: dict[str, list[str]] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True  # set first: a failed load must not retry on every news item
        try:
            resp = httpx.get(
                _SEC_TICKERS_URL, headers={"User-Agent": self._user_agent}, timeout=self._timeout
            )
            resp.raise_for_status()
            for row in resp.json().values():
                t = str(row.get("ticker", "")).upper()
                name = _normalize_name(str(row.get("title", "")))
                raw_cik = str(row.get("cik_str", "")).strip()
                if t and name:
                    self._name_to_ticker.setdefault(name, t)
                    self._ticker_to_name.setdefault(t, name)
                if t and raw_cik.isdigit():
                    cik = raw_cik.zfill(10)
                    tickers = self._cik_to_tickers.setdefault(cik, [])
                    if t not in tickers:
                        tickers.append(t)
            log.info("SEC company_tickers loaded: %d issuers", len(self._ticker_to_name))
        except Exception as exc:
            log.warning("SEC company_tickers load failed: %s", exc)

    def ticker_for_name(self, name: str) -> str | None:
        self.load()
        return self._name_to_ticker.get(_normalize_name(name))

    def tickers_for_cik(self, cik: str | int) -> list[str]:
        """Return every listed share class associated with an SEC CIK."""
        self.load()
        raw_cik = str(cik).strip()
        if not raw_cik.isdigit():
            return []
        return sorted(self._cik_to_tickers.get(raw_cik.zfill(10), []))

    def confirms(self, ticker: str, name: str | None = None) -> bool:
        """True if SEC knows this ticker and (if a name is given) it maps to it."""
        self.load()
        t = ticker.upper()
        if t not in self._ticker_to_name:
            return False
        if name:
            return self._name_to_ticker.get(_normalize_name(name)) == t
        return True


def gather_evidence(
    ticker: str,
    *,
    company_name: str | None = None,
    from_reliable_source: bool = False,
    llm_proposed: bool = False,
    alias_tickers: set[str] | None = None,
    tradable_symbols: set[str] | None = None,
    openfigi: OpenFigiClient | None = None,
    sec: SecCompanyTickers | None = None,
) -> ResolutionEvidence:
    """Assemble ``ResolutionEvidence`` for one candidate ticker from the providers.

    Args:
        from_reliable_source: ticker came from a cashtag or broker/MarketAux metadata.
        llm_proposed:         an LLM entity-extraction step proposed this ticker.
        alias_tickers:        tickers the internal ``ticker_lookup`` matched for the name.
        tradable_symbols:     broker-tradable universe; ``None`` → unknown → treated as
                              tradable (fail-open, mirrors _get_fractionable_symbols).
    """
    t = ticker.upper()
    alias = bool(alias_tickers and t in alias_tickers)
    tradable = True if tradable_symbols is None else (t in tradable_symbols)

    sec_match = bool(sec and sec.confirms(t, company_name))
    figi_data = openfigi.lookup(t) if openfigi else None
    figi_ok = bool(figi_data and (figi_data.get("securityType") in _EQUITY_TYPES))
    sec_openfigi = sec_match or figi_ok

    return ResolutionEvidence(
        ticker=t,
        source_ticker_match=from_reliable_source,
        alias_match=alias,
        sec_openfigi_match=sec_openfigi,
        llm_agreement=llm_proposed,
        tradable=tradable,
        exchange=(figi_data or {}).get("exchCode"),
        figi=(figi_data or {}).get("figi"),
    )
