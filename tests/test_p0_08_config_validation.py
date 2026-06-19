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


class TestRiskWeakeningDetection:
    """_detect_risk_weakening identifies fields moved toward the unsafe direction."""

    def test_detects_stop_loss_increase_as_weakening(self):
        """Raising stop_loss (allows more loss per trade) is a weakening change."""
        from src.api.routes.config_routes import _detect_risk_weakening
        weakened = _detect_risk_weakening(
            current_risk={"stop_loss": 0.02},
            new_risk={"stop_loss": 0.05},
        )
        assert "stop_loss" in weakened

    def test_detects_portfolio_drawdown_increase_as_weakening(self):
        """Raising portfolio_drawdown (kill-switch fires later) is weakening."""
        from src.api.routes.config_routes import _detect_risk_weakening
        weakened = _detect_risk_weakening(
            current_risk={"portfolio_drawdown": 0.05},
            new_risk={"portfolio_drawdown": 0.15},
        )
        assert "portfolio_drawdown" in weakened

    def test_does_not_flag_tightening_as_weakening(self):
        """Decreasing stop_loss (tighter control) is not weakening."""
        from src.api.routes.config_routes import _detect_risk_weakening
        weakened = _detect_risk_weakening(
            current_risk={"stop_loss": 0.05},
            new_risk={"stop_loss": 0.02},
        )
        assert "stop_loss" not in weakened

    def test_does_not_flag_unchanged_fields(self):
        """Fields not in the update are not flagged."""
        from src.api.routes.config_routes import _detect_risk_weakening
        weakened = _detect_risk_weakening(
            current_risk={"stop_loss": 0.02, "portfolio_drawdown": 0.05},
            new_risk={"stop_loss": 0.02},  # same value, not increasing
        )
        assert not weakened


class TestRiskWeakeningApproval:
    """Weakening risk controls requires a reason; tightening does not."""

    def test_weakening_without_reason_raises(self):
        """Increasing stop_loss without a reason raises 422."""
        from fastapi import HTTPException
        from src.api.routes.config_routes import _require_reason_for_weakening
        current = {"risk": {"stop_loss": 0.02}}
        updates = {"risk": {"stop_loss": 0.05}}  # increase → weakening
        with pytest.raises(HTTPException) as exc_info:
            _require_reason_for_weakening(current, updates, reason=None)
        assert exc_info.value.status_code == 422
        assert "stop_loss" in exc_info.value.detail

    def test_weakening_with_reason_passes(self):
        """Increasing stop_loss with a reason is allowed."""
        from src.api.routes.config_routes import _require_reason_for_weakening
        current = {"risk": {"stop_loss": 0.02}}
        updates = {"risk": {"stop_loss": 0.05}}
        _require_reason_for_weakening(current, updates, reason="regime change approved by PO")

    def test_tightening_without_reason_passes(self):
        """Decreasing stop_loss (safer) does not require a reason."""
        from src.api.routes.config_routes import _require_reason_for_weakening
        current = {"risk": {"stop_loss": 0.05}}
        updates = {"risk": {"stop_loss": 0.02}}
        _require_reason_for_weakening(current, updates, reason=None)

    def test_enabling_auto_recovery_requires_reason(self):
        """Setting killswitch_recovery.enabled=true is a weakening change."""
        from fastapi import HTTPException
        from src.api.routes.config_routes import _require_reason_for_weakening
        current = {"risk": {"killswitch_recovery": {"enabled": False}}}
        updates = {"risk": {"killswitch_recovery": {"enabled": True}}}
        with pytest.raises(HTTPException) as exc_info:
            _require_reason_for_weakening(current, updates, reason=None)
        assert exc_info.value.status_code == 422


class TestConfigAuditLog:
    """POST /api/config must write an audit row capturing old and new risk values."""

    def test_audit_log_written_on_config_change(self):
        """update_config writes a 'UPDATE' audit row after persisting changes."""
        from unittest.mock import MagicMock, mock_open, patch
        from src.api.routes.config_routes import update_config

        current_config = {"risk": {"stop_loss": 0.02}}
        mock_pg = MagicMock()

        with patch("src.api.routes.config_routes._read_config", return_value=current_config), \
             patch("builtins.open", mock_open()), \
             patch("yaml.dump"):
            update_config(
                updates={"risk": {"stop_loss": 0.01}},  # tightening — no reason needed
                api_key="test_key",
                pg=mock_pg,
                reason=None,
            )

        mock_pg.write_audit_log.assert_called_once()

    def test_audit_log_captures_old_and_new_risk(self):
        """Audit row details must include old_risk and new_risk."""
        from unittest.mock import MagicMock, mock_open, patch
        from src.api.routes.config_routes import update_config

        current_config = {"risk": {"stop_loss": 0.05}}
        mock_pg = MagicMock()

        with patch("src.api.routes.config_routes._read_config", return_value=current_config), \
             patch("builtins.open", mock_open()), \
             patch("yaml.dump"):
            update_config(
                updates={"risk": {"stop_loss": 0.02}},
                api_key="test_key",
                pg=mock_pg,
                reason=None,
            )

        call_kwargs = mock_pg.write_audit_log.call_args[1]
        details = call_kwargs.get("details") or {}
        assert "old_risk" in details, "Audit must capture old risk values"
        assert "new_risk" in details, "Audit must capture new risk values"
        assert details["old_risk"].get("stop_loss") == 0.05

    def test_audit_failure_does_not_block_config_update(self):
        """If audit write fails, config update must still succeed."""
        from unittest.mock import MagicMock, mock_open, patch
        from src.api.routes.config_routes import update_config

        mock_pg = MagicMock()
        mock_pg.write_audit_log.side_effect = Exception("DB down")

        with patch("src.api.routes.config_routes._read_config", return_value={}), \
             patch("builtins.open", mock_open()), \
             patch("yaml.dump"):
            result = update_config(
                updates={"symbols": {"watchlist": ["AAPL"]}},
                api_key="test_key",
                pg=mock_pg,
                reason=None,
            )
        assert isinstance(result, dict)
