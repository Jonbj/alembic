# Three-Model Sentiment Ensemble — Handoff Brief

**Status:** requirements locked, implementation NOT started. This is a handoff
document for an implementing agent: context, locked design decisions, exact
touch-points, acceptance criteria, and the kickoff prompt (last section).

**Why:** the 2-model ensemble is structurally fragile — with two models, any
material disagreement is unresolvable (no tie-breaker) and forces the FinBERT
fallback. Measured on live data 2026-07-01→10: 70-86% of ~260 signals/day fell
back (kimi-k2.6 ⇄ glm-5.2 directional disagreement), neutralizing S4. Raising
`ENSEMBLE_DIVERGENCE_STD` 0.30→0.40 had **no effect** (fallback 75-80% after)
because the disagreement distribution is bimodal: agreeing pairs sit at
std≈0.03, disagreeing pairs at std≳0.40 (opposite polarity signs). A third
model converts unresolvable ties into majority decisions.

**Current live pair (since 2026-07-11):** glm-5.2 + gpt-oss:20b, selected via
Redis `config:sentiment_llm_models` = `glm52,gptoss`. The 3rd model should be
**deepseek-v4-pro** (Stage 1 retro screen: accuracy 0.47 — tied best with glm —
0 parse fails, 6.2s latency; table in
`~/.claude/.../memory/project_sentiment_model_comparison.md` and below).

Stage 1 reference (n=17, indicative only):

| model | accuracy | parse_fail | avg_conf | avg_latency_ms |
|---|---|---|---|---|
| glm-5.2:cloud | 0.47 | 0.00 | 0.24 | 2784 |
| deepseek-v4-pro:cloud | 0.47 | 0.00 | 0.31 | 6241 |
| gpt-oss:20b-cloud | 0.41 | 0.00 | 0.37 | 8730 |
| kimi-k2.6:cloud | 0.29 | 0.00 | 0.20 | 29174 |
| qwen3.5:cloud | 0.27 | 0.12 | 0.19 | 46316 |

## Locked design decisions

**D1 — Majority-of-3 aggregation.** In `EnsembleAggregator.aggregate()`
(`src/llm/ensemble.py`), when exactly 3 eligible outputs are present and the
all-model std fails the divergence check, do NOT immediately return None.
Instead find the best-agreeing pair (minimum pairwise polarity distance); if
that pair's std passes `divergence_threshold`, aggregate the pair
(confidence-weighted, as today) and treat the outlier as ineligible. Return
None only when NO pair agrees. With 2 eligible outputs, behavior is unchanged
(today's semantics). Do not invent a new voting scheme — this is the minimal
generalization.

**D2 — Outlier audit trail.** The dropped outlier must still be persisted to
`llm_responses` with `eligible=false`. Plumbing exists since commit `7d530bb`:
`PostgreSQLStore.log_llm_responses(..., force_ineligible=...)` and the
fallback path already persists divergent outputs. The aggregator must expose
which model_ids actually entered the consensus (`AggregatedResult.model_ids`
already exists) so the caller can mark only the outlier ineligible — check how
`eligible` is computed today (confidence-based) and extend without breaking
QS-06 semantics documented in `log_llm_responses`'s docstring.

**D3 — Semaphore capacity 2→3.** `src/llm/client.py:626`:
`_OLLAMA_SEM_SLOTS = 2` (hardcoded). Make it configurable
(`OLLAMA_SEM_SLOTS` env, default 3) — but note the Redis token pool is
initialized ONCE via SETNX on `ollama:sem:init`: changing the slot count
requires `redis-cli DEL ollama:sem ollama:sem:init` at deploy, or an init
script that re-seeds when the configured count differs from LLEN. Handle this
in code (compare configured slots vs pool size at init), not via a runbook
footnote — a forgotten DEL would silently serialize the 3rd model's calls.

**D4 — Selection stays the switch.** The 3-model mode is activated by setting
`config:sentiment_llm_models` = `glm52,gptoss,deepseek` — no new feature flag.
This requires a `deepseek` registry entry in `src/llm/model_registry.py`
(`SentimentModel("deepseek", "deepseek-v4-pro:cloud", "DeepSeek V4 Pro",
in_all=False)` + aliases + `build_sentiment_clients` mapping —
`OllamaDeepseekClient` already exists in `src/llm/client.py:786`). Rollback =
set the key back to `glm52,gptoss`. Keep `in_all=False`: "all" must keep
meaning the 2-model live set until a PO decision changes it.

**D5 — Budget.** 3 models = +50% Ollama calls (~60→90 ensemble items/day →
~270 calls/day). Check `llm_budget` limits (`LLMBudgetTracker`) accommodate
this; `deepseek-v4-pro:cloud` cost entry exists in `src/config.py` (4.0/12.0
per 1M tokens — the priciest of the pool). Compute the projected daily cost in
the plan and surface it for approval if it exceeds the current budget config.

**D6 — Success metrics (7 trading days after enable):**
- FinBERT fallback rate < 30% (from 75-80%); measure via
  `sentiment_signals.fallback_used` daily ratio.
- No sentiment-beat overrun: the 15-min cycle must not queue up (3 sequential
  models worst-case ≈ 2.8+8.7+6.2s ≈ 18s/item with 3 slots; verify in logs).
- S4 tradeable signals (positive score ≥ 0.30, fresh) ≥ 3×  the 2-model
  baseline (~15-20/day → target ≥ 45/day at comparable news volume).
If metrics miss, revert the Redis key and report — do not tune thresholds
ad hoc.

## Constraints

- CLAUDE.md rules apply (read it first): LLM never in the execution hot path,
  sentiment score = polarity × confidence, DK-CoT prompt unchanged.
- Do NOT touch: strategy allocations, risk caps, portfolio scheduler, the
  divergence threshold value, FinBERT fallback behavior for the no-majority
  case.
- The QS-03 `agreement_weighting` flag stays default-off (gated on QX-01).
- Full test suite must pass except the 10 known pre-existing failures
  (5 tests/api/test_weight_approval.py, 3 tests/workers/test_sec_edgar_ingestion.py,
  2 tests/workers/test_sentiment_worker.py::TestEnsembleWeightReading).
- Deploy = `docker compose build api worker worker-inference beat && up -d`
  (src is baked into images) + the semaphore re-seed of D3.

## Kickoff prompt for the implementing agent

```
You are working in /home/stefano/Documents/Projects/Alembic (LLM trading
system, paper trading). Read CLAUDE.md, then read
docs/superpowers/plans/2026-07-11-three-model-ensemble-handoff.md — it locks
the design decisions (D1-D6) for adding a third model to the news-sentiment
ensemble with majority-of-3 aggregation.

Process requirements:
1. Use the superpowers:writing-plans skill to turn the handoff brief into a
   full TDD implementation plan (bite-sized tasks, exact code in every step),
   then execute it with superpowers:subagent-driven-development — this flow
   caught two real bugs on the Stage 1 work; do not skip the reviews.
2. Strict TDD throughout: the majority-of-3 aggregator behavior (D1) and the
   semaphore re-seed (D3) are the two highest-risk changes — write their
   failing tests first, including: 2-of-3 agreement aggregates the pair and
   drops the outlier; no-pair-agreement returns None; 2-model behavior
   unchanged; slot-count change re-seeds the Redis pool.
3. Commit per task on a feature branch (deployment branch naming convention:
   <topic>-YYYY-MM-DD). Do NOT merge to main, do NOT deploy, do NOT change
   the config:sentiment_llm_models Redis key: enabling 3-model mode is an
   operator action after review.
4. Budget check (D5): compute projected daily cost, compare to llm_budget
   limits, and put the number in your final report.
5. Finish with: branch name + commits, test counts (expect only the 10 known
   pre-existing failures listed in the brief), the D6 metrics you did NOT
   yet measure (they need live data), and anything you deviated from the
   brief with why. Ask before deviating from D1-D6.
```
