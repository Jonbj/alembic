#!/usr/bin/env python3
"""Copertura per giorno della colonna controfattuale (#337).

Sola lettura su PostgreSQL. Per ogni giornata nella finestra conta le decisioni
skip idonee, quante hanno `counterfactual_computed_at`, quante restano in attesa
per costruzione (`PENDING_OVERNIGHT`), e a che ora cade la prima riga calcolata.

E' la verifica della DoD di #337: la riga di una giornata e' coperta quando

    count(*) = count(counterfactual_computed_at)
             + count(*) FILTER (WHERE counterfactual_skip_reason = 'PENDING_OVERNIGHT')

La firma del difetto che ha motivato il controllo: sopra le ~500 skip al giorno il
vecchio `LIMIT 500` riempiva il batch dalle righe piu' recenti, e la prima riga
calcolata slittava a circa un'ora dopo l'apertura — cioe' proprio la finestra dove
atterrano le news overnight. Se `prima_calcolata` non e' vicina all'apertura,
la censura e' tornata.

Uso:
    set -a; source .env; set +a
    uv run python scripts/check_counterfactual_coverage.py
    uv run python scripts/check_counterfactual_coverage.py --giorni 14
"""
from __future__ import annotations

import argparse

_DECISIONI = ("SKIP_THRESHOLD", "SKIP_EMA", "SKIP_CAP", "SKIP_PYRAMIDING")

_SQL = """
    SELECT
        (tick_time AT TIME ZONE 'UTC')::date               AS giorno,
        COUNT(*)                                            AS righe,
        COUNT(counterfactual_computed_at)                   AS calcolate,
        COUNT(*) FILTER (
            WHERE counterfactual_skip_reason = 'PENDING_OVERNIGHT')  AS in_attesa,
        COUNT(counterfactual_return_1h)                     AS con_return_1h,
        COUNT(counterfactual_return_overnight)              AS con_return_overnight,
        MIN(tick_time) FILTER (
            WHERE counterfactual_computed_at IS NOT NULL)   AS prima_calcolata,
        MIN(tick_time)                                      AS prima_riga
    FROM execution_decisions
    WHERE decision = ANY(%s)
      AND tick_time >= now() - make_interval(days => %s)
    GROUP BY 1
    ORDER BY 1
"""

_SQL_MOTIVI = """
    SELECT COALESCE(counterfactual_skip_reason, '(return valorizzato)') AS motivo,
           COUNT(*) AS righe
    FROM execution_decisions
    WHERE decision = ANY(%s)
      AND tick_time >= now() - make_interval(days => %s)
    GROUP BY 1
    ORDER BY 2 DESC
"""


def main() -> int:
    import psycopg2

    from src.config import config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--giorni", type=int, default=7, help="finestra (default 7)")
    args = parser.parse_args()

    with psycopg2.connect(config.DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(_SQL, (list(_DECISIONI), args.giorni))
        righe = cur.fetchall()
        cur.execute(_SQL_MOTIVI, (list(_DECISIONI), args.giorni))
        motivi = cur.fetchall()

    if not righe:
        print("Nessuna decisione skip nella finestra.")
        return 0

    print(f"Finestra: {args.giorni} giorni · decisioni: {', '.join(_DECISIONI)}\n")
    print(f"{'giorno':<12}{'righe':>7}{'calc':>7}{'attesa':>8}{'ret1h':>7}"
          f"{'overnt':>8}  {'prima riga':<8}{'prima calcolata':<16}esito")

    scoperti = 0
    for (giorno, tot, calc, attesa, ret1h, overnight,
         prima_calc, prima_riga) in righe:
        coperto = (calc + attesa) == tot
        if not coperto:
            scoperti += 1
        h_riga = prima_riga.strftime("%H:%M") if prima_riga else "—"
        h_calc = prima_calc.strftime("%H:%M") if prima_calc else "—"
        esito = "ok" if coperto else f"SCOPERTA: {tot - calc - attesa} righe"
        print(f"{str(giorno):<12}{tot:>7}{calc:>7}{attesa:>8}{ret1h:>7}"
              f"{overnight:>8}  {h_riga:<8}{h_calc:<16}{esito}")

    print("\n=== Motivi persistiti ===")
    for motivo, n in motivi:
        print(f"  {motivo:<24}{n:>7}")

    if scoperti:
        print(f"\nDIFETTO: {scoperti} giornate hanno righe ne' calcolate ne' in attesa.")
        return 1

    print("\nCopertura piena su tutte le giornate della finestra.")
    print("Controlla comunque 'prima calcolata' contro 'prima riga': se slitta di "
          "un'ora, il batch sta di nuovo affamando l'apertura.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
