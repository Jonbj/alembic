"""Cancello a citazione sul referto di triage (2026-09-14).

Modulo puro. Impone la regola che rende utilizzabile un modello che sbaglia:
**un reperto vale solo se cita testualmente una riga di log che esiste davvero,
e che appartiene al template su cui il reperto si pronuncia.** Tutto il resto
viene scartato senza discussione.

Il corollario, gia' imparato su PR #472 e ribadito qui: `SENZA_REPERTI` non e'
un verdetto di sanita'. E' assenza di reperto — il modello e' una lente che
esamina, non un cancello che approva. Nessun campo in cui il modello dichiari
corretto cio' che ha guardato attraversa questo confine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.triage_log.distillazione import Voce, normalizza_riga

CHIAVI_REPERTO = ("template_id", "gravita", "anomalia", "perche_anomalo", "cosa_controllare")

VALIDO = "VALIDO"
SENZA_REPERTI = "SENZA_REPERTI"


@dataclass(frozen=True)
class Esito:
    """Cosa ha superato il cancello, e cosa e' caduto e perche'."""

    stato: str
    reperti: tuple[dict[str, Any], ...] = ()
    scartati: tuple[dict[str, Any], ...] = ()


def _indice(template_id: Any, voci: list[Voce]) -> Voce | None:
    """Risolve `T0007` nella voce corrispondente del digest, o None."""
    if not isinstance(template_id, str) or not template_id.startswith("T"):
        return None
    try:
        posizione = int(template_id[1:])
    except ValueError:
        return None
    if 1 <= posizione <= len(voci):
        return voci[posizione - 1]
    return None


def _normalizza_spazi(testo: str) -> str:
    return " ".join(testo.split())


def verifica(reperti: list[dict], voci: list[Voce], righe: list[str]) -> Esito:
    """Partiziona i reperti in citati-e-verificati contro scartati."""
    grezze = {_normalizza_spazi(riga): riga for riga in righe}
    validi: list[dict] = []
    scartati: list[dict] = []
    for reperto in reperti:
        motivi: list[str] = []
        if not isinstance(reperto, dict):
            scartati.append({"reperto": reperto, "motivi": ["REPERTO_NON_OGGETTO"]})
            continue
        for chiave in CHIAVI_REPERTO:
            if not isinstance(reperto.get(chiave), str) or not reperto[chiave].strip():
                motivi.append(f"MANCA_{chiave.upper()}")
        voce = _indice(reperto.get("template_id"), voci)
        if voce is None:
            motivi.append("TEMPLATE_INESISTENTE")
        citazione = reperto.get("citazione")
        if not isinstance(citazione, str) or not citazione.strip():
            motivi.append("MANCA_CITAZIONE")
        else:
            riga = grezze.get(_normalizza_spazi(citazione))
            if riga is None:
                motivi.append("CITAZIONE_NON_TROVATA")
            elif voce is not None and normalizza_riga(riga) != voce.template:
                motivi.append("CITAZIONE_FUORI_TEMPLATE")
        if motivi:
            scartati.append({"reperto": reperto, "motivi": motivi})
            continue
        validi.append({chiave: reperto[chiave] for chiave in (*CHIAVI_REPERTO, "citazione")})
    stato = VALIDO if validi else SENZA_REPERTI
    return Esito(stato=stato, reperti=tuple(validi), scartati=tuple(scartati))


def recupera_troncato(testo: str) -> str | None:
    """Salva i reperti completi da una risposta tagliata a meta' stringa.

    `append_missing_json_closers` (riusato da `scripts.s4_cluster_literature`)
    ripara solo i tagli avvenuti al confine fra container: si rifiuta, giustamente,
    di chiudere una stringa aperta, perche' non puo' sapere come finiva. Ma il
    taglio reale osservato il 2026-09-15 e' proprio quello — tetto di token
    raggiunto a meta' di un campo — e buttava via 41 minuti di generazione insieme
    ai reperti gia' completi che la precedevano.

    Qui si torna all'**ultimo punto in cui un elemento era chiuso** e si chiudono i
    container ancora aperti a quel punto. Nessun contenuto viene inventato:
    l'elemento troncato si perde, gli altri si salvano. Restituisce None quando non
    c'e' niente da salvare o quando il testo non era troncato affatto.
    """
    pila: list[str] = []
    nella_stringa = False
    evaso = False
    sicuri: list[tuple[int, tuple[str, ...]]] = []
    for posizione, carattere in enumerate(testo):
        if nella_stringa:
            if evaso:
                evaso = False
            elif carattere == "\\":
                evaso = True
            elif carattere == '"':
                nella_stringa = False
            continue
        if carattere == '"':
            nella_stringa = True
        elif carattere in "{[":
            pila.append("}" if carattere == "{" else "]")
        elif carattere in "}]":
            if not pila or pila.pop() != carattere:
                return None
            if pila:
                sicuri.append((posizione + 1, tuple(pila)))
    if not pila and not nella_stringa:
        return None
    for posizione, aperti in reversed(sicuri):
        candidato = testo[:posizione] + "".join(reversed(aperti))
        try:
            json.loads(candidato)
        except json.JSONDecodeError:
            continue
        return candidato
    return None
