"""FinBERT scoring for news articles."""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.news import NewsItem

logger = logging.getLogger(__name__)

_pipeline = None
_pipeline_lock = threading.Lock()


def _get_pipeline():
    """Lazy-load FinBERT pipeline once (singleton, thread-safe)."""
    global _pipeline
    with _pipeline_lock:
        if _pipeline is None:
            import torch
            from transformers import pipeline

            device = 0 if torch.cuda.is_available() else -1
            _pipeline = pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                device=device,
                top_k=None,
            )
    return _pipeline


def score_article(text: str) -> tuple[float, float]:
    """Run FinBERT on text. Returns (polarity, confidence).

    polarity   = pos_prob - neg_prob   ∈ [-1, +1]
    confidence = pos_prob + neg_prob   ∈ [0, 1]   (= 1 - neutral_prob)

    Note: Text is truncated to 512 characters to avoid exceeding model's max token limit.
    FinBERT uses WordPiece tokenizer: 512 tokens ≈ 600-750 words.
    Character truncation (not token) may split words but is sufficient for headlines.
    """
    pipe = _get_pipeline()
    # Truncate to 512 chars (not tokens) - tradeoff: may split words but avoids
    # tokenizer overhead. For headlines/short text this is acceptable.
    truncated = text[:512]
    results = pipe(truncated)
    probs = {r["label"]: r["score"] for r in results[0]}
    pos = probs.get("positive", 0.0)
    neg = probs.get("negative", 0.0)
    return pos - neg, pos + neg


def score_articles(
    articles: list[NewsItem],
    min_confidence: float = 0.3,
) -> list[tuple[date, float]]:
    """Score articles with FinBERT. Returns [(article_date, score)] for articles
    where FinBERT confidence >= min_confidence.

    score = polarity × confidence
    Articles with empty body and title are skipped.
    """
    results = []
    for article in articles:
        text = article.body or article.title
        if not text:
            continue
        try:
            polarity, confidence = score_article(text)
        except Exception as e:
            logger.warning("FinBERT failed for %s: %s", article.id, e)
            continue
        if confidence >= min_confidence:
            results.append((article.timestamp.date(), polarity * confidence))
    return results
