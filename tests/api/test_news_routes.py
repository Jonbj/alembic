"""Tests for news routes."""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_pg_store


def test_get_news_recent_returns_list():
    """GET /api/news/recent returns a list."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = [
        {"id": 1, "title": "AAPL beats Q3", "ticker": "AAPL",
         "source": "gdelt_gkg", "fetched_at": "2026-05-18T14:00:00+00:00"}
    ]
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    resp = tc.get("/api/news/recent")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["ticker"] == "AAPL"


def test_get_news_recent_passes_ticker_filter():
    """GET /api/news/recent?ticker=MSFT passes filter to pg_store."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    tc.get("/api/news/recent?ticker=MSFT&limit=20")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=20, ticker="MSFT", source=None)


def test_get_news_recent_passes_source_filter():
    """GET /api/news/recent?source=gdelt_gkg passes filter to pg_store."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    tc.get("/api/news/recent?source=gdelt_gkg")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=100, ticker=None, source="gdelt_gkg")


def test_get_news_recent_caps_limit():
    """GET /api/news/recent?limit=1000 caps at 500."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    tc = TestClient(app)
    tc.get("/api/news/recent?limit=1000")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=500, ticker=None, source=None)
