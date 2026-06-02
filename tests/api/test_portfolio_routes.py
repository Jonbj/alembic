"""Tests for /api/portfolio endpoints (T-604)."""

import os
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")

from src.api.main import app
from src.api.deps import get_pg_store


def _make_pg_store(cycles: list[dict] | None = None):
    store = MagicMock()
    store.get_last_portfolio_cycle.return_value = (cycles or [None])[0]
    store.get_portfolio_cycle_history.return_value = cycles or []
    return store


# ── /api/portfolio/status ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portfolio_status_returns_200():
    """GET /api/portfolio/status responds with 200."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/portfolio/status")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_status_includes_active_strategies():
    """GET /api/portfolio/status lists active strategies with allocations."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/portfolio/status")
        body = response.json()
        assert "active_strategies" in body
        ids = [s["strategy_id"] for s in body["active_strategies"]]
        assert "S1" in ids
        assert "S2" in ids
        assert "S4" in ids
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_status_last_cycle_is_null_when_no_history():
    """GET /api/portfolio/status returns last_cycle=null when table is empty."""
    pg = _make_pg_store(cycles=[])
    pg.get_last_portfolio_cycle.return_value = None
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/portfolio/status")
        body = response.json()
        assert body["last_cycle"] is None
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_status_last_cycle_populated_when_history_exists():
    """GET /api/portfolio/status includes last_cycle data when available."""
    last = {
        "id": 1,
        "timestamp": "2026-06-02T14:00:00+00:00",
        "strategies_run": ["S1", "S2"],
        "orders_count": 5,
        "constraints_fired": [],
        "final_orders": [],
    }
    pg = _make_pg_store()
    pg.get_last_portfolio_cycle.return_value = last
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/portfolio/status")
        body = response.json()
        assert body["last_cycle"] is not None
        assert body["last_cycle"]["orders_count"] == 5
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


# ── /api/portfolio/cycle-history ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portfolio_cycle_history_returns_200():
    """GET /api/portfolio/cycle-history responds with 200."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/portfolio/cycle-history")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_cycle_history_returns_list():
    """GET /api/portfolio/cycle-history returns a JSON array."""
    pg = _make_pg_store()
    app.dependency_overrides[get_pg_store] = lambda: pg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/portfolio/cycle-history")
        assert isinstance(response.json(), list)
    finally:
        app.dependency_overrides.pop(get_pg_store, None)


@pytest.mark.asyncio
async def test_portfolio_cycle_history_returns_stored_cycles():
    """GET /api/portfolio/cycle-history returns records from the DB."""
    cycles = [
        {
            "id": i,
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
            response = await client.get("/api/portfolio/cycle-history")
        body = response.json()
        assert len(body) == 3
        assert body[0]["id"] == 1
    finally:
        app.dependency_overrides.pop(get_pg_store, None)
