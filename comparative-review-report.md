# Comparative Code Review Report — Frontend-Backend Extensions
## 16 AI Model Implementations vs Reference Worktree
**Date:** 2026-05-19
**Reference branch:** `feat/frontend-backend-extensions` (10 commits, 615 tests passing)
**Plan:** `docs/superpowers/plans/2026-05-18-frontend-backend.md`

---

## Executive Summary

All 16 model-specific worktrees produce **functionally identical implementations** of the 10 required tasks. The source code, migrations, and configuration files are byte-for-byte identical across all models (excluding compiled `__pycache__`). The only meaningful differences are in:

1. **Test infrastructure** — the reference worktree has 3 additional test-support fixtures and 1 extra test that were added after the bulk-copy operation used to seed model worktrees.
2. **Commit history granularity** — 15 models produced a single monolithic commit; `qwen3-coder:480b-cloud` produced 4 incremental commits (plus the final squash).

**Bottom line:** No model produced demonstrably better or worse code. The choice of which worktree to merge should be based on commit history preference, not code quality.

---

## Test Results Comparison

| Worktree (Model) | Passed | Errors | Missing vs Reference |
|---|---|---|---|
| **Reference** | **615** | **0** | **—** |
| deepseek-v4-pro:cloud | 605 | 8 | 10 |
| devstral-2:123b-cloud | 605 | 8 | 10 |
| gemini-3-flash-preview:cloud | 605 | 8 | 10 |
| gemma4:31b-cloud | 605 | 8 | 10 |
| glm-5.1:cloud | 605 | 8 | 10 |
| haiku | 605 | 8 | 10 |
| kimi-k2.6:cloud | 605 | 8 | 10 |
| minimax-m2.7:cloud | 605 | 8 | 10 |
| minimax-m2:cloud | 605 | 8 | 10 |
| ministral-3:14b-cloud | 605 | 8 | 10 |
| nemotron-3-super:cloud | 605 | 8 | 10 |
| opus | 605 | 8 | 10 |
| qwen3.5:cloud | 605 | 8 | 10 |
| **qwen3-coder:480b-cloud** | **606** | **8** | **9** |
| qwen3-coder-next:cloud | 605 | 8 | 10 |
| sonnet | 605 | 8 | 10 |

### Root Cause of the 8 Errors

All 8 errors occur in `tests/store/test_pg_news_llm.py` and are **setup failures**, not test logic failures:

```
ERROR at setup of test_log_news_item_inserts_row
ERROR at setup of test_log_llm_responses_inserts_rows
...
```

**Cause:** The model worktrees were bulk-copied from a snapshot that predated the addition of three pytest fixtures to `tests/conftest.py`:

- `pg_conn()` — real psycopg2 connection to test database
- `pg_store(pg_conn)` — PostgreSQLStore instance using that connection
- `sample_signal()` — mock SentimentResult for LLM response logging tests

These fixtures were added to the reference worktree after the model worktrees were created. The missing fixtures prevent 8 tests from running, but the underlying production code is identical.

**Fix (if merging any model worktree):** Copy `tests/conftest.py` and `tests/store/test_pg_store.py` from the reference, or cherry-pick the commit that added them.

---

## Implementation Completeness (10 Tasks)

All 16 model worktrees and the reference implement **all 10 tasks** from the plan:

1. **Migrations 006-007** — `news_log` and `llm_responses` tables (identical SQL)
2. **`pg_store` write methods** — `log_news_item()`, `log_llm_responses()`
3. **`pg_store` read methods** — `get_news_recent()`, `get_llm_feedback()`
4. **`pg_store` delete methods** — `delete_old_news_log()`, `delete_old_llm_responses()`
5. **`write_signal` returns `signal_id`** — `RETURNING id` clause
6. **Sentiment worker logging** — `run_inference()` returns `(SentimentResult, list[ModelOutput])`
7. **FastAPI endpoints** — `/api/positions`, `/api/orders`, `/api/news/recent`, `/api/llm/feedback`, `/api/performance/pnl`, `/api/config`
8. **Retention Celery task** — `run_retention_sweep()` with crontab schedule
9. **YAML retention config** — `news_log_days: 180`, `llm_responses_days: 365`
10. **Tests for all new endpoints** — 5 new test files in `tests/api/`

**Verification method:** `diff -rq` across `src/`, `migrations/`, and `config/` shows zero non-pycache differences between any model worktree and any other (except the minor `pg_store.py` import style difference noted below).

---

## File-Level Comparison

### Source Code (`src/`)

| Aspect | Result |
|---|---|
| Non-pycache differences | **1 file** across all 16 models |
| File | `src/store/pg_store.py` |
| Nature of difference | Reference uses `TYPE_CHECKING` guard for `NewsItem` and `ModelOutput` imports; model worktrees use a runtime `from src.llm.ensemble import ModelOutput` inside `log_llm_responses()`. Functionally equivalent. |

### Migrations (`migrations/`)

| Aspect | Result |
|---|---|
| Differences | **None** (0 files differ) |
| `006_add_news_log.sql` | Identical across all worktrees |
| `007_add_llm_responses.sql` | Identical across all worktrees |

### Configuration (`config/`)

| Aspect | Result |
|---|---|
| Differences | **None** (0 files differ) |
| `trading.yaml` | All worktrees have identical `retention:` block |

### Tests (`tests/`)

| Aspect | Result |
|---|---|
| Non-pycache differences | **3 items** across all 16 models |
| 1. `tests/conftest.py` | Missing `pg_conn`, `pg_store`, `sample_signal` fixtures |
| 2. `tests/test_pg_store.py` | Missing `test_write_signal_returns_signal_id` (was extracted to `tests/store/test_pg_store.py` in reference) |
| 3. `tests/store/test_pg_store.py` | **Missing entirely** in all model worktrees |

---

## Commit History Analysis

### Reference Worktree
- **Total commits:** 118 (108 base + 10 new)
- **New commits:** 10 granular, task-oriented commits
- **Example commit sequence:**
  1. `feat: add news_log and llm_responses tables (migrations 006-007)`
  2. `feat: write_signal returns inserted signal_id (RETURNING id)`
  3. `feat: pg_store — log_news_item and log_llm_responses write methods`
  4. `feat: pg_store — get_news_recent and get_llm_feedback read methods`
  5. `feat: pg_store — delete_old_news_log and delete_old_llm_responses`
  6. `feat: sentiment worker logs raw model outputs`
  7. `feat: add FastAPI trading routes (positions, orders, pnl)`
  8. `feat: add FastAPI news and llm feedback routes`
  9. `feat: add config read/write route with API key auth`
  10. `feat: add nightly retention sweep Celery task`

### 15 Model Worktrees (Single-Commit Pattern)
- **Total commits:** 108 base + 1 or 2 new
- **Commit style:** One monolithic `feat: implement frontend-backend extensions for <model>`
- **Exceptions:**
  - `devstral-2:123b-cloud`: 2 commits (appears to have been restarted and squashed)
  - All others: exactly 1 new commit

### qwen3-coder:480b-cloud (Incremental Pattern)
- **Total commits:** 108 base + 5 new
- **Commit style:** 4 incremental commits + 1 final squash commit
- **Commit sequence:**
  1. `feat: add news_log and llm_responses tables (migrations 006-007)`
  2. `feat: write_signal returns inserted signal_id (RETURNING id)`
  3. `feat: pg_store — log_news_item and log_llm_responses write methods`
  4. `feat: pg_store — get_news_recent and get_llm_feedback read methods`
  5. `feat: implement frontend-backend extensions for qwen3_coder_480b_cloud model`
- **Note:** The 5th commit appears to be a squash of tasks 5-10, since the incremental commits only cover the first 4 tasks.

---

## Code Quality Assessment

### Strengths (Universal)
- **SQL injection prevention:** All worktrees use parameterized queries with `%s` placeholders. The `delete_old_news_log` and `delete_old_llm_responses` methods correctly use `(%s || ' days')::interval` rather than string interpolation.
- **FastAPI dependency injection:** All routes use `Annotated[Type, Depends(func)]` pattern consistently.
- **Celery task idempotency:** `run_retention_sweep()` returns a dict with counts, safe to retry.
- **Test coverage:** All new endpoints have dedicated test files with mocked dependencies.
- **No secrets in code:** API keys are read from environment variables; test key is explicitly labeled `test-api-key-for-testing-only-12345678`.

### Weaknesses (Universal)
- **Monolithic commits:** 15 of 16 models squashed all 10 tasks into a single commit, making bisection and rollback difficult. Only `qwen3-coder:480b-cloud` showed partial incremental history.
- **Missing test fixtures:** All model worktrees lack the `pg_conn`, `pg_store`, and `sample_signal` fixtures needed for `tests/store/test_pg_news_llm.py`.
- **Missing `test_write_signal_returns_signal_id`:** This test validates a critical contract (returning the inserted row ID) and is absent from all model worktrees.
- **Import style inconsistency:** `pg_store.py` in model worktrees uses a runtime import inside `log_llm_responses()` instead of the cleaner `TYPE_CHECKING` pattern used in the reference. This triggers `F401` noqa comments and slightly reduces readability.

### Notable Observations
- **qwen3-coder:480b-cloud** is the only model that attempted incremental commits, suggesting better alignment with the reference workflow. However, it still missed tasks 5-10 in the incremental phase and squashed them in the final commit.
- **No model introduced unique bugs or novel solutions.** The implementations are structurally identical, suggesting the codebase conventions and plan document were specific enough to constrain all outputs to the same path.

---

## Recommendations

### 1. Do Not Merge Any Model Worktree As-Is
All 16 model worktrees have the same 8 test errors and missing fixtures. Merging any of them without cherry-picking the missing test infrastructure would degrade CI reliability.

### 2. The Reference Worktree Is the Cleanest Candidate
- **615/615 tests passing** (vs 605-606/615 for models)
- **10 granular commits** with clear task boundaries (vs 1-5 commits for models)
- **Contains all test fixtures** and the `test_write_signal_returns_signal_id` validation
- **Authoritative commit history** for `git blame` and archaeology

### 3. If You Must Choose a Model Worktree for Attribution Purposes
Select **qwen3-coder:480b-cloud** — it is the only model that demonstrated partial incremental development (4 task-specific commits before the final squash). However, you would still need to cherry-pick the missing test fixtures from the reference.

### 4. To Fix Any Model Worktree (One-Command)
```bash
git checkout feat/frontend-backend-extensions -- tests/conftest.py tests/store/test_pg_store.py
python -m pytest  # should now pass 615/615
```

---

## Appendix: Worktree Paths

| Model | Branch | Path |
|---|---|---|
| Reference | `feat/frontend-backend-extensions` | `.worktrees/frontend-backend` |
| kimi-k2.6:cloud | `feat/fb-kimi_k2_6_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-kimi_k2_6_cloud` |
| qwen3.5:cloud | `feat/fb-qwen3_5_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-qwen3_5_cloud` |
| deepseek-v4-pro:cloud | `feat/fb-deepseek_v4_pro_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-deepseek_v4_pro_cloud` |
| glm-5.1:cloud | `feat/fb-glm_5_1_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-glm_5_1_cloud` |
| devstral-2:123b-cloud | `feat/fb-devstral_2_123b_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-devstral_2_123b_cloud` |
| gemini-3-flash-preview:cloud | `feat/fb-gemini_3_flash_preview_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-gemini_3_flash_preview_cloud` |
| gemma4:31b-cloud | `feat/fb-gemma4_31b_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-gemma4_31b_cloud` |
| haiku | `feat/fb-haiku` | `.worktrees/frontend-backend/.worktrees/frontend-backend-haiku` |
| minimax-m2.7:cloud | `feat/fb-minimax_m2_7_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-minimax_m2_7_cloud` |
| minimax-m2:cloud | `feat/fb-minimax_m2_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-minimax_m2_cloud` |
| ministral-3:14b-cloud | `feat/fb-ministral_3_14b_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-ministral_3_14b_cloud` |
| nemotron-3-super:cloud | `feat/fb-nemotron_3_super_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-nemotron_3_super_cloud` |
| opus | `feat/fb-opus` | `.worktrees/frontend-backend/.worktrees/frontend-backend-opus` |
| qwen3-coder:480b-cloud | `feat/fb-qwen3_coder_480b_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-qwen3_coder_480b_cloud` |
| qwen3-coder-next:cloud | `feat/fb-qwen3_coder_next_cloud` | `.worktrees/frontend-backend/.worktrees/frontend-backend-qwen3_coder_next_cloud` |
| sonnet | `feat/fb-sonnet` | `.worktrees/frontend-backend/.worktrees/frontend-backend-sonnet` |
