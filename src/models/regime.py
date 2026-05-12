"""Pydantic models for macro regime detection.

Used by:
    src/workers/regime.py  — detect_regime() writes RegimeState to Redis
    src/store/redis_store.py — set_regime() / get_regime() serialization
    src/notifications/telegram.py — format_regime_message() reads RegimeState

Data flow:
    MacroSnapshot (raw FRED + yfinance data)
        → LLM prompt → RegimeOutput (one per LLM)
        → Consensus logic → RegimeState (persisted to Redis, TTL 25h)
"""

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
