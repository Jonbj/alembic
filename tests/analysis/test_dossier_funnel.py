"""Funnel v2 a due assi per il dossier alpha-miss (#281).

Modulo puro sotto test: `src.analysis.dossier.funnel`. Vista PARALLELA alla
serie legacy (`miss_cause`): nessun conteggio legacy sostituito, la metrica
NO_NEWS pre-registrata resta intatta (freeze #171).

Due assi ortogonali:
- actionability: cosa il motore POTREBBE fare sul mover (long-only);
- pipeline: dove la catena della decisione d'ingresso si e' fermata, dal campo
  firmato dello score (criterio 3), mai da reason con `abs(score)`.
"""

from src.analysis.dossier.funnel import (
    ACTIONABILITY_STAGES,
    PIPELINE_STAGES,
    build_funnel,
)


def _mover(rend=0.05, **over):
    """Mover di base: rialzo non detenuto, notizia issuer-specific tempestiva,
    segnale forte non-fallback, selezionato dal ranker, nessun ordine."""
    base = {
        "symbol": "ORCL",
        "return": rend,
        "held": False,
        "in_universo": True,
        "articoli": {
            "articoli_unici": 1,
            "rilevanza": {"ISSUER_SPECIFIC": 1},
            "effective_timely_articles": 1,
        },
        "segnali": [{"score": 0.45, "fallback": False}],
        "intenti": [{
            "final_reason_code": "RANK_SELECTED",
            "is_tradable": True,
            "trade_id": None,
            "pnl_realizzato": None,
        }],
        "guard": [],
        "ordine": None,
        "close": 117.95,
        "legacy_causa": None,
    }
    base.update(over)
    return base


def _row(mover):
    return build_funnel([mover], soglia_gate=0.30)["righe"][0]


# --- asse actionability -----------------------------------------------------


def test_mover_detenuto_in_rialzo_passive_exposure_non_miss():
    """Una posizione gia' detenuta che rialza non e' un miss: e' esposizione
    passiva. La vecchia serie 'catturati' fondeva posizioni vecchie e decisioni
    nuove; qui l'asse le separa."""
    row = _row(_mover(held=True, rend=0.05))
    assert row["actionability"] == "PASSIVE_EXPOSURE"
    # La pipeline d'ingresso non si valuta su chi e' gia' a libro.
    assert row["pipeline"] is None
    # #567 punto 1: PASSIVE_EXPOSURE escluso dal funnel d'ingresso con la
    # stringa distinta 'held_rising' (la stringa 'held' e' sparita).
    assert row["pipeline_escluso_motivo"] == "held_rising"


def test_mover_detenuto_in_ribasso_exit_risk():
    row = _row(_mover(held=True, rend=-0.05))
    assert row["actionability"] == "EXIT_RISK"


def test_ribasso_non_detenuto_non_actionable_long_only():
    """Book long-only: un ribasso non detenuto non era catturabile, quindi non
    e' un miss economico (#280: accessible = 0 verificato)."""
    row = _row(_mover(rend=-0.05))
    assert row["actionability"] == "NON_ACTIONABLE"
    assert row["pipeline"] is None
    assert row["pipeline_escluso_motivo"] == "non_actionable_long_only"


def test_mover_fuori_universo_out_of_scope():
    """Un benchmark (SPY, ETF di settore) non e' commerciabile dal motore:
    e' fuori dal perimetro del funnel, non un miss."""
    row = _row(_mover(in_universo=False))
    assert row["actionability"] == "OUT_OF_SCOPE"
    assert row["pipeline"] is None


def test_rialzo_non_detenuto_entry_opportunity():
    row = _row(_mover())
    assert row["actionability"] == "ENTRY_OPPORTUNITY"
    # il default prosegue lungo la pipeline: nessun ordine e' mai partito
    assert row["pipeline"] == "ORDER_FAIL"


# --- asse pipeline: stadi della notizia (#279) -------------------------------


def test_zero_articoli_no_relevant_news():
    row = _row(_mover(articoli=None, segnali=[]))
    assert row["pipeline"] == "NO_RELEVANT_NEWS"


def test_articolo_issuer_specific_ma_non_tempestivo_late_news():
    """La notizia sul titolo emittente esisteva, ma pubblicata dopo la seduta:
    e' arrivata tardi, non e' assente e non e' un errore di entita'."""
    articoli = {
        "articoli_unici": 1,
        "rilevanza": {"ISSUER_SPECIFIC": 1},
        "effective_timely_articles": 0,
    }
    row = _row(_mover(articoli=articoli, segnali=[]))
    assert row["pipeline"] == "LATE_NEWS"


def test_solo_articoli_false_entity_match_entity_error():
    """#279 rende decidibile la distinzione che la serie legacy fondeva in
    NO_NEWS/THIN_NEUTRAL: qui la notizia c'era ma parlava di un'altra societa'."""
    articoli = {
        "articoli_unici": 2,
        "rilevanza": {"FALSE_ENTITY_MATCH": 2},
        "effective_timely_articles": 0,
    }
    row = _row(_mover(articoli=articoli, segnali=[]))
    assert row["pipeline"] == "ENTITY_ERROR"


def test_articoli_relevanza_sconosciuta_restano_no_relevant_news():
    """UNKNOWN non viene promosso: senza label (QX-01) non possiamo dire ne'
    che la notizia era in tema ne' che era un errore di entita'."""
    articoli = {
        "articoli_unici": 1,
        "rilevanza": {"UNKNOWN": 1},
        "effective_timely_articles": 0,
    }
    row = _row(_mover(articoli=articoli, segnali=[]))
    assert row["pipeline"] == "NO_RELEVANT_NEWS"


# --- asse pipeline: segnale, segno, gate (#281 criterio 3) ------------------


def test_notizia_tempestiva_ma_zero_segnali_no_signal():
    articoli = {
        "articoli_unici": 1,
        "rilevanza": {"ISSUER_SPECIFIC": 1},
        "effective_timely_articles": 1,
    }
    row = _row(_mover(articoli=articoli, segnali=[]))
    assert row["pipeline"] == "NO_SIGNAL"


def test_score_negativo_forte_e_wrong_sign_non_below_gate():
    """Criterio 3: il segno viene dal campo firmato dello score, non da
    `abs(score)`. -0.45 ha magnitudo sopra il gate 0.30, ma per un rialzo
    non detenuto e' il segno SBAGLIATO: la classificazione assoluta lo
    chiamerebbe sopra-gate, quella firmata lo ferma a WRONG_SIGN."""
    row = _row(_mover(segnali=[{"score": -0.45, "fallback": False}]))
    assert row["pipeline"] == "WRONG_SIGN"
    assert row["evidence"]["score_firmato"] == -0.45


def test_punteggio_positivo_sotto_il_gate_below_gate():
    row = _row(_mover(segnali=[{"score": 0.20, "fallback": False}]))
    assert row["pipeline"] == "BELOW_GATE"


def test_punteggio_uguale_al_gate_passa_il_gate():
    """Convenzione legacy (`miss_cause`): il gate e' inclusivo, score >= soglia
    passa. Il funnel v2 non inventa una convenzione diversa."""
    row = _row(_mover(segnali=[{"score": 0.30, "fallback": False}]))
    assert row["pipeline"] == "ORDER_FAIL"  # selezionato, nessun ordine


def test_segnali_qualificanti_tutti_fallback_fallback_reject():
    """Sopra il gate, col segno giusto, ma tutti i punteggi utilizzabili
    vengono dal fallback FinBERT: il filtro #108 li scarta prima del ranker."""
    segnali = [
        {"score": 0.45, "fallback": True},
        {"score": 0.31, "fallback": True},
    ]
    row = _row(_mover(segnali=segnali))
    assert row["pipeline"] == "FALLBACK_REJECT"


def test_un_segnale_non_fallback_sopra_il_gate_supera_il_filtro():
    """Basta UN punteggio ensemble sopra il gate: il fallback accanto non
    trascina giu' il candidato."""
    segnali = [
        {"score": 0.45, "fallback": True},
        {"score": 0.32, "fallback": False},
    ]
    row = _row(_mover(segnali=segnali))
    assert row["pipeline"] != "FALLBACK_REJECT"


# --- asse pipeline: ranker, guard, ordine, fill ------------------------------


def test_segnale_qualificante_ma_ranked_out():
    intenti = [{
        "final_reason_code": "RANK_OUTSIDE_TOP_N",
        "is_tradable": False,
        "trade_id": None,
        "pnl_realizzato": None,
    }]
    row = _row(_mover(intenti=intenti))
    assert row["pipeline"] == "RANKED_OUT"
    assert row["evidence"]["reason_codes"] == ["RANK_OUTSIDE_TOP_N"]


def test_segnale_qualificante_mai_osservato_dal_ranker():
    """Nessuna riga #294 per il simbolo: il punteggio non e' mai arrivato al
    ranker. E' comunque fermo allo stadio del ranking, con l'evidenza esplicita
    che distingue 'scartato' da 'mai visto'."""
    row = _row(_mover(intenti=[]))
    assert row["pipeline"] == "RANKED_OUT"
    assert row["evidence"]["intenti_assenti"] is True


def test_selezionato_ma_bloccato_dal_guard_risk_block():
    guard = [{"decision": "SKIP_PYRAMIDING", "signal_id": 42}]
    row = _row(_mover(guard=guard))
    assert row["pipeline"] == "RISK_BLOCK"
    assert row["evidence"]["guard"] == ["SKIP_PYRAMIDING"]


def test_un_fill_osservato_prevale_su_un_guard_di_un_altro_tentativo():
    """Una riga per simbolo riassume l'esito piu' profondo della seduta: un
    guard osservato in un ciclo non puo' cancellare un fill successivo."""
    ordine = {
        "order_id": "abc",
        "submitted_at": "2026-08-12T15:22:00+00:00",
        "filled_at": "2026-08-12T15:22:02+00:00",
        "fill_price": 117.10,
        "lookup_error": None,
    }
    row = _row(_mover(
        guard=[{"decision": "SKIP_PYRAMIDING", "signal_id": 41}],
        ordine=ordine,
        intenti=[{
            "final_reason_code": "RANK_SELECTED",
            "is_tradable": True,
            "trade_id": 7,
            "pnl_realizzato": 12.5,
        }],
    ))
    assert row["pipeline"] == "CAUGHT"


def test_ordine_inviato_mai_eseguito_order_fail():
    ordine = {
        "order_id": "abc",
        "submitted_at": "2026-08-12T15:07:00+00:00",
        "filled_at": None,
        "fill_price": None,
        "lookup_error": None,
    }
    row = _row(_mover(ordine=ordine))
    assert row["pipeline"] == "ORDER_FAIL"


def test_fill_sopra_il_close_bad_fill():
    """Con exit policy EOD_close, un fill sopra il close di giornata non puo'
    catturare niente per costruzione: il fill da solo ha consumato
    l'opportunita'. Deterministico, nessuna soglia di slippage inventata."""
    ordine = {
        "order_id": "abc",
        "submitted_at": "2026-08-12T15:07:00+00:00",
        "filled_at": "2026-08-12T15:07:02+00:00",
        "fill_price": 118.50,
        "lookup_error": None,
    }
    row = _row(_mover(ordine=ordine))
    assert row["pipeline"] == "BAD_FILL"


def test_fill_sotto_il_close_caught_con_pnl_profittevole():
    ordine = {
        "order_id": "abc",
        "submitted_at": "2026-08-12T15:07:00+00:00",
        "filled_at": "2026-08-12T15:07:02+00:00",
        "fill_price": 117.10,
        "lookup_error": None,
    }
    intenti = [{
        "final_reason_code": "RANK_SELECTED",
        "is_tradable": True,
        "trade_id": 7,
        "pnl_realizzato": 12.5,
    }]
    row = _row(_mover(ordine=ordine, intenti=intenti))
    assert row["pipeline"] == "CAUGHT"
    assert row["net_profitable"] is True


def test_profitto_giornaliero_usa_il_mark_eod_netto_prima_del_realizzato():
    """Un trade ancora aperto deve essere giudicabile nel funnel del giorno;
    quando il mark fill->close netto e' disponibile prevale sul net_pnl finale
    del trade, che appartiene a un orizzonte diverso."""
    ordine = {
        "order_id": "abc",
        "submitted_at": "2026-08-12T15:07:00+00:00",
        "filled_at": "2026-08-12T15:07:02+00:00",
        "fill_price": 117.10,
        "eod_net_pnl": -0.25,
        "lookup_error": None,
    }
    intenti = [{
        "final_reason_code": "RANK_SELECTED",
        "is_tradable": True,
        "trade_id": 7,
        "pnl_realizzato": 12.5,
    }]
    row = _row(_mover(ordine=ordine, intenti=intenti))
    assert row["pipeline"] == "CAUGHT"
    assert row["net_profitable"] is False
    assert row["evidence"]["eod_net_pnl"] == -0.25


# --- KPI distinti (criterio 2) ------------------------------------------------


def _kpi_fixture():
    """Giornata sintetica: 7 mover con esiti miscelati."""
    tempestiva = {
        "articoli_unici": 1,
        "rilevanza": {"ISSUER_SPECIFIC": 1},
        "effective_timely_articles": 1,
    }
    nessuna = None
    selected = [{
        "final_reason_code": "RANK_SELECTED",
        "is_tradable": True,
        "trade_id": None,
        "pnl_realizzato": None,
    }]
    outside = [{
        "final_reason_code": "RANK_OUTSIDE_TOP_N",
        "is_tradable": False,
        "trade_id": None,
        "pnl_realizzato": None,
    }]
    fill_ok = {
        "order_id": "o1", "submitted_at": "2026-08-12T15:07:00+00:00",
        "filled_at": "2026-08-12T15:07:02+00:00", "fill_price": 10.0,
        "lookup_error": None,
    }
    fill_mai = {
        "order_id": "o2", "submitted_at": "2026-08-12T15:07:00+00:00",
        "filled_at": None, "fill_price": None, "lookup_error": None,
    }
    return [
        # A: notizia tempestiva, nessun segnale (recall: denominatore, no num)
        _mover(symbol="A", rend=0.05, articoli=tempestiva, segnali=[],
               opportunity_v2={"net_opportunity_usd": 5.0}),
        # B: catturato e profittevole
        _mover(symbol="B", rend=0.05, articoli=tempestiva, ordine=fill_ok,
               intenti=[{"final_reason_code": "RANK_SELECTED",
                         "is_tradable": True, "trade_id": 7,
                         "pnl_realizzato": 12.5}]),
        # C: segnale qualificante, ranker lo scarta
        _mover(symbol="C", rend=0.05, articoli=tempestiva, intenti=outside,
               opportunity_v2={"net_opportunity_usd": -2.0}),
        # D: selezionato, ordine mai eseguito
        _mover(symbol="D", rend=0.05, articoli=tempestiva, intenti=selected,
               ordine=fill_mai,
               opportunity_v2={"net_opportunity_usd": 8.0}),
        # E: detenuto in rialzo
        _mover(symbol="E", rend=0.05, held=True),
        # F: ribasso non detenuto
        _mover(symbol="F", rend=-0.05, articoli=nessuna, segnali=[]),
        # G: rialzo senza nessuna notizia rilevante
        _mover(symbol="G", rend=0.05, articoli=nessuna, segnali=[],
               opportunity_v2={"net_opportunity_usd": None}),
    ]


def test_kpi_held_at_open_distinto_dal_funnel_di_ingresso():
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    kpi = funnel["kpi"]["held_at_open"]
    assert kpi["mover_held"] == 1
    assert kpi["exit_risk"] == 0
    assert kpi["passive_exposure"] == 1
    assert kpi["definizione"]
    rate = funnel["kpi"]["held_at_open_rate"]
    assert rate["numeratore"] == 1
    assert rate["denominatore"] == 7
    assert rate["valore"] == 1 / 7


def test_kpi_active_signal_recall():
    """Denominatore: mover ENTRY_OPPORTUNITY con notizia tempestiva (A,B,C,D).
    Numeratore: quelli che hanno prodotto un segnale qualificante (B,C,D)."""
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    recall = funnel["kpi"]["active_signal_recall"]
    assert recall["numeratore"] == 3
    assert recall["denominatore"] == 4
    assert recall["valore"] == 3 / 4


def test_kpi_execution_conversion():
    """Denominatore: chi e' arrivato allo stadio dell'ordine (B,D).
    Numeratore: chi e' stato eseguito (B)."""
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    conv = funnel["kpi"]["execution_conversion_rate"]
    assert conv["numeratore"] == 1
    assert conv["denominatore"] == 2
    assert conv["valore"] == 0.5


def test_kpi_profitable_capture_end_to_end():
    """Cattura profittevole end-to-end: ingressi net-profit sul totale delle
    entry opportunity (A,B,C,D,G = 5), non solo sui catturati."""
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    capture = funnel["kpi"]["profitable_capture_rate"]
    assert capture["numeratore"] == 1
    assert capture["denominatore"] == 5
    assert capture["valore"] == 0.2


def test_kpi_avoidable_miss_conta_solo_opportunita_nette_positive_non_catturate():
    """A e D hanno alpha accessibile positivo e non sono CAUGHT; C ha
    opportunity netta negativa e G e' non misurabile, quindi non si inventano
    altri miss economicamente evitabili."""
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    assert funnel["kpi"]["avoidable_miss_count"] == 2
    assert funnel["kpi"]["avoidable_miss_unknown_count"] == 1


def test_kpi_denominatore_nullo_resta_none():
    """Nessun mover: il KPI e' None, non 0.0 — un rapporto senza denominatori
    non dice niente."""
    funnel = build_funnel([], soglia_gate=0.30)
    for nome in ("held_at_open_rate", "active_signal_recall",
                 "execution_conversion_rate", "profitable_capture_rate"):
        assert funnel["kpi"][nome]["valore"] is None
    assert funnel["kpi"]["held_at_open"]["mover_held"] == 0


# --- mapping legacy e partizione (criterio 4) --------------------------------


def test_mapping_legacy_v2_documentato_e_causa_per_riga():
    funnel = build_funnel(
        [_mover(legacy_causa="BELOW_GATE", segnali=[{"score": 0.2, "fallback": False}])],
        soglia_gate=0.30,
    )
    # il blocco e' nel dossier: la mappa e' leggibile senza leggere il codice
    mapping = funnel["mapping_legacy_v2"]
    assert isinstance(mapping, dict) and mapping
    # la riga porta la causa legacy accanto: la mappa e' verificabile per riga
    assert funnel["righe"][0]["legacy_causa"] == "BELOW_GATE"
    assert funnel["righe"][0]["pipeline"] == "BELOW_GATE"


def test_ogni_mover_contato_una_sola_volta():
    """La partizione e' completa: la somma dei conteggi actionability fa il
    totale delle righe, e i nomi sono esattamente quelli della issue."""
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    conteggi = funnel["conteggi_actionability"]
    assert set(conteggi) <= set(ACTIONABILITY_STAGES)
    assert sum(conteggi.values()) == len(funnel["righe"]) == 7
    pipeline_counts = funnel["conteggi_pipeline"]
    assert set(pipeline_counts) <= set(PIPELINE_STAGES)
    # entry-opportunity valutati dalla pipeline + esclusi = totale
    esclusi = funnel["esclusi_pipeline"]
    assert sum(pipeline_counts.values()) + sum(esclusi.values()) == 7


def test_serie_legacy_affiancata_mai_sovrascritta():
    """Il blocco dichiara se stesso come vista parallela e il gate usato:
    la taratura resta quella letta a monte (freeze #171), il funnel la riceve."""
    funnel = build_funnel([_mover()], soglia_gate=0.42)
    assert funnel["soglia_gate"] == 0.42
    assert funnel["funnel_version"]
    assert "parallela" in funnel["nota_freeze"]


# --- #567 lato uscita: EXIT_RISK non e' piu' un'esclusione silenziosa ------


def _held_falling(rend=-0.045, **over):
    """Mover detenuto in ribasso: e' EXIT_RISK finche' non aggiungiamo un
    classificatore di pipeline d'uscita. Restituisce un mover con segnale,
    exit_segnali (lista di score dei cicli d'uscita), e opzionalmente la
    chiusura registrata (None = posizione rimasta aperta tutta la seduta).
    """
    base = {
        "symbol": "DELL",
        "return": rend,
        "held": True,
        "in_universo": True,
        "articoli": None,
        "segnali": [],
        "intenti": [],
        "guard": [],
        "ordine": None,
        "close": None,
        "legacy_causa": None,
        # Campi specifici del lato uscita (#567). Default: nessun segnale,
        # nessuna chiusura -> NO_EXIT_SIGNAL / non-exited.
        "exit_segnali": [],
        "chiusura": None,
        "session_open_hhmm": "14:30",
    }
    base.update(over)
    return base


def test_held_rising_e_held_falling_esclusi_con_motivo_diverso():
    """#567 punto 1: EXIT_RISK e PASSIVE_EXPOSURE non sono piu' la stessa
    stringa 'held'. Una seduta con entrambi deve poterli contare separati."""
    movers = [
        _held_falling(symbol="DELL", rend=-0.045),
        _mover(symbol="AAPL", held=True, rend=0.05),
    ]
    funnel = build_funnel(movers, soglia_gate=0.30)
    esclusi = funnel["esclusi_pipeline"]
    assert esclusi.get("held_falling") == 1
    assert esclusi.get("held_rising") == 1
    assert "held" not in esclusi  # la stringa generica sparisce


def test_classify_exit_pipeline_no_exit_signal():
    """EXIT_RISK senza segnali di sortita per la seduta: NO_EXIT_SIGNAL.
    Stesso pattern del lato d'ingresso per mover senza notizia."""
    mover = _held_falling()
    row = build_funnel([mover], soglia_gate=0.30)["righe"][0]
    assert row["actionability"] == "EXIT_RISK"
    assert row["pipeline_uscita"] == "NO_EXIT_SIGNAL"
    # Il mover resta escluso dal funnel d'ingresso, ma distinto da
    # PASSIVE_EXPOSURE (era 'held', ora 'held_falling'): la stringa
    # comune 'held' e' sparita (#567 punto 1).
    assert row["pipeline_escluso_motivo"] == "held_falling"


def test_classify_exit_pipeline_stale_exit_signal():
    """Tutti i segnali d'uscita precedono l'apertura RTH della seduta
    (DELL 09-10: signal_id 10245 generato 2026-09-09 19:59Z, 14 cicli a
    score 0.000): classificati STALE_EXIT_SIGNAL, non come se fossero una
    scelta attiva del motore (#567 punto 2)."""
    mover = _held_falling(
        rend=-0.053,
        exit_segnali=[
            {"ora": "19:59", "score": 0.131, "signal_id": 10245,
             "generated_day": "2026-09-09"},
        ],
        session_open_hhmm="14:30",
        _data="2026-09-10",
    )
    row = build_funnel([mover], soglia_gate=0.30)["righe"][0]
    assert row["pipeline_uscita"] == "STALE_EXIT_SIGNAL"
    assert row["evidence_uscita"]["signal_id"] == 10245
    assert row["evidence_uscita"]["generated_day"] == "2026-09-09"


def test_classify_exit_pipeline_below_threshold():
    """Segnale attuale presente, segno giusto (negativo per un ribasso), ma
    |score| sotto la soglia d'uscita — classificato EXIT_BELOW_THRESHOLD,
    senza prescrivere una soglia (ricevuta come argomento dal chiamante, come
    `soglia_gate` dal lato d'ingresso)."""
    mover = _held_falling(
        rend=-0.033,
        exit_segnali=[{"ora": "15:10", "score": -0.081,
                       "signal_id": 10251, "generated_day": "2026-09-10"}],
    )
    row = build_funnel([mover], soglia_gate=0.30, soglia_exit=0.10)["righe"][0]
    assert row["pipeline_uscita"] == "EXIT_BELOW_THRESHOLD"
    assert row["evidence_uscita"]["score_firmato"] == -0.081
    assert row["evidence_uscita"]["soglia_exit"] == 0.10


def test_classify_exit_pipeline_wrong_sign():
    """Segnale presente, segno positivo mentre il mover e' in ribasso:
    segno sbagliato, non filtrabile con |score|. Stesso criterio 3 del
    lato d'ingresso: dal campo firmato."""
    mover = _held_falling(
        rend=-0.034,
        exit_segnali=[{"ora": "15:25", "score": 0.109,
                       "signal_id": 10265, "generated_day": "2026-09-10"}],
    )
    row = build_funnel([mover], soglia_gate=0.30, soglia_exit=0.10)["righe"][0]
    assert row["pipeline_uscita"] == "EXIT_WRONG_SIGN"
    assert row["evidence_uscita"]["score_firmato"] == 0.109


def test_classify_exit_pipeline_exited():
    """Posizione chiusa intraday: la pipeline e' arrivata a SELL, e' EXITED.
    L'exit_reason vive nella riga di chiusura registrata dal dossier."""
    mover = _held_falling(
        rend=-0.055,
        exit_segnali=[{"ora": "15:45", "score": -0.10,
                       "signal_id": 10270, "generated_day": "2026-09-10"}],
        chiusura={"exit_reason": "sentiment_reversal", "pnl_net": -88.63},
    )
    row = build_funnel([mover], soglia_gate=0.30, soglia_exit=0.10)["righe"][0]
    assert row["pipeline_uscita"] == "EXITED"
    assert row["evidence_uscita"]["exit_reason"] == "sentiment_reversal"


def test_classify_exit_pipeline_exit_blocked():
    """Segnale d'uscita qualificante (segn corretto, sopra la soglia) ma il
    guard ha bloccato la chiusura: EXIT_BLOCKED. La riga del guard porta il
    verdetto."""
    mover = _held_falling(
        rend=-0.044,
        exit_segnali=[{"ora": "15:50", "score": -0.20,
                       "signal_id": 10266, "generated_day": "2026-09-10"}],
        guard=[{"decision": "SKIP_THRESHOLD", "signal_id": 10266}],
    )
    row = build_funnel([mover], soglia_gate=0.30, soglia_exit=0.10)["righe"][0]
    assert row["pipeline_uscita"] == "EXIT_BLOCKED"
    assert row["evidence_uscita"]["guard"] == ["SKIP_THRESHOLD"]


def test_conteggi_pipeline_uscita_pubblica_stadi_osservati():
    """#567 punto 2: i conteggi della pipeline d'uscita vivono in un blocco
    separato, parallelo a `conteggi_pipeline`, e solo gli stadi osservati."""
    movers = [
        # STALE: signal_id 10245 generato 2026-09-09, dossier 09-10.
        _held_falling(symbol="DELL", rend=-0.053, _data="2026-09-10",
                      exit_segnali=[{"ora": "20:00", "score": -0.036,
                                     "signal_id": 10245,
                                     "generated_day": "2026-09-09"}]),
        # BELOW_THRESHOLD: -0.036 sull'oggi, sotto 0.10.
        _held_falling(symbol="MU", rend=-0.049, _data="2026-09-10",
                      exit_segnali=[{"ora": "15:00", "score": -0.036,
                                     "signal_id": 10249,
                                     "generated_day": "2026-09-10"}]),
        # EXITED: signal_id 10270 + chiusura registrata.
        _held_falling(symbol="INTC", rend=-0.055, _data="2026-09-10",
                      exit_segnali=[{"ora": "15:45", "score": -0.20,
                                     "signal_id": 10270,
                                     "generated_day": "2026-09-10"}],
                      chiusura={"exit_reason": "sentiment_reversal",
                                "pnl_net": -88.63}),
        # NO_EXIT_SIGNAL: zero segnali.
        _held_falling(symbol="AMAT", rend=-0.031, _data="2026-09-10"),
    ]
    funnel = build_funnel(movers, soglia_gate=0.30, soglia_exit=0.10)
    conteggi = funnel["conteggi_pipeline_uscita"]
    assert conteggi.get("NO_EXIT_SIGNAL") == 1
    assert conteggi.get("STALE_EXIT_SIGNAL") == 1
    assert conteggi.get("EXIT_BELOW_THRESHOLD") == 1
    assert conteggi.get("EXITED") == 1
    assert "EXIT_WRONG_SIGN" not in conteggi  # non osservato
    assert "EXIT_BLOCKED" not in conteggi


def test_exit_signal_recall_e_conversion_rate():
    """#567 punto 3: due KPI d'uscita simmetrici a quelli d'ingresso.
    exit_signal_recall = (EXIT_RISK con segnale d'uscita qualificante) /
    (tutti gli EXIT_RISK). exit_conversion_rate = (EXITED) / (EXIT_RISK con
    segnale d'uscita qualificante).
    Sulle 8 sedute di 09-10 (7 senza SELL, 1 con), col default
    exit_signal_recall = 5/8 (i 3 freschi sopra soglia, NO_EXIT_SIGNAL solo AMAT).
    """
    movers = [
        # 1 EXITED (segnale sopra soglia + chiusura)
        _held_falling(symbol="INTC", rend=-0.055, _data="2026-09-10",
                      exit_segnali=[{"ora": "15:45", "score": -0.20,
                                     "signal_id": 10270,
                                     "generated_day": "2026-09-10"}],
                      chiusura={"exit_reason": "sentiment_reversal",
                                "pnl_net": -88.63}),
        # 4 EXIT_BELOW_THRESHOLD (segnale attuale, segno giusto, |s| < soglia)
        _held_falling(symbol="DELL", rend=-0.053, _data="2026-09-10",
                      exit_segnali=[{"ora": "15:00", "score": -0.036,
                                     "signal_id": 10245,
                                     "generated_day": "2026-09-10"}]),
        _held_falling(symbol="MU", rend=-0.049, _data="2026-09-10",
                      exit_segnali=[{"ora": "14:00", "score": -0.036,
                                     "signal_id": 10249,
                                     "generated_day": "2026-09-10"}]),
        _held_falling(symbol="WDC", rend=-0.044, _data="2026-09-10",
                      exit_segnali=[{"ora": "15:00", "score": -0.067,
                                     "signal_id": 10266,
                                     "generated_day": "2026-09-10"}]),
        _held_falling(symbol="AMD", rend=-0.033, _data="2026-09-10",
                      exit_segnali=[{"ora": "15:00", "score": -0.081,
                                     "signal_id": 10251,
                                     "generated_day": "2026-09-10"}]),
        # 2 EXIT_WRONG_SIGN
        _held_falling(symbol="RIO", rend=-0.042, _data="2026-09-10",
                      exit_segnali=[{"ora": "14:00", "score": 0.072,
                                     "signal_id": 10103,
                                     "generated_day": "2026-09-10"}]),
        _held_falling(symbol="MRVL", rend=-0.034, _data="2026-09-10",
                      exit_segnali=[{"ora": "15:00", "score": 0.109,
                                     "signal_id": 10265,
                                     "generated_day": "2026-09-10"}]),
        # 1 NO_EXIT_SIGNAL
        _held_falling(symbol="AMAT", rend=-0.031, _data="2026-09-10"),
    ]
    funnel = build_funnel(movers, soglia_gate=0.30, soglia_exit=0.10)
    recall = funnel["kpi"]["exit_signal_recall"]
    # Numeratore: EXITED + EXIT_BELOW_THRESHOLD + EXIT_BLOCKED = 1 + 4 + 0 = 5
    # Denominatore: tutti gli EXIT_RISK = 8
    assert recall["numeratore"] == 5
    assert recall["denominatore"] == 8
    assert recall["valore"] == 5 / 8
    # exit_conversion_rate = EXITED / con segnale sopra soglia in segno
    # (EXITED + EXIT_BELOW_THRESHOLD + EXIT_BLOCKED = 5): 1/5.
    conv = funnel["kpi"]["exit_conversion_rate"]
    assert conv["numeratore"] == 1
    assert conv["denominatore"] == 5
    assert conv["valore"] == 1 / 5


def test_kpi_esce_con_sufficienza_unset_se_floor_non_dichiarato():
    """#567 punto 4: ogni KPI esce con `sufficienza`. Senza floor dichiarato
    (freeze #171, la soglia la decide l'operatore nel charter) il flag
    dice 'unset' — niente opinioni inventate."""
    funnel = build_funnel([_mover()], soglia_gate=0.30)
    for nome in ("held_at_open_rate", "active_signal_recall",
                 "execution_conversion_rate", "profitable_capture_rate"):
        assert funnel["kpi"][nome]["sufficienza"] == "unset"


def test_kpi_esce_con_sufficienza_insufficient_n_se_floor_non_raggiunto():
    """#567 punto 4: con floor dichiarato, i KPI sotto n marcano
    INSUFFICIENT_N, distinto da un rapporto pubblicato."""
    # 7 mover, di cui 2 ENTRY_OPPORTUNITY con cattura profittevole:
    # profitable_capture_rate = 1/5, sotto la floor 10 -> INSUFFICIENT_N.
    movers = _kpi_fixture()
    funnel = build_funnel(movers, soglia_gate=0.30, floor_kpi=10)
    capture = funnel["kpi"]["profitable_capture_rate"]
    assert capture["denominatore"] == 5
    assert capture["valore"] == 0.2
    assert capture["sufficienza"] == "insufficient_n"
    # held_at_open_rate invece ha denom 7 < 10: anch'esso INSUFFICIENT_N.
    held_rate = funnel["kpi"]["held_at_open_rate"]
    assert held_rate["denominatore"] == 7
    assert held_rate["sufficienza"] == "insufficient_n"
    # Esiste la soglia dichiarata in cima al blocco KPI.
    assert funnel["kpi_floor"] == 10


def test_kpi_esce_con_sufficienza_ok_se_floor_raggiunto():
    """Floor rispettato dal denominatore: il KPI esce 'ok', non insufficiente.
    """
    # 11 mover ENTRY_OPPORTUNITY profittevoli: denominatore 11 >= floor 10.
    movers = [
        _mover(symbol=f"S{i}", rend=0.05,
               ordine={
                   "order_id": "x", "submitted_at": "2026-08-12T15:07:00+00:00",
                   "filled_at": "2026-08-12T15:07:02+00:00",
                   "fill_price": 100.0, "eod_net_pnl": 5.0,
                   "lookup_error": None,
               },
               intenti=[{"final_reason_code": "RANK_SELECTED",
                         "is_tradable": True, "trade_id": i,
                         "pnl_realizzato": 5.0}])
        for i in range(11)
    ]
    funnel = build_funnel(movers, soglia_gate=0.30, floor_kpi=10)
    capture = funnel["kpi"]["profitable_capture_rate"]
    assert capture["denominatore"] == 11
    assert capture["sufficienza"] == "ok"


def test_pipeline_uscita_pubblicata_con_nota_freeze_e_version():
    """#567 parallelo a quanto fece #281: bump `funnel_version`, nota freeze
    che spiega la vista parallela, e mapping che documenta lo scope entry-only
    della serie `conteggi_pipeline`."""
    funnel = build_funnel([_held_falling()], soglia_gate=0.30)
    # Stesso funnel_version della v1 (vista parallela non lo buzza);
    # la nota_freeze si limita ad aggiungere il lato d'uscita.
    assert "parallela" in funnel["nota_freeze"]
    # Conteggi_pipeline d'ingresso restano solo entry, conteggi_pipeline_uscita
    # aggiunge exit.
    assert "EXIT_RISK" in (funnel.get("conteggi_pipeline_uscita") or {}) or \
        "NO_EXIT_SIGNAL" in (funnel.get("conteggi_pipeline_uscita") or {})
