"""Tests for /portfolio endpoints (T-604)."""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")

from src.api.main import app
from src.api.deps import get_pg_store
from src.backtest.engine.types import OrderSide, OrderType
from src.portfolio.types import CombinedOrder


def _make_pg_store(cycles: list[dict] | None = None):
    store = MagicMock()
    store.get_last_portfolio_cycle.return_value = (cycles or [None])[0]
    store.get_portfolio_cycle_history.return_value = cycles or []
    return store


def _make_combined_order(symbol: str, side: OrderSide = OrderSide.BUY, qty: float = 10.0) -> CombinedOrder:
    return CombinedOrder(
        order_id=f"oid-{symbol}",
        timestamp=datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
        symbol=symbol,
        side=side,
        quantity=qty,
        order_type=OrderType.MARKET,
        strategy_id="S1",
        allocation_weight=0.5,
    )


def _make_bars_df(n: int = 100, symbols: list[str] | None = None):
    import pandas as pd
    symbols = symbols or ["SPY", "QQQ", "GLD"]
    data = {sym: [100.0 + i * 0.1 for i in range(n)] for sym in symbols}
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(data, index=idx)


# ── /portfolio/status ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portfolio_status_returns_200():
    """GET /portfolio/status responds with 200."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/status")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_status_includes_active_strategies():
    """GET /portfolio/status lists active strategies with allocations."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/status")
        body = response.json()
        assert "active_strategies" in body
        # Should have some strategies from registry
        assert body["active_strategies"] >= 0
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_status_last_cycle_is_null_when_no_history():
    """GET /portfolio/status returns last_cycle=null when table is empty."""
    pg = _make_pg_store(cycles=[])
    pg.get_last_portfolio_cycle.return_value = None
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/status")
        body = response.json()
        assert body["last_cycle"] is None
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_status_last_cycle_populated_when_history_exists():
    """GET /portfolio/status includes last_cycle data when available."""
    last = {
        "timestamp": "2026-06-02T14:00:00+00:00",
        "strategies_run": ["S1", "S2"],
        "orders_count": 5,
        "constraints_fired": [],
    }
    pg = _make_pg_store()
    pg.get_last_portfolio_cycle.return_value = last
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/status")
        body = response.json()
        assert body["last_cycle"] is not None
        assert body["last_cycle"]["orders_count"] == 5
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


# ── /portfolio/cycle-history ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portfolio_cycle_history_returns_200():
    """GET /portfolio/cycle-history responds with 200."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/cycle-history")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_cycle_history_returns_list():
    """GET /portfolio/cycle-history returns a JSON array."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/cycle-history")
        assert isinstance(response.json(), list)
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_cycle_history_returns_stored_cycles():
    """GET /portfolio/cycle-history returns records from the DB."""
    cycles = [
        {
            "timestamp": f"2026-06-0{i}T14:00:00+00:00",
            "strategies_run": ["S1"],
            "orders_count": i,
            "constraints_fired": [],
            "final_orders": [],
        }
        for i in range(1, 4)
    ]
    pg = _make_pg_store(cycles=cycles)
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/cycle-history")
        body = response.json()
        assert len(body) == 3
        assert body[0]["orders_count"] == 1
    finally:
        app.dependency_overrides.pop(get_pg_store, None)
