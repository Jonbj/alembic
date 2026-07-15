"""Tests for FastAPI endpoints."""

import os
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

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
    store.get_llm_models.return_value = None
    store.set_llm_models = MagicMock()
    store.get_current_weights_stored.return_value = None
    store.set_ensemble_weights = MagicMock()
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
    app.dependency_overrides.pop(get_redis_store, None)


@pytest.mark.asyncio
async def test_get_signal_no_auth_required(mock_redis_store):
    """Test GET /api/signals/{symbol} is publicly accessible (no API key needed)."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/signals/AAPL")
    assert resp.status_code in (200, 404)
    app.dependency_overrides.pop(get_redis_store, None)


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
    app.dependency_overrides.pop(get_redis_store, None)


@pytest.mark.asyncio
@pytest.mark.require_auth
async def test_admin_mode_requires_api_key(mock_redis_store):
    """Test POST /api/admin/mode requires valid API key."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/admin/mode", json={"mode": "paper"})
    assert resp.status_code == 403
    app.dependency_overrides.pop(get_redis_store, None)


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
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "paper"
    assert data["status"] == "ok"
    app.dependency_overrides.pop(get_redis_store, None)


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
@pytest.mark.require_auth
async def test_killswitch_requires_api_key(mock_redis_store):
    """Test POST /api/admin/killswitch requires valid API key."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/admin/killswitch")
    assert resp.status_code == 403
    app.dependency_overrides.pop(get_redis_store, None)


@pytest.mark.asyncio
async def test_killswitch_with_valid_key(mock_redis_store):
    """Test POST /api/admin/killswitch with valid API key activates killswitch."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/admin/killswitch")
    assert resp.status_code == 200
    data = resp.json()
    assert data["killswitch"] == "activated"
    assert data["mode"] == "halted"
    app.dependency_overrides.pop(get_redis_store, None)


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
        )
    assert resp.status_code == 400
    app.dependency_overrides.pop(get_redis_store, None)


@pytest.mark.asyncio
async def test_llm_models_canonicalizes_pair(mock_redis_store):
    """Test POST /api/admin/llm-models canonicalizes a comma-separated pair."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/admin/llm-models",
            json={"models": "gptoss,glm52"},
            headers={"Authorization": "Bearer test-api-key-for-testing-only-12345678"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_models"] == "glm52,gptoss"
    assert data["status"] == "ok"
    mock_redis_store.set_llm_models.assert_called_once_with("glm52,gptoss")
    app.dependency_overrides.pop(get_redis_store, None)


@pytest.mark.asyncio
async def test_llm_models_status_reports_registry(mock_redis_store):
    """Test GET /api/admin/status returns canonical selection and registry."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/admin/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_models"] == "all"  # fallback when Redis key is unset
    assert "llm_model_registry" in data
    assert any(m["key"] == "glm52" for m in data["llm_model_registry"]["models"])
    app.dependency_overrides.pop(get_redis_store, None)


@pytest.mark.asyncio
async def test_llm_models_resyncs_stale_ensemble_weights(mock_redis_store):
    """Test POST /api/admin/llm-models re-syncs stored weights when the new
    pair excludes a model referenced by the old weights."""
    mock_redis_store.get_current_weights_stored.return_value = {
        "weights": {"kimi-k2.6:cloud": 0.41, "qwen3.5:cloud": 0.59},
    }
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/admin/llm-models",
            json={"models": "glm52,gptoss"},
            headers={"Authorization": "Bearer test-api-key-for-testing-only-12345678"},
        )
    assert resp.status_code == 200
    assert resp.json()["llm_models"] == "glm52,gptoss"
    mock_redis_store.set_ensemble_weights.assert_called_once()
    applied = mock_redis_store.set_ensemble_weights.call_args.args[0]
    assert set(applied.keys()) == {"glm-5.2:cloud", "gpt-oss:20b-cloud"}
    assert all(w == pytest.approx(0.5) for w in applied.values())
    app.dependency_overrides.pop(get_redis_store, None)


@pytest.mark.asyncio
async def test_llm_models_keeps_weights_when_pair_unchanged(mock_redis_store):
    """Test POST /api/admin/llm-models does not touch weights when the stored
    weights already match the requested pair."""
    mock_redis_store.get_current_weights_stored.return_value = {
        "weights": {"glm-5.2:cloud": 0.5, "gpt-oss:20b-cloud": 0.5},
    }
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/admin/llm-models",
            json={"models": "glm52,gptoss"},
            headers={"Authorization": "Bearer test-api-key-for-testing-only-12345678"},
        )
    assert resp.status_code == 200
    mock_redis_store.set_ensemble_weights.assert_not_called()
    app.dependency_overrides.pop(get_redis_store, None)