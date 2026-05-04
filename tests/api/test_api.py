"""Tests for FastAPI endpoints."""

import os
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

# Set API key before importing app
os.environ["ADMIN_API_KEY"] = "test-api-key-for-testing-only-12345678"

from src.api.main import app, get_redis_store
from src.store.redis_store import RedisStore


def make_result(symbol: str = "AAPL") -> dict:
    """Create a sample sentiment result dict."""
    return {
        "symbol": symbol,
        "polarity": 0.6,
        "confidence": 0.8,
        "score": 0.48,
        "reasoning": "Strong beat.",
        "source_ids": ["n1"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": "ensemble",
        "worker_version": "1.0",
        "fallback_used": False,
        "worker_type": "ensemble_llm",
    }


@pytest.fixture
def mock_redis_store():
    """Create a mock RedisStore for testing."""
    from unittest.mock import MagicMock

    store = MagicMock()
    store.read_sentiment.return_value = make_result("AAPL")
    store.is_killswitch_active.return_value = False
    store.set_mode = MagicMock()
    store.activate_killswitch = MagicMock()
    return store


@pytest.mark.asyncio
async def test_get_signal_returns_sentiment(mock_redis_store):
    """Test GET /api/signals/{symbol} returns sentiment data."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/signals/AAPL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "AAPL"
    assert data["score"] == pytest.approx(0.48)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_signal_404_when_missing(mock_redis_store):
    """Test GET /api/signals/{symbol} returns 404 when signal not found."""
    mock_redis_store.read_sentiment.return_value = None
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/signals/UNKN")
    assert resp.status_code == 404
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_mode_requires_api_key(mock_redis_store):
    """Test POST /api/admin/mode requires valid API key."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/admin/mode", json={"mode": "paper"})
    assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_mode_with_valid_key(mock_redis_store):
    """Test POST /api/admin/mode with valid API key succeeds."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/admin/mode",
            json={"mode": "paper"},
            headers={"X-API-Key": "test-api-key-for-testing-only-12345678"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "paper"
    assert data["status"] == "ok"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test GET /api/health returns status ok."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_killswitch_requires_api_key(mock_redis_store):
    """Test POST /api/admin/killswitch requires valid API key."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/admin/killswitch")
    assert resp.status_code == 403
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_killswitch_with_valid_key(mock_redis_store):
    """Test POST /api/admin/killswitch with valid API key activates killswitch."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/admin/killswitch",
            headers={"X-API-Key": "test-api-key-for-testing-only-12345678"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["killswitch"] == "activated"
    assert data["mode"] == "halted"
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_mode_invalid_mode(mock_redis_store):
    """Test POST /api/admin/mode rejects invalid mode."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/admin/mode",
            json={"mode": "invalid_mode"},
            headers={"X-API-Key": "test-api-key-for-testing-only-12345678"},
        )
    assert resp.status_code == 400
    app.dependency_overrides.clear()
