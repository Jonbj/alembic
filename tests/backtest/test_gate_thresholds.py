"""B12 (review §8.1): gate defaults must be real thresholds, not 0.0 —
a gate that cannot fail is not a gate. Values from the master roadmap:
Sharpe > 0.5 in-sample, OOS Sharpe > 0.3 (conservative starting point)."""

import inspect


def test_runner_default_min_sharpe_is_meaningful():
    from src.backtest.gates.runner import GateConfig
    cfg = GateConfig()
    assert cfg.min_sharpe >= 0.5
    assert cfg.min_oos_sharpe >= 0.3


def test_gate1_default_min_sharpe_is_meaningful():
    from src.backtest.gates.gate_1_significance import gate_1_significance
    sig = inspect.signature(gate_1_significance)
    assert sig.parameters["min_sharpe"].default >= 0.5


def test_gate2_default_min_oos_sharpe_is_meaningful():
    from src.backtest.gates.gate_2_walkforward import gate_2_walkforward
    sig = inspect.signature(gate_2_walkforward)
    assert sig.parameters["min_oos_sharpe"].default >= 0.3
