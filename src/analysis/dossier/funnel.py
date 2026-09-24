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
e' deterministica: stessi input, stesso output. I KPI pubblicati mantengono i
nomi della specifica consolidata: `held_at_open_rate`, `active_signal_recall`,
`execution_conversion_rate`, `profitable_capture_rate` e
`avoidable_miss_count` (con missingness separata).

Lato uscita (#567): per i mover EXIT_RISK la vecchia serie li contava ma
li droppava in `esclusi_pipeline.held` (con PASSIVE_EXPOSURE nello stesso
bucket, indistinguibili). Il funnel v2 ora distingue `held_falling` da
`held_rising` e aggiunge un asse `pipeline_uscita` con sei stadi paralleli
a quelli d'ingresso:
    NO_EXIT_SIGNAL        EXIT_RISK senza segnali di sortita nella seduta
    STALE_EXIT_SIGNAL     segnali presenti ma tutti pre-apertura RTH
    EXIT_BELOW_THRESHOLD  segnale attuale, segno giusto, |s| < soglia_exit
    EXIT_WRONG_SIGN       segnale presente, segno sbagliato per la direzione
    EXIT_BLOCKED          segnale qualificante, guard ha bloccato la SELL
    EXITED                posizione effettivamente chiusa (riga `chiusure`)

Anche qui la soglia (`soglia_exit`) e' un argomento: il freeze #171 vieta
di tararla qui. Stesso criterio 3 (segno dal campo firmato), stesso mapping
dichiarato. Vista parallela alla v1: la serie pre-registrata
(`conteggi_pipeline` d'ingresso, KPI d'ingresso, legacy causa) resta intatta.
"""

from __future__ import annotations

from typing import Any

from src.analysis.dossier.miss_cause import NON_CLASSIFICATO

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

# Asse pipeline_uscita (#567): stadio della catena d'uscita sui mover
# detenuti in ribasso, parallelo e simmetrico al PIPELINE_STAGES d'ingresso.
# Stessi criteri (3: segno firmato, 4: mapping dichiarato), stesso vincolo:
# la soglia d'uscita e' un argomento — il charter decide la floor, non qui.
EXIT_PIPELINE_STAGES = (
    "NO_EXIT_SIGNAL",         # EXIT_RISK senza segnali di sortita nella seduta
    "STALE_EXIT_SIGNAL",      # segnali presenti ma tutti pre-apertura RTH
    "EXIT_BELOW_THRESHOLD",   # segnale attuale, segno giusto, |s| < soglia_exit
    "EXIT_WRONG_SIGN",        # segnale presente, segno sbagliato per la direzione
    "EXIT_BLOCKED",           # segnale d'uscita qualificante, guard ha bloccato
    "EXITED",                 # posizione chiusa intraday (riga in `chiusure`)
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
    punteggi = []
    for segnale in segnali or []:
        score = segnale.get("score")
        if score is not None:
            punteggi.append(float(score))
    return punteggi


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

    # --- ordine e fill --------------------------------------------------------
    # Una riga riassume il punto piu' profondo raggiunto dal simbolo nella
    # seduta. Se un tentativo precedente e' stato bloccato ma un tentativo
    # successivo ha generato un ordine, il guard non puo' cancellare l'esito
    # osservato a valle.
    ordine = mover.get("ordine") or {}
    if ordine:
        if not ordine.get("submitted_at"):
            return "ORDER_FAIL", {
                "ordine": "mai_inviato",
                "order_id": ordine.get("order_id"),
                "lookup_error": ordine.get("lookup_error"),
            }
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
                "eod_net_pnl": ordine.get("eod_net_pnl"),
            }
        return "CAUGHT", {
            "fill_price": fill_price, "close": close,
            "trade_id": ordine.get("trade_id") or (eseguito or {}).get("trade_id"),
            "eod_net_pnl": ordine.get("eod_net_pnl"),
        }

    # --- guard ---------------------------------------------------------------
    guard = [str(g.get("decision")) for g in (mover.get("guard") or [])
             if g.get("decision")]
    if guard:
        return "RISK_BLOCK", {"guard": guard, "reason_codes": reason_codes}
    return "ORDER_FAIL", {"ordine": "mai_inviato"}


def _net_profitable(mover: dict) -> bool | None:
    """True/False dal mark fill->close netto di costi del giorno.

    Il P&L realizzato e' solo un fallback per le righe storiche senza quantita'
    di fill: puo' appartenere a una seduta successiva e non deve sovrascrivere
    il verdetto EOD quando questo e' misurabile.
    """
    eod_net = (mover.get("ordine") or {}).get("eod_net_pnl")
    if eod_net is not None:
        return float(eod_net) > 0
    eseguiti = [i for i in (mover.get("intenti") or []) if i.get("trade_id") is not None]
    if len(eseguiti) != 1:
        return None
    pnl = eseguiti[0].get("pnl_realizzato")
    if pnl is None:
        return None
    return float(pnl) > 0


def _rapporto(
    numeratore: int,
    denominatore: int,
    definizione: str,
    floor: float | None = None,
) -> dict:
    """Rapporto con denominatore esplicito. None se il denominatore e' 0:
    nessun rapporto inventato su una giornata senza casi.

    `floor` (#567): se il chiamante dichiara una floor di n (la carta
    S4_kill_criterion.yaml prevede INSUFFICIENT_N outrankante PASS/FAIL),
    la risposta include `sufficienza`: 'ok' se denom >= floor, 'insufficient_n'
    altrimenti. Senza floor dichiarata il flag e' 'unset': niente opinioni
    inventate durante il freeze (#171), la soglia la decide l'operatore.
    Il rapporto viene comunque pubblicato: `sufficienza` segnala, non cancella.
    """
    valore = numeratore / denominatore if denominatore else None
    if floor is None:
        sufficienza = "unset"
    elif denominatore >= floor:
        sufficienza = "ok"
    else:
        sufficienza = "insufficient_n"
    return {
        "numeratore": numeratore,
        "denominatore": denominatore,
        "valore": valore,
        "definizione": definizione,
        "sufficienza": sufficienza,
    }


# --- Lato uscita (#567) ------------------------------------------------------
#
# Stessi criteri dell'asse d'ingresso:
# 3 — segno dal campo firmato dello score, mai ricostruito da abs o reason;
# 4 — mapping dichiarato (vedi blocco `mapping_exit_legacy` nel dossier, se
#     richiesto da una issue futura; qui non e' necessario perche' il lato
#     uscita non rimpiazza alcuna serie pre-registrata).


def classify_exit_pipeline(
    mover: dict, soglia_exit: float | None, data: str | None = None
) -> tuple[str | None, dict]:
    """Stadio della pipeline d'uscita per un mover EXIT_RISK.

    Restituisce (stadio, evidence) come `classify_pipeline` d'ingresso.
    `soglia_exit` e' l'argomento di soglia — quando None, gli stadi che
    dipendono da essa (BELOW_THRESHOLD) ricadono su EXIT_BLOCKED.
    `data` (YYYY-MM-DD) e' il giorno di seduta a cui il dossier si riferisce:
    serve per separare STALE (segnale di una seduta precedente) da freschi.
    Per i mover non-EXIT_RISK lo stadio e' None (la pipeline d'uscita non
    si valuta su PASSIVE_EXPOSURE / NON_ACTIONABLE / OUT_OF_SCOPE).
    """
    actionability = classify_actionability(mover)
    if actionability != "EXIT_RISK":
        return None, {}

    # --- esito: posizione effettivamente chiusa -------------------------------
    chiusura = mover.get("chiusura")
    if chiusura:
        return "EXITED", {
            "exit_reason": chiusura.get("exit_reason"),
            "pnl_net": chiusura.get("pnl_net"),
        }

    # --- segnali di sortita del mover ----------------------------------------
    # Convenzione: la lista porta `ora` (HH:MM) e `score` firmato (criterio 3),
    # come per il lato d'ingresso. Il campo opzionale `generated_day`
    # (YYYY-MM-DD) distingue "segnale nato nella seduta di dossier" da
    # "segnale nato in una seduta precedente".
    segnali_uscita = list(mover.get("exit_segnali") or [])
    if not segnali_uscita:
        return "NO_EXIT_SIGNAL", {"n_segnali_uscita": 0}

    # --- STALE: nessun segnale appartiene alla seduta di dossier -----------
    # Criterio: `generated_day` < `data` (segnale di una seduta precedente).
    # Non filtriamo i segnali *della stessa seduta* generati prima del RTH
    # open: un segnale emesso alle 14:00 e' ancora fresco per la seduta
    # corrente — STALE e' una proprieta' del giorno, non dell'ora. Questa
    # scelta corrisponde a #567: DELL 09-10 porta `signal_id 10245`
    # generato il 2026-09-09 19:59Z — `generated_day` e' l'unico dato che
    # basta a classificare STALE_EXIT_SIGNAL.
    freschi: list[dict] = []
    for s in segnali_uscita:
        gd = s.get("generated_day")
        if data and gd and str(gd) < str(data):
            continue  # nato in una seduta precedente → stale
        freschi.append(s)
    if not freschi:
        # Prendiamo l'evidenza dal segnale piu' recente, cosi' il lettore
        # vede *quale* segnale stava guidando l'uscita mancata.
        ultimo = segnali_uscita[-1]
        return "STALE_EXIT_SIGNAL", {
            "signal_id": ultimo.get("signal_id"),
            "ora": ultimo.get("ora"),
            "generated_day": ultimo.get("generated_day"),
            "score_firmato": ultimo.get("score"),
            "session_open_hhmm": mover.get("session_open_hhmm") or None,
            "data": data,
        }

    # --- segno FIRMATO (criterio 3) -----------------------------------------
    # Uscita long-only: un'uscita qualificante richiede score negativo. Il
    # massimo FIRMATO tra i segnali freschi: un +0.05 non 'e' qualificante,
    # e' WRONG_SIGN.
    massimo_firmato = max(float(s.get("score") or 0.0) for s in freschi)
    if massimo_firmato >= 0:
        return "EXIT_WRONG_SIGN", {"score_firmato": massimo_firmato}

    # --- BELOW_THRESHOLD: |score| < soglia_exit (soglia inclusiva) ---------
    if soglia_exit is None or abs(massimo_firmato) < soglia_exit:
        return "EXIT_BELOW_THRESHOLD", {
            "score_firmato": massimo_firmato,
            "soglia_exit": soglia_exit,
        }

    # --- guard: segnale qualificante, ma bloccato ---------------------------
    guard = [str(g.get("decision")) for g in (mover.get("guard") or [])
             if g.get("decision")]
    if guard:
        return "EXIT_BLOCKED", {"guard": guard, "score_firmato": massimo_firmato}

    # Segnale d'uscita qualificante e nessun blocco: la posizione avrebbe
    # dovuto chiudersi ma non c'e' `chiusura`. Per costruzione questo caso
    # non dovrebbe accadere — la catena di scheduling pubblica `chiusure`
    # quando l'ordine viene fillato. Lo annotiamo come EXITED = False.
    return "EXIT_BLOCKED", {
        "guard": [],
        "score_firmato": massimo_firmato,
        "note": "segnale_qualificante_ma_chiusura_assente",
    }


def build_funnel(
    movers: list[dict],
    soglia_gate: float,
    soglia_exit: float | None = None,
    floor_kpi: float | None = None,
) -> dict:
    """Costruisce il blocco `funnel_v2` del dossier. Puro e deterministico.

    Ogni mover riceve ENTRAMBI gli assi. La pipeline d'ingresso valuta solo
    chi ha una decisione d'ingresso da spiegare (ENTRY_OPPORTUNITY); la
    pipeline d'uscita (#567) valuta solo chi ha una decisione d'uscita da
    spiegare (EXIT_RISK): la partizione e' completa e simmetrica.

    Args:
        soglia_gate: soglia di gate d'ingresso, pre-registrata (freeze #171).
        soglia_exit: soglia di attivazione dell'uscita. `None` significa che
            l'operatore non l'ha dichiarata: gli stadi dipendenti ricadono
            su quelli indipendenti da soglia (WRONG_SIGN/BLOCKED).
        floor_kpi:   n-floor per i KPI pubblicati (#567). `None` = no
            opinion (`sufficienza = 'unset'`); un intero o float marca
            'ok' se denom >= floor altrimenti 'insufficient_n'.
    """
    righe: list[dict] = []
    conteggi_actionability: dict[str, int] = {s: 0 for s in ACTIONABILITY_STAGES}
    conteggi_pipeline: dict[str, int] = {s: 0 for s in PIPELINE_STAGES}
    conteggi_pipeline_uscita: dict[str, int] = {s: 0 for s in EXIT_PIPELINE_STAGES}
    esclusi: dict[str, int] = {}

    for mover in movers:
        actionability = classify_actionability(mover)
        conteggi_actionability[actionability] += 1
        pipeline: str | None = None
        pipeline_uscita: str | None = None
        motivo: str | None = None
        evidence: dict = {}
        evidence_uscita: dict = {}
        if actionability == "ENTRY_OPPORTUNITY":
            pipeline, evidence = classify_pipeline(mover, soglia_gate)
            assert pipeline is not None
            conteggi_pipeline[pipeline] += 1
        else:
            # Motivo d'esclusione dal funnel d'ingresso: i mover non-entry sono
            # comunque classificati in actionability. #567 chiede di separare
            # il "detenuto in ribasso" (EXIT_RISK) dal "detenuto in rialzo"
            # (PASSIVE_EXPOSURE): la stringa unica 'held' veniva gonfiata da
            # PASSIVE_EXPOSURE ed e' sintomo dello stesso punto cieco.
            motivo = {
                "OUT_OF_SCOPE": "fuori_universo",
                "EXIT_RISK": "held_falling",
                "PASSIVE_EXPOSURE": "held_rising",
                "NON_ACTIONABLE": "non_actionable_long_only",
            }[actionability]
            esclusi[motivo] = esclusi.get(motivo, 0) + 1
            # Lato uscita (#567): classificato solo per EXIT_RISK.
            if actionability == "EXIT_RISK":
                pipeline_uscita, evidence_uscita = classify_exit_pipeline(
                    mover, soglia_exit, data=mover.get("_data")
                )
                assert pipeline_uscita is not None
                conteggi_pipeline_uscita[pipeline_uscita] += 1
        opportunity = mover.get("opportunity_v2") or {}
        righe.append({
            "symbol": mover.get("symbol"),
            "rendimento": mover.get("return"),
            "held": _as_bool(mover.get("held")),
            "actionability": actionability,
            "pipeline": pipeline,
            "pipeline_uscita": pipeline_uscita,
            "pipeline_escluso_motivo": motivo,
            "evidence": evidence,
            "evidence_uscita": evidence_uscita,
            "legacy_causa": mover.get("legacy_causa"),
            "net_profitable": (
                _net_profitable(mover)
                if pipeline in ("BAD_FILL", "CAUGHT")
                else None
            ),
            "net_opportunity_usd": opportunity.get("net_opportunity_usd"),
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
    miss_non_catturati = [r for r in entry_rows if r["pipeline"] != "CAUGHT"]
    miss_evitabili = [
        r for r in miss_non_catturati
        if r["net_opportunity_usd"] is not None
        and float(r["net_opportunity_usd"]) > 0
    ]
    miss_evitabilita_ignota = [
        r for r in miss_non_catturati if r["net_opportunity_usd"] is None
    ]

    kpi = {
        # I mover gia' a libro non sono miss: contarli insieme ai candidati
        # d'ingresso e' la confusione che la issue vuole eliminare.
        "held_at_open": {
            "mover_held": conteggi_actionability["EXIT_RISK"]
            + conteggi_actionability["PASSIVE_EXPOSURE"],
            "exit_risk": conteggi_actionability["EXIT_RISK"],
            "passive_exposure": conteggi_actionability["PASSIVE_EXPOSURE"],
            "definizione": (
                "mover gia' a libro nello snapshot PIT all'open RTH: non sono "
                "miss d'ingresso e non entrano nei KPI del funnel"
            ),
        },
        "held_at_open_rate": _rapporto(
            conteggi_actionability["EXIT_RISK"]
            + conteggi_actionability["PASSIVE_EXPOSURE"],
            len(righe),
            "mover gia' detenuti all'apertura / tutti i mover della seduta",
            floor=floor_kpi,
        ),
        "active_signal_recall": _rapporto(
            len(con_segnale_qualificante), len(notizia_agibile),
            "mover ENTRY_OPPORTUNITY con notizia tempestiva che hanno prodotto "
            "un punteggio qualificante (segno giusto, sopra il gate, non "
            "fallback) / tutti i mover ENTRY_OPPORTUNITY con notizia tempestiva",
            floor=floor_kpi,
        ),
        "execution_conversion_rate": _rapporto(
            len(eseguiti), len(arrivati_all_ordine),
            "mover arrivati allo stadio dell'ordine che sono stati eseguiti "
            "(fill, anche cattivo) / tutti i mover arrivati all'ordine",
            floor=floor_kpi,
        ),
        "profitable_capture_rate": _rapporto(
            len(catturati_profittevoli), len(entry_rows),
            "ingressi catturati con mark fill->close EOD positivo dopo i costi "
            "/ tutti i mover ENTRY_OPPORTUNITY della seduta (end-to-end)",
            floor=floor_kpi,
        ),
        "avoidable_miss_count": len(miss_evitabili),
        "avoidable_miss_unknown_count": len(miss_evitabilita_ignota),
    }

    # --- Lato uscita (#567) --------------------------------------------------
    exit_rows = [r for r in righe if r["actionability"] == "EXIT_RISK"]
    # Uscita "qualificante" = segnale d'uscita presente, segno giusto,
    # sopra soglia — senza un guard che blocchi. E' la stessa domanda
    # dell'ingresso "con_segnale_qualificante" ma speculare.
    exit_con_segnale_qualificante = [
        r for r in exit_rows
        if r["pipeline_uscita"] in (
            "EXIT_BELOW_THRESHOLD", "EXIT_BLOCKED", "EXITED",
        )
    ]
    exit_eseguiti = [r for r in exit_rows if r["pipeline_uscita"] == "EXITED"]

    kpi.update({
        "exit_signal_recall": _rapporto(
            len(exit_con_segnale_qualificante), len(exit_rows),
            "mover EXIT_RISK con segnale d'uscita qualificante (segn "
            "corretto, |score| >= soglia_exit) / tutti i mover EXIT_RISK "
            "(simmetrico a active_signal_recall, #567)",
            floor=floor_kpi,
        ),
        "exit_conversion_rate": _rapporto(
            len(exit_eseguiti), len(exit_con_segnale_qualificante),
            "mover EXIT_RISK con SELL fillata / EXIT_RISK con segnale "
            "d'uscita qualificante (simmetrico a execution_conversion_rate, "
            "#567)",
            floor=floor_kpi,
        ),
    })

    # Pubblica solo gli stadi osservati, nell'ordine canonico.
    return {
        "funnel_version": FUNNEL_VERSION,
        "soglia_gate": soglia_gate,
        "nota_freeze": (
            "vista v2 parallela: i conteggi legacy (miss_cause #208) e la "
            "metrica NO_NEWS pre-registrata restano intatti (freeze #171); "
            "nessun dato storico riscritto. #567: il lato uscita (EXIT_RISK) "
            "aggiunge `conteggi_pipeline_uscita`, `pipeline_uscita` per riga "
            "e gli stadi NO_EXIT_SIGNAL/STALE_EXIT_SIGNAL/EXIT_BELOW_THRESHOLD/"
            "EXIT_WRONG_SIGN/EXIT_BLOCKED/EXITED; la stringa unica 'held' "
            "in `esclusi_pipeline` e' sostituita da 'held_falling' e "
            "'held_rising' (PASSIVE_EXPOSURE)"
        ),
        "conteggi_actionability": {
            s: n for s, n in conteggi_actionability.items() if n
        },
        "conteggi_pipeline": {
            s: n for s, n in conteggi_pipeline.items() if n
        },
        "conteggi_pipeline_uscita": {
            s: n for s, n in conteggi_pipeline_uscita.items() if n
        },
        "esclusi_pipeline": esclusi,
        "kpi": kpi,
        "kpi_floor": floor_kpi,
        "mapping_legacy_v2": MAPPING_LEGACY_V2,
        "righe": righe,
    }


def riconcilia_cause_con_funnel(
    candidati_classificati: list[dict], funnel_v2: dict | None
) -> list[dict]:
    """Promuove il verdetto funnel_v2 nel campo legacy `causa` (#509).

    Il classificatore #208 definisce NON_CLASSIFICATO per esclusione: segnale
    sopra il gate, "o non era un miss, o il dossier non filtra bene". Il funnel
    v2 nello stesso dossier sa gia' quale dei due: questa funzione fa consumare
    al campo legacy quel verdetto, per esattamente i candidati che la serie
    legacy aveva lasciato nel bucket dell'ignoranza.

    Regola di promozione, per simbolo:
    - riga con `pipeline` (ENTRY_OPPORTUNITY fermato a uno stadio noto): la
      causa diventa quello stadio (FALLBACK_REJECT, RANKED_OUT, ...). E' un
      miss d'ingresso con causa diagnosticabile.
    - riga senza `pipeline`: la causa diventa l'asse `actionability`
      (NON_ACTIONABLE, OUT_OF_SCOPE, ...). La pipeline d'ingresso non si
      valuta, ma "non era un miss, e il motivo e' questo" e' comunque una
      risposta nota, non NON_CLASSIFICATO.
    - nessuna riga (dossier pre-#281, come PLTR il 2026-09-02): la causa resta
      NON_CLASSIFICATO. Non esiste un verdetto da promuovere e inventarlo
      vorrebbe dire riscrivere l'osservato (#288 Opzione 1).

    Il valore storico resta leggibile accanto: `causa_legacy` vale il verdetto
    della serie #208, e `count_by_cause` e' quello che conta — la serie
    pre-registrata (`cause_del_giorno` -> market_daily.jsonl -> criterio di
    uscita n.1) resta invariata. Le altre categorie NON si toccano: sono il
    vocabolario registrato della carta.

    Mut `candidati_classificati` in place e lo restituisce, cosi' l'ordine del
    dossier e i blocchi gia' innestati (opportunity_v2, attribution) restano
    al loro posto. Idempotente: il candidato promosso non e' piu'
    NON_CLASSIFICATO, quindi un secondo passaggio non fa nulla.
    """
    if not funnel_v2:
        return candidati_classificati
    righe = {
        str(riga.get("symbol")): riga
        for riga in funnel_v2.get("righe") or []
    }
    for candidato in candidati_classificati:
        if candidato.get("causa") != NON_CLASSIFICATO:
            continue
        riga = righe.get(str(candidato.get("symbol")))
        if riga is None:
            continue
        verdetto = riga.get("pipeline") or riga.get("actionability")
        if not verdetto:
            continue
        candidato["causa_legacy"] = NON_CLASSIFICATO
        candidato["causa"] = verdetto
    return candidati_classificati
