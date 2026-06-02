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

from src.workers.celery_app import app

log = logging.getLogger(__name__)

_PRICE_BARS = 300


@app.task(name="src.workers.portfolio_scheduler.run_portfolio_cycle")
def run_portfolio_cycle() -> dict:
    """Celery entry-point for the portfolio orchestration cycle."""
    from src.config import config

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

    # Submit orders and persist
    submitted = _submit_portfolio_orders(result.final_orders, trading_client, market)
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
        "submitted": submitted,
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
        return NewsDrivenTactical(config=S4Config(), signals=None)

    log.warning("Unknown strategy_id '%s' — skipping", sid)
    return None


def _submit_portfolio_orders(orders, trading_client, market, _submit_fn=None) -> int:
    """Submit BUY combined orders to Alpaca. SELL orders are skipped.

    Args:
        orders: List of CombinedOrder to submit.
        trading_client: Alpaca TradingClient instance.
        market: MarketSnapshot with current prices.
        _submit_fn: Optional override for testing (receives order, notional, trading_client).
    """
    from src.backtest.engine.types import OrderSide

    submitted = 0
    for order in orders:
        if order.side != OrderSide.BUY:
            continue
        try:
            price = market.prices.get(order.symbol, 100.0)
            notional = round(price * order.quantity, 2)
            if _submit_fn is not None:
                _submit_fn(order, notional, trading_client)
            else:
                from alpaca.trading.requests import MarketOrderRequest
                req = MarketOrderRequest(
                    symbol=order.symbol,
                    notional=notional,
                    side="buy",
                    time_in_force="day",
                )
                trading_client.submit_order(req)
            submitted += 1
        except Exception as exc:
            log.warning("Failed to submit order for %s: %s", order.symbol, exc)
    return submitted


def _persist_cycle_result(cycle_data: dict, conn=None) -> None:
    """Persist cycle stats to portfolio_cycles. DB errors are swallowed."""
    try:
        import psycopg2

        if conn is None:
            from src.config import config
            conn = psycopg2.connect(config.DATABASE_URL.replace("+asyncpg", ""))
            should_close = True
        else:
            should_close = False

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
        if should_close:
            conn.close()
    except Exception as exc:
        log.warning("Failed to persist cycle result: %s", exc)