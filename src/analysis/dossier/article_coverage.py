"""Copertura articolo-centrica e attribution dei segnali (#279).

``news_log`` persiste una riga per (URL, ticker), non una riga per articolo.
Contare quelle righe sovrastima sia la copertura (syndication cross-source) sia
la rilevanza (fan-out dello stesso testo su piu' ticker). Questo modulo e' puro:
riceve le righe gia' lette dal dossier, costruisce un'identita' canonica
riproducibile e separa misura da comportamento live.

``effective_timely`` significa, per definizione versionabile e verificabile:
articolo ``ISSUER_SPECIFIC`` pubblicato prima della chiusura della seduta target
(``ANTICIPATORY`` o ``CONCURRENT``), esclusi i template ``CONTENT_EMPTY``.
Il confronto ``including_content_empty`` conserva in parallelo la definizione
precedente, cosi' la discontinuita' della misura resta quantificabile. Un dato
insufficiente resta ``UNKNOWN``; non viene promosso a copertura effettiva per
colmare un buco informativo.

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

# #566 — Suffissi corporate riconosciuti per derivare il bare stem
# (es. "Oracle Corporation" -> "Oracle"). La lista e' congelata: aggiungere
# un suffisso e' una scelta di copertura, non un default. Casi ambigui
# (nomi corti, collisioni lessicali) sono esclusi e richiedono review umana.
#
# L'ordine conta: la funzione applica la sostituzione greedy ricorsiva per
# ogni suffisso; l'ordine delle tuple non influenza il risultato perche'
# ciascun suffisso si applica una sola volta al nome gia' strippato.
_BARE_STEM_SUFFIXES: tuple[str, ...] = (
    # Suffissi lunghi che inglobano quelli corti (es. "Holdings NV" -> "")
    "Corporation",
    "Incorporated",
    "International",
    "Holdings",
    "Holding",
    "Company",
    "Limited",
    "Group",
    "Bancorp",
    "Financial",
    "Industries",
    "Resources",
    "Technologies",
    "Solutions",
    "Networks",
    "Pharmaceuticals",
    "Therapeutics",
    "Laboratories",
    "Communications",
    "Enterprises",
    "Services",
    "Capital",
    "Partners",
    "Management",
    # Connettivi tipici dei nomi corporate ("Eli Lilly and Company")
    "and",
    "and Company",
    "&",
    # Suffissi brevi, applicati per ultimi
    "AG",
    "SE",
    "SA",
    "S.A.",
    "AB",
    "AS",
    "A/S",
    "PLC",
    "plc",
    "NV",
    "N.V.",
    "Corp",
    "Inc",
    "Co",
)
# Token finali di suffisso, separati da spazio, gestiti come singola parola.
# Usato per casi tipo "AstraZeneca plc", "SAP SE", "Arm Holdings plc".
_BARE_STEM_TRAILING_TOKENS: tuple[str, ...] = (
    "plc",
    "PLC",
    "NV",
    "AG",
    "SE",
    "SA",
)

_HEX_64 = re.compile(r"^[0-9a-fA-F]{64}$")
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid"}
_CONTENT_EMPTY_TITLE_PATTERNS = (
    (
        "EVERGREEN_RETURN_TEMPLATE",
        re.compile(
            r"^(?:if you invested \$[\d,.]+ in|"
            r"(?:here(?:'|’)s how much )?\$[\d,.]+ invested in)"
            r".*\b\d+\s+years?\s+ago\b",
            re.IGNORECASE,
        ),
    ),
    ("WHALE_ACTIVITY_TEMPLATE", re.compile(r"\bwhale activity\b", re.IGNORECASE)),
    (
        "RATINGS_LISTICLE_TEMPLATE",
        re.compile(
            r"\bhere (?:are|is) (?:the )?top \d+ (?:upgrades|downgrades)\b",
            re.IGNORECASE,
        ),
    ),
)


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


# #566 — Stem/alias derivation per il buco di copertura della tabella
# ``ticker_lookup``. Il matcher word-boundary richiede che il nome usato dal
# giornalista ("Apple", "Oracle") sia presente negli alias; i CSV originali
# hanno solo nomi legali ("Apple Inc", "Oracle Corporation"). Aggiungere il
# bare stem in automatico e' deterministico ma va filtrato da una lista di
# collisioni lessicali e da una soglia di lunghezza — la funzione pura
# ``derive_bare_stem`` restituisce sempre lo stem dove possibile; la funzione
# ``propose_stem_backfill`` aggiunge i bucket (safe/short/collision/noop) per
# la revisione umana, separando la correzione automatica da quella manuale.

# Token lessicali che collidono con l'inglese comune o sono troppo generici
# per essere usati come match word-boundary in un titolo finanziario. La lista
# e' il vincolo del ticker-resolution design (CLAUDE.md § Ticker Resolution):
# "ambiguita' risolta deterministicamente, mai indovinando". Anche una collisione
# totale abbassa l'evidenza del match sotto il rumore del lessico.
_STEM_COLLISIONS: frozenset[str] = frozenset({
    "A", "I", "Is", "It", "Be", "We", "He", "On", "To", "Go", "So",
    "And", "The", "For", "One", "All", "Any", "Now", "New", "Old",
    "Best", "More", "Most", "Less", "Last", "Next", "First",
    "Home", "Work", "Bank", "Capital", "Group", "Holdings", "Limited",
    "Real", "True", "Open", "Full", "Big", "Top",
    "Apple",  # frutto + azienda
    "Amazon",  # fiume + azienda
    "Shell",  # conchiglia + azienda
    "Cisco",  # nome proprio spagnolo
    "Palo",  # palo (legno) + Palo Alto
})


def derive_bare_stem(company_name: object) -> str | None:
    """Strip dei suffissi corporate noti da un nome legale.

    Restituisce lo stem se la rimozione ha ridotto la stringa ed e' rimasto
    almeno un token significativo; ``None`` altrimenti. La funzione e'
    case-preserving sul resto (il match avviene case-insensitive sul testo
    normalizzato, vedi ``_contains_term``) e non altera l'ordine dei token
    superstiti.

    La lista di suffissi e' congelata perche' aggiungerne uno cambia il
    contratto: un suffisso troppo generico (es. "Bank") produce collisioni
    lessicali che riaprono il buco dei falsi positivi che #405 chiude.
    """
    text = _normalise_text(company_name)
    if not text:
        return None
    candidate = text
    # Strip ricorsivo: ogni suffisso, finche' qualcosa si stacca. Ciascun
    # suffisso si applica una sola volta perche' il testo post-strip non
    # contiene piu' quel suffisso (almeno in coda).
    changed = True
    while changed:
        changed = False
        for suffix in _BARE_STEM_SUFFIXES:
            token = _normalise_text(suffix)
            if not token:
                continue
            if candidate.endswith(" " + token) or candidate == token:
                stripped = candidate[: -len(token)].rstrip(" ,.&")
                if stripped and stripped != candidate:
                    candidate = stripped
                    changed = True
                    break
    candidate = candidate.strip(" ,.&")
    if not candidate or candidate == text:
        return None
    return candidate


def expand_aliases_with_stem(
    company_name: object, aliases: Iterable[object]
) -> list[str]:
    """Aggiunge il bare stem agli alias se assente, senza duplicati.

    La funzione e' deterministica e idempotente: eseguita due volte produce
    lo stesso output. Non altera l'ordine degli alias esistenti (lo stem
    viene accodato). Se lo stem coincide con il ``company_name`` o con un
    alias gia' presente, non viene aggiunto: il check usa la forma
    case-fold di entrambi i lati, perche' gli alias di produzione mescolano
    "Apple Computer" e "apple computer" senza convenzione.
    """
    base = [str(alias).strip() for alias in aliases if str(alias or "").strip()]
    stem = derive_bare_stem(company_name)
    if not stem:
        return base
    seen = {_normalise_text(company_name)}
    seen.update(_normalise_text(alias) for alias in base)
    if _normalise_text(stem) in seen:
        return base
    return [*base, stem]


# #566 — Backfill proposal: bucket per la review umana.
#
# La proposta separa quattro bucket:
#   - ``safe``:    stem applicabile in automatico. Criteri: stem non vuoto,
#                  non collidente col lessico, ticker >= 3 caratteri.
#                  Candidati all'applicazione automatica.
#   - ``short``:   ticker da 1-2 caratteri (es. "F", "T", "V", "GE"). Lo
#                  stem di per se' puo' essere lungo, ma il ticker corto
#                  segnala che la riga ha bisogno di conferma umana: uno
#                  stem word-boundary "Ford Motor" su F potrebbe matchare
#                  articoli su qualsiasi Ford. La issue lo cita esplicitamente.
#   - ``collision``: lo stem collide con un token lessicale comune.
#                  Da NON aggiungere in automatico (riapre il buco dei
#                  falsi positivi che #405 chiude). Da valutare caso per
#                  caso se il dominio e' abbastanza specifico.
#   - ``noop``:    stem identico a un alias o al company_name, niente da fare.
_STEM_SHORT_THRESHOLD = 3
_SHORT_TICKER_THRESHOLD = 2


def propose_stem_backfill(
    rows: Iterable[dict],
    *,
    short_threshold: int = _STEM_SHORT_THRESHOLD,
    short_ticker_threshold: int = _SHORT_TICKER_THRESHOLD,
    collisions: Iterable[str] = _STEM_COLLISIONS,
) -> list[dict]:
    """Restituisce una proposta di backfill, una entry per riga input.

    Ogni entry ha: ``ticker``, ``company_name``, ``current_aliases``,
    ``proposed_alias``, ``bucket`` e ``reason``. La proposta e' il dato
    di review: l'operatore decide bucket-per-bucket cosa applicare.
    La funzione non scrive nulla e non richiede il DB.
    """
    collision_set = frozenset(_normalise_text(c) for c in collisions)
    out: list[dict] = []
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        company = str(row.get("company_name") or "")
        aliases_raw = row.get("aliases") or []
        if isinstance(aliases_raw, str):
            aliases = [aliases_raw]
        else:
            aliases = list(aliases_raw)
        stem = derive_bare_stem(company)
        if stem is None:
            out.append({
                "ticker": ticker,
                "company_name": company,
                "current_aliases": aliases,
                "proposed_alias": None,
                "bucket": "noop",
                "reason": "no_suffix_detected",
            })
            continue
        # Identico al company_name o gia' presente: niente da fare
        stem_norm = _normalise_text(stem)
        company_norm = _normalise_text(company)
        aliases_norm = {_normalise_text(a) for a in aliases if str(a or "").strip()}
        if stem_norm == company_norm or stem_norm in aliases_norm:
            out.append({
                "ticker": ticker,
                "company_name": company,
                "current_aliases": aliases,
                "proposed_alias": None,
                "bucket": "noop",
                "reason": "already_present",
            })
            continue
        if stem_norm in collision_set:
            out.append({
                "ticker": ticker,
                "company_name": company,
                "current_aliases": aliases,
                "proposed_alias": stem,
                "bucket": "collision",
                "reason": f"stem '{stem}' collides with common English token",
            })
            continue
        if (
            len(ticker) <= short_ticker_threshold
            or len(stem_norm) < short_threshold
        ):
            out.append({
                "ticker": ticker,
                "company_name": company,
                "current_aliases": aliases,
                "proposed_alias": stem,
                "bucket": "short",
                "reason": (
                    f"ticker '{ticker}' has <= {short_ticker_threshold} chars"
                    if len(ticker) <= short_ticker_threshold
                    else f"stem '{stem}' shorter than {short_threshold} chars"
                ),
            })
            continue
        out.append({
            "ticker": ticker,
            "company_name": company,
            "current_aliases": aliases,
            "proposed_alias": stem,
            "bucket": "safe",
            "reason": "",
        })
    return out


def content_empty_title_reason(title: object) -> str | None:
    """Riconosce i soli template content-mill pre-registrati dalla #508.

    La funzione e' pubblica perche' il sampler QX-01 deve campionare lo stesso
    identico detector usato dalla misura, senza ricopiarne le regex.
    """
    normalised = _normalise_text(title)
    for reason, pattern in _CONTENT_EMPTY_TITLE_PATTERNS:
        if pattern.search(normalised):
            return reason
    return None


def classify_relevance(row: dict, fanout_degree: int) -> tuple[str, str | None]:
    """Classifica la pertinenza di una mappatura articolo→ticker.

    Il worker di sentiment la riusa sul testo integrale disponibile allo
    scoring (#637); il dossier la applica allo snippet storico. Chi chiama
    dichiara quindi separatamente il proprio ``input_scope`` invece di
    duplicare una regola che divergerebbe nel tempo.
    """
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

    method = str(row.get("extraction_method") or "").strip()
    # org_lookup conserva per intero il testo scorato (title == body): l'assenza
    # di ticker/ragione sociale e' quindi decidibile, come nel seam #244.
    if method == "org_lookup" and text:
        return "FALSE_ENTITY_MATCH", None
    # #405: il percorso source_metadata accetta i tag del provider sulla parola
    # (89% delle righe scorate) e nessuno verifica che l'emittente taggata sia
    # davvero il soggetto del testo — cosi' un articolo su Boston Scientific ha
    # prodotto un -0.5533 su NVO. L'assenza dell'emittente nel testo persistito
    # NON e' FALSE_ENTITY_MATCH: lo snippet e' troncato a 500 caratteri
    # (pg_store, _INSERT_NEWS_LOG), quindi e' un limite inferiore, non una
    # prova. La riga viene marcata TAG_UNCONFIRMED — conteggiata nel
    # mapping_rilevanza per far accumulare il tasso d'errore del percorso, ed
    # esclusa da max_score_own perche' l'attribution non e' ISSUER_SPECIFIC —
    # ma il verdetto deciso resta alle label (QX-01).
    if method == "source_metadata" and text:
        return "TAG_UNCONFIRMED", None
    # gdelt_doc (query per nome societario) e provenienze assenti: un salto
    # inferenziale, resta UNKNOWN.
    return "UNKNOWN", None


def relevance_for_article(
    *,
    symbol: str,
    title: str | None,
    body_snippet: str | None,
    extraction_method: str | None,
    issuer_terms: list[str] | None,
    fanout_degree: int | None,
) -> str:
    """Categoria di pertinenza di un articolo rispetto a ``symbol`` (#596).

    Unico punto usato sia dal path di uscita (portfolio_scheduler) sia dalla
    misura retrospettiva (scripts/measure_596_...): la misura chiama la regola
    di produzione, non la riscrive (#169/#467). Il testo e' titolo + corpo
    persistito, e gli alias dell'emittente vengono da ``ticker_lookup``: senza
    di loro un articolo su "Micron" non verrebbe riconosciuto come MU.
    """
    row = {
        "ticker": symbol,
        "title": title or "",
        "body_snippet": body_snippet or "",
        "extraction_method": extraction_method or "",
        "issuer_terms": list(issuer_terms or []),
    }
    relevance, _ = classify_relevance(row, int(fanout_degree or 1))
    return relevance


def classify_attribution(relevance: str, fanout_degree: int) -> str:
    """Attribuzione osservazionale di uno score, condivisa con il dossier."""
    if relevance == "ISSUER_SPECIFIC":
        return "ISSUER_SPECIFIC"
    if fanout_degree >= 2:
        return "FANOUT"
    return "UNKNOWN"


def _strongest(scores: Iterable[float]) -> float | None:
    values = list(scores)
    if not values:
        return None
    # Preserva il segno: ``max`` qui significa massima forza |score|. In caso
    # di parita' il valore numericamente maggiore rende l'esito deterministico.
    return max(values, key=lambda value: (abs(value), value))


def _fonti_per_ticker(
    ticker_mappings: list[dict],
    primary_by_canonical: dict[str, dict],
) -> dict:
    """Per ticker: conteggio articoli unici per fonte, distinti per effective.

    #511: la copertura del giorno puo' essere zero effective-timely senza che
    il provider sia assente — Alpaca o GDELT possono restituire mapping
    irrilevanti (SECTOR_MACRO, IRRELEVANT_FANOUT, FALSE_ENTITY_MATCH) che non
    producono copertura utile. Distinguere "fonte assente" da "fonte presente
    ma effective=0" e' il dato che serve per prioritizzare i connettori
    non-deployati (#454/#455/#458/#459): se ASML ha solo Alpaca con effective=0
    la diagnosi e' "Alpaca non copre ASML in modo issuer-specific" e va
    colmata con un provider diverso, non con una soglia di ranking.
    """
    counts: dict[str, dict[str, int]] = {}
    for mapping in ticker_mappings:
        primary = primary_by_canonical.get(mapping["canonical_article_id"])
        if primary is None:
            source = "UNKNOWN"
        else:
            source = str(primary.get("source") or "UNKNOWN")
        bucket = counts.setdefault(
            source, {"articoli_unici": 0, "articoli_effective_timely": 0}
        )
        bucket["articoli_unici"] += 1
        if mapping["effective_timely"]:
            bucket["articoli_effective_timely"] += 1
    return {source: counts[source] for source in sorted(counts)}


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


def _content_empty_reason(
    rows: Iterable[dict], relevance: str, timing: str
) -> str | None:
    """Applica il sotto-tag solo dopo aver stabilito ISSUER_SPECIFIC."""
    if relevance != "ISSUER_SPECIFIC":
        return None
    for row in rows:
        reason = content_empty_title_reason(row.get("title"))
        if reason is not None:
            return reason
    if timing == "RETROSPECTIVE":
        return "RETROSPECTIVE_TIMING"
    return None


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
            relevance, subject = classify_relevance(row, len(tickers))
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
        content_empty_reason = _content_empty_reason(mapping_rows, relevance, timing)
        effective_including_content_empty = (
            relevance == "ISSUER_SPECIFIC" and timing in TIMELY
        )
        mappings[key] = {
            "canonical_article_id": key[0],
            "ticker": ticker,
            "relevance": relevance,
            "subject_ticker": ticker if relevance == "ISSUER_SPECIFIC" else None,
            "timing": timing,
            "content_tag": "CONTENT_EMPTY" if content_empty_reason else None,
            "content_empty_reason": content_empty_reason,
            "effective_timely_including_content_empty": effective_including_content_empty,
            "effective_timely": (
                effective_including_content_empty and content_empty_reason is None
            ),
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
        attribution = classify_attribution(
            mapping["relevance"], row["fanout_degree"]
        )
        signals.append({
            "signal_id": signal_id,
            "news_log_id": row.get("news_log_id"),
            "canonical_article_id": row["canonical_article_id"],
            "source": row.get("source") or "UNKNOWN",
            "ticker": row["ticker"],
            "subject_ticker": mapping["subject_ticker"],
            "relevance": mapping["relevance"],
            "timing": row["timing"],
            "content_tag": mapping["content_tag"],
            "content_empty_reason": mapping["content_empty_reason"],
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
        effective_count = sum(
            bool(mapping["effective_timely"]) for mapping in ticker_mappings
        )
        effective_including_content_empty_count = sum(
            bool(mapping["effective_timely_including_content_empty"])
            for mapping in ticker_mappings
        )
        per_ticker[ticker] = {
            "settore": sector_by_ticker.get(ticker, "UNKNOWN"),
            "articoli_unici": len(ticker_mappings),
            "rilevanza": {category: counts.get(category, 0) for category in RELEVANCE_CATEGORIES},
            "effective_timely_articles": effective_count,
            "effective_timely_articles_including_content_empty": (
                effective_including_content_empty_count
            ),
            "quota_effective_timely": (
                effective_count / len(ticker_mappings) if ticker_mappings else None
            ),
            "quota_effective_timely_including_content_empty": (
                effective_including_content_empty_count / len(ticker_mappings)
                if ticker_mappings else None
            ),
            "content_empty_articles": sum(
                mapping["content_tag"] == "CONTENT_EMPTY"
                for mapping in ticker_mappings
            ),
            "max_score_own": _strongest(own_scores),
            "max_score_fanout": _strongest(fanout_scores),
            "fonti_osservate": _fonti_per_ticker(ticker_mappings, primary_by_canonical),
        }

    sectors = sorted(set(sector_by_ticker.get(ticker, "UNKNOWN") for ticker in universe))
    per_sector: dict[str, dict] = {}
    for sector in sectors:
        members = {ticker for ticker in universe if sector_by_ticker.get(ticker, "UNKNOWN") == sector}
        covered = {ticker for ticker in members if per_ticker[ticker]["effective_timely_articles"] > 0}
        covered_including_content_empty = {
            ticker for ticker in members
            if per_ticker[ticker]["effective_timely_articles_including_content_empty"] > 0
        }
        sector_canonical = {
            key[0] for key, mapping in mappings.items()
            if key[1] in members and mapping["effective_timely"]
        }
        sector_canonical_including_content_empty = {
            key[0] for key, mapping in mappings.items()
            if key[1] in members and mapping["effective_timely_including_content_empty"]
        }
        per_sector[sector] = {
            "ticker_universo": len(members),
            "ticker_coperti": len(covered),
            "quota": len(covered) / len(members) if members else None,
            "articoli_effective_timely": len(sector_canonical),
            "ticker_coperti_including_content_empty": len(
                covered_including_content_empty
            ),
            "quota_including_content_empty": (
                len(covered_including_content_empty) / len(members)
                if members else None
            ),
            "articoli_effective_timely_including_content_empty": len(
                sector_canonical_including_content_empty
            ),
        }

    effective_canonical = {
        key[0] for key, mapping in mappings.items() if mapping["effective_timely"]
    }
    effective_canonical_including_content_empty = {
        key[0] for key, mapping in mappings.items()
        if mapping["effective_timely_including_content_empty"]
    }
    per_source_counts: Counter[str] = Counter()
    per_source_effective: Counter[str] = Counter()
    per_source_effective_including_content_empty: Counter[str] = Counter()
    for canonical_id, primary in primary_by_canonical.items():
        source = str(primary.get("source") or "UNKNOWN")
        per_source_counts[source] += 1
        if canonical_id in effective_canonical:
            per_source_effective[source] += 1
        if canonical_id in effective_canonical_including_content_empty:
            per_source_effective_including_content_empty[source] += 1
    per_source = {
        source: {
            "articoli_unici": per_source_counts[source],
            "articoli_effective_timely": per_source_effective[source],
            "quota_effective_timely": (
                per_source_effective[source] / per_source_counts[source]
            ),
            "articoli_effective_timely_including_content_empty": (
                per_source_effective_including_content_empty[source]
            ),
            "quota_effective_timely_including_content_empty": (
                per_source_effective_including_content_empty[source]
                / per_source_counts[source]
            ),
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
        source: int(metrics["articoli_effective_timely"])
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
    covered_tickers_including_content_empty = sum(
        per_ticker.get(ticker, {}).get(
            "effective_timely_articles_including_content_empty", 0
        ) > 0
        for ticker in universe
    )

    articles = []
    for canonical_id, canonical_rows in sorted(by_canonical.items()):
        primary = primary_by_canonical[canonical_id]
        published = [
            value
            for value in (
                _as_datetime(row.get("published_at")) for row in canonical_rows
            )
            if value is not None
        ]
        article_mappings = [
            mapping for key, mapping in mappings.items() if key[0] == canonical_id
        ]
        articles.append({
            "canonical_article_id": canonical_id,
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
            "content_tag_by_ticker": {
                mapping["ticker"]: mapping["content_tag"]
                for mapping in article_mappings if mapping["ticker"]
            },
            "content_empty_reason_by_ticker": {
                mapping["ticker"]: mapping["content_empty_reason"]
                for mapping in article_mappings if mapping["ticker"]
            },
            "timing": (
                classify_timing(min(published), session_open, session_close)
                if published
                else "UNKNOWN"
            ),
        })

    return {
        "definizione_effective_timely": (
            "ISSUER_SPECIFIC, timing ANTICIPATORY|CONCURRENT e non CONTENT_EMPTY; "
            "deduplica per canonical_article_id. Il confronto "
            "including_content_empty conserva la definizione pre-#508"
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
            "mapping_content_empty": sum(
                mapping["content_tag"] == "CONTENT_EMPTY"
                for mapping in mappings.values()
            ),
            "articoli_effective_timely": len(effective_canonical),
            "articoli_effective_timely_including_content_empty": len(
                effective_canonical_including_content_empty
            ),
        },
        "effective_timely_coverage": {
            "ticker_coperti": covered_tickers,
            "ticker_universo": len(universe),
            "quota": covered_tickers / len(universe) if universe else None,
        },
        "effective_timely_coverage_including_content_empty": {
            "ticker_coperti": covered_tickers_including_content_empty,
            "ticker_universo": len(universe),
            "quota": (
                covered_tickers_including_content_empty / len(universe)
                if universe else None
            ),
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
