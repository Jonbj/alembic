"""Celery task: run portfolio orchestration cycle at market open.

Scheduled: Mon-Fri 14:00-21:00 UTC (hourly) via Celery beat.

Cycle flow:
    1. Build StrategyRegistry + initialize strategy callables.
    2. Build PortfolioOrchestrator with ConstraintEnforcer + VolTargeter.
    3. Call orchestrator.run_cycle() with current market data.
    4. Log cycle results (strategies run, orders, constraints fired).
    5. Submit final orders to Alpaca and persist cycle result.
"""
from __future__ import annotations

import json as _json
import logging
from datetime import datetime, timedelta, timezone

from pathlib import Path

from src.workers.celery_app import app

log = logging.getLogger(__name__)

_PRICE_BARS = 300
_TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"


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

    try:
        return _run_cycle_inner()
    except Exception as exc:
        log.error("Portfolio cycle unhandled error: %s", exc, exc_info=True)
        return {"error": str(exc)}


def _run_cycle_inner() -> dict:
    """Inner cycle logic, separated for testability."""
    import pandas as pd
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient

    from src.backtest.engine.data_replay import DataReplay
    from src.backtest.engine.portfolio import VirtualPortfolio
    from src.backtest.engine.types import MarketSnapshot
    from src.config import config
    from src.portfolio.constraints import ConstraintEnforcer
    from src.portfolio.orchestrator import PortfolioOrchestrator
    from src.portfolio.vol_targeting import PortfolioVolTargeter
    from src.strategies.registry import StrategyRegistry

    registry = StrategyRegistry()
    active = registry.get_active_strategies()
    if not active:
        log.warning("No active strategies in registry — skipping portfolio cycle")
        return {"skipped": True, "reason": "no_active_strategies"}

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

    # Build market snapshot
    latest_prices = {}
    for sym in bars_df.columns:
        if not bars_df[sym].dropna().empty:
            latest_prices[sym] = float(bars_df[sym].dropna().iloc[-1])

    market = MarketSnapshot(
        timestamp=end,
        prices=latest_prices,
        volumes={sym: 1_000_000.0 for sym in latest_prices},
        adv_20d={sym: 1_000_000.0 for sym in latest_prices},
    )

    # Build portfolio proxy
    trading_client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper="paper-api" in config.ALPACA_BASE_URL,
    )
    try:
        account = trading_client.get_account()
        cash = float(account.cash)
    except Exception as exc:
        log.warning("Failed to fetch Alpaca account: %s — using default $100k", exc)
        cash = 100_000.0

    portfolio = VirtualPortfolio(initial_cash=cash)

    # Load existing Alpaca positions so delta-orders are computed correctly.
    # Without this, the VirtualPortfolio is empty → nav ≈ 0 when account.cash ≈ 0
    # (all equity already invested) → all target quantities ≈ 0 → 0 orders.
    try:
        alpaca_positions = trading_client.get_all_positions()
        for ap in alpaca_positions:
            qty = float(ap.qty)
            avg_cost = float(ap.avg_entry_price)
            portfolio.load_position(symbol=ap.symbol, quantity=qty, avg_cost=avg_cost)
        log.info("Loaded %d existing Alpaca positions into VirtualPortfolio", len(alpaca_positions))
    except Exception as exc:
        log.warning("Could not load Alpaca positions: %s — VirtualPortfolio starts empty", exc)

    # Run orchestration cycle
    data_replay = DataReplay(bars_df)
    orchestrator = PortfolioOrchestrator(
        registry=registry,
        strategy_instances=strategy_instances,
        constraint_enforcer=ConstraintEnforcer(),
        vol_targeter=PortfolioVolTargeter(target_vol=0.10),
    )

    ts = end
    result = orchestrator.run_cycle(
        ts=ts, data_replay=data_replay, portfolio=portfolio, market=market,
    )

    log.info(
        "Portfolio cycle: strategies=%s before=%d after=%d constraints=%d final=%d",
        result.strategies_run,
        result.orders_before_constraints,
        result.orders_after_constraints,
        len(result.constraints_fired),
        len(result.final_orders),
    )

    # Log decisions to execution_decisions so the UI Decision Log tab is populated.
    # Also capture decision_ids for later trade DB writes.
    _symbol_decisions: dict[str, dict] = {}  # {symbol: {decision_id, score, signal_id}}
    try:
        from src.store.pg_store import PostgreSQLStore
        _pg = PostgreSQLStore()
        # symbol_strategies maps each symbol to the list of strategies that contributed
        # to its merged weight (e.g. {"AAPL": ["S4"], "SPY": ["S2"]}).
        _sym_strats = result.symbol_strategies
        _s4_symbols = [sym for sym, strats in _sym_strats.items() if "S4" in strats]
        _signal_ids = _pg.fetch_latest_signal_ids(_s4_symbols) if _s4_symbols else {}
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
                regime_mult=1.0,
                ema_pass=True,
                decision=order.side.value,
                reason=reason,
            )
            _symbol_decisions[order.symbol] = {
                "decision_id": decision_id,
                "score": order.allocation_weight,
                "signal_id": _signal_ids.get(order.symbol),
            }
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
    else:
        submitted_orders = _submit_portfolio_orders(result.final_orders, trading_client, market)

    # Write trade entries/exits to DB for P&L tracking.
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
                        regime_mult=1.0,
                    )
                else:
                    _pg_trades.record_trade_exit(
                        symbol=sym,
                        exit_order_id=sub["order_id"],
                        exit_time=ts,
                        exit_reason="portfolio_sell",
                    )
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
            signals = store.fetch_signals_for_cycle(
                hours=s4_config.signals_lookback_hours,
                symbols=list(_cfg.WATCHLIST_SYMBOLS or []),
            )
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
                log.info("S4: loaded %d signals from DB (last %d h)", len(signals), s4_config.signals_lookback_hours)
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
        return NewsDrivenTactical(config=s4_config, signals=signals_df)

    log.warning("Unknown strategy_id '%s' — skipping", sid)
    return None


def _submit_portfolio_orders(orders, trading_client, market, _submit_fn=None) -> list[dict]:
    """Submit BUY and SELL orders to Alpaca.

    Args:
        orders: List of CombinedOrder to submit.
        trading_client: Alpaca TradingClient instance.
        market: MarketSnapshot with current prices.
        _submit_fn: Optional override for testing (receives order, qty_or_notional, trading_client).
            For BUY: receives (order, notional, trading_client).
            For SELL: receives (order, qty, trading_client).

    Returns:
        List of dicts for successfully submitted orders, each containing:
        symbol, side, order_id, and either notional (BUY) or qty (SELL).
    """
    from src.backtest.engine.types import OrderSide

    submitted = []
    for order in orders:
        try:
            if order.side == OrderSide.BUY:
                price = market.prices.get(order.symbol)
                if price is None or price <= 0:
                    log.warning("No market price for %s — skipping BUY order", order.symbol)
                    continue
                notional = round(price * order.quantity, 2)
                if _submit_fn is not None:
                    _submit_fn(order, notional, trading_client)
                    alpaca_id = f"test-{order.symbol}-buy"
                else:
                    from alpaca.trading.requests import MarketOrderRequest
                    req = MarketOrderRequest(
                        symbol=order.symbol,
                        notional=notional,
                        side="buy",
                        time_in_force="day",
                    )
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
    return submitted


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