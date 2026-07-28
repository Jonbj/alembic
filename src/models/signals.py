"""Signal models for trading system."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SentimentResult(BaseModel):
    """Result of sentiment aggregation (ensemble or FinBERT fallback)."""

    symbol: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    model_id: str = Field(description="Source model or 'finbert' for fallback")
    ensemble_std: float = Field(default=0.0, ge=0.0)
    fallback_used: bool = Field(default=False)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # FIX-03: news publication time (event-time). None = unknown (legacy/non-news).
    published_at: datetime | None = None
    # B33-follow-up: sentiment_signals.id, when this result was loaded from the
    # DB. None = synthetic/backtest signal with no DB row. Carried through the
    # ranker so the exact signal that drove a decision can be pinned at
    # decision time, instead of re-querying "latest" later and racing a signal
    # that arrived in between (see the 2026-07-15 MSFT incident).
    signal_id: int | None = None

    def to_redis_json(self) -> str:
        """Serialize to the Redis-compatible JSON format expected by consumers.

        Uses Pydantic native serialization (forward kwargs, all fields included)
        then normalises UTC datetime strings from Pydantic's ``Z`` suffix to the
        ``+00:00`` offset form the original override produced, so existing Redis
        payloads stay readable.
        """
        import re

        raw = super().model_dump_json()
        # Pydantic v2: "2026-07-10T14:30:00Z".  Old override: "2026-07-10T14:30:00+00:00".
        # Only the UTC offset Z needs normalising; a regex targets it precisely.
        return re.sub(r'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z"',
                       r'"\1+00:00"', raw)
