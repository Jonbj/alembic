"""Deriva sull'enum dei campi arricchiti del sentiment (#452).

`directness`/`event_type`/`risk_flags` sono documentati nel prompt come un
elenco chiuso di valori (vedi `_DK_COT_PROMPT` in `src/workers/sentiment.py`),
ma nello schema Pydantic (`LLMSentimentOutput`) sono semplici `str`/`list[str]`:
il vincolo vive solo nella `description`, non nel tipo. Senza un vincolo
grammaticale lato API (`format`, #452), il modello tratta l'enum come un
suggerimento: valori inventati (`supplier_readthrough`), separatori della
lista ricopiati (`competitor_readthrough|macro`), refusi
(`ambiguo_entity`), caratteri invisibili dentro un valore altrimenti valido
(`uncl​ear`).

Funzioni pure: nessun accesso a DB o rete. L'I/O sta in
`scripts/measure_452_schema_drift.py`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

DIRECTNESS_VALIDI = frozenset(
    {"direct", "customer_supplier", "competitor_readthrough", "sector", "macro", "unclear"}
)
EVENT_TYPE_VALIDI = frozenset(
    {
        "earnings", "guidance", "mna", "regulatory", "lawsuit",
        "analyst_rating", "product", "management", "macro", "other",
    }
)
RISK_FLAGS_VALIDI = frozenset(
    {"rumor", "already_priced_in", "ambiguous_entity", "low_source_quality"}
)


def valore_in_deriva(valore: str | None, validi: frozenset[str]) -> bool:
    """Un valore non-NULL che non compare esattamente nell'insieme valido.

    Esatto, non case-insensitive ne' fuzzy: un refuso o un carattere
    invisibile devono contare come deriva, non essere normalizzati via —
    e' proprio quello che il vincolo grammaticale (#452) dovrebbe impedire.
    """
    return valore is not None and valore not in validi


def risk_flags_in_deriva(flags: Iterable[str] | None) -> list[str]:
    """I flag della lista che non sono uno dei quattro valori validi."""
    return [f for f in (flags or []) if f not in RISK_FLAGS_VALIDI]


def classifica_riga(
    directness: str | None,
    event_type: str | None,
    risk_flags: Iterable[str] | None,
) -> dict:
    """Deriva per riga, campo per campo. Una riga con almeno un campo in
    deriva conta come `riga_in_deriva` nell'aggregazione."""
    flags_invalidi = risk_flags_in_deriva(risk_flags)
    directness_invalido = valore_in_deriva(directness, DIRECTNESS_VALIDI)
    event_type_invalido = valore_in_deriva(event_type, EVENT_TYPE_VALIDI)
    return {
        "directness_invalido": directness_invalido,
        "event_type_invalido": event_type_invalido,
        "risk_flags_invalidi": flags_invalidi,
        "riga_in_deriva": bool(
            directness_invalido or event_type_invalido or flags_invalidi
        ),
    }


def aggrega_deriva(righe: Iterable[Mapping]) -> dict:
    """Conteggio e tasso di deriva, per campo e complessivo, con gli esempi
    di valore invalido effettivamente osservati (per ispezione qualitativa).

    `righe`: mapping con chiavi `directness`, `event_type`, `risk_flags`
    (gia' None-safe — una riga senza campi arricchiti, self-report assente,
    non conta ne' come deriva ne' come pulita: e' fuori campione).
    """
    campione: list[dict] = []
    valori_directness_invalidi: set[str] = set()
    valori_event_type_invalidi: set[str] = set()
    valori_risk_flags_invalidi: set[str] = set()

    for riga in righe:
        directness = riga.get("directness")
        event_type = riga.get("event_type")
        risk_flags = riga.get("risk_flags")
        if directness is None and event_type is None and not risk_flags:
            continue
        verdetto = classifica_riga(directness, event_type, risk_flags)
        campione.append(verdetto)
        if verdetto["directness_invalido"] and directness is not None:
            valori_directness_invalidi.add(directness)
        if verdetto["event_type_invalido"] and event_type is not None:
            valori_event_type_invalidi.add(event_type)
        valori_risk_flags_invalidi.update(verdetto["risk_flags_invalidi"])

    n = len(campione)
    n_directness_invalidi = sum(1 for v in campione if v["directness_invalido"])
    n_event_type_invalidi = sum(1 for v in campione if v["event_type_invalido"])
    n_risk_flags_invalidi = sum(1 for v in campione if v["risk_flags_invalidi"])
    n_righe_in_deriva = sum(1 for v in campione if v["riga_in_deriva"])

    return {
        "n_campione": n,
        "directness": {
            "n_invalidi": n_directness_invalidi,
            "tasso": (n_directness_invalidi / n) if n else None,
            "valori_osservati": sorted(valori_directness_invalidi),
        },
        "event_type": {
            "n_invalidi": n_event_type_invalidi,
            "tasso": (n_event_type_invalidi / n) if n else None,
            "valori_osservati": sorted(valori_event_type_invalidi),
        },
        "risk_flags": {
            "n_righe_con_flag_invalido": n_risk_flags_invalidi,
            "tasso": (n_risk_flags_invalidi / n) if n else None,
            "valori_osservati": sorted(valori_risk_flags_invalidi),
        },
        "riga_in_deriva": {
            "n": n_righe_in_deriva,
            "tasso": (n_righe_in_deriva / n) if n else None,
        },
    }
