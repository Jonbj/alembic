"""Tests for FinBERT fallback with entropic confidence mapping."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.llm.finbert import FinBERTClient, FinBERTResult, entropic_confidence
from src.models.news import NewsItem


def _make_article(title: str, ts: datetime | None = None) -> NewsItem:
    ts = ts or datetime.now(timezone.utc)
    return NewsItem(id="test", source="gdelt", timestamp=ts, title=title, body=title)


class TestEntropicConfidence:
    """Tests for the entropic_confidence function."""

    def test_uniform_distribution_low_confidence(self):
        """Uniform distribution [1/3, 1/3, 1/3] should yield low confidence (~0)."""
        probs = [1 / 3, 1 / 3, 1 / 3]
        conf = entropic_confidence(probs)
        # Max entropy for 3 classes = log2(3) ≈ 1.585
        # Normalized entropy = 1.0, so confidence = 1 - 1.0 = 0.0
        assert conf < 0.01  # Should be very close to 0

    def test_peaked_distribution_high_confidence(self):
        """Peaked distribution should yield high confidence."""
        probs = [0.95, 0.03, 0.02]
        conf = entropic_confidence(probs)
        assert conf > 0.7

    def test_deterministic_one_class(self):
        """Single class with probability 1.0 should yield confidence 1.0."""
        probs = [1.0, 0.0, 0.0]
        conf = entropic_confidence(probs)
        assert conf == pytest.approx(1.0, abs=0.01)

    def test_bounds(self):
        """Confidence should always be in [0, 1] range."""
        test_cases = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1 / 3, 1 / 3, 1 / 3],
            [0.5, 0.3, 0.2],
            [0.8, 0.1, 0.1],
        ]
        for probs in test_cases:
            conf = entropic_confidence(probs)
            assert 0.0 <= conf <= 1.0

    def test_empty_list(self):
        """Empty list should return 0.0 confidence."""
        conf = entropic_confidence([])
        assert conf == 0.0


class TestFinBERTClient:
    """Tests for the FinBERTClient class."""

    def _make_mock_pipeline(self, scores):
        """Helper to create a mock pipeline that returns the given scores."""
        mock_pipeline = MagicMock(return_value=[scores])
        return mock_pipeline

    def test_positive_maps_to_positive_polarity(self):
        """Positive sentiment should map to positive polarity."""
        mock_pipe = self._make_mock_pipeline(
            [
                {"label": "positive", "score": 0.85},
                {"label": "neutral", "score": 0.10},
                {"label": "negative", "score": 0.05},
            ]
        )

        # Mock _get_pipeline to return our mock
        with patch.object(FinBERTClient, "_get_pipeline", return_value=mock_pipe):
            client = FinBERTClient()
            result = client.analyze("Apple beats earnings estimates.")

        # polarity = (0.85 - 0.05) * (1 - 0.10) = 0.80 * 0.90 = 0.72
        assert result.polarity > 0
        assert result.confidence > 0.5
        assert result.worker_type == "finbert"

    def test_negative_maps_to_negative_polarity(self):
        """Negative sentiment should map to negative polarity."""
        mock_pipe = self._make_mock_pipeline(
            [
                {"label": "negative", "score": 0.88},
                {"label": "neutral", "score": 0.09},
                {"label": "positive", "score": 0.03},
            ]
        )

        with patch.object(FinBERTClient, "_get_pipeline", return_value=mock_pipe):
            client = FinBERTClient()
            result = client.analyze("Mass layoffs announced.")

        # polarity = (0.03 - 0.88) * (1 - 0.09) = -0.85 * 0.91 = -0.77
        assert result.polarity < 0
        assert result.confidence > 0.5

    def test_neutral_dampening_effect(self):
        """High neutral score should dampen polarity magnitude."""
        mock_high_neutral = self._make_mock_pipeline(
            [
                {"label": "positive", "score": 0.50},
                {"label": "neutral", "score": 0.40},
                {"label": "negative", "score": 0.10},
            ]
        )

        mock_low_neutral = self._make_mock_pipeline(
            [
                {"label": "positive", "score": 0.50},
                {"label": "neutral", "score": 0.05},
                {"label": "negative", "score": 0.10},
            ]
        )

        with patch.object(FinBERTClient, "_get_pipeline", return_value=mock_high_neutral):
            client_high = FinBERTClient()
            result_high = client_high.analyze("text")

        with patch.object(FinBERTClient, "_get_pipeline", return_value=mock_low_neutral):
            client_low = FinBERTClient()
            result_low = client_low.analyze("text")

        # polarity = (0.50 - 0.10) * (1 - neutral)
        # high: 0.40 * 0.60 = 0.24
        # low: 0.40 * 0.95 = 0.38
        assert result_high.polarity < result_low.polarity

    def test_polarity_bounds(self):
        """Polarity should always be in [-1, +1] range."""
        mock_pipe = self._make_mock_pipeline(
            [
                {"label": "positive", "score": 0.99},
                {"label": "neutral", "score": 0.005},
                {"label": "negative", "score": 0.005},
            ]
        )

        with patch.object(FinBERTClient, "_get_pipeline", return_value=mock_pipe):
            client = FinBERTClient()
            result = client.analyze("extremely positive text")

        assert -1.0 <= result.polarity <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_lazy_loading(self):
        """Pipeline should be lazy-loaded on first use (not at construction)."""
        client = FinBERTClient()
        # At construction, _pipe should be None (not loaded yet)
        # This verifies lazy loading: the expensive transformers import
        # doesn't happen until analyze() is first called
        assert client._pipe is None

    def test_result_type(self):
        """Result should be FinBERTResult dataclass."""
        mock_pipe = self._make_mock_pipeline(
            [
                {"label": "positive", "score": 0.60},
                {"label": "neutral", "score": 0.25},
                {"label": "negative", "score": 0.15},
            ]
        )

        with patch.object(FinBERTClient, "_get_pipeline", return_value=mock_pipe):
            client = FinBERTClient()
            result = client.analyze("test")

        assert isinstance(result, FinBERTResult)
        assert hasattr(result, "polarity")
        assert hasattr(result, "confidence")
        assert hasattr(result, "worker_type")
        assert result.worker_type == "finbert"


class TestFinBERTClientScoreArticles:
    """Tests for the batch score_articles method."""

    def test_score_formula_polarity_times_confidence(self):
        articles = [_make_article("Earnings beat")]
        client = FinBERTClient()
        with patch.object(client, "analyze", return_value=FinBERTResult(polarity=0.6, confidence=0.8)):
            results = client.score_articles(articles, min_confidence=0.0)
        assert len(results) == 1
        _, score = results[0]
        assert score == pytest.approx(0.6 * 0.8)

    def test_returns_article_date(self):
        ts = datetime(2025, 11, 15, tzinfo=timezone.utc)
        articles = [_make_article("Test", ts=ts)]
        client = FinBERTClient()
        with patch.object(client, "analyze", return_value=FinBERTResult(polarity=0.4, confidence=0.7)):
            results = client.score_articles(articles, min_confidence=0.0)
        assert results[0][0] == ts.date()

    def test_filters_below_min_confidence(self):
        articles = [_make_article("High conf"), _make_article("Low conf")]
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
        client = FinBERTClient()
        assert client.score_articles([], min_confidence=0.3) == []

    def test_skips_article_with_no_text(self):
        article = NewsItem(id="x", source="gdelt", timestamp=datetime.now(timezone.utc), body="", title="")
        client = FinBERTClient()
        with patch.object(client, "analyze") as mock_analyze:
            results = client.score_articles([article], min_confidence=0.0)
        mock_analyze.assert_not_called()
        assert results == []

    def test_exception_in_analyze_skips_article_and_continues(self):
        articles = [_make_article("Good article"), _make_article("Bad article")]
        client = FinBERTClient()

        def mock_analyze(text):
            if "Bad" in text:
                raise RuntimeError("model error")
            return FinBERTResult(polarity=0.5, confidence=0.9)

        with patch.object(client, "analyze", side_effect=mock_analyze):
            results = client.score_articles(articles, min_confidence=0.0)
        assert len(results) == 1
        assert results[0][1] == pytest.approx(0.5 * 0.9)
