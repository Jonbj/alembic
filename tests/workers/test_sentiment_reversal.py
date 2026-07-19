"""Tests for sentiment reversal exit logic."""
from datetime import datetime, timedelta, timezone


def _fresh_ts(minutes_ago: int = 5) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
import pytest
from unittest.mock import MagicMock


def _make_position(symbol: str, qty: float = 100.0) -> MagicMock:
    pos = MagicMock()
    pos.symbol = symbol
    pos.qty = str(qty)
    return pos


def test_reversal_sells_returns_symbols_with_negative_score():
    """Simboli con score < threshold devono essere restituiti per exit forzato."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells

    positions = [_make_position("AAPL"), _make_position("MSFT"), _make_position("GOOGL")]

    mock_redis = MagicMock()
    import json
    def redis_get(key):
        scores = {
            "signal:AAPL:sentiment": json.dumps({"score": -0.5, "generated_at": _fresh_ts()}),
            "signal:MSFT:sentiment": json.dumps({"score": 0.3, "generated_at": _fresh_ts()}),
            "signal:GOOGL:sentiment": json.dumps({"score": -0.1, "generated_at": _fresh_ts()}),
        }
        return scores.get(key)
    mock_redis.get.side_effect = redis_get

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "AAPL" in result
    assert "MSFT" not in result
    assert "GOOGL" not in result  # -0.1 > -0.20 threshold


def test_reversal_sells_skips_when_no_signal():
    """Simbolo senza segnale Redis → no exit forzato (fail-open)."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells

    positions = [_make_position("NVDA")]
    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "NVDA" not in result


def test_reversal_sells_handles_malformed_redis_value():
    """Valore Redis malformato → no exit forzato, nessuna eccezione."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells

    positions = [_make_position("TSLA")]
    mock_redis = MagicMock()
    mock_redis.get.return_value = "not-valid-json"

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "TSLA" not in result


def test_reversal_sells_returns_signal_metadata():
    """_sentiment_reversal_sells deve restituire {signal_id, score} per ogni simbolo venduto."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells
    import json

    positions = [_make_position("AAPL"), _make_position("MSFT")]
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: {
        "signal:AAPL:sentiment": json.dumps({"score": -0.5, "signal_id": 42, "generated_at": _fresh_ts()}),
        "signal:MSFT:sentiment": json.dumps({"score": 0.3, "signal_id": 99, "generated_at": _fresh_ts()}),
    }.get(key)

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "AAPL" in result
    assert result["AAPL"]["score"] == -0.5
    assert result["AAPL"]["signal_id"] == 42
    assert "MSFT" not in result


def test_reversal_sells_signal_id_optional():
    """signal_id può essere None se non presente nel payload Redis (segnale vecchio stile)."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells
    import json

    positions = [_make_position("NVDA")]
    mock_redis = MagicMock()
    mock_redis.get.return_value = json.dumps({"score": -0.6, "generated_at": _fresh_ts()})  # no signal_id key

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "NVDA" in result
    assert result["NVDA"]["signal_id"] is None
    assert result["NVDA"]["score"] == -0.6


def test_reversal_threshold_from_config():
    """SENTIMENT_REVERSAL_EXIT_THRESHOLD deve essere leggibile da config."""
    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(
        "os.environ", {"SENTIMENT_REVERSAL_EXIT_THRESHOLD": "-0.30"}
    ):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.SENTIMENT_REVERSAL_EXIT_THRESHOLD == -0.30


# ── #67: age-gate + consume-on-fire ──────────────────────────────────────────
# 2026-07-16: SOXX signal 3861 (15:45 UTC) was reused unchanged for 5 SELLs over
# 97 minutes. The reversal path must ignore stale signals (the BUY path already
# enforces max_age) and must never fire twice on the same signal.


def test_reversal_skips_stale_signal():
    """Segnale più vecchio di max_age_minutes → nessun force-sell."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells
    import json

    positions = [_make_position("SOXX")]
    mock_redis = MagicMock()
    stale_ts = (datetime.now(timezone.utc) - timedelta(minutes=90)).isoformat()
    mock_redis.get.side_effect = lambda key: {
        "signal:SOXX:sentiment": json.dumps(
            {"score": -0.42, "signal_id": 3861, "generated_at": stale_ts}
        ),
    }.get(key)

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.35, max_age_minutes=60)

    assert "SOXX" not in result


def test_reversal_passes_fresh_signal_within_age_gate():
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells
    import json

    positions = [_make_position("SOXX")]
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: {
        "signal:SOXX:sentiment": json.dumps(
            {"score": -0.42, "signal_id": 3861, "generated_at": _fresh_ts(10)}
        ),
    }.get(key)

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.35, max_age_minutes=60)

    assert "SOXX" in result


def test_reversal_skips_payload_without_generated_at():
    """Età sconosciuta = non affidabile → nessun force-sell (conservativo)."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells
    import json

    positions = [_make_position("SOXX")]
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: {
        "signal:SOXX:sentiment": json.dumps({"score": -0.42, "signal_id": 3861}),
    }.get(key)

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.35, max_age_minutes=60)

    assert "SOXX" not in result


def test_reversal_skips_already_consumed_signal():
    """Un segnale già consumato da un force-sell non deve ri-sparare."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells
    import json

    positions = [_make_position("SOXX")]
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: {
        "signal:SOXX:sentiment": json.dumps(
            {"score": -0.42, "signal_id": 3861, "generated_at": _fresh_ts(10)}
        ),
        "signal:SOXX:reversal_consumed": "3861",
    }.get(key)

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.35, max_age_minutes=60)

    assert "SOXX" not in result


def test_reversal_fires_when_consumed_marker_is_for_older_signal():
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells
    import json

    positions = [_make_position("SOXX")]
    mock_redis = MagicMock()
    mock_redis.get.side_effect = lambda key: {
        "signal:SOXX:sentiment": json.dumps(
            {"score": -0.42, "signal_id": 3900, "generated_at": _fresh_ts(10)}
        ),
        "signal:SOXX:reversal_consumed": "3861",
    }.get(key)

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.35, max_age_minutes=60)

    assert "SOXX" in result
    assert result["SOXX"]["identity"] == "3900"
