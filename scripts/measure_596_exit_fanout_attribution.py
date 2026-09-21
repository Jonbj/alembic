#!/usr/bin/env python3
"""Misura #596 — fan-out attribution delle uscite S4 in finestra.

Legge SOLO il DB live (alembic-postgres-1), niente Redis state, niente
modifiche. Scrive l'artefatto JSON con il breakdown per categoria di
rilevanza e gli esempi rumorosi per la review.

Pre-registrazione: docs/evidence/PREREGISTRAZIONE_596_EXIT_FANOUT_PROVENANCE_2026-09-21.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.analysis.dossier.article_coverage import classify_attribution  # noqa: E402
from src.store.pg_store import PostgreSQLStore  # noqa: E402

WINDOW_START = datetime(2026, 8, 1, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 9, 21, 23, 59, 59, tzinfo=timezone.utc)

# Population filter — pre-registered in
# docs/evidence/PREREGISTRAZIONE_596_EXIT_FANOUT_PROVENANCE_2026-09-21.md §
# "Campione (fissato prima della misura)". Una SELL entra in popolazione se e
# solo se:
#   exit_mechanism = 'below_entry_gate' (weight-0 S4 in `_run_cycle_inner`),
#   OPPURE exit_mechanism IS NULL AND reason LIKE 'sentiment_reversal:%'
#   (le reversal non scrivono exit_mechanism: il segnale vive in reason).
# Uscite target_hit, stop_loss, *_weight_drop sono FUORI popolazione per la
# issue #596.
QUERY = """
SELECT
    ed.id              AS decision_id,
    ed.tick_time,
    ed.symbol          AS decision_symbol,
    ed.signal_id,
    ed.signal_score,
    ed.exit_mechanism,
    ed.reason,
    n.id               AS news_log_id,
    n.title,
    n.url,
    n.extraction_method,
    CASE
        WHEN COALESCE(n.url, '') = '' THEN NULL
        ELSE (SELECT count(*) FROM news_log n2 WHERE n2.url = n.url)
    END                AS n_ticker_articolo
FROM execution_decisions ed
LEFT JOIN sentiment_signals s ON s.id = ed.signal_id
LEFT JOIN news_log n           ON n.id = s.news_log_id
WHERE ed.decision = 'SELL'
  AND ed.tick_time >= %s AND ed.tick_time <= %s
  AND ed.signal_id IS NOT NULL
  AND s.news_log_id IS NOT NULL
  AND COALESCE(n.url, '') <> ''
  AND (
        ed.exit_mechanism = 'below_entry_gate'
        OR (ed.exit_mechanism IS NULL AND ed.reason LIKE 'sentiment_reversal:%%')
  )
ORDER BY ed.tick_time
"""

OUT_PATH = REPO / "docs" / "evidence" / "EXIT_FANOUT_PROVENANCE_596_2026-09-21.json"


def _is_reversal(reason: str | None) -> bool:
    return bool(reason) and "sentiment_reversal" in (reason or "")


def filter_population(rows: list[dict]) -> list[dict]:
    """Filtra le righe alla popolazione pre-registrata (#596).

    Stessa clausola del QUERY, applicabile post-fetch (utile ai test che non
    aprono il DB live). Ogni riga deve avere almeno `exit_mechanism`, `reason`
    e `decision` per essere classificabile.

    Esclusioni esplicite: ``target_hit``, ``stop_loss``, ``<strategy>_weight_drop``
    e qualsiasi altra exit non in popolazione.
    """
    kept: list[dict] = []
    for row in rows:
        if row.get("decision") != "SELL":
            continue
        mech = row.get("exit_mechanism")
        reason = row.get("reason") or ""
        if mech == "below_entry_gate":
            kept.append(row)
        elif mech is None and reason.startswith("sentiment_reversal:"):
            kept.append(row)
    return kept


def main() -> int:
    store = PostgreSQLStore()
    rows: list[dict] = []
    try:
        conn = store._get_connection()
        with conn.cursor() as cur:
            cur.execute(QUERY, (WINDOW_START, WINDOW_END))
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                rows.append({k: v for k, v in zip(cols, r)})
    finally:
        store.close()

    # Defense-in-depth: la WHEREClause del QUERY gia' applica il filtro
    # pre-registrato, ma rieseguire il check in Python garantisce che la
    # popolazione resti ancorata al criterio anche se il QUERY cambia.
    rows = filter_population(rows)

    by_category: Counter[str] = Counter()
    by_mechanism: Counter[str] = Counter()
    noisy_samples: list[dict] = []
    clean_samples: list[dict] = []

    for row in rows:
        ticker = row["decision_symbol"]
        title = row["title"] or ""
        url = row["url"] or ""
        body_snippet = url
        extraction_method = row["extraction_method"] or ""
        fanout = row["n_ticker_articolo"]

        category = classify_attribution(
            ticker=ticker,
            title=title,
            body_snippet=body_snippet,
            extraction_method=extraction_method,
            n_ticker_articolo=fanout,
        )
        by_category[category] += 1
        is_reversal = _is_reversal(row["reason"])
        mech_label = (
            "sentiment_reversal" if is_reversal
            else f"exit_mechanism={row['exit_mechanism']}" if row["exit_mechanism"]
            else "other"
        )
        by_mechanism[mech_label] += 1

        sample = {
            "decision_id": row["decision_id"],
            "tick_time": row["tick_time"].isoformat() if row["tick_time"] else None,
            "symbol": ticker,
            "signal_id": row["signal_id"],
            "signal_score": float(row["signal_score"]) if row["signal_score"] is not None else None,
            "exit_mechanism": row["exit_mechanism"],
            "mechanism_label": mech_label,
            "category": category,
            "n_ticker_articolo": fanout,
            "news_log_id": row["news_log_id"],
            "title": title[:200],
            "url": url,
            "extraction_method": extraction_method,
        }
        if category in ("SECTOR_MACRO", "IRRELEVANT_FANOUT", "FALSE_ENTITY_MATCH"):
            noisy_samples.append(sample)
        elif category == "ISSUER_SPECIFIC":
            clean_samples.append(sample)

    total = sum(by_category.values())
    noisy = by_category["SECTOR_MACRO"] + by_category["IRRELEVANT_FANOUT"] + by_category["FALSE_ENTITY_MATCH"]
    noisy_rate = noisy / total if total else 0.0

    if noisy_rate > 0.30:
        verdict = "OUT-A"
    elif noisy_rate <= 0.10:
        verdict = "OUT-B"
    else:
        verdict = "OUT-INCONCLUSIVE"

    artifact = {
        "issue": 596,
        "preregistrazione": "docs/evidence/PREREGISTRAZIONE_596_EXIT_FANOUT_PROVENANCE_2026-09-21.md",
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "total_rows": total,
        "by_category": dict(by_category),
        "by_mechanism": dict(by_mechanism),
        "noisy_total": noisy,
        "noisy_rate": noisy_rate,
        "verdict": verdict,
        "noisy_samples_count": len(noisy_samples),
        "noisy_samples_first20": noisy_samples[:20],
        "clean_samples_count": len(clean_samples),
        "clean_samples_first5": clean_samples[:5],
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(artifact, indent=2, default=str))
    print(f"Wrote {OUT_PATH}")
    print(f"Verdict: {verdict}  noisy_rate={noisy_rate:.1%}  (n={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
