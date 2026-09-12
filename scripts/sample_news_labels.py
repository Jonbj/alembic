#!/usr/bin/env python3
"""Sample the QX-01 golden label set into news_labels (offline, deterministic).

Two modes:

* no flags — historical behaviour: 400 DISTINCT articles (by url) from the whole
  news_log, 180 alpaca_benzinga / 150 gdelt_gkg / 70 marketaux (spec §5.9 Fase 1),
  stratified by source only.
* ``--da`` / ``--a`` — temporal window on ``published_at`` (inclusive bounds;
  ``--a`` covers the whole day indicated). Stratified per
  ``(source, extraction_method)`` with explicit targets (_TARGETS_POST_QT03),
  designed for the post-QT-03 population (`--da 2026-06-30`). A branch that
  stays under target is reported loudly (exit code 1), never silently filled
  from another branch. Within the existing near-zero quota, known
  ``CONTENT_EMPTY`` title templates are selected first (#508), so they reach
  QX-01 without changing the sample size or its declared near-zero fraction.

Collinearity caveat (premise of the #405 measurement, not a downstream
discovery): in the post-QT-03 population ``extraction_method`` is nearly
perfectly collinear with ``source`` (org_lookup ↔ gdelt_gkg, source_metadata ↔
alpaca_benzinga/marketaux). A source_metadata vs org_lookup comparison is
therefore inseparably a Benzinga vs GDELT comparison: an error-rate gap cannot
be attributed to the *mechanism* (unvalidated provider tags) rather than the
*provider*. The sampler prints this note on every windowed run.

Deterministic (fixed seed) and idempotent (guard NOT EXISTS on news_log_id)
in both modes. Each row carries news_log_id + fetched_at denormalized (schema
2-annotator, migrazione 046) and status='pending' with the system's extracted
tickers for later precision/recall.

Run inside the worker container (reaches postgres):
    docker compose exec worker python scripts/sample_news_labels.py
    docker compose exec worker python scripts/sample_news_labels.py --da 2026-06-30
"""
from __future__ import annotations

import argparse
import datetime
import os
import random
import sys

import psycopg2
import psycopg2.extras

from src.analysis.dossier.article_coverage import content_empty_title_reason

_SEED = 42
# Per-source targets (sum 400 — spec §5.9 Fase 1). gdelt has headline-only bodies
# → text_adequacy hint. 180/150/70 = alpaca_benzinga / gdelt_gkg / marketaux.
_TARGETS = {"alpaca_benzinga": 180, "gdelt_gkg": 150, "marketaux": 70}
# Target della finestra post-QT-03, stratificati per (source, extraction_method).
# Popolazione verificata sul DB live 2026-09-01 (#461): gdelt_gkg/org_lookup 3.299,
# alpaca_benzinga/source_metadata 1.756, marketaux/source_metadata 5, cnbc/regex 1.
# Ricalibrazione rispetto a 180/150/70:
#   - marketaux: 5 articoli disponibili contro il target storico di 70 → si prende
#     l'intera popolazione, non si puo' pretendere di piu';
#   - alpaca_benzinga resta a 180 (valore storico): e' il ramo principale che #405
#     deve misurare (tag del provider non validati);
#   - gdelt_gkg assorbe il residuo (215) per tenere il totale a 400 (spec §5.9)
#     e entrambi i rami del confronto source_metadata vs org_lookup sopra 180.
_TARGETS_POST_QT03 = {
    ("alpaca_benzinga", "source_metadata"): 180,
    ("gdelt_gkg", "org_lookup"): 215,
    ("marketaux", "source_metadata"): 5,
}
_NEAR_ZERO_FRACTION = 0.40   # oversample |raw_sentiment| < 0.05 (failure mode F2)
_NEAR_ZERO_THRESHOLD = 0.05

# Premessa della misura #405, stampata a ogni run con finestra (vedi docstring).
_COLLINEARITY_NOTE = (
    "NOTE collinearity: extraction_method is nearly perfectly collinear with source\n"
    "in the post-QT-03 population (org_lookup=gdelt_gkg,\n"
    "source_metadata=alpaca_benzinga/marketaux): a method comparison is inseparably\n"
    "a provider comparison — an error-rate gap cannot be attributed to the mechanism\n"
    "rather than the provider. Premise for #405, not a downstream discovery."
)


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


def _fetch_articles(cur, source: str,
                    da: datetime.date | None = None,
                    a: datetime.date | None = None) -> list[dict]:
    """Distinct articles for a source, with aggregated tickers and |raw_sentiment|.

    news_log ha una riga per (url, ticker): per articolo si prende un news_log_id
    rappresentativo (MAX(id)) piu' fetched_at, mantenuti denormalizzati su ogni
    riga di news_labels (lo schema 2-annotator keya su news_log_id). Il metodo
    e' quello della riga rappresentativa (id piu' alto), coerente col news_log_id
    che finisce sulla label. ``da`` e' inclusivo; ``a`` copre l'intera giornata
    indicata (bound = giorno successivo)."""
    where = ["source = %s", "url <> ''"]
    params: list = [source]
    if da is not None:
        where.append("published_at >= %s")
        params.append(da)
    if a is not None:
        where.append("published_at < %s")
        params.append(a + datetime.timedelta(days=1))
    cur.execute(
        f"""
        SELECT MAX(id)                        AS news_log_id,
               url,
               MAX(title)                     AS title,
               MAX(body_snippet)              AS body_snippet,
               MAX(published_at)              AS published_at,
               MAX(fetched_at)                AS fetched_at,
               array_agg(DISTINCT ticker)     AS tickers,
               (array_agg(extraction_method ORDER BY id DESC))[1] AS extraction_method,
               MAX(ABS(COALESCE(raw_sentiment,0))) AS abs_sent
        FROM news_log
        WHERE {' AND '.join(where)}
        GROUP BY url
        """,
        params,
    )
    return [dict(r) for r in cur.fetchall()]


def _fetch_sources(cur, da: datetime.date | None,
                   a: datetime.date | None) -> list[str]:
    """Tutte le fonti presenti nella finestra, incluse quelle senza target."""
    where = ["url <> ''"]
    params: list = []
    if da is not None:
        where.append("published_at >= %s")
        params.append(da)
    if a is not None:
        where.append("published_at < %s")
        params.append(a + datetime.timedelta(days=1))
    cur.execute(
        f"""SELECT DISTINCT source
              FROM news_log
             WHERE {' AND '.join(where)}
             ORDER BY source""",
        params,
    )
    return [row["source"] for row in cur.fetchall()]


def _pick(
    articles: list[dict],
    n: int,
    rng: random.Random,
    *,
    content_empty_stratum: bool = False,
) -> list[dict]:
    """Pick n articles, oversampling near-zero sentiment, deterministically.

    Nei run post-QT-03 la quota near-zero gia' pre-registrata viene riempita
    prima con i template CONTENT_EMPTY della #508. Cosi' il golden set li vede
    senza introdurre un nuovo target o cambiare la numerosita' del campione.
    """
    near = [a for a in articles if a["abs_sent"] < _NEAR_ZERO_THRESHOLD]
    rest = [a for a in articles if a["abs_sent"] >= _NEAR_ZERO_THRESHOLD]
    if content_empty_stratum:
        content_empty = [a for a in near if content_empty_title_reason(a.get("title"))]
        other_near = [a for a in near if not content_empty_title_reason(a.get("title"))]
        rng.shuffle(content_empty)
        rng.shuffle(other_near)
        near = content_empty + other_near
    else:
        rng.shuffle(near)
    rng.shuffle(rest)
    n_near = min(len(near), int(round(n * _NEAR_ZERO_FRACTION)))
    picked = near[:n_near] + rest[: n - n_near]
    # top up from whatever remains if a bucket was short
    if len(picked) < n:
        remaining = (near[n_near:] + rest[n - n_near:])
        picked += remaining[: n - len(picked)]
    return picked[:n]


def _insert_labels(cur, source: str, articles: list[dict]) -> int:
    """Insert one pending row per article (idempotent on news_log_id). 0 se vuoto."""
    if not articles:
        return 0
    adequacy = "headline_only" if source == "gdelt_gkg" else "full"
    inserted = 0
    for a in articles:
        # Idempotenza su news_log_id: una pending row per articolo.
        # (ON CONFLICT (url) non e' piu' valido dopo la 046; annotator_id
        # e' NULL sulle pending — il vincolo UNIQUE(news_log_id, annotator_id)
        # tratta i NULL come distinti, quindi serve il guard NOT EXISTS.)
        cur.execute(
            """
            INSERT INTO news_labels
                (news_log_id, url, source, title, body_snippet,
                 published_at, fetched_at, extracted_tickers,
                 text_adequacy, status)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending'
            WHERE NOT EXISTS (
                SELECT 1 FROM news_labels WHERE news_log_id = %s
            )
            """,
            (a["news_log_id"], a["url"], source, a["title"],
             a["body_snippet"], a["published_at"], a["fetched_at"],
             a["tickers"], adequacy, a["news_log_id"]),
        )
        inserted += cur.rowcount
    return inserted


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Campiona il golden set QX-01 in news_labels (deterministico, idempotente).")
    p.add_argument("--da", type=datetime.date.fromisoformat, metavar="YYYY-MM-DD",
                   help="finestra: solo articoli con published_at >= questa data "
                        "(per QX-01 post-QT-03: --da 2026-06-30)")
    p.add_argument("--a", type=datetime.date.fromisoformat, metavar="YYYY-MM-DD",
                   help="finestra: solo articoli pubblicati entro questa data "
                        "(giornata intera, bound inclusivo)")
    return p.parse_args(argv if argv is not None else sys.argv[1:])


def _sample_legacy(cur, rng: random.Random) -> int:
    """Modalita' storica: nessuna finestra, stratificazione per sola source."""
    inserted = 0
    for source, target in _TARGETS.items():
        articles = _fetch_articles(cur, source)
        picked = _pick(articles, target, rng)
        inserted += _insert_labels(cur, source, picked)
        print(f"{source}: {len(articles)} available → picked {len(picked)}")
    return inserted


def _sample_window(cur, rng: random.Random,
                   da: datetime.date | None, a: datetime.date | None) -> tuple[int, list[str]]:
    """Modalita' con finestra: stratificazione per (source, extraction_method).

    Ritorna (righe inserite, messaggi dei rami sotto target): il riempimento
    silenzioso fra rami non esiste, un ramo corto resta corto e viene dichiarato."""
    if da:
        print(f"Window: published_at >= {da.isoformat()}" +
              (f" AND published_at < {(a + datetime.timedelta(days=1)).isoformat()}" if a else ""))
    elif a:
        print(f"Window: published_at < {(a + datetime.timedelta(days=1)).isoformat()}")
    print(_COLLINEARITY_NOTE)

    # Articoli per strato (source, extraction_method): metodo NULL = pre-QT-03.
    available: dict[tuple[str, str | None], list[dict]] = {}
    for source in _fetch_sources(cur, da, a):
        for art in _fetch_articles(cur, source, da, a):
            available.setdefault((source, art["extraction_method"]), []).append(art)
    for key in sorted(set(available) - set(_TARGETS_POST_QT03), key=repr):
        print(f"{key[0]}/{key[1]}: {len(available[key])} available — "
              f"excluded (no target for this stratum)")

    inserted = 0
    shortfalls = []
    for (source, method), target in _TARGETS_POST_QT03.items():
        arts = available.get((source, method), [])
        picked = _pick(arts, target, rng, content_empty_stratum=True)
        inserted += _insert_labels(cur, source, picked)
        line = f"{source}/{method}: {len(arts)} available → picked {len(picked)} / target {target}"
        content_empty_picked = sum(
            content_empty_title_reason(article.get("title")) is not None
            for article in picked
        )
        line += f" (CONTENT_EMPTY stratum: {content_empty_picked})"
        if len(picked) < target:
            line += "  — UNDER TARGET: not filled from other branches"
            shortfalls.append(f"{source}/{method}: picked {len(picked)} of {target}")
        print(line)
    return inserted, shortfalls


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    rng = random.Random(_SEED)
    # NB: `with conn` in psycopg2 gestisce la transazione, NON chiude la
    # connessione — serve la chiusura esplicita, altrimenti resta aperta fino
    # al GC (blocca ad es. il DROP DATABASE del test a valle).
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if args.da or args.a:
                inserted, shortfalls = _sample_window(cur, rng, args.da, args.a)
            else:
                inserted, shortfalls = _sample_legacy(cur, rng), []
        conn.commit()
    finally:
        conn.close()
    print(f"Inserted {inserted} new label rows (pending).")
    if shortfalls:
        print("\nComposition check FAILED: " + "; ".join(shortfalls))
        print("Sample committed (idempotent), but it does not meet the declared targets.")
        sys.exit(1)


if __name__ == "__main__":
    main()
