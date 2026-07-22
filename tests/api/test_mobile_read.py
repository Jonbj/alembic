"""Integration tests for /api/mobile/v1 read endpoints.

The tests mock Alpaca to avoid real broker calls and verify the coherent
snapshot shape, positions, performance, and events read paths.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import asyncpg
import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-do-not-use-in-production")

from src.api.main import app  # noqa: E402
from src.config import config  # noqa: E402
from src.mobile_monitoring.auth import (  # noqa: E402
    create_mobile_access_token,
)
from src.mobile_monitoring.store import MonitorStore  # noqa: E402

_MIGRATION_PATH = Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql"


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


@pytest.fixture
async def pool():
    dsn = _dsn()
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
    assert pool is not None
    async with pool.acquire() as conn:
        await conn.execute(_MIGRATION_PATH.read_text())
    yield pool
    await pool.close()


@pytest.fixture
async def store(pool):
    yield MonitorStore(pool)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_events CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_event_history CASCADE")


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def monitor_user(store):
    import bcrypt

    return await store.create_user(
        username="monitor",
        password_hash=bcrypt.hashpw("secret123".encode(), bcrypt.gensalt()).decode(),
    )


@pytest.fixture
async def monitor_device(store, monitor_user):
    return await store.create_device(
        user_id=monitor_user.id,
        installation_id=str(uuid.uuid4()),
        name="Pixel 9",
        app_version="1.0.0",
    )


def _token(user, device) -> str:
    return create_mobile_access_token(user_id=user.id, device_id=device.id)


def _mock_alpaca():
    account = MagicMock()
    account.equity = "110307.36"
    account.last_equity = "110422.96"
    account.cash = "76998.12"
    account.portfolio_value = "110307.36"

    pos = MagicMock()
    pos.symbol = "MSFT"
    pos.qty = "12.3456"
    pos.avg_entry_price = "511.22"
    pos.current_price = "505.00"
    pos.market_value = "6234.10"
    pos.unrealized_pl = "-77.88"

    clock = MagicMock()
    clock.is_open = True
    clock.next_open = datetime.now(timezone.utc) + timedelta(hours=1)
    clock.next_close = datetime.now(timezone.utc) + timedelta(hours=7)

    client = MagicMock()
    client.get_account.return_value = account
    client.get_all_positions.return_value = [pos]
    client.get_clock.return_value = clock
    return client


class _FakeRedis:
    """Minimal Redis look-alike for the mobile builder tests."""

    def __init__(self):
        self.store = {}
        self.ping = MagicMock(return_value=True)
        self.is_killswitch_active = MagicMock(return_value=False)

    def get(self, key):
        return self.store.get(key)


@pytest.fixture
async def mobile_deps(pool, client):
    """Override mobile read dependencies with in-memory broker/Redis."""
    from src.api.routes import mobile_read as mobile_read_mod
    from src.mobile_monitoring.builder import MobileEventStore, MobileSnapshotBuilder

    redis = _FakeRedis()
    builder = MobileSnapshotBuilder(pool=pool, alpaca=_mock_alpaca(), redis=redis)
    store = MobileEventStore(pool=pool)

    def _builder_override(request: Request):
        return builder

    def _event_store_override(request: Request):
        return store

    app.dependency_overrides[mobile_read_mod._builder] = _builder_override
    app.dependency_overrides[mobile_read_mod._event_store] = _event_store_override

    yield builder, store, redis

    app.dependency_overrides.pop(mobile_read_mod._builder, None)
    app.dependency_overrides.pop(mobile_read_mod._event_store, None)


class TestMobileRead:
    """Happy-path and negative tests for mobile read API."""

    async def test_snapshot_requires_mobile_token(self, client, monitor_user, monitor_device):
        resp = await client.get("/api/mobile/v1/read/snapshot")
        assert resp.status_code == 401

    async def test_snapshot_returns_coherent_shape(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        resp = await client.get(
            "/api/mobile/v1/read/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["contract_version"] == 1
        assert data["currency"] == "USD"
        assert data["operational"]["state"] == "operational"
        assert data["operational"]["mode"] == "paper"
        assert data["portfolio"]["nav"] is not None
        assert data["pipeline"]["broker"]["status"] == "fresh"
        assert len(data["strategies"]) >= 0

    async def test_positions_returns_items(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        resp = await client.get(
            "/api/mobile/v1/read/positions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["summary"]["count"] == 1
        assert data["items"][0]["symbol"] == "MSFT"

    async def test_performance_rejects_invalid_period(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        resp = await client.get(
            "/api/mobile/v1/read/performance?period=2y",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    async def test_events_returns_feed(self, client, mobile_deps, store, monitor_user, monitor_device):
        token = _token(monitor_user, monitor_device)
        # Seed one event.
        async with store.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO mobile_events
                    (fingerprint, kind, category, severity, status,
                     occurred_at, first_observed_at, last_observed_at, title)
                VALUES ($1, 'alert_incident', 'system', 'warning', 'open',
                        now(), now(), now(), 'test event')
                """,
                "test:fingerprint",
            )
        resp = await client.get(
            "/api/mobile/v1/read/events?category=all&days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "test event"
