"""#279 — copertura effettiva e attribution articolo -> segnale.

Le righe ``news_log`` non sono articoli: la stessa syndication puo' comparire da
piu' fonti e lo stesso articolo puo' essere replicato su piu' ticker. Questi test
fissano il contratto del modulo puro prima del wiring nel dossier.
"""

from datetime import datetime, timezone

from src.analysis.dossier.article_coverage import (
    build_article_coverage,
    canonical_article_id,
    classify_timing,
    content_empty_title_reason,
    derive_bare_stem,
    expand_aliases_with_stem,
    propose_stem_backfill,
)


UTC = timezone.utc
OPEN = datetime(2026, 8, 12, 13, 30, tzinfo=UTC)
CLOSE = datetime(2026, 8, 12, 20, 0, tzinfo=UTC)


def _row(
    news_log_id: int,
    ticker: str,
    title: str,
    *,
    body_snippet: str | None = None,
    content_hash: str = "",
    source: str = "alpaca_benzinga",
    published_at: datetime | None = OPEN,
    first_seen_at: datetime | None = OPEN,
    signal_id: int | None = None,
    score: float | None = None,
    extraction_method: str = "source_metadata",
    issuer_terms: list[str] | None = None,
    ground_truth_relevance: str | None = None,
    ground_truth_tickers: list[str] | None = None,
) -> dict:
    return {
        "news_log_id": news_log_id,
        "ticker": ticker,
        "title": title,
        "body_snippet": title if body_snippet is None else body_snippet,
        "url": f"https://{source}.example/{news_log_id}",
        "source": source,
        "published_at": published_at,
        "first_seen_at": first_seen_at,
        "content_hash": content_hash,
        "extraction_method": extraction_method,
        "issuer_terms": issuer_terms or [],
        "signal_id": signal_id,
        "score": score,
        "ground_truth_relevance": ground_truth_relevance,
        "ground_truth_tickers": ground_truth_tickers,
    }


def test_canonical_id_deduplica_syndication_cross_source_in_modo_riproducibile():
    a = _row(1, "NVDA", "Nvidia unveils Blackwell", content_hash="A" * 64)
    b = _row(2, "NVDA", "Titolo riscritto", content_hash="a" * 64, source="reuters")
    assert canonical_article_id(a) == canonical_article_id(b) == f"content:{'a' * 64}"

    # Il fallback storico (content_hash assente) deduplica titoli identici dopo
    # normalizzazione Unicode/spazi, senza dipendere da URL o fonte.
    c = _row(3, "NVDA", "  NVIDIA   unveils Blackwell  ")
    d = _row(4, "NVDA", "nvidia unveils blackwell", source="reuters")
    assert canonical_article_id(c) == canonical_article_id(d)
    assert canonical_article_id(c).startswith("title:")


def test_timing_ha_tre_bucket_espliciti_e_unknown():
    assert classify_timing(OPEN.replace(hour=12), OPEN, CLOSE) == "ANTICIPATORY"
    assert classify_timing(OPEN, OPEN, CLOSE) == "CONCURRENT"
    assert classify_timing(CLOSE, OPEN, CLOSE) == "CONCURRENT"
    assert classify_timing(CLOSE.replace(hour=21), OPEN, CLOSE) == "RETROSPECTIVE"
    assert classify_timing(None, OPEN, CLOSE) == "UNKNOWN"


def test_detector_content_empty_copre_solo_i_template_pre_registrati():
    assert content_empty_title_reason(
        "Here's How Much $1000 Invested In Meta Platforms 10 Years Ago "
        "Would Be Worth Today"
    ) == "EVERGREEN_RETURN_TEMPLATE"
    assert content_empty_title_reason(
        "6 Financials Stocks Whale Activity In Today's Session"
    ) == "WHALE_ACTIVITY_TEMPLATE"
    assert content_empty_title_reason(
        "This OGE Energy Analyst Turns Bullish; Here Are Top 4 Upgrades For Wednesday"
    ) == "RATINGS_LISTICLE_TEMPLATE"
    assert content_empty_title_reason(
        "Apple raises guidance after stronger iPhone demand"
    ) is None


def test_copertura_deduplica_articoli_separa_relevance_e_attribuisce_ogni_segnale():
    rows = [
        # Una syndication issuer-specific su AAPL: due righe e due segnali, ma
        # un solo articolo effettivo per la copertura.
        _row(1, "AAPL", "Apple launches a new iPhone", content_hash="1" * 64,
             source="wire_a", published_at=OPEN.replace(hour=12),
             first_seen_at=OPEN.replace(hour=12, minute=5), signal_id=101, score=0.42,
             issuer_terms=["Apple", "AAPL"]),
        _row(2, "AAPL", "Apple launches a new iPhone", content_hash="1" * 64,
             source="wire_b", published_at=OPEN.replace(hour=12, minute=2),
             first_seen_at=OPEN.replace(hour=12, minute=10), signal_id=102, score=0.31,
             issuer_terms=["Apple", "AAPL"]),
        # Un solo articolo macro replicato su due ticker: due mapping fan-out,
        # nessuna copertura effettiva issuer-specific.
        _row(3, "AAPL", "Fed keeps rates unchanged", content_hash="2" * 64,
             signal_id=103, score=0.20, ground_truth_relevance="macro",
             ground_truth_tickers=[]),
        _row(4, "MSFT", "Fed keeps rates unchanged", content_hash="2" * 64,
             signal_id=104, score=-0.25, ground_truth_relevance="macro",
             ground_truth_tickers=[]),
        # org_lookup decidibile, ma nessun alias Nvidia nel testo: false entity
        # match (la classe di NOK <- Nokian Renkaat descritta dalla issue).
        _row(5, "NVDA", "Nokian Renkaat names a new CFO", content_hash="3" * 64,
             source="gdelt_gkg", extraction_method="org_lookup",
             signal_id=105, score=0.05, issuer_terms=["Nvidia", "NVDA"]),
        # Ground truth irrilevante e mapping multi-ticker: fan-out irrilevante.
        _row(6, "AAPL", "Ten stocks mentioned in passing", content_hash="4" * 64,
             signal_id=106, score=0.18, ground_truth_relevance="irrelevant",
             ground_truth_tickers=[]),
        _row(7, "MSFT", "Ten stocks mentioned in passing", content_hash="4" * 64,
             signal_id=107, score=-0.30, ground_truth_relevance="irrelevant",
             ground_truth_tickers=[]),
        # Secondo ticker coperto davvero, durante la seduta.
        _row(8, "NVDA", "Nvidia raises guidance", content_hash="5" * 64,
             signal_id=108, score=-0.55,
             ground_truth_relevance="company_specific",
             ground_truth_tickers=["NVDA"]),
    ]

    out = build_article_coverage(
        rows,
        universe=["AAPL", "MSFT", "NVDA"],
        sector_by_ticker={"AAPL": "tech", "MSFT": "tech", "NVDA": "semis"},
        session_open=OPEN,
        session_close=CLOSE,
    )

    assert out["totali"] == {
        "righe_news_log": 8,
        "articoli_unici": 5,
        "duplicati_syndication_per_ticker": 1,
        "mapping_fanout_extra": 2,
        "mapping_rilevanza": {
            "ISSUER_SPECIFIC": 2,
            "SECTOR_MACRO": 2,
            "FALSE_ENTITY_MATCH": 1,
            "IRRELEVANT_FANOUT": 2,
            "TAG_UNCONFIRMED": 0,
            "UNKNOWN": 0,
        },
        "mapping_content_empty": 0,
        "articoli_effective_timely": 2,
        "articoli_effective_timely_including_content_empty": 2,
    }
    assert out["effective_timely_coverage"] == {
        "ticker_coperti": 2,
        "ticker_universo": 3,
        "quota": 2 / 3,
    }
    assert out["per_ticker"]["AAPL"]["articoli_unici"] == 3
    assert out["per_ticker"]["AAPL"]["effective_timely_articles"] == 1
    assert out["per_ticker"]["AAPL"]["quota_effective_timely"] == 1 / 3
    assert out["per_ticker"]["MSFT"]["effective_timely_articles"] == 0
    assert out["per_ticker"]["NVDA"]["effective_timely_articles"] == 1
    assert out["per_ticker"]["AAPL"]["max_score_own"] == 0.42
    assert out["per_ticker"]["AAPL"]["max_score_fanout"] == 0.20
    assert out["per_ticker"]["MSFT"]["max_score_own"] is None
    assert out["per_ticker"]["MSFT"]["max_score_fanout"] == -0.30

    assert out["concentrazione"]["ticker"] == {
        "top_5_share": 1.0,
        "hhi": 0.5,
        "conteggi": {"AAPL": 1, "NVDA": 1},
    }
    assert out["per_settore"]["tech"]["ticker_coperti"] == 1
    assert out["per_settore"]["semis"]["ticker_coperti"] == 1
    assert sum(v["articoli_unici"] for v in out["per_fonte"].values()) == 5
    assert out["per_fonte"]["wire_a"]["quota_effective_timely"] == 1.0

    segnali = {row["signal_id"]: row for row in out["segnali"]}
    assert set(segnali) == set(range(101, 109))
    assert segnali[101]["attribution"] == "ISSUER_SPECIFIC"
    assert segnali[101]["subject_ticker"] == "AAPL"
    assert segnali[103]["attribution"] == "FANOUT"
    assert segnali[105]["relevance"] == "FALSE_ENTITY_MATCH"
    assert segnali[105]["attribution"] == "UNKNOWN"
    assert segnali[108]["timing"] == "CONCURRENT"


def test_timestamp_mancante_resta_unknown_e_il_tag_non_confermato_e_marcato():
    """Il dato che manca (timestamp) resta UNKNOWN; il dato che c'e' (un testo
    che non cita l'emittente taggata dal provider) dal #405 e' marcato, non
    indovinato."""
    row = _row(
        9,
        "MSFT",
        "Markets await the opening bell",
        published_at=None,
        signal_id=109,
        score=0.11,
        issuer_terms=["Microsoft", "MSFT"],
    )
    out = build_article_coverage(
        [row],
        universe=["MSFT"],
        sector_by_ticker={"MSFT": "tech"},
        session_open=OPEN,
        session_close=CLOSE,
    )
    assert out["totali"]["mapping_rilevanza"]["TAG_UNCONFIRMED"] == 1
    assert out["segnali"][0]["relevance"] == "TAG_UNCONFIRMED"
    assert out["segnali"][0]["timing"] == "UNKNOWN"
    assert out["effective_timely_coverage"]["quota"] == 0.0


def test_tag_provider_non_confermato_dal_testo_diventa_tag_unconfirmed():
    """#405 — caso NVO 2026-08-26: un articolo di Boston Scientific, taggato NVO
    dal provider con ``n_ticker=1``, segna -0.5533 su Novo Nordisk.

    Il percorso ``source_metadata`` era l'unico mai validato (89% delle righe
    scorate): la riga va marcata come tag non confermato dal testo persistito,
    non lasciata nel recipiente UNKNOWN dove il tasso d'errore del percorso non
    e' accumulabile. Non e' FALSE_ENTITY_MATCH: lo snippet e' troncato a 500
    caratteri, quindi l'assenza dell'emittente e' un limite inferiore, non una
    prova.
    """
    rows = [
        _row(
            11,
            "NVO",
            "Boston Scientific Reports Global Disruption After Cybersecurity Incident",
            content_hash="6" * 64,
            signal_id=201,
            score=-0.5533,
            issuer_terms=["Novo Nordisk"],
        ),
    ]
    out = build_article_coverage(
        rows,
        universe=["NVO"],
        sector_by_ticker={"NVO": "farmaceutici"},
        session_open=OPEN,
        session_close=CLOSE,
    )

    assert out["totali"]["mapping_rilevanza"] == {
        "ISSUER_SPECIFIC": 0,
        "SECTOR_MACRO": 0,
        "FALSE_ENTITY_MATCH": 0,
        "IRRELEVANT_FANOUT": 0,
        "TAG_UNCONFIRMED": 1,
        "UNKNOWN": 0,
    }
    # La riga marcata non e' copertura effettiva e non puo' impostare
    # max_score_own: il punteggio piu' forte del ticker resta quello meritato.
    segnale = out["segnali"][0]
    assert segnale["relevance"] == "TAG_UNCONFIRMED"
    assert segnale["attribution"] == "UNKNOWN"
    assert segnale["score"] == -0.5533
    assert out["per_ticker"]["NVO"]["max_score_own"] is None
    assert out["per_ticker"]["NVO"]["effective_timely_articles"] == 0
    assert out["per_ticker"]["NVO"]["rilevanza"]["TAG_UNCONFIRMED"] == 1


def test_tag_non_confermato_su_articolo_fanout_va_in_fanout_mai_in_own():
    """#405 — caso LLY 2026-08-26: l'articolo Rulli/Alphabet mappato anche su LLY.

    Il fan-out resta leggibile come tale (l'articolo e' davvero multi-ticker),
    ma la riga che non cita l'emittente conferma al massimo il punteggio
    fan-out, mai quello issuer-specific.
    """
    titolo = "Ohio Rep. Michael Rulli Sold Up to $100K Worth of Alphabet Stock"
    rows = [
        _row(21, "GOOGL", titolo, content_hash="7" * 64, signal_id=301, score=0.40,
             issuer_terms=["Alphabet", "GOOGL"]),
        _row(22, "LLY", titolo, content_hash="7" * 64, signal_id=302, score=-0.20,
             issuer_terms=["Eli Lilly", "LLY"]),
    ]
    out = build_article_coverage(
        rows,
        universe=["GOOGL", "LLY"],
        sector_by_ticker={"GOOGL": "tech", "LLY": "farmaceutici"},
        session_open=OPEN,
        session_close=CLOSE,
    )

    segnali = {row["signal_id"]: row for row in out["segnali"]}
    assert segnali[301]["relevance"] == "ISSUER_SPECIFIC"
    assert segnali[301]["attribution"] == "ISSUER_SPECIFIC"
    assert segnali[302]["relevance"] == "TAG_UNCONFIRMED"
    assert segnali[302]["attribution"] == "FANOUT"
    assert out["per_ticker"]["LLY"]["max_score_own"] is None
    assert out["per_ticker"]["LLY"]["max_score_fanout"] == -0.20


def test_prova_positiva_e_gt_prevalgono_sul_tag_non_confermato():
    """La fusione dei mapping resta conservativa: una sola riga che cita
    l'emittente, o una label adjudicata, vincono sul tag non confermato di una
    syndication con snippet troncato. GT e prova positiva sono evidenza
    piu' forte del limite inferiore #405."""
    righe_stesso_articolo = [
        _row(31, "MSFT", "Microsoft raises Azure prices", content_hash="8" * 64,
             signal_id=401, score=0.30, issuer_terms=["Microsoft", "MSFT"]),
        _row(32, "MSFT", "Microsoft raises Azure prices", content_hash="8" * 64,
             source="wire_b", signal_id=None, score=None,
             issuer_terms=["Microsoft", "MSFT"],
             body_snippet="Azure prices rise across regions, analysts say the"),
    ]
    out = build_article_coverage(
        righe_stesso_articolo,
        universe=["MSFT"],
        sector_by_ticker={"MSFT": "tech"},
        session_open=OPEN,
        session_close=CLOSE,
    )
    assert out["totali"]["mapping_rilevanza"]["TAG_UNCONFIRMED"] == 0
    assert out["totali"]["mapping_rilevanza"]["ISSUER_SPECIFIC"] == 1

    gt = [
        _row(33, "NVO", "Boston Scientific Reports Global Disruption",
             content_hash="9" * 64, signal_id=402, score=-0.10,
             issuer_terms=["Novo Nordisk"],
             ground_truth_relevance="company_specific",
             ground_truth_tickers=["BSX"]),
    ]
    out_gt = build_article_coverage(
        gt,
        universe=["NVO"],
        sector_by_ticker={"NVO": "farmaceutici"},
        session_open=OPEN,
        session_close=CLOSE,
    )
    # La label dice l'emittente: il verdetto e' deciso, non un limite inferiore.
    assert out_gt["segnali"][0]["relevance"] == "FALSE_ENTITY_MATCH"


def test_source_metadata_senza_testo_persistito_resta_unknown():
    """Senza titolo ne snippet la domanda «il tag e' confermato dal testo?» non
    ha materiale: resta UNKNOWN, non si indovina ne' si marca per assenza."""
    row = _row(
        41,
        "MSFT",
        "",
        body_snippet="",
        published_at=None,
        signal_id=501,
        score=0.10,
        issuer_terms=["Microsoft", "MSFT"],
    )
    out = build_article_coverage(
        [row],
        universe=["MSFT"],
        sector_by_ticker={"MSFT": "tech"},
        session_open=OPEN,
        session_close=CLOSE,
    )
    assert out["totali"]["mapping_rilevanza"]["UNKNOWN"] == 1
    assert out["segnali"][0]["relevance"] == "UNKNOWN"


def test_provenienze_diverse_da_source_metadata_non_marcano_il_tag():
    """Il verdetto TAG_UNCONFIRMED e' specifico del percorso provider-tagged
    (#405); ``gdelt_doc`` (query per nome societario) e le righe senza
    provenienza mantengono il contratto storico UNKNOWN."""
    rows = [
        _row(51, "NVO", "Boston Scientific Reports Global Disruption",
             content_hash="a" * 64, extraction_method="gdelt_doc",
             signal_id=601, score=-0.10, issuer_terms=["Novo Nordisk"]),
        _row(52, "NVO", "Boston Scientific Reports Global Disruption",
             content_hash="b" * 64, extraction_method="",
             signal_id=602, score=-0.10, issuer_terms=["Novo Nordisk"]),
    ]
    out = build_article_coverage(
        rows,
        universe=["NVO"],
        sector_by_ticker={"NVO": "farmaceutici"},
        session_open=OPEN,
        session_close=CLOSE,
    )
    assert out["totali"]["mapping_rilevanza"] == {
        "ISSUER_SPECIFIC": 0,
        "SECTOR_MACRO": 0,
        "FALSE_ENTITY_MATCH": 0,
        "IRRELEVANT_FANOUT": 0,
        "TAG_UNCONFIRMED": 0,
        "UNKNOWN": 2,
    }


def test_per_ticker_attribuisce_le_fonti_per_ticker_anche_se_effective_zero():
    """#511 — un ticker puo' essere cieco effective-timely ma avere righe da un
    provider. La copertura del giorno non distingue "il provider non copre" da
    "il provider copre ma irrilevante". Il dossier espone per ogni ticker le
    fonti che hanno reso almeno un mapping, con il conteggio effective-timely
    di quel provider. Una fonte che non compare non e' coperta; una fonte con
    conteggio zero effective non fa coverage utile ma la sua riga esiste."""
    rows = [
        # alpaca_benzinga copre ASML con un mapping irrilevante (macro fan-out):
        # la riga esiste, effective_timely=0. La fonte DEVE comparire, con zero.
        _row(81, "ASML", "Fed keeps rates unchanged", content_hash="c" * 64,
             source="alpaca_benzinga", signal_id=801, score=0.10),
        # gdelt_gkg copre ASML con un mapping ISSUER_SPECIFIC tempestivo.
        _row(82, "ASML", "ASML raises 2026 capex guidance",
             content_hash="d" * 64, source="gdelt_gkg",
             published_at=OPEN.replace(hour=14), first_seen_at=OPEN.replace(hour=14, minute=5),
             signal_id=802, score=0.30, issuer_terms=["ASML", "ASML Holding"]),
    ]
    out = build_article_coverage(
        rows,
        universe=["ASML"],
        sector_by_ticker={"ASML": "semis"},
        session_open=OPEN,
        session_close=CLOSE,
    )

    fonti = out["per_ticker"]["ASML"]["fonti_osservate"]
    assert fonti["alpaca_benzinga"]["articoli_unici"] == 1
    assert fonti["alpaca_benzinga"]["articoli_effective_timely"] == 0
    assert fonti["gdelt_gkg"]["articoli_unici"] == 1
    assert fonti["gdelt_gkg"]["articoli_effective_timely"] == 1


def test_per_ticker_fonti_vuote_quando_il_provider_non_resa_righe():
    """#511 — il caso ``ASML fonti_osservate_finestra: []`` (10 sedute vuote)
    si manifesta a livello di singolo ticker come un dizionario vuoto. Va
    serializzato come tale, non come None e non come un fallback sul totale."""
    out = build_article_coverage(
        [],
        universe=["ASML"],
        sector_by_ticker={"ASML": "semis"},
        session_open=OPEN,
        session_close=CLOSE,
    )

    assert out["per_ticker"]["ASML"]["fonti_osservate"] == {}


def test_content_mill_e_retrospettivi_sono_misurati_senza_cambiare_lo_scoring():
    """#508 — il sotto-tag separa copertura da stato operativo.

    I due template osservati su GS/ORCL non sono copertura utile, mentre il
    segnale resta issuer-specific e continua a concorrere a max_score_own:
    escluderlo dallo scoring durante il freeze sarebbe un cambio di comportamento.
    """
    rows = [
        _row(
            61,
            "GS",
            "If You Invested $100 In Goldman Sachs Group Stock 15 Years Ago, "
            "You Would Have This Much Today",
            signal_id=701,
            score=0.002,
            issuer_terms=["Goldman Sachs", "GS"],
        ),
        _row(
            62,
            "ORCL",
            "$100 Invested In Oracle 20 Years Ago Would Be Worth This Much Today",
            signal_id=702,
            score=0.0,
            issuer_terms=["Oracle", "ORCL"],
        ),
        _row(
            63,
            "AAPL",
            "Apple raises guidance after stronger iPhone demand",
            signal_id=703,
            score=0.41,
            issuer_terms=["Apple", "AAPL"],
        ),
        _row(
            64,
            "MSFT",
            "Microsoft announces a new cloud region",
            published_at=CLOSE.replace(hour=21),
            signal_id=704,
            score=0.22,
            issuer_terms=["Microsoft", "MSFT"],
        ),
    ]

    out = build_article_coverage(
        rows,
        universe=["GS", "ORCL", "AAPL", "MSFT"],
        sector_by_ticker={
            "GS": "financials",
            "ORCL": "tech",
            "AAPL": "tech",
            "MSFT": "tech",
        },
        session_open=OPEN,
        session_close=CLOSE,
    )

    signals = {row["ticker"]: row for row in out["segnali"]}
    assert signals["GS"]["relevance"] == "ISSUER_SPECIFIC"
    assert signals["GS"]["attribution"] == "ISSUER_SPECIFIC"
    assert signals["GS"]["content_tag"] == "CONTENT_EMPTY"
    assert signals["GS"]["content_empty_reason"] == "EVERGREEN_RETURN_TEMPLATE"
    assert signals["ORCL"]["content_tag"] == "CONTENT_EMPTY"
    assert signals["MSFT"]["content_empty_reason"] == "RETROSPECTIVE_TIMING"
    assert signals["AAPL"]["content_tag"] is None

    # Freeze #171: il sotto-tag corregge la misura, non lo stato operativo.
    assert out["per_ticker"]["GS"]["max_score_own"] == 0.002
    assert out["per_ticker"]["ORCL"]["max_score_own"] == 0.0

    assert out["totali"]["mapping_rilevanza"]["ISSUER_SPECIFIC"] == 4
    assert out["totali"]["mapping_content_empty"] == 3
    assert out["totali"]["articoli_effective_timely"] == 1
    assert out["totali"]["articoli_effective_timely_including_content_empty"] == 3
    assert out["effective_timely_coverage"] == {
        "ticker_coperti": 1,
        "ticker_universo": 4,
        "quota": 0.25,
    }
    assert out["effective_timely_coverage_including_content_empty"] == {
        "ticker_coperti": 3,
        "ticker_universo": 4,
        "quota": 0.75,
    }


# ── #566 — bare-stem derivation & issuer_terms expansion ──────────────────
#
# L'articolo "Oracle set to report…" veniva classificato FALSE_ENTITY_MATCH
# perche' ``ticker_lookup`` conserva solo nomi legali suffissi
# ("Oracle Corporation", "Oracle Corp") e il matcher word-boundary non li
# riconosce. Stesso buco su AAPL "Apple Announces…", CMCSA "Comcast CFO Says…",
# F "Ford…". Il fix non rilassa il matcher: aggiunge il bare stem agli alias
# in modo deterministico, con una lista di suffissi nota e verificabile, e
# richiede una review umana caso-per-caso prima di scrivere nel DB live.


def test_derive_bare_stem_riconosce_i_suffissi_corporate_noti():
    """La lista di suffissi e' congelata e leggibile: aggiungere un suffisso
    e' una scelta di copertura, non un default. I suffissi sono elencati in
    ordine di greedy match."""
    assert derive_bare_stem("Oracle Corporation") == "oracle"
    assert derive_bare_stem("Oracle Corp") == "oracle"
    assert derive_bare_stem("Apple Inc") == "apple"
    assert derive_bare_stem("Comcast Corporation") == "comcast"
    assert derive_bare_stem("Ford Motor Company") == "ford motor"
    assert derive_bare_stem("Ford Motor Co") == "ford motor"
    assert derive_bare_stem("Berkshire Hathaway Inc") == "berkshire hathaway"
    assert derive_bare_stem("3M Co") == "3m"
    assert derive_bare_stem("NVIDIA Corporation") == "nvidia"
    # Connettivo "and" finale: "Eli Lilly and Company" -> "Eli Lilly"
    assert derive_bare_stem("Eli Lilly and Company") == "eli lilly"
    # "&" connettivo: "Merck & Co" -> "Merck"
    assert derive_bare_stem("Merck & Co") == "merck"


def test_derive_bare_stem_rifioca_i_nomi_ambigui_o_privi_di_suffisso():
    """Il matcher non indovina: lo stem di "General Electric Co" e' "General
    Electric", ma senza un check di collisione lessicale non va aggiunto in
    automatico. ``propose_stem_backfill`` segnala collisioni; qui la funzione
    pura restituisce lo stem e l'oracolo di review decide."""
    # Suffisso "AG" / "SE" / "N.V." / "PLC" coperti dalla lista
    assert derive_bare_stem("SAP SE") == "sap"
    assert derive_bare_stem("Deutsche Bank AG") == "deutsche bank"
    assert derive_bare_stem("AstraZeneca plc") == "astrazeneca"
    # Review codex su PR #635 (2026-09-20): la lista normalizza solo case e
    # spazi (`_normalise_text`), non i punti — "N.V." e "S.A." dotati vanno
    # elencati per esteso, "NV"/"SA" senza punti non li matchano. "AB" e "AS"
    # (o "A/S") sono i suffissi nordici del caso reale in ticker_lookup: NVO
    # "Novo Nordisk AS" restava `noop/no_suffix_detected` prima di questo fix.
    assert derive_bare_stem("Acme N.V.") == "acme"
    assert derive_bare_stem("Acme S.A.") == "acme"
    assert derive_bare_stem("Ericsson AB") == "ericsson"
    assert derive_bare_stem("Novo Nordisk AS") == "novo nordisk"
    assert derive_bare_stem("Novo Nordisk A/S") == "novo nordisk"
    # Nome senza suffisso corporate riconoscibile: nessuno stem da derivare
    # (la funzione restituisce None, non il nome intatto: e' un segnale che
    # il backfill non aggiunge nulla).
    assert derive_bare_stem("Morgan Stanley") is None
    # Stringa vuota o solo suffisso: nessuno stem da aggiungere
    assert derive_bare_stem("") is None
    assert derive_bare_stem("   ") is None


def test_expand_aliases_aggiunge_lo_stem_solo_se_nuovo_e_non_vuoto():
    """Il backfill e' idempotente e non duplica: stem gia' presente o identico
    al company_name non viene aggiunto. Il case e' casefolded perche' la
    normalizzazione e' condivisa con il resto del modulo."""
    expanded = expand_aliases_with_stem(
        "Oracle Corporation", ["Oracle Corp"]
    )
    assert expanded == ["Oracle Corp", "oracle"]

    # Stem uguale al company_name gia' presente: niente duplicato
    expanded = expand_aliases_with_stem("Oracle Corporation", ["Oracle"])
    assert expanded == ["Oracle"]

    # Stem assente e uguale a un alias esistente: niente duplicato
    expanded = expand_aliases_with_stem("Oracle Corporation", ["Oracle Corp", "Oracle"])
    assert expanded == ["Oracle Corp", "Oracle"]

    # Stem nullo (nome senza suffisso riconoscibile): invariata
    expanded = expand_aliases_with_stem("Morgan Stanley", [])
    assert expanded == []


def test_propose_stem_backfill_classifica_le_righe_in_quattro_bucketti():
    """L'output e' la proposta di review: short / generic / collision / safe.
    Solo "safe" e' pronto per l'applicazione automatica; gli altri vanno
    revisionati a mano."""
    rows = [
        # Safe: stem >= 3 caratteri, non collidente, ticker lungo
        {"ticker": "ORCL", "company_name": "Oracle Corporation", "aliases": ["Oracle Corp"]},
        # Collision: "apple" e' anche un frutto. La issue lo elenca
        # esplicitamente come da NON aggiungere (riapre i falsi positivi
        # di #405). Lo segnaliamo, l'operatore decide a mano.
        {"ticker": "AAPL", "company_name": "Apple Inc", "aliases": ["Apple Computer"]},
        # Short: ticker da 1-2 caratteri (F) — lo stem di per se' sarebbe
        # applicabile, ma il ticker corto segnala che serve una review.
        {"ticker": "F", "company_name": "Ford Motor Company", "aliases": ["Ford Motor Co"]},
        # Noop: "Morgan Stanley" non ha suffisso corporate riconoscibile,
        # niente da strippare.
        {"ticker": "MS", "company_name": "Morgan Stanley", "aliases": []},
        # Noop: stem identico a un alias esistente (Microsoft == Microsoft).
        {"ticker": "MSFT", "company_name": "Microsoft Corporation", "aliases": ["Microsoft"]},
        # "And" e' connettivo: "Eli Lilly and Company" -> "Eli Lilly" dopo
        # strip di "Company", ma il connettivo "And" non va lasciato nello
        # stem perche' collide col connettivo inglese.
        {"ticker": "LLY", "company_name": "Eli Lilly and Company", "aliases": ["Eli Lilly", "Lilly"]},
    ]
    proposal = propose_stem_backfill(rows)
    by_ticker = {row["ticker"]: row for row in proposal}
    assert by_ticker["ORCL"]["bucket"] == "safe"
    assert by_ticker["ORCL"]["proposed_alias"] == "oracle"
    assert by_ticker["AAPL"]["bucket"] == "collision"
    assert by_ticker["AAPL"]["proposed_alias"] == "apple"
    assert by_ticker["F"]["bucket"] == "short"
    assert by_ticker["F"]["proposed_alias"] == "ford motor"
    assert by_ticker["MS"]["bucket"] == "noop"
    assert by_ticker["MS"]["proposed_alias"] is None
    assert by_ticker["MSFT"]["bucket"] == "noop"
    assert by_ticker["MSFT"]["proposed_alias"] is None
    # LLY: "Eli Lilly" e' gia' negli alias, niente da aggiungere (noop)
    assert by_ticker["LLY"]["bucket"] == "noop"
    assert by_ticker["LLY"]["proposed_alias"] is None


def test_alias_con_bare_stem_riconosce_il_nome_comune_nel_titolo():
    """#566 — test pinning del fix: prova il COLLEGAMENTO tra la funzione
    di backfill ``expand_aliases_with_stem`` e il classifier.

    Lo stato pre-fix usa gli alias come sono in produzione (solo nomi
    legali suffissi); lo stato post-fix deriva gli stessi alias dalla
    funzione ``expand_aliases_with_stem`` applicata a quegli alias di
    partenza, cosi' la riga del test cambia se e solo se la funzione
    cambia. Rimuovere o rompere ``expand_aliases_with_stem`` (o rimuovere
    il suo import) fa fallire il test per la ragione giusta.
    """
    titolo = "Oracle set to report as Street weighs capex risk against cloud growth"
    company_name = "Oracle Corporation"
    base_aliases = ["Oracle Corp"]
    # Stato pre-fix: gli alias non contengono lo stem (stato di produzione
    # attuale). Costruiamo manualmente issuer_terms per descrivere il caso.
    pre_terms = [*base_aliases, company_name, "ORCL"]
    pre = _row(
        901, "ORCL", titolo, content_hash="x" * 64,
        source="gdelt_gkg", extraction_method="org_lookup",
        signal_id=901, score=-0.04,
        issuer_terms=pre_terms,
    )
    out_pre = build_article_coverage(
        [pre], universe=["ORCL"], sector_by_ticker={"ORCL": "tech"},
        session_open=OPEN, session_close=CLOSE,
    )
    assert out_pre["totali"]["mapping_rilevanza"]["FALSE_ENTITY_MATCH"] == 1
    assert out_pre["per_ticker"]["ORCL"]["max_score_own"] is None

    # Stato post-fix: lo stem "oracle" viene aggiunto agli alias dalla
    # funzione stessa di backfill. Il test si appoggia esclusivamente a
    # ``expand_aliases_with_stem``: se la funzione sparisse o smettesse di
    # produrre lo stem "oracle", il post-fix crollerebbe in FALSE_ENTITY_MATCH
    # e il test fallirebbe. Il test quindi VINCOLA sia la funzione sia il
    # suo effetto sul classifier.
    post_aliases = expand_aliases_with_stem(company_name, base_aliases)
    post_aliases_lower = {a.casefold() for a in post_aliases}
    assert "oracle" in post_aliases_lower, (
        "expand_aliases_with_stem deve aggiungere 'oracle' (stem di "
        "'Oracle Corporation') agli alias per far passare il test pinning"
    )
    post_terms = [*post_aliases, "ORCL"]
    post = _row(
        902, "ORCL", titolo, content_hash="y" * 64,
        source="gdelt_gkg", extraction_method="org_lookup",
        signal_id=902, score=-0.04,
        issuer_terms=post_terms,
    )
    out_post = build_article_coverage(
        [post], universe=["ORCL"], sector_by_ticker={"ORCL": "tech"},
        session_open=OPEN, session_close=CLOSE,
    )
    assert out_post["totali"]["mapping_rilevanza"]["ISSUER_SPECIFIC"] == 1
    assert out_post["totali"]["mapping_rilevanza"]["FALSE_ENTITY_MATCH"] == 0
    assert out_post["per_ticker"]["ORCL"]["max_score_own"] == -0.04
