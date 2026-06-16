"""EarningsSurpriseClassifier: derives SurpriseSignal from EarningsLLMOutput."""
from __future__ import annotations

from datetime import datetime, timedelta

from src.models.pead import EarningsLLMOutput, SurpriseSignal


class EarningsSurpriseClassifier:
    """Converts LLM-parsed earnings output into a tradeable SurpriseSignal.

    Applies threshold gates:
    - direction must be "beat" or "miss" (not "inline" or "no_eps")
    - |surprise_pct| must exceed surprise_threshold
    - confidence must be >= min_confidence
    """

    def __init__(
        self,
        surprise_threshold: float = 0.05,
        min_confidence: float = 0.70,
        hold_days: int = 20,
    ) -> None:
        self._surprise_threshold = surprise_threshold
        self._min_confidence = min_confidence
        self._hold_days = hold_days

    def to_signal(
        self,
        llm_output: EarningsLLMOutput,
        filing_id: str,
        detected_at: datetime,
    ) -> SurpriseSignal | None:
        """Return a SurpriseSignal or None if the event does not meet quality gates."""
        if llm_output.direction in ("no_eps", "inline"):
            return None

        if llm_output.confidence < self._min_confidence:
            return None

        surprise = llm_output.surprise_pct
        if surprise is None:
            return None

        if abs(surprise) < self._surprise_threshold:
            return None

        return SurpriseSignal(
            symbol=llm_output.ticker,
            direction=llm_output.direction,  # type: ignore[arg-type]
            surprise_pct=surprise,
            confidence=llm_output.confidence,
            filing_id=filing_id,
            detected_at=detected_at,
            hold_until=detected_at + timedelta(days=self._hold_days),
        )
