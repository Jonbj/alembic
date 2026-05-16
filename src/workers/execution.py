"""ExecutionWorker — reads LLM signals from Redis and places orders via Alpaca.

Runs as a Celery beat task every 15 min during market hours. For each symbol
in WATCHLIST_SYMBOLS:

  1. Check kill-switch (halt immediately if active).
  2. Read signal from Redis (signal:{symbol}:sentiment, TTL 4h).
  3. Skip if signal is stale (> SIGNAL_MAX_AGE_MIN minutes old).
  4. Check existing position — idempotent, no pyramiding.
  5. If score > ENTRY_THRESHOLD and no position: place market order.
     Position size = portfolio_value × MAX_POSITION_PCT × regime_multiplier.
  6. Check stop-loss on all open positions.

Why Celery task instead of QC Lean?
  QC Lean requires historical price data and a QC account. For paper trading
  validation during development, a direct Alpaca SDK integration is simpler
  and runs entirely within the existing stack.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from redis import Redis

from src.config import config
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

ENTRY_THRESHOLD = 0.3
MAX_POSITION_PCT = 0.10
STOP_LOSS_PCT = 0.02
SIGNAL_MAX_AGE_MIN = 30


def _is_fresh(signal: dict) -> bool:
    """Return True if signal was generated within SIGNAL_MAX_AGE_MIN minutes."""
    generated_at = signal.get("generated_at") or signal.get("timestamp")
    if not generated_at:
        return False
    try:
        ts = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        return age_min <= SIGNAL_MAX_AGE_MIN
    except (ValueError, TypeError):
        return False


def _regime_multiplier(redis_store: RedisStore) -> float:
    """Return regime multiplier from Redis (default 1.0 if absent)."""
    regime = redis_store.get_regime()
    if regime is None:
        return 1.0
    return float(regime.multiplier)


def run_execution_cycle(
    symbols: list[str],
    redis_store: RedisStore,
    trading_client,
) -> dict:
    """Core execution logic — separated for testability.

    Args:
        symbols:        List of ticker symbols to evaluate.
        redis_store:    RedisStore instance (connected).
        trading_client: Alpaca TradingClient instance.

    Returns:
        Stats dict: checked, skipped_stale, skipped_killswitch, skipped_position,
                    orders_placed, stop_losses_triggered, errors.
    """
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    stats = {
        "checked": 0,
        "skipped_stale": 0,
        "skipped_killswitch": 0,
        "skipped_position": 0,
        "orders_placed": 0,
        "stop_losses_triggered": 0,
        "errors": 0,
    }

    # Kill-switch check — halt all trading if active
    if redis_store.is_killswitch_active():
        log.warning("Kill-switch active — execution worker halted")
        stats["skipped_killswitch"] = len(symbols)
        return stats

    regime_mult = _regime_multiplier(redis_store)

    # Fetch current account + positions once (not per symbol)
    try:
        account = trading_client.get_account()
        portfolio_value = float(account.portfolio_value)
        open_positions = {
            p.symbol: p for p in trading_client.get_all_positions()
        }
    except Exception as e:
        log.error("Failed to fetch account/positions from Alpaca: %s", e)
        stats["errors"] += 1
        return stats

    for symbol in symbols:
        stats["checked"] += 1
        try:
            # --- Signal read ---
            signal = redis_store.read_sentiment(symbol)
            if signal is None or not _is_fresh(signal):
                stats["skipped_stale"] += 1
                log.debug("No fresh signal for %s — skipping", symbol)
                continue

            score = float(signal.get("score", 0.0))
            fallback_used = bool(signal.get("fallback_used", False))

            # Skip FinBERT fallback signals — lower quality, not ensemble
            if fallback_used:
                log.debug("Skipping fallback signal for %s", symbol)
                stats["skipped_stale"] += 1
                continue

            # --- Stop-loss check on existing position ---
            if symbol in open_positions:
                pos = open_positions[symbol]
                entry_price = float(pos.avg_entry_price)
                current_price = float(pos.current_price)
                stop_price = entry_price * (1 - STOP_LOSS_PCT)

                if current_price < stop_price:
                    trading_client.close_position(symbol)
                    stats["stop_losses_triggered"] += 1
                    log.info(
                        "STOP-LOSS %s: entry=%.2f current=%.2f stop=%.2f",
                        symbol, entry_price, current_price, stop_price,
                    )
                else:
                    # Position open and healthy — idempotent, no pyramiding
                    stats["skipped_position"] += 1
                    log.debug("Position already open for %s — skipping entry", symbol)
                continue

            # --- Entry logic ---
            if score <= ENTRY_THRESHOLD:
                log.debug("Signal below threshold for %s (score=%.3f)", symbol, score)
                continue

            # Position sizing: portfolio × max_pct × regime_multiplier
            notional = portfolio_value * MAX_POSITION_PCT * regime_mult

            order = MarketOrderRequest(
                symbol=symbol,
                notional=round(notional, 2),
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
            )
            trading_client.submit_order(order)
            stats["orders_placed"] += 1
            log.info(
                "BUY %s: score=%.3f regime=%.2f notional=%.2f",
                symbol, score, regime_mult, notional,
            )

        except Exception as e:
            log.error("Error processing %s: %s", symbol, e)
            stats["errors"] += 1

    return stats


@app.task(name="src.workers.execution.run_execution_worker")
def run_execution_worker() -> dict:
    """Celery entry-point for ExecutionWorker.

    Reads LLM sentiment signals from Redis and places paper/live orders
    via Alpaca Markets SDK for each symbol in WATCHLIST_SYMBOLS.

    Scheduling:
      - Celery beat: every 15 min, Mon–Fri 14:00–21:00 UTC (market hours).

    Returns:
        Stats dict from run_execution_cycle, or {"skipped": True} if
        Alpaca credentials are not configured.
    """
    from alpaca.trading.client import TradingClient

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — skipping execution")
        return {"skipped": True, "reason": "no_credentials"}

    redis_client = Redis.from_url(config.REDIS_URL)
    redis_store = RedisStore(redis_client)

    # paper=True uses paper-api.alpaca.markets automatically
    paper = "paper-api" in config.ALPACA_BASE_URL
    trading_client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=paper,
    )

    try:
        stats = run_execution_cycle(
            symbols=config.WATCHLIST_SYMBOLS or [],
            redis_store=redis_store,
            trading_client=trading_client,
        )
        log.info("Execution stats: %s", stats)
        return stats
    finally:
        redis_store.close()
        redis_client.close()
