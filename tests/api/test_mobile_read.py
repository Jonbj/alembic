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

_MIGRATION_PATHS = (
    Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql",
    Path(__file__).parent.parent.parent
    / "migrations"
    / "042_mobile_session_access_jti.sql",
)


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or str(config.DATABASE_URL)


@pytest.fixture
async def pool():
    dsn = _dsn()
    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=4)
    assert pool is not None
    async with pool.acquire() as conn:
        for migration_path in _MIGRATION_PATHS:
            await conn.execute(migration_path.read_text())
    yield pool
    await pool.close()


@pytest.fixture
async def store(pool):
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_events CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_event_history CASCADE")
    yield MonitorStore(pool)
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE monitor_sessions CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_devices CASCADE")
        await conn.execute("TRUNCATE TABLE monitor_users CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_events CASCADE")
        await conn.execute("TRUNCATE TABLE mobile_event_history CASCADE")


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
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
        self._r = self
        self.ping = MagicMock(return_value=True)
        self.is_killswitch_active = MagicMock(return_value=False)

    def get(self, key):
        return self.store.get(key)


class _FakeReadModel:
    """In-memory atomic read-model seam used by route tests."""

    def __init__(self, bundle):
        self.bundle = bundle

    def load(self):
        return self.bundle


@pytest.fixture
async def mobile_deps(pool, client):
    """Override mobile read dependencies with in-memory broker/Redis."""
    from src.api.routes import mobile_read as mobile_read_mod
    from src.mobile_monitoring.builder import MobileSnapshotBuilder
    from src.mobile_monitoring.events import MobileEventStore
    from src.mobile_monitoring.performance import MobilePerformanceService

    redis = _FakeRedis()
    alpaca = _mock_alpaca()
    builder = MobileSnapshotBuilder(pool=pool, alpaca=alpaca, redis=redis)
    bundle = await builder.build_bundle()
    read_model = _FakeReadModel(bundle)
    store = MobileEventStore(pool=pool)

    def _event_store_override(request: Request):
        return store

    def _read_model_override():
        return read_model

    def _performance_override():
        return MobilePerformanceService(pool, read_model)

    def _auth_override():
        return {
            "sub": "00000000-0000-0000-0000-000000000001",
            "device_id": "00000000-0000-0000-0000-000000000002",
            "scope": ["monitor:read"],
        }

    app.dependency_overrides[mobile_read_mod._read_model] = _read_model_override
    app.dependency_overrides[mobile_read_mod._performance_service] = (
        _performance_override
    )
    app.dependency_overrides[mobile_read_mod._event_store] = _event_store_override
    app.dependency_overrides[mobile_read_mod.require_mobile_token] = _auth_override

    yield builder, store, redis, alpaca, read_model

    app.dependency_overrides.pop(mobile_read_mod._read_model, None)
    app.dependency_overrides.pop(mobile_read_mod._performance_service, None)
    app.dependency_overrides.pop(mobile_read_mod._event_store, None)
    app.dependency_overrides.pop(mobile_read_mod.require_mobile_token, None)


class TestMobileRead:
    """Happy-path and negative tests for mobile read API."""

    def test_openapi_exposes_canonical_v1_read_contract(self) -> None:
        paths = app.openapi()["paths"]

        for path in (
            "/api/mobile/v1/snapshot",
            "/api/mobile/v1/performance",
            "/api/mobile/v1/positions",
            "/api/mobile/v1/events",
        ):
            assert "get" in paths[path]
        assert not any("/api/mobile/v1/read/" in path for path in paths)

    async def test_snapshot_requires_mobile_token(
        self, client, monitor_user, monitor_device
    ):
        resp = await client.get("/api/mobile/v1/snapshot")
        assert resp.status_code == 401

    async def test_snapshot_returns_coherent_shape(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        _, _, _, alpaca, _ = mobile_deps
        alpaca.reset_mock()
        token = _token(monitor_user, monitor_device)
        resp = await client.get(
            "/api/mobile/v1/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["contract_version"] == 1
        assert data["currency"] == "USD"
        assert data["operational"]["state"] == "operational"
        assert data["operational"]["mode"] == "paper"
        assert data["operational"]["market_timezone"] == "America/New_York"
        assert data["portfolio"]["nav"] is not None
        assert data["pipeline"]["broker"]["status"] == "fresh"
        assert len(data["strategies"]) >= 0
        assert data["snapshot_id"]
        alpaca.get_account.assert_not_called()
        alpaca.get_all_positions.assert_not_called()
        alpaca.get_clock.assert_not_called()

    async def test_snapshot_supports_etag_and_minimum_app_version(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        headers = {"Authorization": f"Bearer {token}"}
        first = await client.get("/api/mobile/v1/snapshot", headers=headers)

        cached = await client.get(
            "/api/mobile/v1/snapshot",
            headers={**headers, "If-None-Match": first.headers["ETag"]},
        )
        upgrade = await client.get(
            "/api/mobile/v1/snapshot",
            headers={**headers, "X-App-Version": "0.9.0"},
        )

        assert cached.status_code == 304
        assert upgrade.status_code == 426
        assert upgrade.json()["error"]["code"] == "upgrade_required"

    async def test_snapshot_absent_returns_safe_503(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        mobile_deps[4].bundle = None
        token = _token(monitor_user, monitor_device)

        response = await client.get(
            "/api/mobile/v1/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "snapshot_unavailable"
        assert response.json()["error"]["retryable"] is True

    async def test_snapshot_stale_beyond_safe_ceiling_returns_503(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        read_model = mobile_deps[4]
        read_model.bundle.snapshot.as_of = datetime.now(timezone.utc) - timedelta(
            seconds=301
        )
        token = _token(monitor_user, monitor_device)

        response = await client.get(
            "/api/mobile/v1/snapshot",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 503
        assert response.json()["error"]["details"]["data_age_seconds"] >= 301

    async def test_closed_market_is_paused_but_dependency_failure_is_blocked(
        self, mobile_deps
    ):
        builder, _, redis, alpaca, _ = mobile_deps
        clock = alpaca.get_clock.return_value
        clock.is_open = False
        clock.next_open = datetime.now(timezone.utc) + timedelta(days=2)

        paused = await builder.build_bundle()
        assert paused.snapshot.operational.state == "paused"
        assert paused.snapshot.pipeline["signal"].status == "not_expected"
        assert paused.snapshot.pipeline["portfolio_cycle"].status == "not_expected"

        redis.ping.side_effect = RuntimeError("redis unavailable")
        blocked = await builder.build_bundle()
        assert blocked.snapshot.operational.state == "blocked"
        assert blocked.snapshot.portfolio.nav is not None

    async def test_broker_failure_is_null_not_zero(
        self, mobile_deps
    ):
        builder, _, _, alpaca, _ = mobile_deps
        alpaca.get_account.side_effect = RuntimeError("broker unavailable")

        bundle = await builder.build_bundle()

        assert bundle.snapshot.operational.state == "blocked"
        assert bundle.snapshot.portfolio.nav is None
        assert bundle.snapshot.portfolio.cash is None
        assert bundle.positions.summary.market_value is None
        assert bundle.positions.summary.unrealized_pnl is None

    async def test_positions_returns_items(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        resp = await client.get(
            "/api/mobile/v1/positions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["summary"]["count"] == 1
        assert data["items"][0]["symbol"] == "MSFT"
        assert data["snapshot_id"] == str(
            mobile_deps[4].bundle.snapshot.snapshot_id
        )

    async def test_performance_rejects_invalid_period(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        resp = await client.get(
            "/api/mobile/v1/performance?period=2y",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    async def test_performance_uses_current_coherent_nav_without_zero_placeholder(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        response = await client.get(
            "/api/mobile/v1/performance?period=1m",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["snapshot_id"] == str(
            mobile_deps[4].bundle.snapshot.snapshot_id
        )
        assert data["summary"]["nav_end"] == 110307.36
        assert data["points"][-1]["nav"] == 110307.36
        assert data["summary"]["benchmark_return"] is None
        assert data["summary"]["alpha"] is None

    async def test_events_returns_feed(
        self, client, mobile_deps, store, monitor_user, monitor_device
    ):
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
            "/api/mobile/v1/events?category=all&days=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "test event"

    async def test_events_signed_cursor_is_stable_and_tampering_is_400(
        self, client, mobile_deps, store, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        occurred_at = datetime.now(timezone.utc)
        async with store.pool.acquire() as conn:
            for fingerprint in ("cursor:newer", "cursor:older"):
                await conn.execute(
                    """
                    INSERT INTO mobile_events (
                        fingerprint, kind, category, severity, status,
                        occurred_at, first_observed_at, last_observed_at, title
                    )
                    VALUES ($1::varchar, 'decision', 'trading', 'info', 'closed',
                            $2, $2, $2, $1::text)
                    """,
                    fingerprint,
                    occurred_at,
                )
        first = await client.get(
            "/api/mobile/v1/events?limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        cursor = first.json()["next_cursor"]
        second = await client.get(
            f"/api/mobile/v1/events?limit=1&cursor={cursor}",
            headers={"Authorization": f"Bearer {token}"},
        )
        tamper_index = len(cursor) // 2
        replacement = "A" if cursor[tamper_index] != "A" else "B"
        tampered = cursor[:tamper_index] + replacement + cursor[tamper_index + 1 :]
        invalid = await client.get(
            f"/api/mobile/v1/events?limit=1&cursor={tampered}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert first.status_code == 200
        assert cursor
        assert second.status_code == 200
        assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "invalid_cursor"
