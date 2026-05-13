"""News and LLM output models."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """A news item to be processed for sentiment."""

    id: str
    body: str
    title: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    asset_tags: list[str] = Field(default_factory=list)
    url: str = ""
    language: str = "en"


class GKGNewsItem(NewsItem):
    """NewsItem enriched with GDELT GKG organisation names."""

    org_names: list[str] = Field(default_factory=list)


class LLMSentimentOutput(BaseModel):
    """Structured output from LLM sentiment analysis."""

    polarity: float = Field(ge=-1.0, le=1.0, description="Sentiment polarity [-1, +1]")
    confidence: float = Field(ge=0.0, le=1.0, description="Model confidence [0, 1]")
    reasoning: str = Field(description="Step-by-step reasoning for the sentiment")
    ticker: str = Field(default="", description="Ticker symbol mentioned")
