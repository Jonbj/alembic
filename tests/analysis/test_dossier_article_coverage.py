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
        "articoli_effective_timely": 2,
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
