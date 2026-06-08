"""T-401: S4 cross-sectional ranking tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.models.signals import SentimentResult
from src.strategies.s4.config import S4Config
from src.strategies.s4.ranking import CrossSectionalRanker, RankedTicker, RankingResult
from src.backtest.engine.types import RebalanceFrequency


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sig(symbol: str, score: float, confidence: float, **kwargs) -> SentimentResult:
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=confidence,
        reasoning="test",
        model_id="test",
        **kwargs,
    )


def _make_signals(n: int, base_score: float = 0.5, base_conf: float = 0.8) -> list[SentimentResult]:
    """Create n signals with slightly varying scores."""
    return [
        _sig(f"T{i:02d}", score=base_score - i * 0.01, confidence=base_conf)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------

def test_s4_config_defaults():
    cfg = S4Config()
    assert cfg.strategy_id == "S4"
    assert cfg.n_top == 5
    assert cfg.bucket_pct == 0.10
    assert cfg.min_confidence == 0.3
    assert cfg.min_score == 0.1
    assert cfg.min_stocks == 3
    assert cfg.rebalance_frequency == RebalanceFrequency.WEEKLY


# ---------------------------------------------------------------------------
# Basic ranking: top 5 from 10 signals
# ---------------------------------------------------------------------------

def test_rank_top5_from_10():
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    assert result.n_selected == 5
    assert len(result.rankings) == 5
    # Ranks are 1-based
    assert [r.rank for r in result.rankings] == [1, 2, 3, 4, 5]
    # First ticker has highest effective_strength
    assert result.rankings[0].ticker == "T00"
    assert result.rankings[4].ticker == "T04"


def test_rank_descending_effective_strength():
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    strengths = [r.effective_strength for r in result.rankings]
    assert strengths == sorted(strengths, reverse=True)


# ---------------------------------------------------------------------------
# Equal weight calculation: 0.10 / 5 = 0.02 per ticker
# ---------------------------------------------------------------------------

def test_equal_weight_calculation():
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    expected_weight = pytest.approx(1.0 / 5, rel=1e-9)
    for r in result.rankings:
        assert r.weight == expected_weight


def test_bucket_weight_preserved():
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    assert result.bucket_weight == pytest.approx(0.10)


def test_custom_bucket_pct():
    signals = _make_signals(10)
    ranker = CrossSectionalRanker(S4Config(bucket_pct=0.20))
    result = ranker.rank(signals)

    # bucket_pct no longer affects per-ticker weight; weights are 1.0 / n
    for r in result.rankings:
        assert r.weight == pytest.approx(1.0 / 5, rel=1e-9)


# ---------------------------------------------------------------------------
# Filter: min_confidence
# ---------------------------------------------------------------------------

def test_filter_by_min_confidence():
    high_conf = [_sig(f"H{i}", score=0.5, confidence=0.9) for i in range(4)]
    low_conf = [_sig(f"L{i}", score=0.9, confidence=0.1) for i in range(10)]
    signals = high_conf + low_conf

    ranker = CrossSectionalRanker(S4Config(min_confidence=0.5, min_stocks=3))
    result = ranker.rank(signals)

    assert all(r.ticker.startswith("H") for r in result.rankings)
    assert result.n_selected == 4


# ---------------------------------------------------------------------------
# Filter: min_score
# ---------------------------------------------------------------------------

def test_filter_by_min_score():
    strong = [_sig(f"S{i}", score=0.8, confidence=0.9) for i in range(5)]
    weak = [_sig(f"W{i}", score=0.05, confidence=0.9) for i in range(10)]
    signals = strong + weak

    ranker = CrossSectionalRanker(S4Config(min_score=0.15))
    result = ranker.rank(signals)

    assert all(r.ticker.startswith("S") for r in result.rankings)


# ---------------------------------------------------------------------------
# Too few stocks → empty result (skip)
# ---------------------------------------------------------------------------

def test_too_few_stocks_returns_empty():
    # Only 2 signals pass filters, min_stocks=3
    signals = _make_signals(2)
    ranker = CrossSectionalRanker(S4Config(min_stocks=3))
    result = ranker.rank(signals)

    assert result.n_selected == 0
    assert len(result.rankings) == 0


def test_exactly_min_stocks_passes():
    signals = _make_signals(3)
    ranker = CrossSectionalRanker(S4Config(n_top=3, min_stocks=3))
    result = ranker.rank(signals)

    assert result.n_selected == 3


# ---------------------------------------------------------------------------
# Long-only: all negative scores → skip
# ---------------------------------------------------------------------------

def test_all_negative_scores_returns_empty():
    signals = [_sig(f"T{i}", score=-0.5, confidence=0.9) for i in range(10)]
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    assert result.n_selected == 0
    assert len(result.rankings) == 0


def test_mixed_signs_only_positive_selected():
    positive = [_sig(f"P{i}", score=0.5 + i * 0.05, confidence=0.8) for i in range(5)]
    negative = [_sig(f"N{i}", score=-0.5, confidence=0.8) for i in range(5)]
    signals = positive + negative

    ranker = CrossSectionalRanker(S4Config(n_top=5))
    result = ranker.rank(signals)

    assert all(r.ticker.startswith("P") for r in result.rankings)


# ---------------------------------------------------------------------------
# Ties
# ---------------------------------------------------------------------------

def test_ties_all_selected_equal_weight():
    # All 5 signals have identical effective_strength
    signals = [_sig(f"T{i}", score=0.5, confidence=0.8) for i in range(5)]
    ranker = CrossSectionalRanker(S4Config(n_top=5))
    result = ranker.rank(signals)

    assert result.n_selected == 5
    weights = [r.weight for r in result.rankings]
    assert all(w == pytest.approx(1.0 / 5, rel=1e-9) for w in weights)


# ---------------------------------------------------------------------------
# Fewer candidates than n_top
# ---------------------------------------------------------------------------

def test_fewer_candidates_than_n_top():
    # Only 4 pass filters, n_top=5, min_stocks=3
    signals = _make_signals(4)
    ranker = CrossSectionalRanker(S4Config(n_top=5, min_stocks=3))
    result = ranker.rank(signals)

    # Should select all 4 available (4 >= min_stocks=3)
    assert result.n_selected == 4
    # weight = 1.0 / 4 = 0.25
    for r in result.rankings:
        assert r.weight == pytest.approx(1.0 / 4, rel=1e-9)


# ---------------------------------------------------------------------------
# Deduplication: keep most recent signal per ticker
# ---------------------------------------------------------------------------

def test_deduplication_keeps_most_recent():
    ts_old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ts_new = datetime(2024, 6, 1, tzinfo=timezone.utc)

    old_sig = _sig("AAPL", score=0.9, confidence=0.9, generated_at=ts_old)
    new_sig = _sig("AAPL", score=0.2, confidence=0.9, generated_at=ts_new)
    other = [_sig(f"T{i}", score=0.5, confidence=0.8) for i in range(4)]
    signals = [old_sig, new_sig] + other

    ranker = CrossSectionalRanker(S4Config(n_top=5))
    result = ranker.rank(signals)

    aapl_ranked = next((r for r in result.rankings if r.ticker == "AAPL"), None)
    if aapl_ranked is not None:
        # Score should be from the newest signal (0.2), not old (0.9)
        assert aapl_ranked.score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# RankingResult helpers
# ---------------------------------------------------------------------------

def test_ranking_result_tickers_property():
    signals = _make_signals(5)
    ranker = CrossSectionalRanker(S4Config(n_top=5))
    result = ranker.rank(signals)

    assert result.tickers == ["T00", "T01", "T02", "T03", "T04"]


def test_ranking_result_weights_property():
    signals = _make_signals(5)
    ranker = CrossSectionalRanker(S4Config(n_top=5))
    result = ranker.rank(signals)

    weights = result.weights
    assert len(weights) == 5
    for v in weights.values():
        assert v == pytest.approx(1.0 / 5, rel=1e-9)


# ---------------------------------------------------------------------------
# as_of timestamp propagated
# ---------------------------------------------------------------------------

def test_as_of_timestamp():
    signals = _make_signals(5)
    ts = datetime(2025, 1, 15, tzinfo=timezone.utc)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals, as_of=ts)

    assert result.as_of == ts


# ---------------------------------------------------------------------------
# effective_strength = score × confidence
# ---------------------------------------------------------------------------

def test_effective_strength_formula():
    sig = _sig("TSLA", score=0.6, confidence=0.8)
    ranker = CrossSectionalRanker(S4Config(n_top=1, min_stocks=1))
    result = ranker.rank([sig])

    assert result.rankings[0].effective_strength == pytest.approx(0.6 * 0.8)


# ---------------------------------------------------------------------------
# Sleeve-local weights must sum to 1.0 for correct orchestrator scaling
# ---------------------------------------------------------------------------

def test_sleeve_local_weights_sum_to_one():
    """Sleeve-local weights must sum to 1.0 so orchestrator × allocation_pct is correct."""
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    assert result.n_selected == 5
    total = sum(result.weights.values())
    assert total == pytest.approx(1.0, rel=1e-9)


def test_orchestrator_scale_gives_correct_portfolio_weight():
    """With allocation_pct=0.10 and 5 tickers, each ticker's portfolio weight = 0.02."""
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    allocation_pct = 0.10
    for weight in result.weights.values():
        portfolio_weight = weight * allocation_pct
        assert portfolio_weight == pytest.approx(0.02, rel=1e-9)
