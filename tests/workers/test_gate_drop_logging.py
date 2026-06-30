"""Gate-dropped signals are surfaced in the Decision Log (decision=SKIP_THRESHOLD)."""
from unittest.mock import MagicMock, patch

import pandas as pd

from src.workers import portfolio_scheduler


def test_record_gate_drops_writes_skip_threshold_per_signal():
    dropped = pd.DataFrame([
        {"symbol": "AMAT", "score": 0.18},
        {"symbol": "VZ", "score": -0.05},
    ])
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7):
        portfolio_scheduler._record_gate_drops(dropped, threshold=0.35)

    assert mock_pg.write_execution_decision.call_count == 2
    calls = mock_pg.write_execution_decision.call_args_list
    assert all(c.kwargs["decision"] == "SKIP_THRESHOLD" for c in calls)
    assert {c.kwargs["symbol"] for c in calls} == {"AMAT", "VZ"}
    # reason carries the score and the threshold so the UI explains the drop
    amat = next(c for c in calls if c.kwargs["symbol"] == "AMAT")
    assert "0.180" in amat.kwargs["reason"] and "0.350" in amat.kwargs["reason"]
    assert amat.kwargs["signal_score"] == 0.18
    assert amat.kwargs["regime_mult"] == 0.7


def test_record_gate_drops_is_fail_safe():
    """A store failure must not propagate — the trading cycle must not break."""
    dropped = pd.DataFrame([{"symbol": "AMAT", "score": 0.18}])
    with patch("src.store.pg_store.PostgreSQLStore", side_effect=RuntimeError("db down")), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7):
        portfolio_scheduler._record_gate_drops(dropped, threshold=0.35)  # must not raise
