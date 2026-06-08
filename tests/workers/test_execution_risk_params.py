"""Tests that _load_risk_params reads max_position_pct from trading.yaml (Issue #2)."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest
import yaml

from src.workers.execution import _load_risk_params, STOP_LOSS_PCT, MAX_DRAWDOWN_PCT, MAX_POSITION_PCT


def _write_yaml(path: str, stop_loss: float, drawdown: float, max_position_pct: float):
    with open(path, "w") as f:
        yaml.dump(
            {"risk": {
                "stop_loss": stop_loss,
                "portfolio_drawdown": drawdown,
                "max_position_pct": max_position_pct,
            }},
            f,
        )


def test_load_risk_params_reads_all_three_values():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as tf:
        yaml.dump({"risk": {"stop_loss": 0.03, "portfolio_drawdown": 0.07, "max_position_pct": 0.05}}, tf)
        name = tf.name
    try:
        with patch("src.workers.execution._TRADING_YAML", name):
            stop_loss, drawdown, max_pos = _load_risk_params()
        assert stop_loss == pytest.approx(0.03)
        assert drawdown == pytest.approx(0.07)
        assert max_pos == pytest.approx(0.05)
    finally:
        os.unlink(name)


def test_load_risk_params_falls_back_to_defaults():
    with patch("src.workers.execution._TRADING_YAML", "/nonexistent/trading.yaml"):
        stop_loss, drawdown, max_pos = _load_risk_params()
    assert stop_loss == pytest.approx(STOP_LOSS_PCT)
    assert drawdown == pytest.approx(MAX_DRAWDOWN_PCT)
    assert max_pos == pytest.approx(MAX_POSITION_PCT)
