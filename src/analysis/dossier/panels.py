"""Pannelli longitudinali e occurrence ledger (#282).

Il ledger corrente (``findings.json``) mescola definizione e occorrenza (un
finding porta dentro le sue ``occorrenze[]``), puo' duplicare lo stesso evento
fra report alpha/forensic e somma importi con soglie di confidenza diverse. Questo
modulo costruisce pannelli PARALLELI e append-only sopra il dossier
deterministico (#174) e il contratto di attribution articolo (#279 / #340),
SENZA riscrivere ``findings.json``: quest'ultimo e' letto in sola lettura per la
vista ``definitions``.

Puro: riceve il dossier (dict) e restituisce dict. Nessun I/O. Lo schema e'
versionato (``PANELS_SCHEMA_VERSION`` / ``LEDGER_SCHEMA_VERSION``) e ogni riga ha
chiavi stabili, cosi' un consumatore puo' evolvere senza rompere i dossier storici.

Tassonomia degli importi (coerente con la carta di osservazione, #278):
    actual_usd    — P&L realizzato, tracciato a righe di DB (confidenza misurata).
                    Si conta SOLO sul verdetto definitivo (uscita), mai
                    sull'ingresso provvisorio: il design alpha-miner vieta di
                    generare occorrenze di costo sull'esito provvisorio.
    missed_usd    — alpha mancato, nessun trade (confidenza congetturale).
                    Magnitudo del movimento non catturato (gross opportunity).
    avoided_usd   — perdita evitata non entrando (accessible opportunita' < 0).
    attributed_usd — importo attribuito al finding primario (vedi sotto).

``causal_event_id`` e' la chiave anti-doppio-conteggio: deterministica da
(kind, data, ticker[, trade_id]). Due report che descrivono lo stesso evento
mappano sullo stesso id; il validator rifiuta duplicati. ``primary_finding``
(F-NNN) e' nullo di default: l'attribuzione del costo di un evento a un finding
strutturale e' giudizio dell'LLM/operatore, non meccanica dal dossier (i
candidati miss NON sono finding, sono conteggi). Il validator garantisce pero'
che, per ogni (data, ticker), al piu' un finding primario riceva il costo.
"""

from __future__ import annotations

from collections import Counter, defaultdict

PANELS_SCHEMA_VERSION = "1.0"
LEDGER_SCHEMA_VERSION = "1.0"

# Cause che NON sono miss e non generano occorrenza di costo: NON_CLASSIFICATO
# significa che il candidato era sopra il gate (non era un miss, o il filtro
# upstream e' rotto); IN_PORTAFOGLIO significa posizione gia' aperta. Entrambe
# restano nel pannello ticker-day (visibilita') ma non nel ledger delle
# occorrenze.
NON_OCCORRENZA = frozenset({"NON_CLASSIFICATO", "IN_PORTAFOGLIO"})

# Precedenza di attribution per scegliere quella dominante di un ticker-day:
# una prova issuer-specific prevale su fanout/unknown.
_ATTRIBUTION_PRECEDENCE = {"ISSUER_SPECIFIC": 3, "FANOUT": 2, "UNKNOWN": 1}


def causal_event_id(kind: str, data: str, ticker: str) -> str:
    """Id deterministico dell'evento causale, stabile e unico per (kind,data,ticker).

    Il ``kind`` distingue le unita' osservative (miss, trade, decision, entry,
    exit, signal); per i trade l'id usa il ``trade_id`` del DB (vedi
    ``build_occurrence_ledger``), che e' univoco per costruzione.
    """
    return f"{kind}:{data}:{ticker}"


def _timeline_by_ticker(dossier: dict) -> dict[str, list[dict]]:
    """Indice timeline per ticker: i signal_id/news_log_id/order_id/trade_id
    vivono nella timeline (sempre presenti), non nei segnali del candidato
    (che sui dossier 2.0 storici possono mancare di signal_id)."""
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for event in dossier.get("timeline") or []:
        symbol = event.get("symbol")
        if symbol is None:
            continue
        by_ticker[symbol].append(event)
    return by_ticker


def _coverage_index(dossier: dict) -> tuple[dict, dict, bool]:
    """Indice del contratto #279/#340: signal_id -> riga attribution,
    ticker -> metriche per_ticker, e flag presence (dossier 2.0 storici non
    lo hanno)."""
    cov = dossier.get("copertura_articoli") or {}
    by_signal = {
        row["signal_id"]: row
        for row in cov.get("segnali") or []
        if row.get("signal_id") is not None
    }
    per_ticker = cov.get("per_ticker") or {}
    return by_signal, per_ticker, bool(cov)


def _opp_view(opp: dict) -> dict:
    """Vista opportunity di un candidato: missingness esplicita, mai importo
    inventato. Un opportunita' fallita (``error``) rende nulli gli importi e
    registra il motivo, cosi' un buco di dato non si confonde con zero."""
    if not isinstance(opp, dict) or "error" in opp:
        error = opp.get("error") if isinstance(opp, dict) else "opportunity_missing"
        return {
            "gross_usd": None,
            "accessible_usd": None,
            "net_usd": None,
            "confidenza": (opp.get("confidenza") if isinstance(opp, dict) else None),
            "estimator_version": (
                opp.get("estimator_version") if isinstance(opp, dict) else None
            ),
            "formula": None,
            "missingness": [error] if error else [],
        }
    return {
        "gross_usd": opp.get("gross_opportunity_usd"),
        "accessible_usd": opp.get("accessible_opportunity_usd"),
        "net_usd": opp.get("net_opportunity_usd"),
        "confidenza": opp.get("confidenza"),
        "estimator_version": opp.get("estimator_version"),
        "formula": opp.get("formula"),
        "missingness": list(opp.get("missingness") or []),
    }


def build_ticker_day_panel(dossier: dict, *, dossier_hash: str = "") -> list[dict]:
    """Una riga per unita' osservativa (ticker, giorno) dai candidati miss del
    dossier. Porta causa, rendimento, opportunity (missed/avoided), ids segnali
    e attribution articolo, ma NON le occorrenze del finding: definition e
    occurrence restano separati (vedi ``build_definitions``)."""
    data = dossier["data"]
    timeline = _timeline_by_ticker(dossier)
    by_signal, per_ticker, has_coverage = _coverage_index(dossier)

    rows: list[dict] = []
    for candidato in dossier.get("candidati_miss") or []:
        ticker = candidato["symbol"]
        tl_events = timeline.get(ticker, [])
        signal_ids = sorted(
            {e["signal_id"] for e in tl_events if e.get("signal_id") is not None}
        )
        news_log_ids = sorted(
            {e["news_log_id"] for e in tl_events if e.get("news_log_id") is not None}
        )

        canonical_article_ids: list[str] = []
        attribution = None
        if has_coverage:
            attrs = []
            for sid in signal_ids:
                entry = by_signal.get(sid)
                if not entry:
                    continue
                if entry.get("canonical_article_id"):
                    canonical_article_ids.append(entry["canonical_article_id"])
                if entry.get("attribution"):
                    attrs.append(entry["attribution"])
            canonical_article_ids = sorted(set(canonical_article_ids))
            if attrs:
                attribution = max(
                    attrs, key=lambda a: _ATTRIBUTION_PRECEDENCE.get(a, 0)
                )
            effective = per_ticker.get(ticker, {}).get("effective_timely_articles")
        else:
            # dossier 2.0 storico: niente copertura. I campi articolo-centrici
            # sono assenti (None/[]), mai confusi con zero: missingness esplicita.
            effective = None

        rows.append(
            {
                "schema_version": PANELS_SCHEMA_VERSION,
                "data": data,
                "ticker": ticker,
                "causal_event_id": causal_event_id("miss", data, ticker),
                "segment": candidato.get("causa"),
                "return": candidato.get("return"),
                "news_count": candidato.get("news_count"),
                "signal_ids": signal_ids,
                "news_log_ids": news_log_ids,
                "canonical_article_ids": canonical_article_ids,
                "attribution": attribution,
                "effective_timely_articles": effective,
                "in_portafoglio": bool(candidato.get("in_portafoglio")),
                "opportunity": _opp_view(candidato.get("opportunity_v2") or {}),
                "primary_finding": None,
                "dossier_hash": dossier_hash,
            }
        )
    return rows


def build_signal_panel(dossier: dict, *, dossier_hash: str = "") -> list[dict]:
    """Una riga per segnale, con attribution articolo (#279/#340) e linkage
    alla decisione/trade (order_id, trade_id) dalla timeline."""
    data = dossier["data"]
    by_signal, _per_ticker, has_coverage = _coverage_index(dossier)

    rows: list[dict] = []
    for event in dossier.get("timeline") or []:
        signal_id = event.get("signal_id")
        if signal_id is None:
            continue
        cov = by_signal.get(signal_id, {}) if has_coverage else {}
        rows.append(
            {
                "schema_version": PANELS_SCHEMA_VERSION,
                "data": data,
                "signal_id": signal_id,
                "ticker": event.get("symbol"),
                "score": event.get("score"),
                "fallback": event.get("fallback"),
                "news_log_id": event.get("news_log_id"),
                "canonical_article_id": cov.get("canonical_article_id"),
                "source": cov.get("source"),
                "subject_ticker": cov.get("subject_ticker"),
                "relevance": cov.get("relevance"),
                "timing": cov.get("timing"),
                "attribution": cov.get("attribution"),
                "order_id": event.get("order_id"),
                "trade_id": event.get("trade_id"),
                "order_lookup_error": event.get("order_lookup_error"),
                # causal_event_id: il segnale e' un evento del dataset e partecipa
                # del contratto anti-doppio conteggio (kind=signal, data, signal_id).
                # signal_id e' la PK di news_log, quindi univoco per costruzione;
                # la data distingue due dossier diversi con lo stesso signal_id
                # (es. replay cross-day).
                "causal_event_id": f"signal:{data}:{signal_id}",
                "dossier_hash": dossier_hash,
            }
        )
    return rows


def build_decision_trade_panel(dossier: dict, *, dossier_hash: str = "") -> list[dict]:
    """Pannello decisioni/trade: una riga per decisione collegata (timeline con
    order_id/trade_id), una per ingresso (provvisorio) e una per uscita
    (definitivo). L'ingresso e' marcato ``provvisorio``: il suo mtm_eod NON e'
    un verdetto e non genera occorrenza di costo (vedi ``build_occurrence_ledger``)."""
    data = dossier["data"]
    rows: list[dict] = []

    for event in dossier.get("timeline") or []:
        order_id = event.get("order_id")
        trade_id = event.get("trade_id")
        if not order_id and not trade_id:
            continue
        if trade_id is not None:
            kind, cid = "trade", f"trade:{trade_id}"
        else:
            kind, cid = "decision", f"decision:{order_id}"
        rows.append(
            {
                "schema_version": PANELS_SCHEMA_VERSION,
                "data": data,
                "kind": kind,
                "ticker": event.get("symbol"),
                "signal_id": event.get("signal_id"),
                "order_id": order_id,
                "trade_id": trade_id,
                "score": event.get("score"),
                "order_lookup_error": event.get("order_lookup_error"),
                "causal_event_id": cid,
                "dossier_hash": dossier_hash,
            }
        )

    for ing in dossier.get("ingressi") or []:
        rows.append(
            {
                "schema_version": PANELS_SCHEMA_VERSION,
                "data": data,
                "kind": "entry",
                "ticker": ing["symbol"],
                "strategia": ing.get("strategia"),
                "ora_utc": ing.get("ora_utc"),
                "entry_price": ing.get("entry_price"),
                "qty": ing.get("qty"),
                "mtm_eod": ing.get("mtm_eod"),
                "vs_apertura": ing.get("vs_apertura"),
                "entry_percentile": ing.get("entry_percentile"),
                "provvisorio": True,
                "confidenza": "congetturale",
                "causal_event_id": f"entry:{data}:{ing['symbol']}:{ing.get('ora_utc')}",
                "dossier_hash": dossier_hash,
            }
        )

    for ch in dossier.get("chiusure") or []:
        rows.append(
            {
                "schema_version": PANELS_SCHEMA_VERSION,
                "data": data,
                "kind": "exit",
                "ticker": ch["symbol"],
                "strategia": ch.get("strategia"),
                "exit_price": ch.get("exit_price"),
                "qty": ch.get("qty"),
                "pnl_net": ch.get("pnl_net"),
                "exit_reason": ch.get("exit_reason"),
                "ore_tenuta": ch.get("ore_tenuta"),
                "drift_post_uscita": ch.get("drift_post_uscita"),
                "provvisorio": False,
                "confidenza": "misurata",
                "causal_event_id": f"exit:{data}:{ch['symbol']}:{ch.get('strategia')}",
                "dossier_hash": dossier_hash,
            }
        )
    return rows


def build_occurrence_ledger(dossier: dict, *, dossier_hash: str = "") -> list[dict]:
    """Ledger append-only: una riga per evento causale. I miss vengono dai
    candidati (causa non in NON_OCCORRENZA); i trade vengono dalle chiusure
    (verdetto definitivo, pnl_net). L'ingresso provvisorio NON produce
    occorrenza: il design vieta costo sull'esito non definitivo.
    ``primary_finding`` parte nullo: l'attribuzione ad F-NNN e' dell'LLM/
    operatore, non meccanica.

    Sul ``causal_event_id`` dei trade: le chiusure NON portano ``trade_id`` (e'
    nella timeline, non nel book). Si usa ``trade:{trade_id}`` solo quando il
    join e' UNIVOCO — esattamente una chiusura per (giorno, ticker, strategia) e
    esattamente un trade nella timeline di quel ticker — perche' altrimenti una
    chiusura parziale di una posizione multi-fill, o due trade distinti sullo
    stesso ticker, colliderebbero sullo stesso id = doppio conteggio. Nei casi
    ambigui si ricade su un id per-riga ``exit:{data}:{ticker}:{strategia}:{idx}``,
    univoco per costruzione: ogni chiusura resta una sua occorrenza, mai fusa."""
    data = dossier["data"]
    fonte = f"dossier/{data}.json"
    timeline = _timeline_by_ticker(dossier)

    # trade_id per ticker nella timeline di questo dossier, con conteggio per
    # decidere l'univocita' del join.
    tl_trade_counts: Counter[str] = Counter()
    tl_trade_id: dict[str, int] = {}
    tl_signal_id: dict[str, int] = {}
    for events in timeline.values():
        for e in events:
            if e.get("trade_id") is not None:
                tkr = e.get("symbol")
                tl_trade_counts[tkr] += 1
                tl_trade_id[tkr] = e["trade_id"]
                if e.get("signal_id") is not None:
                    tl_signal_id[tkr] = e["signal_id"]

    chiusure = dossier.get("chiusure") or []
    chiusure_group_count: Counter[tuple] = Counter(
        (ch.get("symbol"), ch.get("strategia")) for ch in chiusure
    )
    chiusure_group_idx: dict[tuple, int] = defaultdict(int)

    occurrences: list[dict] = []

    for candidato in dossier.get("candidati_miss") or []:
        causa = candidato.get("causa")
        if causa in NON_OCCORRENZA:
            continue
        ticker = candidato["symbol"]
        tl_events = timeline.get(ticker, [])
        signal_ids = sorted(
            {e["signal_id"] for e in tl_events if e.get("signal_id") is not None}
        )
        news_log_ids = sorted(
            {e["news_log_id"] for e in tl_events if e.get("news_log_id") is not None}
        )
        opp = _opp_view(candidato.get("opportunity_v2") or {})
        gross = opp["gross_usd"]
        accessible = opp["accessible_usd"]
        missed_usd = gross if gross is not None else None
        # accessible < 0 = avremmo perso entrando: perdita evitata (segno positivo).
        avoided_usd = (
            -accessible if (accessible is not None and accessible < 0) else None
        )
        occurrences.append(
            {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "causal_event_id": causal_event_id("miss", data, ticker),
                "data": data,
                "tickers": [ticker],
                "signal_ids": signal_ids,
                "trade_ids": [],
                "news_log_ids": news_log_ids,
                "segment": causa,
                "confidenza": opp["confidenza"] or "congetturale",
                "actual_usd": None,
                "attributed_usd": None,
                "missed_usd": missed_usd,
                "avoided_usd": avoided_usd,
                "formula": opp["formula"],
                "estimator_version": opp["estimator_version"],
                "primary_finding": None,
                "primary": True,
                "fonte": fonte,
                "dossier_hash": dossier_hash,
            }
        )

    for ch in chiusure:
        ticker = ch["symbol"]
        strat = ch.get("strategia")
        group = (ticker, strat)
        idx = chiusure_group_idx[group]
        chiusure_group_idx[group] += 1
        # join univoco: una sola chiusura per il gruppo e un solo trade nella
        # timeline di quel ticker. Altrimenti id per-riga (mai doppio conteggio).
        if chiusure_group_count[group] == 1 and tl_trade_counts.get(ticker, 0) == 1:
            trade_id = tl_trade_id[ticker]
            cid = f"trade:{trade_id}"
            trade_ids = [trade_id]
            signal_ids = [tl_signal_id[ticker]] if ticker in tl_signal_id else []
        else:
            cid = f"exit:{data}:{ticker}:{strat}:{idx}"
            trade_ids = []
            signal_ids = []
        occurrences.append(
            {
                "schema_version": LEDGER_SCHEMA_VERSION,
                "causal_event_id": cid,
                "data": data,
                "tickers": [ticker],
                "signal_ids": signal_ids,
                "trade_ids": trade_ids,
                "news_log_ids": [],
                "segment": "trade",
                "confidenza": "misurata",
                "actual_usd": ch.get("pnl_net"),
                "attributed_usd": None,
                "missed_usd": None,
                "avoided_usd": None,
                "formula": None,
                "estimator_version": None,
                "primary_finding": None,
                "primary": True,
                "fonte": fonte,
                "dossier_hash": dossier_hash,
            }
        )
    return occurrences


def build_definitions(findings: dict) -> list[dict]:
    """Vista read-only delle DEFINIZIONI dei finding, separata dalle occorrenze.
    ``findings.json`` non viene modificato: si proietta sui soli campi di
    definizione (id, titolo, tipo, confidenza, stato, issue, primo_avvistamento)
    piu' conteggi aggregati. Le occorrenze vivono nel ledger separato."""
    out: list[dict] = []
    for finding in findings.get("findings") or []:
        occorrenze = finding.get("occorrenze") or []
        out.append(
            {
                "id": finding.get("id"),
                "titolo": finding.get("titolo"),
                "tipo": finding.get("tipo"),
                "confidenza": finding.get("confidenza"),
                "primo_avvistamento": finding.get("primo_avvistamento"),
                "stato": finding.get("stato"),
                "issue": finding.get("issue"),
                "n_occorrenze": len(occorrenze),
                "n_occorrenze_non_stimate": finding.get("occorrenze_non_stimate", 0),
                "costo_cumulato_usd": finding.get("costo_cumulato_usd"),
            }
        )
    return out


def build_status_events(findings: dict) -> list[dict]:
    """Eventi di stato. ``findings.json`` registra solo lo stato CORRENTE di un
    finding, non lo storico delle transizioni: produciamo quindi uno snapshot per
    finding (``kind = status_snapshot``), dichiarato esplicitamente come snapshot
    e non come transizione. Lo storico completo delle transizioni richiede un
    log di stato append-only separato (wiring post-freeze, fuori perimetro)."""
    out: list[dict] = []
    for finding in findings.get("findings") or []:
        out.append(
            {
                "kind": "status_snapshot",
                "finding_id": finding.get("id"),
                "data": finding.get("primo_avvistamento"),
                "stato": finding.get("stato"),
                "issue": finding.get("issue"),
            }
        )
    return out


def build_derived_views(
    panels_by_day: dict[str, list[dict]],
    occ_by_day: dict[str, list[dict]],
) -> dict:
    """Viste derivate cross-day: conteggi per causa (segmento) e per confidenza,
    con somme per confidenza. Rendono meccanici i pattern longitudinali che
    oggi richiedono di rileggere i report a mano."""
    per_causa: Counter[str] = Counter()
    per_confidenza: dict[str, dict] = defaultdict(lambda: {"n": 0, "somma_usd": 0.0})
    for _day, occs in occ_by_day.items():
        for occ in occs:
            per_causa[occ.get("segment") or "sconosciuto"] += 1
            confidenza = occ.get("confidenza") or "sconosciuta"
            bucket = per_confidenza[confidenza]
            bucket["n"] += 1
            # somma degli importi effettivi (realizzati): i missed sono
            # congetturale e non si sommano al P&L reale.
            amount = occ.get("actual_usd")
            if amount is not None:
                bucket["somma_usd"] += float(amount)
    return {
        "schema_version": PANELS_SCHEMA_VERSION,
        "n_giorni": len(panels_by_day),
        "per_causa": dict(per_causa),
        "per_confidenza": {k: dict(v) for k, v in per_confidenza.items()},
    }
