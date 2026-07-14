"""Stage-2 shadow path: total isolation from the live signal path.

The real ensemble client interface (mirrored from run_ensemble_query,
src/llm/ensemble.py) is `client.complete(prompt, response_schema)` — an async
method returning a parsed response object exposing `.polarity`, `.confidence`,
`.reasoning`. `fake_client.complete` below stands in for that.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.workers.sentiment import _shadow_query_candidates


@pytest.mark.asyncio
async def test_shadow_never_raises_even_when_everything_fails():
    redis_store = MagicMock()
    redis_store.get_shadow_comparison_start.return_value = "2026-07-13T00:00:00+00:00"
    redis_store.get_llm_models.return_value = "glm52,gptoss"
    pg_store = MagicMock()
    pg_store.log_shadow_responses.side_effect = RuntimeError("db down")
    with patch("src.workers.sentiment.build_shadow_clients",
               side_effect=RuntimeError("no clients")):
        # Must swallow everything:
        await _shadow_query_candidates(
            clean_body="text", clean_symbol="AAPL", news_log_id=1,
            pg_store=pg_store, redis_store=redis_store,
        )


@pytest.mark.asyncio
async def test_shadow_noop_when_not_armed():
    redis_store = MagicMock()
    redis_store.get_shadow_comparison_start.return_value = None
    pg_store = MagicMock()
    await _shadow_query_candidates(
        clean_body="text", clean_symbol="AAPL", news_log_id=1,
        pg_store=pg_store, redis_store=redis_store,
    )
    pg_store.log_shadow_responses.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_never_touches_live_writes():
    """Whatever happens inside, the shadow path must not call live-path writers."""
    redis_store = MagicMock()
    redis_store.get_shadow_comparison_start.return_value = "2026-07-13T00:00:00+00:00"
    redis_store.get_llm_models.return_value = "glm52,gptoss"
    pg_store = MagicMock()
    fake_client = MagicMock()
    fake_client.model_id = "kimi-k2.6:cloud"
    fake_client.complete = AsyncMock(return_value=MagicMock(polarity=0.3, confidence=0.6,
                                                             reasoning="ok"))
    with patch("src.workers.sentiment.build_shadow_clients", return_value=[fake_client]):
        await _shadow_query_candidates(
            clean_body="text", clean_symbol="AAPL", news_log_id=7,
            pg_store=pg_store, redis_store=redis_store,
        )
    pg_store.write_signal.assert_not_called()
    redis_store.write_sentiment.assert_not_called()
    pg_store.log_shadow_responses.assert_called_once()


@pytest.mark.asyncio
async def test_shadow_partial_failure_keeps_surviving_candidate_row():
    """One candidate raising must not sink the other candidate's row.

    Regression guard for the gather(..., return_exceptions=True) fix: without
    it, a raise from one candidate's coroutine would propagate out of
    asyncio.gather, cancel the sibling in-flight candidate, and skip
    log_shadow_responses entirely — losing ALL shadow rows for the item
    instead of just the one problem candidate.
    """
    redis_store = MagicMock()
    redis_store.get_shadow_comparison_start.return_value = "2026-07-13T00:00:00+00:00"
    redis_store.get_llm_models.return_value = "glm52,gptoss"
    pg_store = MagicMock()

    failing_client = MagicMock()
    failing_client.model_id = "kimi-k2.6:cloud"
    failing_client.complete = AsyncMock(side_effect=RuntimeError("ollama 500"))

    ok_client = MagicMock()
    ok_client.model_id = "qwen3.5:cloud"
    ok_client.complete = AsyncMock(
        return_value=MagicMock(polarity=-0.2, confidence=0.5, reasoning="fine")
    )

    with patch("src.workers.sentiment.build_shadow_clients",
               return_value=[failing_client, ok_client]):
        await _shadow_query_candidates(
            clean_body="text", clean_symbol="AAPL", news_log_id=9,
            pg_store=pg_store, redis_store=redis_store,
        )

    pg_store.log_shadow_responses.assert_called_once()
    (rows,), _ = pg_store.log_shadow_responses.call_args
    model_ids = {r["model_id"] for r in rows}
    assert model_ids == {"kimi-k2.6:cloud", "qwen3.5:cloud"}
    failed_row = next(r for r in rows if r["model_id"] == "kimi-k2.6:cloud")
    assert failed_row["parse_error"] is True
    ok_row = next(r for r in rows if r["model_id"] == "qwen3.5:cloud")
    assert ok_row["parse_error"] is False
    assert ok_row["polarity"] == -0.2
