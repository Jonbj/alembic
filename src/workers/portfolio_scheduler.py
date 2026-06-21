"""Celery task: run portfolio orchestration cycle at market open.

Scheduled: Mon-Fri 14:00-21:00 UTC (hourly) via Celery beat.

Cycle flow:
    1. Check kill-switch (halt immediately if active).
    2. Build StrategyRegistry + initialize strategy callables.
    3. Build PortfolioOrchestrator with ConstraintEnforcer + VolTargeter.
    4. Call orchestrator.run_cycle() with current market data.
    5. Check portfolio drawdown cap — activate kill-switch + Telegram alert if breached.
    6. Submit final orders to Alpaca and persist cycle result.
    7. Back-fill Alpaca order_ids on execution_decisions rows.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
from datetime import datetime, timedelta, timezone

from pathlib import Path

from src.notifications.base import AlertLevel
from src.workers.celery_app import app

_MAX_DRAWDOWN_PCT = 0.10  # portfolio-level circuit breaker; mirrors execution.py constant
_PEAK_EQUITY_KEY = "portfolio:peak_equity"

log = logging.getLogger(__name__)

_PRICE_BARS = 300

# P1-B: In-memory cache for fractionable asset flags (refreshed every 24h per worker process).
import time as _time
_FRACTIONABLE_CACHE: dict[str, bool] = {}
_FRACTIONABLE_CACHE_TS: float = 0.0
_FRACTIONABLE_CACHE_TTL: float = 86400.0


def _portfolio_postmortem(
    pg_store,
    trade_id: int,
    signal: dict,
    score: float,
    entry_price: float,
    exit_price: float,
    tick_time,
) -> None:
    """Run postmortem diagnosis on a portfolio-flow exit and persist it.

    Mirrors execution.py's _maybe_postmortem() but without regime lookup
    (the portfolio cycle doesn't apply regime gating, so regime="risk_on").
    """
    from src.performance.postmortem import TradeContext, diagnose_loss, should_trigger_postmortem

    loss_pct = (entry_price - exit_price) / entry_price if entry_price > 0 else 0.0
    confidence = float(signal.get("confidence", 0.5))
    ensemble_std = float(signal.get("ensemble_std", 0.0))

    if not should_trigger_postmortem(loss_pct, score, ensemble_std):
        return

    ctx = TradeContext(
        loss_pct=loss_pct,
        signal_score=score,
        signal_confidence=confidence,
        ensemble_std=ensemble_std,
        regime="risk_on",
        reasoning_summary="",
    )
    diagnosis = diagnose_loss(ctx)
    try:
        pg_store.write_postmortem(trade_id, diagnosis)
    except Exception as exc:
        log.warning("Failed to write postmortem for trade %s: %s", trade_id, exc)


def _filter_approved_strategies(
    entries: list,
    db_conn,
) -> list:
    """Return only the strategies that are operationally approved in strategy_lifecycle.

    Approval semantics:
    - Row exists + approved=True  → admitted.
    - Row exists + approved=False → excluded (fail-closed: explicitly not approved).
    - Row absent (None)           → admitted with warning (fail-open: legacy strategy,
                                    no lifecycle row seeded yet).
    - DB error                    → excluded (fail-closed: cannot verify approval state).

    This function is a module-level helper so tests can inject a mock db_conn
    without triggering the full Celery task infrastructure.
    """
    from src.strategies.promotion import is_strategy_operationally_approved

    approved: list = []
    for entry in entries:
        try:
            # Peek at the raw lifecycle row to distinguish "absent" from "approved=False".
            with db_conn.cursor() as cur:
                cur.execute(
                    "SELECT approved FROM strategy_lifecycle WHERE strategy_id = %s",
                    (entry.strategy_id,),
                )
                row = cur.fetchone()

            if row is None:
                # No lifecycle row — fail-open: legacy strategy, admit with warning.
                log.warning(
                    "Strategy %s: no strategy_lifecycle row found — admitted as legacy "
                    "(fail-open). Seed the lifecycle table to enable promotion gate.",
                    entry.strategy_id,
                )
                approved.append(entry)
            else:
                # Support both dict-like (RealDictCursor) and positional tuple rows.
                try:
                    approved_val = row["approved"]
                except (TypeError, KeyError):
                    approved_val = row[0]

                if approved_val:
                    # Row present, approved=True.
                    approved.append(entry)
                else:
                    # Row present, approved=False — fail-closed.
                    log.warning(
                        "Strategy %s: approved=False in strategy_lifecycle — excluded from cycle. "
                        "Call approve_promotion() to clear the gate.",
                        entry.strategy_id,
                    )
        except Exception as exc:
            # DB error — fail-closed: cannot verify, must not admit.
            log.warning(
                "Strategy %s: DB error during approval check (%s) — excluded (fail-closed).",
                entry.strategy_id, exc,
            )
    return approved


def _fire_alert(notifier, message: str, level: AlertLevel) -> None:
    if notifier is None:
        return
    try:
        asyncio.run(notifier.send_alert(message, level=level))
    except Exception as exc:
        log.warning("Telegram alert send failed: %s", exc)


def _check_divergence_and_alert(
    signal_syms: set,
    order_syms: set,
    submitted_count: int,
    final_count: int,
    notifier,
) -> None:
    """Fire Telegram WARNING alerts when signal/execution divergence thresholds are exceeded (P2-04).

    Two checks:
    1. Signal/order symbol divergence — Jaccard overlap of signal_syms vs order_syms.
       Alert fires when overlap < 0.8 (check_signal_divergence threshold).
    2. Execution fill divergence — |fill_ratio - 1.0| > 0.20 where
       fill_ratio = submitted_count / final_count.  Alert fires when fewer than
       80% of intended orders were actually submitted to the broker.

    Both alerts are WARNING level (not CRITICAL) — they indicate anomalies that
    warrant review but do not automatically halt trading.
    """
    from src.monitoring.alerts import check_signal_divergence, check_execution_divergence

    if check_signal_divergence(signal_syms, order_syms):
        _fire_alert(
            notifier,
            f"Signal/order divergence: signals={sorted(signal_syms)}, orders={sorted(order_syms)}",
            AlertLevel.WARNING,
        )

    fill_ratio = submitted_count / final_count if final_count > 0 else 0.0
    if check_execution_divergence(fill_ratio, 1.0):
        _fire_alert(
            notifier,
            f"Execution fill divergence: {submitted_count}/{final_count} orders submitted",
            AlertLevel.WARNING,
        )


def _emergency_cancel_all(api_key: str, secret_key: str, paper: bool) -> None:
    """Cancel all pending Alpaca orders. Called from kill-switch path before aborting cycle."""
    from alpaca.trading.client import TradingClient as _TC
    try:
        _tc = _TC(api_key=api_key, secret_key=secret_key, paper=paper)
        _tc.cancel_orders()
        log.warning("EMERGENCY: cancelled all pending Alpaca orders (kill-switch active)")
    except Exception as exc:
        log.warning("EMERGENCY cancel_orders failed: %s", exc)


def _is_ks_active_failclosed(redis_url: str) -> bool:
    """Return True if kill-switch is active, or if Redis is unreachable (fail-closed, P0-06).

    Used for the pre-submission re-check: if we cannot verify the kill-switch is clear,
    we assume it is active and skip order submission rather than risk trading while halted.
    """
    try:
        from redis import Redis as _R
        _r = _R.from_url(redis_url, decode_responses=True)
        try:
            return bool(_r.get("killswitch_active")) or bool(_r.get("system:halted_by_operator"))
        finally:
            _r.close()
    except Exception as _ks_exc:
        log.warning("P0-06: Kill-switch re-check failed (%s) — fail-closed, skipping submission", _ks_exc)
        return True


def _get_regime_multiplier_from_redis(redis_url: str) -> float:
    """Read regime multiplier from Redis key regime:current (P0-09).

    Falls back to 0.2 (high_vol fallback) when the key is absent or Redis is
    unreachable — fail-conservative, matching execution.py._regime_multiplier().
    Never returns 1.0 as a default: 1.0 would silently assume a normal regime
    even when no regime data has been written by the regime worker.
    """
    try:
        import json as _rj
        from redis import Redis as _R
        _r = _R.from_url(redis_url, decode_responses=True)
        try:
            raw = _r.get("regime:current")
        finally:
            _r.close()
        if raw is None:
            log.warning("P0-09: regime:current absent — using high_vol fallback (×0.2)")
            return 0.2
        data = _rj.loads(raw)
        return float(data["multiplier"])
    except Exception as _exc:
        log.warning("P0-09: Could not read regime multiplier (%s) — using fallback (×0.2)", _exc)
        return 0.2


_TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"


def _get_fractionable_symbols(trading_client) -> set[str]:
    """Return set of symbols that support fractional/notional orders.

    Results are cached in-memory for 24h per worker process to avoid N API
    calls per cycle. Falls back to treating all symbols as fractionable on error.
    """
    global _FRACTIONABLE_CACHE, _FRACTIONABLE_CACHE_TS
    now = _time.monotonic()
    if _FRACTIONABLE_CACHE and (now - _FRACTIONABLE_CACHE_TS) < _FRACTIONABLE_CACHE_TTL:
        return {sym for sym, ok in _FRACTIONABLE_CACHE.items() if ok}
    try:
        from alpaca.trading.requests import GetAssetsRequest
        from alpaca.trading.enums import AssetStatus
        assets = trading_client.get_all_assets(GetAssetsRequest(status=AssetStatus.ACTIVE))
        _FRACTIONABLE_CACHE = {a.symbol: bool(a.fractionable) for a in assets if a.symbol}
        _FRACTIONABLE_CACHE_TS = now
        log.debug("P1-B: loaded fractionable flags for %d assets", len(_FRACTIONABLE_CACHE))
    except Exception as exc:
        log.warning("P1-B: failed to load fractionable assets: %s — assuming all fractionable", exc)
    return {sym for sym, ok in _FRACTIONABLE_CACHE.items() if ok}


def _load_execution_engine() -> str:
    """Return execution.engine from trading.yaml; defaults to 'portfolio'."""
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("execution", {}).get("engine", "portfolio")
    except Exception as exc:
        log.warning("Could not load execution.engine (%s) — defaulting to portfolio", exc)
        return "portfolio"


_S4_FIRED_SIGNALS_TTL = 108_000  # 30 hours — auto-expires after session date


def _filter_stale_signals(
    signals: list,
    max_age_hours: int,
    now_utc,
) -> tuple[list, list]:
    """Split signals into (fresh, stale) by comparing generated_at to now_utc.

    Signals with generated_at more than max_age_hours before now_utc are stale.
    Clock-skew (slightly future generated_at) is treated as age=0 (not stale).
    """
    fresh, stale = [], []
    for sig in signals:
        age_seconds = (now_utc - sig.generated_at).total_seconds()
        if age_seconds > max_age_hours * 3600:
            stale.append(sig)
        else:
            fresh.append(sig)
    return fresh, stale


def _get_fired_signal_ids(session_date: str, redis_url: str) -> set[int] | None:
    """Return fired signal_ids for today, or None if Redis is unavailable (P2-05-A fail-closed).

    Returns:
        set[int]: IDs of signals already fired this session (may be empty on first run).
        None:     Redis unreachable — caller must treat as fail-closed (skip all S4 BUYs).
    """
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=False)
        try:
            raw = r.smembers(f"s4:fired_signals:{session_date}")
            return {int(v) for v in raw}
        finally:
            r.close()
    except Exception as exc:
        log.warning(
            "P2-05-A: idempotency Redis unreachable — all S4 BUY signals will be skipped (fail-closed): %s",
            exc,
        )
        return None


def _apply_idempotency_filter(orders: list, skip_syms: set[str]) -> list:
    """Filter S4 BUY orders for symbols in skip_syms (P2-05-A fail-closed safety).

    SELL orders are never filtered — only BUY orders for skipped symbols are excluded.
    When Redis is unavailable, callers pass all S4 symbols as skip_syms to prevent
    duplicate BUYs on the assumption that signals may have already fired.
    """
    from src.backtest.engine.types import OrderSide as _OS
    if not skip_syms:
        return orders
    return [o for o in orders if not (o.symbol in skip_syms and o.side == _OS.BUY)]


def _load_risk_config() -> dict[str, float]:
    """Return risk limits from trading.yaml; returns safe hardcoded defaults on error (P2-05-B)."""
    defaults: dict[str, float] = {"max_portfolio_exposure": 0.50, "max_single_asset_pct": 0.10}
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        risk = cfg.get("risk", {})
        return {
            "max_portfolio_exposure": float(risk.get("max_portfolio_exposure", defaults["max_portfolio_exposure"])),
            "max_single_asset_pct": float(risk.get("max_position_pct", defaults["max_single_asset_pct"])),
        }
    except Exception as exc:
        log.warning("P2-05-B: could not load risk config (%s) — using defaults", exc)
        return defaults


def _mark_signal_fired(
    signal_id: int,
    session_date: str,
    redis_url: str,
    ttl_seconds: int = _S4_FIRED_SIGNALS_TTL,
) -> None:
    """Add signal_id to the per-session Redis set; set TTL on first write (fail-silent)."""
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=False)
        try:
            key = f"s4:fired_signals:{session_date}"
            r.sadd(key, signal_id)
            r.expire(key, ttl_seconds)
        finally:
            r.close()
    except Exception as exc:
        log.warning("P1-S4: failed to mark signal_id=%s as fired: %s", signal_id, exc)


_CYCLE_LOCK_KEY = "portfolio:cycle:lock"
_CYCLE_LOCK_TTL = 840  # 14 min — covers worst case; just under the 15-min schedule
_HOLD_MINIMUM_MINUTES = 30  # don't sell a position entered less than this many minutes ago
_MIN_ORDER_NOTIONAL = 100.0  # skip BUY orders below this USD threshold — prevents $40 micro-rebalancing


@app.task(name="src.workers.portfolio_scheduler.run_portfolio_cycle")
def run_portfolio_cycle() -> dict:
    """Celery entry-point for the portfolio orchestration cycle."""
    from src.config import config

    engine = _load_execution_engine()
    if engine not in ("portfolio",):
        log.info("execution.engine=%s — portfolio cycle inactive", engine)
        return {"skipped": True, "reason": f"engine={engine}"}

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — skipping portfolio cycle")
        return {"skipped": True, "reason": "no_credentials"}

    # Cycle idempotency lock: prevents duplicate runs when Celery beat fires
    # multiple tasks before the previous one completes (e.g. worker restart at :30).
    try:
        from redis import Redis as _RedisLock
        _rl = _RedisLock.from_url(config.REDIS_URL, decode_responses=True)
        try:
            acquired = _rl.set(_CYCLE_LOCK_KEY, 1, nx=True, ex=_CYCLE_LOCK_TTL)
            if not acquired:
                log.info("Portfolio cycle skipped — lock held by a concurrent run")
                return {"skipped": True, "reason": "cycle_lock"}
        finally:
            _rl.close()
    except Exception as _lock_exc:
        log.warning("Could not acquire cycle lock: %s — proceeding anyway", _lock_exc)

    try:
        return _run_cycle_inner()
    except Exception as exc:
        log.error("Portfolio cycle unhandled error: %s", exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        # Release the lock early so the next scheduled cycle can run.
        try:
            from redis import Redis as _RedisUnlock
            from src.config import config as _cfg_ul
            _ru = _RedisUnlock.from_url(_cfg_ul.REDIS_URL, decode_responses=True)
            try:
                _ru.delete(_CYCLE_LOCK_KEY)
            finally:
                _ru.close()
        except Exception as _ul_exc:
            log.debug("Could not release cycle lock: %s", _ul_exc)


def _run_cycle_inner() -> dict:
    """Inner cycle logic, separated for testability."""
    import pandas as pd
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient

    from src.backtest.engine.data_replay import DataReplay
    from src.backtest.engine.portfolio import VirtualPortfolio
    from src.backtest.engine.types import MarketSnapshot
    from src.config import config
    from src.notifications.telegram import TelegramNotifier
    from src.portfolio.constraints import ConstraintEnforcer
    from src.portfolio.orchestrator import PortfolioOrchestrator
    from src.portfolio.vol_targeting import PortfolioVolTargeter
    from src.strategies.registry import StrategyRegistry

    notifier = TelegramNotifier()

    # B2 — Kill-switch check: halt immediately if active (drawdown-triggered or operator).
    # Uses direct Redis (same pattern as system:mode check below) so tests can mock redis.Redis.
    try:
        from redis import Redis as _RedisKS
        _r_ks = _RedisKS.from_url(config.REDIS_URL, decode_responses=True)
        try:
            _ks_active = bool(_r_ks.get("killswitch_active")) or bool(_r_ks.get("system:halted_by_operator"))
            if _ks_active:
                _reason_raw = _r_ks.get("killswitch_reason") or _r_ks.get("system:halted_by_operator_reason")
                try:
                    import json as _jks
                    reason = _jks.loads(_reason_raw).get("reason", "unknown") if _reason_raw else "unknown"
                except Exception:
                    reason = "unknown"
                log.warning("Portfolio cycle skipped — kill-switch active: %s", reason)
                # P0-A: Cancel any pending orders to prevent stale fills after kill-switch.
                _emergency_cancel_all(
                    api_key=config.ALPACA_API_KEY,
                    secret_key=config.ALPACA_SECRET_KEY,
                    paper=config.ALPACA_PAPER_MODE,
                )
                return {"skipped": True, "reason": f"killswitch:{reason}"}
        finally:
            _r_ks.close()
    except Exception as exc:
        # Redis unreachable — CRITICAL: we cannot check the kill-switch safely.
        msg = f"🚨 Portfolio cycle: Redis unreachable — cannot verify kill-switch. Aborting cycle.\n<code>{exc}</code>"
        _fire_alert(notifier, msg, AlertLevel.CRITICAL)
        log.error("Redis unreachable in portfolio cycle: %s", exc)
        return {"error": "redis_unreachable"}

    registry = StrategyRegistry()

    # P2-02: Override YAML mode with DB source-of-truth (fail-open if DB unavailable).
    try:
        from src.store.pg_store import PostgreSQLStore
        with PostgreSQLStore() as _pg_reg:
            _reg_conn = _pg_reg._get_connection()
            registry.load_mode_from_db(_reg_conn)
    except Exception as _db_exc:
        log.warning("load_mode_from_db: DB unavailable (%s) — keeping YAML mode", _db_exc)

    active = registry.get_active_strategies()
    if not active:
        log.warning("No active strategies in registry — skipping portfolio cycle")
        return {"skipped": True, "reason": "no_active_strategies"}

    # P2-02: Filter out strategies not operationally approved in strategy_lifecycle.
    try:
        from src.store.pg_store import PostgreSQLStore
        with PostgreSQLStore() as _pg_gate:
            _gate_conn = _pg_gate._get_connection()
            active = _filter_approved_strategies(active, _gate_conn)
    except Exception as _gate_exc:
        log.warning(
            "Approval gate DB unavailable (%s) — admitting all enabled strategies (fail-open at gate level).",
            _gate_exc,
        )

    if not active:
        log.warning("No operationally approved strategies — skipping portfolio cycle")
        return {"skipped": True, "reason": "no_approved_strategies"}

    # Single TradingClient instance shared across all pre-flight checks and order submission.
    trading_client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )

    # P0-B: Market clock pre-flight — skip cycle if NYSE is closed (handles early-close days).
    try:
        clock = trading_client.get_clock()
        if not clock.is_open:
            log.info("Market closed (next open: %s) — skipping portfolio cycle", clock.next_open)
            return {"skipped": True, "reason": "market_closed", "next_open": str(clock.next_open)}
    except Exception as _clk_exc:
        # P0-07: fail-closed — if we can't verify market is open, abort rather than risk
        # submitting orders on a holiday, early-close day, or during an exchange outage.
        log.error("Could not fetch market clock: %s — aborting cycle (fail-closed)", _clk_exc)
        _fire_alert(
            notifier,
            f"⚠️ Portfolio cycle: Alpaca clock API unreachable — cycle aborted (P0-07 fail-closed).\n<code>{_clk_exc}</code>",
            AlertLevel.WARNING,
        )
        return {"error": "clock_unavailable"}

    # P0-D: Account pre-flight — abort if Alpaca has blocked the account.
    try:
        account = trading_client.get_account()
        cash = float(account.cash)
        equity = float(account.equity)
    except Exception as exc:
        # B2 — Alpaca unreachable: CRITICAL alert, abort cycle (don't trade blind).
        msg = f"🚨 Portfolio cycle: Alpaca API unreachable — cycle aborted.\n<code>{exc}</code>"
        _fire_alert(notifier, msg, AlertLevel.CRITICAL)
        log.error("Failed to fetch Alpaca account: %s — aborting cycle", exc)
        return {"error": "alpaca_unreachable"}

    # Use `is True` (not truthy) so MagicMock objects in tests don't trigger this.
    if account.trading_blocked is True or account.account_blocked is True:
        msg = "🚨 Portfolio cycle: account bloccato da Alpaca (trading_blocked o account_blocked) — ciclo abortito"
        _fire_alert(notifier, msg, AlertLevel.CRITICAL)
        log.error("Alpaca account blocked — aborting cycle (trading_blocked=%s, account_blocked=%s)",
                  account.trading_blocked, account.account_blocked)
        return {"skipped": True, "reason": "account_blocked"}

    buying_power = float(account.buying_power) if account.buying_power else cash
    log.debug("Account: equity=%.2f, cash=%.2f, buying_power=%.2f", equity, cash, buying_power)

    # Fetch price history
    data_client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )
    symbols = list({sym for e in active for sym in _strategy_symbols(e)})
    if not symbols:
        symbols = list(config.WATCHLIST_SYMBOLS or [])

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_PRICE_BARS * 2)

    bars_df = None
    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start, end=end,
            feed=DataFeed.IEX,
            adjustment=Adjustment.ALL,
        )
        raw = data_client.get_stock_bars(request).df
        if not raw.empty:
            raw = raw.reset_index()
            bars_df = raw.pivot(index="timestamp", columns="symbol", values="close")
    except Exception as exc:
        log.warning("Failed to fetch price bars: %s — using empty DataFrame", exc)

    if bars_df is None or bars_df.empty:
        log.error("No price data available — aborting portfolio cycle")
        return {"error": "no_price_data"}

    # Build strategy instances
    strategy_instances = {}
    for entry in active:
        try:
            instance = _build_strategy_instance(entry, bars_df)
            if instance is not None:
                strategy_instances[entry.strategy_id] = instance
        except Exception as exc:
            log.error("Failed to build instance for %s: %s", entry.strategy_id, exc)

    # Build market snapshot — seed prices from daily bar closes.
    latest_prices = {}
    for sym in bars_df.columns:
        if not bars_df[sym].dropna().empty:
            latest_prices[sym] = float(bars_df[sym].dropna().iloc[-1])

    # P1-A: Refresh prices from Snapshot API (latest_trade price, then minute_bar close).
    # This replaces yesterday's close with the current intraday price for order sizing.
    try:
        from alpaca.data.requests import StockSnapshotRequest
        snap_req = StockSnapshotRequest(symbol_or_symbols=symbols, feed=DataFeed.IEX)
        snapshots = data_client.get_stock_snapshot(snap_req)
        refreshed = 0
        for sym, snap in snapshots.items():
            price = None
            if snap.latest_trade and snap.latest_trade.price:
                price = float(snap.latest_trade.price)
            elif snap.minute_bar and snap.minute_bar.close:
                price = float(snap.minute_bar.close)
            if price and price > 0:
                latest_prices[sym] = price
                refreshed += 1
        log.debug("P1-A Snapshot: refreshed %d/%d prices from Alpaca real-time", refreshed, len(symbols))
    except Exception as _snap_exc:
        log.warning("Snapshot API failed: %s — using bar closes for pricing", _snap_exc)

    market = MarketSnapshot(
        timestamp=end,
        prices=latest_prices,
        volumes={sym: 1_000_000.0 for sym in latest_prices},
        adv_20d={sym: 1_000_000.0 for sym in latest_prices},
    )

    # B1 — Portfolio drawdown cap: update peak equity in Redis, halt if drawdown breached.
    try:
        from redis import Redis as _Redis2
        import json as _jdd
        _r_dd = _Redis2.from_url(config.REDIS_URL, decode_responses=True)
        try:
            _raw_peak = _r_dd.get(_PEAK_EQUITY_KEY)
            peak_equity = float(_raw_peak) if _raw_peak else equity
            if equity > peak_equity:
                _r_dd.set(_PEAK_EQUITY_KEY, str(equity))
                peak_equity = equity

            drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
            if drawdown >= _MAX_DRAWDOWN_PCT:
                _dd_reason = f"portfolio drawdown {drawdown:.1%} >= {_MAX_DRAWDOWN_PCT:.0%} cap"
                _dd_payload = _jdd.dumps({"reason": _dd_reason, "activated_at": datetime.now(timezone.utc).isoformat()})
                _r_dd.pipeline().setex("killswitch_active", 64800, 1).setex("killswitch_reason", 64800, _dd_payload).execute()
                msg = (
                    f"🚨 <b>Drawdown cap raggiunto — kill-switch attivato</b>\n\n"
                    f"Equity attuale: <b>${equity:,.0f}</b>\n"
                    f"Picco: <b>${peak_equity:,.0f}</b>\n"
                    f"Drawdown: <b>{drawdown:.1%}</b> (soglia: {_MAX_DRAWDOWN_PCT:.0%})\n\n"
                    f"Trading sospeso per 18h. Per riprendere: <code>redis-cli DEL killswitch_active</code>"
                )
                _fire_alert(notifier, msg, AlertLevel.CRITICAL)
                log.error("Drawdown cap %.1f%% — kill-switch activated, aborting cycle", drawdown * 100)
                return {"skipped": True, "reason": f"drawdown_cap:{drawdown:.3f}"}
        finally:
            _r_dd.close()
    except Exception as exc:
        log.warning("Drawdown cap check failed: %s — proceeding without check", exc)

    portfolio = VirtualPortfolio(initial_cash=cash)

    # Load existing Alpaca positions so delta-orders are computed correctly.
    # Without this, the VirtualPortfolio is empty → nav ≈ 0 when account.cash ≈ 0
    # (all equity already invested) → all target quantities ≈ 0 → 0 orders.
    alpaca_entry_prices: dict[str, float] = {}
    alpaca_positions: list = []
    try:
        alpaca_positions = trading_client.get_all_positions()
        for ap in alpaca_positions:
            qty = float(ap.qty)
            avg_cost = float(ap.avg_entry_price)
            portfolio.load_position(symbol=ap.symbol, quantity=qty, avg_cost=avg_cost)
            alpaca_entry_prices[ap.symbol] = avg_cost
        log.info("Loaded %d existing Alpaca positions into VirtualPortfolio", len(alpaca_positions))
    except Exception as exc:
        log.warning("Could not load Alpaca positions: %s — VirtualPortfolio starts empty", exc)

    # Sentiment reversal check: find held positions with strongly negative LLM signal.
    reversal_sell_symbols: set = set()
    try:
        from redis import Redis as _RedisRev
        _r_rev = _RedisRev.from_url(config.REDIS_URL, decode_responses=True)
        try:
            reversal_sell_symbols = _sentiment_reversal_sells(
                alpaca_positions,
                _r_rev,
                threshold=config.SENTIMENT_REVERSAL_EXIT_THRESHOLD,
            )
        finally:
            _r_rev.close()
    except Exception as _rev_exc:
        log.warning("Sentiment reversal check failed: %s — skipping", _rev_exc)

    # Run orchestration cycle
    # P2-05-B: read risk limits from trading.yaml so operator changes to the config
    # are reflected in the live constraint enforcement (not silently ignored).
    _risk_cfg = _load_risk_config()
    data_replay = DataReplay(bars_df)
    orchestrator = PortfolioOrchestrator(
        registry=registry,
        strategy_instances=strategy_instances,
        constraint_enforcer=ConstraintEnforcer(
            max_portfolio_exposure=_risk_cfg["max_portfolio_exposure"],
            max_single_asset_pct=_risk_cfg["max_single_asset_pct"],
        ),
        vol_targeter=PortfolioVolTargeter(target_vol=0.10),
    )

    ts = end

    # Compute equal-weight portfolio daily returns for vol targeting.
    # Uses all symbols in bars_df so vol estimation reflects the current
    # market environment, not just the strategy's holdings.
    _strategy_returns: dict[str, list[float]] | None = None
    if bars_df is not None and not bars_df.empty and len(bars_df) >= 3:
        _ret = bars_df.pct_change().dropna(how="all")
        _port_returns = _ret.mean(axis=1).dropna().tolist()
        if len(_port_returns) >= 2:
            _strategy_returns = {"portfolio": _port_returns}

    result = orchestrator.run_cycle(
        ts=ts, data_replay=data_replay, portfolio=portfolio, market=market,
        strategy_returns=_strategy_returns,
    )

    log.info(
        "Portfolio cycle: strategies=%s before=%d after=%d constraints=%d final=%d",
        result.strategies_run,
        result.orders_before_constraints,
        result.orders_after_constraints,
        len(result.constraints_fired),
        len(result.final_orders),
    )

    # Hold minimum: don't sell positions entered in the last HOLD_MINIMUM_MINUTES.
    # Prevents buy→sell roundtrips within a single rebalance window (e.g. S4 buys
    # at 18:07, S1 rebalances at 18:22 and immediately sells the same ticker).
    try:
        from src.store.pg_store import PostgreSQLStore as _PGHold
        _pg_hold = _PGHold()
        try:
            _recently_bought = _pg_hold.fetch_recently_bought_symbols(_HOLD_MINIMUM_MINUTES)
        finally:
            _pg_hold.close()
        if _recently_bought:
            _before_hold = len(result.final_orders)
            from src.backtest.engine.types import OrderSide as _OSHold
            result = type(result)(
                strategies_run=result.strategies_run,
                orders_per_strategy=result.orders_per_strategy,
                orders_before_constraints=result.orders_before_constraints,
                orders_after_constraints=result.orders_after_constraints,
                constraints_fired=result.constraints_fired,
                final_orders=[
                    o for o in result.final_orders
                    if not (o.side == _OSHold.SELL and o.symbol in _recently_bought)
                ],
                symbol_strategies=result.symbol_strategies,
            )
            _skipped = _before_hold - len(result.final_orders)
            if _skipped:
                log.info(
                    "Hold minimum (%d min): skipped %d SELL order(s) for recently-bought: %s",
                    _HOLD_MINIMUM_MINUTES,
                    _skipped,
                    sorted(_recently_bought),
                )
    except Exception as _hold_exc:
        log.warning("Hold minimum check failed: %s — proceeding without filter", _hold_exc)

    # Log decisions to execution_decisions so the UI Decision Log tab is populated.
    # Also capture decision_ids for later trade DB writes.
    _symbol_decisions: dict[str, dict] = {}  # {symbol: {decision_id, score, signal_id}}
    _s4_signals: dict[str, dict] = {}
    # P0-09: read actual regime multiplier once; used in both decisions and trade writes.
    _regime_mult: float = _get_regime_multiplier_from_redis(config.REDIS_URL)
    try:
        from src.store.pg_store import PostgreSQLStore
        _pg = PostgreSQLStore()
        # symbol_strategies maps each symbol to the list of strategies that contributed
        # to its merged weight (e.g. {"AAPL": ["S4"], "SPY": ["S2"]}).
        _sym_strats = result.symbol_strategies
        _s4_symbols = [sym for sym, strats in _sym_strats.items() if "S4" in strats]
        _signal_ids = _pg.fetch_latest_signal_ids(_s4_symbols) if _s4_symbols else {}
        # P1-S4-IDEMPOTENCY: skip S4 orders whose signal_id already fired today.
        _session_date = ts.strftime("%Y-%m-%d")
        _fired_ids = _get_fired_signal_ids(_session_date, config.REDIS_URL)
        _idempotency_skip: set[str] = set()
        if _fired_ids is None:
            # P2-05-A: Redis unavailable — fail-closed: skip ALL S4 BUY signals this cycle.
            # We cannot verify whether any signal has already been executed today, so we
            # conservatively treat all S4 BUY symbols as already-fired.
            _idempotency_skip = set(_signal_ids.keys())
            log.warning(
                "P2-05-A: Redis unavailable for idempotency check — all %d S4 BUY signals skipped (fail-closed)",
                len(_idempotency_skip),
            )
        else:
            for _sym, _sid in _signal_ids.items():
                if _sid in _fired_ids:
                    _idempotency_skip.add(_sym)
                    log.warning(
                        "P1-S4: signal_id=%s for %s already fired today — skipping (SIGNAL_DUPLICATE_SKIP)",
                        _sid, _sym,
                    )
                    try:
                        _pg.write_audit_log(
                            action="SIGNAL_DUPLICATE_SKIP",
                            table_name="sentiment_signals",
                            record_id=_sid,
                            details={"symbol": _sym, "signal_id": _sid, "session_date": _session_date},
                        )
                    except Exception as _ae:
                        log.warning("P1-S4: duplicate audit write failed: %s", _ae)
        # Load S4 signal details (score + reasoning) for the reason text
        _s4_signals: dict[str, dict] = {}
        if _s4_symbols:
            try:
                _raw_sigs = _pg.fetch_signals_for_cycle(hours=24, symbols=_s4_symbols)
                _s4_signals = {s.symbol: {"score": s.score, "reasoning": s.reasoning, "model_id": s.model_id} for s in _raw_sigs}
            except Exception:
                pass
        for order in result.final_orders:
            strats = _sym_strats.get(order.symbol, [])
            # P1-S4-IDEMPOTENCY: skip this order if its signal_id was already fired today.
            if order.symbol in _idempotency_skip:
                continue
            wt_pct = f"{order.allocation_weight * 100:.1f}%"
            if "S4" in strats:
                sig = _s4_signals.get(order.symbol, {})
                sig_score = sig.get("score", 0.0)
                sig_model = sig.get("model_id", "unknown")
                sig_reasoning = (sig.get("reasoning") or "")[:200]
                other = [s for s in strats if s != "S4"]
                prefix = f"S4+{'+'.join(other)}" if other else "S4"
                reason = (
                    f"{prefix} news-driven: sentiment {sig_score:+.3f} ({sig_model}), "
                    f"portfolio weight {wt_pct}. {sig_reasoning}"
                ).strip()
            elif "S1" in strats and "S2" not in strats:
                reason = f"S1 momentum: time-series momentum signal, portfolio weight {wt_pct}."
            elif "S2" in strats and "S1" not in strats:
                reason = f"S2 VRP: volatility risk premium signal, portfolio weight {wt_pct}."
            elif strats:
                reason = f"{'+'.join(strats)}: merged portfolio weight {wt_pct}."
            else:
                reason = f"Portfolio rebalance: weight {wt_pct}."
            decision_id = _pg.write_execution_decision(
                tick_time=ts,
                symbol=order.symbol,
                signal_id=_signal_ids.get(order.symbol),
                score=order.allocation_weight,
                regime_mult=_regime_mult,
                ema_pass=True,
                decision=order.side.value,
                reason=reason,
            )
            _symbol_decisions[order.symbol] = {
                "decision_id": decision_id,
                "score": order.allocation_weight,
                "signal_id": _signal_ids.get(order.symbol),
                # LLM sentiment score — distinct from allocation_weight stored in score.
                "signal_score": _s4_signals.get(order.symbol, {}).get("score") if "S4" in strats else None,
            }
            # P1-S4-IDEMPOTENCY: mark this signal_id as fired for today's session.
            _fired_sig_id = _signal_ids.get(order.symbol)
            if _fired_sig_id is not None and "S4" in strats:
                _mark_signal_fired(_fired_sig_id, _session_date, config.REDIS_URL)
        _pg.close()
    except Exception as _exc:
        log.warning("Failed to log portfolio decisions: %s", _exc)

    # Check operating mode before submitting orders
    operating_mode = None
    try:
        from redis import Redis as _Redis
        _r = _Redis.from_url(config.REDIS_URL, decode_responses=True)
        try:
            operating_mode = _r.get("system:mode")
        finally:
            _r.close()
    except Exception as exc:
        log.warning("Could not read system:mode from Redis: %s — proceeding with submission", exc)

    if operating_mode in ("dry_run", "halted"):
        log.info("Skipping order submission - %s mode", operating_mode)
        submitted_orders: list[dict] = []
    elif _is_ks_active_failclosed(config.REDIS_URL):
        # P0-06: re-check kill-switch immediately before submission to close the race window.
        # Kill-switch may have been activated after the B2 check at cycle start.
        log.warning("P0-06: Kill-switch active at pre-submission re-check — aborting order submission")
        _emergency_cancel_all(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        try:
            from src.store.pg_store import PostgreSQLStore as _PGKsAudit
            _pg_ks = _PGKsAudit()
            _pg_ks.write_audit_log(
                action="KILLSWITCH_ACTIVATE",
                details={"event": "pre_submission_abort", "source": "portfolio_scheduler"},
            )
            _pg_ks.close()
        except Exception as _ks_audit_exc:
            log.warning("P0-06: Failed to write KS pre-submission audit row: %s", _ks_audit_exc)
        submitted_orders = []
    else:
        fractionable = _get_fractionable_symbols(trading_client)
        # P0-05: fetch symbols with open DB trades to prevent pyramiding.
        open_db_symbols: set[str] = set()
        try:
            from src.store.pg_store import PostgreSQLStore as _PGGuard
            _pg_guard = _PGGuard()
            _open_trades = _pg_guard.fetch_trades(status="open", limit=1000)
            open_db_symbols = {t["symbol"] for t in _open_trades}
            _pg_guard.close()
            if open_db_symbols:
                log.info("P0-05 pyramiding guard: %d symbols have open DB trades", len(open_db_symbols))
        except Exception as _guard_exc:
            log.warning(
                "P0-05: Could not fetch open DB trades for pyramiding guard: %s — guard disabled for this cycle",
                _guard_exc,
            )
        # P2-05-A: exclude S4 BUY orders for symbols whose idempotency check was skipped
        # (Redis unavailable). SELLs and non-S4 orders are not affected.
        _orders_to_submit = _apply_idempotency_filter(result.final_orders, _idempotency_skip)
        submitted_orders = _submit_portfolio_orders(
            _orders_to_submit, trading_client, market,
            fractionable_symbols=fractionable,
            open_trade_symbols=open_db_symbols or None,
            regime_mult=_regime_mult,
        )

    # Submit forced sells for sentiment reversal (symbols not already being sold).
    if reversal_sell_symbols and operating_mode not in ("dry_run", "halted"):
        already_selling = {o.symbol for o in result.final_orders if o.side.value == "sell"}
        to_force_sell = reversal_sell_symbols - already_selling
        for sym in to_force_sell:
            try:
                from alpaca.trading.enums import OrderSide, TimeInForce
                from alpaca.trading.requests import MarketOrderRequest
                qty_held = next(
                    (float(p.qty) for p in alpaca_positions if p.symbol == sym), None
                )
                if qty_held and qty_held > 0:
                    req = MarketOrderRequest(
                        symbol=sym,
                        qty=qty_held,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.DAY,
                    )
                    resp = trading_client.submit_order(req)
                    submitted_orders.append({
                        "symbol": sym,
                        "side": "sell",
                        "order_id": str(resp.id),
                        "notional": 0.0,
                        "reason": "sentiment_reversal",
                    })
                    log.info("Forced sell submitted for %s (sentiment reversal)", sym)
            except Exception as _fs_exc:
                log.warning("Failed to submit forced sell for %s: %s", sym, _fs_exc)

    # P2-04: fire divergence alerts if signals and submitted orders don't match.
    _check_divergence_and_alert(
        signal_syms=set(_s4_signals.keys()),
        order_syms={o["symbol"] for o in submitted_orders},
        submitted_count=len(submitted_orders),
        final_count=len(result.final_orders),
        notifier=notifier,
    )

    # Write trade entries/exits to DB for P&L tracking.
    # Also back-fill the Alpaca order_id on execution_decisions rows.
    if submitted_orders:
        try:
            from src.store.pg_store import PostgreSQLStore
            _pg_trades = PostgreSQLStore()
            for sub in submitted_orders:
                sym = sub["symbol"]
                dec = _symbol_decisions.get(sym, {})
                if sub["side"] == "buy":
                    _pg_trades.open_trade(
                        symbol=sym,
                        signal_id=dec.get("signal_id"),
                        decision_id=dec.get("decision_id"),
                        entry_order_id=sub["order_id"],
                        entry_time=ts,
                        entry_notional=sub["notional"],
                        score=dec.get("score", 0.0),
                        regime_mult=_regime_mult,
                        signal_score=dec.get("signal_score"),
                    )
                else:
                    _trade_id = _pg_trades.record_trade_exit(
                        symbol=sym,
                        exit_order_id=sub["order_id"],
                        exit_time=ts,
                        exit_reason="portfolio_sell",
                    )
                    if _trade_id is not None:
                        _entry_px = alpaca_entry_prices.get(sym, 0.0)
                        _exit_px = market.prices.get(sym, 0.0)
                        _sig = _s4_signals.get(sym, {})
                        _portfolio_postmortem(
                            _pg_trades,
                            _trade_id,
                            signal=_sig,
                            score=dec.get("score", 0.0),
                            entry_price=_entry_px,
                            exit_price=_exit_px,
                            tick_time=ts,
                        )
                # Back-fill Alpaca order_id on the execution_decisions row.
                dec_id = dec.get("decision_id")
                if dec_id is not None:
                    try:
                        _pg_trades.update_decision_order_id(dec_id, sub["order_id"])
                    except Exception as _eid_exc:
                        log.warning("Could not back-fill order_id on decision %s: %s", dec_id, _eid_exc)
            _pg_trades.close()
        except Exception as _exc:
            log.warning("Failed to write trade fills to DB: %s", _exc)

    _persist_cycle_result({
        "timestamp": end,
        "strategies_run": result.strategies_run,
        "orders_count": len(result.final_orders),
        "constraints_fired": [str(c) for c in result.constraints_fired],
        "final_orders": [str(o) for o in result.final_orders],
    })

    return {
        "strategies_run": result.strategies_run,
        "orders_before_constraints": result.orders_before_constraints,
        "orders_after_constraints": result.orders_after_constraints,
        "constraints_fired": len(result.constraints_fired),
        "final_orders": len(result.final_orders),
        "submitted": len(submitted_orders),
    }


def _apply_zeygos_filter(symbols: list[str], pg) -> list[str]:
    """Intersect symbols with the latest Zeygos universe (score >= 65).

    Fail-open: returns the original list unchanged if no Zeygos data is available
    or the intersection would be empty.
    """
    try:
        universe = pg.fetch_zeygos_universe()
        if not universe:
            return symbols
        filtered = [s for s in symbols if s in universe]
        if not filtered:
            log.warning(
                "Zeygos filter would eliminate all S4 symbols — skipping filter"
            )
            return symbols
        log.info("Zeygos filter: %d → %d symbols", len(symbols), len(filtered))
        return filtered
    except Exception as exc:
        log.warning("Zeygos filter failed: %s — using unfiltered symbols", exc)
        return symbols


def _strategy_symbols(entry) -> list[str]:
    from src.config import config
    syms = list(config.WATCHLIST_SYMBOLS or [])
    if entry.strategy_id == "S2" and "SPY" not in syms:
        syms.append("SPY")
    return syms


def _build_strategy_instance(entry, bars_df):
    from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum
    from src.strategies.s2.strategy import VRPStrategy
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config

    sid = entry.strategy_id

    if sid == "S1":
        if len(bars_df) < 21:
            log.warning("S1 needs >=21 bars, got %d — skipping", len(bars_df))
            return None
        return TimeSeriesMomentum(prices=bars_df, config=S1Config())

    if sid == "S2":
        if len(bars_df) < 63:
            log.warning("S2 needs >=63 bars, got %d — skipping", len(bars_df))
            return None
        return VRPStrategy(prices=bars_df)

    if sid == "S4":
        from src.store.pg_store import PostgreSQLStore
        s4_config = S4Config()
        signals_df = None
        store = None
        try:
            store = PostgreSQLStore()
            from src.config import config as _cfg
            s4_symbols = list(_cfg.WATCHLIST_SYMBOLS or [])
            signals = store.fetch_signals_for_cycle(
                hours=s4_config.signals_lookback_hours,
                symbols=s4_symbols,
            )
            if signals:
                # P1-S4-FRESHNESS: drop signals older than max_signal_age_hours.
                _now_utc = datetime.now(timezone.utc)
                fresh_signals, stale_signals = _filter_stale_signals(
                    signals, s4_config.max_signal_age_hours, _now_utc
                )
                if stale_signals:
                    log.warning(
                        "S4: dropped %d/%d stale signals (age > %dh)",
                        len(stale_signals), len(signals), s4_config.max_signal_age_hours,
                    )
                    for _stale in stale_signals:
                        try:
                            _age_h = round(
                                (_now_utc - _stale.generated_at).total_seconds() / 3600, 2
                            )
                            store.write_audit_log(
                                action="SIGNAL_STALE_SKIP",
                                table_name="sentiment_signals",
                                details={
                                    "symbol": _stale.symbol,
                                    "age_hours": _age_h,
                                    "max_age_hours": s4_config.max_signal_age_hours,
                                    "generated_at": _stale.generated_at.isoformat(),
                                },
                            )
                        except Exception as _ae:
                            log.warning("P1-S4: stale audit write failed: %s", _ae)
                signals = fresh_signals
                if signals:
                    import pandas as pd
                    signals_df = pd.DataFrame([{
                        "symbol": s.symbol,
                        "score": s.score,
                        "confidence": s.confidence,
                        "reasoning": s.reasoning,
                        "model_id": s.model_id,
                        "ensemble_std": s.ensemble_std,
                        "fallback_used": s.fallback_used,
                        "generated_at": s.generated_at,
                    } for s in signals])
                    log.info("S4: loaded %d fresh signals (last %dh, max_age=%dh)",
                             len(signals), s4_config.signals_lookback_hours,
                             s4_config.max_signal_age_hours)
                else:
                    log.warning(
                        "S4: all %d signals were stale (max_age=%dh) — no orders this cycle",
                        len(stale_signals), s4_config.max_signal_age_hours,
                    )
            else:
                log.warning(
                    "S4: no signals in DB for last %d hours — strategy will produce no orders",
                    s4_config.signals_lookback_hours,
                )
        except Exception as exc:
            log.warning("S4: failed to load signals from DB: %s — strategy will produce no orders", exc)
        finally:
            if store is not None:
                store.close()
        # Apply signal velocity multiplier to S4 scores before strategy sees them.
        if signals_df is not None and not signals_df.empty:
            try:
                from redis import Redis as _RedisSV
                from src.config import config as _cfg_sv
                _r_sv = _RedisSV.from_url(_cfg_sv.REDIS_URL, decode_responses=True)
                try:
                    multipliers = {
                        sym: _compute_signal_velocity(
                            sym, _r_sv,
                            threshold=_cfg_sv.SIGNAL_VELOCITY_THRESHOLD,
                            boost=_cfg_sv.SIGNAL_VELOCITY_BOOST,
                        )
                        for sym in signals_df["symbol"].unique()
                    }
                    # T-01: apply loss-feedback threshold from Redis.
                    # ENTRY_THRESHOLD in execution.py applies only to legacy mode;
                    # portfolio mode must enforce it here so the mechanism is not bypassed.
                    try:
                        _fb_raw = _r_sv.get("feedback:entry_threshold")
                        _fb_threshold = float(_fb_raw) if _fb_raw is not None else None
                    except Exception:
                        _fb_threshold = None
                finally:
                    _r_sv.close()
                signals_df = signals_df.copy()
                signals_df["score"] = signals_df.apply(
                    lambda row: row["score"] * multipliers.get(row["symbol"], 1.0),
                    axis=1,
                )
                n_boosted = sum(1 for m in multipliers.values() if m != 1.0)
                if n_boosted:
                    log.info("Signal velocity: %d/%d symbols adjusted", n_boosted, len(multipliers))
                # Drop signals below the active feedback threshold (absolute value check
                # so bearish signals are also gated, consistent with BUY-only logic).
                if _fb_threshold is not None and _fb_threshold > s4_config.min_score:
                    before = len(signals_df)
                    signals_df = signals_df[signals_df["score"].abs() >= _fb_threshold]
                    dropped = before - len(signals_df)
                    if dropped:
                        log.info(
                            "S4 feedback gate: dropped %d/%d signals below threshold %.3f",
                            dropped, before, _fb_threshold,
                        )
            except Exception as exc:
                log.warning("Signal velocity application failed: %s — using raw scores", exc)
        # Each Celery task creates a fresh instance with _last_rebalance=None.
        # We intentionally do NOT restore last_rebalance from Redis: the daily gate
        # conflicts with intraday 15-min cycling — if S4 runs on a zero-signal
        # cycle it blocks all subsequent same-day runs, causing BUY→SELL churn.
        # Delta-ordering in the orchestrator is idempotent: if we already hold the
        # target quantity, delta≈0 and no order is generated.
        return NewsDrivenTactical(config=s4_config, signals=signals_df)

    log.warning("Unknown strategy_id '%s' — skipping", sid)
    return None


def _submit_portfolio_orders(
    orders,
    trading_client,
    market,
    _submit_fn=None,
    fractionable_symbols: set[str] | None = None,
    open_trade_symbols: set[str] | None = None,
    regime_mult: float = 1.0,
    _on_broker_reject=None,
) -> list[dict]:
    """Submit BUY and SELL orders to Alpaca.

    Args:
        orders: List of CombinedOrder to submit.
        trading_client: Alpaca TradingClient instance.
        market: MarketSnapshot with current prices.
        _submit_fn: Optional override for testing (receives order, qty_or_notional, trading_client).
            For BUY: receives (order, notional, trading_client).
            For SELL: receives (order, qty, trading_client).
        fractionable_symbols: Set of symbols that support notional/fractional orders.
            BUY orders for non-fractionable symbols fall back to whole-share qty.
            If None, all symbols are treated as fractionable.
        open_trade_symbols: Symbols that already have an open trade in the DB.
            BUY orders for these symbols are skipped to prevent pyramiding (P0-05).
            If None, no duplicate guard is applied.
        regime_mult: Regime multiplier from Redis (P0-09). Scales BUY notional so
            high-volatility regimes (mult=0.2) result in smaller position sizes.

    Returns:
        List of dicts for successfully submitted orders, each containing:
        symbol, side, order_id, and either notional (BUY) or qty (SELL).
    """
    from src.backtest.engine.types import OrderSide

    submitted = []
    for order in orders:
        try:
            if order.side == OrderSide.BUY:
                # P0-05: skip BUY if an open DB trade already exists for this symbol.
                if open_trade_symbols and order.symbol in open_trade_symbols:
                    log.warning(
                        "P0-05 pyramiding guard: skipping BUY for %s — open trade exists in DB",
                        order.symbol,
                    )
                    continue
                price = market.prices.get(order.symbol)
                if price is None or price <= 0:
                    log.warning("No market price for %s — skipping BUY order", order.symbol)
                    continue
                notional = round(price * order.quantity * regime_mult, 2)
                if notional < _MIN_ORDER_NOTIONAL:
                    log.info(
                        "Min notional skip: %s BUY $%.2f < $%.0f threshold",
                        order.symbol, notional, _MIN_ORDER_NOTIONAL,
                    )
                    continue
                # P1-B: Non-fractionable symbols require whole-share qty instead of notional.
                is_fractionable = (fractionable_symbols is None or order.symbol in fractionable_symbols)
                if _submit_fn is not None:
                    _submit_fn(order, notional, trading_client)
                    alpaca_id = f"test-{order.symbol}-buy"
                else:
                    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest
                    from alpaca.trading.enums import OrderClass
                    from src.config import config as _cfg_order

                    if is_fractionable:
                        base_kwargs: dict = dict(
                            symbol=order.symbol,
                            notional=notional,
                            side="buy",
                            time_in_force="day",
                        )
                    else:
                        whole_qty = max(1, int(order.quantity))
                        log.info("P1-B: %s not fractionable — using qty=%d instead of notional", order.symbol, whole_qty)
                        base_kwargs = dict(
                            symbol=order.symbol,
                            qty=whole_qty,
                            side="buy",
                            time_in_force="day",
                        )

                    # P2-A: Bracket order — attach take-profit and stop-loss legs when enabled.
                    # Requires a known entry price (use snapshot price, not notional).
                    if _cfg_order.ALPACA_BRACKET_ENABLED and price and price > 0:
                        tp_price = round(price * (1 + _cfg_order.ALPACA_TAKE_PROFIT_PCT), 2)
                        sl_price = round(price * (1 - _cfg_order.ALPACA_STOP_LOSS_PCT), 2)
                        base_kwargs["order_class"] = OrderClass.BRACKET
                        base_kwargs["take_profit"] = TakeProfitRequest(limit_price=tp_price)
                        base_kwargs["stop_loss"] = StopLossRequest(stop_price=sl_price)
                        log.debug("P2-A bracket %s: tp=%.2f sl=%.2f (entry≈%.2f)", order.symbol, tp_price, sl_price, price)

                    req = MarketOrderRequest(**base_kwargs)
                    alpaca_order = trading_client.submit_order(req)
                    alpaca_id = str(alpaca_order.id)
                submitted.append({"symbol": order.symbol, "side": "buy", "order_id": alpaca_id, "notional": notional})
            elif order.side == OrderSide.SELL:
                qty = abs(order.quantity)
                if qty < 1e-6:
                    continue
                if _submit_fn is not None:
                    _submit_fn(order, qty, trading_client)
                    alpaca_id = f"test-{order.symbol}-sell"
                else:
                    from alpaca.trading.requests import MarketOrderRequest
                    req = MarketOrderRequest(
                        symbol=order.symbol,
                        qty=qty,
                        side="sell",
                        time_in_force="day",
                    )
                    alpaca_order = trading_client.submit_order(req)
                    alpaca_id = str(alpaca_order.id)
                submitted.append({"symbol": order.symbol, "side": "sell", "order_id": alpaca_id, "qty": qty})
            else:
                log.warning("Unknown order side %s for %s — skipping", order.side, order.symbol)
                continue
        except Exception as exc:
            log.warning("Failed to submit order for %s: %s", order.symbol, exc)
            # P2-05-D: notify caller of broker reject so an audit row can be written.
            if _on_broker_reject is not None:
                try:
                    _on_broker_reject(order.symbol, order.side.value, exc)
                except Exception as _cb_exc:
                    log.debug("_on_broker_reject callback raised: %s", _cb_exc)
    return submitted


def _sentiment_reversal_sells(
    alpaca_positions: list,
    redis_client,
    threshold: float,
) -> set:
    """Return symbols held long whose current sentiment score has gone negative.

    Reads signal:{symbol}:sentiment from Redis for each open position.
    Returns the set of symbols that should be force-sold this cycle.
    Fail-open: symbols with no signal or unparseable value are NOT sold.
    """
    import json as _json

    reversal = set()
    for pos in alpaca_positions:
        try:
            raw = redis_client.get(f"signal:{pos.symbol}:sentiment")
            if raw is None:
                continue
            data = _json.loads(raw)
            score = float(data.get("score", 0.0))
            if score < threshold:
                reversal.add(pos.symbol)
                log.info(
                    "Sentiment reversal: %s score=%.3f < threshold=%.2f — forced exit",
                    pos.symbol, score, threshold,
                )
        except Exception as exc:
            log.debug("Could not read sentiment for %s: %s", pos.symbol, exc)
    return reversal


def _compute_signal_velocity(
    symbol: str,
    redis_client,
    threshold: float,
    boost: float = 0.20,
) -> float:
    """Return a score multiplier based on how fast sentiment is changing.

    Reads last 3 entries from signal:{symbol}:history (newest first).
    velocity = scores[0] - scores[-1]
    - velocity >  threshold → 1 + boost (accelerating upward)
    - velocity < -threshold → 1 - boost (accelerating downward)
    - |velocity| <= threshold → 1.0 (stable, no adjustment)

    Returns 1.0 if fewer than 2 history points exist.
    """
    import json as _json

    try:
        raw_list = redis_client.lrange(f"signal:{symbol}:history", 0, 2)
        if len(raw_list) < 2:
            return 1.0
        scores = [float(_json.loads(r)["score"]) for r in raw_list]
        velocity = scores[0] - scores[-1]
        if velocity > threshold:
            return 1.0 + boost
        if velocity < -threshold:
            return 1.0 - boost
        return 1.0
    except Exception as exc:
        log.debug("Signal velocity error for %s: %s", symbol, exc)
        return 1.0


def _persist_cycle_result(cycle_data: dict, conn=None) -> None:
    """Persist cycle stats to portfolio_cycles. DB errors are swallowed."""
    import psycopg2

    _local_conn = None
    should_close = False
    try:
        if conn is None:
            from src.config import config
            _local_conn = psycopg2.connect(config.DATABASE_URL.replace("+asyncpg", ""))
            conn = _local_conn
            should_close = True

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO portfolio_cycles
                   (timestamp, strategies_run, orders_count, constraints_fired, final_orders)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    cycle_data["timestamp"],
                    _json.dumps(cycle_data["strategies_run"]),
                    cycle_data["orders_count"],
                    _json.dumps(cycle_data.get("constraints_fired", [])),
                    _json.dumps(cycle_data.get("final_orders", [])),
                ),
            )
        conn.commit()
    except Exception as exc:
        log.warning("Failed to persist cycle result: %s", exc)
    finally:
        if should_close and _local_conn is not None:
            _local_conn.close()