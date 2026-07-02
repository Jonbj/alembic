"""Earnings-surprise PEAD worker — the fuel for S7.

S7 (PEAD) was starved: the old path asked the LLM to extract the analyst consensus from
the 8-K text (where it is NOT present) → surprise_pct=None → no signal ever. This worker
computes the surprise from a structured source (Finnhub earnings calendar: actual vs
estimate EPS), deterministically, and writes SurpriseSignals to Redis for S7.

Offline, no LLM, no order path. S7 stays enabled=false / promotion_blocked, so signals
populate Redis for backtest/validation but do NOT trade until S7 is promoted.

The 8-K/transcript LLM guidance-tone layer (the qualitative edge) is a separate future
enrichment on top of this — not needed to give S7 fuel.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.config import config
from src.connectors.earnings_calendar import EarningsCalendarProvider, EarningsEvent
from src.models.pead import EarningsLLMOutput
from src.store.redis_store import RedisStore
from src.strategies.s7.signal import EarningsSurpriseClassifier
from src.workers.celery_app import app

log = logging.getLogger(__name__)

# Only signal on earnings reported within this window (the PEAD entry horizon).
_ENTRY_WINDOW_DAYS = 2


def _to_llm_output(ev: EarningsEvent, threshold: float) -> EarningsLLMOutput:
    """Adapt a structured earnings event to EarningsLLMOutput so the existing
    EarningsSurpriseClassifier gates (threshold/direction/confidence) apply unchanged."""
    surprise = ev.surprise_pct
    if surprise is None:
        direction = "no_eps"
    elif surprise >= threshold:
        direction = "beat"
    elif surprise <= -threshold:
        direction = "miss"
    else:
        direction = "inline"
    return EarningsLLMOutput(
        ticker=ev.symbol,
        filing_type="earnings_8k",
        eps_actual=ev.eps_actual,
        eps_consensus=ev.eps_estimate,
        surprise_pct=surprise,
        direction=direction,  # type: ignore[arg-type]
        confidence=0.95,  # structured data → high confidence in the number
        reasoning=f"Finnhub earnings: actual {ev.eps_actual} vs estimate {ev.eps_estimate}",
    )


@app.task(name="src.workers.earnings_pead_worker.run_earnings_pead_worker")
def run_earnings_pead_worker() -> dict:
    """Fetch recent earnings, compute surprise, write S7 SurpriseSignals to Redis."""
    if not config.FINNHUB_API_KEY:
        return {"skipped": True, "reason": "no_finnhub_key"}

    stats = {"events": 0, "watchlist_reported": 0, "signals_written": 0,
             "skipped_dup": 0, "below_threshold": 0}
    redis = RedisStore()
    try:
        today = datetime.now(timezone.utc).date()
        frm = (today - timedelta(days=_ENTRY_WINDOW_DAYS)).isoformat()
        to = today.isoformat()

        provider = EarningsCalendarProvider(api_key=config.FINNHUB_API_KEY)
        events = asyncio.run(provider.fetch(frm, to))
        stats["events"] = len(events)

        watchlist = {s.upper() for s in (config.WATCHLIST_SYMBOLS or [])}
        classifier = EarningsSurpriseClassifier(
            surprise_threshold=config.PEAD_SURPRISE_THRESHOLD,
            min_confidence=config.PEAD_MIN_CONFIDENCE,
            hold_days=config.PEAD_HOLD_DAYS,
        )

        for ev in events:
            if ev.symbol not in watchlist or ev.surprise_pct is None:
                continue
            stats["watchlist_reported"] += 1

            filing_id = f"finnhub-earnings:{ev.symbol}:{ev.date}"
            if redis.is_pead_processed(filing_id):
                stats["skipped_dup"] += 1
                continue

            try:
                detected_at = datetime.strptime(ev.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                detected_at = datetime.now(timezone.utc)

            llm_out = _to_llm_output(ev, config.PEAD_SURPRISE_THRESHOLD)
            signal = classifier.to_signal(llm_out, filing_id=filing_id, detected_at=detected_at)
            if signal is not None:
                redis.write_pead_signal(signal, ttl=config.PEAD_REDIS_TTL_SECONDS)
                stats["signals_written"] += 1
                log.info(
                    "PEAD (earnings) signal: %s %s (%.1f%% surprise, actual %s vs est %s)",
                    signal.symbol, signal.direction, signal.surprise_pct * 100,
                    ev.eps_actual, ev.eps_estimate,
                )
            else:
                stats["below_threshold"] += 1
            redis.mark_pead_processed(filing_id, ttl=config.PEAD_REDIS_TTL_SECONDS)

        log.info("Earnings PEAD worker stats: %s", stats)
        return stats
    except Exception as exc:
        log.error("Earnings PEAD worker failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        redis.close()
