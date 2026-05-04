"""Tests for FinBERT scoring — all external calls mocked."""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.models.news import NewsItem
from src.analysis.finbert import score_article, score_articles


def make_article(title: str, ts: datetime | None = None) -> NewsItem:
    ts = ts or datetime.now(timezone.utc)
    return NewsItem(id="test", source="gdelt", timestamp=ts, title=title, body=title)


class TestScoreArticle:
    def test_positive_article(self):
        mock_pipe = lambda text: [[
            {"label": "positive", "score": 0.80},
            {"label": "negative", "score": 0.05},
            {"label": "neutral",  "score": 0.15},
        ]]
        with patch("src.analysis.finbert._get_pipeline", return_value=mock_pipe):
            polarity, confidence = score_article("Earnings beat")
        assert abs(polarity - 0.75) < 1e-6    # 0.80 - 0.05
        assert abs(confidence - 0.85) < 1e-6  # 0.80 + 0.05

    def test_negative_article(self):
        mock_pipe = lambda text: [[
            {"label": "positive", "score": 0.05},
            {"label": "negative", "score": 0.85},
            {"label": "neutral",  "score": 0.10},
        ]]
        with patch("src.analysis.finbert._get_pipeline", return_value=mock_pipe):
            polarity, confidence = score_article("Bankruptcy filing")
        assert polarity < 0
        assert confidence > 0.8

    def test_neutral_article_low_confidence(self):
        mock_pipe = lambda text: [[
            {"label": "positive", "score": 0.05},
            {"label": "negative", "score": 0.05},
            {"label": "neutral",  "score": 0.90},
        ]]
        with patch("src.analysis.finbert._get_pipeline", return_value=mock_pipe):
            polarity, confidence = score_article("Annual meeting scheduled")
        assert abs(polarity) < 0.01
        assert confidence < 0.15


class TestScoreArticles:
    def test_score_formula_polarity_times_confidence(self):
        articles = [make_article("Test")]
        with patch("src.analysis.finbert.score_article", return_value=(0.6, 0.8)):
            results = score_articles(articles, min_confidence=0.0)
        assert len(results) == 1
        _, score = results[0]
        assert score == pytest.approx(0.6 * 0.8)

    def test_filters_below_min_confidence(self):
        articles = [make_article("High conf"), make_article("Low conf")]

        def mock_score(text):
            return (0.75, 0.85) if "High" in text else (0.0, 0.10)

        with patch("src.analysis.finbert.score_article", side_effect=mock_score):
            results = score_articles(articles, min_confidence=0.3)
        assert len(results) == 1
        assert results[0][1] == pytest.approx(0.75 * 0.85)

    def test_empty_list_returns_empty(self):
        assert score_articles([], min_confidence=0.3) == []

    def test_skips_article_with_no_text(self):
        article = NewsItem(id="x", source="gdelt", body="", title="")
        with patch("src.analysis.finbert.score_article") as mock_score:
            results = score_articles([article], min_confidence=0.0)
        mock_score.assert_not_called()
        assert results == []
