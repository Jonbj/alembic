"""Riconciliazione tra i simboli registrati nel dossier e quelli citati nel report.

Issue #333, punto 4.
"""

from __future__ import annotations

import re


def _simboli_da_lista(operazioni: list) -> set:
    """Estrae i simboli non vuoti da una lista di operazioni.

    Tollerante su tutto cio' che non e' una lista di dizionari: un dossier malformato
    produce meno simboli, mai un'eccezione.
    """
    simboli = set()
    if not isinstance(operazioni, list):
        return simboli
    for op in operazioni:
        if isinstance(op, dict):
            sym = op.get("symbol")
            if isinstance(sym, str) and sym.strip():
                # `strip()` anche qui, non solo nel controllo: senza, un simbolo scritto
                # " WMT " verrebbe cercato con gli spazi e non troverebbe mai riscontro
                simboli.add(sym.strip().upper())
    return simboli


def _simbolo_mentzionato_in_testo(simbolo: str, testo: str) -> bool:
    """Verifica se il simbolo compare nel testo come parola intera, ignorando le maiuscole/minuscole."""
    # \b garantisce che i confini della parola siano delimitati da caratteri non alfanumerici
    # o da confini della stringa. Questo permette il riconoscimento in tabelle markdown (| HOOD |)
    # ed evita falsi positivi come "NOW" dentro "NOWHERE".
    pattern = r"\b" + re.escape(simbolo) + r"\b"
    return bool(re.search(pattern, testo, re.IGNORECASE))


def simboli_non_menzionati(dossier: dict, testo_report: str) -> dict:
    # `get(k, [])` restituisce None se la chiave esiste col valore None: i dossier piu'
    # vecchi possono averla cosi', e un TypeError qui farebbe cadere l'intero report
    ingressi = _simboli_da_lista(dossier.get("ingressi") or [])
    chiusure = _simboli_da_lista(dossier.get("chiusure") or [])

    ingressi_mancanti = sorted(s for s in ingressi if not _simbolo_mentzionato_in_testo(s, testo_report))
    chiusure_mancanti = sorted(s for s in chiusure if not _simbolo_mentzionato_in_testo(s, testo_report))

    return {
        "ingressi_mancanti": ingressi_mancanti,
        "chiusure_mancanti": chiusure_mancanti,
        "ok": not ingressi_mancanti and not chiusure_mancanti,
    }
