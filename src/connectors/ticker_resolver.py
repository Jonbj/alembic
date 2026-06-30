"""Deterministic ticker resolver (design: docs/Alembic_ticker_sentiment_design.docx §4).

LLMs and extractors PROPOSE entity/ticker candidates; this module DECIDES the canonical,
tradable ticker only when the evidence is strong and unambiguous — otherwise it emits a
NO_TRADE reason. The objective is to minimise ``false_positive_ticker_rate`` (a wrong
ticker triggers an order on an unrelated stock, far worse than a missed news item), not
to maximise recall.

The decision core here is pure and deterministic (no I/O), so it unit-tests cleanly and
its weights/thresholds can be calibrated against historical errors. External evidence
(internal alias table, SEC company_tickers, OpenFIGI, broker tradability) is gathered by
the providers in ``ticker_resolver_providers`` and passed in as ``ResolutionEvidence``.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── Resolution evidence weights (§4.4); sum = 1.0 ─────────────────────────────
_W_SOURCE_TICKER = 0.30   # ticker came from a reliable source (cashtag / broker / MarketAux metadata)
_W_ALIAS_MATCH = 0.25     # internal ticker_lookup company_name / alias match
_W_SEC_OPENFIGI = 0.20    # SEC company_tickers / OpenFIGI confirms ticker ↔ company
_W_LLM_AGREEMENT = 0.15   # LLM entity extraction agrees on this ticker
_W_TRADABLE = 0.10        # tradable on the broker and in the operating universe

# ── NO_TRADE thresholds (§4.3) ────────────────────────────────────────────────
_MIN_RESOLUTION_CONFIDENCE = 0.80
_MIN_AMBIGUITY_MARGIN = 0.15

# ── Directness multipliers (§4.2): how much an indirect mention is discounted ──
_DIRECTNESS_MULT: dict[str, float] = {
    "direct": 1.00,
    "customer_supplier": 0.40,
    "competitor_readthrough": 0.35,
    "sector": 0.20,
    "macro": 0.18,
    "unclear": 0.0,
}


@dataclass(frozen=True)
class ResolutionEvidence:
    """Per-candidate evidence gathered from the resolution providers."""
    ticker: str
    source_ticker_match: bool = False
    alias_match: bool = False
    sec_openfigi_match: bool = False
    llm_agreement: bool = False
    tradable: bool = False
    exchange: str | None = None
    figi: str | None = None


@dataclass(frozen=True)
class ResolvedTicker:
    """Resolver verdict. ``decision`` is ``"RESOLVED"`` only when every gate passes."""
    resolved_ticker: str | None
    exchange: str | None
    figi: str | None
    resolution_confidence: float
    ambiguity_margin: float
    tradable: bool
    directness: str
    decision: str
    candidates: tuple[str, ...] = ()


def score_evidence(ev: ResolutionEvidence) -> float:
    """Weighted resolution score for one candidate (§4.4), in [0, 1]."""
    return (
        _W_SOURCE_TICKER * ev.source_ticker_match
        + _W_ALIAS_MATCH * ev.alias_match
        + _W_SEC_OPENFIGI * ev.sec_openfigi_match
        + _W_LLM_AGREEMENT * ev.llm_agreement
        + _W_TRADABLE * ev.tradable
    )


def directness_multiplier(directness: str) -> float:
    """Sizing multiplier for an indirect mention (§4.2). Unknown → 0.0 (conservative)."""
    return _DIRECTNESS_MULT.get(directness, 0.0)


def resolve(candidates: list[ResolutionEvidence], directness: str = "direct") -> ResolvedTicker:
    """Pick the best candidate and apply the NO_TRADE gates (§4.3).

    The verdict is ``"RESOLVED"`` only when ALL of:
      - resolution_confidence ≥ 0.80,
      - ambiguity_margin ≥ 0.15 (when there is a competing candidate),
      - the ticker is tradable,
      - directness is not ``"unclear"``.
    Otherwise the decision is the specific ``NO_TRADE_*`` reason, and
    ``resolved_ticker`` is None — the caller must drop the signal.
    """
    if not candidates:
        return ResolvedTicker(None, None, None, 0.0, 0.0, False, directness, "NO_TRADE_NO_CANDIDATE")

    scored = sorted(((score_evidence(c), c) for c in candidates), key=lambda x: -x[0])
    top_score, top = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    margin = top_score - second_score

    if directness == "unclear":
        decision = "NO_TRADE_UNCLEAR_ISSUER_IMPACT"
    elif not top.tradable:
        decision = "NO_TRADE_NOT_TRADABLE"
    elif top_score < _MIN_RESOLUTION_CONFIDENCE:
        decision = "NO_TRADE_LOW_RESOLUTION_CONFIDENCE"
    elif len(scored) > 1 and margin < _MIN_AMBIGUITY_MARGIN:
        decision = "NO_TRADE_AMBIGUOUS_TICKER"
    else:
        decision = "RESOLVED"

    return ResolvedTicker(
        resolved_ticker=top.ticker if decision == "RESOLVED" else None,
        exchange=top.exchange,
        figi=top.figi,
        resolution_confidence=round(top_score, 4),
        ambiguity_margin=round(margin, 4),
        tradable=top.tradable,
        directness=directness,
        decision=decision,
        candidates=tuple(c.ticker for _, c in scored),
    )
