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
    assert row["pipeline_escluso_motivo"] == "held"


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
        _mover(symbol="A", rend=0.05, articoli=tempestiva, segnali=[]),
        # B: catturato e profittevole
        _mover(symbol="B", rend=0.05, articoli=tempestiva, ordine=fill_ok,
               intenti=[{"final_reason_code": "RANK_SELECTED",
                         "is_tradable": True, "trade_id": 7,
                         "pnl_realizzato": 12.5}]),
        # C: segnale qualificante, ranker lo scarta
        _mover(symbol="C", rend=0.05, articoli=tempestiva, intenti=outside),
        # D: selezionato, ordine mai eseguito
        _mover(symbol="D", rend=0.05, articoli=tempestiva, intenti=selected,
               ordine=fill_mai),
        # E: detenuto in rialzo
        _mover(symbol="E", rend=0.05, held=True),
        # F: ribasso non detenuto
        _mover(symbol="F", rend=-0.05, articoli=nessuna, segnali=[]),
        # G: rialzo senza nessuna notizia rilevante
        _mover(symbol="G", rend=0.05, articoli=nessuna, segnali=[]),
    ]


def test_kpi_held_at_open_distinto_dal_funnel_di_ingresso():
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    kpi = funnel["kpi"]["held_at_open"]
    assert kpi["mover_held"] == 1
    assert kpi["exit_risk"] == 0
    assert kpi["passive_exposure"] == 1
    assert kpi["definizione"]


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
    conv = funnel["kpi"]["execution_conversion"]
    assert conv["numeratore"] == 1
    assert conv["denominatore"] == 2
    assert conv["valore"] == 0.5


def test_kpi_profitable_capture_end_to_end():
    """Cattura profittevole end-to-end: ingressi net-profit sul totale delle
    entry opportunity (A,B,C,D,G = 5), non solo sui catturati."""
    funnel = build_funnel(_kpi_fixture(), soglia_gate=0.30)
    capture = funnel["kpi"]["profitable_capture"]
    assert capture["numeratore"] == 1
    assert capture["denominatore"] == 5
    assert capture["valore"] == 0.2


def test_kpi_denominatore_nullo_resta_none():
    """Nessun mover: il KPI e' None, non 0.0 — un rapporto senza denominatori
    non dice niente."""
    funnel = build_funnel([], soglia_gate=0.30)
    for nome in ("active_signal_recall", "execution_conversion",
                 "profitable_capture"):
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