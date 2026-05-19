"""ExecutionWorker — reads LLM signals from Redis and places orders via Alpaca.

Runs as a Celery beat task every 15 min during market hours. Per every cycle:

  1. Check Redis kill-switch (halt immediately if active). Redis unreachable → CRITICAL alert.
  2. Build EMA cache: one batch Alpaca data API call for all symbols, compute 20-period EMA.
  3. Fetch Alpaca account + all open positions (one call, shared across symbols).
     Alpaca unreachable → CRITICAL alert.
  4. Drawdown cap: if daily loss ≥ MAX_DRAWDOWN_PCT, activate kill-switch → CRITICAL alert.
  5. Per symbol:
       a. Read signal from Redis (signal:{symbol}:sentiment, TTL 4h).
       b. Skip if signal is stale (> SIGNAL_MAX_AGE_MIN min) or fallback-only.
       c. If position already open: check stop-loss (2% below entry) or skip (no pyramiding).
       d. If score > ENTRY_THRESHOLD and price > EMA20: place market BUY order.
          Notional = portfolio_value × MAX_POSITION_PCT × regime_multiplier.

Why Alpaca direct instead of QC Lean?
  QC Lean requires historical price data and a QC account. For paper trading
  validation during development, a direct Alpaca SDK integration is simpler
  and runs entirely within the existing stack. QC remains the target for
  multi-asset institutional backtesting (Phase C+).

Infrastructure alerts (B2): Redis unreachable, Alpaca unreachable, and drawdown cap
activation all send a CRITICAL Telegram alert via the injected Notifier. Pass
notifier=TelegramNotifier() from the Celery task entry-point; leave None in tests
that don't need alert assertions.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from redis import Redis

from src.config import config
from src.notifications.base import AlertLevel
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

if TYPE_CHECKING:
    from src.notifications.base import Notifier

log = logging.getLogger(__name__)

ENTRY_THRESHOLD = 0.3
MAX_POSITION_PCT = 0.10
STOP_LOSS_PCT = 0.02
MAX_DRAWDOWN_PCT = 0.10
SIGNAL_MAX_AGE_MIN = 30
EMA_PERIOD = 20
_EMA_BARS_FETCH = EMA_PERIOD + 10  # extra bars to warm up EMA


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


def _build_market_cache(symbols: list[str], data_client) -> dict[str, dict]:
    """Fetch hourly bars and compute 20-period EMA for all symbols in one batch.

    Returns:
        {symbol: {"ema": float | None, "price": float | None}}
        ema/price are None when insufficient bars or API error.

    Why one batch call?
      Alpaca's StockBarsRequest accepts a list of symbols, returning a single
      MultiIndex DataFrame. This avoids N sequential HTTP calls per symbol.

    Why fail to None (not raise)?
      A transient data API error should not block stop-loss checks on existing
      positions. Only new entries are skipped when EMA is unavailable.
    """
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    cache: dict[str, dict] = {s: {"ema": None, "price": None} for s in symbols}

    try:
        end = datetime.now(timezone.utc)
        # Fetch enough hours to cover weekends/holidays (3× buffer)
        start = end - timedelta(hours=_EMA_BARS_FETCH * 3)

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Hour,
            start=start,
            end=end,
            limit=_EMA_BARS_FETCH,
        )
        bars_df = data_client.get_stock_bars(request).df

        for symbol in symbols:
            try:
                sym_bars = bars_df.loc[symbol]
                if len(sym_bars) < EMA_PERIOD:
                    log.debug("Insufficient bars for EMA on %s (%d/%d)", symbol, len(sym_bars), EMA_PERIOD)
                    continue
                closes = sym_bars["close"]
                ema = float(closes.ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1])
                price = float(closes.iloc[-1])
                cache[symbol] = {"ema": ema, "price": price}
            except KeyError:
                log.debug("No bars returned for %s", symbol)

    except Exception as e:
        log.warning("Failed to fetch bars for EMA cache: %s — EMA filter disabled", e)

    return cache


def _fire_alert(notifier: "Notifier | None", message: str, level: AlertLevel) -> None:
    """Send alert via notifier; silently swallows send failures."""
    if notifier is None:
        return
    try:
        asyncio.run(notifier.send_alert(message, level=level))
    except Exception as exc:
        log.warning("Alert send failed: %s", exc)


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
    data_client=None,
    notifier: "Notifier | None" = None,
) -> dict:
    """Core execution logic — separated for testability.

    Args:
        symbols:        List of ticker symbols to evaluate.
        redis_store:    RedisStore instance (connected).
        trading_client: Alpaca TradingClient instance.
        data_client:    Alpaca StockHistoricalDataClient for EMA bars.
                        If None, EMA momentum filter is skipped.
        notifier:       Optional Notifier for critical infrastructure alerts.

    Returns:
        Stats dict: checked, skipped_stale, skipped_killswitch, skipped_position,
                    skipped_momentum, orders_placed, stop_losses_triggered, errors.
    """
    from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
    from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

    stats = {
        "checked": 0,
        "skipped_stale": 0,
        "skipped_killswitch": 0,
        "skipped_position": 0,
        "skipped_momentum": 0,
        "orders_placed": 0,
        "stop_losses_triggered": 0,
        "errors": 0,
    }

    # Kill-switch check — halt all trading if active
    try:
        if redis_store.is_killswitch_active():
            log.warning("Kill-switch active — execution worker halted")
            stats["skipped_killswitch"] = len(symbols)
            return stats
    except Exception as e:
        log.error("Redis unreachable: %s", e)
        _fire_alert(notifier, f"Redis non raggiungibile: {e}", AlertLevel.CRITICAL)
        stats["errors"] += 1
        return stats

    regime_mult = _regime_multiplier(redis_store)

    # Build EMA cache once for all symbols (one batch API call)
    market_cache = _build_market_cache(symbols, data_client) if data_client else {}

    # Fetch current account + positions once (not per symbol)
    try:
        account = trading_client.get_account()
        portfolio_value = float(account.portfolio_value)
        open_positions = {
            p.symbol: p for p in trading_client.get_all_positions()
        }
    except Exception as e:
        log.error("Failed to fetch account/positions from Alpaca: %s", e)
        _fire_alert(notifier, f"Alpaca API non raggiungibile: {e}", AlertLevel.CRITICAL)
        stats["errors"] += 1
        return stats

    # Fetch pending (not-yet-filled) orders to prevent duplicate BUY.
    # get_all_positions() only returns filled positions; a pending order
    # would not appear there, causing a second BUY on the next cycle.
    try:
        pending_orders: set[str] = {
            o.symbol
            for o in trading_client.get_orders(
                GetOrdersRequest(status=QueryOrderStatus.OPEN)
            )
        }
    except Exception as e:
        log.warning("Failed to fetch open orders: %s — skipping duplicate BUY check", e)
        pending_orders = set()

    # Drawdown cap — activate kill-switch if daily loss exceeds MAX_DRAWDOWN_PCT
    try:
        last_equity = float(account.last_equity)
        if last_equity > 0:
            drawdown = (last_equity - portfolio_value) / last_equity
            if drawdown >= MAX_DRAWDOWN_PCT:
                reason = f"Daily drawdown {drawdown:.1%} >= {MAX_DRAWDOWN_PCT:.0%} cap"
                redis_store.activate_killswitch(reason)
                log.critical("DRAWDOWN CAP: %s — kill-switch activated", reason)
                _fire_alert(notifier, f"Drawdown cap attivato: {reason}", AlertLevel.CRITICAL)
                stats["skipped_killswitch"] = len(symbols)
                return stats
    except (ValueError, TypeError):
        pass  # last_equity unavailable — skip cap check

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
            if symbol in pending_orders:
                log.debug("Pending order exists for %s — skip to avoid duplicate BUY", symbol)
                stats["skipped_position"] += 1
                continue

            if score <= ENTRY_THRESHOLD:
                log.debug("Signal below threshold for %s (score=%.3f)", symbol, score)
                continue

            # --- EMA momentum filter ---
            if data_client:
                cached = market_cache.get(symbol, {})
                ema = cached.get("ema")
                price = cached.get("price")
                if ema is None or price is None:
                    log.debug("No EMA data for %s — skipping entry", symbol)
                    stats["skipped_momentum"] += 1
                    continue
                if price <= ema:
                    log.debug(
                        "Price below EMA20 for %s (price=%.2f ema=%.2f) — bearish, skip",
                        symbol, price, ema,
                    )
                    stats["skipped_momentum"] += 1
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
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.trading.client import TradingClient

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — skipping execution")
        return {"skipped": True, "reason": "no_credentials"}

    redis_client = Redis.from_url(config.REDIS_URL)
    redis_store = RedisStore(redis_client)

    paper = "paper-api" in config.ALPACA_BASE_URL
    trading_client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=paper,
    )
    data_client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )

    from src.notifications.telegram import TelegramNotifier
    notifier = TelegramNotifier()

    try:
        stats = run_execution_cycle(
            symbols=config.WATCHLIST_SYMBOLS or [],
            redis_store=redis_store,
            trading_client=trading_client,
            data_client=data_client,
            notifier=notifier,
        )
        log.info("Execution stats: %s", stats)
        return stats
    finally:
        redis_store.close()
        redis_client.close()
