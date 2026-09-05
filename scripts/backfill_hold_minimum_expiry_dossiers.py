#!/usr/bin/env python3
"""Aggiunge la misura #430 ai dossier esistenti senza rigenerarli.

Il backfill e' intenzionalmente locale e idempotente: conserva versione schema,
timestamp di generazione e ogni misura gia' pubblicata. I nuovi dossier ricevono
gli stessi campi direttamente da ``alpha_miner_dossier.py``.

Uso:
    python scripts/backfill_hold_minimum_expiry_dossiers.py
"""
from __future__ import annotations

import argparse
import copy
import json
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from src.analysis.dossier.book import aggregate_holding_time_histogram
from src.portfolio.exit_classification import reason_for_hold_minimum_expiry

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DOSSIER_DIR = PROJECT_DIR / "docs" / "evidence" / "dossier"
INIZIO_OSSERVAZIONE = date(2026, 8, 3)

PROVENIENZA = {
    "source": "trades.exit_time - trades.entry_time",
    "bucket": "multiplo nominale piu' vicino, ampiezza 15 minuti",
    "reason_code": (
        "hold_minimum_expiry per portfolio_sell al primo ciclo nominale "
        "successivo al hold di 90 minuti"
    ),
    "freeze": "misura read-only; nessuna logica di uscita modificata",
}


def backfill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Restituisci una copia arricchita, senza riscrivere misure preesistenti."""
    result = copy.deepcopy(payload)
    exits = result.get("chiusure") or []
    for exit_ in exits:
        exit_["exit_reason"] = reason_for_hold_minimum_expiry(
            exit_.get("exit_reason", ""),
            float(exit_["ore_tenuta"]) * 3600,
            hold_minimum_minutes=90,
        )
    result.setdefault("provenienza_dati", {})["ore_tenuta_s4"] = dict(PROVENIENZA)
    result.setdefault("aggregati", {})["ore_tenuta_s4"] = (
        aggregate_holding_time_histogram(exits)
    )
    return result


def _dossier_paths(directory: Path, start: date) -> list[Path]:
    paths = []
    for path in sorted(directory.glob("2026-??-??.json")):
        if date.fromisoformat(path.stem) >= start:
            paths.append(path)
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DOSSIER_DIR)
    parser.add_argument("--da", dest="start", type=date.fromisoformat,
                        default=INIZIO_OSSERVAZIONE)
    args = parser.parse_args(argv)

    n_files = 0
    n_expiry = 0
    pnl_expiry = 0.0
    for path in _dossier_paths(args.directory, args.start):
        payload = json.loads(path.read_text())
        enriched = backfill_payload(payload)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(enriched, indent=2, ensure_ascii=False))
        tmp.replace(path)
        n_files += 1
        expiry_rows = [
            row for row in enriched.get("chiusure", [])
            if row.get("strategia") == "S4"
            and row.get("exit_reason") == "hold_minimum_expiry"
        ]
        n_expiry += len(expiry_rows)
        pnl_expiry += sum(float(row["pnl_net"]) for row in expiry_rows)

    print(
        f"dossier aggiornati: {n_files}; "
        f"uscite S4 hold_minimum_expiry: {n_expiry}; "
        f"pnl_net: {pnl_expiry:.2f}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
