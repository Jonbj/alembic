"""Tests for backtest CLI runner helpers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

# Import the helpers we'll write in run_backtest.py
from scripts.run_backtest import _estimate_cost, phase2_infer


def test_estimate_cost_scales_with_article_count():
    """_estimate_cost returns a positive float proportional to article count."""
    cost_10 = _estimate_cost(10)
    cost_100 = _estimate_cost(100)

    assert cost_10 > 0
    assert cost_100 == pytest.approx(cost_10 * 10)


def test_phase2_infer_dry_run_writes_zero_score(monkeypatch):
    """--dry-run writes score=0.0 for every pending row without calling any LLM."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    pending_rows = [
        (1, "AAPL", datetime(2025, 10, 1, 14, tzinfo=timezone.utc),
         "https://x.com/1", "Apple earns record profit"),
    ]
    mock_cur.fetchall.return_value = pending_rows

    processed = phase2_infer(mock_conn, run_id="test", dry_run=True)

    assert processed == 1
    # UPDATE called with score=0.0
    update_call = mock_cur.execute.call_args_list[-1]
    assert "score=0.0" in update_call[0][0] or 0.0 in update_call[0][1]
    mock_conn.commit.assert_called_once()


def test_phase2_infer_checkpoint_skips_scored_rows(monkeypatch):
    """phase2_infer skips rows that already have a score (checkpoint/resume)."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    # DB returns 0 pending rows (all already scored)
    mock_cur.fetchall.return_value = []

    processed = phase2_infer(mock_conn, run_id="test", dry_run=True)

    assert processed == 0
    # SELECT query must filter score IS NULL
    select_call = mock_cur.execute.call_args_list[0]
    assert "score IS NULL" in select_call[0][0]


def test_phase2_infer_sql_filters_by_run_id(monkeypatch):
    """phase2_infer's SELECT query includes run_id filter."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    mock_cur.fetchall.return_value = []

    phase2_infer(mock_conn, run_id="specific-run-id", dry_run=True)

    select_call = mock_cur.execute.call_args_list[0]
    assert "specific-run-id" in select_call[0][1]


@pytest.mark.asyncio
async def test_infer_batch_returns_result_per_row():
    """_infer_batch returns one (row_id, result) tuple per input row."""
    from scripts.run_backtest import _infer_batch

    rows = [
        (42, "AAPL", datetime(2025, 12, 1, tzinfo=timezone.utc), "https://x.com/1", "Apple profit up"),
        (43, "MSFT", datetime(2025, 12, 1, tzinfo=timezone.utc), "https://x.com/2", "Microsoft beats"),
    ]

    mock_result = MagicMock()
    mock_result.score = 0.5
    mock_result.confidence = 0.8
    mock_result.reasoning = "bullish"
    mock_result.model_id = "ensemble:kimi+qwen"
    mock_result.ensemble_std = 0.05
    mock_result.fallback_used = False

    mock_run_inference = AsyncMock(return_value=(mock_result, []))

    with patch("scripts.run_backtest.run_inference", mock_run_inference):
        results = await _infer_batch(rows, clients=[], aggregator=MagicMock(),
                                     finbert=MagicMock(), budget_tracker=MagicMock())

    assert len(results) == 2
    assert results[0] == (42, (mock_result, []))
    assert results[1] == (43, (mock_result, []))


def test_estimate_cost_uses_two_models():
    """_estimate_cost must reflect 2-model ensemble (not 4)."""
    cost_1 = _estimate_cost(1)
    cost_2 = _estimate_cost(2)
    assert cost_2 == pytest.approx(cost_1 * 2)
    cost_per_call = (300 * 2.0 + 100 * 6.0) / 1_000_000
    assert cost_1 == pytest.approx(2 * cost_per_call)
