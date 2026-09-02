"""#151: fallback-only signals dropped by _filter_fallback_signals (#108) must leave a
trace in the Decision Log (decision=SKIP_FALLBACK), the same way _record_stale_drops
and _record_gate_drops do for their own drop paths. Before this, a symbol whose only
signal that day was a single-model fallback was indistinguishable from NO_NEWS
(ERIC/AMAT, 2026-07-27 — see docs/ALPHA_MISS_REPORT_2026-07-27.md §7).

The drop itself is correct policy (#108, post-SPCX); this only makes it visible instead
of silent — pure observability, no change to the BUY-ranking exclusion.
"""
from unittest.mock import MagicMock, patch

from src.workers import portfolio_scheduler


def _sig(symbol, score, confidence, model_id, gen, signal_id=None):
    from types import SimpleNamespace
    return SimpleNamespace(
        symbol=symbol, score=score, confidence=confidence, model_id=model_id,
        generated_at=gen, fallback_used=True, signal_id=signal_id,
    )


def _mock_redis(mock_cls, existing_keys=None):
    inst = MagicMock()
    inst.smembers.return_value = set(existing_keys or [])
    mock_cls.from_url.return_value = inst
    return inst


# ---------------------------------------------------------------------------
# The decision label is derived from src/portfolio/exit_classification.py, not
# hardcoded in the scheduler — one source of truth for the "fallback filtered"
# concept, two names only where the two levels require them (the in-memory
# disposition FALLBACK_FILTERED and the persisted decision SKIP_FALLBACK).
# ---------------------------------------------------------------------------


def test_skip_fallback_decision_label_is_derived_from_exit_classification():
    """The SKIP_* decision names live next to the FALLBACK_FILTERED disposition they
    describe, so the concept has one home and the scheduler imports rather than retypes
    the string (operator decision 2026-08-07 on issue #151)."""
    from src.portfolio import exit_classification

    assert exit_classification.DECISION_SKIP_FALLBACK == "SKIP_FALLBACK"
    # the scheduler must use that same constant, not a private literal
    assert portfolio_scheduler.DECISION_SKIP_FALLBACK is exit_classification.DECISION_SKIP_FALLBACK


def test_record_fallback_drops_writes_skip_fallback_per_signal():
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
    assert all(c.kwargs["decision"] == "SKIP_FALLBACK" for c in calls)
    assert {c.kwargs["symbol"] for c in calls} == {"ERIC", "AMAT"}
    eric = next(c for c in calls if c.kwargs["symbol"] == "ERIC")
    # reason carries model_id + score + confidence so the UI explains the drop
    assert "single:gpt-oss:20b-cloud" in eric.kwargs["reason"]
    assert "-0.080" in eric.kwargs["reason"]
    assert eric.kwargs["signal_score"] == -0.08
    assert eric.kwargs["regime_mult"] == 0.7


def test_record_fallback_drops_propagates_signal_id_when_present():
    """#406: SKIP_FALLBACK was 0/4 populated on 2026-08-27. The SentimentResult
    already carries a signal_id (set by write_signal() in pg_store); the function
    just needs to pass it through."""
    from datetime import datetime, timezone
    gen = datetime.now(timezone.utc)
    dropped = [
        _sig("ERIC", -0.08, 0.4, "single:gpt-oss:20b-cloud", gen, signal_id=7777),
        _sig("AMAT", 0.36, 0.6, "single:gpt-oss:20b-cloud", gen, signal_id=None),
    ]
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=0.7), \
         patch("redis.Redis") as mock_cls:
        _mock_redis(mock_cls)
        portfolio_scheduler._record_fallback_drops(dropped)

    calls_by_symbol = {c.kwargs["symbol"]: c for c in mock_pg.write_execution_decision.call_args_list}
    assert calls_by_symbol["ERIC"].kwargs["signal_id"] == 7777
    assert calls_by_symbol["AMAT"].kwargs["signal_id"] is None


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

# ---------------------------------------------------------------------------
# Perimetro (review di codex su PR #229): registrare SOLO i simboli il cui unico
# segnale era fallback. Un simbolo che ha ANCHE un segnale ensemble e' stato
# valutato normalmente, e marcarlo SKIP_FALLBACK e' una riga falsa — peggio del
# silenzio che questa modifica vuole togliere, perche' fa sembrare scartato un
# simbolo che e' stato considerato.
#
# Non e' un caso di scuola: sugli ultimi 7 giorni di produzione 54 simboli su 62
# con almeno un segnale fallback avevano anche un ensemble. L'87% delle righe
# sarebbe stato falso.
# ---------------------------------------------------------------------------


def _sig_ens(symbol, gen):
    from types import SimpleNamespace
    return SimpleNamespace(
        symbol=symbol, score=0.5, confidence=0.8, model_id="ensemble:x+y",
        generated_at=gen, fallback_used=False,
    )


def test_simbolo_con_anche_un_ensemble_non_viene_registrato():
    """AMD ha un fallback E un ensemble: e' stato valutato, non scartato."""
    from datetime import datetime, timezone
    gen = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
    mock_pg = MagicMock()
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=1.0), \
         patch("redis.Redis") as mock_redis_cls:
        _mock_redis(mock_redis_cls)
        portfolio_scheduler._record_fallback_drops(
            [_sig("AMD", 0.2, 0.5, "single:finbert", gen)],
            non_fallback_signals=[_sig_ens("AMD", gen)],
        )
    assert mock_pg.write_execution_decision.call_count == 0, (
        "AMD ha un segnale ensemble: non deve risultare scartato per fallback."
    )


def test_registra_solo_i_solo_fallback_di_un_lotto_misto():
    from datetime import datetime, timezone
    gen = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
    mock_pg = MagicMock()
    mock_pg.write_execution_decision.return_value = 1
    with patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch.object(portfolio_scheduler, "_get_regime_multiplier_from_redis", return_value=1.0), \
         patch("redis.Redis") as mock_redis_cls:
        _mock_redis(mock_redis_cls)
        portfolio_scheduler._record_fallback_drops(
            [_sig("AMD", 0.2, 0.5, "single:finbert", gen),
             _sig("ERIC", 0.3, 0.6, "single:finbert", gen)],
            non_fallback_signals=[_sig_ens("AMD", gen)],
        )
    simboli = [c.kwargs["symbol"] for c in mock_pg.write_execution_decision.call_args_list]
    assert simboli == ["ERIC"], f"atteso solo ERIC, ottenuto {simboli}"
