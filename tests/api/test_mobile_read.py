"""Integration tests for /api/mobile/v1 read endpoints.

The tests mock Alpaca to avoid real broker calls and verify the coherent
snapshot shape, positions, performance, and events read paths.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock, MagicMock

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
from src.mobile_monitoring.models import Freshness, OperationalState  # noqa: E402
from src.mobile_monitoring.read_model import (  # noqa: E402
    MobileReadModelStore,
    ResilientMobileReadModelReader,
)
from src.mobile_monitoring.store import MonitorStore  # noqa: E402

_MIGRATION_PATHS = (
    Path(__file__).parent.parent.parent / "migrations" / "041_mobile_monitoring.sql",
    Path(__file__).parent.parent.parent
    / "migrations"
    / "042_mobile_session_access_jti.sql",
    Path(__file__).parent.parent.parent
    / "migrations"
    / "043_mobile_fcm_delivery.sql",
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
    pos.unrealized_plpc = "-0.01234"

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
        self.set = MagicMock(return_value=True)
        self.delete = MagicMock(return_value=1)
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
    bundle.snapshot.operational.state = OperationalState.OPERATIONAL
    bundle.snapshot.operational.primary_reason = None
    bundle.snapshot.pipeline["signal"].status = Freshness.FRESH
    bundle.snapshot.pipeline["signal"].age_seconds = 0
    bundle.snapshot.pipeline["portfolio_cycle"].status = Freshness.FRESH
    bundle.snapshot.pipeline["portfolio_cycle"].age_seconds = 0
    bundle.snapshot.degradations = [
        degradation
        for degradation in bundle.snapshot.degradations
        if degradation.component not in {"signal", "portfolio_cycle"}
    ]
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
        assert data["pipeline"]["signal"]["freshness_budget_seconds"] == 900
        assert data["pipeline"]["signal"]["stale_after_seconds"] == 1380
        assert len(data["strategies"]) >= 0
        assert data["snapshot_id"]
        alpaca.get_account.assert_not_called()
        alpaca.get_all_positions.assert_not_called()
        alpaca.get_clock.assert_not_called()

    async def test_warm_snapshot_read_model_p95_is_below_250ms(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        headers = {"Authorization": f"Bearer {token}"}
        durations = []

        for _ in range(30):
            started = perf_counter()
            response = await client.get(
                "/api/mobile/v1/snapshot",
                headers=headers,
            )
            durations.append(perf_counter() - started)
            assert response.status_code == 200

        p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
        assert p95 < 0.250

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

    @pytest.mark.parametrize(
        "path",
        [
            "/api/mobile/v1/snapshot",
            "/api/mobile/v1/performance?period=1m",
            "/api/mobile/v1/positions",
            "/api/mobile/v1/events?category=system",
        ],
    )
    async def test_all_read_endpoints_support_stable_etag(
        self,
        path,
        client,
        mobile_deps,
        monitor_user,
        monitor_device,
    ):
        token = _token(monitor_user, monitor_device)
        headers = {"Authorization": f"Bearer {token}"}
        first = await client.get(path, headers=headers)
        assert first.status_code == 200, first.text
        cached = await client.get(
            path,
            headers={**headers, "If-None-Match": first.headers["ETag"]},
        )

        assert first.headers["ETag"].startswith('W/"')
        assert cached.status_code == 304

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

    async def test_postgres_fallback_wins_when_read_only_redis_is_stale(
        self, pool, mobile_deps
    ):
        bundle = mobile_deps[4].bundle
        pipeline_health = {
            "_mobile_read_bundle": bundle.model_dump(mode="json"),
        }
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO portfolio_monitor_snapshots (
                    snapshot_id, as_of, nav, pipeline_health, degradations
                )
                VALUES ($1, $2, $3, $4::jsonb, '[]'::jsonb)
                ON CONFLICT (snapshot_id) DO UPDATE
                SET pipeline_health=EXCLUDED.pipeline_health
                """,
                bundle.snapshot.snapshot_id,
                bundle.snapshot.as_of,
                bundle.snapshot.portfolio.nav,
                json.dumps(pipeline_health),
            )

        stale_primary = bundle.model_copy(deep=True)
        stale_primary.snapshot.as_of -= timedelta(minutes=1)
        read_only_redis = MagicMock(spec=MobileReadModelStore)
        read_only_redis.load.return_value = stale_primary
        reader = ResilientMobileReadModelReader(read_only_redis, pool)

        loaded = await reader.load()

        assert loaded is not None
        assert loaded.snapshot.snapshot_id == bundle.snapshot.snapshot_id

    async def test_healthy_redis_wins_when_postgres_fallback_is_unavailable(
        self, mobile_deps
    ):
        bundle = mobile_deps[4].bundle
        healthy_redis = MagicMock(spec=MobileReadModelStore)
        healthy_redis.load.return_value = bundle
        unavailable_pool = MagicMock(spec=asyncpg.Pool)
        unavailable_pool.acquire.side_effect = RuntimeError("database unavailable")
        reader = ResilientMobileReadModelReader(healthy_redis, unavailable_pool)

        loaded = await reader.load()

        assert loaded is bundle

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

    async def test_performance_rejects_stale_read_model(
        self, client, mobile_deps, monitor_user, monitor_device
    ):
        mobile_deps[4].bundle.snapshot.as_of = datetime.now(
            timezone.utc
        ) - timedelta(seconds=301)
        token = _token(monitor_user, monitor_device)

        response = await client.get(
            "/api/mobile/v1/performance?period=1m",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "performance_unavailable"

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

    async def test_redis_read_only_is_degraded_and_reported_not_writeable(
        self, mobile_deps
    ):
        builder, _, redis, _, _ = mobile_deps
        redis.set.side_effect = RuntimeError("READONLY replica")

        bundle = await builder.build_bundle()

        assert bundle.snapshot.operational.state == "degraded"
        assert bundle.snapshot.pipeline["redis"].writeable is False
        redis.ping.assert_called()
        assert any(
            degradation.component == "redis"
            and degradation.severity == "warning"
            for degradation in bundle.snapshot.degradations
        )

    async def test_unknown_incident_state_is_a_critical_block(
        self, mobile_deps
    ):
        builder = mobile_deps[0]
        builder._count_active_incidents = AsyncMock(
            spec=builder._count_active_incidents,
            side_effect=RuntimeError("event schema unavailable"),
        )

        bundle = await builder.build_bundle()

        assert bundle.snapshot.operational.state == "blocked"
        assert bundle.snapshot.operational.primary_reason == "incidents_unavailable"
        assert any(
            degradation.component == "incidents"
            and degradation.severity == "critical"
            for degradation in bundle.snapshot.degradations
        )

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

    async def test_gross_exposure_uses_absolute_long_and_short_values(
        self, mobile_deps
    ):
        builder, _, _, alpaca, _ = mobile_deps
        alpaca.get_account.return_value.equity = "10000"
        alpaca.get_account.return_value.cash = None
        long_position = MagicMock(
            symbol="LONG",
            qty="10",
            avg_entry_price="600",
            current_price="600",
            market_value="6000",
            unrealized_pl="0",
            unrealized_plpc="0",
        )
        short_position = MagicMock(
            symbol="SHORT",
            qty="-10",
            avg_entry_price="300",
            current_price="300",
            market_value="-3000",
            unrealized_pl="0",
            unrealized_plpc="0",
        )
        alpaca.get_all_positions.return_value = [
            long_position,
            short_position,
        ]

        bundle = await builder.build_bundle()

        assert bundle.snapshot.portfolio.gross_exposure == 0.9
        assert bundle.snapshot.portfolio.cash_pct is None
        assert bundle.snapshot.portfolio.unrealized_pnl == 0
        assert bundle.positions.summary.gross_exposure == 0.9

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
            "/api/mobile/v1/events?category=system&days=7",
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
                    VALUES ($1::varchar, 'decision', 'system', 'info', 'closed',
                            $2, $2, $2, $1::text)
                    """,
                    fingerprint,
                    occurred_at,
                )
        first = await client.get(
            "/api/mobile/v1/events?category=system&limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        cursor = first.json()["next_cursor"]
        second = await client.get(
            f"/api/mobile/v1/events?category=system&limit=1&cursor={cursor}",
            headers={"Authorization": f"Bearer {token}"},
        )
        tamper_index = len(cursor) // 2
        replacement = "A" if cursor[tamper_index] != "A" else "B"
        tampered = cursor[:tamper_index] + replacement + cursor[tamper_index + 1 :]
        invalid = await client.get(
            f"/api/mobile/v1/events?category=system&limit=1&cursor={tampered}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert first.status_code == 200
        assert cursor
        assert second.status_code == 200
        assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
        assert invalid.status_code == 400
        assert invalid.json()["error"]["code"] == "invalid_cursor"

    async def test_events_include_significant_lifecycle_and_exclude_skip_chatter(
        self, client, mobile_deps, store, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        now = datetime.now(timezone.utc)
        async with store.pool.acquire() as conn:
            buy_id = await conn.fetchval(
                """
                INSERT INTO execution_decisions (
                    tick_time, symbol, score, regime_mult, ema_pass,
                    decision, order_id
                )
                VALUES ($1, 'MOB03BUY', 0.5, 1.0, TRUE, 'BUY', 'mob03-buy')
                RETURNING id
                """,
                now,
            )
            skip_id = await conn.fetchval(
                """
                INSERT INTO execution_decisions (
                    tick_time, symbol, score, regime_mult, ema_pass, decision
                )
                VALUES ($1, 'MOB03SKIP', 0.1, 1.0, FALSE, 'SKIP_EMA')
                RETURNING id
                """,
                now,
            )
            trade_id = await conn.fetchval(
                """
                INSERT INTO trades (
                    symbol, entry_order_id, entry_price, entry_time,
                    entry_notional, score, regime_mult, qty, stop_strategy
                )
                VALUES (
                    'MOB03POS', 'mob03-fill', 10.0, $1,
                    100.0, 0.5, 1.0, 10.0, 'S1'
                )
                RETURNING id
                """,
                now,
            )
        try:
            response = await client.get(
                "/api/mobile/v1/events?category=trading&days=1&limit=200",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, response.text
            titles = {item["title"] for item in response.json()["items"]}
            assert "Decisione BUY · MOB03BUY" in titles
            assert "Ordine BUY inviato · MOB03BUY" in titles
            assert "Ordine BUY eseguito · MOB03POS" in titles
            assert "Posizione aperta · MOB03POS" in titles
            assert not any("MOB03SKIP" in title for title in titles)
        finally:
            async with store.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM trades WHERE id=$1",
                    trade_id,
                )
                await conn.execute(
                    "DELETE FROM execution_decisions WHERE id = ANY($1::bigint[])",
                    [buy_id, skip_id],
                )

    async def test_events_critical_filter_and_thirty_day_cap(
        self, client, mobile_deps, store, monitor_user, monitor_device
    ):
        token = _token(monitor_user, monitor_device)
        async with store.pool.acquire() as conn:
            for fingerprint, severity in (
                ("filter:critical", "critical"),
                ("filter:warning", "warning"),
            ):
                await conn.execute(
                    """
                    INSERT INTO mobile_events (
                        fingerprint, kind, category, severity, status,
                        occurred_at, first_observed_at, last_observed_at, title
                    )
                    VALUES (
                        $1::varchar, 'alert_incident', 'system', $2, 'open',
                        now(), now(), now(), $1::text
                    )
                    """,
                    fingerprint,
                    severity,
                )

        critical = await client.get(
            "/api/mobile/v1/events?category=critical&days=30",
            headers={"Authorization": f"Bearer {token}"},
        )
        invalid_days = await client.get(
            "/api/mobile/v1/events?days=31",
            headers={"Authorization": f"Bearer {token}"},
        )
        titles = {item["title"] for item in critical.json()["items"]}

        assert "filter:critical" in titles
        assert "filter:warning" not in titles
        assert invalid_days.status_code == 400
        assert invalid_days.json()["error"]["code"] == "invalid_days"
