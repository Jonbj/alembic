"""P0-08 — Config validation server-side bounds.

Problem: POST /api/config accepts any value — risk controls can be dismantled
via a single API call with no validation. Examples:
- risk.stop_loss=0.0 → no stop-loss
- risk.max_position_pct=1.0 → 100% position in one stock
- risk.vix_spike=9999.0 → VIX kill-switch never fires

Fix: _validate_risk_params() raises HTTPException 422 for out-of-bound values.
Bounds are conservative: stop_loss in [0.001, 0.10], max_position_pct in [0.01, 0.20], etc.
"""

from __future__ import annotations

import pytest


class TestConfigRejectsOutOfBound:
    """Server must reject risk parameter values outside safe bounds."""

    def test_rejects_stop_loss_zero(self):
        """stop_loss=0.0 removes all downside protection — must be rejected."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="stop_loss"):
            _validate_risk_params({"risk": {"stop_loss": 0.0}})

    def test_rejects_stop_loss_above_cap(self):
        """stop_loss > 0.10 (10%) is unrealistic and would cause excessive churn."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="stop_loss"):
            _validate_risk_params({"risk": {"stop_loss": 0.5}})

    def test_rejects_max_position_above_cap(self):
        """max_position_pct > 0.20 (20%) violates concentration limit."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="max_position_pct"):
            _validate_risk_params({"risk": {"max_position_pct": 0.50}})

    def test_rejects_max_position_zero(self):
        """max_position_pct=0.0 means no positions can ever be opened."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="max_position_pct"):
            _validate_risk_params({"risk": {"max_position_pct": 0.0}})

    def test_rejects_max_portfolio_exposure_above_one(self):
        """max_portfolio_exposure > 1.0 would allow leveraging beyond portfolio value."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="max_portfolio_exposure"):
            _validate_risk_params({"risk": {"max_portfolio_exposure": 1.5}})

    def test_rejects_vix_spike_too_low(self):
        """vix_spike < 10 would trigger kill-switch on routine volatility."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="vix_spike"):
            _validate_risk_params({"risk": {"vix_spike": 5.0}})

    def test_rejects_vix_spike_too_high(self):
        """vix_spike > 100 effectively disables the VIX kill-switch trigger."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="vix_spike"):
            _validate_risk_params({"risk": {"vix_spike": 200.0}})

    def test_rejects_portfolio_drawdown_zero(self):
        """portfolio_drawdown=0.0 fires kill-switch on any loss — pathological."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="portfolio_drawdown"):
            _validate_risk_params({"risk": {"portfolio_drawdown": 0.0}})

    def test_rejects_portfolio_drawdown_above_cap(self):
        """portfolio_drawdown > 0.20 (20%) allows catastrophic losses before halting."""
        from src.api.routes.config_routes import _validate_risk_params
        with pytest.raises(Exception, match="portfolio_drawdown"):
            _validate_risk_params({"risk": {"portfolio_drawdown": 0.50}})


class TestConfigAcceptsValidValues:
    """Valid risk parameter values must pass without exception."""

    def test_accepts_valid_stop_loss(self):
        from src.api.routes.config_routes import _validate_risk_params
        _validate_risk_params({"risk": {"stop_loss": 0.02}})  # 2% — typical

    def test_accepts_valid_max_position(self):
        from src.api.routes.config_routes import _validate_risk_params
        _validate_risk_params({"risk": {"max_position_pct": 0.10}})  # 10%

    def test_accepts_valid_vix_spike(self):
        from src.api.routes.config_routes import _validate_risk_params
        _validate_risk_params({"risk": {"vix_spike": 40.0}})  # typical

    def test_accepts_non_risk_changes_without_validation(self):
        """Non-risk config changes (symbols, schedule) must not be rejected."""
        from src.api.routes.config_routes import _validate_risk_params
        _validate_risk_params({"symbols": {"watchlist": ["AAPL", "MSFT"]}})

    def test_accepts_empty_updates(self):
        """Empty update dict must not raise."""
        from src.api.routes.config_routes import _validate_risk_params
        _validate_risk_params({})

    def test_accepts_partial_risk_update_within_bounds(self):
        """Partial risk update with valid values must pass."""
        from src.api.routes.config_routes import _validate_risk_params
        _validate_risk_params({"risk": {"stop_loss": 0.03, "max_position_pct": 0.05}})
