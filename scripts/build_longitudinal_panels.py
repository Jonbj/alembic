#!/usr/bin/env python3
"""Costruisce i pannelli longitudinali e l'occurrence ledger (#282) dai dossier
deterministici gia' scritti da ``scripts/alpha_miner_dossier.py``.

Orchestratore SOTTILE: fa solo I/O in LETTURA sui file di evidenza
(``docs/evidence/dossier/*.json``, ``docs/evidence/findings.json``,
``docs/evidence/market_daily.jsonl``) e delega ogni calcolo ai moduli puri in
``src/analysis/dossier/panels.py`` e ``.../ledger_validator.py``. Nessuna formula
vive qui.

Perche' esiste: il ledger corrente (``findings.json``) mescola definizione e
occorrenza e puo' duplicare lo stesso evento fra report. Questo script produce
pannelli PARALLELI (una riga per unita' osservativa, ``causal_event_id``
deterministico anti-doppio-conteggio) e li valida, SENZA riscrivere
``findings.json``: quest'ultimo e' letto in sola lettura per la vista
``definitions``. L'output e' un file derivato e rigenerabile
(``docs/evidence/longitudinal_panels.json``): NON e' evidenza primaria, e' uno
strumento di misura sullaEvidence primaria gia' congelata.

Compatibile con il freeze #171: e' strumentazione/misura, nessuna taratura
toccata. L'attribuzione del costo di un evento a un finding strutturale
(``primary_finding``) resta null: e' giudizio dell'LLM/operatore, da cablare nel
prompt del cron a freeze concluso (fuori perimetro).

Uso:
    uv run python scripts/build_longitudinal_panels.py
    uv run python scripts/build_longitudinal_panels.py --no-write   # solo validazione a stdout
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
from pathlib import Path

from src.analysis.dossier.ledger_validator import validate_findings, validate_panels
from src.analysis.dossier.panels import (
    LEDGER_SCHEMA_VERSION,
    PANELS_SCHEMA_VERSION,
    build_decision_trade_panel,
    build_definitions,
    build_derived_views,
    build_occurrence_ledger,
    build_signal_panel,
    build_status_events,
    build_ticker_day_panel,
)

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DOSSIER_DIR = PROJECT_DIR / "docs" / "evidence" / "dossier"
FINDINGS = PROJECT_DIR / "docs" / "evidence" / "findings.json"
MARKET_DAILY = PROJECT_DIR / "docs" / "evidence" / "market_daily.jsonl"
OUT = PROJECT_DIR / "docs" / "evidence" / "longitudinal_panels.json"

# Fine del periodo di osservazione dichiarata nella carta (#171): non e' una
# taratura, e' una data documentata. L'inizio si deriva dai dati (include le
# osservazioni pre-start del 2026-07-31, legittime).
FINESTRA_FINE = dt.date(2026, 9, 28)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _movers_from_dossier(dossier: dict) -> dict[str, float]:
    """Movers che sono candidati miss (non detenuti): il pannello ticker-day
    copre esattamente questi, per cui il check di completeness li confronta con
    loro e non con i movers detenuti."""
    return {
        c["symbol"]: float(c.get("return") or 0.0)
        for c in dossier.get("candidati_miss") or []
        if c.get("symbol")
    }


def costruisci() -> dict:
    """Legge i dossier, costruisce pannelli + ledger, valida, restituisce il
    report completo (dict) e l'esito della validazione."""
    dossier_paths = sorted(DOSSIER_DIR.glob("*.json"))
    if not dossier_paths:
        raise SystemExit(f"Nessun dossier in {DOSSIER_DIR}.")

    dossier_hashes: dict[str, str] = {}
    ticker_day_all: list[dict] = []
    signal_all: list[dict] = []
    decision_all: list[dict] = []
    ledger_all: list[dict] = []
    panels_by_day: dict[str, list[dict]] = {}
    occ_by_day: dict[str, list[dict]] = {}
    dossier_movers: dict[str, dict[str, float]] = {}
    giorni: list[str] = []

    for path in dossier_paths:
        dossier = _load_json(path)
        data = dossier["data"]
        h = _sha256(path)
        dossier_hashes[data] = h
        giorni.append(data)

        td = build_ticker_day_panel(dossier, dossier_hash=h)
        sp = build_signal_panel(dossier, dossier_hash=h)
        dp = build_decision_trade_panel(dossier, dossier_hash=h)
        occ = build_occurrence_ledger(dossier, dossier_hash=h)

        ticker_day_all.extend(td)
        signal_all.extend(sp)
        decision_all.extend(dp)
        ledger_all.extend(occ)
        panels_by_day[data] = td
        occ_by_day[data] = occ
        dossier_movers[data] = _movers_from_dossier(dossier)

    # il ledger e' append-only: ordina per (data, causal_event_id) per costruzione.
    ledger_all.sort(key=lambda o: (o["data"], o["causal_event_id"]))

    findings = _load_json(FINDINGS) if FINDINGS.exists() else {"findings": []}
    definitions = build_definitions(findings)
    status_events = build_status_events(findings)
    derived = build_derived_views(panels_by_day, occ_by_day)

    # Finestra: inizio derivato dai dati (include le osservazioni pre-start del
    # 2026-07-31), fine = fine periodo dichiarata.
    inizio = min(dt.date.fromisoformat(g) for g in giorni)
    # allarga l'inizio alle occorrenze di findings (possono precedere i dossier).
    for fd in findings.get("findings") or []:
        pa = fd.get("primo_avvistamento")
        if pa:
            inizio = min(inizio, dt.date.fromisoformat(pa))
    window = (inizio, FINESTRA_FINE)

    validation_findings = validate_findings(findings, window=window)
    validation_panels = validate_panels(
        {
            "occurrences": ledger_all,
            "definitions": definitions,
            "ticker_day": ticker_day_all,
        },
        dossier_hashes=dossier_hashes,
        window=window,
        dossier_movers=dossier_movers,
    )
    validation = {
        "ok": not (validation_findings["errors"] or validation_panels["errors"]),
        "errors": validation_findings["errors"] + validation_panels["errors"],
        "warnings": validation_findings["warnings"] + validation_panels["warnings"],
    }

    report = {
        "schema_version": PANELS_SCHEMA_VERSION,
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "generato_il": dt.datetime.now(dt.timezone.utc).isoformat(),
        "finestra": {"inizio": inizio.isoformat(), "fine": FINESTRA_FINE.isoformat()},
        "n_giorni": len(giorni),
        "giorni": giorni,
        "definitions": definitions,
        "status_events": status_events,
        "ticker_day": ticker_day_all,
        "signals": signal_all,
        "decisions_trades": decision_all,
        "occurrences": ledger_all,
        "derived_views": derived,
        "dossier_hashes": dossier_hashes,
        "validation": validation,
        "provenance": {
            "dossier": "docs/evidence/dossier/*.json (read-only, hash sha256)",
            "findings": "docs/evidence/findings.json (read-only, vista definitions)",
            "note": (
                "File derivato e rigenerabile, NON evidenza primaria. "
                "primary_finding resta null: attribuzione ad F-NNN e' dell'LLM/"
                "operatore (wiring post-freeze). findings.json non e' stato "
                "modificato."
            ),
        },
    }
    return report


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--no-write",
        action="store_true",
        help="non scrivere il file, solo validazione a stdout",
    )
    ap.add_argument("--out", default=str(OUT), help="percorso del file di output")
    args = ap.parse_args()

    report = costruisci()
    v = report["validation"]
    log.info(
        "giorni: %d | ticker-day %d | segnali %d | decisioni/trade %d | occorrenze %d",
        report["n_giorni"],
        len(report["ticker_day"]),
        len(report["signals"]),
        len(report["decisions_trades"]),
        len(report["occurrences"]),
    )
    log.info(
        "definitions %d | per_causa %s",
        len(report["definitions"]),
        report["derived_views"]["per_causa"],
    )
    if v["errors"]:
        log.error("VALIDAZIONE FALLITA (%d errori):", len(v["errors"]))
        for e in v["errors"]:
            log.error("  - %s", e)
    else:
        log.info("VALIDAZIONE OK (0 errori, %d warning)", len(v["warnings"]))
    for w in v["warnings"]:
        log.warning("  - %s", w)

    if not args.no_write:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(out)  # atomica
        log.info("scritto: %s", out)
    return 1 if v["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
