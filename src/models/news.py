"""News and LLM output models.

This module defines the Pydantic models used throughout the news ingestion
and sentiment pipeline.

NewsItem is the canonical representation of a news article entering the
sentiment worker. GKGNewsItem extends it with organisation names extracted
from GDELT GKG — these names are used upstream by TickerExtractor to resolve
tickers before the item reaches the sentiment queue.
"""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """A news item to be processed for sentiment.

    Fields:
        id: Unique identifier. For GKG-derived items, this is often
            a composite key "{url}:{ticker}" to support multi-ticker articles.
        body: Article body or content to analyse.
        title: Article headline (used as body proxy when body is unavailable).
        timestamp: UTC datetime when the article was published.
        source: Connector name (e.g. "gdelt", "gdelt_gkg", "rss").
        asset_tags: List of ticker symbols mentioned in the article.
        url: Original article URL.
        language: ISO 639-1 language code (default "en").
    """

    id: str
    body: str
    title: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    asset_tags: list[str] = Field(default_factory=list)
    url: str = ""
    language: str = "en"


class GKGNewsItem(NewsItem):
    """NewsItem enriched with GDELT GKG organisation names.

    This subclass is produced by GDELTGKGConnector and consumed by
    NewsIngestionWorker._process_gkg_items. The org_names field contains
    the raw organisation names extracted by GDELT (e.g. "Apple Inc"),
    which are then mapped to tickers via TickerExtractor.

    Why a subclass instead of adding org_names to NewsItem?
      - Keeps the downstream SentimentWorker contract unchanged.
      - The sentiment pipeline only cares about asset_tags; org_names
        is an ingestion-time concern.
      - Avoids polluting the Redis queue with extra fields that the
        SentimentWorker does not need.
    """

    org_names: list[str] = Field(default_factory=list)


class MarketAuxNewsItem(NewsItem):
    """NewsItem enriched with MarketAux pre-computed entity sentiment.

    The sentiment_score (-1 to +1) is computed by MarketAux per entity
    (ticker) and can be used to pre-filter articles before LLM inference:
    articles near 0 (neutral) may not be worth the token cost.

    Why a subclass instead of adding to NewsItem?
      - Keeps the downstream SentimentWorker contract unchanged.
      - Pre-computed sentiment is an ingestion-time concern; the LLM worker
        only needs body text.
      - Follows the GKGNewsItem pattern already in use.
    """

    marketaux_sentiment: float | None = None


class LLMSentimentOutput(BaseModel):
    """Structured output from LLM sentiment analysis.

    Produced by the SentimentWorker after calling the LLM API.
    Follows the DK-CoT (Domain Knowledge Chain-of-Thought) format
    required by CLAUDE.md.
    """

    polarity: float = Field(ge=-1.0, le=1.0, description="Sentiment polarity [-1, +1]")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence [0, 1]")
    reasoning: str = Field(description="Step-by-step reasoning for the sentiment")
    ticker: str = Field(default="", description="Ticker symbol mentioned")

    # Enriched fields (design doc §5/§9). Backward-compatible defaults: materiality and
    # novelty default to 1.0 and directness to "direct" so an unenriched output (older
    # models, parse fallback) leaves score = polarity × confidence unchanged. These feed
    # the ticker resolver and future score weighting / risk gating (gated on QX-01).
    event_type: str = Field(
        default="other",
        description="earnings|guidance|mna|regulatory|lawsuit|analyst_rating|product|management|macro|other",
    )
    directness: str = Field(
        default="direct",
        description="direct|customer_supplier|competitor_readthrough|sector|macro|unclear",
    )
    materiality: float = Field(default=1.0, ge=0.0, le=1.0, description="Economic relevance [0,1]")
    novelty: float = Field(default=1.0, ge=0.0, le=1.0, description="How new / not-yet-priced [0,1]")
    risk_flags: list[str] = Field(
        default_factory=list,
        description="rumor|already_priced_in|ambiguous_entity|low_source_quality",
    )
    evidence_sentences: list[str] = Field(
        default_factory=list, description="Key sentences from the article supporting the verdict"
    )
