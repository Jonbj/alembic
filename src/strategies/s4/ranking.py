"""S4 cross-sectional ranking of news sentiment signals.

Reads SentimentResult objects for every ticker in the watchlist, computes
effective_strength = score × confidence, and returns the top-N tickers with
equal-weight allocation within the S4 bucket.
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
        per_ticker_weight = cfg.bucket_pct / n

        ranked = tuple(
            RankedTicker(
                ticker=sig.symbol,
                score=sig.score,
                confidence=sig.confidence,
                effective_strength=strength,
                rank=rank + 1,
                weight=per_ticker_weight,
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
            strength = sig.score * sig.confidence
            if strength <= 0:
                # long-only: skip neutral or net-negative signals
                continue
            result.append((sig, strength))

        return result
