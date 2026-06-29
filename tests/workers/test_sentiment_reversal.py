"""Tests for sentiment reversal exit logic."""
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
            "signal:AAPL:sentiment": json.dumps({"score": -0.5}),
            "signal:MSFT:sentiment": json.dumps({"score": 0.3}),
            "signal:GOOGL:sentiment": json.dumps({"score": -0.1}),
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
        "signal:AAPL:sentiment": json.dumps({"score": -0.5, "signal_id": 42}),
        "signal:MSFT:sentiment": json.dumps({"score": 0.3, "signal_id": 99}),
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
    mock_redis.get.return_value = json.dumps({"score": -0.6})  # no signal_id key

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
