"""Funnel v2 a due assi per il dossier alpha-miss (#281).

Vista PARALLELA alla serie legacy (`miss_cause`, #208): i conteggi legacy e la
metrica NO_NEWS pre-registrata restano intatti (freeze #171). Nessun dato
storico viene riscritto — il modulo e' puro, non scrive niente.

Due assi ortogonali, perche' la serie legacy rispondeva a una sola domanda e
fondeva risposte opposte:

- `actionability` — cosa il motore POTREBBE fare sul mover, dato il vincolo
  long-only del book:
      EXIT_RISK         detenuto, seduta negativa (uscita valutabile)
      PASSIVE_EXPOSURE  detenuto, seduta favorevole (esposizione, non miss)
      ENTRY_OPPORTUNITY non detenuto, rialzo (ingresso valutabile)
      NON_ACTIONABLE   non detenuto, ribasso (niente short: accessible = 0
                        verificato, #280 — non e' un miss economico)
      OUT_OF_SCOPE     fuori dall'universo commerciabile (benchmark ETF)
  La vecchia serie `catturati` confondeva posizioni vecchie e decisioni nuove:
  l'asse separa chi e' gia' a libro da chi richiede una decisione.

- `pipeline` — dove la catena della decisione d'INGRESSO si e' fermata, per i
  soli mover ENTRY_OPPORTUNITY, nello stadio che il funnel incontra per primo:
      NO_RELEVANT_NEWS  nessun articolo, o solo SECTOR_MACRO/UNKNOWN/TAG_UNCONFIRMED
      LATE_NEWS         articolo ISSUER_SPECIFIC ma non tempestivo (#279)
      ENTITY_ERROR      solo FALSE_ENTITY_MATCH / IRRELEVANT_FANOUT (#279)
      NO_SIGNAL         notizia tempestiva, nessun punteggio
      WRONG_SIGN        nessun punteggio positivo (rialzo non detenuto)
      BELOW_GATE       segno giusto, |score| sotto il gate
      FALLBACK_REJECT   tutti i punteggi utilizzabili sono fallback FinBERT (#108)
      RANKED_OUT        mai selezionato dal ranker (ledger #294)
      RISK_BLOCK        selezionato, bloccato da un guard
      ORDER_FAIL        ordine mai eseguito (o mai partito)
      BAD_FILL          fill sopra il close: con exit EOD_close niente e'
                        catturabile per costruzione, nessuna soglia inventata
      CAUGHT            eseguito

Criterio 3: il segno viene dal campo firmato dello score, mai ricostruito da
`abs(score)` o da reason. Un -0.45 su un rialzo non detenuto e' WRONG_SIGN,
non un segnale sopra il gate: la classificazione per magnitudo (legacy) non
riesce a dirlo, quella firmata si`.

Criterio 4 — mapping legacy <-> v2, documentato nel blocco `mapping_legacy_v2`
pubblicato nel dossier:
      NO_NEWS (legacy)                -> NO_RELEVANT_NEWS | LATE_NEWS | ENTITY_ERROR
      NO_SIGNAL                       -> NO_SIGNAL
      THIN_NEUTRAL                    -> BELOW_GATE (|score| < thin e' anche < gate)
      OFF_TOPIC / OFF_TOPIC_NON_DECIDIBILE -> ENTITY_ERROR | NO_RELEVANT_NEWS
                                        (il funnel usa la coverage #279, non il
                                        testo isolato della riga)
      BELOW_GATE                      -> WRONG_SIGN | BELOW_GATE (la serie v2
                                        separa il segno dalla magnitudo)
      IN_PORTAFOGLIO                  -> non e' un miss: EXIT_RISK/PASSIVE_EXPOSURE
      NON_CLASSIFICATO                -> FALLBACK_REJECT | RANKED_OUT | RISK_BLOCK
                                        | ORDER_FAIL | BAD_FILL | CAUGHT (il
                                        funnel v2 continua oltre il gate, dove la
                                        serie legacy si fermava dichiarando
                                        "sopra il gate: non un miss")
      FALLBACK_REJECT/RANKED_OUT/RISK_BLOCK/ORDER_FAIL/BAD_FILL/CAUGHT
                                      -> nessun equivalente legacy: la serie v2
                                        misura stadi che il classificatore #208
                                        non guardava.

Le soglie NON vivono qui: `soglia_gate` e' un argomento, la stessa letta a monte
dalla Redis del feedback (fallback al baseline, #208). Il gate e' inclusivo
(score >= soglia passa), la stessa convenzione di `miss_cause`. La decisione
e' deterministica: stessi input, stesso output.
"""

from __future__ import annotations

from typing import Any

FUNNEL_VERSION = "1.0"

# Asse actionability: cosa il motore puo' fare sul mover.
ACTIONABILITY_STAGES = (
    "ENTRY_OPPORTUNITY",
    "EXIT_RISK",
    "PASSIVE_EXPOSURE",
    "NON_ACTIONABLE",
    "OUT_OF_SCOPE",
)

# Asse pipeline: stadio della catena d'ingresso in cui il candidato si ferma.
# L'ordine e' quello della issue #281 ed e' anche l'ordine di valutazione.
PIPELINE_STAGES = (
    "NO_RELEVANT_NEWS",
    "LATE_NEWS",
    "ENTITY_ERROR",
    "NO_SIGNAL",
    "WRONG_SIGN",
    "BELOW_GATE",
    "FALLBACK_REJECT",
    "RANKED_OUT",
    "RISK_BLOCK",
    "ORDER_FAIL",
    "BAD_FILL",
    "CAUGHT",
)

# Categorie #279 che provano un errore di entita': l'articolo esiste ma il
# soggetto non e' l'emittente del ticker scorato.
RELEVANZA_ENTITY_ERROR = ("FALSE_ENTITY_MATCH", "IRRELEVANT_FANOUT")

# Reason code #294 che dichiarano il ranker soddisfatto (l'intento e' tradabile
# e prosegue verso guard/ordine). is_tradable e' settato proprio cosi' in
# src/strategies/s4/strategy.py; il reason code resta il criterio primario.
REASON_SELEZIONATO = "RANK_SELECTED"

MAPPING_LEGACY_V2 = {
    "NO_NEWS": "NO_RELEVANT_NEWS | LATE_NEWS | ENTITY_ERROR (v2: la coverage "
               "#279 separa assente / tardi / entita' sbagliata)",
    "NO_SIGNAL": "NO_SIGNAL (invariato)",
    "THIN_NEUTRAL": "BELOW_GATE (|score| < thin e' anche < gate)",
    "OFF_TOPIC": "ENTITY_ERROR | NO_RELEVANT_NEWS (v2: coverage #279 per "
                 "articolo, non testo isolato della riga)",
    "OFF_TOPIC_NON_DECIDIBILE": "NO_RELEVANT_NEWS (UNKNOWN non e' promosso)",
    "BELOW_GATE": "WRONG_SIGN | BELOW_GATE (v2: il segno e' separato dalla "
                  "magnitudo, dal campo firmato)",
    "IN_PORTAFOGLIO": "non e' un miss: EXIT_RISK | PASSIVE_EXPOSURE "
                      "(l'asse actionability lo separa)",
    "NON_CLASSIFICATO": "FALLBACK_REJECT | RANKED_OUT | RISK_BLOCK | "
                        "ORDER_FAIL | BAD_FILL | CAUGHT (v2: continua oltre il "
                        "gate, la serie legacy si fermava)",
    "_v2_senza_legacy": "FALLBACK_REJECT, RANKED_OUT, RISK_BLOCK, ORDER_FAIL, "
                        "BAD_FILL, CAUGHT non hanno equivalente legacy",
}


def _as_bool(value: Any) -> bool:
    return bool(value)


def classify_actionability(mover: dict) -> str:
    """Asse actionability: cosa il motore puo' fare sul mover.

    `return` e' il rendimento firmato close-to-close della seduta. Un mover e'
    tale perche' |return| >= soglia_mover a monte, quindi il segno e' deciso.
    """
    if not mover.get("in_universo", True):
        return "OUT_OF_SCOPE"
    if _as_bool(mover.get("held")):
        return "EXIT_RISK" if mover.get("return", 0.0) < 0 else "PASSIVE_EXPOSURE"
    return "ENTRY_OPPORTUNITY" if mover.get("return", 0.0) > 0 else "NON_ACTIONABLE"


def _stage_notizia(articoli: dict | None) -> tuple[str, dict]:
    """Stadio della notizia dalla coverage #279, con precedenza dichiarata.

    effective_timely (ISSUER_SPECIFIC e tempestivo) fa passare; a seguire la
    notizia c'e' ma non e' agibile (LATE_NEWS), poi c'e' ma parla d'altro
    (ENTITY_ERROR), e solo in ultimo manca del tutto o e' indecidibile.
    UNKNOWN/TAG_UNCONFIRMED/SECTOR_MACRO non sono promossi (#279).
    """
    if not articoli:
        return "NO_RELEVANT_NEWS", {"articoli": None}
    effective = int(articoli.get("effective_timely_articles") or 0)
    rilevanza = articoli.get("rilevanza") or {}
    if effective > 0:
        return "NOTIZIA_AGGIBILE", {"effective_timely_articles": effective}
    if int(rilevanza.get("ISSUER_SPECIFIC") or 0) > 0:
        return "LATE_NEWS", {"issuer_specific_non_tempestivi":
                             rilevanza.get("ISSUER_SPECIFIC")}
    if any(rilevanza.get(cat) for cat in RELEVANZA_ENTITY_ERROR):
        return "ENTITY_ERROR", {cat: rilevanza[cat]
                                for cat in RELEVANZA_ENTITY_ERROR
                                if rilevanza.get(cat)}
    return "NO_RELEVANT_NEWS", {"rilevanza": dict(rilevanza)}


def _punteggi(segnali: list[dict]) -> list[float]:
    """Punteggi firmati del candidato. Il campo e' gia' firmato: si copia il
    valore, non si ricostruisce il segno (criterio 3)."""
    return [float(s.get("score")) for s in (segnali or []) if s.get("score") is not None]


def _selezionato(intenti: list[dict]) -> tuple[bool, list[str], dict | None]:
    """True se il ranker ha selezionato il simbolo, i reason osservati e
    l'intento eseguito (per il P&L), se esiste."""
    reason_codes: list[str] = []
    selezionato = False
    eseguito: dict | None = None
    for intento in intenti or []:
        reason = intento.get("final_reason_code")
        if reason:
            if reason not in reason_codes:
                reason_codes.append(reason)
        if reason == REASON_SELEZIONATO or _as_bool(intento.get("is_tradable")):
            selezionato = True
        if intento.get("trade_id") is not None and eseguito is None:
            eseguito = intento
    return selezionato, reason_codes, eseguito


def classify_pipeline(mover: dict, soglia_gate: float) -> tuple[str | None, dict]:
    """Stadio della pipeline d'ingresso per un mover, con l'evidenza usata.

    Restituisce (stadio, evidence). Lo stadio e' il primo che ferma il
    candidato nell'ordine di PIPELINE_STAGES.
    """
    # --- notizia (#279) ----------------------------------------------------
    stadio, evidence = _stage_notizia(mover.get("articoli"))
    if stadio != "NOTIZIA_AGGIBILE":
        return stadio, evidence
    del stadio

    # --- segnale ------------------------------------------------------------
    punteggi = _punteggi(mover.get("segnali") or [])
    if not punteggi:
        return "NO_SIGNAL", {"n_segnali": 0, "effective_timely_articles":
                             mover["articoli"].get("effective_timely_articles")}

    # --- segno e gate, dal campo firmato (criterio 3) -----------------------
    # Per un ingresso long conta il massimo FIRMATO, non il massimo in
    # magnitudo: -0.45 non e' "un segnale sopra il gate", e' il segno sbagliato.
    massimo_firmato = max(punteggi)
    if massimo_firmato <= 0:
        return "WRONG_SIGN", {"score_firmato": massimo_firmato}
    if massimo_firmato < soglia_gate:
        return "BELOW_GATE", {"score_firmato": massimo_firmato, "soglia_gate": soglia_gate}

    # --- filtro fallback (#108) ----------------------------------------------
    qualificanti = [
        s for s in (mover.get("segnali") or [])
        if s.get("score") is not None
        and float(s["score"]) > 0
        and float(s["score"]) >= soglia_gate
    ]
    if qualificanti and all(_as_bool(s.get("fallback")) for s in qualificanti):
        return "FALLBACK_REJECT", {
            "score_firmato": massimo_firmato,
            "n_qualificanti_fallback": len(qualificanti),
        }

    # --- ranker (#294) -------------------------------------------------------
    selezionato, reason_codes, eseguito = _selezionato(mover.get("intenti") or [])
    if not selezionato:
        return "RANKED_OUT", {
            "reason_codes": reason_codes,
            "intenti_assenti": not bool(mover.get("intenti")),
        }

    # --- guard ---------------------------------------------------------------
    guard = [str(g.get("decision")) for g in (mover.get("guard") or [])
             if g.get("decision")]
    if guard:
        return "RISK_BLOCK", {"guard": guard, "reason_codes": reason_codes}

    # --- ordine e fill --------------------------------------------------------
    ordine = mover.get("ordine") or {}
    if not ordine or not ordine.get("submitted_at"):
        return "ORDER_FAIL", {"ordine": "mai_inviato"}
    if not ordine.get("filled_at"):
        return "ORDER_FAIL", {
            "order_id": ordine.get("order_id"),
            "lookup_error": ordine.get("lookup_error"),
        }

    close = mover.get("close")
    fill_price = ordine.get("fill_price")
    if close is not None and fill_price is not None and float(fill_price) > float(close):
        return "BAD_FILL", {
            "fill_price": float(fill_price), "close": float(close),
            "exit_policy": "EOD_close",
        }
    return "CAUGHT", {
        "fill_price": fill_price, "close": close,
        "trade_id": ordine.get("trade_id") or (eseguito or {}).get("trade_id"),
    }


def _net_profitable(mover: dict) -> bool | None:
    """True/False dal P&L realizzato dell'intento eseguito; None se il trade e'
    ancora aperto o ambiguo. Nessun P&L congetturale."""
    eseguiti = [i for i in (mover.get("intenti") or []) if i.get("trade_id") is not None]
    if len(eseguiti) != 1:
        return None
    pnl = eseguiti[0].get("pnl_realizzato")
    if pnl is None:
        return None
    return float(pnl) > 0


def _rapporto(numeratore: int, denominatore: int, definizione: str) -> dict:
    """Rapporto con denominatore esplicito. None se il denominatore e' 0:
    nessun rapporto inventato su una giornata senza casi."""
    return {
        "numeratore": numeratore,
        "denominatore": denominatore,
        "valore": numeratore / denominatore if denominatore else None,
        "definizione": definizione,
    }


def build_funnel(movers: list[dict], soglia_gate: float) -> dict:
    """Costruisce il blocco `funnel_v2` del dossier. Puro e deterministico.

    Ogni mover riceve ENTRAMBI gli assi. La pipeline valuta solo chi ha una
    decisione d'ingresso da spiegare (ENTRY_OPPORTUNITY): i mover detenuti, i
    ribassi non detenuti e i fuori-universo sono esclusi con motivo esplicito,
    cosi' la partizione resta completa e leggibile.
    """
    righe: list[dict] = []
    conteggi_actionability: dict[str, int] = {s: 0 for s in ACTIONABILITY_STAGES}
    conteggi_pipeline: dict[str, int] = {s: 0 for s in PIPELINE_STAGES}
    esclusi: dict[str, int] = {}

    for mover in movers:
        actionability = classify_actionability(mover)
        conteggi_actionability[actionability] += 1
        pipeline: str | None = None
        motivo: str | None = None
        evidence: dict = {}
        if actionability == "ENTRY_OPPORTUNITY":
            pipeline, evidence = classify_pipeline(mover, soglia_gate)
            conteggi_pipeline[pipeline] += 1
        else:
            motivo = {
                "OUT_OF_SCOPE": "fuori_universo",
                "EXIT_RISK": "held",
                "PASSIVE_EXPOSURE": "held",
                "NON_ACTIONABLE": "non_actionable_long_only",
            }[actionability]
            esclusi[motivo] = esclusi.get(motivo, 0) + 1
        righe.append({
            "symbol": mover.get("symbol"),
            "rendimento": mover.get("return"),
            "held": _as_bool(mover.get("held")),
            "actionability": actionability,
            "pipeline": pipeline,
            "pipeline_escluso_motivo": motivo,
            "evidence": evidence,
            "legacy_causa": mover.get("legacy_causa"),
            "net_profitable": _net_profitable(mover) if pipeline == "CAUGHT" else None,
        })

    # --- KPI distinti (criterio 2) -------------------------------------------
    entry_rows = [r for r in righe if r["actionability"] == "ENTRY_OPPORTUNITY"]
    notizia_agibile = [
        r for r in entry_rows
        if r["pipeline"] not in ("NO_RELEVANT_NEWS", "LATE_NEWS", "ENTITY_ERROR")
    ]
    con_segnale_qualificante = [
        r for r in entry_rows
        if r["pipeline"] not in ("NO_RELEVANT_NEWS", "LATE_NEWS", "ENTITY_ERROR",
                                "NO_SIGNAL", "WRONG_SIGN", "BELOW_GATE",
                                "FALLBACK_REJECT")
    ]
    arrivati_all_ordine = [r for r in entry_rows
                           if r["pipeline"] in ("ORDER_FAIL", "BAD_FILL", "CAUGHT")]
    eseguiti = [r for r in arrivati_all_ordine
                if r["pipeline"] in ("BAD_FILL", "CAUGHT")]
    catturati_profittevoli = [r for r in eseguiti if r["pipeline"] == "CAUGHT"
                              and r["net_profitable"] is True]

    kpi = {
        # I mover gia' a libro non sono miss: contarli insieme ai candidati
        # d'ingresso e' la confusione che la issue vuole eliminare.
        "held_at_open": {
            "mover_held": conteggi_actionability["EXIT_RISK"]
            + conteggi_actionability["PASSIVE_EXPOSURE"],
            "exit_risk": conteggi_actionability["EXIT_RISK"],
            "passive_exposure": conteggi_actionability["PASSIVE_EXPOSURE"],
        },
        "active_signal_recall": _rapporto(
            len(con_segnale_qualificante), len(notizia_agibile),
            "mover ENTRY_OPPORTUNITY con notizia tempestiva che hanno prodotto "
            "un punteggio qualificante (segno giusto, sopra il gate, non "
            "fallback) / tutti i mover ENTRY_OPPORTUNITY con notizia tempestiva",
        ),
        "execution_conversion": _rapporto(
            len(eseguiti), len(arrivati_all_ordine),
            "mover arrivati allo stadio dell'ordine che sono stati eseguiti "
            "(fill, anche cattivo) / tutti i mover arrivati all'ordine",
        ),
        "profitable_capture": _rapporto(
            len(catturati_profittevoli), len(entry_rows),
            "ingressi catturati con P&L realizzato positivo / tutti i mover "
            "ENTRY_OPPORTUNITY della seduta (end-to-end)",
        ),
    }

    # Pubblica solo gli stadi osservati, nell'ordine canonico.
    return {
        "funnel_version": FUNNEL_VERSION,
        "soglia_gate": soglia_gate,
        "nota_freeze": (
            "vista v2 parallela: i conteggi legacy (miss_cause #208) e la "
            "metrica NO_NEWS pre-registrata restano intatti (freeze #171); "
            "nessun dato storico riscritto"
        ),
        "conteggi_actionability": {
            s: n for s, n in conteggi_actionability.items() if n
        },
        "conteggi_pipeline": {
            s: n for s, n in conteggi_pipeline.items() if n
        },
        "esclusi_pipeline": esclusi,
        "kpi": kpi,
        "mapping_legacy_v2": MAPPING_LEGACY_V2,
        "righe": righe,
    }