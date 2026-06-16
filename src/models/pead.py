"""PEAD (Post-Earnings Announcement Drift) data models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class EarningsLLMOutput(BaseModel):
    """Structured LLM output for earnings 8-K classification."""

    ticker: str
    filing_type: str = Field(description="earnings_8k | guidance | other")
    eps_actual: float | None = None
    eps_consensus: float | None = None
    surprise_pct: float | None = None
    direction: Literal["beat", "miss", "inline", "no_eps"]
    guidance: Literal["revised-up", "revised-down", "maintained", "no-guidance"] = "no-guidance"
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class SurpriseSignal(BaseModel):
    """A classified earnings surprise signal ready for portfolio use."""

    symbol: str
    direction: Literal["beat", "miss", "inline"]
    surprise_pct: float
    confidence: float = Field(ge=0.0, le=1.0)
    filing_id: str
    detected_at: datetime
    hold_until: datetime

    def is_active(self, as_of: datetime | None = None) -> bool:
        """Return True if the hold period has not yet expired."""
        ts = as_of or datetime.now(timezone.utc)
        return ts <= self.hold_until

    def model_dump_json(self) -> str:  # type: ignore[override]
        import json
        return json.dumps(
            {
                "symbol": self.symbol,
                "direction": self.direction,
                "surprise_pct": self.surprise_pct,
                "confidence": self.confidence,
                "filing_id": self.filing_id,
                "detected_at": self.detected_at.isoformat(),
                "hold_until": self.hold_until.isoformat(),
            }
        )
