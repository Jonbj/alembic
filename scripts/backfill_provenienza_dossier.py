#!/usr/bin/env python3
"""Backfill della provenienza per riga scorata nei dossier gia' scritti (#244).

I dossier dal 2026-08-03 in poi hanno `candidati_miss[].segnali[]` con solo
{ora, score, fallback}: la partizione di THIN_NEUTRAL nei tre bucket di #244
non e' decidibile su quel dato. Questo script rilegge da Postgres, per ogni
riga gia' persistita, i tre campi che #244 aggiunge:

    extraction_method  — provenienza (org_lookup | gdelt_doc | source_metadata)
    testo_scorato      — il titolo dell'articolo
    n_ticker_articolo  — fan-out: quanti ticker condividono quell'articolo

e li scrive accanto ai campi esistenti, ricalcolando poi `causa`,
`quota_righe_fanout` e il blocco `aggregati.cause_del_giorno`.

Perche' un backfill dedicato invece di `alpha_miner_dossier.py --backfill-da`:
rigenerare i dossier li ricalcola TUTTI da capo, inclusi i blocchi che
dipendono da prezzi e da Redis (`soglia_gate_usata`, `opportunity_v2`), il cui
valore odierno non e' quello del giorno osservato. La carta di osservazione
(#171) vieta di riscrivere retroattivamente le evidenze gia' lette: qui si
AGGIUNGONO campi e si ricalcola solo cio' che dipende da essi.

La soglia del gate NON viene rilleta: si riusa `soglia_gate_usata` gia'
persistita nel dossier, che e' il valore effettivamente in vigore quel giorno
(#191/#208). Nessuna taratura, nessuna soglia nuova — freeze #171.

Uso:
    uv run python scripts/backfill_provenienza_dossier.py --dry-run
    uv run python scripts/backfill_provenienza_dossier.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.dossier.miss_cause import (  # noqa: E402
    DEFAULT_SOGLIA_GATE,
    cause_del_giorno,
    classify_miss_candidates,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DOSSIER_DIR = PROJECT_DIR / "docs" / "evidence" / "dossier"


def _psql(query: str) -> list[list[str]]:
    """Query read-only su Postgres. Righe come liste di stringhe."""
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", query],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:300]}")
    return [r.split("|") for r in res.stdout.strip().split("\n") if r.strip()]


def provenienza_del_giorno(g: str) -> dict[tuple[str, str], dict]:
    """Provenienza per (symbol, ora) di tutte le righe scorate del giorno.

    La chiave e' (symbol, 'HH:MM'): `unique_signal_per_symbol_time` garantisce
    che (symbol, generated_at) sia unico, quindi al minuto la collisione e'
    possibile ma rara. In caso di collisione vince l'ultima riga: il backfill
    e' una misura aggregata, non un audit riga-per-riga.
    """
    out: dict[tuple[str, str], dict] = {}
    for r in _psql(
        f"SELECT ss.symbol, to_char(ss.generated_at,'HH24:MI'), "
        f"COALESCE(nl.extraction_method,''), "
        f"translate(COALESCE(nl.title,''), '|' || chr(10) || chr(13), '   '), "
        f"CASE WHEN COALESCE(nl.url,'') = '' THEN '' ELSE "
        f"  (SELECT count(*)::text FROM news_log n2 WHERE n2.url = nl.url) END "
        f"FROM sentiment_signals ss LEFT JOIN news_log nl ON nl.id = ss.news_log_id "
        f"WHERE ss.generated_at >= '{g}' AND ss.generated_at < '{g}'::date + 1 "
        f"ORDER BY ss.generated_at;"
    ):
        campi: dict = {}
        if r[2]:
            campi["extraction_method"] = r[2]
        if r[3]:
            campi["testo_scorato"] = r[3]
        if r[4]:
            campi["n_ticker_articolo"] = int(r[4])
        if campi:
            out[(r[0], r[1])] = campi
    return out


def backfill_file(path: Path, dry_run: bool) -> dict:
    giorno = path.stem
    dossier = json.loads(path.read_text())
    provenienza = provenienza_del_giorno(giorno)

    candidati = dossier.get("candidati_miss") or []
    righe_totali = righe_arricchite = 0
    for cand in candidati:
        for seg in cand.get("segnali") or []:
            righe_totali += 1
            campi = provenienza.get((cand.get("symbol", ""), seg.get("ora", "")))
            if campi:
                seg.update(campi)
                righe_arricchite += 1

    cause_prima = {}
    for c in candidati:
        cause_prima[c.get("symbol", "")] = c.get("causa")

    # Il gate e' quello gia' persistito per quel giorno: non si rilegge Redis.
    soglia_gate = float(dossier.get("soglia_gate_usata") or DEFAULT_SOGLIA_GATE)
    riclassificati = classify_miss_candidates(candidati, soglia_gate=soglia_gate)
    # `classify_miss_candidates` restituisce copie: reinnesta i campi calcolati
    # nei candidati originali, per non perdere l'ordine ne' i blocchi (come
    # `opportunity_v2`) che questo script non deve toccare.
    for originale, nuovo in zip(candidati, riclassificati):
        originale["causa"] = nuovo["causa"]
        originale["quota_righe_fanout"] = nuovo["quota_righe_fanout"]

    if "aggregati" in dossier and isinstance(dossier["aggregati"], dict):
        if "cause_del_giorno" in dossier["aggregati"]:
            blocco = cause_del_giorno(candidati)
            # La soglia gate del blocco e' quella del giorno, non il default.
            blocco["soglie"]["gate"] = soglia_gate
            dossier["aggregati"]["cause_del_giorno"] = blocco

    cambi = {
        s: (cause_prima[s], c.get("causa"))
        for s, c in ((c.get("symbol", ""), c) for c in candidati)
        if cause_prima.get(s) != c.get("causa")
    }

    if not dry_run:
        # Stessa serializzazione di alpha_miner_dossier.py:790 (nessun newline
        # finale), cosi' la diff mostra solo i campi aggiunti.
        path.write_text(json.dumps(dossier, indent=2, ensure_ascii=False))

    return {
        "giorno": giorno,
        "righe_totali": righe_totali,
        "righe_arricchite": righe_arricchite,
        "cambi_causa": cambi,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="stampa cosa cambierebbe senza riscrivere i file")
    args = ap.parse_args()

    files = sorted(DOSSIER_DIR.glob("*.json"))
    if not files:
        raise SystemExit(f"Nessun dossier in {DOSSIER_DIR}")

    tot_righe = tot_arricchite = 0
    print(f"{'giorno':12} {'righe':>6} {'con provenienza':>16}  cambi di causa")
    print("-" * 72)
    for path in files:
        r = backfill_file(path, args.dry_run)
        tot_righe += r["righe_totali"]
        tot_arricchite += r["righe_arricchite"]
        cambi = ", ".join(f"{s}: {a}->{b}" for s, (a, b) in r["cambi_causa"].items())
        print(f"{r['giorno']:12} {r['righe_totali']:6d} {r['righe_arricchite']:16d}  {cambi or '-'}")

    print("-" * 72)
    quota = tot_arricchite / tot_righe if tot_righe else 0.0
    print(f"{'TOTALE':12} {tot_righe:6d} {tot_arricchite:16d}  ({quota:.1%} delle righe)")
    if args.dry_run:
        print("\n[dry-run] nessun file riscritto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
