"""Tests for PostgreSQL store - news_log and llm_responses write methods."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.store.pg_store import PostgreSQLStore
from src.models.news import NewsItem, MarketAuxNewsItem
from src.llm.ensemble import ModelOutput


@pytest.fixture
def pg_store():
    """Create a PostgreSQLStore with mocked connection."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    return PostgreSQLStore(conn=mock_conn, use_pool=False)


@pytest.fixture
def sample_news_item():
    """Create a sample NewsItem for testing."""
    return NewsItem(
        id="https://example.com/article:AAPL",
        body="Apple quarterly results beat expectations significantly.",
        title="Apple beats Q3 estimates",
        source="gdelt_gkg",
        url="https://example.com/article",
        asset_tags=["AAPL"],
        timestamp=datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_marketaux_news_item():
    """Create a sample MarketAuxNewsItem with raw_sentiment."""
    return MarketAuxNewsItem(
        id="https://example.com/article:AAPL",
        body="Apple quarterly results beat expectations significantly.",
        title="Apple beats Q3 estimates",
        source="marketaux",
        url="https://example.com/article",
        asset_tags=["AAPL"],
        timestamp=datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc),
        marketaux_sentiment=0.65,
    )


class TestLogNewsItem:
    """Test PostgreSQLStore.log_news_item()."""

    def test_log_news_item_inserts_row(self, pg_store, sample_news_item):
        """log_news_item inserts one row into news_log."""
        pg_store.log_news_item(item=sample_news_item, ticker="AAPL")

        mock_conn = pg_store._conn
        mock_cursor = mock_conn.cursor.return_value

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]

        assert "INSERT INTO news_log" in call_args[0]
        params = call_args[1]
        assert params[0] == "Apple beats Q3 estimates"
        assert params[1] == "https://example.com/article"
        assert params[2] == "gdelt_gkg"
        assert params[3] == "AAPL"
        mock_conn.commit.assert_called_once()

    def test_log_news_item_truncates_long_fields(self, pg_store, sample_news_item):
        """log_news_item truncates title and url to max length."""
        long_title = "A" * 600
        long_url = "https://example.com/" + "B" * 1100
        item = NewsItem(
            id="test",
            body="test",
            title=long_title,
            source="test",
            url=long_url,
            asset_tags=["AAPL"],
            timestamp=datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc),
        )

        pg_store.log_news_item(item=item, ticker="AAPL")

        mock_cursor = pg_store._conn.cursor.return_value
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert len(params[0]) == 500
        assert len(params[1]) == 1000

    def test_log_news_item_handles_marketaux_sentiment(self, pg_store, sample_marketaux_news_item):
        """log_news_item extracts raw_sentiment from MarketAuxNewsItem."""
        pg_store.log_news_item(item=sample_marketaux_news_item, ticker="AAPL")

        mock_cursor = pg_store._conn.cursor.return_value
        call_args = mock_cursor.execute.call_args[0]
        params = call_args[1]
        assert params[5] == 0.65  # raw_sentiment

    def test_log_news_item_rollback_on_error(self, pg_store, sample_news_item):
        """log_news_item rolls back on exception."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.execute.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            pg_store.log_news_item(item=sample_news_item, ticker="AAPL")

        pg_store._conn.rollback.assert_called_once()


class TestLogLlmResponses:
    """Test PostgreSQLStore.log_llm_responses()."""

    def test_log_llm_responses_inserts_rows(self, pg_store):
        """log_llm_responses inserts one row per ModelOutput."""
        outputs = [
            ModelOutput(
                symbol="AAPL",
                polarity=0.7,
                confidence=0.85,
                reasoning="Positive earnings.",
                model_id="opus",
            ),
            ModelOutput(
                symbol="AAPL",
                polarity=0.6,
                confidence=0.80,
                reasoning="Beat estimates.",
                model_id="qwen3.5:cloud",
            ),
        ]

        pg_store.log_llm_responses(signal_id=42, outputs=outputs)

        mock_cursor = pg_store._conn.cursor.return_value
        # Implementation uses executemany for batch insert — one call, two rows.
        assert mock_cursor.executemany.call_count == 1
        _, batch = mock_cursor.executemany.call_args[0]
        batch = list(batch)
        assert len(batch) == 2
        assert batch[0][0] == 42        # signal_id
        assert batch[0][1] == "opus"
        assert batch[1][1] == "qwen3.5:cloud"

    def test_log_llm_responses_eligible_reflects_confidence(self, pg_store):
        """QS-06: eligible = (confidence >= min_confidence), not hardcoded True."""
        outputs = [
            ModelOutput(symbol="AAPL", polarity=0.7, confidence=0.85,
                        reasoning="strong", model_id="kimi"),      # eligible
            ModelOutput(symbol="AAPL", polarity=-0.2, confidence=0.30,
                        reasoning="weak", model_id="weak"),        # discarded (<0.4)
        ]
        pg_store.log_llm_responses(signal_id=42, outputs=outputs, min_confidence=0.4)

        _, batch = pg_store._conn.cursor.return_value.executemany.call_args[0]
        batch = list(batch)
        assert batch[0][11] is True    # eligible column, 0.85 >= 0.4
        assert batch[1][11] is False   # 0.30 < 0.4 → NOT eligible (was hardcoded True)

    def test_log_llm_responses_force_ineligible_overrides_confidence(self, pg_store):
        """Divergence-fallback outputs are audit-only: eligible must be False even
        for high-confidence outputs, because they did NOT enter the signal."""
        outputs = [
            ModelOutput(symbol="AAPL", polarity=0.8, confidence=0.95,
                        reasoning="confident bull", model_id="glm-5.2:cloud"),
            ModelOutput(symbol="AAPL", polarity=-0.7, confidence=0.90,
                        reasoning="confident bear", model_id="kimi-k2.6:cloud"),
        ]
        pg_store.log_llm_responses(signal_id=7, outputs=outputs, force_ineligible=True)

        _, batch = pg_store._conn.cursor.return_value.executemany.call_args[0]
        batch = list(batch)
        assert batch[0][11] is False
        assert batch[1][11] is False

    def test_log_llm_responses_persists_relevance_evidence(self, pg_store):
        output = ModelOutput(
            symbol="F",
            polarity=-0.6,
            confidence=0.8,
            reasoning="Tariffs hurt this issuer directly.",
            model_id="glm-5.2:cloud",
            event_type="regulatory",
            directness="direct",
            materiality=0.7,
            novelty=0.4,
            risk_flags=["already_priced_in"],
            evidence_sentences=["The tariff applies to Ford imports."],
        )

        pg_store.log_llm_responses(signal_id=42, outputs=[output])

        sql, batch = pg_store._conn.cursor.return_value.executemany.call_args[0]
        assert "event_type" in sql
        assert "directness" in sql
        assert "materiality" in sql
        assert "novelty" in sql
        assert "risk_flags" in sql
        assert "evidence_sentences" in sql
        params = list(batch)[0]
        assert params[5:11] == (
            "regulatory",
            "direct",
            0.7,
            0.4,
            ["already_priced_in"],
            ["The tariff applies to Ford imports."],
        )

    def test_log_llm_responses_empty_list_is_noop(self, pg_store):
        """log_llm_responses with empty list writes nothing and does not raise."""
        pg_store.log_llm_responses(signal_id=42, outputs=[])

        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.execute.assert_not_called()
        pg_store._conn.commit.assert_not_called()

    def test_log_llm_responses_rollback_on_error(self, pg_store):
        """log_llm_responses rolls back on exception."""
        outputs = [
            ModelOutput(
                symbol="AAPL",
                polarity=0.7,
                confidence=0.85,
                reasoning="Positive.",
                model_id="opus",
            )
        ]

        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.executemany.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            pg_store.log_llm_responses(signal_id=42, outputs=outputs)

        pg_store._conn.rollback.assert_called_once()


class TestGetNewsRecent:
    """Test PostgreSQLStore.get_news_recent()."""

    def test_get_news_recent_returns_rows(self, pg_store):
        """get_news_recent returns a list of dicts with expected keys."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.description = [("id",), ("title",), ("url",), ("source",), ("ticker",), ("raw_sentiment",), ("fetched_at",)]
        mock_cursor.fetchall.return_value = [
            (1, "Apple beats Q3", "https://example.com", "gdelt_gkg", "AAPL", 0.65, datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc))
        ]

        rows = pg_store.get_news_recent(limit=10)

        assert len(rows) >= 1
        first = rows[0]
        assert "title" in first
        assert "ticker" in first
        assert "source" in first
        assert "fetched_at" in first

    def test_get_news_recent_filters_by_ticker(self, pg_store):
        """get_news_recent with ticker filter returns only matching rows."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.fetchall.return_value = []

        pg_store.get_news_recent(limit=10, ticker="MSFT")

        mock_cursor = pg_store._conn.cursor.return_value
        call_args = mock_cursor.execute.call_args[0]
        query = call_args[0]
        params = call_args[1]
        assert "ticker = %s" in query
        assert "MSFT" in params

    def test_get_news_recent_filters_by_source(self, pg_store):
        """get_news_recent with source filter returns only matching rows."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.fetchall.return_value = []

        pg_store.get_news_recent(limit=10, source="gdelt_gkg")

        mock_cursor = pg_store._conn.cursor.return_value
        call_args = mock_cursor.execute.call_args[0]
        query = call_args[0]
        params = call_args[1]
        assert "source = %s" in query
        assert "gdelt_gkg" in params


class TestGetNewsSourceQuality:
    """Test PostgreSQLStore.get_news_source_quality()."""

    def test_get_news_source_quality_returns_rows(self, pg_store):
        """get_news_source_quality returns per-source funnel rows."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.description = [
            ("source",), ("news_count",), ("with_ticker_count",), ("signals_count",),
            ("decisions_count",), ("orders_count",), ("avg_confidence",),
        ]
        mock_cursor.fetchall.return_value = [
            ("finnhub", 10, 10, 8, 3, 1, 0.72),
        ]

        rows = pg_store.get_news_source_quality(days=30)

        assert rows == [
            {
                "source": "finnhub",
                "news_count": 10,
                "with_ticker_count": 10,
                "signals_count": 8,
                "decisions_count": 3,
                "orders_count": 1,
                "avg_confidence": 0.72,
            }
        ]

    def test_get_news_source_quality_bounds_days(self, pg_store):
        """get_news_source_quality bounds the requested window."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.description = [("source",)]
        mock_cursor.fetchall.return_value = []

        pg_store.get_news_source_quality(days=999)

        params = mock_cursor.execute.call_args[0][1]
        assert params == (365,)


class TestGetLlmFeedback:
    """Test PostgreSQLStore.get_llm_feedback()."""

    def test_get_llm_feedback_returns_rows(self, pg_store):
        """get_llm_feedback returns rows with model_id and polarity."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.description = [
            ("id",), ("signal_id",), ("symbol",), ("model_id",), ("polarity",),
            ("confidence",), ("reasoning",), ("eligible",), ("generated_at",),
            ("fallback_used",), ("ensemble_std",)
        ]
        mock_cursor.fetchall.return_value = [
            (1, 42, "AAPL", "opus", 0.7, 0.85, "Good.", True, datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc), False, 0.1)
        ]

        rows = pg_store.get_llm_feedback(limit=10)

        assert len(rows) >= 1
        assert "model_id" in rows[0]
        assert "polarity" in rows[0]

    def test_get_llm_feedback_filters_by_ticker(self, pg_store):
        """get_llm_feedback with ticker filter returns only matching rows."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.fetchall.return_value = []

        pg_store.get_llm_feedback(limit=10, ticker="AAPL")

        mock_cursor = pg_store._conn.cursor.return_value
        call_args = mock_cursor.execute.call_args[0]
        query = call_args[0]
        params = call_args[1]
        assert "s.symbol = %s" in query
        assert "AAPL" in params

    def test_get_llm_feedback_filters_by_model(self, pg_store):
        """get_llm_feedback with model_id filter returns only matching rows."""
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.fetchall.return_value = []

        pg_store.get_llm_feedback(limit=10, model_id="opus")

        mock_cursor = pg_store._conn.cursor.return_value
        call_args = mock_cursor.execute.call_args[0]
        query = call_args[0]
        params = call_args[1]
        assert "r.model_id = %s" in query
        assert "opus" in params


class TestLogNewsItemNewsLogId:
    """QS-09: news_log_id must be populated even when the article already exists."""

    def test_returns_existing_id_on_conflict(self, pg_store):
        mock_cursor = pg_store._conn.cursor.return_value
        # INSERT ... ON CONFLICT DO NOTHING returns no row, then the fallback SELECT
        # returns the existing news_log id.
        mock_cursor.fetchone.side_effect = [None, (99,)]
        item = NewsItem(id="x", body="b", title="t", url="http://ex/a", asset_tags=["AAPL"])
        result = pg_store.log_news_item(item, ticker="AAPL")
        assert result == 99
        assert mock_cursor.execute.call_count == 2  # INSERT + fallback SELECT

    def test_returns_insert_id_without_conflict(self, pg_store):
        mock_cursor = pg_store._conn.cursor.return_value
        mock_cursor.fetchone.side_effect = [(42,)]
        item = NewsItem(id="x", body="b", title="t", url="http://ex/a", asset_tags=["AAPL"])
        result = pg_store.log_news_item(item, ticker="AAPL")
        assert result == 42
        assert mock_cursor.execute.call_count == 1  # only INSERT, no fallback SELECT
