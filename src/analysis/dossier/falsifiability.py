"""Rende i finding falsificabili e sintetizzabili (#286).

Costruisce VISTE PARALLELE sopra il ledger primario congelato
(``findings.json``, read-only): niente cancellazione, fusione distruttiva o
modifica retroattiva. Per ogni finding arricchisce la definizione con i campi
di falsificabilita' richiesti dalla carta di osservazione:

* ``giorni_distinti`` — giorni distinti in finestra (la carta esclude il
  2026-07-31: la sua nota dice che le occorrenze del 31/07 non contano verso le
  soglie di ricorrenza ne' verso i costi cumulati).
* ``costo_cumulato_in_finestra_usd`` — somma dei costi delle occorrenze in
  finestra (31/07 escluso).
* ``distanza_soglia`` / ``oltre_soglia`` — quanto il finding dista
  dall'attraversare la soglia della sua confidenza, secondo la carta. Le
  soglie sono DOCUMENTATE nella carta, non sono taratura: sono il criterio
  pre-registrato di diritto al lavoro alla scadenza.
* ``dimensione`` — classe di magnitudo del costo cumulato in finestra.
* ``giorni_esposti`` / ``non_occorrenze`` / ``evidenza_contraria`` —
  denominatori di falsificabilita': derivati MECCANICAMENTE solo quando e' nota
  la relazione finding->causa (``relazione_finding_causa`` nelle annotazioni
  dell'operatore); altrimenti ``None`` con missingness esplicita, mai zero.
* ``meccanismo``, ``strategia``, ``relazione_finding_causa``,
  ``stato_falsificazione`` (``supported`` / ``contradicted`` / ``not_exposed``),
  ``prova_decisiva`` — giudizio dell'operatore/LLM, vivono nelle annotazioni
  parallele (``annotations``), default ``None`` / ``not_exposed``. Il wiring
  del prompt cron per popolarle e' post-freeze (fuori perimetro), come
  ``primary_finding`` in #282: la struttura e' pronta, i valori restano null.

Pure: riceve dict, restituisce dict. Nessun I/O. Lo schema e' versionato.
"""

from __future__ import annotations

import datetime as dt

FALSIFIABILITY_SCHEMA_VERSION = "1.0"

# Data esclusa dai conteggi della finestra secondo la carta di osservazione
# (#171, "Nota sulla riga del 2026-07-31"): le occorrenze del 31/07 non contano
# verso le soglie di ricorrenza ne' verso i costi cumulati. Non e' una taratura,
# e' una regola documentata nella carta.
ESCLUDI_DATA = "2026-07-31"

# Soglie della carta di osservazione ("Soglie: cosa guadagna diritto a lavoro"):
#   misurata     — perdita reale tracciata a righe di DB — >= $100 cumulativi,
#                  ricorrenza irrilevante.
#   attribuita  — trade esiste, controfattuale corto — >= $250 cumulativi E
#                  >= 5 giorni distinti.
#   congetturale — alpha mancato, nessun trade — >= $1000 cumulativi E
#                  >= 10 giorni distinti.
#   non stimato  — costo_usd null — >= 15 giorni distinti (ricorrenza, non costo).
# Sono criteri PRE-REGISTRATI documentati nella carta, non parametri di
# taratura: declaring them qui' e' misura, non congelamento violato.
SOGLIA_MISURATA_USD = 100.0
SOGLIA_ATTRIBUITA_USD = 250.0
SOGLIA_ATTRIBUITA_GIORNI = 5
SOGLIA_CONGETTURALE_USD = 1000.0
SOGLIA_CONGETTURALE_GIORNI = 10
SOGLIA_NON_STIMATO_GIORNI = 15

# Stati di falsificazione ammessi per un finding. ``not_exposed`` = non e' stato
# ancora esposto a una prova decisiva (default, onesto: non dichiariamo falso
# cio' che non e' stato testato). ``supported`` / ``contradicted`` richiedono
# una ``prova_decisiva`` registrata (read-only).
STATO_SUPPORTED = "supported"
STATO_CONTRADICTED = "contradicted"
STATO_NOT_EXPOSED = "not_exposed"
STATI_FALSIFICAZIONE = frozenset({STATO_SUPPORTED, STATO_CONTRADICTED, STATO_NOT_EXPOSED})

# Classi di dimensione del costo cumulato in finestra (coerenti con i limiti
# delle soglie della carta).
DIMENSIONE_SOTTO_100 = "sotto_100"
DIMENSIONE_100_250 = "100_250"
DIMENSIONE_250_1000 = "250_1000"
DIMENSIONE_OLTRE_1000 = "oltre_1000"


def _parse_date(value) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _in_finestra(data: dt.date, window: tuple[dt.date, dt.date]) -> bool:
    """La data e' dentro la finestra di osservazione. Il 31/07 e' escluso dai
    conteggi per la carta, ma resta DENTRO la finestra (e' precedente allo
    start): l'esclusione e' gestita a parte (``_conta_per_finestra``)."""
    if data is None:
        return False
    start, end = window
    return start <= data <= end


def _conta_per_finestra(data_str, window: tuple[dt.date, dt.date]) -> bool:
    """L'occorrenza conta verso i conteggi della finestra: dentro la finestra E
    non e' il 31/07 (escluso per la carta)."""
    data = _parse_date(data_str)
    if data is None:
        return False
    if data_str == ESCLUDI_DATA:
        return False
    return _in_finestra(data, window)


def _soglie_per_confidenza(confidenza: str) -> tuple[float | None, int | None]:
    """Soglie della carta per la confidenza del finding (via del costo):
        misurata     — >= $100 (ricorrenza irrilevante).
        attribuita  — >= $250 E >= 5 giorni distinti.
        congetturale — >= $1000 E >= 10 giorni distinti.
    La via "non stimato" (>= 15 giorni non stimabili) e' un FALLBACK OR separato
    (vedi ``_valuta_soglia``): non sostituisce la via del costo quando il
    finding ha costo stimabile."""
    if confidenza == "misurata":
        return (SOGLIA_MISURATA_USD, None)
    if confidenza == "attribuita":
        return (SOGLIA_ATTRIBUITA_USD, SOGLIA_ATTRIBUITA_GIORNI)
    if confidenza == "congetturale":
        return (SOGLIA_CONGETTURALE_USD, SOGLIA_CONGETTURALE_GIORNI)
    return (None, None)


def _dimensione(costo: float | None) -> str:
    """Classe di magnitudo del costo cumulato in finestra."""
    if costo is None:
        return DIMENSIONE_SOTTO_100
    if costo < 100.0:
        return DIMENSIONE_SOTTO_100
    if costo < 250.0:
        return DIMENSIONE_100_250
    if costo < 1000.0:
        return DIMENSIONE_250_1000
    return DIMENSIONE_OLTRE_1000


def _valuta_soglia(
    costo: float,
    giorni: int,
    giorni_non_stimati: int,
    confidenza: str,
) -> dict:
    """Valuta il finding contro le due vie di diritto al lavoro della carta:

    1. via del costo (confidenza): tutti gli assi previsti >= soglia.
    2. via della ricorrenza (non stimato): >= 15 giorni distinti non stimabili.

    Le due vie sono OR: un finding con costo stimabile supera dalla via del
    costo; un finding senza costo stimabile (osservazione strutturale) entra
    comunque in roadmap per ricorrenza. La via della ricorrenza NON maschera
    un finding che ha costo stimabile ma sotto soglia: e' un fallback, non un
    override. ``distanza_soglia`` riporta quanto manca su ciascun asse (signed:
    negativo = gia' oltre). ``None`` dove la confidenza non ha soglia su
    quell'asse."""
    soglia_costo, soglia_giorni = _soglie_per_confidenza(confidenza)

    dist_costo = None
    dist_giorni = None
    via_costo = True
    if soglia_costo is not None:
        dist_costo = soglia_costo - costo
        if costo < soglia_costo:
            via_costo = False
    if soglia_giorni is not None:
        dist_giorni = soglia_giorni - giorni
        if giorni < soglia_giorni:
            via_costo = False
    if soglia_costo is None and soglia_giorni is None:
        via_costo = False

    via_ricorrenza = giorni_non_stimati >= SOGLIA_NON_STIMATO_GIORNI
    dist_ricorrenza = SOGLIA_NON_STIMATO_GIORNI - giorni_non_stimati

    return {
        "costo_usd": dist_costo,
        "giorni": dist_giorni,
        "ricorrenza_giorni": dist_ricorrenza,
        "via_costo": via_costo,
        "via_ricorrenza": via_ricorrenza,
        "oltre_soglia": via_costo or via_ricorrenza,
        "soglia_costo_usd": soglia_costo,
        "soglia_giorni": soglia_giorni,
    }


def _falsificazione_da_annotazioni(
    fid: str, annotations: dict | None
) -> tuple[str, str | None, str | None, str | None, str | None, str | None]:
    """Estrae i campi di giudizio dalle annotazioni parallele dell'operatore.
    Default onesti: stato not_exposed, prova/meccanismo/strategia/relazione
    nulli. Le annotazioni vivono in un file parallelo (non findings.json)."""
    ann = (annotations or {}).get(fid) or {}
    stato = ann.get("stato_falsificazione") or STATO_NOT_EXPOSED
    if stato not in STATI_FALSIFICAZIONE:
        stato = STATO_NOT_EXPOSED
    return (
        stato,
        ann.get("prova_decisiva"),
        ann.get("meccanismo"),
        ann.get("strategia"),
        ann.get("relazione_finding_causa"),
        ann.get("contamination"),
    )


def build_falsifiability_views(
    findings: dict,
    *,
    window: tuple[dt.date, dt.date],
    annotations: dict | None = None,
    segments_by_day: dict[str, set[str]] | None = None,
    occurrences: list[dict] | None = None,
) -> dict:
    """Viste di falsificabilita' per ogni finding, piu' campi di giudizio dalle
    annotazioni parallele.

    Args:
        findings: ``findings.json`` letto in sola lettura (il ledger primario
            congelato non viene mai modificato).
        window: finestra di osservazione (inizio, fine).
        annotations: dict ``{finding_id: {stato_falsificazione, prova_decisiva,
            meccanismo, strategia, relazione_finding_causa, contamination}}``
            opzionali, di competenza dell'operatore. Default vuoto => tutti i
            campi di giudizio nulli e stato ``not_exposed``.
        segments_by_day: ``{giorno: set(segmenti)}`` presenti quel giorno tra i
            candidati miss (dal pannello ticker-day). Serve ai denominatori di
            esposizione (giorni_esposti / non_occorrenze) quando e' nota la
            relazione finding->causa.
        occurrences: ledger delle occorrenze (#282), per i denominatori di
            esposizione per segmento.
    """
    out_findings: list[dict] = []
    for finding in findings.get("findings") or []:
        fid = finding.get("id")
        confidenza = finding.get("confidenza")
        occorrenze = finding.get("occorrenze") or []
        occorrenze_non_stimate = finding.get("occorrenze_non_stimate", 0) or 0

        # Conteggi in finestra (31/07 escluso per la carta).
        giorni_distinti: set[str] = set()
        giorni_non_stimati: set[str] = set()
        costo_finestra = 0.0
        for occ in occorrenze:
            data_str = occ.get("data")
            if not _conta_per_finestra(data_str, window):
                continue
            giorni_distinti.add(data_str)
            costo = occ.get("costo_usd")
            if costo is None:
                # occorrenza non stimabile: conta il giorno nella via ricorrenza.
                giorni_non_stimati.add(data_str)
            else:
                costo_finestra += float(costo)
        n_giorni = len(giorni_distinti)
        n_non_stimati = len(giorni_non_stimati)

        valutazione = _valuta_soglia(
            costo_finestra, n_giorni, n_non_stimati, confidenza
        )

        # campi di giudizio dalle annotazioni (default onesti).
        (
            stato,
            prova_decisiva,
            meccanismo,
            strategia,
            relazione_causa,
            contamination,
        ) = _falsificazione_da_annotazioni(fid, annotations)

        # Denominatori di esposizione: meccanici solo se e' nota la
        # relazione finding->causa. Senza relazione, null + missingness.
        giorni_esposti, non_occorrenze, evidenza_contraria, missingness = (
            _esposizione(
                relazione_causa,
                giorni_distinti,
                segments_by_day,
                window,
            )
        )

        out_findings.append(
            {
                "schema_version": FALSIFIABILITY_SCHEMA_VERSION,
                "id": fid,
                "titolo": finding.get("titolo"),
                "confidenza": confidenza,
                "stato": finding.get("stato"),
                "issue": finding.get("issue"),
                # misurati (carta):
                "giorni_distinti": n_giorni,
                "giorni_non_stimati": n_non_stimati,
                "costo_cumulato_in_finestra_usd": costo_finestra,
                "occorrenze_non_stimate": occorrenze_non_stimate,
                "dimensione": _dimensione(costo_finestra),
                # soglie (due vie OR: costo della confidenza + ricorrenza):
                "soglia": {
                    "costo_usd": valutazione["soglia_costo_usd"],
                    "giorni": valutazione["soglia_giorni"],
                    "ricorrenza_giorni": SOGLIA_NON_STIMATO_GIORNI,
                },
                "distanza_soglia": {
                    "costo_usd": valutazione["costo_usd"],
                    "giorni": valutazione["giorni"],
                    "ricorrenza_giorni": valutazione["ricorrenza_giorni"],
                },
                "oltre_soglia": valutazione["oltre_soglia"],
                "via_costo": valutazione["via_costo"],
                "via_ricorrenza": valutazione["via_ricorrenza"],
                # esposizione (meccanica se nota la relazione, altrimenti null):
                "giorni_esposti": giorni_esposti,
                "non_occorrenze": non_occorrenze,
                "evidenza_contraria": evidenza_contraria,
                "missingness": missingness,
                # giudizio operatore (annotazioni parallele, default null):
                "meccanismo": meccanismo,
                "strategia": strategia,
                "relazione_finding_causa": relazione_causa,
                "stato_falsificazione": stato,
                "prova_decisiva": prova_decisiva,
                "contamination": contamination,
            }
        )

    return {
        "schema_version": FALSIFIABILITY_SCHEMA_VERSION,
        "finestra": {"inizio": window[0].isoformat(), "fine": window[1].isoformat()},
        "escludi_data": ESCLUDI_DATA,
        "findings": out_findings,
    }


def _esposizione(
    relazione_causa: str | None,
    giorni_distinti_finding: set[str],
    segments_by_day: dict[str, set[str]] | None,
    window: tuple[dt.date, dt.date],
) -> tuple[int | None, int | None, list[str] | None, list[str]]:
    """Denominatori di falsificabilita'.

    * ``giorni_esposti`` — giorni in finestra (31/07 escluso) in cui la causa
      collegata al finding era presente tra i candidati.
    * ``non_occorrenze`` — giorni esposti senza occorrenza del finding (la
      causa c'era ma il finding non e' stato registrato): il finding e'
      falsificabile proprio se esistono.
    * ``evidenza_contraria`` — i giorni delle non-occorrenze (le date che
      avrebbero dovuto produrre un'occorrenza e non l'hanno fatto).

    Tutto ``None`` quando la relazione finding->causa non e' nota: senza il
    legame non si puo' definire il denominatore, e inventarlo confonderebbe un
    finding non testato con uno senza contro-evidenza.
    """
    if relazione_causa is None or not segments_by_day:
        return (
            None,
            None,
            None,
            ["relazione_finding_causa_non_nota"],
        )
    giorni_esposti = 0
    non_occorrenze = 0
    evidenza: list[str] = []
    for day, segments in sorted(segments_by_day.items()):
        if not _conta_per_finestra(day, window):
            continue
        if relazione_causa not in (segments or set()):
            continue
        giorni_esposti += 1
        if day not in giorni_distinti_finding:
            non_occorrenze += 1
            evidenza.append(day)
    return giorni_esposti, non_occorrenze, evidenza, []

# ---------------------------------------------------------------------------
# Propagazione del contamination alle metriche dipendenti (AC3).
# ---------------------------------------------------------------------------

# Metriche dipendenti che un finding contaminato infetta: la somma dei costi
# cumulati totale e il conteggio dei finding oltre soglia non sono piu'
# "puliti" se un finding che vi contribuisce e' contaminato.
METRICA_COSTO_TOTALE = "costo_cumulato_totale_usd"
METRICA_OLTRE_SOGLIA = "oltre_soglia_count"


def _normalizza_contamination(value) -> list[str]:
    """Il contamination flag puo' essere una singola stringa o una lista di
    tipi (attribution / segno / tracciabilita'). Lo normalizza a lista."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def build_contamination_summary(views: dict) -> dict:
    """Propaga i contamination flag dei finding alle metriche dipendenti.

    Un finding contaminato non e' rimosso (la vista e' parallela, nulla viene
    cancellato): la sua quota di costo e il suo attraversamento di soglia
    vengono CONTATI A PARTE, e le metriche che li sommano sono marcate
    contaminate con l'elenco dei finding che le infettano.

    Una metrica pulita riporta il valore solo dei finding non contaminati;
    quella contaminata riporta il valore dei soli finding contaminati. La
    somma delle due riprodurrebbe il totale lordo (utile per audit), ma non le
    si medie: il costo contaminato non e' evidenza pulita.
    """
    findings = views.get("findings") or []
    contaminati = []
    costo_pulito = 0.0
    costo_contaminato = 0.0
    oltre_pulito = 0
    oltre_contaminato = 0
    propaga_costo: list[str] = []
    propaga_oltre: list[str] = []

    for f in findings:
        cont = _normalizza_contamination(f.get("contamination"))
        costo = f.get("costo_cumulato_in_finestra_usd") or 0.0
        oltre = bool(f.get("oltre_soglia"))
        if cont:
            contaminati.append({"id": f.get("id"), "contamination": cont})
            costo_contaminato += float(costo)
            if oltre:
                oltre_contaminato += 1
            propaga_costo.append(f.get("id"))
            if oltre:
                propaga_oltre.append(f.get("id"))
        else:
            costo_pulito += float(costo)
            if oltre:
                oltre_pulito += 1

    return {
        "schema_version": FALSIFIABILITY_SCHEMA_VERSION,
        "findings_contaminati": contaminati,
        "costo_pulito_usd": costo_pulito,
        "costo_contaminato_usd": costo_contaminato,
        "oltre_soglia_pulito": oltre_pulito,
        "oltre_soglia_contaminato": oltre_contaminato,
        # propagazione: per ciascuna metrica dipendente, quali finding la
        # infettano. Una metrica assente dalla mappa e' pulita.
        "propagazione": {
            METRICA_COSTO_TOTALE: propaga_costo,
            METRICA_OLTRE_SOGLIA: propaga_oltre,
        },
    }


# ---------------------------------------------------------------------------
# Validator: prova decisiva + read-only, stato ammesso (AC2).
# ---------------------------------------------------------------------------


def validate_falsifiability(
    views: dict,
    *,
    annotations: dict | None = None,
    previous_annotations: dict | None = None,
) -> dict:
    """Controlla le invariabili di falsificazione:

    * ``stato_falsificazione`` ammesso (supported / contradicted / not_exposed).
      Si controlla sull'annotazione GREZZA quando e' passata: la vista normalizza
      gia' gli stati non ammessi a ``not_exposed``, ma il validator deve
      segnalare l'errore di input, non nasconderlo.
    * ``prova_decisiva`` non vuota quando lo stato e' un verdetto
      (supported / contradicted): un verdetto senza prova decisiva e'
      un'opinione, non una falsificazione.
    * ``prova_decisiva`` read-only: una volta registrata in
      ``previous_annotations``, non cambia ne' sparisce. E' un fatto
      registrato (read-only), non un parametro da ri-tarare.

    Ritorna ``{"ok": bool, "errors": [...], "warnings": [...]}``.
    """
    res = {"ok": True, "errors": [], "warnings": []}

    def fail(msg):
        res["errors"].append(msg)

    for f in views.get("findings") or []:
        fid = f.get("id")
        stato = f.get("stato_falsificazione")

        # stato ammesso: si controlla sull'annotazione grezza se disponibile,
        # altrimenti sul valore normalizzato della vista (sempre ammesso).
        raw_stato = None
        if annotations and fid in annotations:
            raw_stato = (annotations[fid] or {}).get("stato_falsificazione")
        if raw_stato is not None and raw_stato not in STATI_FALSIFICAZIONE:
            fail(
                f"{fid}: stato_falsificazione non ammesso {raw_stato!r} "
                f"(atteso uno di {sorted(STATI_FALSIFICAZIONE)})"
            )

        # prova decisiva obbligatoria con un verdetto.
        if stato in (STATO_SUPPORTED, STATO_CONTRADICTED):
            if not f.get("prova_decisiva"):
                fail(
                    f"{fid}: stato {stato!r} richiede una prova_decisiva "
                    f"registrata (un verdetto senza prova non falsifica)"
                )

        # prova decisiva read-only: immutabile una volta scritta.
        if previous_annotations:
            prev = (previous_annotations.get(fid) or {}).get("prova_decisiva")
            curr = f.get("prova_decisiva")
            if prev and curr != prev:
                fail(
                    f"{fid}: prova_decisiva e' read-only, non si retro-aggiorna "
                    f"(era {prev!r}, ora {curr!r})"
                )

    res["ok"] = not res["errors"]
    return res


# ---------------------------------------------------------------------------
# Status events: snapshot di falsificabilita' parallelo per finding.
# ---------------------------------------------------------------------------


def build_status_events_falsifiability(views: dict) -> list[dict]:
    """Snapshot dello stato di falsificazione di ogni finding, parallelo agli
    ``status_events`` del ledger (#282). ``findings.json`` registra solo lo
    stato corrente del finding (aperto/in_roadmap...), non la falsificazione:
    questo snapshot la affianca senza toccare il ledger primario.

    Lo storico completo delle transizioni di falsificazione richiede un log
    append-only separato (wiring post-freeze, fuori perimetro): qui' si emette
    uno snapshot dichiarato tale, come fa #282 per lo stato del finding.
    """
    events: list[dict] = []
    for f in views.get("findings") or []:
        events.append(
            {
                "kind": "falsifiability_snapshot",
                "finding_id": f.get("id"),
                "stato_falsificazione": f.get("stato_falsificazione"),
                "oltre_soglia": f.get("oltre_soglia"),
                "contamination": f.get("contamination"),
                "giorni_distinti": f.get("giorni_distinti"),
            }
        )
    return events


# ---------------------------------------------------------------------------
# SYNTHESIS / weekly rollup deterministici (AC4).
# ---------------------------------------------------------------------------

# Campi della firma di un finding che il digest confronta per isolare i
# cambi: solo cio' che puo' "cambiare" entra nella firma (id/titolo sono
# definizione, non cambi).
_CAMPI_CONFRONTO = (
    ("oltre_soglia", None),
    ("stato_falsificazione", STATO_NOT_EXPOSED),
    ("contamination", None),
    ("giorni_distinti", 0),
    ("costo_cumulato_in_finestra_usd", 0.0),
)


def _firma_finding(f: dict) -> dict:
    """Firma comparabile di un finding per il calcolo dei cambi."""
    firma = {"id": f.get("id")}
    for campo, default in _CAMPI_CONFRONTO:
        firma[campo] = f.get(campo, default)
    return firma


def _cambi(current: dict, previous: dict | None) -> list[dict]:
    """Isola i soli cambi fra la firma corrente e quella precedente.

    * un finding nuovo (non nel precedente) -> ``campo = "nuovo"``.
    * un campo modificato -> ``{campo, da, a}``.
    I finding invariati non compaiono: il digest mostra SOLO i cambi, non
    conferma cio' che e' fermo (evita il confirmation bias della issue)."""
    previous = previous or {}
    prev_by_id = {f["id"]: f for f in previous.get("findings") or [] if f.get("id")}
    cambi: list[dict] = []
    for f in current.get("findings") or []:
        fid = f.get("id")
        if fid not in prev_by_id:
            cambi.append({"finding_id": fid, "campo": "nuovo", "da": None, "a": fid})
            continue
        prev = prev_by_id[fid]
        for campo, default in _CAMPI_CONFRONTO:
            da = prev.get(campo, default)
            a = f.get(campo, default)
            if da != a:
                cambi.append({"finding_id": fid, "campo": campo, "da": da, "a": a})
    return cambi


def _soglie(views: dict) -> list[dict]:
    """Stato di soglia di ogni finding: oltre/sotto e distanza."""
    out: list[dict] = []
    for f in views.get("findings") or []:
        out.append(
            {
                "finding_id": f.get("id"),
                "confidenza": f.get("confidenza"),
                "oltre_soglia": f.get("oltre_soglia"),
                "giorni_distinti": f.get("giorni_distinti"),
                "distanza_soglia": f.get("distanza_soglia"),
            }
        )
    return out


def _build_digest(
    views: dict,
    contamination_summary: dict,
    *,
    scope: dict,
    previous_digest: dict | None = None,
    economic_pnl: dict | None = None,
    integrity: dict | None = None,
) -> dict:
    # contamination_summary resta un parametro (firma stabile, usato dai
    # chiamanti) ma non viene piu' proiettato nel digest: l'AC (#286,
    # criterio 1) dichiara SOLO le 4 sezioni sotto. Il contamination summary
    # e' gia' esposto top-level dall'orchestratore
    # (scripts/build_longitudinal_panels.py, falsifiability.contamination_summary):
    # una copia annidata qui era una quinta sezione non dichiarata.
    return {
        "schema_version": FALSIFIABILITY_SCHEMA_VERSION,
        "scope": scope,
        "cambi": _cambi(_firma_views(views), previous_digest),
        "soglie": _soglie(views),
        "pnl_economico": economic_pnl,
        "integrita": integrity,
    }


def _firma_views(views: dict) -> dict:
    """Views ridotte alla sola firma confrontabile (per i cambi)."""
    return {"findings": [_firma_finding(f) for f in views.get("findings") or []]}


def build_synthesis(
    views: dict,
    contamination_summary: dict,
    *,
    previous_digest: dict | None = None,
    economic_pnl: dict | None = None,
    integrity: dict | None = None,
) -> dict:
    """Digest deterministico sulla finestra intera. Mostra SOLO:

    * ``cambi`` — cio' che e' mutato rispetto al digest precedente (nuovi
      finding, attraversamenti di soglia, transizioni di falsificazione, nuovi
      contamination, crescita di giorni/costo). Senza precedente, tutto e'
      nuovo.
    * ``soglie`` — stato di soglia di ogni finding (oltre/sotto, distanza).
    * ``pnl_economico`` — headline del P&L economico (input: lo calcola
      l'orchestratore da ``economic_pnl``; qui e' misura, non taratura).
    * ``integrita`` — esito della validazione del ledger (input).

    Niente conferme di cio' che e' fermo: il confirmation bias nasce
    dall'elencare occorrenze senza denominatore. Il digest elenca solo i
    cambi e lo stato di soglia, che e' il criterio pre-registrato."""
    scope = {"tipo": "synthesis", "finestra": views.get("finestra")}
    return _build_digest(
        views,
        contamination_summary,
        scope=scope,
        previous_digest=previous_digest,
        economic_pnl=economic_pnl,
        integrity=integrity,
    )


def build_weekly_rollup(
    views: dict,
    contamination_summary: dict,
    *,
    settimana: str,
    previous_digest: dict | None = None,
    economic_pnl: dict | None = None,
    integrity: dict | None = None,
) -> dict:
    """Rollup settimanale deterministico. Stessa struttura del synthesis ma
    con scope ``weekly`` e ``settimana`` (ISO week). I ``cambi`` sono
    riferiti al digest della settimana precedente, cosi' isolano i soli
    eventi di quella settimana. Le views devono essere costruite con la
    finestra della settimana (l'orchestratore le ricrea per sottoperiodo)."""
    scope = {"tipo": "weekly", "settimana": settimana, "finestra": views.get("finestra")}
    return _build_digest(
        views,
        contamination_summary,
        scope=scope,
        previous_digest=previous_digest,
        economic_pnl=economic_pnl,
        integrity=integrity,
    )
