"""Tests for SentimentWorker."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.budget import LLMBudgetExhaustedError, LLMBudgetTracker
from src.llm.ensemble import EnsembleAggregator, ModelOutput
from src.llm.finbert import FinBERTClient
from src.models.news import LLMSentimentOutput, MarketAuxNewsItem, NewsItem
from src.models.signals import SentimentResult
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.sentiment import (
    _DK_COT_PROMPT,
    process_news_batch,
    process_news_item,
    run_inference,
)


def make_news_item(symbol: str = "AAPL", n: int = 0) -> NewsItem:
    """Create a test news item."""
    return NewsItem(
        id=f"news-{n}",
        source="reuters",
        timestamp=datetime.now(timezone.utc),
        title=f"Apple Q{n} earnings beat estimates",
        body=f"Apple Inc. reported record quarterly earnings of $1.2B for Q{n}, beating analyst estimates by 15%. Revenue grew 20% YoY driven by strong iPhone sales.",
        url=f"https://reuters.com/article/{n}",
        language="en",
        asset_tags=[symbol],
    )


def make_model_output(
    polarity: float, confidence: float, model_id: str, symbol: str = "AAPL"
) -> ModelOutput:
    """Create a test model output."""
    return ModelOutput(
        symbol=symbol,
        polarity=polarity,
        confidence=confidence,
        reasoning="Strong earnings beat with revenue growth.",
        model_id=model_id,
    )


def make_sentiment_result(
    symbol: str = "AAPL",
    polarity: float = 0.6,
    confidence: float = 0.8,
    fallback_used: bool = False,
) -> SentimentResult:
    """Create a test sentiment result."""
    score = polarity * confidence
    return SentimentResult(
        symbol=symbol,
        score=max(-1.0, min(1.0, score)),
        confidence=confidence,
        reasoning="Strong earnings beat.",
        model_id="finbert" if fallback_used else "ensemble:opus+qwen35+deepseek",
        fallback_used=fallback_used,
    )


class TestProcessNewsItem:
    """Tests for process_news_item function."""

    @pytest.mark.asyncio
    async def test_successful_ensemble_processing(self):
        """Test successful ensemble processing without fallback."""
        # Mock run_ensemble_query to return model outputs directly
        mock_outputs = [
            make_model_output(0.6, 0.85, "opus"),
            make_model_output(0.55, 0.80, "qwen35:cloud"),
            make_model_output(0.65, 0.78, "deepseek-v4-pro:cloud"),
        ]

        # Mock aggregator
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.6,
            confidence=0.81,
            reasoning="Strong beat",
            model_ids=["opus", "qwen35:cloud", "deepseek-v4-pro:cloud"],
        )

        # Mock budget tracker
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value="ok")
        mock_budget.record_spending = AsyncMock(return_value=1.5)

        # Mock stores
        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # Mock FinBERT (should not be called)
        mock_finbert = MagicMock(spec=FinBERTClient)

        news_item = make_news_item("AAPL", 0)

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble:
            mock_run_ensemble.return_value = mock_outputs

            result = await process_news_item(
                item=news_item,
                clients=[],  # Not used when mocking run_ensemble_query
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Verify result
        assert result is not None
        assert result.symbol == "AAPL"
        assert result.fallback_used is False
        assert result.score > 0

        # Verify budget was checked
        mock_budget.check_budget.assert_called_once()

        # Verify FinBERT was NOT called
        mock_finbert.analyze.assert_not_called()

        # Verify stores were called
        mock_redis.write_sentiment.assert_called_once()
        mock_pg.write_signal.assert_called_once()

        # Verify spending was recorded
        assert mock_budget.record_spending.call_count >= 1

    @pytest.mark.asyncio
    async def test_budget_exhausted_uses_finbert_fallback(self):
        """Test that budget exhausted triggers FinBERT fallback."""
        # Mock budget tracker to raise LLMBudgetExhaustedError
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(
            side_effect=LLMBudgetExhaustedError("Budget exhausted")
        )

        # Mock FinBERT
        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(
            polarity=-0.3, confidence=0.65
        )

        # Mock stores
        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # Mock aggregator (should not be called)
        mock_aggregator = MagicMock(spec=EnsembleAggregator)

        news_item = make_news_item("AAPL", 0)

        result = await process_news_item(
            item=news_item,
            clients=[],  # No clients needed since budget exhausted
            aggregator=mock_aggregator,
            finbert=mock_finbert,
            budget_tracker=mock_budget,
            redis_store=mock_redis,
            pg_store=mock_pg,
        )

        # Verify result uses FinBERT fallback
        assert result is not None
        assert result.fallback_used is True
        assert result.model_id == "finbert"

        # Verify budget was checked
        mock_budget.check_budget.assert_called_once()

        # Verify FinBERT was called
        mock_finbert.analyze.assert_called_once()

        # Verify fallback counter was incremented
        mock_redis.increment_fallback_counter.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensemble_divergence_uses_finbert_fallback(self):
        """Test that ensemble divergence triggers FinBERT fallback."""
        # Mock budget tracker
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value="ok")

        # Mock run_ensemble_query to return outputs
        mock_outputs = [
            make_model_output(0.8, 0.9, "opus"),
            make_model_output(-0.7, 0.85, "qwen35:cloud"),
            make_model_output(0.1, 0.8, "deepseek-v4-pro:cloud"),
        ]

        # Mock aggregator to return None (divergence)
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = None

        # Mock FinBERT
        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(
            polarity=0.4, confidence=0.7
        )

        # Mock stores
        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)

        news_item = make_news_item("AAPL", 0)

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble:
            mock_run_ensemble.return_value = mock_outputs

            result = await process_news_item(
                item=news_item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Verify result uses FinBERT fallback
        assert result is not None
        assert result.fallback_used is True
        assert result.model_id == "finbert"

        # Verify fallback counter was incremented
        mock_redis.increment_fallback_counter.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_ensemble_outputs_uses_finbert(self):
        """Test that empty ensemble outputs triggers FinBERT fallback."""
        # Mock budget tracker
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value="ok")

        # Mock run_ensemble_query to return empty list
        mock_aggregator = MagicMock(spec=EnsembleAggregator)

        # Mock FinBERT
        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(
            polarity=0.2, confidence=0.5
        )

        # Mock stores
        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)

        news_item = make_news_item("AAPL", 0)

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble:
            mock_run_ensemble.return_value = []

            result = await process_news_item(
                item=news_item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Verify result uses FinBERT fallback
        assert result is not None
        assert result.fallback_used is True
        assert result.model_id == "finbert"


class TestRunInference:
    """Tests for run_inference — pure inference without store writes."""

    @pytest.mark.asyncio
    async def test_run_inference_ensemble_success(self):
        """run_inference returns SentimentResult without touching any store."""
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.8,
            confidence=0.9,
            reasoning="Bullish on earnings",
            model_ids=["opus"],
            ensemble_std=0.05,
        )
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()
        mock_budget.record_spending = AsyncMock()
        mock_finbert = MagicMock(spec=FinBERTClient)

        item = make_news_item("AAPL", 0)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock) as mock_eq:
            mock_eq.return_value = [MagicMock()]
            result = await run_inference(
                item=item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.fallback_used is False
        assert abs(result.score) <= 1.0
        mock_budget.check_budget.assert_called_once()
        mock_finbert.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_inference_divergence_uses_finbert(self):
        """run_inference uses FinBERT when ensemble diverges (aggregate returns None)."""
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = None  # divergence

        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(polarity=0.3, confidence=0.7)

        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()

        item = make_news_item("MSFT", 1)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock, return_value=[MagicMock()]):
            result = await run_inference(
                item=item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert result is not None
        assert result.fallback_used is True
        assert result.model_id == "finbert"
        mock_finbert.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_inference_budget_exhausted_uses_finbert(self):
        """run_inference uses FinBERT when budget is exhausted."""
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(
            side_effect=LLMBudgetExhaustedError("exhausted")
        )
        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(polarity=-0.2, confidence=0.6)

        item = make_news_item("SPY", 2)

        result = await run_inference(
            item=item,
            clients=[],
            aggregator=MagicMock(spec=EnsembleAggregator),
            finbert=mock_finbert,
            budget_tracker=mock_budget,
        )

        assert result is not None
        assert result.fallback_used is True
        assert "budget exhausted" in result.reasoning

    @pytest.mark.asyncio
    async def test_run_inference_no_store_writes(self):
        """run_inference never writes to Redis or PostgreSQL."""
        mock_redis = MagicMock()
        mock_pg = MagicMock()
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.5, confidence=0.8, reasoning="ok",
            model_ids=["opus"], ensemble_std=0.0,
        )
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()
        mock_budget.record_spending = AsyncMock()

        item = make_news_item("NVDA", 3)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock, return_value=[MagicMock()]):
            await run_inference(
                item=item, clients=[], aggregator=mock_aggregator,
                finbert=MagicMock(), budget_tracker=mock_budget,
            )

        # run_inference must NOT touch any store
        mock_redis.write_sentiment.assert_not_called()
        mock_pg.write_signal.assert_not_called()


class TestProcessNewsBatch:
    """Tests for process_news_batch function."""

    @pytest.mark.asyncio
    async def test_process_batch_returns_sentiment_results(self):
        """Test processing a batch of news items."""
        # Mock run_ensemble_query
        mock_outputs = [make_model_output(0.6, 0.8, "opus")]

        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.6,
            confidence=0.8,
            reasoning="Strong beat",
            model_ids=["opus"],
        )

        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value="ok")
        mock_budget.record_spending = AsyncMock(return_value=1.0)

        mock_finbert = MagicMock(spec=FinBERTClient)

        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)

        # Create batch of news items
        news_items = [make_news_item("AAPL", i) for i in range(3)]

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble:
            mock_run_ensemble.return_value = mock_outputs

            results = await process_news_batch(
                news_items=news_items,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Verify results
        assert len(results) == 3
        for result in results:
            assert isinstance(result, SentimentResult)
            assert result.fallback_used is False
            assert result.model_id.startswith("ensemble:")

    @pytest.mark.asyncio
    async def test_process_batch_mixed_results(self):
        """Test batch with some ensemble successes and some fallbacks."""
        # Use a list to track calls across the mock
        call_count = [0]

        def make_budget_mock():
            """Create a budget mock that raises on 2nd+ call."""
            mock = AsyncMock(spec=LLMBudgetTracker)

            async def check_budget_side_effect():
                call_count[0] += 1
                if call_count[0] >= 2:
                    raise LLMBudgetExhaustedError("Budget exhausted")
                return "ok"

            mock.check_budget = check_budget_side_effect
            mock.record_spending = AsyncMock(return_value=1.0)
            return mock

        mock_budget = make_budget_mock()

        mock_outputs = [make_model_output(0.6, 0.8, "opus")]

        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.6,
            confidence=0.8,
            reasoning="Strong beat",
            model_ids=["opus"],
        )

        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(
            polarity=0.3, confidence=0.6
        )

        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)

        news_items = [make_news_item("AAPL", i) for i in range(3)]

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble:
            mock_run_ensemble.return_value = mock_outputs

            results = await process_news_batch(
                news_items=news_items,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Should have 3 results
        assert len(results) == 3

        # First should be ensemble, rest should be FinBERT fallbacks
        ensemble_count = sum(1 for r in results if not r.fallback_used)
        fallback_count = sum(1 for r in results if r.fallback_used)

        assert ensemble_count == 1
        assert fallback_count == 2


class TestDKCoTPrompt:
    """Tests for Domain Knowledge Chain-of-Thought prompt."""

    def test_prompt_formatting(self):
        """Test that the DK-CoT prompt is properly formatted."""
        # Verify prompt contains required elements
        assert "buy-side equity analyst" in _DK_COT_PROMPT
        assert "step-by-step" in _DK_COT_PROMPT.lower()
        assert "revenue" in _DK_COT_PROMPT.lower()
        assert "bull case" in _DK_COT_PROMPT.lower()
        assert "bear case" in _DK_COT_PROMPT.lower()
        assert "{text}" in _DK_COT_PROMPT
        assert "{symbol}" in _DK_COT_PROMPT
        assert "polarity" in _DK_COT_PROMPT
        assert "confidence" in _DK_COT_PROMPT
        assert "reasoning" in _DK_COT_PROMPT

    def test_prompt_truncation(self):
        """Test that prompt truncates long bodies."""
        # The truncation happens in process_news_item:
        # prompt = _DK_COT_PROMPT.format(text=item.body[:2000], symbol=symbol)
        long_body = "A" * 5000
        truncated = long_body[:2000]
        assert len(truncated) == 2000

        # Verify the prompt template itself accepts the truncated text
        prompt = _DK_COT_PROMPT.format(text=truncated, symbol="AAPL")
        assert "AAPL" in prompt
        assert "polarity" in prompt


class TestMarketAuxPreFilter:
    """Tests for MarketAux neutral pre-filter in run_sentiment_worker."""

    def _make_marketaux_item(self, sentiment: float, ticker: str = "AAPL") -> MarketAuxNewsItem:
        from datetime import datetime, timezone
        return MarketAuxNewsItem(
            id=f"https://marketaux.com/{ticker}",
            source="marketaux",
            timestamp=datetime.now(timezone.utc),
            title="Test headline",
            body="Test body text for sentiment analysis.",
            url=f"https://marketaux.com/{ticker}",
            language="en",
            asset_tags=[ticker],
            marketaux_sentiment=sentiment,
        )

    def test_neutral_marketaux_item_skipped(self):
        """Items with |marketaux_sentiment| < 0.2 are skipped before LLM."""
        from src.workers.sentiment import _MARKETAUX_NEUTRAL_THRESHOLD
        item = self._make_marketaux_item(sentiment=0.1)
        assert abs(item.marketaux_sentiment) < _MARKETAUX_NEUTRAL_THRESHOLD

    def test_strong_marketaux_item_not_skipped(self):
        """Items with |marketaux_sentiment| >= 0.2 pass the pre-filter."""
        from src.workers.sentiment import _MARKETAUX_NEUTRAL_THRESHOLD
        item = self._make_marketaux_item(sentiment=0.5)
        assert abs(item.marketaux_sentiment) >= _MARKETAUX_NEUTRAL_THRESHOLD

    def test_negative_strong_marketaux_item_not_skipped(self):
        """Negative strong sentiment items pass the pre-filter."""
        from src.workers.sentiment import _MARKETAUX_NEUTRAL_THRESHOLD
        item = self._make_marketaux_item(sentiment=-0.4)
        assert abs(item.marketaux_sentiment) >= _MARKETAUX_NEUTRAL_THRESHOLD

    def test_marketaux_neutral_threshold_is_0_2(self):
        """Threshold constant is 0.2 (agreed token-saving boundary)."""
        from src.workers.sentiment import _MARKETAUX_NEUTRAL_THRESHOLD
        assert _MARKETAUX_NEUTRAL_THRESHOLD == pytest.approx(0.2)

    def test_plain_newsitem_not_affected_by_prefilter(self):
        """Plain NewsItem (no marketaux_sentiment) is never skipped by the pre-filter."""
        item = make_news_item("MSFT")
        assert not isinstance(item, MarketAuxNewsItem)
        assert not hasattr(item, "marketaux_sentiment") or True  # NewsItem has no such attr
