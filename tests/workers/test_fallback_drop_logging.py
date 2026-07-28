"""#151: fallback-only signals dropped by _filter_fallback_signals (#108) must leave a
trace in the Decision Log (decision=SKIP_FALLBACK_ONLY), the same way _record_stale_drops
and _record_gate_drops do for their own drop paths. Before this, a symbol whose only
signal that day was a single-model fallback was indistinguishable from NO_NEWS (ERIC/AMAT,
2026-07-27 — see docs/ALPHA_MISS_REPORT_2026-07-27.md §7)."""
from unittest.mock import MagicMock, patch

from src.workers import portfolio_scheduler


def _sig(symbol, score, confidence, model_id, gen):
    from types import SimpleNamespace
    return SimpleNamespace(
        symbol=symbol, score=score, confidence=confidence, model_id=model_id,
        generated_at=gen, fallback_used=True,
    )


def _mock_redis(mock_cls, existing_keys=None):
    inst = MagicMock()
    inst.smembers.return_value = set(existing_keys or [])
    mock_cls.from_url.return_value = inst
    return inst


def test_record_fallback_drops_writes_skip_fallback_only_per_signal():
    from datetime import datetime, timezone
    gen = datetime.now(timezone.utc)
    dropped = [
        _sig("ERIC", -0.08, 0.4, "single:gpt-oss:20b-cloud", gen),
        _sig("AMAT", 0.36, 0.6, "single:gpt-oss:20b-cloud", gen),
    ]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        _mock_redis(mock_cls)
        portfolio_scheduler._record_fallback_drops(dropped)

    assert mock_pg.write_execution_decision.call_count == 2
    calls = mock_pg.write_execution_decision.call_args_list
    assert all(c.kwargs["decision"] == "SKIP_FALLBACK_ONLY" for c in calls)
    assert {c.kwargs["symbol"] for c in calls} == {"ERIC", "AMAT"}
    eric = next(c for c in calls if c.kwargs["symbol"] == "ERIC")
    # reason carries model_id + score + confidence so the UI explains the drop
    assert "single:gpt-oss:20b-cloud" in eric.kwargs["reason"]
    assert "-0.080" in eric.kwargs["reason"]
    assert eric.kwargs["signal_score"] == -0.08
    assert eric.kwargs["regime_mult"] == 0.7


def test_record_fallback_drops_no_signals_is_noop():
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg):
        portfolio_scheduler._record_fallback_drops([])
    mock_pg.write_execution_decision.assert_not_called()


def test_record_fallback_drops_does_not_relog_already_logged_signal():
    """Same signal is re-fetched every 15-min cycle within the lookback window — must
    not write a duplicate execution_decisions row each time."""
    from datetime import datetime, timedelta, timezone
    gen = datetime.now(timezone.utc) - timedelta(hours=1)
    dropped = [_sig("ERIC", -0.08, 0.4, "single:gpt-oss:20b-cloud", gen)]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        _mock_redis(mock_cls, existing_keys=[portfolio_scheduler._stale_signal_key("ERIC", gen)])
        portfolio_scheduler._record_fallback_drops(dropped)

    mock_pg.write_execution_decision.assert_not_called()


def test_record_fallback_drops_marks_signal_logged_after_write():
    from datetime import datetime, timedelta, timezone
    gen = datetime.now(timezone.utc) - timedelta(hours=1)
    dropped = [_sig("ERIC", -0.08, 0.4, "single:gpt-oss:20b-cloud", gen)]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        inst = _mock_redis(mock_cls)
        portfolio_scheduler._record_fallback_drops(dropped)

    assert inst.sadd.called
    key_added = inst.sadd.call_args[0][-1]
    assert key_added == portfolio_scheduler._stale_signal_key("ERIC", gen)


def test_record_fallback_drops_fails_open_when_redis_unreachable():
    """If the idempotency store (Redis) is unreachable, log anyway — visibility matters
    more than avoiding a possible duplicate row (mirrors _record_stale_drops)."""
    from datetime import datetime, timezone
    dropped = [_sig("ERIC", -0.08, 0.4, "single:gpt-oss:20b-cloud", datetime.now(timezone.utc))]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        mock_cls.from_url.side_effect = ConnectionError("down")
        portfolio_scheduler._record_fallback_drops(dropped)

    mock_pg.write_execution_decision.assert_called_once()


def test_record_fallback_drops_is_fail_safe():
    """A store failure must not propagate — the trading cycle must not break."""
    from datetime import datetime, timezone
    dropped = [_sig("ERIC", -0.08, 0.4, "single:gpt-oss:20b-cloud", datetime.now(timezone.utc))]
    with patch("src.store.pg_store.PostgreSQLStore", side_effect=RuntimeError("db down")), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        _mock_redis(mock_cls)
        portfolio_scheduler._record_fallback_drops(dropped)  # must not raise
