"""Tests for strategy routes (Bug 3 — S3 parameters/null rendering)."""

from fastapi.testclient import TestClient

from src.api.main import app


def test_list_strategies_returns_list():
    """GET /api/strategies returns all strategies without auth."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    ids = [s["id"] for s in data]
    assert "s1" in ids
    assert "s3" in ids


def test_list_strategies_no_auth_required():
    """GET /api/strategies is publicly accessible (no API key needed)."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies")
    assert resp.status_code == 200


def test_get_s3_detail_returns_null_annual_return():
    """GET /api/strategies/s3 returns annual_return=null without crashing."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "s3"
    assert data["annual_return"] is None


def test_get_s3_detail_parameters_is_dict_with_lookbacks_array():
    """GET /api/strategies/s3 has parameters.lookbacks as array, not lookback_long/short."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s3")
    assert resp.status_code == 200
    params = resp.json()["parameters"]
    assert isinstance(params, dict)
    assert "lookbacks" in params
    assert isinstance(params["lookbacks"], list)
    assert "lookback_long" not in params
    assert "lookback_short" not in params


def test_get_s3_backtest_returns_empty_list():
    """GET /api/strategies/s3/backtest returns [] (S3 not in live portfolio)."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s3/backtest")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_s1_backtest_returns_equity_curve():
    """GET /api/strategies/s1/backtest returns non-empty equity curve."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s1/backtest")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "cumulative_return" in data[0]
    assert "drawdown" in data[0]


def test_get_s1_detail_parameters_has_lookback_fields():
    """GET /api/strategies/s1 has parameters with lookback_short and lookback_long."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s1")
    assert resp.status_code == 200
    params = resp.json()["parameters"]
    assert "lookback_short" in params
    assert "lookback_long" in params
    assert isinstance(params["lookback_short"], int)
    assert isinstance(params["lookback_long"], int)


def test_get_strategy_gates_s1_all_pass():
    """GET /api/strategies/s1/gates returns 5 gates all passing."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s1/gates")
    assert resp.status_code == 200
    gates = resp.json()
    assert len(gates) == 5
    assert all(g["passed"] for g in gates)


def test_get_strategy_gates_s3_has_failures():
    """GET /api/strategies/s3/gates has gate failures (robustness + stress)."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s3/gates")
    assert resp.status_code == 200
    gates = resp.json()
    failed = [g for g in gates if not g["passed"]]
    assert len(failed) == 2
    failed_ids = {g["gate_id"] for g in failed}
    assert "robustness" in failed_ids
    assert "stress" in failed_ids


def test_get_unknown_strategy_returns_404():
    """GET /api/strategies/unknown returns 404."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/unknown")
    assert resp.status_code == 404


def test_get_sensitivity_returns_grid():
    """GET /api/strategies/s1/sensitivity returns a non-empty list."""
    tc = TestClient(app)
    resp = tc.get("/api/strategies/s1/sensitivity")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "sharpe" in data[0]
    assert "lookback" in data[0]
