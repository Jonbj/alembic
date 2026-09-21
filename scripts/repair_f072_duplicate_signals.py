#!/usr/bin/env python3
"""#551/F-072: one-off repair of the 12 duplicate-signal groups of 2026-09-08.

Il 2026-09-08 un SoftTimeLimitExceeded ha ucciso run_sentiment_worker a meta'
batch: gli articoli gia' persistiti sono rimasti in news:processing e la
crash-recovery del run successivo li ha ri-scorati. Risultato: 12 news_log_id
(9902-9913) con due righe in sentiment_signals ciascuno, a ~27 minuti di
distanza, con score e provider diversi. Il ranker prende il segnale piu'
recente (F-023), quindi la seconda riga — il re-score spurio — e' quella
autoritativa.

Cosa tiene e cosa via: si tiene il PRIMO giro di scoring (id minore), quello
che l'articolo ha davvero prodotto; si cancella il secondo, figlio del
difetto. Il 2° giro di GOOGL 9902 cambia provider (finbert -> single:gpt-oss)
e SPY 9912 passa da single:glm a ensemble: e' la firma del bug, non un
secondo segnale legittimo.

ATTENZIONE — serie osservata. Queste 12 righe cadono dentro la finestra di
osservazione #171 (chiude il 2026-09-28): cancellarle e' una modifica di una
serie osservata e come tale va registrata (OBSERVATION_CHARTER), non fatta in
silenzio. Lo script e' lo STRUMENTO della decisione dell'operatore: di
default stampa cosa farebbe (dry-run), scrive solo con --apply. L'IC e i
conteggi che le usavano vanno ricalcolati dopo.

Idempotente: rieseguire dopo il repair non trova piu' duplicati e non scrive.

Run (dry-run, nessuna scrittura):
    .venv/bin/python scripts/repair_f072_duplicate_signals.py
Run (scrittura):
    .venv/bin/python scripts/repair_f072_duplicate_signals.py --apply
"""
from __future__ import annotations

import argparse
import sys

F072_NEWS_LOG_IDS = list(range(9902, 9914))


def rows_to_delete(rows: list[dict]) -> list[dict]:
    """Per ogni news_log_id tiene il segnale piu' vecchio, restituisce i successivi.

    L'ordinamento e' su (news_log_id, id): gli id di sentiment_signals sono
    monotoni nel tempo, quindi il minimo e' il primo giro di scoring.
    """
    kept: dict[int, dict] = {}
    drop: list[dict] = []
    for row in sorted(rows, key=lambda r: (r["news_log_id"], r["id"])):
        news_log_id = row["news_log_id"]
        if news_log_id in kept:
            drop.append(row)
        else:
            kept[news_log_id] = row
    return drop


def main() -> int:
    import psycopg2

    from src.config import config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="esegue la DELETE (default: dry-run, nessuna scrittura)",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, news_log_id, symbol, score, model_id, generated_at
                FROM sentiment_signals
                WHERE news_log_id = ANY(%s)
                ORDER BY news_log_id, id
                """,
                (F072_NEWS_LOG_IDS,),
            )
            columns = [d.name for d in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]
    except Exception:
        conn.rollback()
        raise

    drop = rows_to_delete(rows)
    print(f"F-072: {len(F072_NEWS_LOG_IDS)} news_log_id, "
          f"{len(rows)} righe totali, {len(drop)} da cancellare\n")
    for row in rows:
        mark = "DELETE" if row in drop else "keep "
        print(f"  [{mark}] signal {row['id']} news_log {row['news_log_id']} "
              f"{row['symbol']} score={row['score']:+.4f} "
              f"model={row['model_id']} at {row['generated_at']}")

    if not drop:
        print("\nNessun duplicato: nulla da fare.")
        return 0

    if not args.apply:
        print("\nDRY-RUN — nessuna scrittura. Riesegui con --apply per eseguire.")
        return 0

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM sentiment_signals WHERE id = ANY(%s)",
            ([r["id"] for r in drop],),
        )
        deleted = cur.rowcount
    conn.commit()
    print(f"\n--apply: cancellate {deleted} righe "
          f"(le tabelle figlie seguono le FK: llm_responses ON DELETE CASCADE, "
          f"le altre ON DELETE SET NULL).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
