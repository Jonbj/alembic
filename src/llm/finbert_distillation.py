"""Offline FinBERT knowledge distillation utilities.

This module deliberately has no import or call site in the live sentiment path.
It trains and evaluates a checkpoint from historical, forward-return-confirmed
ensemble verdicts; publishing or activating that checkpoint is an operator action.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import torch
import torch.nn.functional as F
from scipy.stats import spearmanr
from torch.utils.data import DataLoader, Dataset

from src.text.sanitizer import sanitize_text, sanitize_ticker


MODEL_NAME = "ProsusAI/finbert"
MAX_TOKENS = 512
MAX_INPUT_CHARS = 512


@dataclass(frozen=True, slots=True)
class DistillationExample:
    """One article/ticker teacher verdict with an observable forward return."""

    signal_id: int
    news_log_id: int
    generated_at: datetime
    symbol: str
    title: str
    body: str
    teacher_polarity: float
    forward_return: float


# The earliest usable verdict wins when the same news_log row was scored again.
# Selecting one row per (article, ticker) prevents duplicates crossing the temporal
# split and being memorised on both sides.  ``llm_responses`` is required as proof
# that the parent signal came from an actual cloud-model response, while the final
# aggregate polarity is recovered from score/confidence exactly as it was persisted.
DISTILLATION_QUERY = """
    WITH candidates AS (
        SELECT DISTINCT ON (ss.news_log_id, ss.symbol)
               ss.id AS signal_id,
               ss.news_log_id,
               ss.generated_at,
               ss.symbol,
               nl.title,
               nl.body_snippet,
               GREATEST(-1.0, LEAST(1.0, ss.score / NULLIF(ss.confidence, 0)))
                   AS teacher_polarity,
               ss.forward_return
        FROM sentiment_signals ss
        JOIN news_log nl ON nl.id = ss.news_log_id
        WHERE ss.news_log_id IS NOT NULL
          AND ss.fallback_used = FALSE
          AND ss.model_id LIKE 'ensemble:%'
          AND ss.confidence > 0
          AND ss.forward_return IS NOT NULL
          AND COALESCE(nl.title, '') <> ''
          AND COALESCE(nl.body_snippet, '') <> ''
          AND EXISTS (
              SELECT 1 FROM llm_responses lr WHERE lr.signal_id = ss.id
          )
        ORDER BY ss.news_log_id, ss.symbol, ss.generated_at, ss.id
    )
    SELECT signal_id, news_log_id, generated_at, symbol, title, body_snippet,
           teacher_polarity, forward_return
    FROM candidates
    ORDER BY generated_at, signal_id
"""


def fetch_distillation_examples(connection) -> list[DistillationExample]:
    """Read the immutable training population without changing database state."""
    with connection.cursor() as cursor:
        cursor.execute(DISTILLATION_QUERY)
        columns = [description[0] for description in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return [
        DistillationExample(
            signal_id=int(row["signal_id"]),
            news_log_id=int(row["news_log_id"]),
            generated_at=row["generated_at"],
            symbol=str(row["symbol"]),
            title=str(row["title"] or ""),
            body=str(row["body_snippet"] or ""),
            teacher_polarity=float(row["teacher_polarity"]),
            forward_return=float(row["forward_return"]),
        )
        for row in rows
    ]


def chronological_split(
    examples: Sequence[DistillationExample], validation_fraction: float = 0.20
) -> tuple[list[DistillationExample], list[DistillationExample]]:
    """Return an oldest-first train set and a strictly later validation set."""
    if not 0.0 < validation_fraction < 1.0:
        raise ValueError("validation_fraction must be between 0 and 1")
    if len(examples) < 2:
        raise ValueError("at least two examples are required for a temporal split")

    ordered = sorted(examples, key=lambda row: (row.generated_at, row.signal_id))
    validation_size = max(1, math.ceil(len(ordered) * validation_fraction))
    validation_size = min(validation_size, len(ordered) - 1)
    return ordered[:-validation_size], ordered[-validation_size:]


def build_model_input(example: DistillationExample) -> str:
    """Build the ticker-aware text shared by training and offline evaluation."""
    symbol = sanitize_ticker(example.symbol) or "UNKNOWN"
    title = sanitize_text(example.title)
    body = sanitize_text(example.body)
    return f"Ticker: {symbol}\nHeadline: {title}\nNews: {body}"[:MAX_INPUT_CHARS]


def _normalised_label2id(label2id: dict[str, int]) -> dict[str, int]:
    normalised = {str(label).lower(): int(index) for label, index in label2id.items()}
    required = {"positive", "neutral", "negative"}
    if not required.issubset(normalised):
        raise ValueError(f"FinBERT label mapping lacks {sorted(required - set(normalised))}")
    return normalised


def polarity_from_logits(logits: torch.Tensor, label2id: dict[str, int]) -> torch.Tensor:
    """Map FinBERT class logits to a differentiable continuous polarity."""
    mapping = _normalised_label2id(label2id)
    probabilities = torch.softmax(logits, dim=-1)
    return (
        probabilities[..., mapping["positive"]]
        - probabilities[..., mapping["negative"]]
    )


def _direction_targets(targets: torch.Tensor, label2id: dict[str, int]) -> torch.Tensor:
    mapping = _normalised_label2id(label2id)
    negative = torch.full_like(targets, mapping["negative"], dtype=torch.long)
    neutral = torch.full_like(targets, mapping["neutral"], dtype=torch.long)
    positive = torch.full_like(targets, mapping["positive"], dtype=torch.long)
    return torch.where(targets < 0, negative, torch.where(targets > 0, positive, neutral))


def distillation_loss(
    logits: torch.Tensor,
    teacher_polarities: torch.Tensor,
    label2id: dict[str, int],
) -> torch.Tensor:
    """Equal-weight soft-polarity MSE plus hard sign cross-entropy."""
    soft_loss = F.mse_loss(
        polarity_from_logits(logits, label2id), teacher_polarities
    )
    direction_loss = F.cross_entropy(
        logits, _direction_targets(teacher_polarities, label2id)
    )
    return soft_loss + direction_loss


def compute_metrics(
    predictions: Sequence[float], examples: Sequence[DistillationExample]
) -> dict[str, float | int]:
    """Compute price IC/hit-rate and imitation MAE on one fixed population."""
    if len(predictions) != len(examples):
        raise ValueError("predictions and examples must have the same length")
    if not examples:
        return {"n": 0, "ic": float("nan"), "hit_rate": float("nan"), "mae": float("nan")}

    predicted = np.asarray(predictions, dtype=float)
    returns = np.asarray([row.forward_return for row in examples], dtype=float)
    teachers = np.asarray([row.teacher_polarity for row in examples], dtype=float)
    correlation = spearmanr(predicted, returns).statistic if len(examples) >= 3 else float("nan")
    return {
        "n": len(examples),
        "ic": float(correlation),
        "hit_rate": float(np.mean(np.sign(predicted) == np.sign(returns))),
        "mae": float(np.mean(np.abs(predicted - teachers))),
    }


class _TokenizedExamples(Dataset):
    def __init__(self, examples: Sequence[DistillationExample], tokenizer, max_tokens: int):
        self.examples = list(examples)
        self.tokenizer = tokenizer
        self.max_tokens = max_tokens

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.examples[index]
        encoded = self.tokenizer(
            build_model_input(row), truncation=True, max_length=self.max_tokens
        )
        encoded["teacher_polarity"] = row.teacher_polarity
        return encoded


def _collator(tokenizer):
    def collate(rows: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
        targets = torch.tensor(
            [row.pop("teacher_polarity") for row in rows], dtype=torch.float32
        )
        batch = tokenizer.pad(rows, padding=True, return_tensors="pt")
        batch["teacher_polarity"] = targets
        return batch

    return collate


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def train_model(
    model,
    tokenizer,
    examples: Sequence[DistillationExample],
    *,
    device: torch.device,
    epochs: int = 3,
    batch_size: int = 8,
    learning_rate: float = 2e-5,
    max_tokens: int = MAX_TOKENS,
    seed: int = 466,
    progress: Callable[[str], None] | None = None,
) -> list[float]:
    """Fine-tune all FinBERT parameters and return mean loss for each epoch."""
    if epochs < 1 or batch_size < 1 or learning_rate <= 0:
        raise ValueError("epochs, batch_size and learning_rate must be positive")
    seed_everything(seed)
    generator = torch.Generator().manual_seed(seed)
    loader = DataLoader(
        _TokenizedExamples(examples, tokenizer, max_tokens),
        batch_size=batch_size,
        shuffle=True,
        generator=generator,
        collate_fn=_collator(tokenizer),
    )
    model.to(device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    history: list[float] = []
    label2id = model.config.label2id

    progress_interval = max(1, len(loader) // 10)
    for epoch in range(epochs):
        total_loss = 0.0
        observations = 0
        for batch_number, batch in enumerate(loader, start=1):
            targets = batch.pop("teacher_polarity").to(device)
            inputs = {name: tensor.to(device) for name, tensor in batch.items()}
            optimizer.zero_grad(set_to_none=True)
            logits = model(**inputs).logits
            loss = distillation_loss(logits, targets, label2id)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            count = len(targets)
            total_loss += float(loss.detach()) * count
            observations += count
            if progress and (
                batch_number % progress_interval == 0 or batch_number == len(loader)
            ):
                progress(
                    f"epoch {epoch + 1}/{epochs}: batch {batch_number}/{len(loader)}"
                )
        history.append(total_loss / observations)
    return history


def predict_polarities(
    model,
    tokenizer,
    examples: Sequence[DistillationExample],
    *,
    device: torch.device,
    batch_size: int = 16,
    max_tokens: int = MAX_TOKENS,
    progress: Callable[[str], None] | None = None,
) -> list[float]:
    """Return continuous polarities without quantisation or live-path side effects."""
    loader = DataLoader(
        _TokenizedExamples(examples, tokenizer, max_tokens),
        batch_size=batch_size,
        shuffle=False,
        collate_fn=_collator(tokenizer),
    )
    model.to(device)
    model.eval()
    predictions: list[float] = []
    progress_interval = max(1, len(loader) // 10)
    with torch.inference_mode():
        for batch_number, batch in enumerate(loader, start=1):
            batch.pop("teacher_polarity")
            inputs = {name: tensor.to(device) for name, tensor in batch.items()}
            logits = model(**inputs).logits
            polarities = polarity_from_logits(logits, model.config.label2id)
            predictions.extend(float(value) for value in polarities.cpu())
            if progress and (
                batch_number % progress_interval == 0 or batch_number == len(loader)
            ):
                progress(f"batch {batch_number}/{len(loader)}")
    return predictions


def save_checkpoint(model, tokenizer, output_dir: Path, metadata: dict[str, Any]) -> None:
    """Save a standard HuggingFace checkpoint plus its reproducibility metadata."""
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    (output_dir / "distillation_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def example_manifest(examples: Iterable[DistillationExample]) -> list[dict[str, Any]]:
    """Serialisable provenance manifest without article text."""
    return [
        {
            key: value
            for key, value in asdict(example).items()
            if key not in {"title", "body"}
        }
        for example in examples
    ]
