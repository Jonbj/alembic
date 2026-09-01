#!/usr/bin/env python3
"""QX-01 validation harness — measure extraction (and later sentiment) quality.

Reads the golden label set (news_labels) and computes, per source and overall:
  - ticker extraction precision / recall / FP-rate / FN-rate (extracted_tickers vs
    gt_tickers), with a separate in-watchlist recall (the system can only extract
    watchlist symbols, so off-watchlist ground truth is an inherent recall ceiling);
  - relevance-aware false positives: for macro/irrelevant articles the system should
    extract nothing, so any extraction is a false positive.

Sentiment sign-accuracy and end-to-end IC require forward returns + a clean
news→signal join and are reported once compute_label_forward_returns.py has run.

Offline / read-only. Run inside the worker container:
    docker compose exec worker python scripts/validate_ticker_sentiment.py
"""
from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable

import psycopg2
import psycopg2.extras
import yaml


def _conn():
    url = os.environ.get("DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading")
    return psycopg2.connect(url)


def _watchlist() -> set[str]:
    path = os.path.join(os.path.dirname(__file__), "..", "config", "trading.yaml")
    try:
        with open(path) as f:
            return set(yaml.safe_load(f).get("symbols", {}).get("watchlist", []))
    except Exception:
        return set()


def _safe_div(a: float, b: float) -> float | None:
    return (a / b) if b else None


def _news_label_columns(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = current_schema()
                 AND table_name = 'news_labels'"""
        )
        return {row[0] for row in cur.fetchall()}


def _label_signature(row: dict) -> tuple:
    """Campi discreti che devono coincidere per essere ground truth canonica.

    La strength continua non entra nella worklist di adjudication #54: imporne
    l'uguaglianza esatta scarterebbe coppie che il workflow considera concordi.
    """
    return (
        tuple(
            sorted(
                {
                    str(ticker).strip().upper()
                    for ticker in (row.get("gt_tickers") or [])
                    if str(ticker).strip()
                }
            )
        ),
        row.get("gt_relevance"),
        row.get("gt_sentiment_dir"),
    )


def _latest_label(rows: Iterable[dict]) -> dict:
    return max(
        rows,
        key=lambda row: (
            str(row.get("label_date") or ""),
            int(row.get("label_id") or 0),
        ),
    )


def _select_measurement_labels(
    rows: list[dict], *, two_annotator_schema: bool
) -> list[dict]:
    """Restituisce al massimo una ground truth per articolo.

    Sullo schema legacy ``UNIQUE(url)`` ogni riga labeled era gia' finale. Sullo
    schema 046 una coppia non adjudicata entra solo se i due annotatori
    concordano; un disaccordo richiede una singola decisione adjudicated. Dati
    incompleti o ambigui restano fuori dalla misura invece di essere contati
    come ground truth indipendenti.
    """
    if not two_annotator_schema:
        return list(rows)

    by_article: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        news_log_id = row.get("news_log_id")
        if news_log_id is not None:
            by_article[int(news_log_id)].append(row)

    selected: list[dict] = []
    for news_log_id in sorted(by_article):
        article_rows = by_article[news_log_id]
        adjudicated = [row for row in article_rows if row.get("adjudicated") is True]
        if len(adjudicated) == 1:
            selected.append(adjudicated[0])
            continue

        signatures = {_label_signature(row) for row in article_rows}
        if len(signatures) != 1:
            continue
        if len(article_rows) == 2 or adjudicated:
            selected.append(_latest_label(article_rows))
    return selected


def _load_measurement_labels() -> list[dict]:
    with _conn() as conn:
        columns = _news_label_columns(conn)
        two_annotator_schema = "adjudicated" in columns
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if two_annotator_schema:
                cur.execute(
                    """SELECT label_id, news_log_id, url, source,
                              extracted_tickers, gt_tickers, gt_relevance,
                              gt_sentiment_dir, gt_sentiment_strength,
                              text_adequacy, annotator_id, label_date, adjudicated
                         FROM news_labels WHERE status = 'labeled'"""
                )
            else:
                cur.execute(
                    """SELECT label_id, url, source, extracted_tickers,
                              gt_tickers, gt_relevance, gt_sentiment_dir,
                              gt_sentiment_strength, text_adequacy,
                              annotator_id, label_date
                         FROM news_labels WHERE status = 'labeled'"""
                )
            rows = [dict(row) for row in cur.fetchall()]
    return _select_measurement_labels(
        rows, two_annotator_schema=two_annotator_schema
    )


def main() -> None:
    watch = _watchlist()
    rows = _load_measurement_labels()

    if not rows:
        print("No canonical labeled articles yet — complete second annotations/adjudication.")
        return

    # accumulators per source (+ 'ALL')
    acc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def add(key: str, **kw):
        for k, v in kw.items():
            acc[key][k] += v

    for r in rows:
        ext = set(r["extracted_tickers"] or [])
        gt = set(r["gt_tickers"] or [])
        gt_inwatch = {t for t in gt if t in watch}
        tp = ext & gt
        fp = ext - gt
        fn = gt - ext
        relevance = r["gt_relevance"]
        # macro/irrelevant → system should extract nothing
        rel_fp = len(ext) if relevance in ("macro", "irrelevant") else 0

        for key in (r["source"], "ALL"):
            add(key, n=1, n_extracted=len(ext), n_gt=len(gt), n_gt_inwatch=len(gt_inwatch),
                tp=len(tp), fp=len(fp), fn=len(fn),
                tp_inwatch=len(ext & gt_inwatch), rel_fp=rel_fp,
                n_macro_irrelevant=1 if relevance in ("macro", "irrelevant") else 0)

    print(f"# QX-01 Extraction Validation — {len(rows)} labeled articles\n")
    print(f"{'source':16} {'n':>4} {'prec':>6} {'recall':>7} {'rec(WL)':>8} {'FP/art':>7} {'macro-FP':>9}")
    for key in sorted(acc, key=lambda k: (k != "ALL", k)):
        a = acc[key]
        prec = _safe_div(a["tp"], a["n_extracted"])
        recall = _safe_div(a["tp"], a["n_gt"])
        recall_wl = _safe_div(a["tp_inwatch"], a["n_gt_inwatch"])
        fp_per_art = _safe_div(a["fp"], a["n"])
        macro_fp = _safe_div(a["rel_fp"], a["n_macro_irrelevant"]) if a["n_macro_irrelevant"] else None

        def f(x): return f"{x:.2f}" if x is not None else "  -"
        print(f"{key:16} {int(a['n']):>4} {f(prec):>6} {f(recall):>7} {f(recall_wl):>8} "
              f"{f(fp_per_art):>7} {f(macro_fp):>9}")

    print("\nLegenda: prec = ext∩gt / ext · recall = ext∩gt / gt · rec(WL) = recall solo su gt in watchlist")
    print("FP/art = falsi positivi medi per articolo · macro-FP = ticker estratti su news macro/irrilevanti (dovrebbe ≈0)")

    _print_precision_by_method(rows)

    print("\nSentiment sign-accuracy + IC end-to-end: in attesa di compute_label_forward_returns.py.")


def _method_metrics(mapping_rows: list[dict], labels: list[dict]) -> dict[str, dict]:
    gt_by_url = {
        str(row.get("url") or ""): {
            str(ticker).strip().upper()
            for ticker in (row.get("gt_tickers") or [])
            if str(ticker).strip()
        }
        for row in labels
        if row.get("url")
    }
    by: dict[str, list[int]] = defaultdict(list)
    for row in mapping_rows:
        url = str(row.get("url") or "")
        method = str(row.get("method") or "")
        if url not in gt_by_url or not method:
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        by[method].append(int(ticker in gt_by_url[url]))
    return {
        method: {
            "n": len(values),
            "precision": sum(values) / len(values),
            "error_rate": 1.0 - (sum(values) / len(values)),
        }
        for method, values in by.items()
    }


def _print_precision_by_method(labels: list[dict]) -> None:
    """Extraction precision per extraction_method (source_metadata / cashtag / org_lookup
    / regex), joining labeled articles to news_log. This is the data-driven lens for the
    'keep or drop GDELT (org_lookup)' decision: it isolates which extraction PATH — not
    just which source — produces false positives. Only rows with a recorded method (QT-03).

    ``labels`` contiene gia' una sola ground truth canonica per articolo: la
    query legge soltanto i mapping ``news_log`` e non moltiplica il campione per
    i due annotatori dello schema 046.
    """
    urls = sorted({str(row.get("url") or "") for row in labels if row.get("url")})
    if not urls:
        print("\nPrecision per extraction_method: nessuna label con URL canonico.")
        return
    with _conn() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute(
            """SELECT url, extraction_method AS method, ticker
                 FROM news_log
                WHERE url = ANY(%s)
                  AND extraction_method IS NOT NULL
                  AND extraction_method <> ''""",
            (urls,),
        )
        mapping_rows = [dict(row) for row in cur.fetchall()]
    metrics = _method_metrics(mapping_rows, labels)
    if not metrics:
        print("\nPrecision per extraction_method: nessuna label con extraction_method (QT-03) ancora.")
        return
    print(
        f"\n# Precision per extraction_method\n"
        f"{'method':18} {'n':>5} {'precision':>10} {'error':>8}"
    )
    for method in sorted(metrics, key=lambda name: (-metrics[name]["n"], name)):
        values = metrics[method]
        print(
            f"{method:18} {values['n']:>5} {values['precision']:>10.2f} "
            f"{values['error_rate']:>8.2f}"
        )
    print("→ Confrontare i path solo dopo un campione sufficiente per ciascun metodo.")


if __name__ == "__main__":
    main()
