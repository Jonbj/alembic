"""B13 (FUNCTIONAL_REVIEW_2026-07-03 §6.1): the drawdown cap must come from
config/trading.yaml (risk.portfolio_drawdown), not from a hardcoded constant."""

from unittest.mock import mock_open, patch


def test_load_risk_config_includes_portfolio_drawdown_from_yaml():
    from src.workers import portfolio_scheduler as ps
    yaml_text = (
        "risk:\n"
        "  portfolio_drawdown: 0.05\n"
        "  max_portfolio_exposure: 0.50\n"
        "  max_position_pct: 0.10\n"
        "  stop_loss: 0.02\n"
    )
    with patch("builtins.open", mock_open(read_data=yaml_text)):
        cfg = ps._load_risk_config()
    assert cfg["portfolio_drawdown"] == 0.05


def test_load_risk_config_portfolio_drawdown_failsafe_default():
    """On unreadable yaml the default must be the CONFIG value (0.05), not 0.10."""
    from src.workers import portfolio_scheduler as ps
    with patch("builtins.open", side_effect=OSError("boom")):
        cfg = ps._load_risk_config()
    assert cfg["portfolio_drawdown"] == 0.05


def test_no_hardcoded_drawdown_constant():
    """The 0.10 module-level constant must be gone."""
    from src.workers import portfolio_scheduler as ps
    assert not hasattr(ps, "_MAX_DRAWDOWN_PCT")
