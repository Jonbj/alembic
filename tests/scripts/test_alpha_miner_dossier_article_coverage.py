"""#279 — wiring della copertura articolo-centrica nel dossier giornaliero."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import scripts.alpha_miner_dossier as dossier


UTC = timezone.utc


def test_query_copertura_unisce_news_e_segnali_e_legge_solo_label_adjudicate():
    db_row = [[
        "10", "101", "AAPL", "Apple raises guidance", "Apple raises guidance",
        "https://wire.example/apple", "wire", "2026-08-12 12:00:00+00",
        "2026-08-12 12:01:00+00", "a" * 64, "source_metadata", "0.42",
        "company_specific", "AAPL", "Apple\x1fApple Inc.\x1fAAPL",
    ]]
    columns = {"adjudicated", "news_log_id", "gt_relevance", "gt_tickers", "url"}
    with (
        patch.object(dossier, "_psql", return_value=db_row) as psql,
        patch.object(dossier, "_news_label_columns", return_value=columns),
    ):
        rows = dossier._article_coverage_rows(date(2026, 8, 12))

    query = psql.call_args.args[0]
    assert "FULL JOIN sentiment_signals" in query
    assert "nl.content_hash" in query
    assert "l.adjudicated" in query
    assert rows == [{
        "news_log_id": 10,
        "signal_id": 101,
        "ticker": "AAPL",
        "title": "Apple raises guidance",
        "body_snippet": "Apple raises guidance",
        "url": "https://wire.example/apple",
        "source": "wire",
        "published_at": datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        "first_seen_at": datetime(2026, 8, 12, 12, 1, tzinfo=UTC),
        "content_hash": "a" * 64,
        "extraction_method": "source_metadata",
        "score": 0.42,
        "ground_truth_relevance": "company_specific",
        "ground_truth_tickers": ["AAPL"],
        "issuer_terms": ["Apple", "Apple Inc.", "AAPL"],
    }]


def test_query_copertura_supporta_lo_schema_label_legacy_senza_adjudicated():
    """Il DB live puo' precedere migration 046: schema 029 ha una sola label/URL."""
    columns = {"gt_relevance", "gt_tickers", "url", "status", "label_date", "label_id"}
    with (
        patch.object(dossier, "_psql", return_value=[]) as psql,
        patch.object(dossier, "_news_label_columns", return_value=columns),
    ):
        assert dossier._article_coverage_rows(date(2026, 8, 12)) == []

    query = psql.call_args.args[0]
    assert "l.url = nl.url" in query
    assert "l.adjudicated" not in query


def test_dossier_espone_copertura_e_propaga_attribution_sul_candidato():
    daily = {
        "AAPL": {
            "open": 100.0, "high": 109.0, "low": 99.0, "close": 107.0,
            "close_prec": 100.0,
        }
    }
    coverage_rows = [{
        "news_log_id": 10,
        "signal_id": 101,
        "ticker": "AAPL",
        "title": "Apple raises guidance",
        "body_snippet": "Apple raises guidance",
        "url": "https://wire.example/apple",
        "source": "wire",
        "published_at": datetime(2026, 8, 12, 12, 0, tzinfo=UTC),
        "first_seen_at": datetime(2026, 8, 12, 12, 1, tzinfo=UTC),
        "content_hash": "a" * 64,
        "extraction_method": "source_metadata",
        "score": 0.20,
        "ground_truth_relevance": "company_specific",
        "ground_truth_tickers": ["AAPL"],
        "issuer_terms": ["Apple", "AAPL"],
    }]

    def fake_psql(query):
        if "FROM sentiment_signals ss LEFT JOIN news_log" in query:
            return [[
                "AAPL", "15:30", "0.20", "f", "source_metadata",
                "Apple raises guidance", "1", "101",
            ]]
        if "SELECT ticker, count(*) FROM news_log" in query:
            return [["AAPL", "1"]]
        return []

    cutoff = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)
    with (
        patch.object(dossier, "_psql", side_effect=fake_psql),
        patch.object(dossier, "_barre", return_value=daily),
        patch.object(dossier, "_article_coverage_rows", return_value=coverage_rows),
        patch.object(dossier, "_soglia_gate_s4", return_value=0.30),
        patch.object(dossier, "_timeline_eventi", return_value=[]),
        patch.object(dossier, "_barre_intraday", return_value=({}, cutoff)),
        patch.object(dossier, "_dettagli_ordini", return_value={}),
        patch.object(dossier, "_sector_by_ticker", return_value={"AAPL": "tech"}),
        patch("redis.Redis", MagicMock()),
    ):
        out = dossier.costruisci_dossier(date(2026, 8, 12), ["AAPL"])

    assert out["schema_version"] == "2.2"
    assert out["copertura_articoli"]["effective_timely_coverage"]["quota"] == 1.0
    signal = out["candidati_miss"][0]["segnali"][0]
    assert signal["canonical_article_id"] == f"content:{'a' * 64}"
    assert signal["source"] == "wire"
    assert signal["subject_ticker"] == "AAPL"
    assert signal["attribution"] == "ISSUER_SPECIFIC"
    assert signal["max_score_own"] == 0.20
    assert signal["max_score_fanout"] is None
