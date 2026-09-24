"""Contratto della serie osservazionale #637."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "080_article_signal_coverage.sql"
)


def test_la_classificazione_vive_in_una_tabella_additiva():
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS article_signal_coverage" in sql
    for column in (
        "signal_id",
        "timing_category",
        "session_anchor",
        "relevance",
        "attribution",
        "subject_ticker",
        "content_empty_reason",
        "fanout_degree",
        "score_own",
        "score_fanout",
        "novelty_proxy",
        "input_scope",
    ):
        assert column in sql


def test_la_migrazione_non_tocca_i_ledger_esistenti_ne_il_money_path():
    sql = MIGRATION.read_text()

    for forbidden in (
        "ALTER TABLE news_log",
        "ALTER TABLE sentiment_signals",
        "UPDATE news_log",
        "UPDATE sentiment_signals",
        "execution_decisions",
        "trades",
        "signal_threshold",
    ):
        assert forbidden not in sql
