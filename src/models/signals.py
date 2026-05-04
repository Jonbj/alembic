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

    def model_dump_json(self) -> str:  # type: ignore[override]
        """Serialize to JSON string for Redis storage."""
        import json

        return json.dumps(
            {
                "symbol": self.symbol,
                "score": self.score,
                "confidence": self.confidence,
                "reasoning": self.reasoning,
                "model_id": self.model_id,
                "ensemble_std": self.ensemble_std,
                "fallback_used": self.fallback_used,
                "generated_at": self.generated_at.isoformat(),
            }
        )
