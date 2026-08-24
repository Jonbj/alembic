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
from src.analysis.dossier.decision_quality import (
    build_decision_quality_panel,
    build_decision_quality_rollup,
)
from src.analysis.dossier.falsifiability import (
    FALSIFIABILITY_SCHEMA_VERSION,
    build_contamination_summary,
    build_falsifiability_views,
    build_status_events_falsifiability,
    build_synthesis,
    build_weekly_rollup,
    validate_falsifiability,
)
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
# Annotazioni parallele dell'operatore per i campi di giudizio di #286
# (stato_falsificazione, prova_decisiva, meccanismo, strategia,
# relazione_finding_causa, contamination). File OPZIONALE e nuovo: non e' tra
# i vietati e non e' il ledger primario. Default vuoto => tutti i campi di
# giudizio nulli e stato not_exposed (struttura pronta, wiring prompt post-freeze).
#
# Schema atteso (due forme accettate, entrambe indicizzate per finding_id):
#   {"F-001": {"stato_falsificazione": "supported",
#              "prova_decisiva": "test X conferma (read-only)",
#              "meccanismo": "NO_NEWS", "strategia": "S4",
#              "relazione_finding_causa": "NO_NEWS",
#              "contamination": "attribution"}}
# oppure {"findings": [{"id": "F-001", ...}, ...]}.
# stato_falsificazione in {supported, contradicted, not_exposed} (default
# not_exposed). prova_decisiva obbligatoria con un verdetto e read-only una
# volta registrata.
ANNOTATIONS = PROJECT_DIR / "docs" / "evidence" / "finding_annotations.json"
# P&L economico (#278): file derivato read-only, fonte della headline del
# synthesis. Opzionale: se assente la headline e' None con missingness.
ECONOMIC_PNL = PROJECT_DIR / "docs" / "evidence" / "economic_pnl.json"

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


def _segments_by_day(ticker_day: list[dict]) -> dict[str, set[str]]:
    """Segmenti (cause) presenti per giorno, dal pannello ticker-day. Serve ai
    denominatori di esposizione di #286 (giorni_esposti / non_occorrenze) quando
    e' nota la relazione finding->causa."""
    out: dict[str, set[str]] = {}
    for row in ticker_day:
        day = row.get("data")
        seg = row.get("segment")
        if day is None or seg is None:
            continue
        out.setdefault(day, set()).add(seg)
    return out


def _load_economic_pnl() -> dict | None:
    """Carica il file derivato del P&L economico (#278), read-only. None se
    assente o non leggibile (missingness dichiarata a valle)."""
    if not ECONOMIC_PNL.exists():
        return None
    try:
        return _load_json(ECONOMIC_PNL)
    except (OSError, ValueError):
        return None


def _economic_pnl_headline(epnl: dict | None) -> dict | None:
    """Headline del P&L economico per il synthesis: ultimo cumulato per sleeve
    (S1 / S4 / BOOK) sulla finestra. File derivato read-only."""
    if not epnl:
        return None
    cumulato = (epnl.get("pnl_economico") or {}).get("cumulato") or {}
    headline: dict[str, float | None] = {}
    for sleeve in ("S1", "S4", "BOOK"):
        serie = cumulato.get(sleeve)
        if not serie:
            headline[sleeve] = None
            continue
        # ultimo valore della serie (chiave data ordinata).
        headline[sleeve] = sorted(serie.items())[-1][1]
    headline["finestra_inizio"] = epnl.get("finestra_inizio")
    headline["fonte"] = str(ECONOMIC_PNL.relative_to(PROJECT_DIR))
    headline["missingness"] = [] if any(
        v is not None for k, v in headline.items() if k in ("S1", "S4", "BOOK")
    ) else ["economic_pnl_non_disponibile"]
    return headline


def _economic_pnl_for_window(epnl: dict | None, start: dt.date, end: dt.date) -> dict | None:
    """P&L economico di una sotto-finestra (somma del giornaliero sui giorni di
    borsa presenti in [start, end]). Per il weekly rollup: il contributo
    economico di quella settimana, non il cumulato totale."""
    if not epnl:
        return None
    giornaliero = (epnl.get("pnl_economico") or {}).get("giornaliero") or {}
    out: dict[str, float | None] = {}
    any_value = False
    for sleeve in ("S1", "S4", "BOOK"):
        serie = giornaliero.get(sleeve) or {}
        totale = 0.0
        found = False
        for day_str, val in serie.items():
            try:
                day = dt.date.fromisoformat(day_str)
            except ValueError:
                continue
            if start <= day <= end and val is not None:
                totale += float(val)
                found = True
        out[sleeve] = totale if found else None
        any_value = any_value or found
    out["finestra"] = f"{start.isoformat()}..{end.isoformat()}"
    out["fonte"] = str(ECONOMIC_PNL.relative_to(PROJECT_DIR))
    out["missingness"] = [] if any_value else ["economic_pnl_non_disponibile_nella_sotto_finestra"]
    return out


def _iso_week(day_str: str) -> str:
    """Etichetta ISO week (es. ``2026-W33``) per il weekly rollup."""
    cal = dt.date.fromisoformat(day_str).isocalendar()
    return f"{cal[0]}-W{cal[1]:02d}"


def _week_window(week_label: str) -> tuple[dt.date, dt.date]:
    """Finestra (lunedi'->domenica) di una ISO week label ``YYYY-Www``."""
    year, week = week_label.split("-W")
    # lunedi' della ISO week
    monday = dt.date.fromisocalendar(int(year), int(week), 1)
    sunday = dt.date.fromisocalendar(int(year), int(week), 7)
    return monday, sunday


def costruisci(*, previous_report: dict | None = None) -> dict:
    """Legge i dossier, costruisce pannelli + ledger, valida, restituisce il
    report completo (dict) e l'esito della validazione.

    ``previous_report`` e' l'output della run precedente (lo stesso file
    derivato): fonte dei ``cambi`` del synthesis e della baseline read-only
    della prova decisiva. E' iniettato da ``main()`` che lo legge da ``OUT``;
    qui' resta un parametro esplicito cosi' ``costruisci()`` e' deterministica
    e testabile senza dipendere da file su disco. Default ``None`` => primo run:
    tutto nuovo, nessun vincolo read-only."""
    dossier_paths = sorted(DOSSIER_DIR.glob("*.json"))
    if not dossier_paths:
        raise SystemExit(f"Nessun dossier in {DOSSIER_DIR}.")

    dossier_hashes: dict[str, str] = {}
    ticker_day_all: list[dict] = []
    signal_all: list[dict] = []
    decision_all: list[dict] = []
    ledger_all: list[dict] = []
    decision_quality_all: list[dict] = []
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
        dq = build_decision_quality_panel(dossier, dossier_hash=h)

        ticker_day_all.extend(td)
        signal_all.extend(sp)
        decision_all.extend(dp)
        ledger_all.extend(occ)
        decision_quality_all.append(dq)
        panels_by_day[data] = td
        occ_by_day[data] = occ
        dossier_movers[data] = _movers_from_dossier(dossier)

    # il ledger e' append-only: ordina per (data, causal_event_id) per costruzione.
    ledger_all.sort(key=lambda o: (o["data"], o["causal_event_id"]))

    findings = _load_json(FINDINGS) if FINDINGS.exists() else {"findings": []}
    definitions = build_definitions(findings)
    status_events = build_status_events(findings)
    derived = build_derived_views(panels_by_day, occ_by_day)
    decision_quality_rollup = build_decision_quality_rollup(decision_quality_all)

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

    # --- #286: falsificabilita' e sintesi (viste parallele, read-only su
    # findings.json). Annotazioni opzionali dell'operatore; previous_report per
    # i cambi e per il check read-only della prova decisiva. ---
    annotations = _load_json(ANNOTATIONS) if ANNOTATIONS.exists() else {}
    # assicura che le annotazioni siano indicizzate per finding_id.
    if annotations and "findings" in annotations:
        annotations = {f.get("id"): f for f in annotations["findings"] if f.get("id")}
    segments_day = _segments_by_day(ticker_day_all)

    # run precedente (lo stesso file derivato, iniettato da main): fonte dei
    # cambi e della prova decisiva read-only. Su primo run e' None => tutto
    # nuovo, niente vincoli.
    previous_fals = (previous_report or {}).get("falsifiability") or None
    previous_annotations = None
    if previous_fals and previous_fals.get("annotations_used"):
        previous_annotations = previous_fals["annotations_used"]

    fals_views = build_falsifiability_views(
        findings,
        window=window,
        annotations=annotations,
        segments_by_day=segments_day,
    )
    contamination_summary = build_contamination_summary(fals_views)
    fals_status_events = build_status_events_falsifiability(fals_views)
    validation_fals = validate_falsifiability(
        fals_views,
        annotations=annotations,
        previous_annotations=previous_annotations,
    )

    epnl = _load_economic_pnl()
    economic_headline = _economic_pnl_headline(epnl)
    integrity = {
        "ok": validation["ok"] and validation_fals["ok"],
        "n_errori": len(validation["errors"]) + len(validation_fals["errors"]),
        "n_warning": len(validation["warnings"]) + len(validation_fals["warnings"]),
        "errori": validation["errors"] + validation_fals["errors"],
        "warning": validation["warnings"] + validation_fals["warnings"],
    }
    synthesis = build_synthesis(
        fals_views,
        contamination_summary,
        # previous_digest = le VISTE della run precedente (hanno ``findings``
        # top-level, dove ``_cambi`` li legge). Non il blocco ``falsifiability``
        # intero: quello ha ``views`` annidate, e ``_cambi`` non le troverebbe.
        previous_digest=(previous_fals or {}).get("views"),
        economic_pnl=economic_headline,
        integrity=integrity,
    )

    # weekly rollup: per ogni ISO week con dossier, i "cambi della settimana"
    # sono la DIFF CUMULATIVA (viste a fine settimana meno viste a inizio
    # settimana): cio' che e' mutato durante la settimana, non il rumore di un
    # finding dormiente che resetta a zero. Una settimana senza variazioni vs
    # l'inizio produce cambi vuoti: e' il punto (nessuna nuova evidenza).
    weekly: dict[str, dict] = {}
    for week_label in sorted({_iso_week(g) for g in giorni}):
        w_start, w_end = _week_window(week_label)
        # vista cumulativa a fine settimana (inizio finestra..domenica).
        w_views = build_falsifiability_views(
            findings,
            window=(inizio, w_end),
            annotations=annotations,
            segments_by_day=segments_day,
        )
        # vista cumulativa a inizio settimana (inizio..giorno prima del
        # lunedi'): la baseline rispetto a cui misurare i cambi della settimana.
        prev_sunday = w_start - dt.timedelta(days=1)
        if prev_sunday >= inizio:
            prev_week_views = build_falsifiability_views(
                findings,
                window=(inizio, prev_sunday),
                annotations=annotations,
                segments_by_day=segments_day,
            )
        else:
            prev_week_views = None
        w_cont = build_contamination_summary(w_views)
        w_pnl = _economic_pnl_for_window(epnl, w_start, w_end)
        weekly[week_label] = build_weekly_rollup(
            w_views,
            w_cont,
            settimana=week_label,
            previous_digest=prev_week_views,
            economic_pnl=w_pnl,
            integrity=integrity,
        )

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
        "decision_quality": decision_quality_all,
        "decision_quality_rollup": decision_quality_rollup,
        "derived_views": derived,
        "dossier_hashes": dossier_hashes,
        "validation": validation,
        "falsifiability": {
            "schema_version": FALSIFIABILITY_SCHEMA_VERSION,
            "views": fals_views,
            "contamination_summary": contamination_summary,
            "status_events": fals_status_events,
            "validation": validation_fals,
            "synthesis": synthesis,
            "weekly_rollup": weekly,
            # annotazioni usate questa run: registra la baseline per il check
            # read-only della prova decisiva alla prossima run.
            "annotations_used": annotations,
            "provenance": {
                "findings": "docs/evidence/findings.json (read-only)",
                "annotations": (
                    f"{ANNOTATIONS.relative_to(PROJECT_DIR)} (operatore, opzionale)"
                    if ANNOTATIONS.exists()
                    else "assente (tutti i campi di giudizio nulli, stato not_exposed)"
                ),
                "economic_pnl": (
                    f"{ECONOMIC_PNL.relative_to(PROJECT_DIR)} (read-only, headline)"
                    if economic_headline is not None
                    else "assente (headline None, missingness dichiarata)"
                ),
                "note": (
                    "Viste parallele di falsificabilita' (#286): nessuna modifica "
                    "a findings.json. I campi di giudizio (stato_falsificazione, "
                    "prova_decisiva, meccanismo, strategia, relazione_finding_causa, "
                    "contamination) vivono nelle annotazioni dell'operatore e "
                    "restano null/not_exposed finche' il prompt cron non le "
                    "popola (wiring post-freeze)."
                ),
            },
        },
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

    # run precedente (lo stesso file derivato): fonte dei cambi del synthesis
    # (#286) e della baseline read-only della prova decisiva. Iniettato in
    # costruisci() per mantenerla deterministica e testabile.
    out_path = Path(args.out)
    previous_report = _load_json(out_path) if out_path.exists() else None

    report = costruisci(previous_report=previous_report)
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
