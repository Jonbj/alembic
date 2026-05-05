"""Regime detection Pydantic models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

REGIME_DEFAULTS: dict[str, float] = {
    "bull": 1.0,
    "sideways": 0.7,
    "bear": 0.4,
    "high_vol": 0.2,
}

RegimeLabel = Literal["bull", "sideways", "bear", "high_vol"]


class RegimeOutput(BaseModel):
    """Output di un singolo LLM."""

    regime: RegimeLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    data_quality: Literal["complete", "partial"] = "complete"
    regime_secondary: RegimeLabel | None = None


class MacroSnapshot(BaseModel):
    """Dati macro al momento della detection."""

    vix: float
    yield_curve: float
    spy_momentum_20d: float


class RegimeState(BaseModel):
    """Stato regime persistito in Redis."""

    regime: RegimeLabel
    multiplier: float
    macro_snapshot: MacroSnapshot
    llm_outputs: list[dict]
    disagreement: bool = False
    detected_at: datetime
