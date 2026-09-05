"""Regression tests for the offline FinBERT distillation pipeline (#466)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
import torch

from src.llm.finbert_distillation import (
    DistillationExample,
    build_model_input,
    chronological_split,
    compute_metrics,
    distillation_loss,
    polarity_from_logits,
)


def _example(index: int, *, polarity: float = 0.2, forward_return: float = 0.01):
    return DistillationExample(
        signal_id=index,
        news_log_id=1000 + index,
        generated_at=datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(days=index),
        symbol="AAPL",
        title=f"Headline {index}",
        body=f"Body {index}",
        teacher_polarity=polarity,
        forward_return=forward_return,
    )


def test_chronological_split_is_time_forward_even_with_unsorted_input():
    examples = [_example(index) for index in [5, 1, 4, 0, 3, 2]]

    train, validation = chronological_split(examples, validation_fraction=1 / 3)

    assert [row.signal_id for row in train] == [0, 1, 2, 3]
    assert [row.signal_id for row in validation] == [4, 5]
    assert max(row.generated_at for row in train) < min(
        row.generated_at for row in validation
    )


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1, 1.1])
def test_chronological_split_rejects_degenerate_fraction(fraction):
    with pytest.raises(ValueError, match="validation_fraction"):
        chronological_split([_example(0), _example(1)], validation_fraction=fraction)


def test_model_input_prepends_sanitized_ticker_and_keeps_headline():
    row = _example(1)
    row = replace(row, symbol="$ＡＡＰＬ", title="Beat\u202e hidden")

    text = build_model_input(row)

    assert text.startswith("Ticker: AAPL\nHeadline:")
    assert "Beat hidden" in text
    assert "\u202e" not in text


def test_model_input_matches_live_512_character_budget():
    row = replace(_example(1), title="T" * 300, body="B" * 500)

    text = build_model_input(row)

    assert len(text) == 512
    assert text.startswith("Ticker: AAPL\nHeadline:")
    assert "B" in text


def test_polarity_uses_finbert_label_mapping_not_positional_assumptions():
    logits = torch.tensor([[0.0, 2.0, -1.0]])
    label2id = {"negative": 0, "positive": 1, "neutral": 2}

    polarity = polarity_from_logits(logits, label2id)

    probs = torch.softmax(logits, dim=-1)
    assert polarity.item() == pytest.approx((probs[0, 1] - probs[0, 0]).item())


def test_distillation_loss_combines_soft_mse_and_direction_cross_entropy():
    logits = torch.tensor([[2.0, -1.0, 0.0], [-1.0, 2.0, 0.0]])
    targets = torch.tensor([-0.7, 0.8])
    label2id = {"negative": 0, "positive": 1, "neutral": 2}

    loss = distillation_loss(logits, targets, label2id)

    polarities = polarity_from_logits(logits, label2id)
    expected_mse = torch.nn.functional.mse_loss(polarities, targets)
    expected_ce = torch.nn.functional.cross_entropy(logits, torch.tensor([0, 1]))
    assert loss.item() == pytest.approx((expected_mse + expected_ce).item())


def test_compute_metrics_reports_ic_hit_rate_and_teacher_mae():
    predictions = [-0.7, 0.1, 0.8]
    rows = [
        _example(0, polarity=-0.8, forward_return=-0.02),
        _example(1, polarity=0.2, forward_return=0.01),
        _example(2, polarity=0.6, forward_return=0.04),
    ]

    metrics = compute_metrics(predictions, rows)

    assert metrics == {
        "n": 3,
        "ic": pytest.approx(1.0),
        "hit_rate": pytest.approx(1.0),
        "mae": pytest.approx((0.1 + 0.1 + 0.2) / 3),
    }
