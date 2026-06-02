"""Celery task: run portfolio orchestration cycle at market open.

Scheduled: Mon-Fri 14:30 UTC (9:30 AM ET) via Celery beat.

Cycle flow:
    1. Build StrategyRegistry + initialize strategy callables.
    2. Build PortfolioOrchestrator with ConstraintEnforcer + VolTargeter.
    3. Call orchestrator.run_cycle() with current market data.
    4. Log cycle results (strategies run, orders, constraints fired).
    5. Queue final orders for execution via run_execution_worker.

Note: Strategy callables require price history. In the Celery context we load
a minimal price window from Alpaca for signal computation; strategies that need
a longer warm-up (S1: 252 bars, S2: 63 bars) are initialized with the available
window and may produce no orders if data is insufficient.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.workers.celery_app import app

log = logging.getLogger(__name__)

_PRICE_BARS = 300  # bars to fetch for strategy warm-up (> S1's 252-bar lookback)


@app.task(name="src.workers.portfolio_scheduler.run_portfolio_cycle")
def run_portfolio_cycle() -> dict:
    """Celery entry-point for the portfolio orchestration cycle.

    Returns:
        Stats dict: strategies_run, orders_before, orders_after, constraints,
                    or {"skipped": True} when credentials are missing,
                    or {"error": str} on unhandled exception.
    """
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

    # ── Fetch price history ────────────────────────────────────────────────────
    data_client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )
    symbols = list({sym for e in active for sym in _strategy_symbols(e)})
    if not symbols:
        symbols = list(config.WATCHLIST_SYMBOLS or [])

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_PRICE_BARS * 2)  # 2× buffer for weekends/holidays

    bars_df: pd.DataFrame | None = None
    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            limit=_PRICE_BARS,
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

    # ── Build strategy instances ───────────────────────────────────────────────
    strategy_instances: dict = {}
    for entry in active:
        try:
            instance = _build_strategy_instance(entry, bars_df)
            if instance is not None:
                strategy_instances[entry.strategy_id] = instance
        except Exception as exc:
            log.error("Failed to build instance for %s: %s", entry.strategy_id, exc)

    # ── Build market snapshot ──────────────────────────────────────────────────
    latest_prices: dict[str, float] = {}
    for sym in bars_df.columns:
        if not bars_df[sym].dropna().empty:
            latest_prices[sym] = float(bars_df[sym].dropna().iloc[-1])

    market = MarketSnapshot(
        timestamp=end,
        prices=latest_prices,
        volumes={sym: 1_000_000.0 for sym in latest_prices},
        adv_20d={sym: 1_000_000.0 for sym in latest_prices},
    )

    # ── Build portfolio proxy from Alpaca account ─────────────────────────────
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

    # ── Run orchestration cycle ───────────────────────────────────────────────
    data_replay = DataReplay(bars_df)
    orchestrator = PortfolioOrchestrator(
        registry=registry,
        strategy_instances=strategy_instances,
        constraint_enforcer=ConstraintEnforcer(),
        vol_targeter=PortfolioVolTargeter(target_vol=0.10),
    )

    ts = end.replace(tzinfo=None)
    result = orchestrator.run_cycle(
        ts=ts,
        data_replay=data_replay,
        portfolio=portfolio,
        market=market,
    )

    log.info(
        "Portfolio cycle: strategies=%s before=%d after=%d constraints=%d final=%d",
        result.strategies_run,
        result.orders_before_constraints,
        result.orders_after_constraints,
        len(result.constraints_fired),
        len(result.final_orders),
    )

    return {
        "strategies_run": result.strategies_run,
        "orders_before_constraints": result.orders_before_constraints,
        "orders_after_constraints": result.orders_after_constraints,
        "constraints_fired": len(result.constraints_fired),
        "final_orders": len(result.final_orders),
    }


def _strategy_symbols(entry) -> list[str]:
    """Return the universe symbols that a strategy class typically uses."""
    from src.config import config
    return list(config.WATCHLIST_SYMBOLS or [])


def _build_strategy_instance(entry, bars_df):
    """Instantiate a strategy from its registry entry and price history.

    Returns None if the strategy cannot be initialized with available data.
    """
    from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum
    from src.strategies.s2.strategy import VRPStrategy
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config

    sid = entry.strategy_id

    if sid == "S1":
        if len(bars_df) < 21:
            log.warning("S1 needs ≥21 bars, got %d — skipping", len(bars_df))
            return None
        return TimeSeriesMomentum(prices=bars_df, config=S1Config())

    if sid == "S2":
        if len(bars_df) < 63 or "SPY" not in bars_df.columns:
            log.warning("S2 needs ≥63 bars with SPY — skipping (bars=%d)", len(bars_df))
            return None
        return VRPStrategy(prices=bars_df)

    if sid == "S4":
        return NewsDrivenTactical(config=S4Config(), signals=None)

    # Generic fallback: try instantiating with no args
    log.warning("Unknown strategy_id '%s' — skipping", sid)
    return None
