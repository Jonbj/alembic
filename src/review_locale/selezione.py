"""Quale PR esaminare stanotte (spec 2026-09-03 §4).

Modulo puro: riceve l'elenco delle PR aperte e le voci del ledger gia' lette,
non chiama `gh` ne' legge file.

Una PR per notte, la piu' vecchia non ancora esaminata: a ~4 ore per referto il
ritmo reale e' uno, e riempire la notte con le PR piu' piccole rimanderebbe per
sempre quelle grandi, che sono dove i difetti si nascondono.

L'identita' dell'esame e' `(numero, sha del head)`: nuovi commit riaprono una PR
gia' esaminata, perche' il referto vecchio parlava di un altro codice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


MAX_TENTATIVI = 2

STATI_ESAMINATA = ("ESAMINATA_CON_RILIEVI", "ESAMINATA_SENZA_RILIEVI")
STATO_FALLITO = "NON_ESAMINATA"


@dataclass(frozen=True)
class PrCandidata:
    numero: int
    sha: str
    creata_il: str


def scegli(
    candidate: Iterable[PrCandidata],
    ledger: Iterable[dict[str, Any]],
    max_tentativi: int = MAX_TENTATIVI,
) -> PrCandidata | None:
    """La PR da esaminare, o None se non ce n'e' nessuna eleggibile."""
    voci = list(ledger)
    esaminate = {
        (voce["pr"], voce["sha"])
        for voce in voci
        if voce.get("stato") in STATI_ESAMINATA
    }
    tentativi: dict[tuple[int, str], int] = {}
    for voce in voci:
        if voce.get("stato") == STATO_FALLITO:
            chiave = (voce["pr"], voce["sha"])
            tentativi[chiave] = tentativi.get(chiave, 0) + 1

    eleggibili = [
        pr
        for pr in candidate
        if (pr.numero, pr.sha) not in esaminate
        and tentativi.get((pr.numero, pr.sha), 0) < max_tentativi
    ]
    if not eleggibili:
        return None
    return min(eleggibili, key=lambda pr: pr.creata_il)
