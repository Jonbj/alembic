"""#294: il ranker deve spiegare la disposizione di ogni candidato."""

from __future__ import annotations

from datetime import timedelta

from src.models.signals import SentimentResult
from src.strategies.s4.config import S4Config
from src.strategies.s4.ranking import CrossSectionalRanker


def _signal(symbol: str, signal_id: int, score: float, confidence: float = 0.9):
    return SentimentResult(
        symbol=symbol,
        signal_id=signal_id,
        score=score,
        confidence=confidence,
        reasoning="test",
        model_id="ensemble:test",
    )


def test_diagnostics_conservano_rank_oltre_top_n_e_reason_dei_filtri():
    signals = [
        _signal("AAA", 1, 0.9),
        _signal("BBB", 2, 0.8),
        _signal("CCC", 3, 0.7),
        _signal("NEG", 4, -0.6),
        _signal("LOW", 5, 0.05),
        _signal("CONF", 6, 0.95, confidence=0.1),
    ]
    result = CrossSectionalRanker(
        S4Config(n_top=2, min_stocks=1, min_score=0.1, min_confidence=0.3)
    ).rank(signals)
    diagnostics = {row.signal_id: row for row in result.diagnostics}

    assert (diagnostics[1].rank, diagnostics[1].reason_code) == (1, "RANK_SELECTED")
    assert (diagnostics[2].rank, diagnostics[2].reason_code) == (2, "RANK_SELECTED")
    assert (diagnostics[3].rank, diagnostics[3].reason_code) == (3, "RANK_OUTSIDE_TOP_N")
    assert diagnostics[4].rank is None
    assert diagnostics[4].reason_code == "RANK_LONG_ONLY"
    assert diagnostics[5].reason_code == "RANK_MIN_SCORE"
    assert diagnostics[6].reason_code == "RANK_MIN_CONFIDENCE"


def test_diagnostics_segnalano_dedup_e_minimo_di_popolazione():
    old = _signal("AAA", 10, 0.9)
    new = _signal("AAA", 11, 0.8)
    new.generated_at = old.generated_at + timedelta(seconds=1)
    result = CrossSectionalRanker(S4Config(n_top=5, min_stocks=2)).rank([old, new])
    diagnostics = {row.signal_id: row for row in result.diagnostics}

    assert diagnostics[10].reason_code == "RANK_DEDUPLICATED"
    assert diagnostics[11].reason_code == "RANK_MIN_STOCKS"
    assert result.rankings == ()
