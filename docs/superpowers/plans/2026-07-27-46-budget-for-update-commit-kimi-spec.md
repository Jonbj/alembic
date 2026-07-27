# #46 (B31) — LLMBudgetTracker check_budget: FOR UPDATE without commit — Kimi Execution Spec

> **For the executing agent (Kimi):** You have NO prior context on this repo. Read this whole document once, then execute the single task exactly as written, on ONE git branch with ONE PR that closes #46. Do NOT improvise beyond this spec. A human reviewer reviews the PR before merge.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — an LLM-based paper-trading system. This is a pre-live (Tier 4) DB-correctness fix in the LLM budget tracker.

**Goal:** Close GitHub issue #46 (B31). `LLMBudgetTracker.check_budget` runs a `SELECT ... FOR UPDATE` (a row-level lock) but never commits or rolls back, so the transaction stays open — an idle-in-transaction connection holding a lock. This is the same failure class as the previously-fixed B7/B32 pool leak. Add a commit after the read (rollback on error) to release the lock.

**Tech stack:** Python 3, `psycopg2` (RealDictCursor), asyncio, pytest (run via `uv run pytest`). `uv.lock` unchanged.

**Branch:** `fix/46-budget-for-update-commit`

---

## Session protocol

1. **Test runner:** always `uv run pytest <path> -v`; `uv run pytest -q` for the full suite. Never bare `pytest`.
2. **TDD, strictly:** write the failing test → run it and SEE it fail → minimal implementation → run it and SEE it pass → run the file's module → commit.
3. **One branch + one PR** (name above). PR body must contain `closes #46` and a 2-3 line root-cause + fix summary.
4. **Touch only these files:** `src/llm/budget.py`, `tests/test_budget_tracker.py`. Nothing else. Do NOT touch `record_spending` (it already commits at the end).
5. **No DB migrations, no config changes.**
6. **Never delete/weaken an existing test.** The existing `check_budget` tests use a `MagicMock` connection; adding `conn.commit()` is a no-op mock call there, so they stay green untouched.
7. **Full-suite gate before the PR:** capture the baseline first (`uv run pytest -q 2>&1 | tail -5`). Known pre-existing failures (NOT yours): `tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` (issue #112) and a flaky `tests/api/test_strategies_routes.py::test_get_s1_backtest_returns_equity_curve`.
8. **Do not deploy, do not restart containers, do not push to `main`.** PR only.

---

## Root cause (verified)

`src/llm/budget.py`, `check_budget` (async) runs its query in a nested sync `_check()` executed on a thread:

```python
        def _check() -> Literal["ok", "exhausted"]:
            today = date.today()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT total_spent_usd, budget_exhausted
                    FROM llm_budget
                    WHERE date = %s
                    FOR UPDATE  -- Row-level lock for thread safety
                    """,
                    (today,),
                )
                row = cur.fetchone()

                if row is None:
                    # No row yet = no spending = ok
                    return "ok"

                if row["budget_exhausted"]:
                    return "exhausted"

                if row["total_spent_usd"] >= self._daily_limit:
                    return "exhausted"

                return "ok"
```

`FOR UPDATE` takes a row lock that is held until the transaction ends. `_check` returns without `conn.commit()` or `conn.rollback()`, so the transaction stays open (idle-in-transaction), holding the lock and pinning the pooled connection. `record_spending` in the same class ends with `conn.commit()` (correct); `check_budget` must do the same to release the lock after its read.

## Files
- Modify: `src/llm/budget.py` (`check_budget`'s inner `_check`)
- Test: `tests/test_budget_tracker.py`

## Steps

- [ ] **Step 1 — Write the failing tests.** Append to `tests/test_budget_tracker.py` (it already imports `MagicMock`/`patch`, `asyncio`, `pytest`, `LLMBudgetTracker`, and `LLMBudgetExhaustedError`; if any import is missing, add it):

```python
class TestCheckBudgetReleasesLock:
    """#46: check_budget must end its FOR UPDATE transaction (commit/rollback)
    so the row lock is released — no idle-in-transaction leak."""

    def test_commits_after_read_ok_path(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # no row -> "ok"
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)
        result = asyncio.run(tracker.check_budget())

        assert result == "ok"
        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()

    def test_commits_even_on_exhausted_path(self):
        # The lock must be released BEFORE the exhausted error is raised.
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"total_spent_usd": 40.0, "budget_exhausted": True}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        tracker = LLMBudgetTracker(conn=mock_conn)
        with pytest.raises(LLMBudgetExhaustedError):
            asyncio.run(tracker.check_budget())

        mock_conn.commit.assert_called_once()

    def test_rolls_back_on_db_error(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = RuntimeError("db error")
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        # Do not let the mock cursor's __exit__ swallow the exception.
        mock_conn.cursor.return_value.__exit__.return_value = False

        tracker = LLMBudgetTracker(conn=mock_conn)
        with pytest.raises(RuntimeError):
            asyncio.run(tracker.check_budget())

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
```

- [ ] **Step 2 — Run them, confirm they fail.**

Run: `uv run pytest tests/test_budget_tracker.py::TestCheckBudgetReleasesLock -v`
Expected: FAIL — `commit.assert_called_once()` fails (current code never commits), and `rollback.assert_called_once()` fails (no rollback path).

- [ ] **Step 3 — Fix.** In `src/llm/budget.py`, replace the entire inner `_check` function (the block shown in Root cause above) with:

```python
        def _check() -> Literal["ok", "exhausted"]:
            today = date.today()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(
                        """
                        SELECT total_spent_usd, budget_exhausted
                        FROM llm_budget
                        WHERE date = %s
                        FOR UPDATE  -- Row-level lock for thread safety
                        """,
                        (today,),
                    )
                    row = cur.fetchone()

                if row is None:
                    result: Literal["ok", "exhausted"] = "ok"  # no row = no spending
                elif row["budget_exhausted"]:
                    result = "exhausted"
                elif row["total_spent_usd"] >= self._daily_limit:
                    result = "exhausted"
                else:
                    result = "ok"

                # B31/#46: release the FOR UPDATE row lock. Without a commit the
                # transaction stays open (idle-in-transaction), holding the lock
                # and pinning the pooled connection — the B7/B32 pool-leak class.
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
```

- [ ] **Step 4 — Run the new tests, confirm they pass.**

Run: `uv run pytest tests/test_budget_tracker.py::TestCheckBudgetReleasesLock -v`
Expected: PASS.

- [ ] **Step 5 — Run the whole module, confirm no regression.**

Run: `uv run pytest tests/test_budget_tracker.py -v`
Expected: PASS (new class + all pre-existing `check_budget`/`record_spending` tests — they use a MagicMock conn, so the added `conn.commit()` is an inert mock call).

- [ ] **Step 6 — Commit.**

```bash
git add src/llm/budget.py tests/test_budget_tracker.py
git commit -m "fix(#46): commit after check_budget FOR UPDATE to release the row lock

check_budget ran SELECT ... FOR UPDATE but never committed/rolled back, leaving
an idle-in-transaction connection holding the lock (the B7/B32 pool-leak class).
Compute the result, commit to release the lock, and roll back on error.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7 — Full suite + PR.** `uv run pytest -q` (baseline-identical failures only), then open the PR with `closes #46`.

---

## Hand-back checklist (for the human reviewer)

- Verify the commit happens on BOTH the "ok" and "exhausted" paths (lock released before the exhausted error is raised), and rollback-then-reraise on any DB error.
- Confirm `record_spending` was not touched and the existing budget tests still pass with the inert mock `commit()`.
- Note: this only adds transaction termination; it does not change whether `FOR UPDATE` is the right locking choice for a read-only check (out of scope for this ticket).
