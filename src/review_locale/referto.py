"""Validazione del referto prodotto dal modello locale (spec 2026-09-03).

Modulo puro: riceve il testo che il modello ha emesso e non tocca rete, disco o
processi.

La regola che questo modulo esiste per imporre: **su GitHub va solo un referto
completo con almeno un rilievo azionabile.** Il campo `verificato_e_scartato`
— le "verifiche" con cui il modello dichiara corretto cio' che ha guardato —
non attraversa questo confine in nessuna circostanza. Su PR #472 ne ha prodotte
undici, di cui almeno due false, e false esattamente sui due punti dove i
difetti erano reali: e' una lente che esamina, non un cancello che approva.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# Chiavi che ogni rilievo deve portare per essere azionabile. `mascherato_da`
# resta fuori: e' informativa e legittimamente assente.
CHIAVI_RILIEVO = ("gravita", "categoria", "posizione", "difetto", "scenario_di_fallimento")

PUBBLICABILE = "PUBBLICABILE"
SENZA_RILIEVI = "SENZA_RILIEVI"
NON_VALIDO = "NON_VALIDO"


@dataclass(frozen=True)
class Esito:
    """Cosa e' uscito dal referto, e cosa se ne puo' fare.

    `rilievi` contiene SOLO rilievi completi, e per costruzione nessuna
    assoluzione: e' l'unico campo che l'orchestratore ha il diritto di
    pubblicare.
    """

    stato: str
    rilievi: tuple[dict[str, Any], ...] = ()
    causa: str | None = None


def _rilievo_completo(rilievo: Any) -> bool:
    if not isinstance(rilievo, dict):
        return False
    return all(rilievo.get(chiave) for chiave in CHIAVI_RILIEVO)


def prepara(testo: str) -> Esito:
    """Trasforma il testo emesso dal modello in un esito pubblicabile o no."""
    try:
        corpo = json.loads(testo)
    except (json.JSONDecodeError, TypeError) as exc:
        return Esito(NON_VALIDO, causa=f"JSON non parsabile: {exc}")

    if not isinstance(corpo, dict):
        return Esito(NON_VALIDO, causa="il referto non e' un oggetto JSON")

    grezzi = corpo.get("rilievi")
    if not isinstance(grezzi, list):
        return Esito(NON_VALIDO, causa="il campo `rilievi` manca o non e' una lista")

    # Si ricostruiscono i rilievi chiave per chiave invece di filtrare il corpo:
    # cosi' nessun campo del modello puo' passare per inerzia, incluse le
    # assoluzioni e qualunque chiave nuova che il modello inventasse.
    validi = tuple(
        {chiave: rilievo[chiave] for chiave in CHIAVI_RILIEVO}
        | {"mascherato_da": rilievo.get("mascherato_da")}
        for rilievo in grezzi
        if _rilievo_completo(rilievo)
    )

    if not validi:
        return Esito(SENZA_RILIEVI)
    return Esito(PUBBLICABILE, rilievi=validi)
