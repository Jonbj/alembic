"""Tests for the deterministic ticker resolver (design doc §4)."""
from __future__ import annotations

import pytest

from src.connectors.ticker_resolver import (
    ResolutionEvidence,
    directness_multiplier,
    resolve,
    score_evidence,
)


def _ev(ticker, *, src=False, alias=False, sec=False, llm=False, tradable=False, exch=None):
    return ResolutionEvidence(
        ticker=ticker, source_ticker_match=src, alias_match=alias,
        sec_openfigi_match=sec, llm_agreement=llm, tradable=tradable, exchange=exch,
    )


class TestScoreEvidence:
    def test_all_evidence_sums_to_one(self):
        assert score_evidence(_ev("AAPL", src=True, alias=True, sec=True, llm=True, tradable=True)) == \
            pytest.approx(1.0)

    def test_weights(self):
        assert score_evidence(_ev("X", src=True)) == pytest.approx(0.30)
        assert score_evidence(_ev("X", alias=True)) == pytest.approx(0.25)
        assert score_evidence(_ev("X", sec=True)) == pytest.approx(0.20)
        assert score_evidence(_ev("X", llm=True)) == pytest.approx(0.15)
        assert score_evidence(_ev("X", tradable=True)) == pytest.approx(0.10)

    def test_empty_evidence_zero(self):
        assert score_evidence(_ev("X")) == 0.0


class TestDirectnessMultiplier:
    def test_known(self):
        assert directness_multiplier("direct") == 1.0
        assert directness_multiplier("customer_supplier") == 0.40
        assert directness_multiplier("competitor_readthrough") == 0.35
        assert directness_multiplier("sector") == 0.20
        assert directness_multiplier("macro") == pytest.approx(0.18)
        assert directness_multiplier("unclear") == 0.0

    def test_unknown_is_zero(self):
        assert directness_multiplier("garbage") == 0.0


class TestResolve:
    def test_resolved_when_strong_and_unambiguous(self):
        r = resolve([_ev("AAPL", src=True, alias=True, sec=True, tradable=True)])
        assert r.decision == "RESOLVED"
        assert r.resolved_ticker == "AAPL"
        assert r.resolution_confidence == pytest.approx(0.85)
        assert r.tradable is True

    def test_no_candidate(self):
        r = resolve([])
        assert r.decision == "NO_TRADE_NO_CANDIDATE"
        assert r.resolved_ticker is None

    def test_low_confidence_blocks(self):
        # alias + tradable only = 0.35 < 0.80
        r = resolve([_ev("XYZ", alias=True, tradable=True)])
        assert r.decision == "NO_TRADE_LOW_RESOLUTION_CONFIDENCE"
        assert r.resolved_ticker is None

    def test_not_tradable_blocks(self):
        r = resolve([_ev("XYZ", src=True, alias=True, sec=True, llm=True, tradable=False)])
        assert r.decision == "NO_TRADE_NOT_TRADABLE"
        assert r.resolved_ticker is None

    def test_ambiguous_blocks(self):
        # AAPL (1.0, tradable) vs APLE (0.90) → margin 0.10 < 0.15
        top = _ev("AAPL", src=True, alias=True, sec=True, llm=True, tradable=True)   # 1.0
        rival = _ev("APLE", src=True, alias=True, sec=True, llm=True, tradable=False)  # 0.90
        r = resolve([top, rival])
        assert r.decision == "NO_TRADE_AMBIGUOUS_TICKER"
        assert r.resolved_ticker is None
        assert r.ambiguity_margin == pytest.approx(0.10)

    def test_clear_winner_resolves(self):
        top = _ev("AAPL", src=True, alias=True, sec=True, llm=True, tradable=True)  # 1.0
        rival = _ev("APLE", alias=True, tradable=True)                               # 0.35
        r = resolve([top, rival])
        assert r.decision == "RESOLVED"
        assert r.resolved_ticker == "AAPL"
        assert r.ambiguity_margin == pytest.approx(0.65)

    def test_unclear_directness_blocks_even_if_strong(self):
        r = resolve([_ev("AAPL", src=True, alias=True, sec=True, llm=True, tradable=True)],
                    directness="unclear")
        assert r.decision == "NO_TRADE_UNCLEAR_ISSUER_IMPACT"
        assert r.resolved_ticker is None

    def test_candidates_listed(self):
        r = resolve([_ev("A", alias=True), _ev("B", src=True, tradable=True)])
        assert set(r.candidates) == {"A", "B"}
