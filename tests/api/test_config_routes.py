"""Tests for config routes."""
import os

import pytest
from fastapi.testclient import TestClient
from unittest.mock import mock_open, patch

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")

from src.api.main import app
from src.api.auth import require_api_key

_SAMPLE_YAML = """
symbols:
  watchlist:
    - AAPL
    - MSFT
risk:
  portfolio_drawdown: 0.05
"""


@pytest.fixture(autouse=True)
def _override_auth():
    """Override auth for all config route tests."""
    app.dependency_overrides[require_api_key] = lambda: "test-key"
    yield
    app.dependency_overrides.pop(require_api_key, None)


def test_get_config_returns_yaml_as_dict():
    """GET /api/config returns trading.yaml as a dict."""
    with patch("builtins.open", mock_open(read_data=_SAMPLE_YAML)):
        tc = TestClient(app)
        resp = tc.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "symbols" in data
    assert "AAPL" in data["symbols"]["watchlist"]


def test_get_config_requires_api_key():
    """GET /api/config without API key override returns 403."""
    app.dependency_overrides.pop(require_api_key, None)
    with patch("builtins.open", mock_open(read_data=_SAMPLE_YAML)):
        tc = TestClient(app)
        resp = tc.get("/api/config")
    assert resp.status_code == 403


def test_post_config_requires_api_key():
    """POST /api/config without API key override returns 403."""
    app.dependency_overrides.pop(require_api_key, None)
    tc = TestClient(app)
    resp = tc.post("/api/config", json={"symbols": {"watchlist": ["AAPL"]}})
    assert resp.status_code == 403


def test_post_config_updates_watchlist(tmp_path):
    """POST /api/config updates config/trading.yaml."""
    yaml_file = tmp_path / "trading.yaml"
    yaml_file.write_text(_SAMPLE_YAML)

    with patch("src.api.routes.config_routes._CONFIG_PATH", str(yaml_file)):
        tc = TestClient(app)
        resp = tc.post(
            "/api/config",
            json={"symbols": {"watchlist": ["AAPL", "MSFT", "NVDA"]}},
        )
    assert resp.status_code == 200
    assert "NVDA" in yaml_file.read_text()


def test_post_config_deep_merges_nested_dict(tmp_path):
    """POST /api/config deep merges nested dicts."""
    yaml_file = tmp_path / "trading.yaml"
    yaml_file.write_text("""
symbols:
  watchlist:
    - AAPL
risk:
  portfolio_drawdown: 0.05
  max_position_pct: 0.10
""")

    with patch("src.api.routes.config_routes._CONFIG_PATH", str(yaml_file)):
        tc = TestClient(app)
        resp = tc.post(
            "/api/config",
            json={"risk": {"max_position_pct": 0.20}},
        )
    assert resp.status_code == 200
    content = yaml_file.read_text()
    assert "portfolio_drawdown: 0.05" in content
    assert "max_position_pct: 0.2" in content