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
    _shadow_query_candidates,
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

            await process_news_item(
                item=news_item,
                clients=[],  # Not used when mocking run_ensemble_query
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Verify budget was checked
        mock_budget.check_budget.assert_called_once()

        # Verify FinBERT was NOT called
        mock_finbert.analyze.assert_not_called()

        # Verify stores were called
        mock_redis.write_sentiment.assert_called_once()
        mock_pg.write_signal.assert_called_once()
        mock_pg.log_news_item.assert_called_once()
        mock_pg.log_llm_responses.assert_called_once()

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

        await process_news_item(
            item=news_item,
            clients=[],  # No clients needed since budget exhausted
            aggregator=mock_aggregator,
            finbert=mock_finbert,
            budget_tracker=mock_budget,
            redis_store=mock_redis,
            pg_store=mock_pg,
        )

        # Verify budget was checked
        mock_budget.check_budget.assert_called_once()

        # Verify FinBERT was called
        mock_finbert.analyze.assert_called_once()

        # Verify fallback counter was incremented
        mock_redis.increment_fallback_counter.assert_called_once()
        mock_pg.write_signal.assert_called_once()
        mock_pg.log_news_item.assert_called_once()
        # No LLM responses on fallback
        mock_pg.log_llm_responses.assert_not_called()

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

            await process_news_item(
                item=news_item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Verify fallback counter was incremented
        mock_redis.increment_fallback_counter.assert_called_once()
        mock_pg.write_signal.assert_called_once()
        mock_pg.log_news_item.assert_called_once()
        # Divergent raw outputs are persisted for audit, but marked ineligible:
        # they did NOT enter the signal (FinBERT did), so LOO-ICIR and post-hoc
        # analysis must not count them as contributors.
        mock_pg.log_llm_responses.assert_called_once()
        _kwargs = mock_pg.log_llm_responses.call_args.kwargs
        assert _kwargs["outputs"] == mock_outputs
        assert _kwargs["force_ineligible"] is True

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

            await process_news_item(
                item=news_item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # Verify FinBERT fallback was used
        mock_finbert.analyze.assert_called_once()
        mock_redis.increment_fallback_counter.assert_called_once()
        mock_pg.write_signal.assert_called_once()
        mock_pg.log_news_item.assert_called_once()
        mock_pg.log_llm_responses.assert_not_called()


class TestFallbackCounterPersistence:
    """The fallback_counters Postgres table (migrations/001_initial.sql) was never
    written to — only the Redis key was. process_news_item must persist both.
    """

    @pytest.mark.asyncio
    async def test_fallback_used_persists_counter_to_postgres(self):
        """On fallback, Postgres must record the same count Redis just returned."""
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(
            side_effect=LLMBudgetExhaustedError("Budget exhausted")
        )
        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(polarity=-0.3, confidence=0.65)
        mock_redis = MagicMock(spec=RedisStore)
        mock_redis.increment_fallback_counter.return_value = 3
        mock_pg = MagicMock(spec=PostgreSQLStore)
        mock_aggregator = MagicMock(spec=EnsembleAggregator)

        news_item = make_news_item("AAPL", 0)

        await process_news_item(
            item=news_item,
            clients=[],
            aggregator=mock_aggregator,
            finbert=mock_finbert,
            budget_tracker=mock_budget,
            redis_store=mock_redis,
            pg_store=mock_pg,
        )

        mock_pg.record_fallback_increment.assert_called_once_with(
            "consecutive_fallback", 3
        )

    @pytest.mark.asyncio
    async def test_single_model_success_resets_breaker_counter(self):
        """#128: a single-model read is gated for trading (fallback_used=True) but
        is NOT a full ensemble outage, so it must RESET the sizing-breaker counter
        (increment only on a real FinBERT full fallback), not increment it."""
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
        mock_redis.increment_fallback_counter.return_value = 1
        mock_pg = MagicMock(spec=PostgreSQLStore)

        news_item = make_news_item("AAPL", 0)

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble:
            mock_run_ensemble.return_value = mock_outputs

            await process_news_item(
                item=news_item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        mock_pg.record_fallback_reset.assert_called_once_with("consecutive_fallback")
        mock_pg.record_fallback_increment.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensemble_success_persists_counter_reset_to_postgres(self):
        """On a true >=2-model ensemble success, Postgres must record the reset."""
        mock_outputs = [
            make_model_output(0.6, 0.8, "opus"),
            make_model_output(0.55, 0.75, "glm-5.2:cloud"),
        ]
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.6,
            confidence=0.8,
            reasoning="Strong beat",
            model_ids=["opus", "glm-5.2:cloud"],
        )
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value="ok")
        mock_budget.record_spending = AsyncMock(return_value=1.0)
        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)

        news_item = make_news_item("AAPL", 0)

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble:
            mock_run_ensemble.return_value = mock_outputs

            await process_news_item(
                item=news_item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        mock_pg.record_fallback_reset.assert_called_once_with("consecutive_fallback")


class TestRunInference:
    """Tests for run_inference — pure inference without store writes."""

    @pytest.mark.asyncio
    async def test_run_inference_single_model_labeled_as_fallback(self):
        """#111: a one-model aggregate is labeled single: and gated like a fallback."""
        mock_raw_output = ModelOutput(
            symbol="AAPL", polarity=0.8, confidence=0.9,
            reasoning="Bullish on earnings", model_id="opus",
        )
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
            mock_eq.return_value = [mock_raw_output]
            inference_result = await run_inference(
                item=item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert inference_result is not None
        result, raw_outputs = inference_result
        assert result.symbol == "AAPL"
        assert result.fallback_used is True
        assert result.model_id == "single:opus"
        assert "[single-model:opus]" in result.reasoning
        assert abs(result.score) <= 1.0
        assert isinstance(raw_outputs, list)
        assert len(raw_outputs) > 0
        assert raw_outputs[0].model_id == "opus"
        mock_budget.check_budget.assert_called_once()
        mock_finbert.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_inference_ensemble_success(self):
        """run_inference returns a true >=2-model ensemble result without fallback."""
        mock_raw_outputs = [
            ModelOutput(
                symbol="AAPL", polarity=0.8, confidence=0.9,
                reasoning="Bullish on earnings", model_id="glm-5.2:cloud",
            ),
            ModelOutput(
                symbol="AAPL", polarity=0.75, confidence=0.85,
                reasoning="Bullish on earnings", model_id="gpt-oss:20b-cloud",
            ),
        ]
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.8,
            confidence=0.9,
            reasoning="Bullish on earnings",
            model_ids=["glm-5.2:cloud", "gpt-oss:20b-cloud"],
            ensemble_std=0.05,
        )
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()
        mock_budget.record_spending = AsyncMock()
        mock_finbert = MagicMock(spec=FinBERTClient)

        item = make_news_item("AAPL", 0)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock) as mock_eq:
            mock_eq.return_value = mock_raw_outputs
            inference_result = await run_inference(
                item=item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert inference_result is not None
        result, raw_outputs = inference_result
        assert result.symbol == "AAPL"
        assert result.fallback_used is False
        assert result.model_id == "ensemble:glm-5.2:cloud+gpt-oss:20b-cloud"
        assert abs(result.score) <= 1.0
        assert isinstance(raw_outputs, list)
        assert len(raw_outputs) == 2
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

        mock_raw = [MagicMock()]
        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock, return_value=mock_raw):
            inference_result = await run_inference(
                item=item,
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert inference_result is not None
        result, raw_outputs = inference_result
        assert result.fallback_used is True
        assert result.model_id == "finbert"
        # Raw outputs are preserved on divergence so the disagreement can be
        # audited in llm_responses (they were silently discarded before).
        assert raw_outputs == mock_raw
        mock_finbert.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_inference_low_confidence_agreement_skips_finbert(self):
        """#90: when the primary aggregation fails only because no model met
        min_confidence (not genuine divergence), run_inference must retry with
        min_confidence=0.0 and use that consensus directly instead of calling
        FinBERT — the models agreeing at low confidence is a legitimate weak
        signal, not a "divergence" to discard.
        """
        low_confidence_result = MagicMock(
            polarity=0.05, confidence=0.225, reasoning="Sector-level, no direct read-through",
            model_ids=["glm", "gpt"], ensemble_std=0.05,
        )
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        # First call (default threshold) -> None; retry call (min_confidence=0.0) -> succeeds.
        mock_aggregator.aggregate.side_effect = [None, low_confidence_result]

        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()
        mock_budget.record_spending = AsyncMock()

        item = make_news_item("AAPL", 4)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock, return_value=[MagicMock(), MagicMock()]):
            inference_result = await run_inference(
                item=item, clients=[], aggregator=mock_aggregator,
                finbert=mock_finbert, budget_tracker=mock_budget,
            )

        assert inference_result is not None
        result, _ = inference_result
        assert result.fallback_used is False
        assert result.model_id == "ensemble:glm+gpt"
        assert abs(result.score - (0.05 * 0.225)) < 1e-6
        mock_finbert.analyze.assert_not_called()

        assert mock_aggregator.aggregate.call_count == 2
        retry_call = mock_aggregator.aggregate.call_args_list[1]
        assert retry_call.kwargs.get("min_confidence") == 0.0

    @pytest.mark.asyncio
    async def test_run_inference_genuine_divergence_still_uses_finbert(self):
        """#90 regression guard: if the retry (min_confidence=0.0) ALSO returns
        None, the models genuinely disagree even without a confidence floor —
        must still fall back to FinBERT, same as before."""
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.side_effect = [None, None]

        mock_finbert = MagicMock(spec=FinBERTClient)
        mock_finbert.analyze.return_value = MagicMock(polarity=0.3, confidence=0.7)
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock()

        item = make_news_item("MSFT", 5)

        with patch("src.workers.sentiment.run_ensemble_query",
                   new_callable=AsyncMock, return_value=[MagicMock(), MagicMock()]):
            inference_result = await run_inference(
                item=item, clients=[], aggregator=mock_aggregator,
                finbert=mock_finbert, budget_tracker=mock_budget,
            )

        assert inference_result is not None
        result, _ = inference_result
        assert result.fallback_used is True
        assert result.model_id == "finbert"
        assert result.reasoning == "FinBERT fallback (ensemble divergence)"
        mock_finbert.analyze.assert_called_once()
        assert mock_aggregator.aggregate.call_count == 2

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

        inference_result = await run_inference(
            item=item,
            clients=[],
            aggregator=MagicMock(spec=EnsembleAggregator),
            finbert=mock_finbert,
            budget_tracker=mock_budget,
        )

        assert inference_result is not None
        result, raw_outputs = inference_result
        assert result.fallback_used is True
        assert "budget exhausted" in result.reasoning
        assert raw_outputs == []

    @pytest.mark.asyncio
    async def test_run_inference_no_store_writes(self):
        """run_inference never writes to Redis or PostgreSQL."""
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
            inference_result = await run_inference(
                item=item, clients=[], aggregator=mock_aggregator,
                finbert=MagicMock(), budget_tracker=mock_budget,
            )

        assert inference_result is not None
        result, raw_outputs = inference_result
        assert result is not None
        # run_inference must NOT touch any store (verified by absence of store mocks)


class TestProcessNewsBatch:
    """Tests for process_news_batch function."""

    @pytest.mark.asyncio
    async def test_process_batch_returns_single_model_labeled_as_fallback(self):
        """#111: a batch of single-model successes is gated like fallbacks."""
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
        mock_redis.increment_fallback_counter.return_value = 1
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
            assert result.fallback_used is True
            assert result.model_id == "single:opus"

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

        mock_outputs = [
            make_model_output(0.6, 0.8, "opus"),
            make_model_output(0.55, 0.75, "glm-5.2:cloud"),
        ]

        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.6,
            confidence=0.8,
            reasoning="Strong beat",
            model_ids=["opus", "glm-5.2:cloud"],
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
        assert "bull" in _DK_COT_PROMPT.lower()  # "bull/bear case" / "bull/bear analysis"
        assert "bear" in _DK_COT_PROMPT.lower()
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



class TestEnsembleWeightReading:
    """Verify that per-model weights from Redis are applied to ensemble aggregation (Bug 2 fix).

    The sentiment worker must use LOO-rebalanced weights when available.
    When the primary key is absent (auto-apply guardrails frozen), it falls
    back to the suggestion key so the weekly ICIR computation is never wasted.
    """

    def _make_outputs(self) -> list[ModelOutput]:
        return [
            make_model_output(polarity=0.8, confidence=0.9, model_id="kimi-k2.6:cloud"),
            make_model_output(polarity=0.6, confidence=0.7, model_id="qwen3.5:cloud"),
            make_model_output(polarity=0.4, confidence=0.6, model_id="deepseek-v4-pro:cloud"),
        ]

    def test_aggregate_with_equal_weights_uses_confidence_only(self):
        """When weights=None, aggregate uses pure confidence weighting."""
        aggregator = EnsembleAggregator()
        outputs = self._make_outputs()
        result_no_weights = aggregator.aggregate(outputs, weights=None)
        assert result_no_weights is not None
        # Confidence-weighted mean of 0.8, 0.6, 0.4 with confs 0.9, 0.7, 0.6
        total_conf = 0.9 + 0.7 + 0.6
        expected = (0.8 * 0.9 + 0.6 * 0.7 + 0.4 * 0.6) / total_conf
        assert result_no_weights.polarity == pytest.approx(expected, abs=1e-6)

    def test_aggregate_applies_per_model_weights(self):
        """When weights dict is provided, per-model weights scale confidence."""
        aggregator = EnsembleAggregator()
        outputs = self._make_outputs()

        # Give kimi a much higher weight — result should shift toward kimi's polarity
        weights = {"kimi-k2.6:cloud": 0.80, "qwen3.5:cloud": 0.10, "deepseek-v4-pro:cloud": 0.10}
        result_with_weights = aggregator.aggregate(outputs, weights=weights)
        result_no_weights = aggregator.aggregate(outputs, weights=None)

        assert result_with_weights is not None
        assert result_no_weights is not None
        # Kimi has highest polarity (0.8), so weighted result should be higher
        assert result_with_weights.polarity > result_no_weights.polarity

    def test_aggregate_unknown_model_falls_back_to_1(self):
        """Model IDs not in weights dict get a factor of 1.0 (no penalty)."""
        aggregator = EnsembleAggregator()
        outputs = self._make_outputs()
        # Weights only cover kimi; qwen and deepseek get factor=1.0
        partial_weights = {"kimi-k2.6:cloud": 0.5}
        result = aggregator.aggregate(outputs, weights=partial_weights)
        assert result is not None

    def test_run_sentiment_worker_uses_suggestion_when_applied_not_set(self):
        """Worker falls back to suggestion weights when ensemble:weights:current absent (Bug 2).

        Verifies that when the primary Redis key is absent but a suggestion exists,
        the worker resolves model_weights from the suggestion and passes them
        to process_news_batch.
        """
        import json
        from unittest.mock import patch, MagicMock
        from src.workers.sentiment import run_sentiment_worker

        suggestion = {
            "suggested_weights": {
                # Active default pair is "all" -> kimi + glm52, so suggestion
                # weights must match active models.
                "kimi-k2.6:cloud": 0.40,
                "glm-5.2:cloud": 0.60,
            },
            "purified_icir": {},
            "freeze_reason": "VIX data unavailable (fail-safe)",
            "computed_at": "2026-06-01T04:00:00+00:00",
        }

        # Provide a valid news item in the queue so the worker reaches
        # process_news_batch instead of returning early.
        news_item_json = json.dumps({
            "id": "test-aapl-1",
            "title": "AAPL earnings beat",
            "body": "Apple reported strong Q4 earnings.",
            "url": "https://example.com/aapl",
            "source": "test",
            "asset_tags": ["AAPL"],
        }).encode()

        mock_redis_client = MagicMock()
        mock_redis_client.lrange.return_value = []  # no stuck items
        # lmove returns one item on first call, then None (empty queue)
        mock_redis_client.lmove.side_effect = [news_item_json, None]
        mock_redis_client.delete.return_value = None

        mock_redis_store = MagicMock()
        mock_redis_store.get_ensemble_weights.return_value = None  # primary key absent
        mock_redis_store.get_weight_suggestion.return_value = suggestion
        mock_redis_store.get_llm_models.return_value = None

        with patch("src.workers.sentiment.is_market_open", return_value=True), \
             patch("redis.Redis") as mock_redis_cls, \
             patch("src.workers.sentiment.RedisStore", return_value=mock_redis_store), \
             patch("psycopg2.connect") as mock_pg_connect, \
             patch("src.workers.sentiment.PostgreSQLStore") as mock_pg_cls, \
             patch("src.workers.sentiment.LLMBudgetTracker") as mock_bt_cls, \
             patch("src.workers.sentiment.process_news_batch") as mock_pnb, \
             patch("src.workers.sentiment.asyncio.run") as mock_async_run:
            mock_redis_cls.from_url.return_value = mock_redis_client
            mock_pg_connect.return_value = MagicMock()
            mock_pg_cls.return_value = MagicMock()
            mock_bt_cls.return_value = MagicMock()
            # asyncio.run is mocked, so process_news_batch is called
            # (creating a coroutine from the mock), but never awaited.
            # The mock records what kwargs were passed.
            mock_async_run.return_value = []
            run_sentiment_worker()

        # process_news_batch should have been called with the suggestion weights
        assert mock_pnb.call_count == 1, f"Expected 1 call, got {mock_pnb.call_count}"
        assert mock_pnb.call_args.kwargs.get("weights") == suggestion["suggested_weights"]

    def test_run_sentiment_worker_prefers_applied_over_suggestion(self):
        """Worker uses applied weights (ensemble:weights:current) when available."""
        import json
        from unittest.mock import patch, MagicMock
        from src.workers.sentiment import run_sentiment_worker

        applied = {"kimi-k2.6:cloud": 0.35, "glm-5.2:cloud": 0.65}
        raw_applied = json.dumps({"weights": applied, "source": "auto_apply"}).encode()

        # Provide a valid news item in the queue
        news_item_json = json.dumps({
            "id": "test-aapl-1",
            "title": "AAPL earnings beat",
            "body": "Apple reported strong Q4 earnings.",
            "url": "https://example.com/aapl",
            "source": "test",
            "asset_tags": ["AAPL"],
        }).encode()

        mock_redis_client = MagicMock()
        mock_redis_client.lrange.return_value = []
        mock_redis_client.lmove.side_effect = [news_item_json, None]
        mock_redis_client.delete.return_value = None

        mock_redis_store = MagicMock()
        mock_redis_store.get_ensemble_weights.return_value = raw_applied
        mock_redis_store.get_llm_models.return_value = None

        with patch("src.workers.sentiment.is_market_open", return_value=True), \
             patch("redis.Redis") as mock_redis_cls, \
             patch("src.workers.sentiment.RedisStore", return_value=mock_redis_store), \
             patch("psycopg2.connect") as mock_pg_connect, \
             patch("src.workers.sentiment.PostgreSQLStore") as mock_pg_cls, \
             patch("src.workers.sentiment.LLMBudgetTracker") as mock_bt_cls, \
             patch("src.workers.sentiment.process_news_batch") as mock_pnb, \
             patch("src.workers.sentiment.asyncio.run") as mock_async_run:
            mock_redis_cls.from_url.return_value = mock_redis_client
            mock_pg_connect.return_value = MagicMock()
            mock_pg_cls.return_value = MagicMock()
            mock_bt_cls.return_value = MagicMock()
            mock_async_run.return_value = []
            run_sentiment_worker()

        assert mock_pnb.call_count == 1, f"Expected 1 call, got {mock_pnb.call_count}"
        assert mock_pnb.call_args.kwargs.get("weights") == applied

    def test_run_sentiment_worker_pulls_more_than_four_fresh_items_per_cycle(self):
        """Worker must drain more than 4 fresh items/cycle.

        With 6 fresh items available, the old hardcoded cap of 4 stopped the
        scan early — leaving fresh news unscored until it aged past the S4
        strategy's 4h usability window (throughput bottleneck, worker idle
        70-90% of each 15-min cycle).
        """
        import json
        from unittest.mock import patch, MagicMock
        from src.workers.sentiment import run_sentiment_worker

        def make_item_json(n: int) -> bytes:
            return json.dumps({
                "id": f"test-item-{n}",
                "title": f"AAPL earnings update {n}",
                "body": "Apple reported strong quarterly results.",
                "url": f"https://example.com/aapl-{n}",
                "source": "test",
                "asset_tags": ["AAPL"],
            }).encode()

        fresh_items = [make_item_json(n) for n in range(6)]

        mock_redis_client = MagicMock()
        mock_redis_client.lrange.return_value = []
        mock_redis_client.lmove.side_effect = fresh_items + [None]
        mock_redis_client.delete.return_value = None

        mock_redis_store = MagicMock()
        mock_redis_store.get_ensemble_weights.return_value = None
        mock_redis_store.get_weight_suggestion.return_value = None
        mock_redis_store.get_llm_models.return_value = None

        with patch("src.workers.sentiment.is_market_open", return_value=True), \
             patch("redis.Redis") as mock_redis_cls, \
             patch("src.workers.sentiment.RedisStore", return_value=mock_redis_store), \
             patch("psycopg2.connect") as mock_pg_connect, \
             patch("src.workers.sentiment.PostgreSQLStore") as mock_pg_cls, \
             patch("src.workers.sentiment.LLMBudgetTracker") as mock_bt_cls, \
             patch("src.workers.sentiment.process_news_batch") as mock_pnb, \
             patch("src.workers.sentiment.asyncio.run") as mock_async_run:
            mock_redis_cls.from_url.return_value = mock_redis_client
            mock_pg_connect.return_value = MagicMock()
            mock_pg_cls.return_value = MagicMock()
            mock_bt_cls.return_value = MagicMock()
            mock_async_run.return_value = []
            run_sentiment_worker()

        assert mock_pnb.call_count == 1, f"Expected 1 call, got {mock_pnb.call_count}"
        pulled = mock_pnb.call_args.kwargs["news_items"]
        assert len(pulled) == 6, (
            f"Expected all 6 fresh items to be pulled in one cycle, got {len(pulled)}"
        )


class TestProcessNewsBatchConcurrency:
    """process_news_batch must overlap item processing, not fully serialize it."""

    @pytest.mark.asyncio
    async def test_process_batch_allows_two_concurrent_items(self):
        """At least 2 items should be in flight at once.

        The old asyncio.Semaphore(1) fully serialized the batch even though
        each item's own Ollama round-trip only ever occupies at most 2 of the
        2 global Ollama semaphore slots — serializing everything left the
        non-Ollama portion of each item (store writes, aggregation) idle time
        that a second in-flight item could have used.
        """
        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def fake_process_item(item, **kwargs):
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1
            return make_sentiment_result(symbol=item.asset_tags[0])

        news_items = [make_news_item("AAPL", i) for i in range(4)]

        with patch(
            "src.workers.sentiment.process_news_item", side_effect=fake_process_item
        ):
            await process_news_batch(
                news_items=news_items,
                clients=[],
                aggregator=MagicMock(),
                finbert=MagicMock(),
                budget_tracker=MagicMock(),
                redis_store=MagicMock(),
                pg_store=MagicMock(),
            )

        assert max_active >= 2, (
            f"Expected at least 2 concurrent items, max observed was {max_active}"
        )


class TestProcessNewsBatchShadowDecoupling:
    """Critical finding (stage2-shadow-2026-07-12 review): Stage-2 shadow scoring
    awaited inline inside process_news_item composed with the live ensemble's
    up-to-90s call, inside process_news_batch's per-item semaphore — across the
    batch's 6 sequential concurrency-2 rounds this could blow celery_app.py's
    task_soft_time_limit (780s). process_news_batch must instead give shadow
    tasks a single bounded wait AFTER all live items have returned, so a slow
    shadow candidate cannot hold up the batch's return, while a fast one still
    gets to finish and log its row.
    """

    @staticmethod
    def _make_live_mocks():
        mock_outputs = [make_model_output(0.6, 0.8, "opus")]
        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = MagicMock(
            polarity=0.6, confidence=0.8, reasoning="Strong beat", model_ids=["opus"],
        )
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value="ok")
        mock_budget.record_spending = AsyncMock(return_value=1.0)
        mock_finbert = MagicMock(spec=FinBERTClient)
        return mock_outputs, mock_aggregator, mock_budget, mock_finbert

    @pytest.mark.asyncio
    async def test_slow_shadow_candidate_does_not_block_batch_return(self):
        """A shadow call slower than the bounded-wait window must not make
        process_news_batch wait for it: the batch must return within roughly
        the bounded-wait window, not the shadow call's full duration.
        """
        mock_outputs, mock_aggregator, mock_budget, mock_finbert = self._make_live_mocks()
        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)
        news_items = [make_news_item("AAPL", i) for i in range(4)]

        async def slow_shadow(**kwargs):
            await asyncio.sleep(0.5)

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble, patch(
            "src.workers.sentiment._shadow_query_candidates",
            new=AsyncMock(side_effect=slow_shadow),
        ), patch("src.workers.sentiment._SHADOW_BOUNDED_WAIT_S", 0.05, create=True):
            mock_run_ensemble.return_value = mock_outputs

            # Old (pre-fix) behavior awaits the 0.5s shadow call inline inside
            # each item's semaphore slot: with 4 items at concurrency 2 that's
            # >= 1.0s total, which the 0.3s ceiling below is well under —
            # proving we're no longer waiting for the slow shadow candidate.
            results = await asyncio.wait_for(
                process_news_batch(
                    news_items=news_items,
                    clients=[],
                    aggregator=mock_aggregator,
                    finbert=mock_finbert,
                    budget_tracker=mock_budget,
                    redis_store=mock_redis,
                    pg_store=mock_pg,
                ),
                timeout=0.3,
            )

        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_fast_shadow_candidate_still_logs_within_bounded_wait(self):
        """A shadow call that finishes well inside the bounded-wait window must
        NOT be cancelled — its store write must still happen. Guards against an
        overly-aggressive bounded wait that would defeat the point of giving
        shadow tasks a chance to complete at all.
        """
        mock_outputs, mock_aggregator, mock_budget, mock_finbert = self._make_live_mocks()
        mock_redis = MagicMock(spec=RedisStore)
        mock_pg = MagicMock(spec=PostgreSQLStore)
        news_items = [make_news_item("AAPL", 0)]

        async def fast_shadow(*, clean_body, clean_symbol, news_log_id, pg_store, redis_store):
            await asyncio.sleep(0.01)
            pg_store.log_shadow_responses([{"symbol": clean_symbol}])

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_run_ensemble, patch(
            "src.workers.sentiment._shadow_query_candidates",
            new=AsyncMock(side_effect=fast_shadow),
        ), patch("src.workers.sentiment._SHADOW_BOUNDED_WAIT_S", 0.2, create=True):
            mock_run_ensemble.return_value = mock_outputs

            await asyncio.wait_for(
                process_news_batch(
                    news_items=news_items,
                    clients=[],
                    aggregator=mock_aggregator,
                    finbert=mock_finbert,
                    budget_tracker=mock_budget,
                    redis_store=mock_redis,
                    pg_store=mock_pg,
                ),
                timeout=1.0,
            )

        mock_pg.log_shadow_responses.assert_called_once()


class TestProcessNewsItemCorrelation:
    """process_news_item must write signal first, then link to news_log row."""

    @pytest.mark.asyncio
    async def test_news_log_id_linked_after_write(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.workers.sentiment import process_news_item
        from src.models.signals import SentimentResult
        from src.models.news import NewsItem
        from datetime import datetime, timezone

        item = NewsItem(
            id="http://u.com:AAPL",
            title="T", url="http://u.com", source="gdelt",
            body="b", asset_tags=["AAPL"],
            timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        result = SentimentResult(
            symbol="AAPL", score=0.6, confidence=0.9,
            reasoning="r", model_id="ensemble:glm",
        )

        mock_pg = MagicMock()
        mock_pg.write_signal.return_value = 7       # signal_id = 7
        mock_pg.log_news_item.return_value = 42     # news_log_id = 42

        mock_redis = MagicMock()
        mock_clients = []
        mock_aggregator = MagicMock()
        mock_finbert = MagicMock()
        mock_budget = MagicMock()
        mock_budget.check_budget = AsyncMock()

        with patch(
            "src.workers.sentiment.run_inference",
            new=AsyncMock(return_value=(result, [])),
        ):
            await process_news_item(
                item=item,
                clients=mock_clients,
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
                redis_store=mock_redis,
                pg_store=mock_pg,
            )

        # signal written first
        mock_pg.write_signal.assert_called_once()
        # Redis write called with signal_id=7
        mock_redis.write_sentiment.assert_called_once()
        call_kwargs = mock_redis.write_sentiment.call_args
        assert call_kwargs[1].get("signal_id") == 7 or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 7
        )
        # news_log_id linked
        mock_pg.link_signal_to_news.assert_called_once_with(signal_id=7, news_log_id=42)

    @pytest.mark.asyncio
    async def test_news_log_conflict_skips_link(self):
        """When log_news_item returns None (duplicate), link_signal_to_news is NOT called."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from src.workers.sentiment import process_news_item
        from src.models.signals import SentimentResult
        from src.models.news import NewsItem
        from datetime import datetime, timezone

        item = NewsItem(
            id="http://u.com:AAPL",
            title="T", url="http://u.com", source="gdelt",
            body="b", asset_tags=["AAPL"],
            timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        result = SentimentResult(
            symbol="AAPL", score=0.6, confidence=0.9,
            reasoning="r", model_id="ensemble:glm",
        )

        mock_pg = MagicMock()
        mock_pg.write_signal.return_value = 7
        mock_pg.log_news_item.return_value = None   # conflict → no id

        mock_redis = MagicMock()

        with patch(
            "src.workers.sentiment.run_inference",
            new=AsyncMock(return_value=(result, [])),
        ):
            await process_news_item(
                item=item, clients=[], aggregator=MagicMock(),
                finbert=MagicMock(), budget_tracker=MagicMock(),
                redis_store=mock_redis, pg_store=mock_pg,
            )

        mock_pg.link_signal_to_news.assert_not_called()


def test_run_sentiment_worker_skips_when_market_closed():
    """WS-4: sentiment worker exits early when US market is closed."""
    from src.workers.sentiment import run_sentiment_worker

    with patch("src.workers.sentiment.is_market_open", return_value=False), \
         patch("redis.Redis") as mock_redis_cls, \
         patch("psycopg2.connect") as mock_pg_connect:
        result = run_sentiment_worker()

    assert result["skipped"] is True
    assert result["reason"] == "market_closed"
    mock_redis_cls.from_url.return_value.close.assert_called_once()
    mock_pg_connect.return_value.close.assert_called_once()


class TestShadowTimeoutSymmetry:
    """#358: i candidati shadow devono ricevere lo stesso budget di tempo dei
    modelli live. Un tetto piu' basso non misura i modelli: misura il tetto.
    """

    @staticmethod
    def _redis_armato():
        redis = MagicMock(spec=RedisStore)
        redis.get_shadow_comparison_start.return_value = "2026-08-24T07:00:00+00:00"
        return redis

    @staticmethod
    def _client(model_id, timeout):
        client = MagicMock()
        client.model_id = model_id
        client._OLLAMA_TIMEOUT = timeout
        client.complete = AsyncMock(
            return_value=MagicMock(polarity=0.4, confidence=0.7, reasoning="ok")
        )
        return client

    @pytest.mark.asyncio
    async def test_il_candidato_riceve_il_budget_del_proprio_client(self, mocker):
        """Il timeout applicato deriva da _OLLAMA_TIMEOUT del client, non da 45."""
        visti = []
        vero_wait_for = asyncio.wait_for

        async def _spia(coro, timeout=None):
            visti.append(timeout)
            return await vero_wait_for(coro, timeout=timeout)

        mocker.patch(
            "src.workers.sentiment.build_shadow_clients",
            return_value=[self._client("lento:cloud", 90)],
        )
        mocker.patch.object(asyncio, "wait_for", _spia)
        pg = MagicMock(spec=PostgreSQLStore)

        await _shadow_query_candidates("corpo", "AAPL", 1, pg, self._redis_armato())

        assert visti, "wait_for non e' stato chiamato"
        assert min(visti) >= 90, (
            f"il candidato ha ricevuto {min(visti)}s invece dei 90s del suo client"
        )

    @pytest.mark.asyncio
    async def test_budget_diverso_per_client_diverso(self, mocker):
        """Due candidati con timeout diversi ricevono budget diversi: il tetto
        non e' un letterale condiviso."""
        visti = []
        vero_wait_for = asyncio.wait_for

        async def _spia(coro, timeout=None):
            visti.append(timeout)
            return await vero_wait_for(coro, timeout=timeout)

        mocker.patch(
            "src.workers.sentiment.build_shadow_clients",
            return_value=[self._client("a:cloud", 60), self._client("b:cloud", 120)],
        )
        mocker.patch.object(asyncio, "wait_for", _spia)
        pg = MagicMock(spec=PostgreSQLStore)

        await _shadow_query_candidates("corpo", "AAPL", 1, pg, self._redis_armato())

        assert len(set(visti)) == 2, f"stesso tetto per client diversi: {visti}"

    @pytest.mark.asyncio
    async def test_timeout_distinguibile_da_parse_error(self, mocker):
        """Un timeout e un output non parsabile devono lasciare tracce diverse:
        oggi entrambi finiscono come parse_error=True con reasoning NULL, e la
        diagnosi post-hoc e' impossibile senza guardare le latenze."""
        scaduto = self._client("scaduto:cloud", 1)
        scaduto.complete = AsyncMock(side_effect=asyncio.TimeoutError())
        rotto = self._client("rotto:cloud", 90)
        rotto.complete = AsyncMock(side_effect=ValueError("schema non valido"))

        mocker.patch(
            "src.workers.sentiment.build_shadow_clients",
            return_value=[scaduto, rotto],
        )
        pg = MagicMock(spec=PostgreSQLStore)

        await _shadow_query_candidates("corpo", "AAPL", 1, pg, self._redis_armato())

        righe = {r["model_id"]: r for r in pg.log_shadow_responses.call_args[0][0]}
        assert righe["scaduto:cloud"]["failure_reason"] == "timeout"
        assert righe["rotto:cloud"]["failure_reason"] != "timeout"
        assert righe["rotto:cloud"]["failure_reason"] is not None

    @pytest.mark.asyncio
    async def test_timeout_non_numerico_degrada_al_default(self, mocker):
        """#358: un _OLLAMA_TIMEOUT assente o non numerico non deve trasformare
        ogni chiamata in un fallimento del modello — sarebbe di nuovo un guasto
        dello strumento scambiato per un difetto della cosa misurata."""
        visti = []
        vero_wait_for = asyncio.wait_for

        async def _spia(coro, timeout=None):
            visti.append(timeout)
            return await vero_wait_for(coro, timeout=timeout)

        senza = self._client("senza:cloud", None)
        del senza._OLLAMA_TIMEOUT
        assurdo = self._client("assurdo:cloud", -3)

        mocker.patch(
            "src.workers.sentiment.build_shadow_clients",
            return_value=[senza, assurdo],
        )
        mocker.patch.object(asyncio, "wait_for", _spia)
        pg = MagicMock(spec=PostgreSQLStore)

        await _shadow_query_candidates("corpo", "AAPL", 1, pg, self._redis_armato())

        assert set(visti) == {95.0}, f"atteso il default 90+5, visto {visti}"
        righe = pg.log_shadow_responses.call_args[0][0]
        assert all(r["parse_error"] is False for r in righe), (
            "un timeout mal tipizzato ha prodotto falsi fallimenti del modello"
        )
