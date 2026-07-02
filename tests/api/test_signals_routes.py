"""Tests for signal routes."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.api.deps import get_pg_store, get_redis_store
from src.api.main import app


def test_get_signals_by_news_id_uses_historical_news_trace():
    mock_pg = MagicMock()
    mock_pg.fetch_signals_for_news.return_value = [
        {
            "signal_id": 7,
            "symbol": "XLI",
            "score": 0.12,
            "confidence": 0.81,
            "reasoning": "Sector ETF article.",
            "model_id": "ensemble:test",
            "ensemble_std": 0.01,
            "fallback_used": False,
            "generated_at": "2026-06-30T22:03:33+00:00",
        }
    ]
    mock_pg.fetch_signal_decision_status.return_value = {}
    mock_redis = MagicMock()

    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[get_redis_store] = lambda: mock_redis
    tc = TestClient(app)
    resp = tc.get("/api/signals?news_id=1444")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["signal_id"] == 7
    assert data[0]["symbol"] == "XLI"
    assert data[0]["used_in_decision"] is False
    mock_pg.fetch_signals_for_news.assert_called_once_with(1444)
    mock_redis.read_sentiment.assert_not_called()


def test_get_signals_by_signal_id_uses_exact_historical_trace():
    mock_pg = MagicMock()
    mock_pg.fetch_signals_by_ids.return_value = [
        {
            "signal_id": 7,
            "symbol": "NVDA",
            "score": 0.42,
            "confidence": 0.76,
            "reasoning": "Exact signal.",
            "model_id": "ensemble:test",
            "ensemble_std": 0.02,
            "fallback_used": False,
            "generated_at": "2026-06-30T22:03:33+00:00",
        }
    ]
    mock_pg.fetch_signal_decision_status.return_value = {
        7: {
            "used_in_decision": True,
            "decision_at": "2026-06-30T22:15:00+00:00",
            "decision_type": "BUY",
        }
    }
    mock_redis = MagicMock()

    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[get_redis_store] = lambda: mock_redis
    tc = TestClient(app)
    resp = tc.get("/api/signals?signal_id=7")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["signal_id"] == 7
    assert data[0]["symbol"] == "NVDA"
    assert data[0]["used_in_decision"] is True
    assert data[0]["decision_type"] == "BUY"
    mock_pg.fetch_signals_by_ids.assert_called_once_with([7])
    mock_pg.fetch_signals_for_news.assert_not_called()
    mock_redis.read_sentiment.assert_not_called()
