# Stage 2 Shadow-Mode Model Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended — this touches the live worker hot path) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Score every live news item with the NON-active candidate models (shadow, fire-and-forget, totally isolated), store results in `llm_shadow_responses`, and auto-report a ranked model/pair comparison via Telegram after a 7-day window — implementing the approved spec `docs/superpowers/specs/2026-07-09-ensemble-model-comparison-design.md` (Stage 2 + Auto-report sections).

**Architecture:** Per the spec: inline shadow calls in `process_news_item` AFTER the live write; dedicated Redis semaphore `ollama:sem:shadow` (3 slots); Redis toggle `shadow:model_comparison:started_at` (self-disarming); new table joins forward returns via `news_log_id`. ONE adaptation to the spec (written when the pair was kimi+glm): shadow candidates are derived from the registry as *pool minus active selection* — today that yields kimi/qwen35/deepseek — instead of a hardcoded list, so a future pair swap automatically re-targets the shadow.

**Tech Stack:** Python 3.11, asyncio, psycopg2, Redis, pandas, pytest.

---

## Context (read before Task 1)

Read `CLAUDE.md`, the spec above (all of it), and these verified facts (2026-07-12):

- Live pair via Redis `config:sentiment_llm_models` = `glm52,gptoss`; registry
  `src/llm/model_registry.py` exposes `sentiment_models()` (5 models incl.
  `in_all=False` candidates) and `build_sentiment_clients(keys)`.
- `_OllamaSemaphore` class in `src/llm/client.py:630` takes `(key, slots)` — reusable
  for the shadow pool as-is.
- `process_news_item` / `run_inference` in `src/workers/sentiment.py`: the live write
  sequence ends around line ~300 (`pg_store.log_llm_responses(...)`). `clean_body` /
  `clean_symbol` / `_DK_COT_PROMPT` live in `run_inference`'s scope — the shadow hook
  needs `item`, the news_log_id returned by `log_news_item`, and the stores.
- The isolation invariant (spec §Error handling) is NON-NEGOTIABLE: no exception from
  the shadow path may propagate, delay, or alter anything on the live path.
- Migration pattern: plain SQL files in `migrations/` (latest: 036). The spec mentions
  the `scripts/migrate_add_news_source.py` pattern; for consistency with 034-036 use a
  plain SQL file — application is an operator step.

Constraints:
- Branch `stage2-shadow-2026-07-12` off `main`. No merge, no deploy, no live-DB
  changes, do NOT set the `shadow:model_comparison:started_at` key (arming = operator).
- Strict TDD. Full suite: only the 10 known pre-existing failures
  (5 test_weight_approval, 3 test_sec_edgar_ingestion, 2 TestEnsembleWeightReading).
- Budget: shadow triples per-item LLM calls while armed. The window is bounded by the
  self-disarming toggle; do NOT add other throttles (spec decision).

---

### Task 1: Migration 037 — `llm_shadow_responses`

**Files:**
- Create: `migrations/037_llm_shadow_responses.sql`

- [ ] **Step 1: Write the migration** (schema verbatim from the spec)

```sql
-- 037_llm_shadow_responses.sql
-- Stage 2 shadow-mode model comparison (spec 2026-07-09). Shadow candidates score
-- live news items; forward returns join via news_log_id -> sentiment_signals.
SET lock_timeout = '2s';

CREATE TABLE IF NOT EXISTS llm_shadow_responses (
    id          BIGSERIAL PRIMARY KEY,
    news_log_id BIGINT REFERENCES news_log(id) ON DELETE SET NULL,
    symbol      VARCHAR(20) NOT NULL,
    model_id    TEXT NOT NULL,
    polarity    DOUBLE PRECISION,
    confidence  DOUBLE PRECISION,
    reasoning   TEXT,
    parse_error BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms  INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shadow_model_time
    ON llm_shadow_responses (model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_news
    ON llm_shadow_responses (news_log_id);
```

(`symbol` is added vs the spec's minimal schema: news_log_id can be NULL on URL
conflicts — same as live signals — and without symbol those rows would be unjoinable.)

- [ ] **Step 2: Commit**

```bash
git add migrations/037_llm_shadow_responses.sql
git commit -m "feat(shadow): migration 037 — llm_shadow_responses table"
```

---

### Task 2: Store writer `log_shadow_responses`

**Files:**
- Modify: `src/store/pg_store.py`
- Test: `tests/store/test_shadow_responses.py` (new; copy the `pg_store` fixture
  VERBATIM from `tests/store/test_pg_news_llm.py`)

- [ ] **Step 1: Failing tests**

```python
"""llm_shadow_responses writer — Stage 2 shadow mode."""
from src.store.pg_store import PostgreSQLStore

# pg_store fixture: copy verbatim from tests/store/test_pg_news_llm.py


def test_log_shadow_responses_inserts_rows(pg_store):
    rows = [
        {"news_log_id": 5, "symbol": "AAPL", "model_id": "kimi-k2.6:cloud",
         "polarity": 0.4, "confidence": 0.7, "reasoning": "r", "parse_error": False,
         "latency_ms": 2100},
        {"news_log_id": None, "symbol": "AAPL", "model_id": "qwen3.5:cloud",
         "polarity": None, "confidence": None, "reasoning": None, "parse_error": True,
         "latency_ms": 46000},
    ]
    pg_store.log_shadow_responses(rows)
    cur = pg_store._conn.cursor.return_value
    assert cur.executemany.call_count == 1
    _, batch = cur.executemany.call_args[0]
    batch = list(batch)
    assert len(batch) == 2
    assert batch[1][0] is None      # news_log_id nullable (URL-conflict path)
    assert batch[1][6] is True      # parse_error


def test_log_shadow_responses_empty_noop(pg_store):
    pg_store.log_shadow_responses([])
    assert pg_store._conn.cursor.return_value.executemany.call_count == 0
```

- [ ] **Step 2: RED** — `.venv/bin/pytest tests/store/test_shadow_responses.py -q`
Expected: FAIL `AttributeError: log_shadow_responses`.

- [ ] **Step 3: Implement** (mirror `log_llm_responses`'s transaction pattern)

```python
    _INSERT_SHADOW_RESPONSE = """
        INSERT INTO llm_shadow_responses
            (news_log_id, symbol, model_id, polarity, confidence, reasoning,
             parse_error, latency_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    def log_shadow_responses(self, rows: list[dict]) -> None:
        """Write Stage-2 shadow-model outputs. No-op for empty list.

        Rows are audit/measurement only: nothing in the live path reads them.
        news_log_id may be None (URL/ticker conflict in log_news_item), hence
        the extra symbol column for joinability.
        """
        if not rows:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    self._INSERT_SHADOW_RESPONSE,
                    [
                        (r.get("news_log_id"), r["symbol"], r["model_id"],
                         r.get("polarity"), r.get("confidence"), r.get("reasoning"),
                         bool(r.get("parse_error", False)), r.get("latency_ms"))
                        for r in rows
                    ],
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 4: GREEN + commit**

```bash
git add src/store/pg_store.py tests/store/test_shadow_responses.py
git commit -m "feat(shadow): log_shadow_responses store writer"
```

---

### Task 3: Shadow semaphore + Redis toggle helpers

**Files:**
- Modify: `src/llm/client.py` (one instance), `src/store/redis_store.py` (3 helpers)
- Test: `tests/llm/test_shadow_semaphore.py` (new), `tests/store/` (append toggle tests
  wherever RedisStore helpers are tested — grep `get_feedback_state` for the file)

- [ ] **Step 1: Failing tests**

`tests/llm/test_shadow_semaphore.py`:

```python
from src.llm.client import _ollama_shadow_sem, _ollama_sem


def test_shadow_semaphore_is_separate_pool():
    assert _ollama_shadow_sem._key == "ollama:sem:shadow"
    assert _ollama_shadow_sem._key != _ollama_sem._key
    assert _ollama_shadow_sem._slots == 3
```

RedisStore toggle tests (same mock style as neighbors in the chosen file):

```python
def test_shadow_toggle_roundtrip(redis_store):
    redis_store.set_shadow_comparison_start("2026-07-13T14:00:00+00:00")
    redis_store._r.set.assert_called_once()
    redis_store.get_shadow_comparison_start()
    redis_store._r.get.assert_called_with("shadow:model_comparison:started_at")
    redis_store.clear_shadow_comparison_start()
    redis_store._r.delete.assert_called_with("shadow:model_comparison:started_at")
```

- [ ] **Step 2: RED**, then implement:

`client.py`, right under `_ollama_sem = _OllamaSemaphore()`:

```python
# Stage-2 shadow candidates get their own pool: shadow load must never compete
# with live ensemble calls (spec 2026-07-09 §Concurrency).
_ollama_shadow_sem = _OllamaSemaphore(key="ollama:sem:shadow", slots=3)
```

`redis_store.py` (near the feedback helpers):

```python
    _SHADOW_START_KEY = "shadow:model_comparison:started_at"

    def set_shadow_comparison_start(self, iso_ts: str) -> None:
        """Arm Stage-2 shadow mode (operator action; auto-report disarms it)."""
        self._r.set(self._SHADOW_START_KEY, iso_ts)

    def get_shadow_comparison_start(self) -> str | None:
        raw = self._r.get(self._SHADOW_START_KEY)
        return raw.decode() if isinstance(raw, bytes) else raw

    def clear_shadow_comparison_start(self) -> None:
        self._r.delete(self._SHADOW_START_KEY)
```

- [ ] **Step 3: GREEN + commit**

```bash
git add src/llm/client.py src/store/redis_store.py tests/
git commit -m "feat(shadow): dedicated ollama:sem:shadow pool + Redis arm/disarm toggle"
```

---

### Task 4: `_shadow_query_candidates` in the sentiment worker

**Files:**
- Modify: `src/workers/sentiment.py` (new function + one call in `process_news_item`)
- Modify: `src/llm/client.py` (per-instance semaphore override — see Step 2)
- Test: `tests/workers/test_shadow_query.py` (new)

- [ ] **Step 1: Failing tests** (the spec's three invariants)

```python
"""Stage-2 shadow path: total isolation from the live signal path."""
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
    fake_client.query = AsyncMock(return_value=MagicMock(polarity=0.3, confidence=0.6,
                                                         reasoning="ok"))
    with patch("src.workers.sentiment.build_shadow_clients", return_value=[fake_client]):
        await _shadow_query_candidates(
            clean_body="text", clean_symbol="AAPL", news_log_id=7,
            pg_store=pg_store, redis_store=redis_store,
        )
    pg_store.write_signal.assert_not_called()
    redis_store.write_sentiment.assert_not_called()
    pg_store.log_shadow_responses.assert_called_once()
```

NOTE for the implementer: the exact client-call interface (`query` vs another
method, its signature, and how the response parses into polarity/confidence) must
be mirrored from `run_ensemble_query` in `src/llm/ensemble.py:315` — read it FIRST
and adjust `fake_client` in the test to the real method name BEFORE running RED,
so the test exercises the true interface. The three assertions (never raise /
no-op unarmed / no live writes) are the fixed requirements.

- [ ] **Step 2: Implement**

(a) `build_shadow_clients` in `src/workers/sentiment.py` (module level, so tests can
patch it):

```python
def build_shadow_clients(redis_store):
    """Candidates = registry pool minus the active selection (pair-swap-proof)."""
    from src.llm.model_registry import (
        build_sentiment_clients, normalize_model_selection, sentiment_models,
    )
    from src.llm.client import _ollama_shadow_sem

    _, active_keys, _ = normalize_model_selection(redis_store.get_llm_models())
    candidate_keys = [m.key for m in sentiment_models() if m.key not in active_keys]
    clients = build_sentiment_clients(candidate_keys)
    for c in clients:
        # Route through the dedicated shadow pool (never the live semaphore).
        c._semaphore_override = _ollama_shadow_sem
    return clients
```

(b) Semaphore override support: in `src/llm/client.py`, find where the Ollama call
acquires `_ollama_sem` (around line 720-740, `async with _ollama_sem.acquire()`),
and change it to:

```python
        sem = getattr(self, "_semaphore_override", None) or _ollama_sem
        async with sem.acquire():
```

Read the surrounding method first; keep everything else identical. Add a one-line
class comment on `OllamaCloudClient`: `_semaphore_override` is set only by the
Stage-2 shadow path.

(c) `_shadow_query_candidates` (async, module level in sentiment.py):

```python
async def _shadow_query_candidates(
    clean_body: str, clean_symbol: str, news_log_id: int | None,
    pg_store, redis_store,
) -> None:
    """Stage-2 shadow scoring. TOTAL ISOLATION: never raises, never writes
    live-path stores, never blocks the live signal (already written by caller)."""
    import time as _time
    try:
        if not redis_store.get_shadow_comparison_start():
            return
        clients = build_shadow_clients(redis_store)
        if not clients:
            return
        prompt = _DK_COT_PROMPT.format(text=clean_body[:600], symbol=clean_symbol)
        rows: list[dict] = []
        for client in clients:
            t0 = _time.monotonic()
            try:
                out = await asyncio.wait_for(
                    client.query(prompt, response_schema=LLMSentimentOutput),
                    timeout=45,
                )
                rows.append({
                    "news_log_id": news_log_id, "symbol": clean_symbol,
                    "model_id": client.model_id, "polarity": out.polarity,
                    "confidence": out.confidence, "reasoning": out.reasoning,
                    "parse_error": False,
                    "latency_ms": int((_time.monotonic() - t0) * 1000),
                })
            except Exception:
                rows.append({
                    "news_log_id": news_log_id, "symbol": clean_symbol,
                    "model_id": client.model_id, "polarity": None,
                    "confidence": None, "reasoning": None, "parse_error": True,
                    "latency_ms": int((_time.monotonic() - t0) * 1000),
                })
        pg_store.log_shadow_responses(rows)
    except Exception as exc:
        log.debug("shadow path swallowed: %s", exc)
```

Mirror the real client-call from `run_ensemble_query` (method name/signature) — the
`client.query(...)` line above is the pattern, not gospel.

(d) Call site in `process_news_item`, AFTER the existing
`pg_store.log_llm_responses(...)` block (i.e., after every live write), inside its
own try/except:

```python
        try:
            await _shadow_query_candidates(
                clean_body=sanitize_text(item.body or ""),
                clean_symbol=result.symbol,
                news_log_id=news_log_id,
                pg_store=pg_store,
                redis_store=redis_store,
            )
        except Exception as _sh_exc:      # belt & braces on top of internal catch
            log.debug("shadow hook swallowed: %s", _sh_exc)
```

(If `clean_body` is already available in scope at the call site, use it instead of
re-sanitizing — check; `run_inference` computes it internally, `process_news_item`
may only have `item`.)

- [ ] **Step 3: GREEN + commit**

Run: `.venv/bin/pytest tests/workers/test_shadow_query.py tests/workers/test_sentiment_worker.py -q`
Expected: PASS except the 2 known TestEnsembleWeightReading failures.

```bash
git add src/workers/sentiment.py src/llm/client.py tests/workers/test_shadow_query.py
git commit -m "feat(shadow): fire-and-forget candidate scoring with total live-path isolation"
```

---

### Task 5: Shared comparison module

**Files:**
- Create: `src/performance/model_comparison.py`
- Test: `tests/performance/test_model_comparison.py` (new)

- [ ] **Step 1: Failing test**

```python
"""Pairwise shadow/live model comparison (Stage 2 auto-report core)."""
import pandas as pd

from src.performance.model_comparison import build_comparison


def _rows():
    # 4 news items; model A ~tracks fwd, model B anti-tracks, both agree on 2 items.
    return pd.DataFrame([
        # news_log_id, model_id, polarity, confidence, parse_error
        (1, "A", 0.8, 0.9, False), (1, "B", 0.7, 0.8, False),
        (2, "A", -0.6, 0.8, False), (2, "B", -0.5, 0.9, False),
        (3, "A", 0.9, 0.9, False), (3, "B", -0.9, 0.8, False),   # divergent pair
        (4, "A", 0.5, 0.7, False), (4, "B", None, None, True),   # B parse fail
    ], columns=["news_log_id", "model_id", "polarity", "confidence", "parse_error"])


def _fwd():
    return {1: 0.02, 2: -0.01, 3: 0.03, 4: 0.01}


def test_per_model_stats():
    report = build_comparison(_rows(), _fwd(), divergence_threshold=0.40)
    a = report["models"]["A"]
    assert a["n"] == 4 and a["parse_fail_rate"] == 0.0
    b = report["models"]["B"]
    assert b["parse_fail_rate"] == 0.25
    assert a["ic"] > 0        # A tracks forward returns directionally


def test_pairwise_divergence_rate():
    report = build_comparison(_rows(), _fwd(), divergence_threshold=0.40)
    pair = report["pairs"]["A+B"]
    # 3 items where both parsed; item 3 diverges (std of 0.9/-0.9 >= 0.40)
    assert pair["n_common"] == 3
    assert abs(pair["divergence_rate"] - 1 / 3) < 1e-9
```

- [ ] **Step 2: RED**, then implement `src/performance/model_comparison.py`:

```python
"""Shared Stage-2 comparison logic (beat auto-report + manual script — factored
once per the spec; never duplicated)."""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd


def build_comparison(
    rows: pd.DataFrame,
    fwd_by_news: dict[int, float],
    divergence_threshold: float = 0.40,
) -> dict:
    """Rank models and model-pairs from (shadow + live) per-model outputs.

    Args:
        rows: columns news_log_id, model_id, polarity, confidence, parse_error.
        fwd_by_news: news_log_id -> forward_return (from sentiment_signals).
        divergence_threshold: live ENSEMBLE_DIVERGENCE_STD for pair replay.

    Returns:
        {"models": {model_id: {n, parse_fail_rate, ic, hit_rate}},
         "pairs":  {"A+B": {n_common, divergence_rate, pair_ic}}}
    """
    out: dict = {"models": {}, "pairs": {}}
    rows = rows.copy()
    rows["fwd"] = rows["news_log_id"].map(fwd_by_news)

    for model_id, g in rows.groupby("model_id"):
        ok = g[~g["parse_error"] & g["fwd"].notna() & g["polarity"].notna()]
        score = ok["polarity"] * ok["confidence"]
        ic = float(score.rank().corr(ok["fwd"].rank())) if len(ok) >= 3 else float("nan")
        hit = float((np.sign(score) == np.sign(ok["fwd"])).mean()) if len(ok) else float("nan")
        out["models"][model_id] = {
            "n": int(len(g)),
            "parse_fail_rate": float(g["parse_error"].mean()),
            "ic": ic,
            "hit_rate": hit,
        }

    parsed = rows[~rows["parse_error"] & rows["polarity"].notna()]
    by_news = parsed.pivot_table(index="news_log_id", columns="model_id",
                                 values="polarity", aggfunc="first")
    for a, b in combinations(sorted(out["models"]), 2):
        if a not in by_news.columns or b not in by_news.columns:
            continue
        common = by_news[[a, b]].dropna()
        if common.empty:
            out["pairs"][f"{a}+{b}"] = {"n_common": 0, "divergence_rate": float("nan"),
                                        "pair_ic": float("nan")}
            continue
        stds = common.std(axis=1, ddof=1)  # matches EnsembleAggregator (ddof=1)
        diverged = stds >= divergence_threshold
        agreed = common[~diverged]
        fwd = agreed.index.to_series().map(fwd_by_news)
        pair_score = agreed.mean(axis=1)
        pair_ic = (float(pair_score.rank().corr(fwd.rank()))
                   if fwd.notna().sum() >= 3 else float("nan"))
        out["pairs"][f"{a}+{b}"] = {
            "n_common": int(len(common)),
            "divergence_rate": float(diverged.mean()),
            "pair_ic": pair_ic,
        }
    return out


def render_markdown(report: dict) -> str:
    lines = ["# Stage-2 model comparison", "", "## Models",
             "| model | n | parse_fail | IC | hit rate |", "|---|---|---|---|---|"]
    for m, s in sorted(report["models"].items(), key=lambda kv: -(kv[1]["ic"] or -9)):
        lines.append(f"| {m} | {s['n']} | {s['parse_fail_rate']:.0%} "
                     f"| {s['ic']:.3f} | {s['hit_rate']:.0%} |")
    lines += ["", "## Pairs (replayed at live threshold)",
              "| pair | n | divergence | pair IC |", "|---|---|---|---|"]
    for p, s in sorted(report["pairs"].items(),
                       key=lambda kv: kv[1]["divergence_rate"]):
        lines.append(f"| {p} | {s['n_common']} | {s['divergence_rate']:.0%} "
                     f"| {s['pair_ic']:.3f} |")
    return "\n".join(lines)
```

- [ ] **Step 3: GREEN + commit**

```bash
git add src/performance/model_comparison.py tests/performance/test_model_comparison.py
git commit -m "feat(shadow): shared pairwise comparison module (models + pair replay)"
```

---

### Task 6: Beat auto-report + manual script

**Files:**
- Modify: `src/workers/performance.py` (new task), `src/workers/celery_app.py`
  (schedule entry), `src/store/pg_store.py` (two fetch helpers)
- Create: `scripts/report_model_comparison.py`
- Test: `tests/workers/test_shadow_report.py` (new)

- [ ] **Step 1: Failing test**

```python
"""Auto-report task: no-op before 7 days; report+disarm after."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.workers.performance import run_shadow_comparison_report


def _run(started_at: str | None):
    redis = MagicMock()
    redis.get_shadow_comparison_start.return_value = started_at
    pg = MagicMock()
    pg.fetch_shadow_rows.return_value = []
    pg.fetch_live_response_rows.return_value = []
    with patch("src.workers.performance.RedisStore", return_value=redis), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_shadow_comparison_report()
    return result, redis, tn


def test_noop_when_not_armed():
    result, redis, tn = _run(None)
    assert result["skipped"] is True
    tn.assert_not_called()


def test_noop_before_seven_days():
    ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    result, redis, tn = _run(ts)
    assert result["skipped"] is True
    redis.clear_shadow_comparison_start.assert_not_called()


def test_report_and_disarm_after_seven_days():
    ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    result, redis, tn = _run(ts)
    assert result.get("reported") is True
    tn.assert_called_once()
    redis.clear_shadow_comparison_start.assert_called_once()
```

- [ ] **Step 2: Implement**

(a) `pg_store.py` fetch helpers (mirror existing fetch patterns; constants + methods):

```python
    _FETCH_SHADOW_ROWS = """
        SELECT news_log_id, model_id, polarity, confidence, parse_error
        FROM llm_shadow_responses
        WHERE created_at >= %s
    """
    _FETCH_LIVE_RESPONSE_ROWS = """
        SELECT s.news_log_id, r.model_id, r.polarity, r.confidence, FALSE AS parse_error
        FROM llm_responses r
        JOIN sentiment_signals s ON s.id = r.signal_id
        WHERE r.generated_at >= %s AND s.news_log_id IS NOT NULL
    """
```

plus `fetch_shadow_rows(since)` / `fetch_live_response_rows(since)` returning
`cur.fetchall()`, and reuse the existing forward-return join by fetching
`(news_log_id, forward_return)` from `sentiment_signals WHERE news_log_id IS NOT
NULL AND forward_return IS NOT NULL AND generated_at >= %s` as
`fetch_fwd_by_news(since)`.

(b) `run_shadow_comparison_report` task in `performance.py`:

```python
@app.task(name="src.workers.performance.run_shadow_comparison_report")
def run_shadow_comparison_report() -> dict:
    """Stage-2 auto-report: after >=7 days armed, build the ranked comparison,
    send it via Telegram, and DISARM the shadow toggle (self-bounding spend)."""
    import pandas as pd
    from src.performance.model_comparison import build_comparison, render_markdown

    redis = RedisStore()
    try:
        started_raw = redis.get_shadow_comparison_start()
        if not started_raw:
            return {"skipped": True, "reason": "not_armed"}
        started = datetime.fromisoformat(started_raw)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - started) < timedelta(days=7):
            return {"skipped": True, "reason": "window_open"}

        pg = PostgreSQLStore()
        try:
            cols = ["news_log_id", "model_id", "polarity", "confidence", "parse_error"]
            rows = pd.DataFrame(
                list(pg.fetch_shadow_rows(started)) + list(pg.fetch_live_response_rows(started)),
                columns=cols,
            )
            fwd = dict(pg.fetch_fwd_by_news(started))
        finally:
            pg.close()

        report = build_comparison(rows, fwd, divergence_threshold=config.ENSEMBLE_DIVERGENCE_STD)
        md = render_markdown(report)
        try:
            notifier = TelegramNotifier()
            run_async(notifier.send_alert(md, level="info"))
        except Exception as exc:
            log.warning("shadow report Telegram send failed: %s", exc)
        redis.clear_shadow_comparison_start()
        return {"reported": True, "models": len(report["models"])}
    finally:
        redis.close()
```

(c) Beat entry in `celery_app.py` (next to `loss-feedback-check`):

```python
    "shadow-comparison-report": {
        "task": "src.workers.performance.run_shadow_comparison_report",
        "schedule": crontab(hour=21, minute=40),
    },
```

(d) `scripts/report_model_comparison.py`: thin wrapper — parse `--since ISO`,
call the same fetch helpers + `build_comparison` + print `render_markdown`.

- [ ] **Step 3: GREEN + commit**

Run: `.venv/bin/pytest tests/workers/test_shadow_report.py tests/performance/test_model_comparison.py -q`

```bash
git add src/workers/performance.py src/workers/celery_app.py src/store/pg_store.py scripts/report_model_comparison.py tests/
git commit -m "feat(shadow): 7-day auto-report with self-disarm + manual report script"
```

---

### Task 7: Full suite + report

- [ ] `.venv/bin/pytest -q` → only the 10 known pre-existing failures.
- [ ] Final report: branch, commits, test counts; confirm shadow is NOT armed and
nothing was deployed.

---

## Operator rollout after review (NOT for the implementing agent)

1. Merge; apply migration 037; `docker compose build worker worker-inference beat api && up -d`.
2. Arm: `docker exec alembic-redis-1 redis-cli SET shadow:model_comparison:started_at "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"`.
3. Watch cost: shadow triples per-item LLM calls for 7 days; report + auto-disarm
   arrive via Telegram. Manual cut anytime: `python scripts/report_model_comparison.py --since <ISO>`.
