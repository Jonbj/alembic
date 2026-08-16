#!/usr/bin/env python3
"""QX-01 inter-annotator agreement harness (#54).

Misura l'accordo fra i 2 annotatori del golden label set (news_labels) e
gestisce il workflow di adjudication della specifica
(docs/TICKER_SENTIMENT_QUALITY_REVIEW_2026-06-30.md §5.5):

  - Cohen's kappa sulla direzione (positive/negative/neutral), target >= 0.7;
  - Cohen's kappa sul ticker (presenza/assenza di ogni ticker dell'universo,
    metrica standard per annotazioni set-valued), target >= 0.6;
  - worklist dei disaccordi (direzione diversa o insiemi di ticker non
    coincidenti) per l'adjudicator;
  - `--adjudicate <news_log_id> <adjudicator_id>` marca la coppia come risolta
    (adjudicated=true, adjudicator_id) dopo la decisione del terzo annotatore.
    La coppia marcata esce dal dataset: non rientra nel calcolo del kappa
    ne' nella worklist del run successivo (la decisione dell'adjudicator
    chiude il disaccordo).

Le metriche sono calcolate sugli articoli con esattamente 2 righe labeled
(2 annotatori); i due slot sono ordinati per annotator_id (deterministico).
Offline / read-only tranne il modo --adjudicate. Run nel container worker:

    docker compose exec worker python scripts/inter_annotator_agreement.py
    docker compose exec worker python scripts/inter_annotator_agreement.py \\
        --adjudicate 12345 adjudicator_b
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import psycopg2
import psycopg2.extras

DIRECTIONS = ("positive", "negative", "neutral")
DIR_TARGET = 0.70     # kappa >= 0.7 (substantial) per direction
TICKER_TARGET = 0.60  # kappa >= 0.6 (substantial) per ticker

# Categorie della relazione simmetrica fra i due insiemi di ticker (worklist).
_TICKER_CATS = ("match", "overlap", "disjoint", "both_empty")


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


# --------------------------------------------------------------------- pura

def cohens_kappa(a: list, b: list, categories) -> float | None:
    """Cohen's kappa fra due annotatori sulle stesse n unita'.

    categories e' l'universo delle etichette (per il calcolo del pe atteso,
    incluse classi che non co-occorrono). Ritorna None se n=0 o se non c'e'
    varianza (pe=1, kappa indefinito)."""
    n = len(a)
    if n == 0 or len(a) != len(b):
        return None
    ma = defaultdict(int)
    mb = defaultdict(int)
    for x, y in zip(a, b):
        ma[x] += 1
        mb[y] += 1
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((ma[c] / n) * (mb[c] / n) for c in categories)
    if abs(1.0 - pe) < 1e-12:
        return None
    return (po - pe) / (1.0 - pe)


def ticker_category(set_a: frozenset, set_b: frozenset) -> str:
    """Relazione simmetrica fra i due insiemi di ticker (per la worklist)."""
    if not set_a and not set_b:
        return "both_empty"
    if set_a == set_b:
        return "match"
    if set_a & set_b:
        return "overlap"
    return "disjoint"


def ticker_kappa(sets_a: list, sets_b: list) -> float | None:
    """Cohen's kappa sul ticker: presenza/assenza di ogni ticker dell'universo.

    Universo = tutti i ticker visti da almeno un annotatore. Per ogni
    (item, ticker) un'unita' binaria (1=presente, 0=assente) per ciascun
    annotatore; kappa su queste unita'. E' la metrica standard per annotazioni
    set-valued (l'unione per-item renderebbe l'assenza non informativa)."""
    if not sets_a or len(sets_a) != len(sets_b):
        return None
    universe = sorted(set().union(*sets_a, *sets_b))
    if not universe:
        return None  # nessun ticker da nessuna parte → niente da misurare
    a_labels, b_labels = [], []
    for sa, sb in zip(sets_a, sets_b):
        for t in universe:
            a_labels.append(1 if t in sa else 0)
            b_labels.append(1 if t in sb else 0)
    return cohens_kappa(a_labels, b_labels, (0, 1))


def disagreements(items: list[dict]) -> list[dict]:
    """Articoli in disaccordo: direzione diversa o ticker non coincidenti.

    Ogni item ha: news_log_id, dir (tuple 2), tickers (tuple di 2 set).
    "match"/"both_empty" = accordo; "overlap"/"disjoint" = disaccordo."""
    out = []
    for it in items:
        d_a, d_b = it["dir"]
        s_a, s_b = it["tickers"]
        dir_disagree = d_a != d_b
        cat = ticker_category(frozenset(s_a), frozenset(s_b))
        ticker_disagree = cat in ("overlap", "disjoint")
        if dir_disagree or ticker_disagree:
            out.append({"news_log_id": it["news_log_id"], "source": it.get("source"),
                        "dir": it["dir"], "ticker_cat": cat})
    return out


# --------------------------------------------------------------------- I/O

def _load_pairs(conn) -> dict[str, list[dict]]:
    """Articoli con esattamente 2 annotatori labeled, per source.

    Esclude le coppie gia' adjudicated: dopo che l'adjudicator ha risolto un
    disaccordo, il dato non entra piu' nel calcolo del kappa ne' nella worklist
    (altrimenti il report riproporrebbe lo stesso articolo all'infinito).

    Ritorna {source: [item, ...]} dove item = {news_log_id, source, dir,
    tickers} con i due slot ordinati per annotator_id (deterministico)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT news_log_id, source, annotator_id, gt_tickers,
                      gt_sentiment_dir
                 FROM news_labels
                WHERE status = 'labeled'
                  AND news_log_id IS NOT NULL
                  AND gt_sentiment_dir IS NOT NULL
                  AND (adjudicated IS FALSE OR adjudicated IS NULL)"""
        )
        rows = cur.fetchall()
    by_article: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_article[r["news_log_id"]].append(r)

    by_source: dict[str, list[dict]] = defaultdict(list)
    for nid, rows2 in by_article.items():
        if len(rows2) != 2:           # solo le coppie 2-annotator
            continue
        rows2.sort(key=lambda r: r["annotator_id"] or "")
        by_source[rows2[0]["source"]].append({
            "news_log_id": nid,
            "source": rows2[0]["source"],
            "dir": (rows2[0]["gt_sentiment_dir"], rows2[1]["gt_sentiment_dir"]),
            "tickers": (set(rows2[0]["gt_tickers"] or []),
                        set(rows2[1]["gt_tickers"] or [])),
        })
    return by_source


def _report(by_source: dict[str, list[dict]]) -> int:
    """Stampa kappa per direction/ticker (overall + per source) e la worklist."""
    all_items = [it for items in by_source.values() for it in items]
    if not all_items:
        print("Nessuna coppia 2-annotator labeled ancora. Annota due annotatori"
              " per articolo ( campagne #30).")
        return 0

    def kappas(items):
        dirs = list(zip(*[it["dir"] for it in items]))
        tks = list(zip(*[it["tickers"] for it in items]))
        return (cohens_kappa(dirs[0], dirs[1], DIRECTIONS),
                ticker_kappa(tks[0], tks[1]))

    def fmt(k):
        return f"{k:.3f}" if k is not None else "  -  "

    print(f"# Inter-annotator agreement — {len(all_items)} coppie 2-annotator\n")
    print(f"{'source':16} {'n':>4} {'k_dir':>7} {'k_tick':>7}   "
          f"{'dir>=0.7':>7} {'tick>=0.6':>9}")
    overall_dir, overall_tk = kappas(all_items)
    rows = [("ALL", len(all_items), overall_dir, overall_tk)]
    for src in sorted(by_source):
        kd, kt = kappas(by_source[src])
        rows.append((src, len(by_source[src]), kd, kt))
    for name, n, kd, kt in rows:
        ok_d = "OK" if kd is not None and kd >= DIR_TARGET else "no"
        ok_t = "OK" if kt is not None and kt >= TICKER_TARGET else "no"
        print(f"{name:16} {n:>4} {fmt(kd):>7} {fmt(kt):>7}   {ok_d:>7} {ok_t:>9}")

    print(f"\nTarget: kappa direction >= {DIR_TARGET} (substantial), "
          f"ticker >= {TICKER_TARGET}.")
    print("Sotto soglia → rifinire la rubric prima di continuare (spec §5.5).")

    dis = disagreements(all_items)
    print(f"\n# Adjudication worklist — {len(dis)} disaccordi")
    for d in dis:
        print(f"  news_log_id={d['news_log_id']:>6}  source={d['source']:<14}  "
              f"dir={d['dir']}  ticker={d['ticker_cat']}")
    if dis:
        print("\nRisolvi con: python scripts/inter_annotator_agreement.py "
              "--adjudicate <news_log_id> <adjudicator_id>")
    return 0


def _adjudicate(news_log_id: int, adjudicator_id: str) -> int:
    """Marca la coppia di righe di un articolo come risolta dall'adjudicator."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE news_labels
                      SET adjudicated = true, adjudicator_id = %s
                    WHERE news_log_id = %s AND status = 'labeled'""",
                (adjudicator_id, news_log_id),
            )
            n = cur.rowcount
        conn.commit()
    print(f"Adjudication registrata: news_log_id={news_log_id}, "
          f"adjudicator_id={adjudicator_id}, righe marcate={n}.")
    if n == 0:
        print("  (nessuna riga labeled per questo news_log_id)")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--adjudicate"]:
        if len(argv) != 3:
            print("uso: inter_annotator_agreement.py --adjudicate <news_log_id> "
                  "<adjudicator_id>")
            return 2
        return _adjudicate(int(argv[1]), argv[2])
    with _conn() as conn:
        by_source = _load_pairs(conn)
    return _report(by_source)


if __name__ == "__main__":
    raise SystemExit(main())