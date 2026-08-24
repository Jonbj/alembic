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
        "body_snippet": title,
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


def test_dati_non_sufficienti_restano_unknown_invece_di_essere_indovinati():
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
    assert out["totali"]["mapping_rilevanza"]["UNKNOWN"] == 1
    assert out["segnali"][0]["relevance"] == "UNKNOWN"
    assert out["segnali"][0]["timing"] == "UNKNOWN"
    assert out["effective_timely_coverage"]["quota"] == 0.0
