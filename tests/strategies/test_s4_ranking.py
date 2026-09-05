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
    defaults = {"reasoning": "test", "model_id": "test"}
    defaults.update(kwargs)
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=confidence,
        **defaults,
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
    assert cfg.min_stocks == 1  # default: a lone gate-surviving signal must trade
    assert cfg.signals_lookback_hours == 96  # extended from 24 to cover weekend gaps
    assert cfg.rebalance_frequency == RebalanceFrequency.DAILY


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


# ---------------------------------------------------------------------------
# B33-follow-up: signal provenance (signal_id/reasoning/model_id) pinned per
# ticker at ranking time, so the decision log / idempotency never need to
# re-fetch "latest" later and race a newer signal for the same symbol.
# ---------------------------------------------------------------------------

def test_ranked_ticker_carries_signal_id():
    sig = _sig("MSFT", score=0.165, confidence=0.9, signal_id=3770)
    ranker = CrossSectionalRanker(S4Config(min_stocks=1))
    result = ranker.rank([sig])
    assert result.rankings[0].signal_id == 3770


def test_ranked_ticker_carries_reasoning_and_model_id():
    sig = _sig("MSFT", score=0.165, confidence=0.9, signal_id=3770,
                reasoning="bull case", model_id="ensemble:glm-5.2:cloud")
    ranker = CrossSectionalRanker(S4Config(min_stocks=1))
    result = ranker.rank([sig])
    assert result.rankings[0].reasoning == "bull case"
    assert result.rankings[0].model_id == "ensemble:glm-5.2:cloud"


def test_ranking_result_provenance_keyed_by_ticker():
    sigs = [
        _sig("MSFT", score=0.165, confidence=0.9, signal_id=3770, reasoning="bull", model_id="m1"),
        _sig("AAPL", score=0.5, confidence=0.9, signal_id=42, reasoning="beat", model_id="m2"),
    ]
    ranker = CrossSectionalRanker(S4Config(min_stocks=1))
    result = ranker.rank(sigs)
    assert result.provenance["MSFT"] == {
        "signal_id": 3770, "score": 0.165, "reasoning": "bull", "model_id": "m1",
    }
    assert result.provenance["AAPL"]["signal_id"] == 42


def test_ranked_ticker_signal_id_defaults_to_none():
    """Backtest signals with no DB row have signal_id=None — provenance still works."""
    sig = _sig("MSFT", score=0.165, confidence=0.9)
    ranker = CrossSectionalRanker(S4Config(min_stocks=1))
    result = ranker.rank([sig])
    assert result.rankings[0].signal_id is None
    assert result.provenance["MSFT"]["signal_id"] is None


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


def test_single_candidate_forms_bucket_of_one():
    """A lone strong signal must trade under the default config (min_stocks=1),
    but (#81, fixed_slot_sizing default True) at its 1/n_top slot weight, not
    the whole sleeve bucket — the lone-survivor concentration fix.

    The live entry gate is enforced upstream in portfolio_scheduler; by the time
    signals reach the ranker they have already passed the gate. Discarding a
    lone survivor at min_stocks=2 was the original deployment chokepoint —
    still fixed here (n_selected==1), just no longer over-sized.
    """
    signals = _make_signals(1)
    ranker = CrossSectionalRanker(S4Config())  # default min_stocks=1, fixed_slot_sizing=True
    result = ranker.rank(signals)

    assert result.n_selected == 1
    assert result.weights == {"T00": pytest.approx(0.2, rel=1e-9)}


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
    # Only 4 pass filters, n_top=5, min_stocks=3. Default fixed_slot_sizing=True
    # (#81): each still gets its fixed 1/n_top slot, not the bucket redistributed
    # across the 4 that showed up.
    signals = _make_signals(4)
    ranker = CrossSectionalRanker(S4Config(n_top=5, min_stocks=3))
    result = ranker.rank(signals)

    # Should select all 4 available (4 >= min_stocks=3)
    assert result.n_selected == 4
    # weight = 1.0 / n_top = 0.2 (fixed slot, not 1/4 redistribution)
    for r in result.rankings:
        assert r.weight == pytest.approx(1.0 / 5, rel=1e-9)


def test_fewer_candidates_than_n_top_legacy_redistribution_with_flag_off():
    """Rollback path: fixed_slot_sizing=False reproduces the pre-#81 formula
    (unused slots redistributed across the survivors, weight = 1/n_selected)."""
    signals = _make_signals(4)
    ranker = CrossSectionalRanker(S4Config(n_top=5, min_stocks=3, fixed_slot_sizing=False))
    result = ranker.rank(signals)

    assert result.n_selected == 4
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
# effective_strength = score (score already encodes confidence)
# ---------------------------------------------------------------------------

def test_effective_strength_formula():
    # score already = polarity × confidence (sentiment worker). effective_strength
    # equals score — the ranker must NOT multiply by confidence again.
    sig = _sig("TSLA", score=0.6, confidence=0.8)
    ranker = CrossSectionalRanker(S4Config(n_top=1, min_stocks=1))
    result = ranker.rank([sig])

    assert result.rankings[0].effective_strength == pytest.approx(0.6)


def test_ranking_does_not_apply_confidence_twice():
    """Regression: effective_strength = score, NOT score × confidence (confidence²).

    score is already polarity × confidence. Re-applying confidence would flip the
    top-N selection toward high-confidence over high-polarity names.
      A: polarity 0.9 × conf 0.5 → score 0.45
      B: polarity 0.5 × conf 0.8 → score 0.40
    Documented formula: A (0.45) outranks B (0.40).
    Buggy confidence²:  A→0.225, B→0.32  → B would wrongly outrank A.
    """
    sig_a = _sig("AAA", score=0.45, confidence=0.5)
    sig_b = _sig("BBB", score=0.40, confidence=0.8)
    ranker = CrossSectionalRanker(S4Config(n_top=2, min_stocks=2))
    result = ranker.rank([sig_a, sig_b])

    assert [r.ticker for r in result.rankings] == ["AAA", "BBB"]
    assert result.rankings[0].effective_strength == pytest.approx(0.45)
    assert result.rankings[1].effective_strength == pytest.approx(0.40)


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


# ---------------------------------------------------------------------------
# #81: lone-survivor concentration — fixed_slot_sizing flag
#
# Bug: with the legacy formula (weight = 1/n_selected), a lone gate-surviving
# ticker gets the WHOLE sleeve bucket (weight=1.0 -> 10% NAV at allocation_pct
# =0.10), not a size proportional to its "slot". Real losses 2026-07-17 (DB,
# -$77.88 on a -1.05% price move) and 2026-07-20 (MSFT, same pattern, weaker
# signal 0.150 vs DB's 0.672). Fix: when fixed_slot_sizing is enabled, each
# selected ticker gets a FIXED weight of 1/n_top regardless of how many
# tickers actually passed the gate that cycle — unused slots are left
# undeployed (smaller total sleeve utilization), not redistributed to the
# survivors. Zero change in the fully-subscribed case (n_selected==n_top).
# ON by default per explicit operator decision 2026-07-20 (real realized
# loss + an identical live position exposed to the same risk at decision
# time) — flag remains available to roll back to the legacy formula
# (config/trading.yaml risk.s4_fixed_slot_sizing_enabled).
# ---------------------------------------------------------------------------

def test_config_fixed_slot_sizing_defaults_true():
    """ON by default per explicit operator decision 2026-07-20 (real realized
    loss + an identical live position exposed to the same risk)."""
    cfg = S4Config()
    assert cfg.fixed_slot_sizing is True


def test_fixed_slot_sizing_false_preserves_legacy_lone_survivor_behavior():
    """Explicit regression guard: flag off must reproduce the pre-#81 bug exactly."""
    signals = _make_signals(1)
    ranker = CrossSectionalRanker(S4Config(fixed_slot_sizing=False))
    result = ranker.rank(signals)

    assert result.weights == {"T00": 1.0}


def test_fixed_slot_sizing_true_caps_lone_survivor_to_one_slot():
    """The #81 fix: n_top=5, only 1 candidate -> weight = 1/5, not 1.0."""
    signals = _make_signals(1)
    ranker = CrossSectionalRanker(S4Config(n_top=5, fixed_slot_sizing=True))
    result = ranker.rank(signals)

    assert result.n_selected == 1
    assert result.weights == {"T00": pytest.approx(0.2, rel=1e-9)}


def test_fixed_slot_sizing_true_unchanged_when_fully_subscribed():
    """No behavior change in the common case: n_selected == n_top."""
    signals = _make_signals(10)
    ranker = CrossSectionalRanker(S4Config(n_top=5, fixed_slot_sizing=True))
    result = ranker.rank(signals)

    assert result.n_selected == 5
    for w in result.weights.values():
        assert w == pytest.approx(1.0 / 5, rel=1e-9)
    assert sum(result.weights.values()) == pytest.approx(1.0, rel=1e-9)


def test_fixed_slot_sizing_true_partial_subscription_leaves_bucket_undeployed():
    """n_top=5, only 3 candidates -> each still gets 1/5 (not 1/3); sleeve
    utilization is 3/5=0.6, not the full 1.0 the legacy formula always gives."""
    signals = _make_signals(3)
    ranker = CrossSectionalRanker(S4Config(n_top=5, fixed_slot_sizing=True))
    result = ranker.rank(signals)

    assert result.n_selected == 3
    for w in result.weights.values():
        assert w == pytest.approx(1.0 / 5, rel=1e-9)
    assert sum(result.weights.values()) == pytest.approx(0.6, rel=1e-9)


def test_fixed_slot_sizing_true_matches_historical_2pct_norm_at_default_config():
    """Default S4Config (n_top=5, allocation_pct=0.10 applied by caller): a lone
    survivor's portfolio-level weight becomes 1/5 * 0.10 = 2%, matching the
    documented historical S4 norm (0.020-0.050), not the 10% concentration bug."""
    signals = _make_signals(1)
    ranker = CrossSectionalRanker(S4Config(fixed_slot_sizing=True))
    result = ranker.rank(signals)

    allocation_pct = 0.10
    portfolio_weight = result.weights["T00"] * allocation_pct
    assert portfolio_weight == pytest.approx(0.02, rel=1e-9)


# --- #401: l'invariante "rank e' funzione decrescente del punteggio" ---------
# Il ranker deve sempre produrre rank monotonici rispetto al campo che usa per
# ordinare. Questo test e' la guardia a livello di ranker: quando il ledger
# (#294) osserva un'inversione, la causa non e' il ranker stesso ma la
# divergenza fra il punteggio catturato nel candidate snapshot e quello visto
# dal ranker. Il dossier (#401 sweep) copre la verifica a livello di ledger.


def test_ranker_rank_monotone_decrescente_in_effective_strength():
    """Per ogni signal nello stesso slot, il rank assegnato deve essere
    strettamente decrescente in effective_strength (= score, vedi
    ranking.py:4-8). Pareggi ammessi."""
    signals = [
        _sig("MRVL", score=0.3578, confidence=0.9),
        _sig("CSCO", score=0.3199, confidence=0.9),
        _sig("SOXX", score=0.3600, confidence=0.9),
        _sig("DELL", score=0.5810, confidence=0.9),
        _sig("AMAT", score=0.5210, confidence=0.9),
    ]
    ranker = CrossSectionalRanker(S4Config(n_top=5, min_stocks=5))
    result = ranker.rank(signals)

    # Per il ranker, score e effective_strength coincidono (ranking.py:227-230).
    # Costruiamo una mappa signal_id -> (rank, score) dai diagnostics e
    # verifichiamo che l'ordine per rank sia coerente con l'ordine per score.
    by_ticker: dict[str, tuple[int, float]] = {}
    for r in result.rankings:
        by_ticker[r.ticker] = (r.rank, r.effective_strength)
    by_rank = sorted(by_ticker.items(), key=lambda kv: kv[1][0])
    by_score = sorted(by_ticker.items(), key=lambda kv: kv[1][1], reverse=True)
    assert [t for t, _ in by_rank] == [t for t, _ in by_score]


def test_ranker_diagnostics_rank_coerente_con_ranking():
    """#401: ogni diagnostic emesso dal ranker deve avere rank strettamente
    crescente e consistente con l'ordinamento per effective_strength. Una
    inversione qui e' una firma del bug #401 sul lato ranker (non sul lato
    ledger)."""
    signals = _make_signals(7)
    ranker = CrossSectionalRanker(S4Config(n_top=5, min_stocks=5))
    result = ranker.rank(signals)

    ranks = [d.rank for d in result.diagnostics if d.rank is not None]
    assert ranks == sorted(ranks), (
        f"ranker diagnostics rank not monotone: {ranks} — #401 violation"
    )

    # Per ogni coppia (i, j) di diagnostics emessi, se rank_i < rank_j allora
    # il signal di i deve avere effective_strength >= signal di j.
    by_signal: dict[int, int] = {
        d.signal_id: d.rank
        for d in result.diagnostics
        if d.signal_id is not None and d.rank is not None
    }
    strengths = {
        r.signal_id: r.effective_strength
        for r in result.rankings
    }
    for s_i, r_i in by_signal.items():
        for s_j, r_j in by_signal.items():
            if r_i < r_j:
                assert strengths[s_i] >= strengths[s_j], (
                    f"ranker: signal {s_i} (rank {r_i}, strength "
                    f"{strengths[s_i]}) precedes signal {s_j} "
                    f"(rank {r_j}, strength {strengths[s_j]}) — "
                    f"viola l'invariante #401"
                )
