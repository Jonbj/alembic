"""S4 cross-sectional ranking of news sentiment signals.

Reads SentimentResult objects for every ticker in the watchlist, ranks by
effective_strength = score, and returns the top-N tickers with equal-weight
allocation within the S4 bucket. NOTE: score already encodes confidence — the
sentiment worker stores score = polarity × confidence (CLAUDE.md). The ranker
must NOT multiply by confidence again (that would apply confidence² and bias
selection toward high-confidence over high-polarity names).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from src.models.signals import SentimentResult
from src.strategies.s4.config import S4Config


@dataclass(frozen=True)
class RankedTicker:
    ticker: str
    score: float
    confidence: float
    effective_strength: float
    rank: int
    weight: float
    # B33-follow-up: provenance of the exact SentimentResult used for this
    # ticker, pinned here so callers never need to re-fetch "latest" later.
    signal_id: int | None = None
    reasoning: str = ""
    model_id: str = ""


@dataclass(frozen=True)
class RankingResult:
    as_of: datetime
    rankings: tuple[RankedTicker, ...]
    bucket_weight: float
    n_selected: int

    @property
    def tickers(self) -> list[str]:
        return [r.ticker for r in self.rankings]

    @property
    def weights(self) -> dict[str, float]:
        return {r.ticker: r.weight for r in self.rankings}

    @property
    def provenance(self) -> dict[str, dict]:
        """Per-ticker {signal_id, score, reasoning, model_id} pinned at rank time.

        B33-follow-up: this is the single source of truth for "which signal
        drove this ticker's weight" — callers must use this instead of
        re-querying the signal store for the latest signal, which can return
        a different (newer) signal than the one actually ranked.
        """
        return {
            r.ticker: {
                "signal_id": r.signal_id,
                "score": r.score,
                "reasoning": r.reasoning,
                "model_id": r.model_id,
            }
            for r in self.rankings
        }


class CrossSectionalRanker:
    """Rank sentiment signals cross-sectionally and return the top-N bucket.

    Long-only: only considers tickers with positive effective_strength after
    applying the min_score / min_confidence filters.  If fewer than
    config.min_stocks pass, returns an empty RankingResult (no partial bucket).
    """

    def __init__(self, config: S4Config | None = None) -> None:
        self._config = config or S4Config()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(
        self,
        signals: Sequence[SentimentResult],
        as_of: datetime | None = None,
    ) -> RankingResult:
        """Compute cross-sectional ranking from a collection of SentimentResult.

        Args:
            signals: One SentimentResult per ticker (duplicates collapsed to the
                     most recent by generated_at).
            as_of: Timestamp to stamp the result; defaults to now (UTC).

        Returns:
            RankingResult with top-N tickers and equal weights, or an empty
            result if fewer than min_stocks pass the filters.
        """
        if as_of is None:
            as_of = datetime.utcnow()

        cfg = self._config
        candidates = self._filter_and_deduplicate(signals)

        if len(candidates) < cfg.min_stocks:
            return RankingResult(
                as_of=as_of,
                rankings=(),
                bucket_weight=cfg.bucket_pct,
                n_selected=0,
            )

        # Sort descending by effective_strength; take top n_top
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = candidates[: cfg.n_top]

        if len(selected) < cfg.min_stocks:
            return RankingResult(
                as_of=as_of,
                rankings=(),
                bucket_weight=cfg.bucket_pct,
                n_selected=0,
            )

        n = len(selected)
        # #81: fixed_slot_sizing caps each ticker's weight at 1/n_top instead of
        # 1/n_selected — a lone survivor gets its one slot, not the whole
        # sleeve. n <= cfg.n_top always holds (selected is truncated above),
        # so this only ever reduces total sleeve utilization, never increases
        # any single ticker's weight above the legacy formula.
        per_ticker_weight = 1.0 / cfg.n_top if cfg.fixed_slot_sizing else 1.0 / n

        ranked = tuple(
            RankedTicker(
                ticker=sig.symbol,
                score=sig.score,
                confidence=sig.confidence,
                effective_strength=strength,
                rank=rank + 1,
                weight=per_ticker_weight,
                signal_id=sig.signal_id,
                reasoning=sig.reasoning,
                model_id=sig.model_id,
            )
            for rank, (sig, strength) in enumerate(selected)
        )

        return RankingResult(
            as_of=as_of,
            rankings=ranked,
            bucket_weight=cfg.bucket_pct,
            n_selected=n,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_and_deduplicate(
        self, signals: Sequence[SentimentResult]
    ) -> list[tuple[SentimentResult, float]]:
        """Apply min_confidence / min_score filters and deduplicate by symbol.

        Returns list of (SentimentResult, effective_strength) for qualifying,
        positive-strength signals.
        """
        cfg = self._config
        best: dict[str, SentimentResult] = {}

        for sig in signals:
            prev = best.get(sig.symbol)
            if prev is None or sig.generated_at > prev.generated_at:
                best[sig.symbol] = sig

        result: list[tuple[SentimentResult, float]] = []
        for sig in best.values():
            if sig.confidence < cfg.min_confidence:
                continue
            if abs(sig.score) < cfg.min_score:
                continue
            # effective_strength = score. score already = polarity × confidence
            # (set by the sentiment worker, CLAUDE.md). Multiplying by confidence
            # here would apply it twice (confidence²) and distort the top-N ranking.
            strength = sig.score
            if strength <= 0:
                # long-only: skip neutral or net-negative signals
                continue
            result.append((sig, strength))

        return result
