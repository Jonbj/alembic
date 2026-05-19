"""Tests for LLM routes."""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_pg_store


def test_get_llm_feedback_returns_list():
    """GET /api/llm/feedback returns a list."""
    mock_pg = MagicMock()
    mock_pg.get_llm_feedback.return_value = [
        {"id": 1, "symbol": "AAPL", "model_id": "opus",
         "polarity": 0.7, "confidence": 0.85, "reasoning": "Good."}
    ]
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    resp = tc.get("/api/llm/feedback")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()[0]["model_id"] == "opus"


def test_get_llm_feedback_passes_ticker_filter():
    """GET /api/llm/feedback?ticker=AAPL passes filter to pg_store."""
    mock_pg = MagicMock()
    mock_pg.get_llm_feedback.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    tc.get("/api/llm/feedback?ticker=AAPL")
    app.dependency_overrides.clear()
    mock_pg.get_llm_feedback.assert_called_once_with(limit=50, ticker="AAPL", model_id=None)


def test_get_llm_feedback_passes_model_filter():
    """GET /api/llm/feedback?model_id=opus passes filter to pg_store."""
    mock_pg = MagicMock()
    mock_pg.get_llm_feedback.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    tc.get("/api/llm/feedback?model_id=opus")
    app.dependency_overrides.clear()
    mock_pg.get_llm_feedback.assert_called_once_with(limit=50, ticker=None, model_id="opus")


def test_get_llm_feedback_caps_limit():
    """GET /api/llm/feedback?limit=500 caps at 200."""
    mock_pg = MagicMock()
    mock_pg.get_llm_feedback.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    tc.get("/api/llm/feedback?limit=500")
    app.dependency_overrides.clear()
    mock_pg.get_llm_feedback.assert_called_once_with(limit=200, ticker=None, model_id=None)
