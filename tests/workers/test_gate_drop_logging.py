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


def _sig(symbol, score, gen):
    from types import SimpleNamespace
    return SimpleNamespace(symbol=symbol, score=score, generated_at=gen)


def _mock_redis(mock_cls, existing_keys=None):
    inst = MagicMock()
    inst.smembers.return_value = set(existing_keys or [])
    mock_cls.from_url.return_value = inst
    return inst


def test_record_stale_drops_logs_all_notable_signals_regardless_of_age():
    """SKIP_STALE logs any notable (|score| >= min_score) signal not yet logged —
    including deep-lookback ones. A late-day signal that only gets evaluated for the
    first time well past max_age (e.g. after an overnight gap with no running cycles)
    must not be silently dropped forever just because it's "old" the first time it's seen."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    stale = [
        _sig("AMAT", 0.42, now - timedelta(hours=4, minutes=30)),  # notable, just aged → logged
        _sig("VZ", 0.02, now - timedelta(hours=4, minutes=30)),    # near-zero → not logged
        _sig("INTC", 0.45, now - timedelta(hours=20)),             # notable, deep-stale, never seen before → logged
    ]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        _mock_redis(mock_cls)
        portfolio_scheduler._record_stale_drops(stale, max_age_hours=4, min_score=0.1)

    assert mock_pg.write_execution_decision.call_count == 2  # AMAT + INTC, not VZ
    symbols = {c.kwargs["symbol"] for c in mock_pg.write_execution_decision.call_args_list}
    assert symbols == {"AMAT", "INTC"}
    amat = next(c for c in mock_pg.write_execution_decision.call_args_list if c.kwargs["symbol"] == "AMAT")
    assert amat.kwargs["decision"] == "SKIP_STALE"
    assert "max_age 4h" in amat.kwargs["reason"]


def test_record_stale_drops_does_not_relog_already_logged_signal():
    """A stale signal already recorded in the Decision Log (same symbol+generated_at)
    must not be re-logged on every subsequent 15-min re-scan of the lookback window."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    gen = now - timedelta(hours=20)
    stale = [_sig("INTC", 0.45, gen)]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        _mock_redis(mock_cls, existing_keys=[portfolio_scheduler._stale_signal_key("INTC", gen)])
        portfolio_scheduler._record_stale_drops(stale, max_age_hours=4, min_score=0.1)

    mock_pg.write_execution_decision.assert_not_called()


def test_record_stale_drops_marks_signal_logged_after_write():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    gen = now - timedelta(hours=4, minutes=30)
    stale = [_sig("AMAT", 0.42, gen)]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        inst = _mock_redis(mock_cls)
        portfolio_scheduler._record_stale_drops(stale, max_age_hours=4, min_score=0.1)

    assert inst.sadd.called
    key_added = inst.sadd.call_args[0][-1]
    assert key_added == portfolio_scheduler._stale_signal_key("AMAT", gen)


def test_record_stale_drops_fails_open_when_redis_unreachable():
    """If the idempotency store (Redis) is unreachable, log anyway — visibility into a
    strong signal matters more than avoiding a possible duplicate row."""
    from datetime import datetime, timedelta, timezone
    stale = [_sig("AMAT", 0.42, datetime.now(timezone.utc) - timedelta(hours=20))]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        mock_cls.from_url.side_effect = ConnectionError("down")
        portfolio_scheduler._record_stale_drops(stale, max_age_hours=4, min_score=0.1)

    mock_pg.write_execution_decision.assert_called_once()


def test_record_stale_drops_is_fail_safe():
    from datetime import datetime, timedelta, timezone
    stale = [_sig("AMAT", 0.42, datetime.now(timezone.utc) - timedelta(hours=4, minutes=15))]
    with patch("src.store.pg_store.PostgreSQLStore", side_effect=RuntimeError("db down")), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        _mock_redis(mock_cls)
        portfolio_scheduler._record_stale_drops(stale, max_age_hours=4, min_score=0.1)  # no raise


def test_entry_threshold_baseline_is_the_gate_floor():
    """Fix 2: the order-gate floor is the config baseline (0.30), not min_score (0.10)."""
    assert portfolio_scheduler._load_entry_threshold_baseline() == 0.30
    assert portfolio_scheduler._ENTRY_THRESHOLD_BASELINE == 0.30
