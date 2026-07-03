"""SentimentWorker — Celery task for LLM ensemble sentiment analysis.

Consumes news items from the Redis queue (news:queue) and produces sentiment
signals written to both Redis (TTL 4 h) and PostgreSQL for audit.

Pipeline per batch (up to 10 items pulled atomically via LMOVE):
  1. Crash recovery — re-queue any items stranded in news:processing from a
     previous crash (LMOVE is atomic; items are never lost, only delayed).
  2. Pre-filter — skip near-neutral MarketAux articles
     (|marketaux_sentiment| < 0.20) to save 60-80% of token spend.
  3. LLM ensemble — query Kimi K2.6, GLM-5.2 in
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
from datetime import datetime, timedelta, timezone

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
# Freshness: news older than this is skipped WITHOUT an LLM call. A news-driven signal
# is only useful while the news is recent (the trading cycle reads a 4h window); spending
# minutes/article on old news both wastes inference and, since the signal's generated_at
# is the processing time, injects stale sentiment as if it were fresh. Skipping also lets
# the worker drain a backlog fast (instant skip vs ~minutes/article).
# FIX-03: config-driven (MAX_NEWS_AGE_HOURS, default 2h). Editorial news older than this
# is priced in; tactical horizon is intraday. Previously a hardcoded 12h (cross-session
# leftovers from the prior day's 14-21 UTC ingestion window were skipped so each market
# open started on that day's news) — tightened per the event-time freshness gate.
_SENTIMENT_MAX_NEWS_AGE_HOURS = config.MAX_NEWS_AGE_HOURS
# Cap on items scanned per run while skipping stale ones (bounds one task; a large stale
# backlog drains over a few runs rather than holding everything in news:processing at once).
_MAX_QUEUE_SCAN_PER_RUN = 5000
# Fresh items processed per run. Sized against the 15-min beat cadence: observed per-item
# latency is 25-70s, so 12 items at the batch semaphore's concurrency of 2 (see
# process_news_batch) fit comfortably inside one cycle instead of leaving the worker idle
# 70-90% of it. The old cap of 4 let fresh news outpace processing capacity, aging past
# the S4 strategy's 4h usability window before ever being scored (throughput bottleneck,
# DAY-2026-07-02).
_SENTIMENT_BATCH_SIZE = 12
# Single named row in the fallback_counters table (Postgres mirror of the Redis
# consecutive-fallback counter — kept in sync so the count survives a Redis flush
# and is queryable for audit/dashboards).
_FALLBACK_COUNTER_NAME = "consecutive_fallback"
# Resolver shadow (Fase A): compute + persist deterministic ticker resolution for
# measurement. Offline/fail-safe; never gates the signal. Disable via RESOLVER_SHADOW_ENABLED=0.
_RESOLVER_SHADOW_ENABLED = os.environ.get("RESOLVER_SHADOW_ENABLED", "1") != "0"
from src.store.pg_store import PostgreSQLStore


def _is_stale_news(item, now: datetime, max_age_hours: int = _SENTIMENT_MAX_NEWS_AGE_HOURS) -> bool:
    """True if the item's news timestamp is older than max_age_hours (tz-safe)."""
    ts = item.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts) > timedelta(hours=max_age_hours)
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

# Module-level FinBERT singleton — survives across task invocations in the same
# ForkPoolWorker process, eliminating the 108-242s reload on every sentiment run.
# None until first sentiment task; then persists for the lifetime of the process.
_finbert_singleton: FinBERTClient | None = None

# Worker version constant
WORKER_VERSION = "1.0.0"

# Domain Knowledge Chain-of-Thought prompt for sentiment analysis (design doc §9).
# Issuer-specific: assess the impact on THIS ticker only. The model produces signal
# features (polarity, materiality, event type, directness, risk flags) — never a
# trading action (no buy/sell/hold). Enriched fields feed the resolver and future
# score weighting; they are backward-compatible (defaults leave score unchanged).
_DK_COT_PROMPT = """You are a buy-side equity analyst. Assess this news item's impact on the SPECIFIC issuer below.

Think step-by-step:
1. What does this mean for THIS company's revenue, cash flows and competitive position?
2. Is the impact direct, or only an indirect read-through (customer/supplier/competitor/sector/macro)?
3. How material and how novel (not already priced in) is it? What is the bull/bear case?
4. What is your overall verdict?

Rules:
- Sentiment must be issuer-specific (about {symbol}, not the news in general).
- Do NOT output a trading action (no buy/sell/hold) — only the signal features below.
- Use only evidence in the article; if the market impact is unclear, set polarity=0, confidence low.

News: {text}
Ticker: {symbol}

Respond ONLY with valid JSON matching this schema:
{{"polarity": <float -1.0..1.0>, "confidence": <float 0.0..1.0>, "reasoning": "<bull/bear analysis, one sentence>", "event_type": "earnings|guidance|mna|regulatory|lawsuit|analyst_rating|product|management|macro|other", "directness": "direct|customer_supplier|competitor_readthrough|sector|macro|unclear", "materiality": <0.0..1.0>, "novelty": <0.0..1.0>, "risk_flags": ["rumor"|"already_priced_in"|"ambiguous_entity"|"low_source_quality"], "evidence_sentences": ["<key sentence>"]}}"""


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
    if not item.asset_tags:
        log.debug("Skipping news item with no asset_tags: %s", (item.url or "")[:80])
        return None
    raw_symbol = item.asset_tags[0]
    # Sanitize text BEFORE truncation to ensure proper handling of unicode/homoglyphs
    clean_body = sanitize_text(item.body or "")
    clean_symbol = sanitize_ticker(raw_symbol) if raw_symbol else "UNKNOWN"
    if clean_symbol == "UNKNOWN":
        log.debug("Skipping news item with unresolvable ticker (raw=%r)", raw_symbol)
        return None
    _body_limit = int(os.environ.get("SENTIMENT_LLM_BODY_CHARS", "600"))
    prompt = _DK_COT_PROMPT.format(text=clean_body[:_body_limit], symbol=clean_symbol)

    try:
        await budget_tracker.check_budget()

        raw_outputs = await run_ensemble_query(
            prompt=prompt,
            clients=clients,
            response_schema=LLMSentimentOutput,
            symbol=clean_symbol,
        )

        all_models_timed_out = not raw_outputs
        aggregated = (
            aggregator.aggregate(raw_outputs, weights=weights) if raw_outputs else None
        )

        if aggregated is None:
            if all_models_timed_out:
                fallback_reason = "FinBERT fallback (Ollama timeout)"
                log.info(f"All ensemble models timed out for {clean_symbol}, using FinBERT fallback")
            else:
                fallback_reason = "FinBERT fallback (ensemble divergence)"
                log.info(f"Ensemble diverged for {clean_symbol}, using FinBERT fallback")
            loop = asyncio.get_running_loop()
            fb_result = await loop.run_in_executor(
                None, finbert.analyze, clean_body[:512]
            )
            return SentimentResult(
                symbol=clean_symbol,
                score=fb_result.polarity * fb_result.confidence,
                confidence=fb_result.confidence,
                reasoning=fallback_reason,
                model_id="finbert",
                fallback_used=True,
                published_at=item.timestamp,
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
            symbol=clean_symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=aggregated.confidence,
            reasoning=aggregated.reasoning,
            model_id=f"ensemble:{'+'.join(aggregated.model_ids)}",
            ensemble_std=aggregated.ensemble_std,
            fallback_used=False,
            published_at=item.timestamp,
        ), raw_outputs

    except LLMBudgetExhaustedError:
        log.info(f"Budget exhausted for {clean_symbol}, using FinBERT fallback")
        loop = asyncio.get_running_loop()
        fb_result = await loop.run_in_executor(None, finbert.analyze, clean_body[:512])
        return SentimentResult(
            symbol=clean_symbol,
            score=fb_result.polarity * fb_result.confidence,
            confidence=fb_result.confidence,
            reasoning="FinBERT fallback (budget exhausted)",
            model_id="finbert",
            fallback_used=True,
            published_at=item.timestamp,
        ), []

    except Exception as e:
        log.error(f"Error processing news item for {clean_symbol}: {e}")
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
            count = redis_store.increment_fallback_counter()
            pg_store.record_fallback_increment(_FALLBACK_COUNTER_NAME, count)
        else:
            redis_store.reset_fallback_counter()
            pg_store.record_fallback_reset(_FALLBACK_COUNTER_NAME)
        signal_id = pg_store.write_signal(result)
        redis_store.write_sentiment(result, signal_id=signal_id)
        try:
            redis_store.append_signal_history(result.symbol, result.score)
        except Exception as _vh_exc:
            log.debug("Could not append signal history for %s: %s", result.symbol, _vh_exc)
        news_log_id = pg_store.log_news_item(
            item=item, ticker=ticker, computed_sentiment=result.score
        )
        if news_log_id is not None:
            pg_store.link_signal_to_news(signal_id=signal_id, news_log_id=news_log_id)
        else:
            # ON CONFLICT (url, ticker) DO NOTHING returned None — article already in
            # news_log from a previous fetch. Signal will have news_log_id = NULL.
            # High NULL rate breaks signal auditability; monitor with:
            #   SELECT COUNT(*)-COUNT(news_log_id) FROM sentiment_signals WHERE generated_at > now()-'1h'::interval
            log.debug("news_log_id NULL for signal %s/%s (url conflict or empty url)", ticker, signal_id)
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
    # 2, not 1: each item's own ensemble call already bounds itself to the 2 global
    # Ollama semaphore slots (client.py _OLLAMA_SEM_SLOTS), so this doesn't add pressure
    # beyond that ceiling — it just lets one item's store writes/aggregation overlap
    # with the next item's Ollama round-trip instead of leaving the worker fully idle
    # between items.
    sem = asyncio.Semaphore(2)

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


_OLLAMA_TIMEOUT_ALERT_KEY = "ollama:timeout_alert:last_sent"
_OLLAMA_TIMEOUT_ALERT_COOLDOWN_S = 1800  # one alert per 30 minutes max

_OLLAMA_SEM_KEY = "ollama:sem"
_OLLAMA_SEM_INIT_KEY = "ollama:sem:init"


def _recover_ollama_semaphore_if_leaked(redis_client) -> None:
    """Reset the Ollama semaphore if all slots have been leaked by a killed task.

    Safe to call at task startup: worker-inference has concurrency=1, so a
    starting task is guaranteed to be the only live holder — any prior task
    that leaked tokens has already terminated.

    Only resets when LLEN==0 AND init flag is set (semaphore was ever initialized).
    Partial leaks (1-2 slots missing) are left alone to avoid false positives.
    """
    try:
        slots = redis_client.llen(_OLLAMA_SEM_KEY)
        init_exists = redis_client.exists(_OLLAMA_SEM_INIT_KEY)
        if init_exists and slots == 0:
            log.warning(
                "Ollama semaphore exhausted (0 slots) — auto-recovering leaked tokens "
                "(safe: worker-inference concurrency=1 guarantees no concurrent holder)"
            )
            redis_client.delete(_OLLAMA_SEM_KEY, _OLLAMA_SEM_INIT_KEY)
    except Exception as exc:
        log.warning("_recover_ollama_semaphore_if_leaked: Redis error (%s) — skipping", exc)


def _maybe_notify_ollama_timeout(redis_client, timeout_count: int, total: int) -> None:
    """Send a rate-limited Telegram alert when all ensemble models time out.

    Uses Redis SET NX with TTL as the cooldown gate — at most one alert per 30 min.
    Silently swallows any Telegram errors to avoid crashing the worker.
    """
    if timeout_count == 0:
        return
    if not redis_client.set(
        _OLLAMA_TIMEOUT_ALERT_KEY, "1", nx=True, ex=_OLLAMA_TIMEOUT_ALERT_COOLDOWN_S
    ):
        return  # cooldown active: suppress duplicate alert
    try:
        from src.notifications.telegram import TelegramNotifier
        from src.notifications.base import AlertLevel

        notifier = TelegramNotifier()
        asyncio.run(
            notifier.send_alert(
                f"Ollama timeout: tutti i modelli LLM non disponibili "
                f"({timeout_count}/{total} news → FinBERT fallback). "
                f"Se persiste: docker exec alembic-redis-1 redis-cli DEL ollama:sem ollama:sem:init",
                level=AlertLevel.WARNING,
            )
        )
    except Exception as exc:
        log.warning("Failed to send Ollama timeout Telegram alert: %s", exc)


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

    from src.llm.model_registry import (
        build_sentiment_clients,
        model_ids_for_keys,
        normalize_model_selection,
        normalize_weights_for_active_models,
    )

    # Initialize connections
    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)
    redis_store = RedisStore(redis_client)
    pg_store = PostgreSQLStore(conn=pg_conn)

    # Initialize components — model selection read from Redis (set by UI toggle),
    # falling back to SENTIMENT_LLM_MODELS env var, then "all".
    _redis_model_sel = redis_store.get_llm_models()
    _canonical_selection, _model_keys, _invalid_models = normalize_model_selection(
        _redis_model_sel or os.environ.get("SENTIMENT_LLM_MODELS", "all")
    )
    if _invalid_models:
        log.warning(
            "Ignoring invalid sentiment model selection tokens: %s",
            _invalid_models,
        )
    clients = build_sentiment_clients(_model_keys)
    active_model_ids = model_ids_for_keys(_model_keys)
    aggregator = EnsembleAggregator(
        min_confidence=config.ENSEMBLE_MIN_CONFIDENCE,
        divergence_threshold=config.ENSEMBLE_DIVERGENCE_STD,
    )
    global _finbert_singleton
    if _finbert_singleton is None:
        # First call in this worker process: create and warm up the pipeline.
        # Must happen in this single-threaded context before asyncio.run() dispatches
        # concurrent run_in_executor calls — transformers._LazyModule is not thread-safe.
        _finbert_singleton = FinBERTClient()
        _finbert_singleton._get_pipeline()
        log.info("FinBERT singleton initialized for this worker process")
    finbert = _finbert_singleton
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
        raw_model_weights = json.loads(_raw_weights).get("weights")
        model_weights, dropped_weights = normalize_weights_for_active_models(
            raw_model_weights,
            active_model_ids,
        )
        if dropped_weights:
            log.warning(
                "Ignoring weights for inactive sentiment models: %s",
                dropped_weights,
            )
    else:
        suggestion = redis_store.get_weight_suggestion()
        if suggestion:
            model_weights, dropped_weights = normalize_weights_for_active_models(
                suggestion.get("suggested_weights"),
                active_model_ids,
            )
            if model_weights:
                log.info(
                    "Using suggestion weights (applied weights not yet set): %s",
                    {m: f"{w:.2f}" for m, w in model_weights.items()},
                )
            if dropped_weights:
                log.warning(
                    "Ignoring suggested weights for inactive sentiment models: %s",
                    dropped_weights,
                )

    try:
        # Semaphore auto-recovery: reset leaked slots before any inference starts.
        _recover_ollama_semaphore_if_leaked(redis_client)

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
        skipped_stale = 0
        _now = datetime.now(timezone.utc)
        # Pull until _SENTIMENT_BATCH_SIZE FRESH items (or queue empty / scan cap). Stale
        # items are skipped without an LLM call and left in news:processing → discarded by
        # the delete() at run end. This drains a backlog of old news fast instead of
        # generating stale-but-"fresh"-timestamped signals on it.
        scanned = 0
        while len(news_items) < _SENTIMENT_BATCH_SIZE and scanned < _MAX_QUEUE_SCAN_PER_RUN:
            item_json = redis_client.lmove(
                "news:queue", "news:processing", "LEFT", "RIGHT"
            )
            if item_json is None:
                break
            scanned += 1
            raw_items.append(item_json)
            try:
                data = json.loads(item_json)
                item = (
                    MarketAuxNewsItem(**data)
                    if "marketaux_sentiment" in data
                    else NewsItem(**data)
                )
            except (json.JSONDecodeError, Exception) as e:
                log.warning(f"Failed to parse news item from queue: {e}")
                failed_raw.append(item_json)
                continue
            if _is_stale_news(item, _now):
                skipped_stale += 1
                continue
            news_items.append(item)
        if skipped_stale:
            log.info(
                "Skipped %d stale news items (> %dh old) without inference",
                skipped_stale, _SENTIMENT_MAX_NEWS_AGE_HOURS,
            )

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
            # No fresh items this run. If we scanned (and skipped stale) items, discard
            # them from news:processing so the crash-recovery block does NOT re-queue them
            # — otherwise a stale backlog would loop forever instead of draining.
            if raw_items:
                redis_client.delete("news:processing")
            return {
                "processed": 0,
                "reason": "no_items_in_queue",
                "skipped_stale": skipped_stale,
            }

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

        # Resolver SHADOW (Fase A): persist deterministic ticker resolution for each item
        # to news_resolved_entities so resolver precision can be measured vs news_labels.
        # Offline + fail-safe — does NOT affect the signal just written.
        if _RESOLVER_SHADOW_ENABLED and items_to_process:
            try:
                from src.connectors.resolver_shadow import resolve_and_log_shadow
                resolve_and_log_shadow(items_to_process, pg_store)
            except Exception as exc:
                log.warning("resolver shadow batch failed: %s", exc)

        # Count fallbacks — distinguish Ollama timeout from ensemble divergence
        fallback_count = sum(1 for r in results if r.fallback_used)
        ollama_timeout_count = sum(
            1 for r in results if r.reasoning == "FinBERT fallback (Ollama timeout)"
        )
        if ollama_timeout_count > 0:
            _maybe_notify_ollama_timeout(
                redis_client,
                timeout_count=ollama_timeout_count,
                total=len(items_to_process),
            )

        # All items processed successfully — clear from processing queue
        if raw_items:
            redis_client.delete("news:processing")

        return {
            "processed": len(results),
            "ensemble_success": len(results) - fallback_count,
            "finbert_fallbacks": fallback_count,
            "skipped_neutral": skipped_neutral,
            "skipped_stale": skipped_stale,
            "symbols": list(set(r.symbol for r in results)),
        }

    finally:
        # Cleanup
        budget_tracker.close()
        redis_store.close()
        pg_store.close()
        redis_client.close()
        pg_conn.close()
