"""SentimentWorker — Celery task for LLM ensemble sentiment analysis.

Consumes news items from the Redis queue (news:queue) and produces sentiment
signals written to both Redis (TTL 4 h) and PostgreSQL for audit.

Pipeline per batch (up to 10 items pulled atomically via LMOVE):
  1. Crash recovery — re-queue any items stranded in news:processing from a
     previous crash (LMOVE is atomic; items are never lost, only delayed).
  2. Pre-filter — skip near-neutral MarketAux articles
     (|marketaux_sentiment| < 0.20) to save 60-80% of token spend.
  3. LLM ensemble — query Kimi K2.6, Qwen3.5, DeepSeek-V4-Pro, GLM-5.1 in
     parallel using DK-CoT prompting; aggregate with LOO ICIR weights if
     available, else confidence-weighted mean.
  4. Divergence fallback — if ensemble std > 0.30 (models disagree strongly)
     or budget is exhausted, fall back to FinBERT (local, zero cost).
  5. Store writes — signal → PostgreSQL (audit) and Redis (live cache);
     per-model LLM responses logged for LOO weight recalculation.
  6. Dead-letter — unparseable queue items moved to news:dead-letter to
     prevent infinite retry loops.

Exported public API (used by backtest CLI):
  run_inference()        Pure inference: no store writes, reusable in backtest.
  process_news_item()    Single item: inference + store writes.
  process_news_batch()   Batch: runs process_news_item() concurrently.
  run_sentiment_worker() Celery task entry point.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from src.config import config
from src.llm.budget import LLMBudgetExhaustedError, LLMBudgetTracker
from src.llm.client import LLMClient
from src.llm.ensemble import EnsembleAggregator, ModelOutput, run_ensemble_query
from src.llm.finbert import FinBERTClient
from src.models.news import LLMSentimentOutput, MarketAuxNewsItem, NewsItem
from src.models.signals import SentimentResult
from src.text.sanitizer import sanitize_text, sanitize_ticker

# Articles with |marketaux_sentiment| below this threshold are near-neutral.
# Skipping LLM inference on them saves 60-80% of token spend.
_MARKETAUX_NEUTRAL_THRESHOLD = 0.2
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
    weights: dict[str, float] | None = None,
) -> tuple[SentimentResult, list[ModelOutput]] | None:
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
    6. Return SentimentResult + raw_outputs (no Redis/PG writes)

    Why no store writes here?
      The live worker writes to Redis + PostgreSQL after receiving the result.
      The backtest CLI writes to backtest_signals via UPDATE. Keeping store
      logic outside run_inference makes it reusable for both contexts.
    """
    raw_symbol = item.asset_tags[0] if item.asset_tags else ""
    # Sanitize text BEFORE truncation to ensure proper handling of unicode/homoglyphs
    clean_body = sanitize_text(item.body or "")
    clean_symbol = sanitize_ticker(raw_symbol) if raw_symbol else "UNKNOWN"
    _body_limit = int(os.environ.get("SENTIMENT_LLM_BODY_CHARS", "600"))
    prompt = _DK_COT_PROMPT.format(text=clean_body[:_body_limit], symbol=clean_symbol)

    try:
        await budget_tracker.check_budget()

        raw_outputs = await run_ensemble_query(
            prompt=prompt,
            clients=clients,
            response_schema=LLMSentimentOutput,
            symbol=symbol,
        )

        aggregated = (
            aggregator.aggregate(raw_outputs, weights=weights) if raw_outputs else None
        )

        if aggregated is None:
            log.info(f"Ensemble diverged for {symbol}, using FinBERT fallback")
            loop = asyncio.get_running_loop()
            fb_result = await loop.run_in_executor(
                None, finbert.analyze, item.body[:512]
            )
            return SentimentResult(
                symbol=symbol,
                score=fb_result.polarity * fb_result.confidence,
                confidence=fb_result.confidence,
                reasoning="FinBERT fallback (ensemble divergence)",
                model_id="finbert",
                fallback_used=True,
            ), []

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
        ), raw_outputs

    except LLMBudgetExhaustedError:
        log.info(f"Budget exhausted for {symbol}, using FinBERT fallback")
        loop = asyncio.get_running_loop()
        fb_result = await loop.run_in_executor(None, finbert.analyze, item.body[:512])
        return SentimentResult(
            symbol=symbol,
            score=fb_result.polarity * fb_result.confidence,
            confidence=fb_result.confidence,
            reasoning="FinBERT fallback (budget exhausted)",
            model_id="finbert",
            fallback_used=True,
        ), []

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
    weights: dict[str, float] | None = None,
) -> SentimentResult | None:
    """Process a single news item: infer, update fallback counters, write to stores."""
    inference_result = await run_inference(
        item, clients, aggregator, finbert, budget_tracker, weights=weights
    )
    if inference_result is None:
        return None
    result, raw_outputs = inference_result
    try:
        ticker = result.symbol
        if result.fallback_used:
            redis_store.increment_fallback_counter()
        else:
            redis_store.reset_fallback_counter()
        signal_id = pg_store.write_signal(result)
        redis_store.write_sentiment(result, signal_id=signal_id)
        news_log_id = pg_store.log_news_item(
            item=item, ticker=ticker, computed_sentiment=result.score
        )
        if news_log_id is not None:
            pg_store.link_signal_to_news(signal_id=signal_id, news_log_id=news_log_id)
        if raw_outputs:
            pg_store.log_llm_responses(signal_id=signal_id, outputs=raw_outputs)
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
    weights: dict[str, float] | None = None,
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
        weights: Per-model weights from Redis (LOO ICIR rebalancing). None = confidence-only.

    Returns:
        List of SentimentResult objects
    """
    sem = asyncio.Semaphore(3)

    async def _bounded(item):
        async with sem:
            return await process_news_item(
                item=item,
                clients=clients,
                aggregator=aggregator,
                finbert=finbert,
                budget_tracker=budget_tracker,
                redis_store=redis_store,
                pg_store=pg_store,
                weights=weights,
            )

    gathered = await asyncio.gather(*[_bounded(item) for item in news_items])
    return [r for r in gathered if r is not None]


@app.task(name="src.workers.sentiment.run_sentiment_worker", acks_late=True)
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

    from src.llm.client import OllamaKimiClient, OllamaQwen35Client

    # Initialize connections
    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)
    redis_store = RedisStore(redis_client)
    pg_store = PostgreSQLStore(conn=pg_conn)

    # Initialize components — model selection read from Redis (set by UI toggle),
    # falling back to SENTIMENT_LLM_MODELS env var, then "all".
    # Accepted values (comma-separated subset of: kimi, qwen):
    #   "all"   → 2-model ensemble Kimi + Qwen (default, best quality/quota balance)
    #   "qwen"  → single model, saves 50% Ollama quota
    _redis_model_sel = redis_store.get_llm_models()
    _model_selection = (
        (_redis_model_sel or os.environ.get("SENTIMENT_LLM_MODELS", "all"))
        .lower()
        .split(",")
    )
    _all_clients = {
        "kimi": OllamaKimiClient(),
        "qwen": OllamaQwen35Client(),
    }
    if "all" in _model_selection:
        clients = list(_all_clients.values())
    else:
        clients = [
            _all_clients[k] for k in _model_selection if k in _all_clients
        ] or list(_all_clients.values())
    aggregator = EnsembleAggregator(
        min_confidence=config.ENSEMBLE_MIN_CONFIDENCE,
        divergence_threshold=config.ENSEMBLE_DIVERGENCE_STD,
    )
    finbert = FinBERTClient()
    # Warm up the pipeline in this (single-threaded) context before asyncio.run()
    # dispatches concurrent run_in_executor calls. transformers._LazyModule is not
    # thread-safe: concurrent 'from transformers import pipeline' calls corrupt the
    # module state, causing "Device set to use meta" and Tensor.item() failures.
    finbert._get_pipeline()
    budget_tracker = LLMBudgetTracker(conn=pg_conn)

    # Read per-model weights from Redis (set by weekly LOO ICIR rebalancing).
    # Primary key: "ensemble:weights:current" — only written when all auto-apply
    # guardrails pass (VIX, IC variance, weight delta). On a fresh deploy or
    # when the VIX key is absent, the guardrail fails and this key stays empty.
    # Fallback: use the most recent suggestion from run_weekly_weights() so
    # that LOO-rebalanced weights reach the ensemble even before formal approval.
    _raw_weights = redis_store.get_ensemble_weights()
    model_weights: dict[str, float] | None = None
    if _raw_weights:
        model_weights = json.loads(_raw_weights).get("weights")
    else:
        suggestion = redis_store.get_weight_suggestion()
        if suggestion:
            model_weights = suggestion.get("suggested_weights")
            if model_weights:
                log.info(
                    "Using suggestion weights (applied weights not yet set): %s",
                    {m: f"{w:.2f}" for m, w in model_weights.items()},
                )

    try:
        # Crash recovery: restore items from processing queue left by a previous crash.
        # LMOVE is atomic so partial crashes leave items in news:processing, not lost.
        stuck = redis_client.lrange("news:processing", 0, -1)
        if stuck:
            log.warning(
                "Recovering %d stuck items from news:processing into news:queue",
                len(stuck),
            )
            pipe = redis_client.pipeline()
            for item in stuck:
                pipe.rpush("news:queue", item)
            pipe.delete("news:processing")
            pipe.execute()

        # Pull batch using LMOVE (atomic: src LEFT → dst RIGHT).
        # Items are in news:processing until successfully written to stores,
        # so a crash does not lose them — next run's recovery block above re-queues them.
        news_items: list[NewsItem] = []
        raw_items: list[bytes] = []
        failed_raw: list[bytes] = []
        for _ in range(6):
            item_json = redis_client.lmove(
                "news:queue", "news:processing", "LEFT", "RIGHT"
            )
            if item_json is None:
                break
            raw_items.append(item_json)
            try:
                data = json.loads(item_json)
                if "marketaux_sentiment" in data:
                    news_items.append(MarketAuxNewsItem(**data))
                else:
                    news_items.append(NewsItem(**data))
            except (json.JSONDecodeError, Exception) as e:
                log.warning(f"Failed to parse news item from queue: {e}")
                failed_raw.append(item_json)

        # Move unparseable items to dead-letter queue — prevents infinite retry loop
        # where the recovery block keeps re-queuing corrupt items on every invocation.
        if failed_raw:
            pipe = redis_client.pipeline()
            for item in failed_raw:
                pipe.lrem("news:processing", 1, item)
                pipe.rpush("news:dead-letter", item)
            pipe.execute()
            log.warning(
                "Moved %d unparseable items to news:dead-letter", len(failed_raw)
            )

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
                weights=model_weights,
            )
        )

        # Count fallbacks
        fallback_count = sum(1 for r in results if r.fallback_used)

        # All items processed successfully — clear from processing queue
        if raw_items:
            redis_client.delete("news:processing")

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
