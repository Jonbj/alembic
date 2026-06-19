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
import json
import logging
from datetime import datetime, timedelta, timezone
from src.workers._async_utils import run_async
from pathlib import Path
from typing import TYPE_CHECKING

from redis import Redis

from src.config import config
from src.costs.calculator import TradeCostCalculator
from src.notifications.base import AlertLevel
from src.performance.postmortem import TradeContext, diagnose_loss, should_trigger_postmortem
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

if TYPE_CHECKING:
    from src.notifications.base import Notifier

log = logging.getLogger(__name__)

_TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"

ENTRY_THRESHOLD = 0.3           # module-level baseline; overridable via Redis feedback keys
MAX_POSITION_PCT = 0.10
MAX_CYCLE_NOTIONAL_PCT = 0.20  # cap total notional placed per execution cycle
STOP_LOSS_PCT = 0.02
MAX_DRAWDOWN_PCT = 0.10


def _load_execution_engine() -> str:
    """Return execution.engine from trading.yaml; defaults to 'legacy_sentiment'."""
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("execution", {}).get("engine", "legacy_sentiment")
    except Exception as exc:
        log.warning("Could not load execution.engine from %s (%s) — defaulting to legacy_sentiment", _TRADING_YAML, exc)
        return "legacy_sentiment"


def _load_risk_params() -> tuple[float, float, float]:
    """Return (stop_loss_pct, max_drawdown_pct, max_position_pct) from trading.yaml."""
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        risk = cfg.get("risk", {})
        stop_loss = float(risk.get("stop_loss", STOP_LOSS_PCT))
        drawdown = float(risk.get("portfolio_drawdown", MAX_DRAWDOWN_PCT))
        max_pos = float(risk.get("max_position_pct", MAX_POSITION_PCT))
        return stop_loss, drawdown, max_pos
    except Exception as exc:
        log.warning("Could not load risk params from %s (%s) — using defaults", _TRADING_YAML, exc)
        return STOP_LOSS_PCT, MAX_DRAWDOWN_PCT, MAX_POSITION_PCT


def _load_killswitch_recovery_config() -> dict:
    """Return killswitch_recovery section from trading.yaml with safe defaults."""
    defaults = {
        "enabled": False,  # P0-06: auto-recovery disabled by default; opt-in via trading.yaml
        "min_hold_hours": 2.0,
        "recovery_drawdown_pct": 0.025,
        "require_non_panic_regime": True,
    }
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f) or {}
        return {**defaults, **cfg.get("risk", {}).get("killswitch_recovery", {})}
    except Exception as exc:
        log.warning("Could not load killswitch_recovery config (%s) — using defaults", exc)
        return defaults


def _try_killswitch_recovery(
    redis_store: RedisStore,
    portfolio_value: float,
    last_equity: float,
    regime_mult: float,
    notifier: "Notifier | None",
) -> bool:
    """Attempt condition-based recovery from a drawdown-triggered kill-switch.

    Only acts on the drawdown-triggered kill-switch (killswitch_active key).
    Operator halts (system:halted_by_operator) are never auto-cleared.

    Returns True if the kill-switch was deactivated, False otherwise.
    """
    cfg = _load_killswitch_recovery_config()
    if not cfg["enabled"]:
        return False

    # Only auto-recover drawdown-triggered freezes, never operator halts
    if not redis_store.is_drawdown_killswitch_active():
        return False
    if redis_store.is_operator_halted():
        return False

    # Check minimum hold time
    reason_data = redis_store.get_killswitch_reason()
    if reason_data:
        try:
            activated_at = datetime.fromisoformat(reason_data.get("activated_at", ""))
            if activated_at.tzinfo is None:
                activated_at = activated_at.replace(tzinfo=timezone.utc)
            hours_held = (datetime.now(timezone.utc) - activated_at).total_seconds() / 3600
            if hours_held < cfg["min_hold_hours"]:
                log.debug(
                    "Kill-switch recovery: %.1fh held < %.1fh minimum — not yet eligible",
                    hours_held, cfg["min_hold_hours"],
                )
                return False
        except Exception:
            return False  # malformed timestamp — conservative: stay locked

    # Check current drawdown has recovered enough
    if last_equity <= 0:
        return False
    current_drawdown = (last_equity - portfolio_value) / last_equity
    if current_drawdown >= cfg["recovery_drawdown_pct"]:
        log.debug(
            "Kill-switch recovery: drawdown %.2f%% >= threshold %.2f%% — not recovered",
            current_drawdown * 100, cfg["recovery_drawdown_pct"] * 100,
        )
        return False

    # Check regime is not high_vol (panic)
    if cfg["require_non_panic_regime"] and regime_mult <= 0.25:
        log.debug("Kill-switch recovery: regime multiplier %.2f (panic) — not recovering", regime_mult)
        return False

    # All conditions met — deactivate
    redis_store.deactivate_killswitch()
    log.warning(
        "Kill-switch auto-recovered: drawdown=%.2f%% < %.2f%% threshold, regime=%.2f",
        current_drawdown * 100, cfg["recovery_drawdown_pct"] * 100, regime_mult,
    )
    msg = (
        f"✅ *Kill-switch auto-deactivato*\n"
        f"Drawdown rientrato a {current_drawdown:.1%} (soglia: {cfg['recovery_drawdown_pct']:.1%})\n"
        f"Regime multiplier: {regime_mult:.2f} — trading ripreso"
    )
    _fire_alert(notifier, msg, AlertLevel.WARNING)
    return True
def _load_entry_threshold(redis_store: "RedisStore") -> float:
    """Return effective entry threshold: Redis feedback override, else module constant."""
    try:
        value = redis_store.get_feedback_entry_threshold()
        if value is not None:
            log.debug("Using feedback-adjusted ENTRY_THRESHOLD=%.3f from Redis", value)
            return value
    except Exception as exc:
        log.warning("Could not read feedback:entry_threshold (%s) — using default", exc)
    return ENTRY_THRESHOLD


def _load_feedback_regime_scale(redis_store: "RedisStore") -> float:
    """Return feedback regime scale factor (0.0–1.0); defaults to 1.0 (no adjustment)."""
    try:
        value = redis_store.get_feedback_regime_scale()
        if value is not None:
            return float(value)
    except Exception as exc:
        log.warning("Could not read feedback:regime_scale (%s) — using 1.0", exc)
    return 1.0


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
    from alpaca.data.enums import DataFeed
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
            feed=DataFeed.IEX,
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
        run_async(notifier.send_alert(message, level=level))
    except Exception as exc:
        log.warning("Alert send failed: %s", exc)


def _write_decision(
    pg_store,
    tick_time,
    symbol: str,
    signal_id: "int | None",
    score: float,
    regime_mult: float,
    ema_pass: bool,
    decision: str,
    order_id: "str | None" = None,
    reason: "str | None" = None,
) -> "int | None":
    """Write one execution decision row. Returns decision_id or None on failure/no-store."""
    if pg_store is None:
        return None
    try:
        return pg_store.write_execution_decision(
            tick_time=tick_time,
            symbol=symbol,
            signal_id=signal_id,
            score=score,
            regime_mult=regime_mult,
            ema_pass=ema_pass,
            decision=decision,
            order_id=order_id,
            reason=reason,
        )
    except Exception as e:
        log.warning("Failed to write execution decision for %s: %s", symbol, e)
        return None


def _regime_label(regime_mult: float) -> str:
    """Convert a numeric regime multiplier to the string label expected by TradeContext."""
    if regime_mult <= 0.3:
        return "high_vol"
    if regime_mult <= 0.6:
        return "risk_off"
    if regime_mult <= 0.9:
        return "uncertain"
    return "risk_on"


def _maybe_postmortem(
    pg_store,
    trade_id: int,
    signal: dict,
    score: float,
    regime_mult: float,
    entry_price: float,
    exit_price: float,
    tick_time,
    entry_time=None,
) -> None:
    """Run postmortem diagnosis on a losing trade and persist the result.

    Silently skips if the loss is below the trigger thresholds to avoid
    writing a diagnosis for every tiny dip.

    entry_time: when provided, used to detect overnight gap risk (tick_time.date()
    > entry_time.date() means the position was held at least one overnight session).
    """
    loss_pct = (entry_price - exit_price) / entry_price if entry_price > 0 else 0.0
    confidence = float(signal.get("confidence", 0.5))
    ensemble_std = float(signal.get("ensemble_std", 0.0))

    if not should_trigger_postmortem(loss_pct, score, ensemble_std):
        return

    signal_age_min = 0.0
    generated_at = signal.get("generated_at")
    if generated_at:
        try:
            sig_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
            if sig_dt.tzinfo is None:
                sig_dt = sig_dt.replace(tzinfo=timezone.utc)
            signal_age_min = (tick_time - sig_dt).total_seconds() / 60
        except Exception:
            pass

    was_overnight = False
    if entry_time is not None:
        try:
            et = entry_time if entry_time.tzinfo else entry_time.replace(tzinfo=timezone.utc)
            was_overnight = tick_time.date() > et.date()
        except Exception:
            pass

    ctx = TradeContext(
        loss_pct=loss_pct,
        signal_score=score,
        signal_confidence=confidence,
        ensemble_std=ensemble_std,
        regime=_regime_label(regime_mult),
        reasoning_summary="",
        signal_age_minutes=signal_age_min,
        was_overnight_gap=was_overnight,
    )
    diagnosis = diagnose_loss(ctx)
    try:
        pg_store.write_postmortem(trade_id, diagnosis)
    except Exception as pm_exc:
        log.warning("Failed to write postmortem for trade %s: %s", trade_id, pm_exc)


def _regime_multiplier(redis_store: RedisStore, notifier: "Notifier | None" = None) -> float:
    """Return regime multiplier from Redis.

    Falls back to 0.2 (high_vol multiplier) when the key is absent — e.g. on first
    startup or after a regime worker failure. Fail-conservative rather than fail-open.
    """
    regime = redis_store.get_regime()
    if regime is None:
        _fire_alert(
            notifier,
            "Regime key absent in Redis — using high_vol fallback (×0.2). Check regime worker.",
            AlertLevel.WARNING,
        )
        return 0.2
    return float(regime.multiplier)


def run_execution_cycle(
    symbols: list[str],
    redis_store: RedisStore,
    trading_client,
    data_client=None,
    notifier: "Notifier | None" = None,
    pg_store=None,
    cost_calc: "TradeCostCalculator | None" = None,
) -> dict:
    """Core execution logic — separated for testability.

    Args:
        symbols:        List of ticker symbols to evaluate.
        redis_store:    RedisStore instance (connected).
        trading_client: Alpaca TradingClient instance.
        data_client:    Alpaca StockHistoricalDataClient for EMA bars.
                        If None, EMA momentum filter is skipped.
        notifier:       Optional Notifier for critical infrastructure alerts.
        pg_store:       Optional PostgreSQLStore for decision + trade lifecycle logging.
                        If None, all observability writes are silently skipped.

    Returns:
        Stats dict: checked, skipped_stale, skipped_killswitch, skipped_position,
                    skipped_momentum, skipped_cycle_cap, orders_placed, stop_losses_triggered, errors.
    """
    from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
    from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, StopLossRequest

    stats = {
        "checked": 0,
        "skipped_stale": 0,
        "skipped_killswitch": 0,
        "skipped_position": 0,
        "skipped_momentum": 0,
        "skipped_cycle_cap": 0,
        "orders_placed": 0,
        "stop_losses_triggered": 0,
        "errors": 0,
    }

    _cost_calc = cost_calc or TradeCostCalculator()
    _, max_drawdown_pct, max_position_pct = _load_risk_params()
    # per-symbol stop-loss is tier-based via _cost_calc.stop_loss_pct().

    # --- Account fetch (always runs, even during kill-switch freeze) ---
    # Keeps portfolio:value fresh in Redis for recovery checks and reporting.
    # Open positions are fetched later, only when not frozen.
    try:
        account = trading_client.get_account()
        portfolio_value = float(account.portfolio_value)
        redis_store.set_portfolio_value(portfolio_value)
    except Exception as e:
        log.error("Failed to fetch account from Alpaca: %s", e)
        _fire_alert(notifier, f"Alpaca API non raggiungibile: {e}", AlertLevel.CRITICAL)
        stats["errors"] += 1
        return stats

    # --- Regime (needed for recovery check and position sizing) ---
    regime_mult = _regime_multiplier(redis_store, notifier)
    feedback_scale = _load_feedback_regime_scale(redis_store)
    regime_mult = regime_mult * feedback_scale

    # --- Condition-based kill-switch recovery ---
    # Attempts to auto-deactivate a drawdown-triggered freeze when the drawdown
    # has recovered enough and the regime is no longer in panic mode.
    try:
        last_equity_for_recovery = float(account.last_equity)
    except (ValueError, TypeError):
        last_equity_for_recovery = 0.0
    try:
        _try_killswitch_recovery(redis_store, portfolio_value, last_equity_for_recovery, regime_mult, notifier)
    except Exception as rec_exc:
        log.warning("Kill-switch recovery check failed: %s", rec_exc)

    # --- Kill-switch gate — halt all trading if still active ---
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

    entry_threshold = _load_entry_threshold(redis_store)

    # Build EMA cache once for all symbols (one batch API call)
    market_cache = _build_market_cache(symbols, data_client) if data_client else {}

    # Fetch open positions + pending orders (only when not frozen)
    try:
        open_positions = {
            p.symbol: p for p in trading_client.get_all_positions()
        }
    except Exception as e:
        log.error("Failed to fetch positions from Alpaca: %s", e)
        _fire_alert(notifier, f"Alpaca API non raggiungibile: {e}", AlertLevel.CRITICAL)
        stats["errors"] += 1
        return stats

    # Fetch pending (not-yet-filled) orders to prevent duplicate BUY.
    # get_all_positions() only returns filled positions; a pending order
    # would not appear there, causing a second BUY on the next cycle.
    # Failure to fetch is treated as fail-safe: pending_orders=None blocks
    # all new entries that cycle rather than risking a duplicate BUY.
    pending_orders: set[str] | None
    try:
        pending_orders = {
            o.symbol
            for o in trading_client.get_orders(
                GetOrdersRequest(status=QueryOrderStatus.OPEN)
            )
        }
    except Exception as e:
        log.error("Failed to fetch open orders from Alpaca: %s — blocking new entries this cycle", e)
        _fire_alert(notifier, f"Alpaca (open orders) non raggiungibile: {e}", AlertLevel.CRITICAL)
        pending_orders = None

    # Drawdown cap — activate kill-switch if daily loss exceeds MAX_DRAWDOWN_PCT
    try:
        last_equity = float(account.last_equity)
        if last_equity > 0:
            drawdown = (last_equity - portfolio_value) / last_equity
            if drawdown >= max_drawdown_pct:
                reason = f"Daily drawdown {drawdown:.1%} >= {max_drawdown_pct:.0%} cap"
                redis_store.activate_killswitch(reason, ttl=64800)
                log.critical("DRAWDOWN CAP: %s — kill-switch activated", reason)
                _fire_alert(notifier, f"Drawdown cap attivato: {reason}", AlertLevel.CRITICAL)
                stats["skipped_killswitch"] = len(symbols)
                return stats
    except (ValueError, TypeError):
        pass  # last_equity unavailable — skip cap check

    cycle_notional = 0.0
    cycle_cap = portfolio_value * MAX_CYCLE_NOTIONAL_PCT

    for symbol in symbols:
        stats["checked"] += 1
        try:
            tick_time = datetime.now(timezone.utc)

            # --- Signal read ---
            signal = redis_store.read_sentiment(symbol)

            # --- Stop-loss check on existing position (runs regardless of signal freshness) ---
            if symbol in open_positions:
                pos = open_positions[symbol]
                entry_price = float(pos.avg_entry_price)
                current_price = float(pos.current_price)
                sym_stop_pct = _cost_calc.stop_loss_pct(symbol)
                stop_price = entry_price * (1 - sym_stop_pct)

                if current_price < stop_price:
                    try:
                        trading_client.close_position(symbol)
                        stats["stop_losses_triggered"] += 1
                        log.info(
                            "STOP-LOSS %s: entry=%.2f current=%.2f stop=%.2f",
                            symbol, entry_price, current_price, stop_price,
                        )
                        _fire_alert(
                            notifier,
                            f"🔴 STOP-LOSS {symbol}: entry={entry_price:.2f} current={current_price:.2f} (−{sym_stop_pct*100:.0f}%)",
                            AlertLevel.WARNING,
                        )
                        trade_id: "int | None" = None
                        trade_entry_time = None
                        if pg_store is not None:
                            try:
                                # Fetch entry_time before closing for overnight-gap detection
                                open_rec = pg_store.fetch_trades(symbol=symbol, status="open", limit=1)
                                if open_rec:
                                    trade_entry_time = open_rec[0].get("entry_time")
                                trade_id = pg_store.close_trade(
                                    symbol=symbol,
                                    exit_price=current_price,
                                    exit_time=tick_time,
                                    exit_reason="stop_loss",
                                    entry_price=entry_price,
                                    entry_notional=float(pos.avg_entry_price) * float(pos.qty),
                                    qty=float(pos.qty),
                                )
                            except Exception as trade_exc:
                                log.warning("Failed to close trade record for %s: %s", symbol, trade_exc)

                        if trade_id is not None and pg_store is not None:
                            _maybe_postmortem(
                                pg_store=pg_store,
                                trade_id=trade_id,
                                signal=signal,
                                score=float(signal.get("score", 0.0)) if signal else 0.0,
                                regime_mult=regime_mult,
                                entry_price=entry_price,
                                exit_price=current_price,
                                tick_time=tick_time,
                                entry_time=trade_entry_time,
                            )
                    except Exception as stop_exc:
                        log.error("Failed to close stop-loss position for %s: %s", symbol, stop_exc)
                        _fire_alert(
                            notifier,
                            f"🚨 STOP-LOSS FAILED {symbol}: could not close position — {stop_exc}",
                            AlertLevel.CRITICAL,
                        )
                        stats["errors"] += 1
                else:
                    # Position open and healthy — idempotent, no pyramiding
                    stats["skipped_position"] += 1
                    log.debug("Position already open for %s — skipping entry", symbol)
                    if signal is not None and _is_fresh(signal):
                        _sig_score = float(signal.get("score", 0.0))
                        _sig_id = signal.get("signal_id")
                        if _sig_score > entry_threshold:
                            _write_decision(pg_store, tick_time, symbol, _sig_id, _sig_score,
                                            regime_mult, ema_pass=True, decision="SKIP_POSITION")
                continue

            # --- Signal freshness check (entry candidates only) ---
            if signal is None:
                stats["skipped_stale"] += 1
                log.debug("No signal for %s — skipping", symbol)
                continue
            if not _is_fresh(signal):
                stats["skipped_stale"] += 1
                log.debug("Stale signal for %s — skipping", symbol)
                _write_decision(pg_store, tick_time, symbol, signal.get("signal_id"),
                                float(signal.get("score", 0.0)), regime_mult,
                                ema_pass=True, decision="SKIP_STALE",
                                reason=f"signal age > {SIGNAL_MAX_AGE_MIN}min")
                continue

            score = float(signal.get("score", 0.0))
            fallback_used = bool(signal.get("fallback_used", False))
            signal_id: "int | None" = signal.get("signal_id")

            # Skip FinBERT fallback signals — lower quality, not ensemble
            if fallback_used:
                log.debug("Skipping fallback signal for %s (score=%.3f)", symbol, score)
                stats["skipped_stale"] += 1
                _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                ema_pass=True, decision="SKIP_FALLBACK",
                                reason="FinBERT fallback only — no LLM ensemble consensus")
                continue

            # --- Entry logic ---
            if pending_orders is None or symbol in pending_orders:
                log.debug("Pending order check unavailable or order exists for %s — skip", symbol)
                stats["skipped_position"] += 1
                if score > entry_threshold:
                    _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                    ema_pass=True, decision="SKIP_POSITION")
                continue

            if score <= entry_threshold:
                log.debug("Signal below threshold for %s (score=%.3f, threshold=%.3f)", symbol, score, entry_threshold)
                _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                ema_pass=True, decision="SKIP_SCORE",
                                reason=f"score {score:.3f} <= threshold {entry_threshold:.3f}")
                continue

            # --- EMA momentum filter ---
            if data_client:
                cached = market_cache.get(symbol, {})
                ema = cached.get("ema")
                price = cached.get("price")
                if ema is None or price is None:
                    log.debug("EMA/price unavailable for %s — skipping entry (fail-safe)", symbol)
                    stats["skipped_momentum"] += 1
                    _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                    ema_pass=False, decision="SKIP_EMA")
                    continue
                elif price <= ema:
                    log.debug(
                        "Price below EMA20 for %s (price=%.2f ema=%.2f) — bearish, skip",
                        symbol, price, ema,
                    )
                    stats["skipped_momentum"] += 1
                    _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                    ema_pass=False, decision="SKIP_EMA")
                    continue

            # Position sizing: portfolio × max_pct × regime_multiplier
            notional = portfolio_value * max_position_pct * regime_mult

            # Per-cycle allocation cap: don't deploy more than MAX_CYCLE_NOTIONAL_PCT in one cycle
            if cycle_notional + notional > cycle_cap:
                log.info(
                    "Cycle cap reached (%.2f/%.2f) — skipping %s",
                    cycle_notional, cycle_cap, symbol,
                )
                stats["skipped_cycle_cap"] += 1
                _write_decision(pg_store, tick_time, symbol, signal_id, score, regime_mult,
                                ema_pass=True, decision="SKIP_CAP")
                continue

            # Broker-side stop order: use OTO class when price is available from EMA cache.
            # Avoids relying solely on the 15-min software poll for stop-loss enforcement.
            qty: "float | None" = None
            cached = market_cache.get(symbol, {})
            price = cached.get("price")

            if price is not None:
                qty = round(notional / price, 4)
                sym_stop_pct = _cost_calc.stop_loss_pct(symbol)
                stop_price = round(price * (1 - sym_stop_pct), 2)
                order = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    order_class=OrderClass.OTO,
                    stop_loss=StopLossRequest(stop_price=stop_price),
                )
            else:
                order = MarketOrderRequest(
                    symbol=symbol,
                    notional=round(notional, 2),
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                )
            submitted_order = trading_client.submit_order(order)
            order_id_str = str(submitted_order.id)
            cycle_notional += notional
            stats["orders_placed"] += 1
            log.info(
                "BUY %s: score=%.3f regime=%.2f notional=%.2f broker_stop=%s",
                symbol, score, regime_mult, notional, price is not None,
            )
            _fire_alert(
                notifier,
                f"🟢 BUY {symbol}: score={score:.2f} notional=${notional:.0f} regime={regime_mult:.2f}×",
                AlertLevel.INFO,
            )
            decision_id = _write_decision(
                pg_store, tick_time, symbol, signal_id, score, regime_mult,
                ema_pass=True, decision="BUY", order_id=order_id_str,
            )
            if pg_store is not None:
                try:
                    pg_store.open_trade(
                        symbol=symbol,
                        signal_id=signal_id,
                        decision_id=decision_id,
                        entry_order_id=order_id_str,
                        entry_time=tick_time,
                        entry_notional=notional,
                        score=score,
                        regime_mult=regime_mult,
                        qty=qty,
                    )
                except Exception as trade_exc:
                    log.warning("Failed to open trade record for %s: %s", symbol, trade_exc)

        except Exception as e:
            log.error("Error processing %s: %s", symbol, e)
            stats["errors"] += 1

    # Near market close (19:30–20:00 UTC = 15:30–16:00 ET): alert on open positions
    # that will be held overnight. Fires once per day via a Redis dedup key.
    _near_close = (tick_time.hour == 19 and tick_time.minute >= 30) or tick_time.hour == 20
    if _near_close:
        _alert_overnight_positions(open_positions, portfolio_value, notifier, redis_store, tick_time)

    return stats


def _alert_overnight_positions(
    open_positions: dict,
    portfolio_value: float,
    notifier: "Notifier | None",
    redis_store: RedisStore,
    tick_time,
) -> None:
    """Send a Telegram alert if positions are open going into the overnight session.

    Deduped per calendar date so only one alert fires per market day even if
    multiple execution cycles fall in the 19:30-20:00 UTC window.
    """
    if not open_positions:
        return

    date_str = tick_time.date().isoformat()
    if redis_store.is_overnight_alert_sent(date_str):
        return  # already alerted today
    redis_store.mark_overnight_alert_sent(date_str)

    lines = ["🌙 *Overnight Hold Alert*", f"{len(open_positions)} position(s) going into overnight:"]
    for sym, pos in open_positions.items():
        try:
            entry = float(pos.avg_entry_price)
            current = float(pos.current_price)
            notional = entry * float(pos.qty)
            pnl_pct = (current - entry) / entry * 100 if entry > 0 else 0.0
            lines.append(f"  • {sym}: ${notional:.0f} notional | P&L {pnl_pct:+.1f}%")
        except Exception:
            lines.append(f"  • {sym}")

    lines.append("_Gap risk: stop-loss may fill below trigger at next open._")
    msg = "\n".join(lines)
    log.info("Overnight hold alert: %d positions", len(open_positions))
    _fire_alert(notifier, msg, AlertLevel.WARNING)


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

    engine = _load_execution_engine()
    if engine not in ("legacy_sentiment",):
        log.info("execution.engine=%s — legacy execution worker inactive", engine)
        return {"skipped": True, "reason": f"engine={engine}"}

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — skipping execution")
        return {"skipped": True, "reason": "no_credentials"}

    redis_client = Redis.from_url(config.REDIS_URL)
    redis_store = RedisStore(redis_client)

    paper = config.ALPACA_PAPER_MODE
    log.info("Trading mode: %s", "paper" if paper else "LIVE")
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

    import psycopg2
    from src.store.pg_store import PostgreSQLStore
    pg_conn = psycopg2.connect(config.DATABASE_URL.replace("+asyncpg", ""))
    pg_store = PostgreSQLStore(conn=pg_conn)

    try:
        stats = run_execution_cycle(
            symbols=config.WATCHLIST_SYMBOLS or [],
            redis_store=redis_store,
            trading_client=trading_client,
            data_client=data_client,
            notifier=notifier,
            pg_store=pg_store,
            cost_calc=TradeCostCalculator(),
        )
        log.info("Execution stats: %s", stats)
        return stats
    finally:
        redis_store.close()
        redis_client.close()
        pg_store.close()
        pg_conn.close()
