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

    stable = "|".join(
        _normalise_text(row.get(key)) for key in ("source", "ticker", "published_at")
    )
    return f"unknown:{_digest(stable)}"


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def classify_timing(
    published_at: datetime | str | None,
    session_open: datetime,
    session_close: datetime,
) -> str:
    """Classifica il momento dell'articolo rispetto alla seduta target."""
    published = _as_datetime(published_at)
    if published is None:
        return "UNKNOWN"
    try:
        if published < session_open:
            return "ANTICIPATORY"
        if published <= session_close:
            return "CONCURRENT"
    except TypeError:
        # Timestamp naive contro bound timezone-aware (o viceversa): il dato non
        # e' confrontabile senza inventare un fuso.
        return "UNKNOWN"
    return "RETROSPECTIVE"


def _contains_term(text: str, term: str) -> bool:
    normalised = _normalise_text(term)
    if not normalised:
        return False
    pattern = rf"(?<![\w]){re.escape(normalised)}(?![\w])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _classify_relevance(row: dict, fanout_degree: int) -> tuple[str, str | None]:
    ticker = str(row.get("ticker") or "").strip().upper()
    gt_relevance = str(row.get("ground_truth_relevance") or "").strip().casefold()
    gt_tickers = {
        str(value).strip().upper() for value in (row.get("ground_truth_tickers") or [])
        if str(value).strip()
    }
    if gt_relevance == "company_specific":
        if ticker and ticker in gt_tickers:
            return "ISSUER_SPECIFIC", ticker
        return "FALSE_ENTITY_MATCH", None
    if gt_relevance in {"sector", "macro"}:
        return "SECTOR_MACRO", None
    if gt_relevance == "irrelevant":
        if fanout_degree >= 2:
            return "IRRELEVANT_FANOUT", None
        return "FALSE_ENTITY_MATCH", None
    if gt_relevance:
        return "UNKNOWN", None

    text = _normalise_text(f"{row.get('title') or ''} {row.get('body_snippet') or ''}")
    issuer_terms = list(row.get("issuer_terms") or [])
    if ticker:
        issuer_terms.append(ticker)
    if any(_contains_term(text, term) for term in issuer_terms):
        return "ISSUER_SPECIFIC", ticker or None

    # org_lookup conserva per intero il testo scorato (title == body): l'assenza
    # di ticker/ragione sociale e' quindi decidibile, come nel seam #244. Sugli
    # snippet source_metadata e su gdelt_doc (query per nome societario) sarebbe
    # invece un salto inferenziale: resta UNKNOWN.
    if str(row.get("extraction_method") or "").strip() == "org_lookup" and text:
        return "FALSE_ENTITY_MATCH", None
    return "UNKNOWN", None


def _strongest(scores: Iterable[float]) -> float | None:
    values = list(scores)
    if not values:
        return None
    # Preserva il segno: ``max`` qui significa massima forza |score|. In caso
    # di parita' il valore numericamente maggiore rende l'esito deterministico.
    return max(values, key=lambda value: (abs(value), value))


def _concentration(counts: dict[str, int]) -> dict:
    positive = {key: value for key, value in sorted(counts.items()) if value > 0}
    total = sum(positive.values())
    if total == 0:
        return {"top_5_share": None, "hhi": None, "conteggi": {}}
    shares = [value / total for value in positive.values()]
    return {
        "top_5_share": sum(sorted(shares, reverse=True)[:5]),
        "hhi": sum(share * share for share in shares),
        "conteggi": positive,
    }


def _primary_row(rows: list[dict]) -> dict:
    def key(row: dict) -> tuple:
        seen = _as_datetime(row.get("first_seen_at"))
        return (
            seen is None,
            seen.isoformat() if seen is not None else "",
            str(row.get("source") or ""),
            str(row.get("news_log_id") or ""),
        )

    return min(rows, key=key)


def _known_relevance(values: Iterable[str]) -> str:
    known = set(values)
    # Una prova positiva issuer-specific prevale su mapping meno informativi
    # della stessa coppia canonica/ticker. Gli altri bucket sono mutuamente
    # esclusivi quando arrivano da ground truth; l'ordine risolve solo dati
    # storici discordanti in modo stabile.
    for category in RELEVANCE_CATEGORIES:
        if category in known:
            return category
    return "UNKNOWN"


def build_article_coverage(
    rows: list[dict],
    *,
    universe: list[str],
    sector_by_ticker: dict[str, str],
    session_open: datetime,
    session_close: datetime,
) -> dict:
    """Deduplica articoli e produce copertura/attribution senza doppio conteggio."""
    prepared: list[dict] = []
    by_canonical: dict[str, list[dict]] = defaultdict(list)
    for original in rows:
        row = dict(original)
        row["ticker"] = str(row.get("ticker") or "").strip().upper()
        row["canonical_article_id"] = canonical_article_id(row)
        by_canonical[row["canonical_article_id"]].append(row)
        prepared.append(row)

    for canonical_rows in by_canonical.values():
        tickers = {row["ticker"] for row in canonical_rows if row["ticker"]}
        for row in canonical_rows:
            relevance, subject = _classify_relevance(row, len(tickers))
            row["relevance"] = relevance
            row["subject_ticker"] = subject
            row["timing"] = classify_timing(
                row.get("published_at"), session_open, session_close
            )
            row["fanout_degree"] = len(tickers)

    by_mapping: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in prepared:
        by_mapping[(row["canonical_article_id"], row["ticker"])].append(row)

    mappings: dict[tuple[str, str], dict] = {}
    for key, mapping_rows in by_mapping.items():
        relevance = _known_relevance(row["relevance"] for row in mapping_rows)
        published = [
            value for value in (_as_datetime(row.get("published_at")) for row in mapping_rows)
            if value is not None
        ]
        timing = classify_timing(min(published), session_open, session_close) if published else "UNKNOWN"
        ticker = key[1]
        mappings[key] = {
            "canonical_article_id": key[0],
            "ticker": ticker,
            "relevance": relevance,
            "subject_ticker": ticker if relevance == "ISSUER_SPECIFIC" else None,
            "timing": timing,
            "effective_timely": relevance == "ISSUER_SPECIFIC" and timing in TIMELY,
        }

    primary_by_canonical = {
        canonical: _primary_row(canonical_rows)
        for canonical, canonical_rows in by_canonical.items()
    }

    signals: list[dict] = []
    seen_signal_ids: set[object] = set()
    for row in prepared:
        signal_id = row.get("signal_id")
        if signal_id is None or signal_id in seen_signal_ids:
            continue
        seen_signal_ids.add(signal_id)
        mapping = mappings[(row["canonical_article_id"], row["ticker"])]
        if mapping["relevance"] == "ISSUER_SPECIFIC":
            attribution = "ISSUER_SPECIFIC"
        elif row["fanout_degree"] >= 2:
            attribution = "FANOUT"
        else:
            attribution = "UNKNOWN"
        signals.append({
            "signal_id": signal_id,
            "news_log_id": row.get("news_log_id"),
            "canonical_article_id": row["canonical_article_id"],
            "source": row.get("source") or "UNKNOWN",
            "ticker": row["ticker"],
            "subject_ticker": mapping["subject_ticker"],
            "relevance": mapping["relevance"],
            "timing": row["timing"],
            "attribution": attribution,
            "score": row.get("score"),
        })
    signals.sort(key=lambda item: str(item["signal_id"]))

    per_ticker: dict[str, dict] = {}
    for ticker in sorted(set(universe) | {key[1] for key in mappings if key[1]}):
        ticker_mappings = [value for key, value in mappings.items() if key[1] == ticker]
        own_scores = [
            float(signal["score"]) for signal in signals
            if signal["ticker"] == ticker
            and signal["attribution"] == "ISSUER_SPECIFIC"
            and signal.get("score") is not None
        ]
        fanout_scores = [
            float(signal["score"]) for signal in signals
            if signal["ticker"] == ticker
            and signal["attribution"] == "FANOUT"
            and signal.get("score") is not None
        ]
        counts = Counter(mapping["relevance"] for mapping in ticker_mappings)
        per_ticker[ticker] = {
            "settore": sector_by_ticker.get(ticker, "UNKNOWN"),
            "articoli_unici": len(ticker_mappings),
            "rilevanza": {category: counts.get(category, 0) for category in RELEVANCE_CATEGORIES},
            "effective_timely_articles": sum(
                bool(mapping["effective_timely"]) for mapping in ticker_mappings
            ),
            "max_score_own": _strongest(own_scores),
            "max_score_fanout": _strongest(fanout_scores),
        }

    sectors = sorted(set(sector_by_ticker.get(ticker, "UNKNOWN") for ticker in universe))
    per_sector: dict[str, dict] = {}
    for sector in sectors:
        members = {ticker for ticker in universe if sector_by_ticker.get(ticker, "UNKNOWN") == sector}
        covered = {ticker for ticker in members if per_ticker[ticker]["effective_timely_articles"] > 0}
        canonical = {
            key[0] for key, mapping in mappings.items()
            if key[1] in members and mapping["effective_timely"]
        }
        per_sector[sector] = {
            "ticker_universo": len(members),
            "ticker_coperti": len(covered),
            "quota": len(covered) / len(members) if members else None,
            "articoli_effective_timely": len(canonical),
        }

    effective_canonical = {
        key[0] for key, mapping in mappings.items() if mapping["effective_timely"]
    }
    per_source_counts: Counter[str] = Counter()
    per_source_effective: Counter[str] = Counter()
    for canonical, primary in primary_by_canonical.items():
        source = str(primary.get("source") or "UNKNOWN")
        per_source_counts[source] += 1
        if canonical in effective_canonical:
            per_source_effective[source] += 1
    per_source = {
        source: {
            "articoli_unici": per_source_counts[source],
            "articoli_effective_timely": per_source_effective[source],
        }
        for source in sorted(per_source_counts)
    }

    ticker_effective = {
        ticker: metrics["effective_timely_articles"]
        for ticker, metrics in per_ticker.items()
        if metrics["effective_timely_articles"] > 0
    }
    sector_effective = {
        sector: metrics["articoli_effective_timely"]
        for sector, metrics in per_sector.items()
        if metrics["articoli_effective_timely"] > 0
    }
    source_effective = {
        source: metrics["articoli_effective_timely"]
        for source, metrics in per_source.items()
        if metrics["articoli_effective_timely"] > 0
    }

    unique_news_ids = {
        row.get("news_log_id") for row in prepared if row.get("news_log_id") is not None
    }
    syndication_duplicates = sum(
        max(0, len({row.get("news_log_id") for row in mapping_rows}) - 1)
        for mapping_rows in by_mapping.values()
    )
    relevance_counts = Counter(mapping["relevance"] for mapping in mappings.values())
    covered_tickers = sum(
        per_ticker.get(ticker, {}).get("effective_timely_articles", 0) > 0
        for ticker in universe
    )

    articles = []
    for canonical, canonical_rows in sorted(by_canonical.items()):
        primary = primary_by_canonical[canonical]
        article_mappings = [mapping for key, mapping in mappings.items() if key[0] == canonical]
        articles.append({
            "canonical_article_id": canonical,
            "source": primary.get("source") or "UNKNOWN",
            "sources": sorted({str(row.get("source") or "UNKNOWN") for row in canonical_rows}),
            "tickers": sorted({mapping["ticker"] for mapping in article_mappings if mapping["ticker"]}),
            "subject_tickers": sorted({
                mapping["subject_ticker"] for mapping in article_mappings
                if mapping["subject_ticker"]
            }),
            "relevance_by_ticker": {
                mapping["ticker"]: mapping["relevance"] for mapping in article_mappings
                if mapping["ticker"]
            },
            "timing": classify_timing(primary.get("published_at"), session_open, session_close),
        })

    return {
        "definizione_effective_timely": (
            "ISSUER_SPECIFIC e timing ANTICIPATORY|CONCURRENT; deduplica per "
            "canonical_article_id"
        ),
        "totali": {
            "righe_news_log": len(unique_news_ids),
            "articoli_unici": len(by_canonical),
            "duplicati_syndication_per_ticker": syndication_duplicates,
            "mapping_fanout_extra": max(0, len(mappings) - len(by_canonical)),
            "mapping_rilevanza": {
                category: relevance_counts.get(category, 0)
                for category in RELEVANCE_CATEGORIES
            },
            "articoli_effective_timely": len(effective_canonical),
        },
        "effective_timely_coverage": {
            "ticker_coperti": covered_tickers,
            "ticker_universo": len(universe),
            "quota": covered_tickers / len(universe) if universe else None,
        },
        "per_ticker": per_ticker,
        "per_settore": per_sector,
        "per_fonte": per_source,
        "concentrazione": {
            "ticker": _concentration(ticker_effective),
            "settore": _concentration(sector_effective),
            "fonte": _concentration(source_effective),
        },
        "articoli": articles,
        "segnali": signals,
    }
