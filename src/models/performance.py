"""Performance tracking models for trading system."""

from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# Valid diagnosis categories for PostMortem (B5 - minimax)
VALID_DIAGNOSES: frozenset[str] = frozenset({
    "low_confidence_passed",
    "ensemble_divergence_ignored",
    "regime_mismatch",
    "news_staleness",
    "market_gap",
    "stop_too_tight",
    "correlated_portfolio_loss",
    "model_drift_active",
    "threshold_boundary",
    "unknown",
})


class PostMortem(BaseModel):
    """Post-mortem analysis for a losing trade.

    Generated when:
    - loss_pct >= 0.03 (loss >= 3%)
    - loss_pct >= 0.02 AND (signal_score >= 0.5 OR ensemble_std >= 0.3)
    """

    trade_id: UUID
    symbol: str
    loss_pct: float = Field(ge=0.0, description="Loss percentage (positive value)")
    signal_score: float = Field(ge=-1.0, le=1.0, description="Signal score at trade entry")
    signal_confidence: float = Field(ge=0.0, le=1.0, description="Signal confidence at trade entry")
    ensemble_std: float = Field(ge=0.0, description="Ensemble standard deviation at signal time")
    regime_at_trade: str = Field(description="Regime label at trade time")
    reasoning_summary: str = Field(description="First 200 chars of LLM reasoning")
    diagnosis: str = Field(description="Classification of loss cause")

    @field_validator("diagnosis")
    @classmethod
    def validate_diagnosis(cls, v: str) -> str:
        """Validate diagnosis is one of the allowed categories."""
        if v not in VALID_DIAGNOSES:
            raise ValueError(
                f"diagnosis must be one of {VALID_DIAGNOSES}, got {v!r}"
            )
        return v

    @field_validator("reasoning_summary")
    @classmethod
    def truncate_reasoning(cls, v: str) -> str:
        """Truncate reasoning summary to 200 chars."""
        return v[:200] if len(v) > 200 else v


class PerformanceReport(BaseModel):
    """Daily performance report with IC analysis and recommendations."""

    period_start: date
    period_end: date
    overall_ic: float = Field(description="Composite IC aggregated over all models")
    icir: float = Field(description="IC / std(IC) - stability measure")
    hit_rate: float = Field(description="Percentage of signals with correct sign")
    model_ic: dict[str, float] = Field(
        description="IC per model: {'opus': 0.18, 'qwen35': 0.14, ...}"
    )
    model_icir: dict[str, float] = Field(
        description="ICIR per model"
    )
    recommended_weights: dict[str, float] = Field(
        description="Suggested weights for ensemble"
    )
    weight_change_applied: bool = Field(
        description="True if auto-applied weight change"
    )
    threshold_analysis: dict[str, float] = Field(
        description="IC by score range: {'0.2-0.3': 0.05, '0.3-0.4': 0.12, ...}"
    )
    threshold_suggestion: float | None = Field(
        default=None,
        description="Suggested new threshold if gain > 15%"
    )
    drift_alerts: list[str] = Field(
        default_factory=list,
        description="Models with anomalous distribution (PSI-based)"
    )
    post_mortems: list[PostMortem] = Field(
        default_factory=list,
        description="Post-mortem analyses for significant losses"
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    report_version: str = Field(description="Report schema version")

    @field_validator("overall_ic", "icir", "hit_rate")
    @classmethod
    def validate_metrics(cls, v: float, info) -> float:
        """Validate IC and hit_rate are in reasonable bounds."""
        field_name = info.field_name
        if field_name == "hit_rate":
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{field_name} must be between 0 and 1, got {v}")
        elif field_name == "overall_ic":
            if not -1.0 <= v <= 1.0:
                raise ValueError(f"{field_name} must be between -1 and 1, got {v}")
        # icir can be any real number (IC / std)
        return v

    @field_validator("recommended_weights")
    @classmethod
    def validate_weights(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate weights are in [0, 1] and sum to ~1."""
        for model, weight in v.items():
            if not 0.0 <= weight <= 1.0:
                raise ValueError(f"Weight for {model} must be between 0 and 1, got {weight}")
        total = sum(v.values())
        if not 0.99 <= total <= 1.01:  # Allow small floating point tolerance
            raise ValueError(f"Weights must sum to 1, got {total}")
        return v
