"""Validator del ledger delle evidenze e dei pannelli longitudinali (#282).

Criteri di accettazione della issue: il validator controlla ID, somme,
date/finestra, duplicati, append-only, dossier hash e completeness. Puro:
riceve dict, restituisce ``{"ok": bool, "errors": [...], "warnings": [...]}``.

Due ambiti, entrambi coperti:
    ``validate_findings`` — integrita' strutturale di ``findings.json`` (ID
        F-NNN conformi e non riusati, costo_cumulato == somma occorrenze,
        date dentro la finestra e coerenti con primo_avvistamento).
    ``validate_panels``   — integrita' dei pannelli longitudinali nuovi
        (causal_event_id conforme e univoco, data coerente con l'id,
        primary_finding esistente e senza doppio conteggio per (data, ticker),
        dossier_hash corrispondente al file reale, append-only, completeness
        per giornata e per mover).
    ``validate_ledger``   — orchestra i due e fonde gli errori.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict

ID_PATTERN = re.compile(r"^F-\d{3}$")
# kind ammessi per causal_event_id; il payload e' kind-specifico.
CAUSAL_KINDS = frozenset({"miss", "trade", "decision", "entry", "exit", "signal"})
CAUSAL_ID_PATTERN = re.compile(r"^(?P<kind>miss|trade|decision|entry|exit|signal):[A-Za-z0-9._:\-]+$")
# kind che incorporano la data come secondo token (per il check di coerenza).
DATE_EMBEDDING_KINDS = frozenset({"miss", "entry", "exit"})


def _result() -> dict:
    return {"ok": True, "errors": [], "warnings": []}


def _fail(res: dict, msg: str) -> None:
    res["errors"].append(msg)


def _warn(res: dict, msg: str) -> None:
    res["warnings"].append(msg)


def _parse_date(value) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def validate_findings(findings: dict, *, window: tuple[dt.date, dt.date] | None = None) -> dict:
    """Controlla ID, somme, date/finestra, duplicati di ``findings.json``."""
    res = _result()
    seen_ids: set[str] = set()
    win_start, win_end = window or (None, None)
    for finding in findings.get("findings") or []:
        fid = finding.get("id")
        if not isinstance(fid, str) or not ID_PATTERN.match(fid):
            _fail(res, f"id non conforme (atteso F-NNN): {fid!r}")
        elif fid in seen_ids:
            _fail(res, f"id {fid} duplicato (riusato): un ID non si riutilizza mai")
        else:
            seen_ids.add(fid)

        primo = _parse_date(finding.get("primo_avvistamento"))
        if finding.get("primo_avvistamento") is not None and primo is None:
            _fail(res, f"{fid}: primo_avvistamento non leggibile come data: {finding.get('primo_avvistamento')!r}")

        occorrenze = finding.get("occorrenze") or []
        somma = 0.0
        for occ in occorrenze:
            data = _parse_date(occ.get("data"))
            if occ.get("data") is not None and data is None:
                _fail(res, f"{fid}: occorrenza con data non leggibile: {occ.get('data')!r}")
                continue
            if data is not None:
                if primo is not None and data < primo:
                    _fail(res, f"{fid}: occorrenza {data} precedente a primo_avvistamento {primo}")
                if win_start is not None and (data < win_start or data > win_end):
                    _fail(res, f"{fid}: occorrenza {data} fuori dalla finestra di osservazione")
            costo = occ.get("costo_usd")
            if costo is not None:
                somma += float(costo)

        costo_cum = finding.get("costo_cumulato_usd")
        if costo_cum is not None:
            # Tolleranza a un centesimo: gli importi sono stimati, non contabili.
            if abs(float(costo_cum) - somma) > 0.01:
                _fail(res, f"{fid}: costo cumulato incoerente: {costo_cum} != somma occorrenze {somma:.2f}")
    res["ok"] = not res["errors"]
    return res


def validate_panels(
    panels: dict,
    *,
    dossier_hashes: dict[str, str],
    window: tuple[dt.date, dt.date] | None = None,
    dossier_movers: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Controlla i pannelli longitudinali: causal_event_id, primary_finding,
    dossier_hash, duplicati, append-only, completeness."""
    res = _result()
    win_start, win_end = window or (None, None)
    definitions = panels.get("definitions") or []
    def_ids = {d.get("id") for d in definitions if isinstance(d, dict)}
    occurrences = panels.get("occurrences") or []

    prev_key: tuple = None  # per il check append-only (ordinamento per data)
    seen_causal: set[str] = set()
    # (data, ticker) -> numero di primary_finding assegnati (max 1).
    primary_count: dict[tuple, int] = defaultdict(int)

    for occ in occurrences:
        cid = occ.get("causal_event_id")
        match = CAUSAL_ID_PATTERN.match(cid) if isinstance(cid, str) else None
        if match is None:
            _fail(res, f"causal_event_id malformato: {cid!r}")
        else:
            kind = match.group("kind")
            if kind not in CAUSAL_KINDS:
                _fail(res, f"causal_event_id con kind non ammesso: {cid!r}")

        # data coerente con l'id (per i kind che incorporano la data).
        data = occ.get("data")
        data_parsed = _parse_date(data)
        if data is not None and data_parsed is None:
            _fail(res, f"occorrenza con data non leggibile: {data!r} (id {cid})")
        if isinstance(cid, str) and match is not None and match.group("kind") in DATE_EMBEDDING_KINDS:
            tokens = cid.split(":")
            if len(tokens) >= 3 and tokens[1] != str(data):
                _fail(res, f"data {data} incoerente con causal_event_id {cid}")

        if data_parsed is not None and win_start is not None:
            if data_parsed < win_start or data_parsed > win_end:
                _fail(res, f"occorrenza {data} fuori dalla finestra di osservazione (id {cid})")

        # primary_finding: se assegnato, deve esistere nelle definizioni.
        primary = occ.get("primary_finding")
        if primary is not None:
            if not (isinstance(primary, str) and ID_PATTERN.match(primary)):
                _fail(res, f"primary_finding non conforme (atteso F-NNN): {primary!r}")
            elif primary not in def_ids:
                _fail(res, f"primary_finding {primary} non presente nelle definizioni")
            # un solo finding primario riceve il costo per (data, ticker).
            for ticker in occ.get("tickers") or []:
                key = (data, ticker)
                primary_count[key] += 1
                if primary_count[key] > 1:
                    _fail(res, f"doppio primary_finding per ({data}, {ticker}): "
                              f"un solo finding primario puo' ricevere il costo")

        # dossier_hash: se la giornata ha un dossier reale, l'hash deve matchare.
        if data is not None and data in dossier_hashes:
            actual = dossier_hashes[data]
            if actual is not None and occ.get("dossier_hash") != actual:
                _fail(res, f"dossier_hash non corrispondente per {data}: "
                          f"atteso {actual}, trovato {occ.get('dossier_hash')}")

        # duplicati: causal_event_id univoco (anti-doppio-conteggio).
        if isinstance(cid, str):
            if cid in seen_causal:
                _fail(res, f"causal_event_id duplicato (doppio conteggio): {cid}")
            seen_causal.add(cid)

        # append-only: le occorrenze sono ordinate per data crescente.
        sort_key = (data or "", cid or "")
        if prev_key is not None and sort_key < prev_key:
            _fail(res, f"ledger non append-only: occorrenza {sort_key} precede {prev_key}")
        prev_key = sort_key

    # completeness: ogni giornata con dossier reale deve avere almeno
    # un'occorrenza; ogni mover del dossier deve apparire nel pannello ticker-day.
    occ_days = {occ.get("data") for occ in occurrences}
    for day, _h in dossier_hashes.items():
        if day not in occ_days:
            _fail(res, f"completeness: giornata {day} con dossier ma senza occorrenze")

    ticker_day = panels.get("ticker_day") or []
    if dossier_movers:
        panel_by_day: dict[str, set[str]] = defaultdict(set)
        for row in ticker_day:
            panel_by_day[row.get("data")].add(row.get("ticker"))
        for day, movers in dossier_movers.items():
            for ticker, ret in movers.items():
                if abs(float(ret)) >= 0.03 and ticker not in panel_by_day.get(day, set()):
                    _fail(res, f"completeness: mover {ticker} del {day} assente dal pannello ticker-day")

    res["ok"] = not res["errors"]
    return res


def validate_ledger(
    findings: dict,
    occurrences: list[dict],
    definitions: list[dict],
    *,
    dossier_hashes: dict[str, str],
    window: tuple[dt.date, dt.date] | None = None,
) -> dict:
    """Orchestra la validazione di findings + pannelli e fonde gli errori."""
    res = _result()
    f = validate_findings(findings, window=window)
    p = validate_panels(
        {"occurrences": occurrences, "definitions": definitions},
        dossier_hashes=dossier_hashes, window=window,
    )
    res["errors"] = f["errors"] + p["errors"]
    res["warnings"] = f["warnings"] + p["warnings"]
    res["ok"] = not res["errors"]
    return res