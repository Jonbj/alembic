# S4 entry-gate floor + TTL heartbeat — Execution Spec

> **For the executing agent:** You have NO prior context on this repo. Read this whole document once, then execute exactly as written, on one git branch with one PR. Do NOT improvise beyond this spec. A human reviewer reviews the PR before merge — your job is to execute and hand back, not to merge or deploy.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — an LLM-based algorithmic **paper-trading** system. This is a money-path risk lever that is currently **disarmed in production**, so precision matters more than speed.

**Goal:** Re-arm the S4 entry-threshold gate and make it impossible for it to silently disarm itself again.

**Tech stack:** Python 3, pytest (via `uv run pytest`), Redis (feedback state), PostgreSQL, Celery. No new deps, no migration, no config change.

**Branch:** `fix/s4-entry-gate-floor-and-ttl`

**Issue:** `<TO BE FILLED — open the issue first, label `bug`+`critical`+`paper-monitoring`, `Part of #21`, put `closes #N` in the PR body>`

---

## Session protocol

1. **Test runner:** always `uv run pytest <path> -v` for targeted runs, `uv run pytest -q` for the full suite. Never bare `pytest`.
2. **TDD, strictly:** write the failing test → run it and SEE it fail for the right reason → minimal implementation → run it and SEE it pass → run the whole test module → commit.
3. **One branch + one PR.** PR body must contain `closes #N` and a 3-line root-cause + fix summary.
4. **Touch only these four files:**
   - `src/workers/portfolio_scheduler.py`
   - `src/workers/performance.py`
   - `tests/workers/test_gate_drop_logging.py`
   - `tests/workers/test_loss_feedback.py`

   Nothing else. In particular do NOT touch `config/trading.yaml`, `src/store/redis_store.py`, `src/workers/execution.py`, order submission, the kill-switch, or the sentiment scoring formula. The fix needs none of them.
5. **No DB migrations, no config changes, no new Redis keys.**
6. **Never delete or weaken an existing test.** Exactly one existing test is expected to need an *addition* (Step 2); no existing assertion may be removed.
7. **Full-suite gate before the PR:** capture the baseline first (`uv run pytest -q 2>&1 | tail -5`) so pre-existing unrelated failures are provably identical before and after. Known pre-existing failures in this repo, neither of which is yours: `tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` (issue #112) and the flaky `tests/api/test_strategies_routes.py::test_get_s1_backtest_returns_equity_curve` (issue #152, depends on gitignored `reports/`).
8. **Do not deploy, do not restart containers, do not push to `main`, do not touch live Redis.** PR only. The operator handles the live stopgap and the deploy.

---

## Root cause (verified in code and against live Redis/Postgres on 2026-07-30)

The S4 entry gate has been **fully disarmed since 2026-07-28 17:22:05 UTC** and does not self-heal. Three defects compose:

**(1) The Redis key expires and nothing ever rewrites it.**
`feedback:entry_threshold:S4` is written with a 96h TTL (`feedback_ttl_hours: 96`, `performance.py:1731`) and is written **only** by a ratchet, recovery, or decay event (`performance.py:1805`, `:1940`). When both levers are at rest, `_step_threshold_down` early-returns `None` at `performance.py:1795-1796` (`if current_threshold <= baseline and current_scale >= 1.0: return None`) and the trigger branch does not fire — so **no branch writes anything**, the key ages out after 96h, and never comes back. Verified live: `feedback:entry_threshold:S4` → absent, `ttl=-2`.

**(2) The fallback lands on the ranker prefilter instead of the gate floor.**
On a missing key (or an unreachable Redis), `_get_feedback_threshold` returns `S4Config().min_score` = **0.10** (`portfolio_scheduler.py:1300-1301`). `min_score` is explicitly documented in `src/strategies/s4/config.py:14` as a **ranker prefilter, not the order threshold**. The intended floor, `_ENTRY_THRESHOLD_BASELINE` = 0.30 (`portfolio_scheduler.py:2947`, added by commit `b2c0f54` with the docstring *"Used as the ORDER-GATE FLOOR when feedback:entry_threshold is absent (expired) — so the gate never drops to the min_score prefilter (0.10)"*), is **dead code**: its only reference in the whole repo is `tests/workers/test_gate_drop_logging.py:139`, which asserts its value. The test suite is green while the protection does nothing.

**(3) The guard then disables the gate entirely.**
The gate is wrapped in `if _fb_threshold is not None and _fb_threshold > s4_config.min_score:` (`portfolio_scheduler.py:3231`). With the fallback at 0.10, `0.10 > 0.10` is `False`, so the **whole block is skipped** — no filtering *and* no `SKIP_THRESHOLD` rows. The Decision Log's explanation of no-trade cycles disappears at the same moment the gate does.

**Why nobody noticed:** `performance.py:1898` resolves the same value with a *different* fallback (`redis.get_feedback_entry_threshold(...) or cfg["threshold_baseline"]` → 0.30) and logs `S4 current_threshold: 0.3` on every run. **Telemetry reports 0.30 while enforcement is 0.10/off.**

**Blast radius (both call sites of `_get_feedback_threshold`, both with `strategy="S4"`):**
- `portfolio_scheduler.py:3200` — the entry gate itself. Signals with `0.10 ≤ |score| < 0.30` now reach the ranker and can be bought.
- `portfolio_scheduler.py:2209` — `_fresh_signal_protected_symbols`, which vetoes SELLs of positions still backed by a fresh signal above the threshold. A lower threshold **protects more positions from being sold**.

**Evidence:** `SKIP_THRESHOLD` rows in `execution_decisions` per day: 211 (07-24), 146 (07-27), 250 (07-28, last row 17:22:05), **0** (07-29). On 07-29 NVDA was bought for $1,272.95 on a sentiment score of exactly **+0.100** (model reasoning: *"modest and not directly tied to NVIDIA's core revenue"*) and sold 2h15m later at ~breakeven. The 0.30 floor would have rejected it. Cross-referenced in `docs/ALPHA_MISS_REPORT_2026-07-29.md` §1/§7 and `docs/FORENSIC_DAILY_REPORT_2026-07-29.md`.

**Note — a related latent bug that is deliberately OUT OF SCOPE.** `performance.py:1898-1899` uses `or` rather than an `is None` check, so a stored value of `0.0` reads back as the baseline. This actually bites S1, whose threshold is deliberately forced to `0.0` (`performance.py:1938-1939`, *"S1 has no discrete entry-threshold gate"*). It is currently masked (S1's threshold is never enforced anywhere) and fixing it would change `threshold_before` in the audit state, breaking existing assertions. **Do not fix it in this PR.** Step 3 below is written specifically to avoid depending on those two lines.

---

## Fix

Three surgical changes, one per defect. All three are needed — any two leave a hole.

| # | Defect | Change | File |
|---|---|---|---|
| A | fallback lands on the prefilter | `_get_feedback_threshold` falls back to `_ENTRY_THRESHOLD_BASELINE` (0.30), not `S4Config().min_score` | `portfolio_scheduler.py` |
| B | guard disables the gate at equality | `>` → `>=` in the gate condition | `portfolio_scheduler.py` |
| C | key expires at rest and never returns | heartbeat: re-write both feedback keys with a fresh TTL at the top of every run, for every sleeve, preserving stored values | `performance.py` |

Design notes the reviewer will check:
- **A is a fallback-path change only.** Do **not** wrap the returned Redis value in `max(value, baseline)`. A present value must be honoured verbatim: S1 legitimately stores `0.0`, and a blanket floor would silently arm a gate for a strategy that is designed not to have one, should a future caller pass `strategy="S1"`.
- **C must not reuse `current_threshold`/`current_scale` from `performance.py:1898-1899`** — see the out-of-scope note above. Read the stored values fresh, and preserve them exactly.
- **C must not live inside the per-strategy loop.** That loop is `for strategy in sorted(fb._history.keys())` (`performance.py:1881`) and `fb._history` is populated only from closed trades whose `exit_reason` is in `TEACHING_EXIT_REASONS = {"stop_loss", "portfolio_sell"}` (`src/portfolio/loss_feedback.py:16`) **and** whose `risk_budget_at_entry` is > 0, within the last 50 closed trades. A sleeve that goes quiet — or whose recent exits are all `sentiment_reversal`, which is *not* a teaching reason — silently drops out of the loop and would get no heartbeat, reproducing this exact bug. (Measured on the live DB today: the last 50 closed trades are S4 `portfolio_sell` ×25, S1 `portfolio_sell` ×12, S1 `sentiment_reversal` ×13 — so S4 is in the loop *right now*, but only by trade flow, not by construction.) There is also an early `return {"skipped": True, "reason": "no_closed_trades"}` at `performance.py:1857-1859` that bypasses the loop entirely. The heartbeat must run **before both**, over a fixed sleeve set.
- `_ENTRY_THRESHOLD_BASELINE` is defined at line 2947, *after* `_get_feedback_threshold` at line 1277. Referencing it from inside the function body is fine (resolved at call time, after the module is loaded). **Do not move either definition.**

---

## Steps

### Step 1 — Fix A: the fallback floor (TDD)

**1a. Write the failing tests.** Append to `tests/workers/test_gate_drop_logging.py`:

```python
def test_get_feedback_threshold_falls_back_to_baseline_when_key_absent():
    """The order-gate floor on a missing/expired Redis key is the config baseline
    (0.30), NOT the ranker prefilter min_score (0.10). Regression for the gate
    being silently disarmed from 2026-07-28 17:22 UTC onward."""
    with patch("redis.Redis") as mock_cls:
        inst = MagicMock()
        inst.get.return_value = None  # both per-strategy and legacy keys absent
        mock_cls.from_url.return_value = inst
        got = portfolio_scheduler._get_feedback_threshold("redis://x", strategy="S4")
    assert got == portfolio_scheduler._ENTRY_THRESHOLD_BASELINE == 0.30


def test_get_feedback_threshold_falls_back_to_baseline_when_redis_unreachable():
    """A Redis outage must degrade to the strict floor, never to an open gate."""
    with patch("redis.Redis") as mock_cls:
        mock_cls.from_url.side_effect = ConnectionError("down")
        got = portfolio_scheduler._get_feedback_threshold("redis://x", strategy="S4")
    assert got == 0.30


def test_get_feedback_threshold_honours_a_present_value_verbatim():
    """A stored value is returned as-is — including values below the baseline, so a
    strategy that deliberately stores 0.0 (S1: no entry gate) is not silently armed."""
    for stored, expected in (("0.45", 0.45), ("0.0", 0.0)):
        with patch("redis.Redis") as mock_cls:
            inst = MagicMock()
            inst.get.return_value = stored
            mock_cls.from_url.return_value = inst
            assert portfolio_scheduler._get_feedback_threshold("redis://x", strategy="S4") == expected
```

Run: `uv run pytest tests/workers/test_gate_drop_logging.py -v`. The first two MUST fail with `0.1 != 0.3`. If they pass, stop — you are not testing what you think.

**1b. Implement.** In `src/workers/portfolio_scheduler.py`, in `_get_feedback_threshold`, replace the two closing lines:

```python
    from src.strategies.s4.config import S4Config as _S4Cfg
    return _S4Cfg().min_score
```

with:

```python
    return _ENTRY_THRESHOLD_BASELINE
```

and update the two places that name the old fallback:
- the docstring line `and then to S4Config.min_score when Redis is unreachable.` → `and then to the config gate floor (_ENTRY_THRESHOLD_BASELINE) when Redis is unreachable.`
- the `log.warning` message `"...— using S4 min_score"` → `"...— using gate floor %.2f"`, adding `_ENTRY_THRESHOLD_BASELINE` as the trailing format arg.

Add a comment above the return recording *why*, in one line: the fallback used to be `min_score` (0.10), a ranker prefilter, which combined with the `>` guard below disarmed the gate entirely for 1.5 trading days (2026-07-28/29).

Re-run the module. All tests green, including the pre-existing `test_entry_threshold_baseline_is_the_gate_floor`. Commit.

### Step 2 — Fix B: the equality guard (TDD)

**2a. Write the failing test.** Append to the same test file:

```python
def test_gate_block_runs_when_threshold_equals_min_score():
    """Guard regression: the gate must engage at threshold == min_score, not be
    skipped. `>` meant a 0.10 fallback compared 0.10 > 0.10 == False and the whole
    filter+logging block was bypassed."""
    from src.strategies.s4.config import S4Config
    min_score = S4Config().min_score
    assert portfolio_scheduler._gate_is_active(min_score, min_score) is True
    assert portfolio_scheduler._gate_is_active(0.30, min_score) is True
    assert portfolio_scheduler._gate_is_active(None, min_score) is False
    assert portfolio_scheduler._gate_is_active(0.05, min_score) is False
```

**2b. Implement.** The condition currently lives inline at `portfolio_scheduler.py:3231`:

```python
            if _fb_threshold is not None and _fb_threshold > s4_config.min_score:
```

Extract it into a module-level helper placed immediately above `_record_gate_drops` (i.e. just after the `_ENTRY_THRESHOLD_BASELINE` assignment), so it is unit-testable without standing up a whole cycle:

```python
def _gate_is_active(threshold: float | None, min_score: float) -> bool:
    """True when the S4 feedback gate should filter this cycle.

    `>=` not `>`: at equality the gate is a no-op filter but still writes
    SKIP_THRESHOLD rows, which is exactly the visibility we want. The old `>`
    turned a 0.10 fallback into a fully bypassed block — no filter AND no log.
    """
    return threshold is not None and threshold >= min_score
```

and change line 3231 to `if _gate_is_active(_fb_threshold, s4_config.min_score):`. Leave the body of the block untouched.

Run the module, then `uv run pytest tests/workers/ -q`. Commit.

### Step 3 — Fix C: the TTL heartbeat (TDD)

**3a. Write the failing test.** Append a new class to `tests/workers/test_loss_feedback.py`, following the file's existing `_patched_run` / mock-redis conventions (read the top of that file first and match them — do not invent a new harness):

```python
class TestFeedbackKeyHeartbeat:
    """The feedback keys carry a 96h TTL but are only written by a ratchet/recovery/
    decay event. At rest no branch writes, so the keys age out and the gate falls back
    forever (live: gate disarmed 2026-07-28 17:22 UTC, never self-healed). Every run
    must refresh the TTL for every sleeve, preserving the stored values."""

    def test_at_rest_run_refreshes_ttl_without_changing_values(self):
        # threshold at baseline, scale at 1.0 -> nothing adjusts, but TTL must refresh
        ...
        thr_calls = {c.kwargs["strategy"]: c for c in mock_redis.set_feedback_entry_threshold.call_args_list}
        assert set(thr_calls) >= {"S1", "S4"}
        assert thr_calls["S4"].kwargs["ttl"] == 96 * 3600
        # value preserved, NOT recomputed
        assert thr_calls["S4"].args[0] == pytest.approx(0.30)

    def test_heartbeat_restores_the_key_when_it_has_already_expired(self):
        # get_feedback_entry_threshold -> None (expired): heartbeat writes the baseline
        ...

    def test_heartbeat_preserves_a_stored_zero(self):
        # S1 stores 0.0 deliberately (no entry gate); the heartbeat must not
        # promote it to the baseline
        ...

    def test_heartbeat_covers_a_sleeve_with_no_recent_teaching_trades(self):
        """THE REGRESSION THAT MATTERS. Feed only S1 teaching trades (so
        fb._history == {"S1"}) and assert S4's keys are STILL refreshed. A heartbeat
        placed inside the per-strategy loop passes every other test in this class and
        fails this one — which is precisely how the gate expired in production."""
        ...

    def test_heartbeat_runs_even_when_there_are_no_closed_trades(self):
        # pg.fetch_trades -> [] : the task early-returns "no_closed_trades", but the
        # keys must still have been refreshed before that return
        ...

    def test_heartbeat_is_fail_safe(self):
        # a Redis error in the heartbeat must not break the loss-feedback run
        ...
```

Fill in the bodies using the existing helpers. Run them and see them fail for the right reason (no `set_feedback_entry_threshold` call at all on an at-rest run).

**3b. Implement.** Two edits in `src/workers/performance.py`.

First, a module-level constant and a helper. Put the constant next to the other module constants near the top (around `_MIN_SAMPLES`, line ~80) and the helper immediately above `run_loss_feedback_check`:

```python
# Sleeves that own feedback keys. Hardcoded rather than derived from fb._history:
# that dict only contains sleeves with a recent *teaching* trade, so a quiet sleeve
# would silently stop getting its TTL refreshed — the exact failure this guards.
_FEEDBACK_STRATEGIES = ("S1", "S4")


def _refresh_feedback_ttl(redis, cfg: dict) -> None:
    """Re-arm the TTL on every sleeve's feedback keys, preserving stored values.

    The keys carry feedback_ttl_hours (96h) but are written ONLY by a ratchet,
    recovery, or decay event. When a sleeve is at rest no branch writes, so the keys
    age out and never come back — live, this left the S4 entry gate disarmed from
    2026-07-28 17:22 UTC with no self-heal. Values are read fresh and written back
    verbatim (an absent key is restored to the baseline / scale 1.0); an absent value
    is NOT the same as 0.0, which S1 stores deliberately. Fail-safe: a Redis error
    here must not break the loss-feedback run.
    """
    ttl_seconds = int(cfg["feedback_ttl_hours"] * 3600)
    for strategy in _FEEDBACK_STRATEGIES:
        try:
            stored_thr = redis.get_feedback_entry_threshold(strategy=strategy)
            stored_scale = redis.get_feedback_regime_scale(strategy=strategy)
            redis.set_feedback_entry_threshold(
                cfg["threshold_baseline"] if stored_thr is None else stored_thr,
                ttl=ttl_seconds, strategy=strategy,
            )
            redis.set_feedback_regime_scale(
                1.0 if stored_scale is None else stored_scale,
                ttl=ttl_seconds, strategy=strategy,
            )
        except Exception as exc:
            log.warning("Feedback TTL heartbeat failed for %s: %s", strategy, exc)
```

Second, call it at the top of `run_loss_feedback_check`, immediately after `redis = RedisStore()` (currently line 1848) and **before** `pg = PostgreSQLStore()` — i.e. before the `if not trades: ... return` early-return at 1857-1859 and before the per-strategy loop:

```python
    redis = RedisStore()
    _refresh_feedback_ttl(redis, cfg)
    pg = PostgreSQLStore()
```

That is the whole change. Do **not** add a guard on `adjusted/recovered/decayed`: a later branch writing the same keys again with a fresh TTL is harmless (one extra Redis write per run), and an unconditional heartbeat is far easier to reason about than one whose correctness depends on which branch fired. Note that the heartbeat writes the *stored* value back, so the `current_threshold = redis.get_feedback_entry_threshold(...)` read later in the loop is unchanged — this edit must be behaviour-neutral apart from the TTL.

Run the module, then the full suite. Commit.

### Step 4 — Hand back

- `uv run pytest -q 2>&1 | tail -5` and diff against the baseline you captured in protocol §7. Only the two known pre-existing failures may remain.
- Open the PR with `closes #N`, a 3-line root cause, and the before/after `SKIP_THRESHOLD` table from the Root cause section.
- In the PR body, state explicitly: **"Not deployed. The live gate is still disarmed until the operator restarts `worker` and `beat`."**

---

## Out of scope — file as follow-ups, do not implement here

1. **Detection.** This bug ran 1.5 trading days undetected because its only symptom was an *absence* of rows. A monitor should alert when zero `SKIP_THRESHOLD` rows are written during market hours while S4 signals exist. Needs a new check in the risk-monitor task — separate PR.
2. **The `or` vs `is None` fallback at `performance.py:1898-1899`** — see the note in Root cause.
3. **Single-source resolver for gate vs telemetry.** After Fix A both paths fall back to 0.30 and can no longer disagree, so the divergence is closed by construction; a shared resolver module would be a cross-module refactor with no behavioural gain. Note it, do not build it.
4. **`_FEEDBACK_STRATEGIES` should come from `StrategyRegistry.get_active_strategies()`**, not a hardcoded tuple, so a future S2/S3 sleeve is covered automatically. Not done here: it would add a DB-backed registry call to a task that currently needs none, widening the failure surface of a fix whose whole point is reliability. The constant carries a comment saying so.

---

## Operator checklist (NOT for the executing agent)

**Stopgap, before the fix ships** — re-arms the live gate immediately, expires again in 96h:

```bash
docker exec alembic-redis-1 redis-cli SETEX feedback:entry_threshold:S4 345600 0.30
docker exec alembic-redis-1 redis-cli GET feedback:entry_threshold:S4   # -> "0.30"
```

**After merge** — rebuild and restart `worker` + `beat` (the gate lives in the Celery worker image; `config/trading.yaml` is baked, not mounted).

**Acceptance, on the first market session after deploy:**

```sql
SELECT date_trunc('day', tick_time)::date AS d, decision, count(*)
FROM execution_decisions
WHERE tick_time >= now() - interval '3 days'
GROUP BY 1, 2 ORDER BY 1, 3 DESC;
```

`SKIP_THRESHOLD` must be back in the 100–250/day band, and no BUY may carry `signal_score < 0.30`. Then re-check after 5+ days (> the 96h TTL) that `TTL feedback:entry_threshold:S4` is still positive — that is the proof the heartbeat works, and it is the only part of this fix that a single session cannot verify.
