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
CAUSAL_ID_PATTERN = re.compile(
    r"^(?P<kind>miss|trade|decision|entry|exit|signal):[A-Za-z0-9._:\-]+$"
)
# kind che incorporano la data come secondo token (per il check di coerenza).
DATE_EMBEDDING_KINDS = frozenset({"miss", "entry", "exit", "signal"})


def _result() -> dict:
    return {"ok": True, "errors": [], "warnings": []}


def _fail(res: dict, msg: str) -> None:
    res["errors"].append(msg)


def _warn(res: dict, msg: str) -> None:
    res["warnings"].append(msg)


def _check_causal_row(
    res: dict,
    row: dict,
    *,
    seen_causal: set[str],
    row_kind_label: str,
    dossier_hashes: dict[str, str],
    win_start,
    win_end,
) -> str | None:
    """Controlla un singolo ``causal_event_id``: formato, kind ammesso, coerenza
    della data, finestra, dossier_hash, univocita' cross-row. Ritorna il
    ``prev_key`` (per il check append-only delle occurrences) oppure None se la
    riga non porta una data sortabile.

    ``row_kind_label`` distingue le occorrenze del ledger (``"occorrenza"``)
    dalle righe del pannello ``signals``: la label entra nel messaggio d'errore
    cosi' il destinatario sa dove guardare.
    """
    cid = row.get("causal_event_id")
    match = CAUSAL_ID_PATTERN.match(cid) if isinstance(cid, str) else None
    if match is None:
        _fail(res, f"{row_kind_label} senza causal_event_id valido: {cid!r}")
    else:
        kind = match.group("kind")
        if kind not in CAUSAL_KINDS:
            _fail(res, f"{row_kind_label} con kind non ammesso: {cid!r}")

    data = row.get("data")
    data_parsed = _parse_date(data)
    if data is not None and data_parsed is None:
        _fail(res, f"{row_kind_label} con data non leggibile: {data!r} (id {cid})")
    if (
        isinstance(cid, str)
        and match is not None
        and match.group("kind") in DATE_EMBEDDING_KINDS
    ):
        tokens = cid.split(":")
        if len(tokens) >= 3 and tokens[1] != str(data):
            _fail(res, f"data {data} incoerente con causal_event_id {cid} ({row_kind_label})")

    if data_parsed is not None and win_start is not None:
        if data_parsed < win_start or data_parsed > win_end:
            _fail(
                res,
                f"{row_kind_label} {data} fuori dalla finestra di osservazione (id {cid})",
            )

    if data is not None and data in dossier_hashes:
        actual = dossier_hashes[data]
        if actual is not None and row.get("dossier_hash") != actual:
            _fail(
                res,
                f"dossier_hash non corrispondente per {data} ({row_kind_label}): "
                f"atteso {actual}, trovato {row.get('dossier_hash')}",
            )

    if isinstance(cid, str):
        if cid in seen_causal:
            _fail(
                res,
                f"causal_event_id duplicato (doppio conteggio) su {row_kind_label}: {cid}",
            )
        seen_causal.add(cid)

    sort_key = (data or "", cid or "")
    return sort_key


def _parse_date(value) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def validate_findings(
    findings: dict, *, window: tuple[dt.date, dt.date] | None = None
) -> dict:
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
            _fail(
                res,
                f"{fid}: primo_avvistamento non leggibile come data: {finding.get('primo_avvistamento')!r}",
            )

        occorrenze = finding.get("occorrenze") or []
        somma = 0.0
        for occ in occorrenze:
            data = _parse_date(occ.get("data"))
            if occ.get("data") is not None and data is None:
                _fail(
                    res,
                    f"{fid}: occorrenza con data non leggibile: {occ.get('data')!r}",
                )
                continue
            if data is not None:
                if primo is not None and data < primo:
                    _fail(
                        res,
                        f"{fid}: occorrenza {data} precedente a primo_avvistamento {primo}",
                    )
                if win_start is not None and (data < win_start or data > win_end):
                    _fail(
                        res,
                        f"{fid}: occorrenza {data} fuori dalla finestra di osservazione",
                    )
            costo = occ.get("costo_usd")
            if costo is not None:
                somma += float(costo)

        costo_cum = finding.get("costo_cumulato_usd")
        if costo_cum is not None:
            # Tolleranza a un centesimo: gli importi sono stimati, non contabili.
            if abs(float(costo_cum) - somma) > 0.01:
                _fail(
                    res,
                    f"{fid}: costo cumulato incoerente: {costo_cum} != somma occorrenze {somma:.2f}",
                )
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
        sort_key = _check_causal_row(
            res,
            occ,
            seen_causal=seen_causal,
            row_kind_label="occorrenza",
            dossier_hashes=dossier_hashes,
            win_start=win_start,
            win_end=win_end,
        )

        cid = occ.get("causal_event_id")
        data = occ.get("data")

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
                    _fail(
                        res,
                        f"doppio primary_finding per ({data}, {ticker}): "
                        f"un solo finding primario puo' ricevere il costo",
                    )

        # append-only: le occorrenze sono ordinate per data crescente.
        if prev_key is not None and sort_key is not None and sort_key < prev_key:
            _fail(
                res, f"ledger non append-only: occorrenza {sort_key} precede {prev_key}"
            )
        if sort_key is not None:
            prev_key = sort_key

    # Pannello signals: stesso contratto anti-doppio conteggio sulle righe del
    # segnale (kind=signal, data, signal_id). L'append-only e' gia' coperto
    # dalle occurrences del ledger; qui' conta solo univocita' e formato.
    for sig in panels.get("signals") or []:
        _check_causal_row(
            res,
            sig,
            seen_causal=seen_causal,
            row_kind_label="segnale",
            dossier_hashes=dossier_hashes,
            win_start=win_start,
            win_end=win_end,
        )

    # completeness: ogni giornata con dossier e movers deve produrre occorrenze
    # (una giornata con candidati ma zero occorrenze = tutti NON_CLASSIFICATO, e'
    # un'anomalia del filtro upstream, non una giornata vuota legittima). Una
    # giornata piatta senza movers non si segnala: zero occorrenze e' corretto.
    # Se i movers non sono noti (dossier_movers assente), si resta conservativi.
    occ_days = {occ.get("data") for occ in occurrences}
    for day, _h in dossier_hashes.items():
        if day in occ_days:
            continue
        movers = dossier_movers.get(day) if dossier_movers else None
        if movers is None:
            _fail(res, f"completeness: giornata {day} con dossier ma senza occorrenze")
        elif any(abs(float(r)) >= 0.03 for r in movers.values()):
            _fail(
                res,
                f"completeness: giornata {day} con movers ma senza occorrenze "
                f"(tutti NON_CLASSIFICATO? filtro upstream da verificare)",
            )

    # ogni mover dichiarato deve apparire nel pannello ticker-day: il pannello
    # copre tutti i candidati miss, nessuno escluso in silenzio.
    ticker_day = panels.get("ticker_day") or []
    if dossier_movers:
        panel_by_day: dict[str, set[str]] = defaultdict(set)
        for row in ticker_day:
            panel_by_day[row.get("data")].add(row.get("ticker"))
        for day, movers in dossier_movers.items():
            for ticker, ret in movers.items():
                if abs(float(ret)) >= 0.03 and ticker not in panel_by_day.get(
                    day, set()
                ):
                    _fail(
                        res,
                        f"completeness: mover {ticker} del {day} assente dal pannello ticker-day",
                    )

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
        dossier_hashes=dossier_hashes,
        window=window,
    )
    res["errors"] = f["errors"] + p["errors"]
    res["warnings"] = f["warnings"] + p["warnings"]
    res["ok"] = not res["errors"]
    return res
