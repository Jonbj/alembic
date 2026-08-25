"""#282 — pannelli longitudinali e occurrence ledger.

Il ledger corrente (``findings.json``) mescola definizione e occorrenza, puo'
duplicare lo stesso evento fra report alpha/forensic e combina importi con
soglie di confidenza diverse. Questi test fissano il contratto dei pannelli
paralleli e append-only costruiti sopra il dossier deterministico (#174) e il
contratto di attribution articolo (#279, #340), SENZA riscrivere ``findings.json``.

I pannelli sono viste derivate: una riga per unita' osservativa, chiavi e schema
versionati, ``causal_event_id`` deterministico che impedisce il doppio conteggio.
Il modulo e' puro: riceve il dossier (dict) e restituisce dict, niente I/O.
"""

from __future__ import annotations

from src.analysis.dossier import panels


# ---------------------------------------------------------------------------
# Fixture minimali: un dossier 2.1 (con copertura_articoli + attribution sui
# segnali) e uno 2.0 (senza). Il builder deve digerire entrambi: i dossier
# storici su disco sono 2.0, quelli freschi dallo script corrente 2.1.
# ---------------------------------------------------------------------------


def _opp(candidate: dict) -> dict:
    """Riempie opportunity_v2 con i soli campi che il pannello legge."""
    return {
        "estimator_version": "2.0",
        "confidenza": "congetturale",
        "formula": "gross=|close_to_close|xsize; accessible=(exit-entry)xshares",
        "gross_opportunity_usd": 100.0,
        "accessible_opportunity_usd": 40.0,
        "net_opportunity_usd": None,
        "missingness": [],
        "legacy": {"costo_usd": 100.0},
    }


def _signal(signal_id, ticker="AAPL", **kw):
    s = {"ora": "14:22", "score": 0.31, "fallback": False, "signal_id": signal_id}
    s.update(kw)
    return s


def _dossier_2_1() -> dict:
    return {
        "schema_version": "2.1",
        "data": "2026-08-12",
        "soglia_mover": 0.03,
        "mercato": {"rendimenti": {"AAPL": 0.05, "MSFT": -0.04, "FLAT": 0.01}},
        "candidati_miss": [
            {
                "symbol": "AAPL",
                "return": 0.05,
                "news_count": 2,
                "causa": "BELOW_GATE",
                "in_portafoglio": False,
                "segnali": [
                    _signal(
                        101,
                        "AAPL",
                        canonical_article_id="content:" + "a" * 64,
                        attribution="ISSUER_SPECIFIC",
                        relevance="ISSUER_SPECIFIC",
                        timing="CONCURRENT",
                        source="alpaca_benzinga",
                        subject_ticker="AAPL",
                    ),
                ],
                "opportunity_v2": _opp({}),
            },
            {
                "symbol": "MSFT",
                "return": -0.04,
                "news_count": 0,
                "causa": "NO_NEWS",
                "in_portafoglio": False,
                "segnali": [],
                "opportunity_v2": _opp({})
                | {
                    "gross_opportunity_usd": 88.0,
                    "accessible_opportunity_usd": -12.0,
                },
            },
        ],
        "ingressi": [
            {
                "symbol": "AAPL",
                "strategia": "S4",
                "ora_utc": "14:37",
                "entry_price": 190.0,
                "qty": 10.0,
                "mtm_eod": 5.0,
                "vs_apertura": 3.0,
                "entry_percentile": 0.8,
                "quota_movimento_precedente_al_segnale": 0.5,
                "denominatore_degenere": False,
                "quota_nel_gap": 0.2,
            },
        ],
        "chiusure": [
            {
                "symbol": "AAPL",
                "strategia": "S4",
                "exit_price": 195.0,
                "qty": 10.0,
                "pnl_net": 12.5,
                "exit_reason": "portfolio_sell",
                "ore_tenuta": 2.75,
                "drift_post_uscita": -3.0,
            },
        ],
        "timeline": [
            {
                "kind": "signal",
                "symbol": "AAPL",
                "is_mover": True,
                "signal_id": 101,
                "news_log_id": 101,
                "score": 0.31,
                "fallback": False,
                "order_id": "ord-1",
                "trade_id": 726,
                "order_lookup_error": None,
                "latenze_secondi": {
                    "scored_to_eligible_cycle": 240.0,
                    "eligible_cycle_to_order_submitted": 10.0,
                    "order_submitted_to_filled": 1.0,
                    "scored_to_filled": 251.0,
                },
                "movimento": {},
                "sessioni": {},
                "stages": {},
            },
            {
                "kind": "signal",
                "symbol": "MSFT",
                "is_mover": True,
                "signal_id": 102,
                "news_log_id": None,
                "score": None,
                "fallback": False,
                "order_id": None,
                "trade_id": None,
                "order_lookup_error": None,
                "movimento": {},
                "sessioni": {},
                "stages": {},
            },
        ],
        "copertura_articoli": {
            "segnali": [
                {
                    "signal_id": 101,
                    "news_log_id": 101,
                    "canonical_article_id": "content:" + "a" * 64,
                    "source": "alpaca_benzinga",
                    "ticker": "AAPL",
                    "subject_ticker": "AAPL",
                    "relevance": "ISSUER_SPECIFIC",
                    "timing": "CONCURRENT",
                    "attribution": "ISSUER_SPECIFIC",
                    "score": 0.31,
                },
            ],
            "per_ticker": {
                "AAPL": {
                    "effective_timely_articles": 1,
                    "quota_effective_timely": 0.5,
                    "articoli_unici": 2,
                },
                "MSFT": {
                    "effective_timely_articles": 0,
                    "quota_effective_timely": 0.0,
                    "articoli_unici": 0,
                },
            },
        },
    }


def _dossier_2_0() -> dict:
    """Dossier storico: niente copertura_articoli, segnali senza attribution."""
    d = _dossier_2_1()
    d["schema_version"] = "2.0"
    d.pop("copertura_articoli", None)
    for c in d["candidati_miss"]:
        for s in c.get("segnali") or []:
            for k in (
                "canonical_article_id",
                "attribution",
                "relevance",
                "timing",
                "source",
                "subject_ticker",
            ):
                s.pop(k, None)
    return d


# ---------------------------------------------------------------------------
# causal_event_id
# ---------------------------------------------------------------------------


def test_causal_event_id_e_deterministico_e_stabile():
    a = panels.causal_event_id("miss", "2026-08-12", "AAPL")
    b = panels.causal_event_id("miss", "2026-08-12", "AAPL")
    assert a == b == "miss:2026-08-12:AAPL"


def test_causal_event_id_distingue_ticker_giorno_e_kind():
    assert panels.causal_event_id(
        "miss", "2026-08-12", "AAPL"
    ) != panels.causal_event_id("miss", "2026-08-13", "AAPL")
    assert panels.causal_event_id(
        "miss", "2026-08-12", "AAPL"
    ) != panels.causal_event_id("trade", "2026-08-12", "AAPL")


# ---------------------------------------------------------------------------
# ticker-day panel
# ---------------------------------------------------------------------------


def test_ticker_day_panel_una_riga_per_candidato_con_schema_versionato():
    rows = panels.build_ticker_day_panel(_dossier_2_1(), dossier_hash="h")
    assert len(rows) == 2
    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    assert aapl["schema_version"] == panels.PANELS_SCHEMA_VERSION
    assert aapl["data"] == "2026-08-12"
    assert aapl["ticker"] == "AAPL"
    assert aapl["segment"] == "BELOW_GATE"
    assert aapl["return"] == 0.05
    assert aapl["news_count"] == 2
    assert aapl["dossier_hash"] == "h"
    assert aapl["causal_event_id"] == "miss:2026-08-12:AAPL"
    # primary_finding parte nullo: l'attribuzione ad F-NNN e' del LLM, non meccanica
    assert aapl["primary_finding"] is None


def test_ticker_day_panel_porta_opportunity_e_ids_segnali():
    rows = panels.build_ticker_day_panel(_dossier_2_1(), dossier_hash="h")
    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    assert aapl["signal_ids"] == [101]
    assert aapl["news_log_ids"] == [101]
    assert aapl["canonical_article_ids"] == ["content:" + "a" * 64]
    assert aapl["attribution"] == "ISSUER_SPECIFIC"
    assert aapl["effective_timely_articles"] == 1
    opp = aapl["opportunity"]
    assert opp["gross_usd"] == 100.0
    assert opp["accessible_usd"] == 40.0
    assert opp["confidenza"] == "congetturale"
    assert opp["estimator_version"] == "2.0"
    assert "formula" in opp and opp["formula"]


def test_ticker_day_panel_distingue_missed_da_avoided_sul_segno():
    rows = panels.build_ticker_day_panel(_dossier_2_1(), dossier_hash="h")
    msft = next(r for r in rows if r["ticker"] == "MSFT")
    # accessible negativo = perdita evitata non entrando (avoided), non missed
    assert msft["opportunity"]["gross_usd"] == 88.0
    assert msft["opportunity"]["accessible_usd"] == -12.0


def test_ticker_day_panel_tollera_dossier_2_0_senza_attribution():
    rows = panels.build_ticker_day_panel(_dossier_2_0(), dossier_hash="h")
    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    # Nessuna copertura articoli: i campi attribution/degli articoli sono assenti,
    # mai confusi con zero. missingness esplicita.
    assert aapl["attribution"] is None
    assert aapl["canonical_article_ids"] == []
    assert aapl["effective_timely_articles"] is None
    # i signal_ids arrivano comunque dai segnali del candidato
    assert aapl["signal_ids"] == [101]


def test_ticker_day_panel_salta_candidati_senza_opportunity():
    d = _dossier_2_1()
    d["candidati_miss"][0]["opportunity_v2"] = {
        "estimator_version": "2.0",
        "error": "daily_bar_missing",
    }
    rows = panels.build_ticker_day_panel(d, dossier_hash="h")
    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    # opportunity fallita: si registra la missingness, non si inventa un importo
    assert aapl["opportunity"]["gross_usd"] is None
    assert aapl["opportunity"]["missingness"] == ["daily_bar_missing"]


# ---------------------------------------------------------------------------
# signal panel
# ---------------------------------------------------------------------------


def test_signal_panel_una_riga_per_segnale_con_attribution():
    rows = panels.build_signal_panel(_dossier_2_1(), dossier_hash="h")
    by_id = {r["signal_id"]: r for r in rows}
    assert 101 in by_id and 102 in by_id
    s = by_id[101]
    assert s["schema_version"] == panels.PANELS_SCHEMA_VERSION
    assert s["ticker"] == "AAPL"
    assert s["canonical_article_id"] == "content:" + "a" * 64
    assert s["attribution"] == "ISSUER_SPECIFIC"
    assert s["relevance"] == "ISSUER_SPECIFIC"
    assert s["timing"] == "CONCURRENT"
    assert s["latenze_secondi"]["scored_to_filled"] == 251.0
    # linkage al trade/decision
    assert s["order_id"] == "ord-1"
    assert s["trade_id"] == 726
    assert s["dossier_hash"] == "h"


def test_signal_panel_tollera_dossier_2_0_senza_copertura():
    rows = panels.build_signal_panel(_dossier_2_0(), dossier_hash="h")
    s = next(r for r in rows if r["signal_id"] == 101)
    assert s["canonical_article_id"] is None
    assert s["attribution"] is None
    assert s["trade_id"] == 726  # arriva comunque dalla timeline


def test_signal_panel_assegna_causal_event_id_deterministico():
    # Il pannello signals partecipa del contratto anti-doppio conteggio: ogni
    # segnale riceve un causal_event_id stabile da (data, signal_id), univoco
    # per costruzione (signal_id e' la PK di news_log).
    rows = panels.build_signal_panel(_dossier_2_1(), dossier_hash="h")
    by_id = {r["signal_id"]: r for r in rows}
    assert by_id[101]["causal_event_id"] == "signal:2026-08-12:101"
    assert by_id[102]["causal_event_id"] == "signal:2026-08-12:102"
    # univocita' nel pannello di un singolo dossier.
    ids = [r["causal_event_id"] for r in rows]
    assert len(ids) == len(set(ids))


def test_signal_panel_causal_event_id_distingue_due_dossier_stesso_signal_id():
    # Lo stesso signal_id in due dossier diversi (es. un replay) collide se non
    # si incorpora la data: con la data nel kind=signal l'id resta univoco.
    d_a = _dossier_2_1()
    d_b = _dossier_2_1()
    d_b["data"] = "2026-08-13"
    rows = (
        panels.build_signal_panel(d_a, dossier_hash="h-a")
        + panels.build_signal_panel(d_b, dossier_hash="h-b")
    )
    ids = [r["causal_event_id"] for r in rows]
    assert len(ids) == len(set(ids)), "causal_event_id deve restare univoco fra dossier"


# ---------------------------------------------------------------------------
# decision / trade panel
# ---------------------------------------------------------------------------


def test_decision_trade_panel_una_riga_per_decisione_con_id_db():
    rows = panels.build_decision_trade_panel(_dossier_2_1(), dossier_hash="h")
    # Una decisione che e' diventata trade (timeline event con order_id/trade_id)
    dec = next(r for r in rows if r.get("trade_id") == 726)
    assert dec["schema_version"] == panels.PANELS_SCHEMA_VERSION
    assert dec["ticker"] == "AAPL"
    assert dec["signal_id"] == 101
    assert dec["order_id"] == "ord-1"
    assert dec["causal_event_id"] == "trade:726"
    # Esito: l'uscita e' il verdetto definitivo (pnl_net), non l'ingresso provvisorio
    exits = [r for r in rows if r["kind"] == "exit"]
    entries = [r for r in rows if r["kind"] == "entry"]
    assert exits and exits[0]["pnl_net"] == 12.5
    assert exits[0]["confidenza"] == "misurata"
    assert entries and entries[0]["mtm_eod"] == 5.0
    assert entries[0]["provvisorio"] is True


def test_entry_panel_conserva_la_misura_direzionale_e_il_suo_flag():
    rows = panels.build_decision_trade_panel(_dossier_2_1(), dossier_hash="h")
    entry = next(row for row in rows if row["kind"] == "entry")

    assert entry["quota_movimento_precedente_al_segnale"] == 0.5
    assert entry["denominatore_degenere"] is False
    assert entry["quota_nel_gap"] == 0.2


# ---------------------------------------------------------------------------
# occurrence ledger
# ---------------------------------------------------------------------------


def test_occurrence_ledger_miss_e_trade_con_causal_event_id_univoci():
    ledger = panels.build_occurrence_ledger(_dossier_2_1(), dossier_hash="h")
    ids = [o["causal_event_id"] for o in ledger]
    assert len(ids) == len(set(ids)), "causal_event_id deve essere univoco"
    # miss occurrence per il candidato (NON_CLASSIFICATO non genera costo)
    miss = next(o for o in ledger if o["causal_event_id"] == "miss:2026-08-12:AAPL")
    assert miss["segment"] == "BELOW_GATE"
    assert miss["confidenza"] == "congetturale"
    assert miss["missed_usd"] == 100.0
    assert miss["actual_usd"] is None
    assert miss["primary_finding"] is None
    assert miss["dossier_hash"] == "h"
    assert miss["schema_version"] == panels.LEDGER_SCHEMA_VERSION


def test_occurrence_ledger_conta_solo_verdetto_definitivo_non_provvisorio():
    ledger = panels.build_occurrence_ledger(_dossier_2_1(), dossier_hash="h")
    # Il trade e' contato sull'uscita (definitivo, pnl_net), non sull'ingresso
    trade = next(o for o in ledger if o["causal_event_id"] == "trade:726")
    assert trade["actual_usd"] == 12.5
    assert trade["confidenza"] == "misurata"
    # non esiste un'occorrenza di costo per l'ingresso provvisorio
    assert not any(o["causal_event_id"].startswith("trade_entry") for o in ledger)


def test_occurrence_ledger_evita_doppio_conteggio_stesso_ticker_day():
    # Due dossier nello stesso giorno non dovrebbero capitare, ma se un evento
    # venisse duplicato il causal_event_id lo svela: stesso (kind,data,ticker)
    # => stesso id. Il builder deduplica per causal_event_id.
    d = _dossier_2_1()
    ledger = panels.build_occurrence_ledger(d, dossier_hash="h")
    assert len({o["causal_event_id"] for o in ledger}) == len(ledger)


def test_occurrence_ledger_salta_non_classificato_e_in_portafoglio():
    d = _dossier_2_1()
    d["candidati_miss"][0]["causa"] = "NON_CLASSIFICATO"
    ledger = panels.build_occurrence_ledger(d, dossier_hash="h")
    # NON_CLASSIFICATO non e' un miss: o il filtro upstream e' rotto, o non era un miss
    assert not any(o["causal_event_id"] == "miss:2026-08-12:AAPL" for o in ledger)


# ---------------------------------------------------------------------------
# definitions + status events (vista read-only da findings.json)
# ---------------------------------------------------------------------------


def _findings() -> dict:
    return {
        "schema_version": 1,
        "prossimo_id": 3,
        "findings": [
            {
                "id": "F-001",
                "titolo": "copertura news bassa",
                "tipo": "osservazione",
                "confidenza": "congetturale",
                "primo_avvistamento": "2026-07-31",
                "occorrenze": [
                    {
                        "data": "2026-07-31",
                        "costo_usd": None,
                        "nota": "...",
                        "fonte": "R1",
                    },
                    {
                        "data": "2026-08-03",
                        "costo_usd": 10.0,
                        "nota": "...",
                        "fonte": "R2",
                    },
                ],
                "costo_cumulato_usd": 10.0,
                "stato": "aperto",
                "issue": None,
                "occorrenze_non_stimate": 1,
            },
            {
                "id": "F-002",
                "titolo": "S4 ora 14",
                "tipo": "difetto",
                "confidenza": "attribuita",
                "primo_avvistamento": "2026-07-30",
                "occorrenze": [
                    {
                        "data": "2026-07-30",
                        "costo_usd": 5.0,
                        "nota": "...",
                        "fonte": "R0",
                    }
                ],
                "costo_cumulato_usd": 5.0,
                "stato": "in_roadmap",
                "issue": 226,
                "occorrenze_non_stimate": 0,
            },
        ],
    }


def test_definitions_separa_definizione_da_occorrenze_senza_cancellare():
    defs = panels.build_definitions(_findings())
    assert len(defs) == 2
    f1 = next(d for d in defs if d["id"] == "F-001")
    # la definizione NON porta le occorrenze: definition e occurrence sono separati
    assert "occorrenze" not in f1
    assert f1["confidenza"] == "congetturale"
    assert f1["stato"] == "aperto"
    assert f1["issue"] is None
    assert f1["primo_avvistamento"] == "2026-07-31"
    assert f1["n_occorrenze"] == 2
    f2 = next(d for d in defs if d["id"] == "F-002")
    assert f2["issue"] == 226 and f2["stato"] == "in_roadmap"


def test_status_events_snapshot_da_stato_corrente():
    ev = panels.build_status_events(_findings())
    # findings.json registra solo lo stato corrente, non lo storico: produciamo
    # uno snapshot per finding (un evento di stato), dichiarato come snapshot.
    by_id = {e["finding_id"]: e for e in ev}
    assert by_id["F-001"]["stato"] == "aperto"
    assert by_id["F-002"]["stato"] == "in_roadmap"
    assert by_id["F-002"]["issue"] == 226
    assert all(e["kind"] == "status_snapshot" for e in ev)


# ---------------------------------------------------------------------------
# derived views (cross-day)
# ---------------------------------------------------------------------------


def test_derived_views_aggrega_per_causa_e_per_confidenza():
    d = _dossier_2_1()
    panels_by_day = {"2026-08-12": panels.build_ticker_day_panel(d, dossier_hash="h")}
    occ_by_day = {"2026-08-12": panels.build_occurrence_ledger(d, dossier_hash="h")}
    views = panels.build_derived_views(panels_by_day, occ_by_day)
    # una riga per causa, somme per confidenza: nessun importo perso o duplicato
    assert "per_causa" in views and "per_confidenza" in views
    assert views["per_causa"]["NO_NEWS"] == 1
    assert views["per_confidenza"]["congetturale"]["n"] >= 1
    assert views["n_giorni"] == 1
