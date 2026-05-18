"""Tests for FinBERTClient.score_articles batch method."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.llm.finbert import FinBERTClient, FinBERTResult
from src.models.news import NewsItem


def make_article(title: str, ts: datetime | None = None) -> NewsItem:
    ts = ts or datetime.now(timezone.utc)
    return NewsItem(id="test", source="gdelt", timestamp=ts, title=title, body=title)


class TestScoreArticles:
    def test_score_formula_polarity_times_confidence(self):
        articles = [make_article("Test")]
        client = FinBERTClient()
        with patch.object(client, "analyze", return_value=FinBERTResult(polarity=0.6, confidence=0.8)):
            results = client.score_articles(articles, min_confidence=0.0)
        assert len(results) == 1
        _, score = results[0]
        assert score == pytest.approx(0.6 * 0.8)

    def test_filters_below_min_confidence(self):
        articles = [make_article("High conf"), make_article("Low conf")]
        client = FinBERTClient()

        def mock_analyze(text):
            if "High" in text:
                return FinBERTResult(polarity=0.75, confidence=0.85)
            return FinBERTResult(polarity=0.0, confidence=0.10)

        with patch.object(client, "analyze", side_effect=mock_analyze):
            results = client.score_articles(articles, min_confidence=0.3)
        assert len(results) == 1
        assert results[0][1] == pytest.approx(0.75 * 0.85)

    def test_empty_list_returns_empty(self):
        assert FinBERTClient().score_articles([], min_confidence=0.3) == []

    def test_skips_article_with_no_text(self):
        article = NewsItem(id="x", source="gdelt", timestamp=datetime.now(timezone.utc), body="", title="")
        client = FinBERTClient()
        with patch.object(client, "analyze") as mock_analyze:
            results = client.score_articles([article], min_confidence=0.0)
        mock_analyze.assert_not_called()
        assert results == []
