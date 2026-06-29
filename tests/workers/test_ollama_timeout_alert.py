"""Tests for Ollama timeout detection and Telegram alert.

When all ensemble models fail with semaphore timeout (raw_outputs=[]),
we distinguish this from genuine ensemble divergence and emit a rate-limited
Telegram notification so the operator knows Ollama needs attention.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.news import NewsItem
from src.models.signals import SentimentResult


def _make_news_item(symbol: str = "MS") -> NewsItem:
    return NewsItem(
        id="test-001",
        title="Test article",
        body="Company reported strong earnings.",
        asset_tags=[symbol],
    )


def _make_finbert_result(polarity: float = 0.6, confidence: float = 0.8):
    r = MagicMock()
    r.polarity = polarity
    r.confidence = confidence
    return r


class TestRunInferenceOllamaTimeout:
    """run_inference must use 'Ollama timeout' reasoning when all models fail (empty raw_outputs)."""

    @pytest.mark.asyncio
    async def test_empty_raw_outputs_sets_ollama_timeout_reasoning(self):
        """When run_ensemble_query returns [] (all models timed out), reasoning must be 'Ollama timeout'."""
        from src.workers.sentiment import run_inference
        from src.llm.ensemble import EnsembleAggregator
        from src.llm.budget import LLMBudgetTracker

        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_finbert = MagicMock()
        mock_finbert.analyze.return_value = _make_finbert_result()
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value=None)

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_ensemble:
            mock_ensemble.return_value = []  # all models timed out

            result, raw_outputs = await run_inference(
                item=_make_news_item(),
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert result.fallback_used is True
        assert "Ollama timeout" in result.reasoning, (
            f"Expected 'Ollama timeout' in reasoning, got: {result.reasoning!r}"
        )
        assert raw_outputs == []

    @pytest.mark.asyncio
    async def test_diverged_raw_outputs_keeps_divergence_reasoning(self):
        """When models respond but disagree (aggregated=None), reasoning must still be 'divergence'."""
        from src.workers.sentiment import run_inference
        from src.llm.ensemble import EnsembleAggregator, ModelOutput
        from src.llm.budget import LLMBudgetTracker

        mock_aggregator = MagicMock(spec=EnsembleAggregator)
        mock_aggregator.aggregate.return_value = None  # diverged
        mock_finbert = MagicMock()
        mock_finbert.analyze.return_value = _make_finbert_result()
        mock_budget = AsyncMock(spec=LLMBudgetTracker)
        mock_budget.check_budget = AsyncMock(return_value=None)

        fake_output = ModelOutput(
            symbol="MS", model_id="kimi", polarity=0.8, confidence=0.9, reasoning="bullish"
        )

        with patch(
            "src.workers.sentiment.run_ensemble_query", new_callable=AsyncMock
        ) as mock_ensemble:
            mock_ensemble.return_value = [fake_output]  # model responded but diverged

            result, raw_outputs = await run_inference(
                item=_make_news_item(),
                clients=[],
                aggregator=mock_aggregator,
                finbert=mock_finbert,
                budget_tracker=mock_budget,
            )

        assert result.fallback_used is True
        assert "divergence" in result.reasoning.lower(), (
            f"Expected 'divergence' in reasoning for non-empty raw_outputs, got: {result.reasoning!r}"
        )


class TestOllamaTimeoutTelegramAlert:
    """run_sentiment_worker must send a rate-limited Telegram alert when all models time out."""

    def _make_result(self, reasoning: str, fallback_used: bool = True) -> SentimentResult:
        return SentimentResult(
            symbol="MS",
            score=0.25,
            confidence=0.8,
            reasoning=reasoning,
            model_id="finbert",
            fallback_used=fallback_used,
        )

    def test_timeout_alert_sent_when_all_items_are_ollama_timeout(self):
        """When all results have 'Ollama timeout' reasoning and no recent alert in Redis → send Telegram alert."""
        from src.workers.sentiment import _maybe_notify_ollama_timeout

        mock_redis = MagicMock()
        # SET NX returns True → key was set → cooldown not active → send alert
        mock_redis.set.return_value = True

        with patch("src.notifications.telegram.TelegramNotifier") as MockNotifier:
            notifier_instance = MockNotifier.return_value
            notifier_instance.send_alert = AsyncMock()

            _maybe_notify_ollama_timeout(mock_redis, timeout_count=3, total=3)

            notifier_instance.send_alert.assert_called_once()
            call_args = notifier_instance.send_alert.call_args
            message = call_args[0][0] if call_args[0] else call_args[1].get("message", "")
            assert "ollama" in message.lower() or "timeout" in message.lower()

    def test_timeout_alert_suppressed_during_cooldown(self):
        """If a recent alert was already sent (Redis key exists), do not send another one."""
        from src.workers.sentiment import _maybe_notify_ollama_timeout

        mock_redis = MagicMock()
        # SET NX returns False (None) → key already exists → cooldown active → suppress
        mock_redis.set.return_value = False

        with patch("src.notifications.telegram.TelegramNotifier") as MockNotifier:
            notifier_instance = MockNotifier.return_value
            notifier_instance.send_alert = AsyncMock()

            _maybe_notify_ollama_timeout(mock_redis, timeout_count=2, total=2)

            notifier_instance.send_alert.assert_not_called()

    def test_timeout_alert_not_sent_for_genuine_divergence(self):
        """When fallback is due to divergence (not timeout), no Telegram alert."""
        from src.workers.sentiment import _maybe_notify_ollama_timeout

        mock_redis = MagicMock()
        # Even if cooldown not active, zero timeout_count means no alert
        mock_redis.set.return_value = True

        with patch("src.notifications.telegram.TelegramNotifier") as MockNotifier:
            notifier_instance = MockNotifier.return_value
            notifier_instance.send_alert = AsyncMock()

            _maybe_notify_ollama_timeout(mock_redis, timeout_count=0, total=3)

            notifier_instance.send_alert.assert_not_called()
            # Should not even touch Redis if count=0
            mock_redis.set.assert_not_called()

    def test_telegram_error_does_not_crash_worker(self):
        """If TelegramNotifier.send_alert raises, the function must not propagate the exception."""
        from src.workers.sentiment import _maybe_notify_ollama_timeout

        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        with patch("src.notifications.telegram.TelegramNotifier") as MockNotifier:
            notifier_instance = MockNotifier.return_value
            notifier_instance.send_alert = AsyncMock(side_effect=Exception("Telegram down"))

            # Must not raise
            _maybe_notify_ollama_timeout(mock_redis, timeout_count=1, total=1)
