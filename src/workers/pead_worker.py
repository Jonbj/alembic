"""PEAD ingestion worker — classify SEC 8-K earnings filings for S7 strategy.

Task: run_pead_ingestion_worker()
Schedule: every 30 min, Mon-Fri 14:00-21:00 UTC (same as SEC EDGAR ingestion)

Pipeline:
    SECEdgarConnector (8-K only) → [dedup check] → LLM classify →
    EarningsSurpriseClassifier → SurpriseSignal → Redis (TTL 30d)

Only filings with asset_tags (watchlist tickers from SEC connector) are processed.
Each filing_id is marked in Redis to prevent duplicate LLM calls across restarts.
LLM failures are logged and skipped — worker continues to next filing.
"""

import asyncio
import logging

from src.config import config
from src.connectors.sec_edgar import SECEdgarConnector
from src.llm.client import OllamaKimiClient
from src.models.news import NewsItem
from src.models.pead import EarningsLLMOutput
from src.store.redis_store import RedisStore
from src.strategies.s7.signal import EarningsSurpriseClassifier
from src.workers._async_utils import run_async
from src.workers.celery_app import app

log = logging.getLogger(__name__)

_PEAD_PROMPT_TEMPLATE = """\
You are a buy-side equity analyst specializing in earnings analysis.

SEC 8-K filing text:
Title: {title}
Body: {body}

Analyze step-by-step:
1. Identify the ticker and filing type (earnings results, guidance update, or other)
2. Extract: EPS reported, EPS consensus (if present), revenue reported, revenue consensus
3. Calculate direction: beat / miss / inline / no_eps
4. Evaluate guidance: revised-up / revised-down / maintained / no-guidance
5. Assign confidence score [0, 1]

Output ONLY valid JSON:
{{
  "ticker": "<symbol from the filing or asset_tags>",
  "filing_type": "earnings_8k"|"guidance"|"other",
  "eps_actual": <float or null>,
  "eps_consensus": <float or null>,
  "surprise_pct": <float or null>,
  "direction": "beat"|"miss"|"inline"|"no_eps",
  "guidance": "revised-up"|"revised-down"|"maintained"|"no-guidance",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}}"""


async def _classify_filing(item: NewsItem, ticker: str) -> EarningsLLMOutput:
    """Call LLM to classify an 8-K filing. Raises on failure."""
    prompt = _PEAD_PROMPT_TEMPLATE.format(
        title=item.title,
        body=item.body[:2000],  # truncate to avoid token limits
    )
    client = OllamaKimiClient()
    result = await client.complete(prompt, EarningsLLMOutput)
    # Override ticker from asset_tags (more reliable than LLM extraction)
    return result.model_copy(update={"ticker": ticker})


async def _fetch_8k_items(connector: SECEdgarConnector) -> list[NewsItem]:
    return [item async for item in connector.fetch()]


@app.task(name="src.workers.pead_worker.run_pead_ingestion_worker")
def run_pead_ingestion_worker() -> dict:
    """Classify fresh 8-K filings and store PEAD signals in Redis.

    Returns stats dict: {processed, signals_written, skipped_dup, errors}.
    """
    redis = RedisStore()
    try:
        connector = SECEdgarConnector(form_types=["8-K"], max_results=40)
        classifier = EarningsSurpriseClassifier(
            surprise_threshold=config.PEAD_SURPRISE_THRESHOLD,
            min_confidence=config.PEAD_MIN_CONFIDENCE,
            hold_days=config.PEAD_HOLD_DAYS,
        )

        items: list[NewsItem] = run_async(_fetch_8k_items(connector))

        stats = {"processed": 0, "signals_written": 0, "skipped_dup": 0, "errors": 0}

        for item in items:
            if not item.asset_tags:
                continue  # no ticker identified → skip

            ticker = item.asset_tags[0]
            filing_id = item.id or f"{item.url}:{ticker}"

            if redis.is_pead_processed(filing_id):
                stats["skipped_dup"] += 1
                continue

            try:
                llm_out: EarningsLLMOutput = run_async(_classify_filing(item, ticker))
            except Exception as exc:
                log.warning("PEAD LLM classification failed for %s (%s): %s", ticker, filing_id, exc)
                stats["errors"] += 1
                continue

            from datetime import datetime, timezone
            signal = classifier.to_signal(llm_out, filing_id=filing_id, detected_at=item.timestamp or datetime.now(timezone.utc))

            if signal is not None:
                redis.write_pead_signal(signal, ttl=config.PEAD_REDIS_TTL_SECONDS)
                stats["signals_written"] += 1
                log.info("PEAD signal stored: %s %s (%.1f%% surprise, conf=%.2f)",
                         signal.symbol, signal.direction, signal.surprise_pct * 100, signal.confidence)

            redis.mark_pead_processed(filing_id, ttl=config.PEAD_REDIS_TTL_SECONDS)
            stats["processed"] += 1

        log.info("PEAD worker stats: %s", stats)
        return stats

    except Exception as exc:
        log.error("PEAD worker failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        redis.close()
