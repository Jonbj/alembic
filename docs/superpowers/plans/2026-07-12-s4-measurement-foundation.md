# S4 Measurement Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make S4's alpha measurable: populate forward returns for ALL sentiment signals (fallback included — today 70-80% of the stream is excluded by design, coverage 29%) and add 3-day / 5-day horizons alongside the existing 1-day.

**Architecture:** One SQL migration (two new columns), a widened pending-query + bulk-writer in `PostgreSQLStore`, and a multi-horizon computation in the existing `run_forward_return_worker`. No new services, no behavior change to trading — this is measurement plumbing only.

**Tech Stack:** Python 3.11, psycopg2, alpaca-py daily bars, pytest (`.venv/bin/pytest`).

---

## Context (read before Task 1)

Read `CLAUDE.md` first. `sentiment_signals.forward_return` (1-day) is populated
nightly by `run_forward_return_worker` (`src/workers/performance.py:1399`), which
gets its work list from `PostgreSQLStore.fetch_signals_pending_forward_return`
(`src/store/pg_store.py:2079`). That query filters `fallback_used = false`, so the
70-80% of signals that fall back to FinBERT never get a forward return → only 29%
of the last 30 days' signals are measurable, and per-horizon analysis is impossible.

**Verified safety fact (2026-07-12):** every IC/LOO consumer query in
`src/store/pg_store.py` filters `fallback_used = FALSE` explicitly in SQL (three
occurrences), so populating forward returns on fallback rows does NOT change any
existing IC/ICIR/threshold series. Task 5 adds a tripwire test to keep it that way.

Constraints:
- Branch `s4-measurement-2026-07-12` off `main`. No merge to main, no deploy, no
  live-DB changes (the migration FILE is created here; applying it is an operator
  step listed at the end).
- Strict TDD. Full suite at the end: the ONLY acceptable failures are the 10 known
  pre-existing ones (5 `tests/api/test_weight_approval.py`,
  3 `tests/workers/test_sec_edgar_ingestion.py`,
  2 `tests/workers/test_sentiment_worker.py::TestEnsembleWeightReading`).

---

### Task 1: Migration 036 — multi-horizon columns

**Files:**
- Create: `migrations/036_forward_return_horizons.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 036_forward_return_horizons.sql
-- Multi-horizon forward returns for sentiment_signals (S4 measurement foundation).
-- forward_return stays the 1-day horizon (backward compatible); 3d/5d are new.
-- Horizons are TRADING days (T+3, T+5 vs T close), computed by
-- run_forward_return_worker.

ALTER TABLE sentiment_signals
    ADD COLUMN IF NOT EXISTS forward_return_3d DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS forward_return_5d DOUBLE PRECISION;

COMMENT ON COLUMN sentiment_signals.forward_return_3d IS
    'Close-to-close return T -> T+3 trading days (NULL until computable)';
COMMENT ON COLUMN sentiment_signals.forward_return_5d IS
    'Close-to-close return T -> T+5 trading days (NULL until computable)';
```

- [ ] **Step 2: Commit**

```bash
git add migrations/036_forward_return_horizons.sql
git commit -m "feat(measurement): migration 036 — forward_return_3d/5d columns"
```

(No test for a plain DDL file; it gets exercised indirectly when the operator
applies it — see the wrap-up section.)

---

### Task 2: Pending-query includes fallback signals + all horizons

**Files:**
- Modify: `src/store/pg_store.py` (`fetch_signals_pending_forward_return`, line ~2079)
- Create: `tests/store/test_forward_return_pending.py`

- [ ] **Step 1: Refactor the inline SQL into a class constant (no behavior change yet)**

In `src/store/pg_store.py`, the method currently executes an inline query.
Move the SQL into a class-level constant named `_FETCH_PENDING_FWD` (same pattern
as the existing `_FETCH_PER_MODEL_FOR_IC` constant) and have the method execute
`self._FETCH_PENDING_FWD`. Keep the SQL text identical in this step.

- [ ] **Step 2: Write the failing tests**

Create `tests/store/test_forward_return_pending.py`. Copy the `pg_store` fixture
from the top of `tests/store/test_pg_news_llm.py` VERBATIM (it wires the mocked
connection/cursor context manager correctly — do not invent your own wiring).

```python
"""Pending-forward-return query: must cover fallback signals and all horizons."""
from src.store.pg_store import PostgreSQLStore

# pg_store fixture: copy verbatim from tests/store/test_pg_news_llm.py


def test_pending_query_includes_fallback_signals():
    """70-80% of the stream is FinBERT fallback; excluding it caps measurement
    coverage at ~29%. The pending query must NOT filter on fallback_used."""
    assert "fallback_used" not in PostgreSQLStore._FETCH_PENDING_FWD


def test_pending_query_covers_all_horizons():
    """A row stays pending until every horizon that can be computed is computed."""
    sql = PostgreSQLStore._FETCH_PENDING_FWD
    assert "forward_return IS NULL" in sql
    assert "forward_return_3d IS NULL" in sql
    assert "forward_return_5d IS NULL" in sql
```

- [ ] **Step 3: Run to verify RED**

Run: `.venv/bin/pytest tests/store/test_forward_return_pending.py -q`
Expected: 2 FAIL (constant still contains `fallback_used = false` and no 3d/5d columns).
(If Step 1's refactor was skipped, the tests fail with AttributeError — do Step 1.)

- [ ] **Step 4: Update the SQL**

```python
    _FETCH_PENDING_FWD = """
        SELECT id, symbol, generated_at
        FROM sentiment_signals
        WHERE (forward_return IS NULL
               OR forward_return_3d IS NULL
               OR forward_return_5d IS NULL)
          AND generated_at < NOW() - INTERVAL '1 day'
          AND generated_at > NOW() - INTERVAL '1 day' * %s
        ORDER BY symbol, generated_at
    """
```

Update the method docstring: it now returns fallback signals too (they are
tradeable via the no-fresh-ensemble path and needed for shadow-model evaluation),
and a row is pending until all computable horizons are filled.

- [ ] **Step 5: Run to verify GREEN**

Run: `.venv/bin/pytest tests/store/test_forward_return_pending.py tests/test_pg_store.py -q`
Expected: PASS (if a pre-existing test in `tests/test_pg_store.py` asserts the old
fallback filter, update THAT test — its premise is the thing this task changes;
say so in the commit message).

- [ ] **Step 6: Commit**

```bash
git add src/store/pg_store.py tests/store/test_forward_return_pending.py
git commit -m "feat(measurement): pending forward-return query covers fallback signals + 3d/5d horizons"
```

---

### Task 3: Bulk writer for three horizons

**Files:**
- Modify: `src/store/pg_store.py` (`bulk_add_forward_returns`)
- Test: `tests/store/test_forward_return_pending.py` (append)

- [ ] **Step 1: Read the current method**

`grep -n "def bulk_add_forward_returns" -A 25 src/store/pg_store.py` — note its
current tuple shape `(signal_id, fwd_ret)` and transaction pattern (mirror it).

- [ ] **Step 2: Write the failing test** (append to the Task-2 test file)

```python
def test_bulk_add_forward_returns_writes_three_horizons(pg_store):
    """Writer takes (id, fwd_1d, fwd_3d, fwd_5d); None preserves existing values
    via COALESCE so partially-computable rows can be completed later."""
    updates = [(42, 0.01, 0.02, None), (43, None, None, 0.05)]
    pg_store.bulk_add_forward_returns(updates)

    cur = pg_store._conn.cursor.return_value
    assert cur.executemany.call_count == 1
    sql, batch = cur.executemany.call_args[0]
    assert "COALESCE" in sql
    assert "forward_return_3d" in sql and "forward_return_5d" in sql
    batch = list(batch)
    # Param order: (fwd_1d, fwd_3d, fwd_5d, id)
    assert batch[0] == (0.01, 0.02, None, 42)
    assert batch[1] == (None, None, 0.05, 43)
```

- [ ] **Step 3: Run to verify RED**

Run: `.venv/bin/pytest tests/store/test_forward_return_pending.py -q -k bulk`
Expected: FAIL (old 2-tuple shape / missing columns).

- [ ] **Step 4: Implement**

Replace the UPDATE statement inside `bulk_add_forward_returns` with:

```sql
UPDATE sentiment_signals
SET forward_return    = COALESCE(%s, forward_return),
    forward_return_3d = COALESCE(%s, forward_return_3d),
    forward_return_5d = COALESCE(%s, forward_return_5d)
WHERE id = %s
```

and adapt the executemany parameter build to `(f1, f3, f5, sid)` per update tuple
`(sid, f1, f3, f5)`. Update the docstring (tuple shape + COALESCE semantics).
The only caller is `run_forward_return_worker` — updated in Task 4.

- [ ] **Step 5: GREEN + commit**

Run: `.venv/bin/pytest tests/store/test_forward_return_pending.py -q`
Expected: all PASS.

```bash
git add src/store/pg_store.py tests/store/test_forward_return_pending.py
git commit -m "feat(measurement): bulk forward-return writer handles 1d/3d/5d with COALESCE"
```

---

### Task 4: Worker computes 1d/3d/5d

**Files:**
- Modify: `src/workers/performance.py` (`run_forward_return_worker`, lines ~1454-1523)
- Test: `tests/workers/test_forward_return_horizons.py` (new)

- [ ] **Step 1: Read the existing worker tests**

`grep -rn "forward_return" tests/workers/test_performance_worker.py | head` —
if that file already tests this worker, mirror its mocking helpers; the test
below is self-contained either way.

- [ ] **Step 2: Write the failing test**

Create `tests/workers/test_forward_return_horizons.py`:

```python
"""run_forward_return_worker: multi-horizon computation (1d/3d/5d trading days)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from src.workers.performance import run_forward_return_worker


def _bars(dates_closes: list[tuple[str, float]]) -> MagicMock:
    idx = pd.to_datetime([d for d, _ in dates_closes], utc=True)
    df = pd.DataFrame({"close": [c for _, c in dates_closes]}, index=idx)
    resp = MagicMock()
    resp.df = df
    return resp


def test_worker_writes_three_horizons():
    # Signal on Mon 2026-06-01 10:00 UTC; bars Mon..Mon (6 trading days).
    signal_rows = [(7, "AAPL", datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc))]
    bars = _bars([
        ("2026-06-01", 100.0),  # T0
        ("2026-06-02", 101.0),  # T+1
        ("2026-06-03", 102.0),
        ("2026-06-04", 103.0),  # T+3
        ("2026-06-05", 104.0),
        ("2026-06-08", 105.0),  # T+5
    ])

    mock_pg = MagicMock()
    mock_pg.fetch_signals_pending_forward_return.return_value = signal_rows
    mock_pg.bulk_add_forward_returns.return_value = 1

    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value = bars

    with patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg), \
         patch("psycopg2.connect", return_value=MagicMock()), \
         patch("alpaca.data.historical.StockHistoricalDataClient", return_value=mock_client):
        stats = run_forward_return_worker()

    assert stats["updated"] == 1
    (updates,) = mock_pg.bulk_add_forward_returns.call_args[0]
    sid, f1, f3, f5 = updates[0]
    assert sid == 7
    assert abs(f1 - 0.01) < 1e-9          # 101/100 - 1
    assert abs(f3 - 0.03) < 1e-9          # 103/100 - 1
    assert abs(f5 - 0.05) < 1e-9          # 105/100 - 1


def test_worker_partial_horizons_when_future_bars_missing():
    # Only T0..T+2 available: 1d computable, 3d/5d stay None (row remains pending).
    signal_rows = [(9, "MSFT", datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc))]
    bars = _bars([("2026-06-01", 200.0), ("2026-06-02", 202.0), ("2026-06-03", 204.0)])

    mock_pg = MagicMock()
    mock_pg.fetch_signals_pending_forward_return.return_value = signal_rows
    mock_pg.bulk_add_forward_returns.return_value = 1
    mock_client = MagicMock()
    mock_client.get_stock_bars.return_value = bars

    with patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg), \
         patch("psycopg2.connect", return_value=MagicMock()), \
         patch("alpaca.data.historical.StockHistoricalDataClient", return_value=mock_client):
        run_forward_return_worker()

    (updates,) = mock_pg.bulk_add_forward_returns.call_args[0]
    sid, f1, f3, f5 = updates[0]
    assert abs(f1 - 0.01) < 1e-9
    assert f3 is None and f5 is None
```

Note: `run_forward_return_worker` imports `StockHistoricalDataClient` INSIDE the
function body, so the patch target is the alpaca module path (as written above),
not `src.workers.performance.StockHistoricalDataClient`.

- [ ] **Step 3: Run to verify RED**

Run: `.venv/bin/pytest tests/workers/test_forward_return_horizons.py -q`
Expected: FAIL — updates tuples still have the 2-element shape `(sid, fwd)`.

- [ ] **Step 4: Implement the multi-horizon loop**

In `run_forward_return_worker`:

(a) Widen the bars window (5 trading days ≈ up to 9 calendar days):

```python
                start = min(dates) - timedelta(days=2)
                end = max(dates) + timedelta(days=9)
```

(b) Replace the per-signal computation block

```python
                        t0, t1 = t_dates[0], t_dates[1]
                        close_t0 = close_by_date[t0]
                        close_t1 = close_by_date[t1]

                        if close_t0 == 0:
                            stats["skipped_no_data"] += 1
                            continue

                        fwd_ret = (close_t1 - close_t0) / close_t0
                        updates.append((sid, fwd_ret))
```

with:

```python
                        close_t0 = close_by_date[t_dates[0]]
                        if close_t0 == 0:
                            stats["skipped_no_data"] += 1
                            continue

                        # Horizons in TRADING days from T0; None when the future
                        # bar is not yet available (row stays pending for that
                        # horizon; COALESCE in the writer preserves prior values).
                        fwd: dict[int, float | None] = {}
                        for n in (1, 3, 5):
                            if len(t_dates) > n:
                                fwd[n] = (close_by_date[t_dates[n]] - close_t0) / close_t0
                            else:
                                fwd[n] = None

                        if all(v is None for v in fwd.values()):
                            stats["skipped_no_data"] += 1
                            continue

                        updates.append((sid, fwd[1], fwd[3], fwd[5]))
```

(c) The earlier guard `if len(t_dates) < 2:` must become `if not t_dates:` (a
signal with only T0 available still can't compute anything — the `all None`
check above handles it — but zero T dates would crash `t_dates[0]`).

(d) Update the worker docstring: three horizons, trading days, fallback signals
now included (query change in Task 2), partial rows re-processed until complete.

- [ ] **Step 5: GREEN + regression**

Run: `.venv/bin/pytest tests/workers/test_forward_return_horizons.py tests/workers/test_performance_worker.py -q`
Expected: PASS. If `test_performance_worker.py` has forward-return tests asserting
the 2-tuple shape, update them to the 4-tuple shape (that is this task's change).

- [ ] **Step 6: Commit**

```bash
git add src/workers/performance.py tests/workers/test_forward_return_horizons.py tests/workers/test_performance_worker.py
git commit -m "feat(measurement): forward-return worker computes 1d/3d/5d trading-day horizons"
```

---

### Task 5: Tripwire — IC consumers keep excluding fallback

**Files:**
- Test: `tests/store/test_forward_return_pending.py` (append)

- [ ] **Step 1: Write the test (passes today; guards Task 2's safety premise)**

```python
def test_ic_queries_still_exclude_fallback_signals():
    """Populating forward_return on fallback rows is safe ONLY because every
    IC/LOO consumer filters fallback_used = FALSE in SQL. If someone removes
    one of those filters, FinBERT fallback rows would silently pollute the
    ensemble IC series. Three consumers exist as of 2026-07-12."""
    from pathlib import Path
    src = Path("src/store/pg_store.py").read_text()
    assert src.upper().count("FALLBACK_USED = FALSE") >= 3
```

- [ ] **Step 2: Run (expected PASS immediately — this one is a tripwire, not TDD)**

Run: `.venv/bin/pytest tests/store/test_forward_return_pending.py -q`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/store/test_forward_return_pending.py
git commit -m "test(measurement): tripwire — IC queries must keep excluding fallback signals"
```

---

### Task 6: Full suite + report

- [ ] **Step 1:** `.venv/bin/pytest -q` → only the 10 known pre-existing failures.

- [ ] **Step 2:** Final report: branch + commits, test counts, and confirm NO
deploy/merge/live-DB action was taken.

---

## Operator steps after review (NOT for the implementing agent)

1. Merge branch → `docker exec -i alembic-postgres-1 psql -U trading -d trading < migrations/036_forward_return_horizons.sql`
2. `docker compose build worker beat && docker compose up -d worker beat`
3. Backfill: `docker exec alembic-worker-1 celery -A src.workers.celery_app call src.workers.performance.run_forward_return_worker` (repeat next day for late horizons)
4. Acceptance: coverage ≥ 85% —
   `SELECT round(100.0*count(forward_return)/count(*),0) FROM sentiment_signals WHERE generated_at BETWEEN now()-interval '30 days' AND now()-interval '2 days';`
5. Follow-up (separate work): per-horizon IC in the daily performance report.
