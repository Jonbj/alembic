#!/usr/bin/env python3
"""Disposizione dei reperti di triage: vero, falso, gia' noto (2026-09-16).

Il pezzo che mancava alla review notturna delle PR: 79 rilievi pubblicati, nove
commenti su dieci senza risposta, e nessun modo di sapere se lo strumento
funzionasse. Qui ogni reperto viene chiuso con un esito, e da quegli esiti esce
un numero invece di un'impressione.

Clausola di uscita dichiarata il 2026-09-14: **zero reperti confermati in due
settimane e il job si spegne.** `--riassunto` serve a verificarla.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ESITI = ("confermato", "falso", "gia_noto")


def carica(percorso: Path) -> list[dict]:
    """Righe di un jsonl, o lista vuota se il file non esiste ancora."""
    if not percorso.exists():
        return []
    return [json.loads(riga) for riga in percorso.read_text().splitlines() if riga.strip()]


def riassunto(reperti: list[dict], disposizioni: list[dict], da: date) -> str:
    """Quanti reperti, quanti giudicati, e con che esito, dalla data in poi."""
    recenti = [r for r in reperti if r["giorno"] >= da.isoformat()]
    giudizi = {(d["giorno"], d["id"]): d["esito"] for d in disposizioni}
    esiti = Counter(giudizi.get((r["giorno"], r["id"]), "non_disposto") for r in recenti)
    confermati = esiti["confermato"]
    disposti = sum(v for k, v in esiti.items() if k != "non_disposto")
    precisione = f"{confermati / disposti:.0%}" if disposti else "n/d"
    return "\n".join(
        [
            f"Dal {da.isoformat()}: {len(recenti)} reperti, {disposti} disposti.",
            "  " + ", ".join(f"{k}={v}" for k, v in sorted(esiti.items())),
            f"  precisione sui disposti: {precisione}",
            (
                "  ATTENZIONE: zero confermati — se la finestra e' di due settimane piene, "
                "la clausola di uscita dice di spegnere il job."
                if disposti and not confermati
                else ""
            ),
        ]
    ).rstrip()


def main() -> int:
    """Registra la disposizione di un reperto, o stampa il riassunto."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=Path("logs/triage"))
    parser.add_argument("--giorno")
    parser.add_argument("--id", dest="identificativo")
    parser.add_argument("--esito", choices=ESITI)
    parser.add_argument("--nota", default="")
    parser.add_argument("--riassunto", action="store_true")
    parser.add_argument("--finestra-giorni", type=int, default=14)
    args = parser.parse_args()

    reperti = carica(args.dir / "reperti.jsonl")
    disposizioni_path = args.dir / "disposizioni.jsonl"
    disposizioni = carica(disposizioni_path)

    if args.riassunto:
        print(riassunto(reperti, disposizioni, date.today() - timedelta(days=args.finestra_giorni)))
        return 0

    if not (args.giorno and args.identificativo and args.esito):
        parser.error("servono --giorno, --id e --esito (oppure --riassunto)")
    noti = {(r["giorno"], r["id"]) for r in reperti}
    if (args.giorno, args.identificativo) not in noti:
        parser.error(f"reperto {args.identificativo} del {args.giorno} inesistente")
    with disposizioni_path.open("a") as fh:
        fh.write(
            json.dumps(
                {
                    "giorno": args.giorno,
                    "id": args.identificativo,
                    "esito": args.esito,
                    "nota": args.nota,
                    "disposto_il": datetime.now(timezone.utc).isoformat(),
                }
            )
            + "\n"
        )
    print(f"{args.identificativo} del {args.giorno}: {args.esito}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
