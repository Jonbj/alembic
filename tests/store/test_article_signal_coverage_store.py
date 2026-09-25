"""#637 — scrittura della serie osservazionale separata."""

from datetime import date
from unittest.mock import MagicMock, patch

from src.store.pg_store import PostgreSQLStore


def test_classification_write_uses_only_the_new_table():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(False,), None]
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    coverage = {
        "symbol": "ORCL",
        "canonical_article_id": "title:abc",
        "timing_category": "ANTICIPATORY",
        "session_anchor": date(2026, 9, 21),
        "relevance": "ISSUER_SPECIFIC",
        "attribution": "ISSUER_SPECIFIC",
        "content_empty_reason": None,
        "fanout_degree": 1,
        "score_own": 0.42,
        "score_fanout": None,
        "novelty_proxy": True,
        "input_scope": "full_article",
    }

    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.write_article_signal_coverage(
            signal_id=17, news_log_id=9, coverage=coverage
        )

    sql = "\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
    assert "article_signal_coverage" in sql
    assert "INSERT INTO sentiment_signals" not in sql
    assert "INSERT INTO news_log" not in sql
    conn.commit.assert_called_once()
