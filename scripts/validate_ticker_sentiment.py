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


def main() -> None:
    watch = _watchlist()
    with _conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """SELECT source, extracted_tickers, gt_tickers, gt_relevance
                   FROM news_labels WHERE status='labeled'"""
            )
            rows = cur.fetchall()

    if not rows:
        print("No labeled rows yet — annotate first.")
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
    print("\nSentiment sign-accuracy + IC end-to-end: in attesa di compute_label_forward_returns.py.")


if __name__ == "__main__":
    main()
