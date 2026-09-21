"""#637 — classificazione additiva al momento dello scoring."""

from datetime import date, datetime, time, timezone

from src.models.news import NewsItem
from src.models.signals import SentimentResult
from src.workers.article_signal_coverage import (
    MarketSession,
    build_signal_coverage,
)
from src.workers.sentiment import LiveSignalSink


UTC = timezone.utc


def test_after_close_anchors_timing_to_the_next_actionable_session():
    item = NewsItem(
        id="orcl-1",
        title="Oracle raises cloud guidance",
        body="Oracle Corporation raises cloud guidance.",
        asset_tags=["ORCL", "MSFT"],
        timestamp=datetime(2026, 9, 18, 20, 1, tzinfo=UTC),
    )
    result = SentimentResult(
        symbol="ORCL", score=0.42, confidence=0.8, reasoning="", model_id="test"
    )
    sessions = [
        MarketSession(
            date=date(2026, 9, 18),
            open_at=datetime(2026, 9, 18, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 9, 18, 20, 0, tzinfo=UTC),
        ),
        MarketSession(
            date=date(2026, 9, 21),
            open_at=datetime(2026, 9, 21, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 9, 21, 20, 0, tzinfo=UTC),
        ),
    ]

    coverage = build_signal_coverage(
        item=item,
        result=result,
        issuer_terms=["Oracle Corporation", "Oracle"],
        sessions=sessions,
    )

    assert coverage["session_anchor"] == date(2026, 9, 21)
    assert coverage["timing_category"] == "ANTICIPATORY"
    assert coverage["relevance"] == "ISSUER_SPECIFIC"
    assert coverage["attribution"] == "ISSUER_SPECIFIC"
    assert coverage["subject_ticker"] == "ORCL"
    assert coverage["fanout_degree"] == 2
    assert coverage["score_own"] == 0.42
    assert coverage["score_fanout"] is None
    assert coverage["input_scope"] == "full_article"


def test_unavailable_calendar_persists_unknown_instead_of_inventing_anchor():
    item = NewsItem(id="x", title="Macro update", body="Macro update")
    result = SentimentResult(
        symbol="SPY", score=0.1, confidence=0.5, reasoning="", model_id="test"
    )

    coverage = build_signal_coverage(
        item=item, result=result, issuer_terms=[], sessions=[]
    )

    assert coverage["session_anchor"] is None
    assert coverage["timing_category"] == "UNKNOWN"
    assert coverage["novelty_proxy"] is None


async def test_live_sink_records_coverage_without_changing_signal_destination(monkeypatch):
    """La classificazione e' una seconda scrittura, mai un gate o un filtro."""
    from unittest.mock import AsyncMock, MagicMock

    pg = MagicMock()
    pg.find_signal_id_for_news.return_value = None
    pg.write_signal.return_value = 17
    pg.log_news_item.return_value = 9
    redis = MagicMock()
    item = NewsItem(
        id="orcl-1", title="Oracle raises guidance", body="Oracle guidance",
        asset_tags=["ORCL"], url="https://example.test/orcl",
    )
    result = SentimentResult(
        symbol="ORCL", score=0.42, confidence=0.8, reasoning="", model_id="test"
    )
    monkeypatch.setattr(
        "src.workers.sentiment.load_actionable_sessions", lambda _published: []
    )
    monkeypatch.setattr(
        "src.workers.sentiment.build_signal_coverage",
        lambda **_kwargs: {
            "symbol": "ORCL", "canonical_article_id": "title:x",
            "timing_category": "UNKNOWN", "session_anchor": None,
            "relevance": "UNKNOWN", "attribution": "UNKNOWN",
            "content_empty_reason": None, "fanout_degree": 1,
            "score_own": None, "score_fanout": None,
            "novelty_proxy": None, "input_scope": "full_article",
        },
    )
    monkeypatch.setattr(pg, "fetch_issuer_terms", lambda _symbol: [])

    await LiveSignalSink(redis, pg).persist(item, result, [], shadow_tasks=[])

    pg.write_article_signal_coverage.assert_called_once()
    redis.write_sentiment.assert_called_once_with(result, signal_id=17)
