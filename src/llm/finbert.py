"""
FinBERT fallback with entropic confidence mapping.

FinBERT outputs 3-class probabilities: positive, neutral, negative.
Confidence is derived from 1 - normalized_entropy, so a peaked distribution
→ high confidence, uniform distribution → low confidence (~0).
Polarity maps the positive/negative balance accounting for neutral dampening.
"""

import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.models.news import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class FinBERTResult:
    """Result from FinBERT sentiment analysis."""

    polarity: float  # [-1, +1]
    confidence: float  # [0, 1] - entropic
    worker_type: Literal["finbert"] = "finbert"


def entropic_confidence(probs: list[float]) -> float:
    """
    Calculate confidence as 1 - normalized entropy.

    Confidence = 1 - H(p) / H_max where H_max = log2(n_classes).
    A peaked distribution (low entropy) → high confidence.
    A uniform distribution (max entropy) → low confidence (~0).

    Args:
        probs: List of probabilities for each class (must sum to ~1.0)

    Returns:
        Confidence value in [0, 1]
    """
    n = len(probs)
    if n == 0:
        return 0.0

    h_max = math.log2(n)
    if h_max == 0:
        return 1.0

    # Add small epsilon to avoid log(0)
    entropy = -sum(p * math.log2(p + 1e-12) for p in probs)
    # Clamp to [0, 1] to handle floating-point errors
    return max(0.0, min(1.0, float(1.0 - entropy / h_max)))


class FinBERTClient:
    """
    FinBERT sentiment analysis client.

    Uses the ProsusAI/finbert model from HuggingFace transformers.
    The pipeline is lazy-loaded on first use to avoid slow startup.
    """

    _MODEL_NAME = "ProsusAI/finbert"
    _MAX_TOKENS = 512  # FinBERT context window

    def __init__(self) -> None:
        self._pipe = None

    def _get_pipeline(self):
        """
        Lazy-load the FinBERT pipeline.

        Import transformers inside this method to avoid slow startup
        when FinBERT is not used (e.g., ensemble succeeds).
        """
        if self._pipe is None:
            from transformers import pipeline

            self._pipe = pipeline(
                "text-classification",
                model=self._MODEL_NAME,
                top_k=None,  # return all class scores (replaces deprecated return_all_scores=True)
                device=-1,  # CPU
            )
        return self._pipe

    def analyze(self, text: str) -> FinBERTResult:
        """
        Analyze text sentiment using FinBERT.

        Args:
            text: Input text to analyze (will be truncated to 512 tokens)

        Returns:
            FinBERTResult with polarity, confidence, and worker_type
        """
        pipe = self._get_pipeline()
        raw = pipe(text[: self._MAX_TOKENS])
        # raw is either [[{label, score}, ...]] (old) or [{label, score}, ...] (new top_k=None)
        inner = raw[0] if isinstance(raw[0], list) else raw
        scores = {item["label"]: item["score"] for item in inner}

        # Extract probabilities for each class
        probs = [
            scores.get("positive", 0),
            scores.get("neutral", 0),
            scores.get("negative", 0),
        ]

        # Calculate entropic confidence
        confidence = entropic_confidence(probs)

        # Calculate polarity: positive - negative, dampened by neutral
        # Formula: polarity = (positive - negative) * (1 - neutral)
        polarity = (scores.get("positive", 0) - scores.get("negative", 0)) * (
            1.0 - scores.get("neutral", 0)
        )
        # Clamp to [-1, +1]
        polarity = max(-1.0, min(1.0, polarity))

        return FinBERTResult(polarity=polarity, confidence=confidence)

    def score_articles(
        self,
        articles: "list[NewsItem]",
        min_confidence: float = 0.3,
    ) -> list[tuple[date, float]]:
        """Score a list of articles, returning (article_date, score) pairs.

        score = polarity × confidence (using entropic confidence formula).
        Articles below min_confidence or with no text are excluded.
        Exceptions from analyze() are logged and skipped.
        """
        results = []
        for article in articles:
            text = article.body or article.title
            if not text:
                continue
            try:
                result = self.analyze(text)
            except Exception as exc:
                logger.warning("FinBERT failed for %s: %s", article.id, exc)
                continue
            if result.confidence >= min_confidence:
                results.append((article.timestamp.date(), result.polarity * result.confidence))
        return results
