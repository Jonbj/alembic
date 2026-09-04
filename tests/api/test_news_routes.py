"""Tests for news routes."""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.auth import require_api_key
from src.api.deps import get_pg_store

_skip_auth = lambda: "test-key"


def test_get_news_recent_returns_list():
    """GET /api/news/recent returns a list."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = [
        {"id": 1, "title": "AAPL beats Q3", "ticker": "AAPL",
         "source": "gdelt_gkg", "fetched_at": "2026-05-18T14:00:00+00:00"}
    ]
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth
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
    app.dependency_overrides[require_api_key] = _skip_auth
    tc = TestClient(app)
    tc.get("/api/news/recent?ticker=MSFT&limit=20")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=20, ticker="MSFT", source=None, news_id=None)


def test_get_news_recent_passes_source_filter():
    """GET /api/news/recent?source=gdelt_gkg passes filter to pg_store."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth
    tc = TestClient(app)
    tc.get("/api/news/recent?source=gdelt_gkg")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=100, ticker=None, source="gdelt_gkg", news_id=None)


def test_get_news_recent_caps_limit():
    """GET /api/news/recent?limit=1000 caps at 500."""
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth
    tc = TestClient(app)
    tc.get("/api/news/recent?limit=1000")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=500, ticker=None, source=None, news_id=None)


def test_get_news_recent_passes_news_id_filter():
    """GET /api/news/recent?news_id=9279 deep-links a single article.

    Regression: the causal trace panel (SignalTraceLinks) linked to /news
    with only the ticker, dumping the operator into the whole feed with no
    way to tell which article a signal/decision/order traced back to.
    """
    mock_pg = MagicMock()
    mock_pg.get_news_recent.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth
    tc = TestClient(app)
    tc.get("/api/news/recent?news_id=9279")
    app.dependency_overrides.clear()
    mock_pg.get_news_recent.assert_called_once_with(limit=100, ticker=None, source=None, news_id=9279)


def test_get_news_source_quality_returns_list():
    """GET /api/news/source-quality returns per-source rows."""
    mock_pg = MagicMock()
    mock_pg.get_news_source_quality.return_value = [
        {"source": "finnhub", "news_count": 10, "signals_count": 8}
    ]
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth
    tc = TestClient(app)
    resp = tc.get("/api/news/source-quality?days=30")
    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["source"] == "finnhub"
    mock_pg.get_news_source_quality.assert_called_once_with(days=30)


def test_get_news_source_quality_bounds_days():
    """GET /api/news/source-quality bounds days to the supported window."""
    mock_pg = MagicMock()
    mock_pg.get_news_source_quality.return_value = []
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth
    tc = TestClient(app)
    tc.get("/api/news/source-quality?days=999")
    app.dependency_overrides.clear()
    mock_pg.get_news_source_quality.assert_called_once_with(days=365)
