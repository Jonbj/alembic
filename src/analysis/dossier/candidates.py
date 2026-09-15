"""Validazione e applicazione dei candidati ledger alpha-miss (#287, L3/P1).

Fino a oggi la sessione LLM appendeva direttamente a ``findings.json`` e
``market_daily.jsonl``, e le uniche guardie erano istruzioni in prosa nel
prompt — le stesse che il prompt contraddiceva altrove. Con il nuovo contratto
la sessione emette un file di candidati; questo modulo (puro, dict in/out) ne
fa la validazione meccanica, e solo un payload che passa puo' essere
applicato dal materializzatore deterministico.

Le regole qui dentro sono le stesse che prima vivevano nel prompt, rese
enforcabili: schema esatto della riga di mercato, tassonomia miss congelata,
ID conformi, costo nullo solo con formula, campi di audit obbligatori
(esposizione, evidenza contraria, non-occorrenza, next evidence, meccanismo,
alternative scartate), confidenza coerente col record esistente.

Modulo puro: nessun I/O, nessuna formula nuova — la somma dei costi e' la
stessa del prompt (somma delle sole occorrenze con costo non-null).
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from src.analysis.dossier.prompt_contract import PROMPT_VERSION

CANDIDATES_SCHEMA_VERSION = "1.0"

# Schema della riga di market_daily.jsonl: la serie pre-registrata della carta
# (#171). E' lo stesso ordine del prompt storico; cambiarlo e' una
# discontinuita' di misura da annotare, non un refactor.
CHIAVI_RIGA_MARKET = (
    "data",
    "spy",
    "qqq",
    "dispersione_sigma",
    "mover_3pct",
    "up",
    "down",
    "watchlist_zero_news",
    "tema",
    "miss",
    "catturati",
    "book",
)

# Tassonomia miss legacy della serie pre-registrata: congelata fino al
# 28/09 (#171, O1). Il funnel v2 vive nel dossier, non qui.
CHIAVI_MISS = frozenset(
    {"NO_NEWS", "THIN_NEUTRAL", "WRONG_SIGN", "FILTERED", "OUT_OF_STRATEGY_SCOPE"}
)

CHIAVI_BOOK = ("equity", "realizzato", "mtm", "s1_realizzato", "s4_realizzato")

TIPI_FINDING = frozenset({"difetto", "alpha_miss", "osservazione"})
CONFIDENZE = frozenset({"misurata", "attribuita", "congetturale"})

NUOVO_ID = "F-NUOVO"
ID_FINDING = re.compile(r"^F-\d{3}$")

# Campi di audit (P3): senza uno di questi l'occorrenza non e' difendibile.
CAMPI_AUDIT = (
    "esposizione",
    "evidenza_contraria",
    "non_occorrenza",
    "next_evidence",
    "meccanismo",
)
CAMPI_OBBLIGATORI = ("nota", "fonte", *CAMPI_AUDIT)


def _errore(errors: list[str], msg: str) -> None:
    errors.append(msg)


def _testo_non_vuoto(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _valida_riga_market(
    riga: Any, data_attesa: str, errors: list[str], warnings: list[str], righe_esistenti
) -> None:
    if not isinstance(riga, Mapping):
        _errore(errors, "market_daily: riga mancante o non e' un oggetto")
        return

    chiavi_riga = set(riga.keys())
    attese = set(CHIAVI_RIGA_MARKET)
    mancanti = attese - chiavi_riga
    extra = chiavi_riga - attese
    for k in sorted(mancanti):
        _errore(errors, f"market_daily: chiave mancante {k!r}")
    for k in sorted(extra):
        _errore(errors, f"market_daily: chiave non prevista {k!r}")

    if riga.get("data") != data_attesa:
        _errore(
            errors,
            f"market_daily: data {riga.get('data')!r} diversa dalla seduta "
            f"{data_attesa!r}",
        )

    for k in ("spy", "qqq", "dispersione_sigma"):
        v = riga.get(k)
        if v is not None and not isinstance(v, (int, float)):
            _errore(errors, f"market_daily: {k} deve essere numero o null, non {v!r}")
    for k in ("mover_3pct", "up", "down", "watchlist_zero_news", "catturati"):
        v = riga.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            _errore(errors, f"market_daily: {k} deve essere un intero >= 0, non {v!r}")

    if not _testo_non_vuoto(riga.get("tema")):
        _errore(errors, "market_daily: tema deve essere testo non vuoto (ammesso 'non chiaro')")

    miss = riga.get("miss")
    if not isinstance(miss, Mapping) or set(miss.keys()) != CHIAVI_MISS:
        _errore(
            errors,
            f"market_daily: miss deve avere esattamente le chiave "
            f"{sorted(CHIAVI_MISS)}, trovate {sorted(miss) if isinstance(miss, Mapping) else miss!r}",
        )
    else:
        for k, v in miss.items():
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                _errore(errors, f"market_daily: miss.{k} deve essere un intero >= 0, non {v!r}")

    book = riga.get("book")
    if not isinstance(book, Mapping) or set(book.keys()) != set(CHIAVI_BOOK):
        _errore(errors, f"market_daily: book deve avere esattamente le chiave {CHIAVI_BOOK}")
    elif any(
        book.get(k) is not None and not isinstance(book.get(k), (int, float))
        for k in CHIAVI_BOOK
    ):
        _errore(errors, "market_daily: i valori di book devono essere numero o null")

    # Riga gia' presente: il report e' stato rigenerato. Non e' un errore (la
    # regola storica e' "lascia il file com'e' e segnalalo"), ma il
    # materializzatore deve saperlo.
    if any(r.get("data") == riga.get("data") for r in righe_esistenti or []):
        warnings.append(
            f"market_daily: riga per {riga.get('data')} gia' presente — "
            "non se ne appende una seconda"
        )


def _valida_candidato_finding(
    candidato: Any,
    indice: int,
    findings: Mapping,
    data_attesa: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    prefisso = f"findings[{indice}]"
    if not isinstance(candidato, Mapping):
        _errore(errors, f"{prefisso}: non e' un oggetto")
        return

    fid = candidato.get("finding_id")
    esistenti = {f.get("id"): f for f in findings.get("findings") or []}
    record = esistenti.get(fid) if isinstance(fid, str) else None
    nuovo = fid == NUOVO_ID

    if nuovo:
        for campo in ("titolo", "giustificazione_nuovo"):
            if not _testo_non_vuoto(candidato.get(campo)):
                _errore(errors, f"{prefisso}: {campo} obbligatorio per un finding nuovo")
        record = None
    elif record is None:
        _errore(errors, f"{prefisso}: finding_id {fid!r} non esiste nel ledger")
        return

    for campo in ("tipo",):
        if candidato.get(campo) not in TIPI_FINDING:
            _errore(errors, f"{prefisso}: {campo} {candidato.get(campo)!r} non ammesso")
    confidenza = candidato.get("confidenza")
    if confidenza not in CONFIDENZE:
        _errore(errors, f"{prefisso}: confidenza {confidenza!r} non ammessa")
    elif record is not None and record.get("confidenza") != confidenza:
        # La confidenza fissa la soglia della carta per il finding: cambiarla
        # da una sessione all'altra muterebbe la serie dei verdetti.
        _errore(
            errors,
            f"{prefisso}: confidenza {confidenza!r} diversa dal record "
            f"({record.get('confidenza')!r}) — e' una decisione dell'operatore, "
            "non della sessione",
        )

    costo = candidato.get("costo_usd")
    if costo is not None:
        if not isinstance(costo, (int, float)) or isinstance(costo, bool):
            _errore(errors, f"{prefisso}: costo_usd deve essere numero o null, non {costo!r}")
        elif not _testo_non_vuoto(candidato.get("formula_costo")):
            _errore(
                errors,
                f"{prefisso}: costo_usd stimato ({costo}) senza formula_costo: "
                "il costo non e' auditabile",
            )

    for campo in CAMPI_OBBLIGATORI:
        if not _testo_non_vuoto(candidato.get(campo)):
            _errore(errors, f"{prefisso}: {campo} mancante o vuoto")

    alternative = candidato.get("alternative_scartate")
    if (
        not isinstance(alternative, list)
        or not alternative
        or not all(_testo_non_vuoto(a) for a in alternative)
    ):
        _errore(
            errors,
            f"{prefisso}: alternative_scartate deve contenere almeno una "
            "spiegazione alternativa scartata, con evidenza",
        )

    if candidato.get("data", data_attesa) != data_attesa:
        _errore(errors, f"{prefisso}: data diversa dalla seduta {data_attesa!r}")

    # Occorrenza doppia per (finding, giorno): il report rigenerato appendeva
    # due volte la stessa giornata. Si salta, non si riappende.
    if record is not None:
        gia_presente = any(
            o.get("data") == data_attesa for o in record.get("occorrenze") or []
        )
        if gia_presente:
            warnings.append(
                f"{prefisso}: occorrenza per {fid} del {data_attesa} gia' presente — "
                "candidato saltato per evitare il doppio conteggio"
            )


def valida_candidati(
    candidati: Mapping[str, Any],
    findings: Mapping[str, Any],
    *,
    righe_market: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Valida il payload dei candidati contro il ledger corrente.

    Ritorna ``{"ok", "errors", "warnings"}``. Le righe di mercato gia'
    presenti e le occorrenze doppie sono warning, non errori: il
    materializzatore le salta, non rifiuta la seduta.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(candidati, Mapping):
        return {"ok": False, "errors": ["payload candidati non e' un oggetto"], "warnings": []}

    if candidati.get("schema_version") != CANDIDATES_SCHEMA_VERSION:
        _errore(
            errors,
            f"schema_version {candidati.get('schema_version')!r} non supportata "
            f"(attesa {CANDIDATES_SCHEMA_VERSION})",
        )
    if candidati.get("prompt_version") != PROMPT_VERSION:
        _errore(
            errors,
            f"prompt_version {candidati.get('prompt_version')!r} non e' quella del "
            f"contratto corrente ({PROMPT_VERSION}): candidati generati da un "
            "prompt diverso",
        )

    data_attesa = candidati.get("data")
    if not _testo_non_vuoto(data_attesa):
        _errore(errors, "data della seduta mancante")
        data_attesa = ""

    _valida_riga_market(
        candidati.get("market_daily"), data_attesa, errors, warnings, righe_market
    )

    lista = candidati.get("findings")
    if lista is None:
        lista = []
    if not isinstance(lista, list):
        _errore(errors, "findings deve essere una lista (anche vuota)")
        lista = []
    for indice, candidato in enumerate(lista):
        _valida_candidato_finding(
            candidato, indice, findings, data_attesa, errors, warnings
        )

    return {"ok": not errors, "errors": errors, "warnings": warnings}

def _ricalcola_cumulati(record: dict[str, Any]) -> None:
    """Somma i costi come faceva il prompt, ma in codice: le sole occorrenze
    con costo non-null contano, le altre incrementano ``occorrenze_non_stimate``.
    """
    occorrenze = record.get("occorrenze") or []
    record["costo_cumulato_usd"] = sum(
        o["costo_usd"] for o in occorrenze if o.get("costo_usd") is not None
    )
    record["occorrenze_non_stimate"] = sum(
        1 for o in occorrenze if o.get("costo_usd") is None
    )


def applica_candidati(
    candidati: Mapping[str, Any],
    findings: Mapping[str, Any],
    *,
    righe_market: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Applica un payload gia' validato, senza mutare gli input.

    Ritorna ``{"findings", "righe", "mercato", "applicati", "warnings"}``:
    ``findings`` e ``righe`` sono copie nuove pronte per la scrittura atomica
    del materializzatore; ``mercato`` dice se la riga e' stata appesa o era
    gia' presente; ``applicati`` elenca finding e azione per il log.
    Gli input restano immutati: chi chiama decide se e quando scrivere.
    """
    import copy

    righe_esistenti = list(righe_market or [])
    data = candidati.get("data")
    warnings: list[str] = []

    riga = candidati.get("market_daily")
    if isinstance(riga, Mapping) and not any(
        r.get("data") == data for r in righe_esistenti
    ):
        righe = [*righe_esistenti, dict(riga)]
        mercato = "aggiunta"
    else:
        righe = righe_esistenti
        mercato = "riga_gia_presente"

    nuovo_findings = copy.deepcopy(dict(findings))
    esistenti = {f["id"]: f for f in nuovo_findings.get("findings") or []}
    prossimo = int(nuovo_findings.get("prossimo_id") or 1)
    applicati: list[dict[str, Any]] = []

    for candidato in candidati.get("findings") or []:
        fid = candidato.get("finding_id")
        occorrenza = {
            "data": data,
            "costo_usd": candidato.get("costo_usd"),
            "nota": candidato.get("nota"),
            "fonte": candidato.get("fonte"),
        }

        if fid == NUOVO_ID:
            nuovo_id = f"F-{prossimo:03d}"
            prossimo += 1
            record = {
                "id": nuovo_id,
                "titolo": candidato.get("titolo"),
                "tipo": candidato.get("tipo"),
                "confidenza": candidato.get("confidenza"),
                "primo_avvistamento": data,
                "occorrenze": [occorrenza],
                "costo_cumulato_usd": 0.0,
                "occorrenze_non_stimate": 0,
                "stato": "aperto",
                "issue": None,
            }
            _ricalcola_cumulati(record)
            nuovo_findings["findings"] = [*(nuovo_findings.get("findings") or []), record]
            esistenti[nuovo_id] = record
            applicati.append({"finding_id": nuovo_id, "azione": "nuovo_record"})
            continue

        record = esistenti.get(fid)
        if record is None:
            # La validazione deve averlo gia' rifiutato: qui si salta in
            # silenzio perche' un'applicazione parziale non rompa il ledger.
            continue
        if any(o.get("data") == data for o in record.get("occorrenze") or []):
            warnings.append(
                f"occorrenza per {fid} del {data} gia' presente — candidato saltato"
            )
            continue
        record["occorrenze"] = [*(record.get("occorrenze") or []), occorrenza]
        _ricalcola_cumulati(record)
        applicati.append({"finding_id": fid, "azione": "occorrenza_appesa"})

    nuovo_findings["prossimo_id"] = prossimo
    return {
        "findings": nuovo_findings,
        "righe": righe,
        "mercato": mercato,
        "applicati": applicati,
        "warnings": warnings,
    }
