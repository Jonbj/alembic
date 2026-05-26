# Backtest Inference Optimization Design

**Date:** 2026-05-26  
**Scope:** `scripts/run_backtest.py` only — live worker unchanged  
**Status:** Approved

## Problem

`phase2_infer` processes articles sequentially: one `asyncio.run(run_inference(...))` per article. Each article takes ~85s (4 model calls in parallel). With 687 pending articles, estimated remaining time is ~16h.

## Changes

### 1. Batch parallelism

Replace the sequential per-article loop with batch processing:

- New async helper `_infer_batch(items, clients, aggregator, finbert, budget_tracker)` uses `asyncio.gather` to run N articles in parallel.
- `phase2_infer` calls `asyncio.run(_infer_batch(...))` once per batch instead of per article.
- DB writes (psycopg2) remain synchronous after each batch — no concurrent DB access.
- New CLI argument `--concurrency INT` (default `5`). Can be lowered if Ollama cloud throttles.
- Checkpoint logging every 50 rows preserved (trigger fires after each batch that crosses a 50-row boundary).

### 2. 2-model ensemble

Change the client list in `phase2_infer` from 4 models to 2:

```python
clients = [OllamaKimiClient(), OllamaQwen35Client()]
```

**Rationale:** `kimi-k2.6:cloud + qwen3.5:cloud` is the highest-confidence pair in historical data (avg_conf=0.76). GLM and Deepseek appear less frequently as the primary ensemble output. FinBERT fallback on divergence is unchanged.

## Expected impact

| Metric | Before | After |
|--------|--------|-------|
| Models per article | 4 | 2 |
| Parallelism | 1 article at a time | 5 articles at a time |
| Estimated time (687 articles) | ~16h | ~23 min |
| Cost estimate | $3.30 | ~$0.85 |

## Files changed

- `scripts/run_backtest.py`: add `_infer_batch`, refactor `phase2_infer`, add `--concurrency` arg, reduce clients to 2

## Files unchanged

- `src/workers/sentiment.py` — live worker keeps 4 models
- `src/llm/ensemble.py` — ensemble logic unchanged
- `src/llm/client.py` — clients unchanged
