#!/usr/bin/env python3
"""Quali simboli di watchlist il sentiment non raggiunge mai (#226).

Sola lettura su PostgreSQL: conta i segnali per simbolo nella finestra, li confronta
con la watchlist di `config/trading.yaml` e applica i due controlli di
`src/analysis/watchlist_coverage.py`. Non scrive niente, non manda alert, non tocca
ordini.

Il caso che ha motivato il controllo: `BRK.B` e' rimasto cieco al sentiment per 96
segnali, perche' venivano scritti come `BRKB`. Nessuno se n'era accorto, e un
controllo su `execution_decisions` non l'avrebbe visto — quel simbolo ha quattro
righe li', prodotte dal path momentum, che non passa dal sentiment.

Uso:
    set -a; source .env; set +a
    uv run python scripts/check_watchlist_coverage.py
    uv run python scripts/check_watchlist_coverage.py --giorni 90
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

_TRADING_YAML = Path(__file__).resolve().parents[1] / "config" / "trading.yaml"


def _watchlist() -> list[str]:
    cfg = yaml.safe_load(_TRADING_YAML.read_text())
    return list(cfg.get("symbols", {}).get("watchlist", []))


def main() -> int:
    import psycopg2

    from src.analysis.watchlist_coverage import (
        orfani_di_normalizzazione,
        simboli_watchlist_senza_segnali,
    )
    from src.config import config

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--giorni",
        type=int,
        default=30,
        help="finestra di osservazione (default 30). Un simbolo puo' non fare notizia "
        "per settimane: su finestre corte i 'muti' sono rumore.",
    )
    args = parser.parse_args()

    watchlist = _watchlist()
    if not watchlist:
        print("Watchlist vuota in config/trading.yaml — niente da controllare.")
        return 1

    with psycopg2.connect(config.DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT symbol, COUNT(*)
            FROM sentiment_signals
            WHERE created_at > NOW() - make_interval(days => %s)
            GROUP BY symbol
            """,
            (args.giorni,),
        )
        conteggi = {riga[0]: riga[1] for riga in cur.fetchall()}

    orfani = orfani_di_normalizzazione(watchlist, conteggi.keys())
    muti = simboli_watchlist_senza_segnali(watchlist, conteggi)

    print(f"Finestra: {args.giorni} giorni · watchlist: {len(watchlist)} simboli · "
          f"simboli con segnali: {len(conteggi)}")

    print(f"\n=== Orfani di normalizzazione ({len(orfani)}) ===")
    if not orfani:
        print("  nessuno.")
    for forma_segnale, forma_watchlist in orfani:
        n = conteggi.get(forma_segnale, 0)
        print(f"  {forma_segnale:<8} → watchlist dice '{forma_watchlist}' · "
              f"{n} segnali persi")
    if orfani:
        print("  ^ DIFETTO: questi segnali non raggiungeranno mai il libro.")

    print(f"\n=== Simboli di watchlist senza segnali ({len(muti)}) ===")
    if not muti:
        print("  nessuno.")
    else:
        # Un orfano spiega gia' perche' la sua forma canonica e' muta: separarli
        # evita di far leggere due volte lo stesso difetto.
        spiegati = {canonica for _, canonica in orfani}
        for simbolo in muti:
            nota = " (spiegato da un orfano qui sopra)" if simbolo in spiegati else ""
            print(f"  {simbolo}{nota}")
        if len(muti) > len(spiegati):
            print("  ^ SOSPETTO: verificare se e' assenza di notizie o un altro "
                  "difetto di scrittura del simbolo.")

    # Uscita non-zero solo sugli orfani: quelli sono un difetto accertato, i muti
    # sono un sospetto e non devono far fallire un controllo automatico.
    return 2 if orfani else 0


if __name__ == "__main__":
    raise SystemExit(main())
