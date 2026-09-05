"""Detector deterministico per headline di secondo ordine/spillover (#408).

La classificazione e' volutamente precision-biased: un testo persistito viene
marcato solo se nomina l'emittente taggato prima di un connettore causale esplicito e,
dopo quel connettore, nomina una societa' diversa presente in ``ticker_lookup``.
L'assenza di match significa soltanto "non classificata", mai "notizia diretta".

Il detector non usa ``llm_responses.directness``: quel campo e' l'autovalutazione
del modello che questa misura deve poter controllare indipendentemente.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

CAUSAL_CONNECTORS = (
    "following",
    "after",
    "on the back of",
    "amid",
    "on news of",
    "thanks to",
    "as a result of",
)

_LEGAL_SUFFIX = re.compile(
    r"(?:[\s,.]+(?:incorporated|inc|corporation|corp|company|co|limited|ltd|plc|nv|as))\.?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompanyIdentity:
    ticker: str
    company_name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecondOrderMatch:
    category: str
    connector: str
    third_party_ticker: str
    third_party_company: str


def _normalise(value: object) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _short_company_name(value: str) -> str:
    """Rimuove soltanto suffissi societari terminali.

    ``ticker_lookup`` contiene per esempio ``Adobe Inc`` e ``NVIDIA
    Corporation``, mentre le headline usano quasi sempre ``Adobe`` e
    ``NVIDIA``. La riduzione e' stretta e terminale: non inventa sigle o nomi.
    """
    current = _normalise(value)
    while current:
        shortened = _LEGAL_SUFFIX.sub("", current).strip(" ,.")
        if shortened == current:
            return current
        current = shortened
    return ""


def _identity_terms(company: CompanyIdentity) -> tuple[str, ...]:
    terms: set[str] = set()
    for raw in (company.company_name, *company.aliases):
        normalised = _normalise(raw)
        shortened = _short_company_name(raw)
        if len(normalised) >= 2:
            terms.add(normalised)
        if len(shortened) >= 2:
            terms.add(shortened)
    return tuple(sorted(terms, key=lambda value: (-len(value), value)))


def _term_pattern(term: str) -> re.Pattern[str]:
    pieces = [re.escape(piece) for piece in term.split()]
    body = r"\s+".join(pieces)
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


_CONNECTOR_PATTERNS = {
    connector: _term_pattern(connector) for connector in CAUSAL_CONNECTORS
}


class SecondOrderDetector:
    """Indice immutabile di ``ticker_lookup`` riusabile su molte headline."""

    def __init__(self, companies: Iterable[CompanyIdentity]):
        by_ticker: dict[str, list[CompanyIdentity]] = {}
        for company in companies:
            ticker = str(company.ticker or "").strip().upper()
            if not ticker or not company.company_name:
                continue
            normalised = CompanyIdentity(
                ticker=ticker,
                company_name=str(company.company_name).strip(),
                aliases=tuple(str(alias).strip() for alias in company.aliases if str(alias).strip()),
            )
            by_ticker.setdefault(ticker, []).append(normalised)
        self._by_ticker = by_ticker

        third_party_terms: list[tuple[re.Pattern[str], CompanyIdentity, str]] = []
        for ticker in sorted(by_ticker):
            for company in by_ticker[ticker]:
                for term in _identity_terms(company):
                    third_party_terms.append((_term_pattern(term), company, term))
        self._third_party_terms = tuple(third_party_terms)

    @property
    def known_tickers(self) -> frozenset[str]:
        return frozenset(self._by_ticker)

    def _mentions_self(self, ticker: str, title: str) -> bool:
        identities = self._by_ticker.get(ticker, [])
        terms = {
            term
            for company in identities
            for term in _identity_terms(company)
        }
        terms.add(_normalise(ticker))
        terms.add(f"${_normalise(ticker)}")
        return any(_term_pattern(term).search(title) for term in terms if term)

    def _connectors(self, title: str) -> list[tuple[int, int, str]]:
        matches: list[tuple[int, int, str]] = []
        for connector, pattern in _CONNECTOR_PATTERNS.items():
            for match in pattern.finditer(title):
                matches.append((match.start(), match.end(), connector))
        return sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2]))

    def _third_party_after(
        self, ticker: str, suffix: str
    ) -> CompanyIdentity | None:
        candidates: list[tuple[int, int, str, CompanyIdentity]] = []
        for pattern, company, term in self._third_party_terms:
            if company.ticker == ticker:
                continue
            match = pattern.search(suffix)
            if match is not None:
                candidates.append((match.start(), -len(term), company.ticker, company))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[:3])[3]

    def classify(self, ticker: str, text: str) -> SecondOrderMatch | None:
        ticker = str(ticker or "").strip().upper()
        normalised_text = _normalise(text)
        if ticker not in self._by_ticker or not normalised_text:
            return None
        for start, end, connector in self._connectors(normalised_text):
            if not self._mentions_self(ticker, normalised_text[:start]):
                continue
            third_party = self._third_party_after(ticker, normalised_text[end:])
            if third_party is not None:
                return SecondOrderMatch(
                    category="second_order",
                    connector=connector,
                    third_party_ticker=third_party.ticker,
                    third_party_company=third_party.company_name,
                )
        return None
