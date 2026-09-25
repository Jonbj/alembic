"""
FinBERT fallback with entropic confidence mapping and int8 quantization.

FinBERT outputs 3-class probabilities: positive, neutral, negative.
Confidence is derived from 1 - normalized_entropy, so a peaked distribution
→ high confidence, uniform distribution → low confidence (~0).
Polarity maps the positive/negative balance accounting for neutral dampening.

int8 quantization: PyTorch dynamic quantization is applied after loading.
Weights are stored as int8; activations stay fp32. Result: ~50% RAM reduction
(~420MB → ~210MB), ~30% faster CPU inference, ~0.1-0.5% accuracy drop on
3-class classification — acceptable for a fallback role.
"""

import json
import logging
import math
import sys
import threading
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal

from src.text.sanitizer import sanitize_text

if TYPE_CHECKING:
    from src.models.news import NewsItem

logger = logging.getLogger(__name__)

FINBERT_MODEL = "ProsusAI/finbert"
FINBERT_REVISION = "4556d13015211d73dccd3fdd39d39232506f3e43"


def finbert_runtime_provenance(*, torch_module=None, transformers_version: str | None = None) -> dict[str, object]:
    """Return the immutable model and runtime identity used by FinBERT."""
    if torch_module is None:
        import torch as torch_module
    if transformers_version is None:
        import transformers

        transformers_version = transformers.__version__

    cuda_available = torch_module.cuda.is_available()
    cuda_devices = torch_module.cuda.device_count() if cuda_available else 0
    return {
        "model": FINBERT_MODEL,
        "revision": FINBERT_REVISION,
        "torch": torch_module.__version__,
        "transformers": transformers_version,
        "device": "cuda:0" if cuda_available else "cpu",
        "cuda_devices": cuda_devices,
    }


def _log_runtime_provenance(provenance: dict[str, object]) -> None:
    logger.info("FinBERT runtime provenance: %s", json.dumps(provenance, sort_keys=True))


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
    FinBERT sentiment analysis client with int8 quantization.

    Uses the ProsusAI/finbert model from HuggingFace transformers.
    The pipeline is lazy-loaded on first use to avoid slow startup.
    After loading, dynamic int8 quantization is applied to Linear layers.
    """

    _MODEL_NAME = FINBERT_MODEL
    _MAX_TOKENS = 512  # FinBERT context window in tokens

    def __init__(self) -> None:
        self._pipe = None
        self._lock = threading.Lock()

    def _get_pipeline(self):
        """
        Lazy-load the FinBERT pipeline and apply int8 quantization.

        Import transformers inside this method to avoid slow startup
        when FinBERT is not used (e.g., ensemble succeeds).

        Thread-safe: multiple run_in_executor threads can call this
        concurrently; double-checked locking ensures a single init.
        """
        if self._pipe is None:
            with self._lock:
                if self._pipe is None:
                    import torch
                    import torch.nn as nn
                    from transformers import pipeline

                    provenance = finbert_runtime_provenance(torch_module=torch)
                    device = 0 if provenance["device"] == "cuda:0" else -1
                    self._pipe = pipeline(
                        "text-classification",
                        model=self._MODEL_NAME,
                        tokenizer=self._MODEL_NAME,
                        revision=FINBERT_REVISION,
                        top_k=None,  # return all class scores (replaces deprecated return_all_scores=True)
                        device=device,
                    )
                    if device == -1:
                        # Dynamic int8 quantization is CPU-only. It keeps the fallback
                        # usable when no NVIDIA runtime is present.
                        torch.quantization.quantize_dynamic(
                            self._pipe.model,
                            {nn.Linear},
                            dtype=torch.qint8,
                            inplace=True,
                        )
                        logger.info("FinBERT loaded on CPU with int8 dynamic quantization")
                    else:
                        logger.info("FinBERT loaded on CUDA without CPU quantization")
                    _log_runtime_provenance(provenance)
        return self._pipe

    def analyze(self, text: str) -> FinBERTResult:
        """
        Analyze text sentiment using FinBERT.

        Args:
            text: Input text to analyze (truncated to 512 tokens by the tokenizer)

        Returns:
            FinBERTResult with polarity, confidence, and worker_type
        """
        pipe = self._get_pipeline()
        clean_text = sanitize_text(text)
        # truncation=True + max_length lets the tokenizer truncate at the token
        # boundary (not character boundary — fixes A-13 character-slice bug).
        raw = pipe(clean_text, truncation=True, max_length=self._MAX_TOKENS)
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
                results.append(
                    (article.timestamp.date(), result.polarity * result.confidence)
                )
        return results


def main() -> int:
    """Print FinBERT runtime evidence; optionally require CUDA for container health."""
    provenance = finbert_runtime_provenance()
    print(json.dumps(provenance, sort_keys=True))
    if "--require-cuda" in sys.argv and provenance["cuda_devices"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
