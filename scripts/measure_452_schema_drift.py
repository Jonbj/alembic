#!/usr/bin/env python3
"""Tasso di deriva sull'enum di directness/event_type/risk_flags (#452).

Sola lettura su `llm_responses`. Il rilevatore (`src.analysis.schema_drift`)
confronta ogni valore contro l'insieme esatto dichiarato nel prompt — non
normalizza maiuscole/minuscole ne' spazi, perche' proprio i refusi e i
caratteri invisibili sono la deriva che #452 vuole misurare.

Non esiste, ad oggi, un contatore persistito del "parse fail" per la coppia
LIVE (`llm_responses` contiene solo le chiamate riuscite per costruzione):
un fallimento totale di parsing/validazione viene solo loggato
(`run_ensemble_query`, `log.warning`) e non sopravvive al riavvio del
container. Questo script misura quindi la deriva sull'ENUM (il segnale
disponibile e persistito), non il tasso di parse-fail totale — vedi il
campo `nota_parse_fail` nell'evidenza.

Uso:
    export DATABASE_URL=postgresql://trading:trading@localhost:5432/trading
    python scripts/measure_452_schema_drift.py [--since 2026-08-26]
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src.analysis.schema_drift import aggrega_deriva

_PERCORSO_EVIDENZA = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "ollama_schema_drift_452.json"

_QUERY = """
    SELECT model_id, directness, event_type, risk_flags, generated_at
    FROM llm_responses
    WHERE generated_at >= %s
"""


def _connetti():
    import psycopg2

    from src.config import config

    return psycopg2.connect(config.DATABASE_URL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--since",
        default="2026-08-26",
        help="Inizio della finestra (default 2026-08-26, prima comparsa nota della deriva).",
    )
    args = parser.parse_args()

    with _connetti() as conn:
        with conn.cursor() as cur:
            cur.execute(_QUERY, (args.since,))
            righe_raw = cur.fetchall()

    righe = [
        {"model_id": model_id, "directness": directness, "event_type": event_type, "risk_flags": risk_flags}
        for model_id, directness, event_type, risk_flags, _generated_at in righe_raw
    ]

    sintesi = aggrega_deriva(righe)
    per_modello = {}
    for model_id in sorted({r["model_id"] for r in righe}):
        per_modello[model_id] = aggrega_deriva(r for r in righe if r["model_id"] == model_id)

    evidenza = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "issue": "#452",
        "finestra": {"since": args.since},
        "metodo": (
            "confronto esatto (case-sensitive, nessuna normalizzazione) contro "
            "l'insieme di valori dichiarato nel prompt DK-CoT per directness, "
            "event_type e risk_flags; una riga senza nessuno dei tre campi "
            "arricchiti e' fuori campione, non conta ne' come deriva ne' come "
            "pulita."
        ),
        "nota_parse_fail": (
            "llm_responses contiene solo le chiamate riuscite per costruzione "
            "(un fallimento totale di parsing/validazione non viene mai "
            "persistito, solo loggato in run_ensemble_query e non sopravvive "
            "al riavvio del container). Questa evidenza misura la deriva "
            "sull'enum tra le chiamate riuscite, non il tasso di parse-fail "
            "totale della coppia live."
        ),
        "sintesi": sintesi,
        "per_modello": per_modello,
    }

    _PERCORSO_EVIDENZA.parent.mkdir(parents=True, exist_ok=True)
    _PERCORSO_EVIDENZA.write_text(json.dumps(evidenza, indent=2, ensure_ascii=False))
    print(
        f"Scritto {_PERCORSO_EVIDENZA} — campione {sintesi['n_campione']}, "
        f"righe in deriva {sintesi['riga_in_deriva']['n']} "
        f"({sintesi['riga_in_deriva']['tasso']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
