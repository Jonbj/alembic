"""Copertura articolo-centrica e attribution dei segnali (#279).

``news_log`` persiste una riga per (URL, ticker), non una riga per articolo.
Contare quelle righe sovrastima sia la copertura (syndication cross-source) sia
la rilevanza (fan-out dello stesso testo su piu' ticker). Questo modulo e' puro:
riceve le righe gia' lette dal dossier, costruisce un'identita' canonica
riproducibile e separa misura da comportamento live.

``effective_timely`` significa, per definizione versionabile e verificabile:
articolo ``ISSUER_SPECIFIC`` pubblicato prima della chiusura della seduta target
(``ANTICIPATORY`` o ``CONCURRENT``). Un dato insufficiente resta ``UNKNOWN``;
non viene promosso a copertura effettiva per colmare un buco informativo.

#405: le righe ``source_metadata`` il cui tag del provider non trova riscontro
nel testo persistito sono marcate ``TAG_UNCONFIRMED``. Non e' un verdetto di
falso positivo (lo snippet e' troncato a 500 caratteri: l'assenza e' un limite
inferiore) ma rende accumulabile il tasso d'errore del percorso provider-tagged,
che altrimenti spariva nel recipiente ``UNKNOWN``.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


RELEVANCE_CATEGORIES = (
    "ISSUER_SPECIFIC",
    "SECTOR_MACRO",
    "FALSE_ENTITY_MATCH",
    "IRRELEVANT_FANOUT",
    "TAG_UNCONFIRMED",
    "UNKNOWN",
)
TIMING_CATEGORIES = ("ANTICIPATORY", "CONCURRENT", "RETROSPECTIVE", "UNKNOWN")
TIMELY = frozenset({"ANTICIPATORY", "CONCURRENT"})

_HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}


def _normalise_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(text.split())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalise_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw)
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_QUERY_KEYS
            and not key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
        )
    )
    host = parsed.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), host, path, query, ""))


def canonical_article_id(row: dict) -> str:
    """Identita' stabile dell'articolo, con fallback espliciti.

    Il ``content_hash`` e' la chiave migliore: deriva da titolo+corpo
    normalizzati ed esiste dal funnel EN-05. I dossier storici possono non
    averlo; in quel caso un hash del titolo deduplica la syndication con URL
    differenti. URL normalizzato e ``news_log_id`` sono gli ultimi fallback.
    """
    content_hash = str(row.get("content_hash") or "").strip()
    if _HEX_64.fullmatch(content_hash):
        return f"content:{content_hash.casefold()}"

    title = _normalise_text(row.get("title"))
    if title:
        return f"title:{_digest(title)}"

    url = _normalise_url(row.get("url"))
    if url:
        return f"url:{_digest(url)}"

    news_log_id = row.get("news_log_id")
    if news_log_id is not None:
        return f"news_log:{news_log_id}"

    signal_id = row.get("signal_id")
    if signal_id is not None:
        return f"signal:{signal_id}"

    stable = "|".join(
        _normalise_text(row.get(key)) for key in ("source", "ticker", "published_at")
    )
    return f"unknown:{_digest(stable)}"


def _as_datetime(value: object) -> datetime | None:
    """Converte un valore qualsiasi in datetime, gestendo isoformat e edge cases."""
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        # Fallback for weird legacy formats or non-string inputs
        return None