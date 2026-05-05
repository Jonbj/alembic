"""Tests for GET /api/weights/suggestion and POST /api/weights/approve."""

import hashlib
import json
import os
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/test_db")

from src.api.main import app, get_pg_store, get_redis_store

API_KEY = "test-api-key-for-testing-only-12345678"

SAMPLE_SUGGESTION = {
    "suggested_weights": {
        "opus": 0.45,
        "qwen3.5:cloud": 0.35,
        "deepseek-v4-pro:cloud": 0.20,
    },
    "purified_icir": {
        "opus": 0.31,
        "qwen3.5:cloud": 0.18,
        "deepseek-v4-pro:cloud": 0.09,
    },
    "freeze_reason": "",
    "computed_at": "2026-05-04T08:00:00+00:00",
}


def make_redis_mock(suggestion=SAMPLE_SUGGESTION):
    store = MagicMock()
    store.get_weight_suggestion.return_value = suggestion
    store.set_ensemble_weights = MagicMock()
    store._r = MagicMock()
    return store


def make_pg_mock():
    store = MagicMock()
    store.log_weight_update.return_value = 42
    return store


@pytest.mark.asyncio
async def test_get_suggestion_ok():
    """GET /api/weights/suggestion returns 200 with payload + computed expires_at."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/weights/suggestion")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested_weights"]["opus"] == pytest.approx(0.45)
    assert "expires_at" in data
    assert data["expires_at"].startswith("2026-05-11")


@pytest.mark.asyncio
async def test_get_suggestion_not_found():
    """GET /api/weights/suggestion returns 404 when Redis has no suggestion."""
    redis = make_redis_mock(suggestion=None)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/weights/suggestion")
    app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_from_suggestion():
    """POST /approve with empty body applies suggestion, source='suggestion', returns log_id."""
    redis = make_redis_mock()
    pg = make_pg_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    app.dependency_overrides[get_pg_store] = lambda: pg
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "suggestion"
    assert data["log_id"] == 42
    redis.set_ensemble_weights.assert_called_once_with(
        SAMPLE_SUGGESTION["suggested_weights"], source="suggestion"
    )
    redis._r.delete.assert_called_once_with("ensemble:weights:suggestion:snapshot")
    pg.log_weight_update.assert_called_once()


@pytest.mark.asyncio
async def test_approve_frozen_returns_403():
    """POST /approve without override_weights when freeze_reason is set → 403."""
    frozen = {**SAMPLE_SUGGESTION, "freeze_reason": "VIX > 40"}
    redis = make_redis_mock(suggestion=frozen)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "VIX > 40" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_override_bypasses_freeze():
    """POST /approve with override_weights succeeds even when freeze_reason is set."""
    frozen = {**SAMPLE_SUGGESTION, "freeze_reason": "VIX > 40"}
    redis = make_redis_mock(suggestion=frozen)
    pg = make_pg_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    app.dependency_overrides[get_pg_store] = lambda: pg
    override = {"opus": 0.50, "qwen3.5:cloud": 0.30, "deepseek-v4-pro:cloud": 0.20}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": override},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["source"] == "override"
    assert resp.json()["applied_weights"] == override


@pytest.mark.asyncio
async def test_approve_override_invalid_sum():
    """POST /approve with weights summing to ≠ 1.0 → 422."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    bad = {"opus": 0.50, "qwen3.5:cloud": 0.30, "deepseek-v4-pro:cloud": 0.30}  # sum=1.1
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": bad},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert "sum to 1.0" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_override_cap_exceeded():
    """POST /approve with weight > 0.70 → 422."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    bad = {"opus": 0.80, "qwen3.5:cloud": 0.10, "deepseek-v4-pro:cloud": 0.10}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": bad},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert "cap" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_unknown_model():
    """POST /approve with an unknown model id → 422."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    bad = {"opus": 0.50, "gpt5": 0.50}  # gpt5 is not in config.MODEL_COSTS
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": bad},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert "gpt5" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_logs_approved_by_hash():
    """POST /approve stores approved_by as SHA-256[:8] of the api key, never raw."""
    redis = make_redis_mock()
    pg = make_pg_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    app.dependency_overrides[get_pg_store] = lambda: pg
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    call_kwargs = pg.log_weight_update.call_args.kwargs
    expected_hash = hashlib.sha256(API_KEY.encode()).hexdigest()[:8]
    assert call_kwargs["approved_by"] == expected_hash
    assert API_KEY not in str(call_kwargs)


@pytest.mark.asyncio
async def test_approve_no_suggestion_returns_404():
    """POST /approve when Redis has no suggestion → 404."""
    redis = make_redis_mock(suggestion=None)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_suggestion_invalid_computed_at_format():
    """GET /weights/suggestion returns 400 when computed_at is malformed."""
    bad_suggestion = {**SAMPLE_SUGGESTION, "computed_at": "not-an-iso-format"}
    redis = make_redis_mock(suggestion=bad_suggestion)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/weights/suggestion")
    app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert "Invalid computed_at" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_suggestion_missing_computed_at():
    """GET /weights/suggestion returns 400 when computed_at is missing."""
    bad_suggestion = {k: v for k, v in SAMPLE_SUGGESTION.items() if k != "computed_at"}
    redis = make_redis_mock(suggestion=bad_suggestion)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/weights/suggestion")
    app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert "computed_at" in resp.json()["detail"]
