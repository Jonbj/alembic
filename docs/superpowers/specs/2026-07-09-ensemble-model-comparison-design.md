# Sentiment Ensemble Model Comparison — Design

**Date:** 2026-07-09
**Status:** Approved, pending implementation plan

## Motivation

Earlier this session we diagnosed and fixed an order drought on Alpaca: the 2026-06-29
qwen3.5→GLM-5.2 swap in the sentiment ensemble (Kimi K2.6 + GLM-5.2) made the pair
disagree (ensemble_std ≥ 0.30) far more often than Kimi+Qwen3.5 did, pushing the
FinBERT-fallback rate from ~15-20% to ~70-86% of signals. FinBERT fallback scores are
much weaker (avg |score| 0.07 vs 0.20, confidence 0.33 vs 0.65), so they rarely clear
the entry threshold — 68% of `execution_decisions` over 14 days were `SKIP_THRESHOLD`.
Immediate fix applied: `ENSEMBLE_DIVERGENCE_STD` 0.30→0.40 + loss-feedback
`recovery_win_streak` 5→3 (deployed).

That swap was a one-off manual decision justified by a marketing-style claim
("GLM-5.2 has better calibrated long-horizon reasoning") that was never measured before
going live, and the project's own backtest scripts (`scripts/run_backtest.py`,
`scripts/backtest_smallmid_ic.py`) validate a *different* pair (GLM-5.1 + Deepseek-v4-pro)
than what's live (Kimi + GLM-5.2) — so no existing validation would have caught the
regression. This spec covers a two-stage comparison to (a) get an early read on whether
the current pool is still well-chosen, and (b) build a repeatable, low-cost way to
evaluate model-pool changes on real traffic before they're pushed live, so this doesn't
happen silently again.

Candidates to evaluate against the current pair (Kimi K2.6, GLM-5.2): **gpt-oss:20b**
(OpenAI open-weight — the only non-Chinese-lab model in the current pool, chosen for
structured-output reliability and lab diversity), **qwen3.5** (the model removed on
2026-06-29 — worth re-checking now that ticker resolution is fully deterministic and
independent of the sentiment LLMs, so qwen's original "aggressive ticker extraction"
complaint may no longer apply to this path), and **deepseek-v4-pro** (already configured
and used in the backtest scripts, but never in the live worker — including it lets us
align backtest and live validation).

## Stage 1 — Retrospective screen (cheap, indicative only)

**Data:** `news_labels WHERE status='labeled'` — **17 rows today** (of 148 total; the
rest are `pending`, un-annotated). None have `forward_return_1h/1d/2d` populated yet.
This is not enough for a statistically meaningful IC — Stage 1 is a coarse sanity check
only (directional accuracy vs `gt_sentiment_dir`, JSON-parse reliability), not a ranking.
All 17 labeled rows have `text_adequacy='full'`, so the body text is representative
(not truncated), unlike the 122-char average `news_log.body_snippet`.

**Script:** `scripts/compare_models_retro.py`
- For each of the 17 labeled rows × 5 models (Kimi, GLM-5.2, gpt-oss:20b, qwen3.5,
  deepseek-v4-pro): build the DK-CoT prompt (import `_DK_COT_PROMPT` from
  `src/workers/sentiment.py`, don't duplicate it) using `body_snippet` as body and
  `gt_tickers[0]` (fallback `extracted_tickers[0]`) as symbol; call the model directly.
- Idempotent CSV cache keyed by `(label_id, model_id)` — same resumable pattern as the
  S7 POC-2b tone-scoring harness. Reruns never re-spend tokens on already-cached rows.
- Spend goes through the existing `LLMBudgetTracker` so actual cost is visible, not
  assumed.
- Output: markdown table per model — directional accuracy vs `gt_sentiment_dir`
  (`polarity > 0.1` → positive, `< -0.1` → negative, else neutral — same style of
  deadzone as the existing MarketAux near-neutral prefilter), JSON-parse failure count,
  avg confidence, avg latency.

## Stage 2 — Shadow mode on live traffic (the real answer)

**Mechanism:** inline in `process_news_item` (`src/workers/sentiment.py`), *after* the
live signal is written and never blocking it. Fire-and-forget queries to gpt-oss:20b,
qwen3.5, deepseek-v4-pro using the same `clean_body`/`clean_symbol` already in memory
for the live item (full ~600-char text, not the truncated `news_log.body_snippet` —
this is why shadow can't just replay `news_log` retroactively and has to ride along
with live processing).

**Isolation (hard requirement, mirrors `resolver_shadow.py`'s existing invariant):**
any exception in the shadow path (timeout, malformed JSON, semaphore wait-timeout) is
caught and logged, never re-raised, never delays or alters the live signal write.

**Concurrency:** new Redis-distributed semaphore `ollama:sem:shadow`, 3 slots (one per
shadow candidate), entirely separate from the live `ollama:sem` (2 slots). Shadow load
can never compete with or slow down the live Kimi/GLM-5.2 calls.

**Toggle:** Redis key `shadow:model_comparison:started_at` (not a static env var) —
set once on the first shadow call. Runtime-readable/writable like
`feedback:entry_threshold` / `sentiment:llm_models`, so the system can turn itself off
(see Auto-report below) without a redeploy.

**Storage:** new table `llm_shadow_responses`:
```
id BIGSERIAL PK
news_log_id BIGINT REFERENCES news_log(id)
model_id TEXT
polarity DOUBLE PRECISION
confidence DOUBLE PRECISION
reasoning TEXT
parse_error BOOLEAN
latency_ms INTEGER
created_at TIMESTAMPTZ DEFAULT now()
```
Migration script follows the `scripts/migrate_add_news_source.py` pattern (autocommit
DDL, `lock_timeout='2s'`, safe to run against a live system).

Forward returns are **not** computed separately for shadow rows — `news_log_id` joins
straight to `sentiment_signals.forward_return` (that column depends only on
symbol+time, not on which model scored it, since `decay_monitor_task.py` already
computes it for the live signal on the same news item).

## Auto-report (answers "who remembers in a week?")

New Celery beat task (added to the existing `schedule:` block in
`config/trading.yaml`, daily cadence like `performance_worker_daily`):
1. Reads `shadow:model_comparison:started_at` from Redis. If unset or <7 days elapsed,
   no-op.
2. Once ≥7 days elapsed: runs the comparison/aggregation logic — a function shared with
   `scripts/report_model_comparison.py` (factored once, called from both places, never
   duplicated) — over `llm_shadow_responses` + live `llm_responses` (Kimi/GLM-5.2) +
   `sentiment_signals.forward_return`. Replays `EnsembleAggregator.aggregate()` offline
   for all 10 possible pairs among the 5 models, computing divergence rate at the live
   threshold (0.40), IC/ICIR (`src/performance/ic.py`, same formula as LOO-ICIR
   rebalancing), and JSON-parse failure rate per model.
3. Sends the ranked markdown table via `TelegramNotifier` (same channel as the existing
   weekly performance report / loss-feedback alerts).
4. Deletes/clears the Redis start-time key, which stops future shadow calls (self
   re-arms only if someone manually sets a new start time) — bounds spend to the
   intended window without anyone needing to remember to turn it off.

The manual script remains available for re-running the analysis on demand (e.g. a
different cut of the data) — the beat task solves "nobody remembers", the script
solves "I want to look again later."

## Error handling

- Stage 2 shadow path: total isolation per the invariant above — this is the
  non-negotiable part of the design, since it runs inside the live worker process.
- Stage 1 script: per-row try/except, resumable CSV, isolated from any live path
  entirely (offline script, no interaction with `sentiment.py`'s live code path).
- Beat auto-report task: wrapped like the existing weekly report (`try/except` around
  the Telegram send, logged on failure, never crashes the beat scheduler).

## Testing

- `_shadow_query_candidates` (new function in `sentiment.py`): unit tests proving it
  never raises even when every candidate client fails/times out, that it never calls
  any live-path write (`redis_store.write_sentiment`, `pg_store.write_signal`), and
  that it acquires the dedicated `ollama:sem:shadow` semaphore, not the live one.
- New `pg_store.py` write helper for `llm_shadow_responses`: unit test for the insert
  and for FK-null tolerance (news_log_id may be absent if the URL/ticker conflict path
  in `log_news_item` returned `None`, same as the existing live signal path).
- `scripts/compare_models_retro.py`: unit test with mocked clients over a small fixture,
  verifying the CSV cache skips already-fetched `(label_id, model_id)` pairs on rerun.
- Shared aggregation function (used by both the beat task and the manual report
  script): unit test with a synthetic `llm_shadow_responses` + `sentiment_signals`
  fixture, verifying correct pairwise divergence/IC computation for a known input.

## Out of scope

- Auto-promoting a winning pair to production — this spec only produces a ranked
  report; switching the live pair based on it is a separate, deliberate decision.
- Bumping the live `ollama:sem` semaphore capacity (2→3+) to support a 3-model live
  ensemble — flagged in an earlier session as a real option but a separate
  architecture decision with its own Ollama Cloud cost/capacity sign-off, not part of
  this measurement work.
- Backfilling `forward_return_1h/1d/2d` on the 148 `news_labels` rows or running
  `compute_label_forward_returns.py` — not needed since Stage 1 only checks directional
  accuracy, and Stage 2 gets forward returns for free via `sentiment_signals`.
