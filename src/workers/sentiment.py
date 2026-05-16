"""SentimentWorker - Celery task for LLM ensemble sentiment analysis."""

import asyncio
import logging
from datetime import datetime, timezone

from src.config import config
from src.llm.budget import LLMBudgetExhaustedError, LLMBudgetTracker
from src.llm.client import LLMClient
from src.llm.ensemble import EnsembleAggregator, ModelOutput, run_ensemble_query
from src.llm.finbert import FinBERTClient
from src.models.news import LLMSentimentOutput, MarketAuxNewsItem, NewsItem

# Articles with |marketaux_sentiment| below this threshold are near-neutral.
# Skipping LLM inference on them saves 60-80% of token spend.
_MARKETAUX_NEUTRAL_THRESHOLD = 0.2
from src.models.signals import SentimentResult
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

# Worker version constant
WORKER_VERSION = "1.0.0"

# Domain Knowledge Chain-of-Thought prompt for sentiment analysis
_DK_COT_PROMPT = """You are a buy-side equity analyst. Analyze the following news item and provide a sentiment assessment.

Think step-by-step:
1. What does this mean for the company's revenue and cash flows?
2. How does this compare to competitor performance?
3. What is the bull case? What is the bear case?
4. What is your overall verdict?

News: {text}
Ticker: {symbol}

Respond ONLY with valid JSON matching this schema:
{{"polarity": <float -1.0 to 1.0>, "confidence": <float 0.0 to 1.0>, "reasoning": "<bull/bear analysis in one sentence>"}}"""


async def run_inference(
    item: NewsItem,
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: LLMBudgetTracker,
) -> SentimentResult | None:
    """Core LLM inference — no store writes. Callable from live worker and backtest.

    Why extracted as a standalone function?
      The live SentimentWorker (Celery) and the backtest CLI both need the exact
      same inference logic (ensemble → aggregate → fallback). By extracting
      run_inference(), we guarantee the backtest validates the *production*
      pipeline, not a simplified version.

    Flow:
    1. Check budget BEFORE calling LLM ensemble
    2. If budget exhausted, fall back to FinBERT immediately
    3. Run ensemble query (models in parallel)
    4. Aggregate; if divergence (aggregate returns None), fall back to FinBERT
    5. Record spending for successful LLM calls
    6. Return SentimentResult (no Redis/PG writes)

    Why no store writes here?
      The live worker writes to Redis + PostgreSQL after receiving the result.
      The backtest CLI writes to backtest_signals via UPDATE. Keeping store
      logic outside run_inference makes it reusable for both contexts.
    """
    symbol = item.asset_tags[0] if item.asset_tags else "UNKNOWN"
    prompt = _DK_COT_PROMPT.format(text=item.body[:2000], symbol=symbol)

    try:
        await budget_tracker.check_budget()

        raw_outputs = await run_ensemble_query(
            prompt=prompt,
            clients=clients,
            response_schema=LLMSentimentOutput,
            symbol=symbol,
        )

        aggregated = aggregator.aggregate(raw_outputs) if raw_outputs else None

        if aggregated is None:
            log.info(f"Ensemble diverged for {symbol}, using FinBERT fallback")
            fb_result = finbert.analyze(item.body[:512])
            return SentimentResult(
                symbol=symbol,
                score=fb_result.polarity * fb_result.confidence,
                confidence=fb_result.confidence,
                reasoning="FinBERT fallback (ensemble divergence)",
                model_id="finbert",
                fallback_used=True,
            )

        score = aggregated.polarity * aggregated.confidence
        # Rough token estimate: ~4 chars per token (English text average).
        input_tokens = len(prompt) // 4
        output_tokens = len(aggregated.reasoning) // 4
        for model_id in aggregated.model_ids:
            try:
                await budget_tracker.record_spending(
                    model_id=model_id,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            except Exception as e:
                log.warning(f"Failed to record spending for {model_id}: {e}")

        return SentimentResult(
            symbol=symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=aggregated.confidence,
            reasoning=aggregated.reasoning,
            model_id=f"ensemble:{'+'.join(aggregated.model_ids)}",
            ensemble_std=aggregated.ensemble_std,
            fallback_used=False,
        )

    except LLMBudgetExhaustedError:
        log.info(f"Budget exhausted for {symbol}, using FinBERT fallback")
        fb_result = finbert.analyze(item.body[:512])
        return SentimentResult(
            symbol=symbol,
            score=fb_result.polarity * fb_result.confidence,
            confidence=fb_result.confidence,
            reasoning="FinBERT fallback (budget exhausted)",
            model_id="finbert",
            fallback_used=True,
        )

    except Exception as e:
        log.error(f"Error processing news item for {symbol}: {e}")
        return None


async def process_news_item(
    item: NewsItem,
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: LLMBudgetTracker,
    redis_store: RedisStore,
    pg_store: PostgreSQLStore,
) -> SentimentResult | None:
    """Process a single news item: infer, update fallback counters, write to stores."""
    result = await run_inference(item, clients, aggregator, finbert, budget_tracker)

    if result is not None:
        try:
            if result.fallback_used:
                redis_store.increment_fallback_counter()
            else:
                redis_store.reset_fallback_counter()
            redis_store.write_sentiment(result)
            pg_store.write_signal(result)
        except Exception as e:
            log.error(f"Failed to write signal for {result.symbol}: {e}")

    return result


async def process_news_batch(
    news_items: list[NewsItem],
    clients: list[LLMClient],
    aggregator: EnsembleAggregator,
    finbert: FinBERTClient,
    budget_tracker: LLMBudgetTracker,
    redis_store: RedisStore,
    pg_store: PostgreSQLStore,
) -> list[SentimentResult]:
    """
    Process a batch of news items through the sentiment pipeline.

    Args:
        news_items: List of news items to process
        clients: List of LLM clients for ensemble
        aggregator: Ensemble aggregator
        finbert: FinBERT fallback client
        budget_tracker: Budget tracker for cost enforcement
        redis_store: Redis store for signal caching
        pg_store: PostgreSQL store for audit

    Returns:
        List of SentimentResult objects
    """
    results: list[SentimentResult] = []

    for item in news_items:
        result = await process_news_item(
            item=item,
            clients=clients,
            aggregator=aggregator,
            finbert=finbert,
            budget_tracker=budget_tracker,
            redis_store=redis_store,
            pg_store=pg_store,
        )
        if result is not None:
            results.append(result)

    return results


@app.task(name="src.workers.sentiment.run_sentiment_worker")
def run_sentiment_worker() -> dict:
    """
    Celery entry-point for SentimentWorker.

    Pulls news items from Redis queue, runs sentiment pipeline,
    and writes results to Redis cache and PostgreSQL audit.

    Returns:
        Dict with processing statistics
    """
    import json

    import psycopg2
    from redis import Redis

    from src.llm.client import DeepseekClient, OpusClient, Qwen35Client

    # Initialize connections
    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)

    # Initialize components
    clients = [OpusClient(), Qwen35Client(), DeepseekClient()]
    aggregator = EnsembleAggregator(
        min_confidence=config.ENSEMBLE_MIN_CONFIDENCE,
        divergence_threshold=config.ENSEMBLE_DIVERGENCE_STD,
    )
    finbert = FinBERTClient()
    budget_tracker = LLMBudgetTracker(conn=pg_conn)
    redis_store = RedisStore(redis_client)
    pg_store = PostgreSQLStore(conn=pg_conn)

    try:
        # Pull batch from Redis queue (up to 10 items)
        news_items: list[NewsItem] = []
        for _ in range(10):
            item_json = redis_client.lpop("news:queue")
            if item_json is None:
                break
            try:
                data = json.loads(item_json)
                if "marketaux_sentiment" in data:
                    news_items.append(MarketAuxNewsItem(**data))
                else:
                    news_items.append(NewsItem(**data))
            except (json.JSONDecodeError, Exception) as e:
                log.warning(f"Failed to parse news item from queue: {e}")

        if not news_items:
            return {"processed": 0, "reason": "no_items_in_queue"}

        # Pre-filter: skip near-neutral MarketAux articles before LLM inference.
        # This saves 60-80% of token spend on articles that are unlikely to
        # produce a tradeable signal.
        skipped_neutral = 0
        items_to_process: list[NewsItem] = []
        for item in news_items:
            if (
                isinstance(item, MarketAuxNewsItem)
                and item.marketaux_sentiment is not None
                and abs(item.marketaux_sentiment) < _MARKETAUX_NEUTRAL_THRESHOLD
            ):
                skipped_neutral += 1
                log.debug(
                    "Skipping neutral MarketAux article (sentiment=%.3f): %s",
                    item.marketaux_sentiment,
                    item.title[:60],
                )
            else:
                items_to_process.append(item)

        # Process batch
        results = asyncio.run(
            process_news_batch(
                news_items=items_to_process,
                clients=clients,
                aggregator=aggregator,
                finbert=finbert,
                budget_tracker=budget_tracker,
                redis_store=redis_store,
                pg_store=pg_store,
            )
        )

        # Count fallbacks
        fallback_count = sum(1 for r in results if r.fallback_used)

        return {
            "processed": len(results),
            "ensemble_success": len(results) - fallback_count,
            "finbert_fallbacks": fallback_count,
            "skipped_neutral": skipped_neutral,
            "symbols": list(set(r.symbol for r in results)),
        }

    finally:
        # Cleanup
        budget_tracker.close()
        redis_store.close()
        pg_store.close()
        redis_client.close()
        pg_conn.close()
