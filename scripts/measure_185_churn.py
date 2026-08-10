#!/usr/bin/env python3
"""Misura la firma di churn S1 descritta dalla issue #185.

Una uscita conta come churn solo se una posizione S1 chiusa da
``s1_weight_drop`` viene ricomprata da S1, allo stesso peso, tra 15 e 60
minuti dopo. Le righe senza ``order_id`` non rappresentano ordini eseguiti e
sono escluse. Lo script legge soltanto ``execution_decisions`` e ``trades``.

La firma e' volutamente stretta (strategia + peso + esecuzione + finestra)
perche' qualunque BUY entro 60 minuti confonde tre meccanismi diversi — la PR
#207 fu respinta proprio per questo. Vedi ``tests/test_185_churn_measurement.py``
per i quattro vincoli inchiodati come test.

Il verdetto di uscita distingue tre stati, perche' "zero churn post-deploy" da
solo non dimostra che il fix ha funzionato: se non c'e' stata una finestra di
ribilanciamento mensile nei giorni successivi al deploy, ci sono zero drop da
misurare e il numero si legge come successo a vuoto. E' la stessa classe di
errore di #191/#210 — una misura che non misura cio' che dichiara.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone
from typing import Any


# Primo ciclo di portafoglio dopo il deploy del fix #188 (rebuild delle 11:08
# UTC del 2026-08-07). Separra le evidenze "pre" (churn a 15 min) dalle "post"
# (cadenza MONTHLY rispettata).
DEFAULT_DEPLOY_CUTOFF = datetime(2026, 8, 7, 14, 7, tzinfo=timezone.utc)
MIN_REENTRY_DELAY = timedelta(minutes=15)
MAX_REENTRY_DELAY = timedelta(minutes=60)


EXIT_MECHANISM_CAVEAT = (
    "Avvertenza exit_mechanism (#184): fino al fix #184 l'etichetta era dedotta "
    "dall'eta' dell'ultimo segnale in DB, quindi i conteggi su 'expired'/'whipsaw' "
    "pre-fix sono una stima per eta', non una misura del meccanismo "
    "(docs/exit_mechanism_labels.md). Questa misura NON ne soffre: filtra su "
    "exit_mechanism='s1_weight_drop', che e' il tag osservato del path #72 "
    "(_reason_and_mechanism_for_non_s4_weight_drop, basato sull'origine "
    "trades.stop_strategy della posizione, non sull'eta' del segnale), deployato "
    "il 2026-07-21, prima della finestra letta. Il classificatore S4 corretto "
    "da #184 non entra in questa firma."
)


def _same_weight(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    try:
        # portfolio_scheduler scrive i pesi target nel Decision Log come
        # percentuale a un decimale (es. 1.2%). Il valore raw si muove leggermente
        # col NAV fra cicli, quindi confrontiamo il peso visibile all'operatore
        # invece di pretendere che i float binari siano identici.
        return f"{float(left) * 100:.1f}" == f"{float(right) * 100:.1f}"
    except (TypeError, ValueError):
        return False


def classify_drops(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classifica le uscite S1 eseguite contro la firma prescritta da #185."""
    drops = [
        row
        for row in rows
        if row.get("decision") in {"SELL", "EXIT"}
        and row.get("exit_mechanism") == "s1_weight_drop"
        and row.get("strategy_id") == "S1"
        and row.get("order_id")
    ]
    buys_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if (
            row.get("decision") == "BUY"
            and row.get("strategy_id") == "S1"
            and row.get("order_id")
        ):
            buys_by_symbol.setdefault(str(row["symbol"]), []).append(row)
    for buys in buys_by_symbol.values():
        buys.sort(key=lambda row: row["tick_time"])

    classified: list[dict[str, Any]] = []
    for drop in drops:
        reentry_time = None
        for buy in buys_by_symbol.get(str(drop["symbol"]), []):
            delay = buy["tick_time"] - drop["tick_time"]
            if delay < MIN_REENTRY_DELAY:
                continue
            if delay > MAX_REENTRY_DELAY:
                break
            if _same_weight(drop.get("target_weight"), buy.get("target_weight")):
                reentry_time = buy["tick_time"]
                break
        classified.append(
            {
                "tick_time": drop["tick_time"],
                "symbol": drop["symbol"],
                "target_weight": drop.get("target_weight"),
                "reentry_time": reentry_time,
                "is_churn": reentry_time is not None,
            }
        )
    return classified


def per_session(
    drops: list[dict[str, Any]], deploy_cutoff: datetime
) -> list[dict[str, Any]]:
    """Aggrega le uscite per data UTC e le separa sul cutoff di deploy."""
    sessions: dict[str, dict[str, Any]] = {}
    for drop in drops:
        tick_time = drop["tick_time"].astimezone(timezone.utc)
        date = tick_time.date().isoformat()
        slot = sessions.setdefault(
            date,
            {"date": date, "phase": "post", "drops": 0, "churn": 0},
        )
        slot["drops"] += 1
        slot["churn"] += int(drop["is_churn"])
        if tick_time < deploy_cutoff:
            slot["phase"] = "pre"
    return sorted(sessions.values(), key=lambda row: row["date"])


def verdict(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Sintetizza il verdetto distinguendo tre stati per la fase post-deploy.

    - ``inconclusive``: zero drop post-deploy. Niente da misurare — tipicamente
      perche' non c'e' ancora stata una finestra di ribilanciamento mensile.
      Non e' prova che il churn sia sparito.
    - ``resolved``: drop osservati e nessun reingresso entro la firma. Il fix
      ha tenuto.
    - ``still_present``: la firma e' ancora osservata. La diagnosi di #185 era
      incompleta.
    """
    pre = [s for s in sessions if s["phase"] == "pre"]
    post = [s for s in sessions if s["phase"] == "post"]
    pre_drops = sum(s["drops"] for s in pre)
    pre_churn = sum(s["churn"] for s in pre)
    post_drops = sum(s["drops"] for s in post)
    post_churn = sum(s["churn"] for s in post)
    if post_drops == 0:
        post_status = "inconclusive"
    elif post_churn == 0:
        post_status = "resolved"
    else:
        post_status = "still_present"
    return {
        "pre_drops": pre_drops,
        "pre_churn": pre_churn,
        "post_drops": post_drops,
        "post_churn": post_churn,
        "post_status": post_status,
    }


def _fetch_rows(conn: Any, since: datetime) -> list[dict[str, Any]]:
    """Legge drop e BUY con attribuzione, peso e prova di submission.

    Acquisisce ``trades.stop_strategy`` (strategia d'origine della posizione,
    #72) e ``trades.score`` (peso di allocazione, non il sentiment score che sta
    in ``signal_score`` — vedi migration 023/028) e richiede ``order_id`` non
    NULL su entrambi i lati, cosicche' un ordine mai eseguito non conti come
    churn. Sono i tre attributi che la query respinta di #207 non acquisiva.
    """
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            WITH drop_events AS (
                SELECT ed.tick_time,
                       ed.symbol,
                       ed.decision,
                       ed.exit_mechanism,
                       t.stop_strategy AS strategy_id,
                       t.score AS target_weight,
                       ed.order_id
                FROM execution_decisions ed
                JOIN trades t
                  ON ed.order_id = t.exit_order_id
                  OR ed.order_id = ANY(COALESCE(t.exit_order_ids, ARRAY[]::TEXT[]))
                WHERE ed.tick_time >= %s
                  AND ed.decision IN ('SELL', 'EXIT')
                  AND ed.exit_mechanism = 's1_weight_drop'
                  AND ed.order_id IS NOT NULL
            ),
            buy_events AS (
                SELECT ed.tick_time,
                       ed.symbol,
                       ed.decision,
                       ed.exit_mechanism,
                       t.stop_strategy AS strategy_id,
                       t.score AS target_weight,
                       ed.order_id
                FROM execution_decisions ed
                JOIN trades t
                  ON t.decision_id = ed.id
                 AND t.entry_order_id = ed.order_id
                WHERE ed.tick_time >= %s
                  AND ed.decision = 'BUY'
                  AND ed.order_id IS NOT NULL
            )
            SELECT * FROM drop_events
            UNION ALL
            SELECT * FROM buy_events
            ORDER BY tick_time
            """,
            (since, since),
        )
        return [dict(row) for row in cursor.fetchall()]


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _connect():
    import psycopg2

    database_url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(database_url)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--deploy-cutoff",
        default=DEFAULT_DEPLOY_CUTOFF.isoformat(),
        help="Primo ribilanciamento S1 dopo il deploy del fix.",
    )
    parser.add_argument(
        "--since",
        default=(DEFAULT_DEPLOY_CUTOFF - timedelta(days=14)).isoformat(),
        help="Inizio della finestra letta dal DB.",
    )
    args = parser.parse_args()
    deploy_cutoff = _parse_timestamp(args.deploy_cutoff)
    since = _parse_timestamp(args.since)

    print(EXIT_MECHANISM_CAVEAT)
    print()

    conn = _connect()
    try:
        drops = classify_drops(_fetch_rows(conn, since))
    finally:
        conn.close()
    sessions = per_session(drops, deploy_cutoff)

    print(f"{'date (UTC)':<12} {'phase':<6} {'drops':>6} {'churn':>6}")
    for session in sessions:
        print(
            f"{session['date']:<12} {session['phase']:<6} "
            f"{session['drops']:>6} {session['churn']:>6}"
        )

    summary = verdict(sessions)
    print()
    print(f"pre-fix:  drops={summary['pre_drops']:<3} churn={summary['pre_churn']}")
    print(f"post-fix: drops={summary['post_drops']:<3} churn={summary['post_churn']}")
    status_line = {
        "inconclusive": (
            "INCONCLUSIVE: nessun drop S1 osservato dopo il deploy — niente da "
            "misurare (probabilmente nessuna finestra di ribilanciamento mensile "
            "ancora). Non e' prova che il churn sia sparito."
        ),
        "resolved": (
            "RESOLVED: drop osservati e nessun reingresso entro la firma. Il fix "
            "#188 ha tenuto."
        ),
        "still_present": (
            "STILL PRESENT: la firma di churn e' ancora osservata dopo il deploy. "
            "La diagnosi di #185 era incompleta."
        ),
    }[summary["post_status"]]
    print(status_line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())