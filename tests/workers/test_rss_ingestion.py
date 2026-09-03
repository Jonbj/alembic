"""Tests for RSS ingestion worker."""
import os
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.models.news import NewsItem


def _make_rss_item(title: str, body: str = "", ticker: str = "") -> NewsItem:
    return NewsItem(
        id=f"rss:{hash(title)}",
        source="reuters",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=body,
        url="https://reuters.com/article/foo",
        language="en",
        asset_tags=[ticker] if ticker else [],
    )


class TestExtractTickersFromText:
    def test_finds_ticker_in_title(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("AAPL shares rose 3% today", {"AAPL", "MSFT"})
        assert "AAPL" in result
        assert "MSFT" not in result

    def test_finds_multiple_tickers(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("AAPL and MSFT both up", {"AAPL", "MSFT", "GOOGL"})
        assert set(result) == {"AAPL", "MSFT"}

    def test_no_match_returns_empty(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("Federal Reserve raises rates", {"AAPL", "MSFT"})
        assert result == []

    def test_partial_word_not_matched(self):
        """'APPS' non deve matchare 'APP' nella watchlist."""
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("APPS rallied today", {"APP"})
        assert result == []

    # --- Ticker-resolution safety: false-positive guard (design doc §3/§11.1) ---

    def test_single_letter_ticker_not_matched_bare(self):
        """'F' in 'F-150 sales rose' must NOT signal Ford — needs a cashtag."""
        from src.workers.ingestion import _extract_tickers_from_text
        assert _extract_tickers_from_text("F-150 sales rose 4%", {"F"}) == []
        assert _extract_tickers_from_text("Vitamin C demand up", {"C"}) == []

    def test_two_letter_ticker_not_matched_bare(self):
        """'GS' bare in prose is too ambiguous — needs a cashtag."""
        from src.workers.ingestion import _extract_tickers_from_text
        assert _extract_tickers_from_text("GS reported strong Q3", {"GS"}) == []

    def test_common_word_ticker_not_matched_bare(self):
        """Word-tickers (CAT, ON, META) must not match as bare prose words."""
        from src.workers.ingestion import _extract_tickers_from_text
        assert _extract_tickers_from_text("CAT bonds surged", {"CAT"}) == []
        assert _extract_tickers_from_text("the ON switch flipped", {"ON"}) == []

    def test_cashtag_accepts_ambiguous_ticker(self):
        """An explicit cashtag is high-confidence and always accepted."""
        from src.workers.ingestion import _extract_tickers_from_text
        assert _extract_tickers_from_text("$F gained 2% today", {"F"}) == ["F"]
        assert _extract_tickers_from_text("$GS beat estimates", {"GS"}) == ["GS"]
        assert _extract_tickers_from_text("$CAT raised guidance", {"CAT"}) == ["CAT"]

    def test_cashtag_and_bare_unambiguous_both_work(self):
        """Normal >=3-char tickers still match bare; cashtags also work."""
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("AAPL rose, $MSFT fell", {"AAPL", "MSFT"})
        assert set(result) == {"AAPL", "MSFT"}


def test_rss_worker_queues_items_with_ticker_match():
    """Worker deve pushare solo articoli con almeno un ticker della watchlist."""
    items = [
        _make_rss_item("AAPL quarterly results beat estimates"),      # match
        _make_rss_item("Federal Reserve holds rates steady"),          # no match
        _make_rss_item("MSFT Azure revenue grows 30%"),                # match
    ]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: not under test here

    with patch("src.workers.ingestion.RSSConnector") as mock_rss_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.PostgreSQLStore") as mock_store_cls, \
         patch("src.workers.ingestion.config") as mock_cfg, \
         patch.dict(os.environ, {"RSS_INGESTION_ENABLED": "1"}):  # FIX-02: source is gated off by default

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_rss_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_rss_ingestion_worker
        result = run_rss_ingestion_worker()

    # AAPL article → 1 push; MSFT article → 1 push; Federal Reserve → filtered
    assert result["queued"] == 2
    assert result["filtered"] == 1
    assert mock_store_cls.call_count == 2


def test_rss_worker_expands_per_ticker():
    """Articolo con 2 ticker → 2 item separati in coda."""
    items = [_make_rss_item("AAPL and MSFT both surge on AI news")]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False
    mock_dedup.is_duplicate_content_symbol.return_value = False  # EN-03: not under test here

    with patch("src.workers.ingestion.RSSConnector") as mock_rss_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.PostgreSQLStore") as mock_store_cls, \
         patch("src.workers.ingestion.config") as mock_cfg, \
         patch.dict(os.environ, {"RSS_INGESTION_ENABLED": "1"}):  # FIX-02: source is gated off by default

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_rss_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_rss_ingestion_worker
        result = run_rss_ingestion_worker()

    assert result["queued"] == 2  # un item per AAPL, uno per MSFT
    assert mock_redis.rpush.call_count == 2
    assert mock_store_cls.call_count == 2


def test_ingestion_observability_accepts_an_injected_store_factory():
    """La persistenza e' testabile senza risolvere DATABASE_URL."""
    from src.workers.ingestion import _persist_ingestion_observability

    mock_store = MagicMock()
    mock_store_factory = MagicMock()
    mock_store_factory.return_value.__enter__.return_value = mock_store

    _persist_ingestion_observability(
        "reuters",
        {"fetched": 1, "queued": 1},
        [],
        store_factory=mock_store_factory,
    )

    mock_store_factory.assert_called_once_with()
    mock_store.record_ingestion_stats.assert_called_once_with(
        "reuters", {"fetched": 1, "queued": 1}
    )
    mock_store.record_news_discards.assert_called_once_with([])
