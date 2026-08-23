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
    # #294: provenance point-in-time for the S4 entry-intent ledger. Nullable
    # fields keep legacy rows and synthetic/backtest signals compatible.
    news_log_id: int | None = None
    first_seen_at: datetime | None = None
    news_source: str | None = None
    content_hash: str | None = None
    extraction_method: str | None = None
    resolver_decision: str | None = None
    resolver_method: str | None = None
