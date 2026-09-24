"""#281: `funnel_v2` cablato nel dossier.

Il funnel v2 e' una vista PARALLELA: costruisce le righe per i mover della
seduta dai dati che il dossier ha gia' caricato (rendimenti, portafoglio,
coverage #279, segnali firmati, ledger #294, decisioni di guard, dettagli
ordine Alpaca), senza toccare i conteggi legacy o la NO_NEWS pre-registrata.

Il wiring ha due peccati facili che questi test fermano:
1. caricare TUTTE le righe SKIP_* come RISK_BLOCK: SKIP_THRESHOLD e' lo stadio
   del gate (gia' deciso dal punteggio firmato) e SKIP_FALLBACK e' lo stadio del
   filtro fallback — contarli come guard doppio-conterebbe gli stessi scarti;
2. dimenticare un mover detenuto o fuori-universo: la partizione deve essere
   completa, la somma dei conteggi fa i mover del giorno.
"""

from datetime import date

from unittest.mock import patch


import scripts.alpha_miner_dossier as dossier


def test_risk_decisions_esclude_gate_e_fallback_dal_risk_block(monkeypatch):
    """SKIP_THRESHOLD (gate) e SKIP_FALLBACK (filtro #108) appartengono a stadi
    che il funnel decide dal punteggio firmato: non sono guard."""
    query_vista = []

    def fake_psql(query: str):
        # La fake onora il WHERE della query: sono guard SOLO le SKIP_* fuori
        # dal NOT IN, piu' BUY_POWER_CAP. SKIP_THRESHOLD e SKIP_FALLBACK non
        # attraversano il filtro, come nel DB vero.
        query_vista.append(query)
        return [
            ["2026-08-12 15:07:00", "ORCL", "42", "SKIP_PYRAMIDING"],
            ["2026-08-12 15:37:00", "META", "45", "SKIP_BUY_POWER"],
        ]

    monkeypatch.setattr(dossier, "_psql", fake_psql)
    guard = dossier._risk_decisions(date(2026, 8, 12))
    by_symbol = {g["symbol"]: g["decision"] for g in guard}
    assert by_symbol == {"ORCL": "SKIP_PYRAMIDING", "META": "SKIP_BUY_POWER"}
    # la query filtra a monte: non carica le righe che servono ad altri stadi
    assert "SKIP_FALLBACK" in query_vista[0]
    assert "SKIP_THRESHOLD" in query_vista[0]
    assert "NOT IN" in query_vista[0]


def _barra(sym, close):
    return {"open": close, "high": close, "low": close, "close": close,
            "close_prec": close}


def test_funnel_v2_costruisce_le_righe_per_ogni_mover():
    """Movers della seduta: 3% su ORCL (non detenuto, catturato), -4% su HOOD
    (detenuto: exit risk), +5% su benchmark (fuori universo)."""
    rendimenti = {"ORCL": 0.03, "HOOD": -0.04, "SPY": 0.05}
    copertura = {
        "per_ticker": {
            "ORCL": {"articoli_unici": 1,
                     "rilevanza": {"ISSUER_SPECIFIC": 1},
                     "effective_timely_articles": 1},
        },
    }
    segnali = {"ORCL": [{"ora": "15:00", "score": 0.45, "fallback": False,
                         "signal_id": 42}]}
    intenti = [{"intent_id": "i1", "signal_id": 42, "symbol": "ORCL",
                "signal_at": None, "decision_at": None, "signal_score": 0.45,
                "final_reason_code": "RANK_SELECTED", "is_tradable": True,
                "trade_id": 7, "pnl_realizzato": 12.5}]
    eventi = [{"signal_id": 42, "symbol": "ORCL", "news_log_id": 1,
               "score": 0.45, "fallback": False, "published_at": None,
               "first_seen_at": None, "ingested_at": None,
               "scored_at": None, "eligible_cycle_at": None,
               "order_id": "o1", "trade_id": 7, "order_submitted_at": "t",
               "filled_at": "t", "fill_price": 117.10,
               "order_lookup_error": None}]
    candidati = [{"symbol": "ORCL", "causa": "NON_CLASSIFICATO"}]
    guard = []  # nessun guard: ORCL arriva al fill

    funnel = dossier._funnel_v2(
        rendimenti=rendimenti,
        held_at_open={"HOOD"},
        universo=["ORCL", "HOOD"],
        copertura=copertura,
        segnali=segnali,
        intenti=intenti,
        eventi=eventi,
        guard=guard,
        barre={"ORCL": _barra("ORCL", 117.95)},
        candidati_classificati=candidati,
        soglia_gate=0.30,
    )

    righe = {r["symbol"]: r for r in funnel["righe"]}
    # tre mover, tre righe: la partizione copre tutta la giornata
    assert set(righe) == {"ORCL", "HOOD", "SPY"}
    # ORCL: rialzo non detenuto, notizia tempestiva, eseguito con profitto
    assert righe["ORCL"]["actionability"] == "ENTRY_OPPORTUNITY"
    assert righe["ORCL"]["pipeline"] == "CAUGHT"
    assert righe["ORCL"]["legacy_causa"] == "NON_CLASSIFICATO"
    # HOOD detenuto in ribasso: exit risk, la pipeline d'ingresso non si valuta
    assert righe["HOOD"]["actionability"] == "EXIT_RISK"
    assert righe["HOOD"]["pipeline"] is None
    # SPY non e' in universo: fuori dal perimetro
    assert righe["SPY"]["actionability"] == "OUT_OF_SCOPE"
    # KPI end-to-end: 1 catturato profittevole su 1 entry opportunity
    assert funnel["kpi"]["profitable_capture_rate"]["valore"] == 1.0
    assert funnel["soglia_gate"] == 0.30


def test_funnel_v2_niente_mover_righe_vuote_kpi_none():
    funnel = dossier._funnel_v2(
        rendimenti={"AAPL": 0.001},
        held_at_open=set(),
        universo=["AAPL"],
        copertura={"per_ticker": {}},
        segnali={},
        intenti=[],
        eventi=[],
        guard=[],
        barre={},
        candidati_classificati=[],
        soglia_gate=0.30,
    )
    assert funnel["righe"] == []
    for nome in ("held_at_open_rate", "active_signal_recall",
                 "execution_conversion_rate", "profitable_capture_rate"):
        assert funnel["kpi"][nome]["valore"] is None


def test_dossier_pubblica_il_blocco_funnel_v2_affiancato_al_legacy():
    """Full flow: il dossier costruito pubblica `funnel_v2` accanto ai
    `candidati_miss` legacy (che restano al loro posto), e la riga del mover
    porta la causa legacy accanto agli assi v2 (criterio 4)."""
    from datetime import datetime, timezone

    def fake_psql(query: str):
        if "risk_blocks_281" in query:
            return []  # nessun guard: WMT arriva all'ordine
        if "FROM s4_candidate_population" in query:
            return [["intent-wmt", "7001", "WMT",
                     "2026-08-20T16:36:00+00:00", "2026-08-20T16:37:00+00:00",
                     "0.45", "RANK_SELECTED", "true", "42", ""]]
        if "article_coverage_279" in query:
            return [["1", "7001", "WMT", "WMT beats earnings expectations",
                     "", "https://example.com/wmt", "gdelt_gkg",
                     "2026-08-20T14:10:00+00:00", "2026-08-20T14:12:00+00:00",
                     "", "org_lookup", "0.45", "", "", ""]]
        if "FROM sentiment_signals ss LEFT JOIN news_log nl" in query:
            return [["WMT", "16:36", "0.45", "f", "", "", "", "7001"]]
        if "SELECT ticker, count(*) FROM news_log" in query:
            return [["WMT", "1"]]
        if "SELECT DISTINCT symbol FROM trades" in query:
            # Vista legacy a fine giornata: WMT e' in portafoglio perche' e'
            # entrato intraday. Non era pero' detenuto all'open e il funnel v2
            # deve continuare a riconoscerlo come ingresso attivo.
            return [["WMT"]]
        return []

    cutoff = datetime(2026, 8, 20, 23, 59, tzinfo=timezone.utc)
    with (
        patch.object(dossier, "_psql", side_effect=fake_psql),
        patch.object(dossier, "_barre", return_value={
            "WMT": {"open": 116.0, "high": 118.5, "low": 115.0,
                    "close": 117.95, "close_prec": 112.0},
            "SPY": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                    "close_prec": 100.0},
        }),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=[
            {"signal_id": 7001, "symbol": "WMT", "news_log_id": 1,
             "score": 0.45, "fallback": False,
             "published_at": None, "first_seen_at": None, "ingested_at": None,
             "scored_at": None, "eligible_cycle_at": None,
             "order_id": "o1", "trade_id": 42},
        ]),
        patch.object(dossier, "_dettagli_ordini", return_value={
            "o1": {"submitted_at": "2026-08-20T16:52:12+00:00",
                   "filled_at": "2026-08-20T16:52:13+00:00",
                   "filled_avg_price": 117.10, "filled_qty": 18.0,
                   "lookup_error": None},
        }),
        patch.object(dossier, "_barre_intraday", return_value=({}, cutoff)),
        patch.object(dossier, "_opening_positions", return_value=[]),
        patch.object(dossier, "_sedute_di_borsa", return_value=[]),
    ):
        payload = dossier.costruisci_dossier(date(2026, 8, 20), ["WMT"])

    # la vista e' affiancata, non sostitutiva: i candidati legacy restano
    assert "candidati_miss" in payload
    funnel = payload["funnel_v2"]
    assert funnel["funnel_version"]
    assert funnel["soglia_gate"] == 0.30
    wmt = {r["symbol"]: r for r in funnel["righe"]}["WMT"]
    # WMT: +5.3% non detenuto, notizia tempestiva issuer-specific, segnale
    # 0.45 non fallback, selezionato, eseguito a 117.10 sotto il close 117.95
    assert wmt["actionability"] == "ENTRY_OPPORTUNITY"
    assert wmt["pipeline"] == "CAUGHT"
    assert wmt["legacy_causa"] is None
    # Il trade e' ancora aperto (net_pnl realizzato NULL): il verdetto viene
    # dal mark fill->close al netto del cost model, quindi resta misurabile EOD.
    assert wmt["net_profitable"] is True
    # KPI end-to-end cablati, non solo il modulo puro
    assert funnel["kpi"]["profitable_capture_rate"]["valore"] == 1.0
    # il funnel dichiara la sua natura nel blocco provenienza del dossier
    assert "funnel_v2" in payload["provenienza_dati"]


def test_dossier_riconcilia_la_causa_legacy_con_il_verdetto_funnel():
    """#509 full flow: un candidato sopra il gate (legacy NON_CLASSIFICATO)
    la cui causa e' pienamente nota nel funnel_v2 dello stesso dossier non
    resta nel bucket dell'ignoranza. La causa viene promossa con il verdetto
    v2, il valore storico resta in causa_legacy, e la serie pre-registrata
    (`aggregati.cause_del_giorno`) resta invariata (#288 Opzione 1)."""
    from datetime import datetime, timezone

    def fake_psql(query: str):
        if "risk_blocks_281" in query:
            return []
        if "FROM s4_candidate_population" in query:
            return [["intent-wmt", "7001", "WMT",
                     "2026-08-20T16:36:00+00:00", "2026-08-20T16:37:00+00:00",
                     "0.45", "RANK_SELECTED", "true", "42", ""]]
        if "article_coverage_279" in query:
            return [["1", "7001", "WMT", "WMT beats earnings expectations",
                     "", "https://example.com/wmt", "gdelt_gkg",
                     "2026-08-20T14:10:00+00:00", "2026-08-20T14:12:00+00:00",
                     "", "org_lookup", "0.45", "", "", ""]]
        if "FROM sentiment_signals ss LEFT JOIN news_log nl" in query:
            return [["WMT", "16:36", "0.45", "f", "", "", "", "7001"]]
        if "SELECT ticker, count(*) FROM news_log" in query:
            return [["WMT", "1"]]
        if "SELECT DISTINCT symbol FROM trades" in query:
            # WMT NON e' in portafoglio: e' un candidato miss vero, sopra il
            # gate (0.45), il cui ingresso pero' e' stato eseguito (CAUGHT).
            return []
        return []

    cutoff = datetime(2026, 8, 20, 23, 59, tzinfo=timezone.utc)
    with (
        patch.object(dossier, "_psql", side_effect=fake_psql),
        patch.object(dossier, "_barre", return_value={
            "WMT": {"open": 116.0, "high": 118.5, "low": 115.0,
                    "close": 117.95, "close_prec": 112.0},
            "SPY": {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                    "close_prec": 100.0},
        }),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=[
            {"signal_id": 7001, "symbol": "WMT", "news_log_id": 1,
             "score": 0.45, "fallback": False,
             "published_at": None, "first_seen_at": None, "ingested_at": None,
             "scored_at": None, "eligible_cycle_at": None,
             "order_id": "o1", "trade_id": 42},
        ]),
        patch.object(dossier, "_dettagli_ordini", return_value={
            "o1": {"submitted_at": "2026-08-20T16:52:12+00:00",
                   "filled_at": "2026-08-20T16:52:13+00:00",
                   "filled_avg_price": 117.10, "filled_qty": 18.0,
                   "lookup_error": None},
        }),
        patch.object(dossier, "_barre_intraday", return_value=({}, cutoff)),
        patch.object(dossier, "_opening_positions", return_value=[]),
        patch.object(dossier, "_sedute_di_borsa", return_value=[]),
    ):
        payload = dossier.costruisci_dossier(date(2026, 8, 20), ["WMT"])

    wmt = next(c for c in payload["candidati_miss"] if c["symbol"] == "WMT")
    # promozione #509: il verdetto funnel vince sul sentinel legacy
    assert wmt["causa"] == "CAUGHT"
    assert wmt["causa_legacy"] == "NON_CLASSIFICATO"
    # l'annotazione nella riga funnel resta il valore pre-promozione
    riga = next(r for r in payload["funnel_v2"]["righe"] if r["symbol"] == "WMT")
    assert riga["pipeline"] == "CAUGHT"
    assert riga["legacy_causa"] == "NON_CLASSIFICATO"
    # serie pre-registrata invariata (#288 Opzione 1): il conteggio aggregato
    # continua a vedere il verdetto #208
    assert payload["aggregati"]["cause_del_giorno"]["conteggi"] == {
        "NON_CLASSIFICATO": 1
    }


def test_funnel_sceglie_il_tentativo_fillato_se_un_simbolo_ha_piu_ordini():
    eventi = [
        {"symbol": "ORCL", "order_id": "o1", "order_submitted_at": "t1",
         "filled_at": None, "fill_price": None, "order_lookup_error": None,
         "trade_id": None},
        {"symbol": "ORCL", "order_id": "o2", "order_submitted_at": "t2",
         "filled_at": "t3", "fill_price": 117.10, "order_lookup_error": None,
         "trade_id": 7},
    ]
    funnel = dossier._funnel_v2(
        rendimenti={"ORCL": 0.05},
        held_at_open=set(),
        universo=["ORCL"],
        copertura={"per_ticker": {"ORCL": {
            "rilevanza": {"ISSUER_SPECIFIC": 1},
            "effective_timely_articles": 1,
        }}},
        segnali={"ORCL": [{"score": 0.45, "fallback": False}]},
        intenti=[{"symbol": "ORCL", "final_reason_code": "RANK_SELECTED",
                  "is_tradable": True, "trade_id": 7,
                  "pnl_realizzato": 12.5}],
        eventi=eventi,
        guard=[],
        barre={"ORCL": _barra("ORCL", 117.95)},
        candidati_classificati=[],
        soglia_gate=0.30,
    )
    assert funnel["righe"][0]["pipeline"] == "CAUGHT"


# --- #567: il caller di _funnel_v2 deve cablare la pipeline d'uscita.
# Senza il wiring, ogni EXIT_RISK collassa a NO_EXIT_SIGNAL perche' il modulo
# puro non riceve `chiusura`, `exit_segnali` o la data di dossier. I test qui
# chiamano `_funnel_v2` esattamente come fa l'orchestratore (con i tre campi
# nuovi: chiusure_by_symbol, exit_segnali_by_symbol, giorno_iso) e verificano
# che la pipeline d'uscita produca stadi diversi da NO_EXIT_SIGNAL.


def test_funnel_v2_cabla_chiusure_per_simbolo_a_exit_risk():
    """HOOD e' EXIT_RISK (detenuto, ribasso) ed e' stato chiuso: la riga deve
    classificarsi EXITED, non restare NO_EXIT_SIGNAL. Il caller deve passare la
    chiusura caricata dal ledger `trades`."""
    rendimenti = {"HOOD": -0.04}
    chiusura_hood = {
        "symbol": "HOOD", "strategia": "S4",
        "exit_price": 28.40, "qty": 50.0, "pnl_net": -12.50,
        "exit_reason": "sentiment_reversal", "ore_tenuta": 1.0,
    }
    funnel = dossier._funnel_v2(
        rendimenti=rendimenti,
        held_at_open={"HOOD"},
        universo=["HOOD"],
        copertura={"per_ticker": {}},
        segnali={},
        intenti=[],
        eventi=[],
        guard=[],
        barre={"HOOD": _barra("HOOD", 28.13)},
        candidati_classificati=[],
        soglia_gate=0.30,
        chiusure_by_symbol={"HOOD": chiusura_hood},
        exit_segnali_by_symbol={},
        giorno_iso="2026-09-10",
    )
    riga = funnel["righe"][0]
    assert riga["actionability"] == "EXIT_RISK"
    # wiring essenziale: chiusura passata -> stadio EXITED, non NO_EXIT_SIGNAL
    assert riga["pipeline_uscita"] == "EXITED"
    assert riga["evidence_uscita"]["exit_reason"] == "sentiment_reversal"


def test_funnel_v2_cabla_exit_segnali_per_simbolo_a_exit_risk():
    """HOOD e' EXIT_RISK senza chiusura ma con segnali d'uscita nella seduta
    (uno fresco sopra-soglia). Il caller passa i segnali: la riga NON collassa
    a NO_EXIT_SIGNAL. Con `soglia_exit=None` (freeze #171 — l'operatore non
    l'ha dichiarata) il modulo classifica BELOW_THRESHOLD con `soglia_exit`
    annotata a None: questo e' lo stadio "segnale qualificante, soglia non
    dichiarata" ed e' contato nei KPI come qualificante, distinto da
    NO_EXIT_SIGNAL."""
    rendimenti = {"HOOD": -0.04}
    funnel = dossier._funnel_v2(
        rendimenti=rendimenti,
        held_at_open={"HOOD"},
        universo=["HOOD"],
        copertura={"per_ticker": {}},
        segnali={},
        intenti=[],
        eventi=[],
        guard=[],
        barre={"HOOD": _barra("HOOD", 28.13)},
        candidati_classificati=[],
        soglia_gate=0.30,
        chiusure_by_symbol={},
        exit_segnali_by_symbol={
            "HOOD": [{"signal_id": 10245, "ora": "15:10",
                      "score": -0.20, "generated_day": "2026-09-10"}],
        },
        giorno_iso="2026-09-10",
    )
    riga = funnel["righe"][0]
    assert riga["actionability"] == "EXIT_RISK"
    # niente NO_EXIT_SIGNAL: il segnale e' passato, lo stadio cambia
    assert riga["pipeline_uscita"] != "NO_EXIT_SIGNAL"
    assert riga["pipeline_uscita"] in (
        "EXIT_BELOW_THRESHOLD", "EXIT_BLOCKED",
    )


def test_funnel_v2_cabla_giorno_iso_per_stale_exit_signal():
    """Segnali d'uscita della seduta precedente (generated_day < giorno_iso)
    sono STALE, non freschi. Senza `giorno_iso` il modulo non puo' decidere.
    Il caller deve passare il giorno di dossier (stringa YYYY-MM-DD)."""
    rendimenti = {"HOOD": -0.04}
    funnel = dossier._funnel_v2(
        rendimenti=rendimenti,
        held_at_open={"HOOD"},
        universo=["HOOD"],
        copertura={"per_ticker": {}},
        segnali={},
        intenti=[],
        eventi=[],
        guard=[],
        barre={"HOOD": _barra("HOOD", 28.13)},
        candidati_classificati=[],
        soglia_gate=0.30,
        chiusure_by_symbol={},
        exit_segnali_by_symbol={
            "HOOD": [{"signal_id": 99999, "ora": "19:59",
                      "score": -0.20, "generated_day": "2026-09-09"}],
        },
        giorno_iso="2026-09-10",
    )
    riga = funnel["righe"][0]
    # segnale della seduta precedente -> STALE_EXIT_SIGNAL
    assert riga["pipeline_uscita"] == "STALE_EXIT_SIGNAL"
    assert riga["evidence_uscita"]["signal_id"] == 99999


def test_funnel_v2_senza_wiring_tutti_a_no_exit_signal():
    """Sentinella del difetto: senza wiring (i tre parametri nuovi mancanti),
    la pipeline d'uscita collassa a NO_EXIT_SIGNAL per OGNI EXIT_RISK. Quando
    il wiring e' attivo, il numero di NO_EXIT_SIGNAL e' <= quello del caso non
    cablato. Il test fallisce finche' il caller non riceve i dati del dossier.
    """
    rendimenti = {"HOOD": -0.04}
    senza_wiring = dossier._funnel_v2(
        rendimenti=rendimenti,
        held_at_open={"HOOD"},
        universo=["HOOD"],
        copertura={"per_ticker": {}},
        segnali={},
        intenti=[],
        eventi=[],
        guard=[],
        barre={"HOOD": _barra("HOOD", 28.13)},
        candidati_classificati=[],
        soglia_gate=0.30,
        # nessun chiusure_by_symbol / exit_segnali_by_symbol / giorno_iso
    )
    riga_senza = senza_wiring["righe"][0]
    assert riga_senza["pipeline_uscita"] == "NO_EXIT_SIGNAL"
    # E i KPI d'uscita, su un solo EXIT_RISK non cablato, non producono
    # attivazione: exit_signal_recall denom = 1 (EXIT_RISK), num = 0 (perche'
    # NO_EXIT_SIGNAL non e' qualificante) -> 0.0.
    kpi_exit = senza_wiring["kpi"]["exit_signal_recall"]
    assert kpi_exit["valore"] == 0.0
    assert kpi_exit["denominatore"] == 1


def test_chiusure_per_simbolo_dedup_by_symbol():
    """`_chiusure_per_simbolo` riusa le righe di `compute_exits` (nessuna query
    in piu') e tiene per ogni simbolo l'ultima in exit_time: se lo stesso trade
    esce in piu' tranche, il funnel vede il verdetto finale della giornata."""
    righe = [
        {"symbol": "HOOD", "strategia": "S4", "exit_price": 28.50, "qty": 25.0,
         "pnl_net": -10.00, "exit_reason": "sentiment_reversal", "ore_tenuta": 0.5},
        {"symbol": "HOOD", "strategia": "S4", "exit_price": 28.20, "qty": 25.0,
         "pnl_net": -12.50, "exit_reason": "stop_loss", "ore_tenuta": 0.8},
        {"symbol": "MU", "strategia": "S4", "exit_price": 95.10, "qty": 50.0,
         "pnl_net": -22.00, "exit_reason": "sentiment_reversal", "ore_tenuta": 1.2},
    ]

    per_simbolo = dossier._chiusure_per_simbolo(righe)

    assert set(per_simbolo) == {"HOOD", "MU"}
    h = per_simbolo["HOOD"]
    assert h["exit_reason"] == "stop_loss"
    assert h["pnl_net"] == -12.50
    assert h["exit_price"] == 28.20
    assert per_simbolo["MU"]["exit_reason"] == "sentiment_reversal"


def test_il_segnale_del_giorno_prima_arriva_al_funnel_e_rende_lo_stale(monkeypatch):
    """RESPINGI di codex su PR #636: il loader reale non portava mai il segnale
    di una seduta precedente, quindi STALE_EXIT_SIGNAL era irraggiungibile. Qui
    il segnale passa dal loader vero (`_segnali_uscita`), non da un map
    iniettato a mano (DELL 09-10, signal 10245 generato il 09-09 19:59Z)."""
    query_viste = []

    def fake_psql(query: str):
        query_viste.append(query)
        return [["DELL", "19:59", "-0.20", "10245", "2026-09-09"]]

    monkeypatch.setattr(dossier, "_psql", fake_psql)
    exit_segnali = dossier._segnali_uscita(date(2026, 9, 10), {}, {"DELL"})

    assert "generated_at < '2026-09-10'" in query_viste[0]
    assert exit_segnali["DELL"][0]["generated_day"] == "2026-09-09"

    funnel = dossier._funnel_v2(
        rendimenti={"DELL": -0.05},
        held_at_open={"DELL"},
        universo=["DELL"],
        copertura={"per_ticker": {}},
        segnali={},
        intenti=[],
        eventi=[],
        guard=[],
        barre={"DELL": _barra("DELL", 120.0)},
        candidati_classificati=[],
        soglia_gate=0.30,
        chiusure_by_symbol={},
        exit_segnali_by_symbol=exit_segnali,
        giorno_iso="2026-09-10",
    )
    riga = funnel["righe"][0]
    assert riga["pipeline_uscita"] == "STALE_EXIT_SIGNAL"
    assert riga["evidence_uscita"]["signal_id"] == 10245


def test_un_segnale_della_seduta_rende_fresca_la_pipeline(monkeypatch):
    """Segnale precedente + segnale della seduta: non e' STALE."""
    monkeypatch.setattr(
        dossier, "_psql", lambda _q: [["DELL", "19:59", "-0.20", "10245", "2026-09-09"]]
    )
    exit_segnali = dossier._segnali_uscita(
        date(2026, 9, 10), {"DELL": [{"ora": "15:10", "score": -0.4, "signal_id": 10300}]},
        {"DELL"},
    )

    assert [s["generated_day"] for s in exit_segnali["DELL"]] == ["2026-09-09", "2026-09-10"]


def test_senza_titoli_tenuti_nessuna_query_sui_segnali_precedenti(monkeypatch):
    def esplodi(_q):
        raise AssertionError("query inattesa")

    monkeypatch.setattr(dossier, "_psql", esplodi)
    out = dossier._segnali_uscita(date(2026, 9, 10), {"MU": [{"ora": "15:00", "score": 0.3}]}, set())

    assert out == {"MU": [{"ora": "15:00", "score": 0.3, "generated_day": "2026-09-10"}]}
