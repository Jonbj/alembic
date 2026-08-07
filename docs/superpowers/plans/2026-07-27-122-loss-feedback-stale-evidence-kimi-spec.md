# #122 — Loss-feedback stale-evidence guard — Kimi Execution Spec

> **For the executing agent (Kimi):** You have NO prior context on this repo. Read this whole document once, then execute the single task exactly as written, on one git branch with one PR. Do NOT improvise beyond this spec. A human reviewer will review the PR before merge — your job is to execute and hand back, not to merge.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — an LLM-based algorithmic **paper-trading** system. This bug is on a money-path risk lever, so precision matters more than speed.

**Goal:** Close GitHub issue #122 — stop the loss-feedback ratchet from re-applying a second identical step-down on the *same* loss episode after the cooldown expires.

**Tech stack:** Python 3, pytest (run via `uv run pytest`), Redis (feedback state), PostgreSQL, Celery. `uv.lock` deps are unchanged — no `uv sync` needed beyond what the runner does.

**Branch:** `fix/122-loss-feedback-stale-evidence-guard`

---

## Session protocol

1. **Test runner:** always `uv run pytest <path> -v` for a targeted run, `uv run pytest -q` for the full suite. Never bare `pytest`.
2. **TDD, strictly:** write the failing test → run it and SEE it fail for the right reason → write the minimal implementation → run it and SEE it pass → run the file's whole module → commit.
3. **One branch + one PR.** Branch name above. PR body must contain `closes #122` and a 2-3 line root-cause + fix summary.
4. **Touch only these files:** `src/workers/performance.py` and `tests/workers/test_loss_feedback.py`. Nothing else. In particular do NOT touch order execution, kill-switch, the sentiment scoring formula, `config/trading.yaml`, or any Redis/PG store method signatures — the fix needs none of them.
5. **No DB migrations, no config changes.**
6. **Never delete/weaken an existing test.** If an existing test breaks, it means the change was wrong — re-read this spec; the change is designed to be inert for trades without an `id` (all existing fixtures), so existing tests must stay green untouched.
7. **Full-suite gate before the PR:** capture the baseline first (`uv run pytest -q 2>&1 | tail -5`) so pre-existing unrelated failures are identical before and after. Known pre-existing failure in this repo: `tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` (issue #112) and a flaky `tests/api/test_strategies_routes.py::test_get_s1_backtest_returns_equity_curve` — neither is yours.
8. **Do not deploy, do not restart containers, do not push to `main`.** PR only.

---

## Root cause (verified in the code)

`run_loss_feedback_check` in `src/workers/performance.py` applies a per-strategy ratchet: on a loss trigger it raises the entry threshold by a step and multiplies the regime scale down by a factor, gated by `if outcome.triggered and cooldown_ok:`. `cooldown_ok` is **purely temporal** (`cooldown_hours: 4`). `outcome` is recomputed from scratch each run by iterating the recent closed *teaching* trades. **There is no check that the evidence differs from the previous trigger.** So when the 4h cooldown expires and no new teaching trade has closed, `outcome` is identical to the last trigger and the system applies a **second** step-down on the *same* loss episode. Observed live: S1 on 2026-07-23 ratcheted `regime_scale` 0.26→0.21→0.20 twice (14:00 and 18:30) on identical evidence (EWMA R −0.55, 11 losses, rolling P&L −$178.68), no new S1 trade closed between them; recurred 07-22 and 07-24.

## Fix (no new store methods, no migration)

Fingerprint the evidence by the **id of the most-recent teaching trade** observed for that strategy, persist it in the feedback state on each ratchet, and skip a re-apply when the id is unchanged since the last ratchet — regardless of cooldown expiry. A genuinely new teaching trade (new evidence) changes the id and correctly allows another ratchet. Trades without an `id` fail open (apply as today), so all existing fixtures/tests are unaffected. Only the down-ratchet (trigger) path is guarded; recovery and decay (which move *toward* baseline) are intentionally left alone.

### Files
- Modify: `src/workers/performance.py` (`run_loss_feedback_check`)
- Test: `tests/workers/test_loss_feedback.py` (extend the `_make_trade` helper; add a new test class)

---

## Steps

- [ ] **Step 1 — Write the failing tests.** First, extend the `_make_trade` helper so a fixture trade can carry an id. In `tests/workers/test_loss_feedback.py`, replace the whole `_make_trade` function (currently at the top, under `# Helpers`) with:

```python
def _make_trade(
    net_pnl: float,
    *,
    signal_id: int | None = None,
    entry_notional: float = 1000.0,
    stop_d_init: float = 0.02,
    exit_reason: str = "stop_loss",
    trade_id: int | None = None,
) -> dict:
    """Return a closed trade fixture.

    signal_id=None  -> strategy S1 (momentum/rebalance)
    signal_id=set   -> strategy S4 (news-driven signal)
    trade_id        -> value for the DB 'id' column (None = unset)
    """
    return {
        "id": trade_id,
        "net_pnl": net_pnl,
        "symbol": "AAPL",
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "signal_id": signal_id,
        "entry_notional": entry_notional,
        "stop_d_init": stop_d_init,
        "exit_reason": exit_reason,
    }
```

Then append this test class to the same file (it reuses the existing `_patched_run` helper, `datetime`/`timedelta`/`timezone` imports, and `pytest`, all already present):

```python
class TestStaleEvidenceGuard:
    """#122: the down-ratchet must not re-apply on the same loss episode after
    the cooldown expires — only when a NEW teaching trade has closed."""

    def _losing_s4_trades(self):
        # Most-recent first; newest teaching trade id = 100.
        return [
            _make_trade(-5, signal_id=123, trade_id=100),
            _make_trade(-10, signal_id=123, trade_id=99),
            _make_trade(-3, signal_id=123, trade_id=98),
        ]

    def _old_ts(self):
        # 5h ago > cooldown_hours (4) -> cooldown_ok is True.
        return (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()

    def test_skips_reapply_on_same_evidence_after_cooldown(self):
        state = {"last_adjustment_ts": self._old_ts(), "last_trigger_evidence_trade_id": 100}
        result, mock_redis = _patched_run(self._losing_s4_trades(), redis_state=state)

        s4 = result["per_strategy"]["S4"]
        assert s4["triggered"] is True          # evidence still triggers
        assert s4["cooldown_ok"] is True         # cooldown expired
        assert s4.get("adjusted") is False       # but NOT re-applied
        assert s4.get("skipped_stale_evidence") is True
        mock_redis.set_feedback_regime_scale.assert_not_called()
        mock_redis.set_feedback_state.assert_not_called()

    def test_reapplies_when_new_teaching_trade_closed(self):
        # Last ratchet was on trade 99; a new teaching trade (100) has since closed.
        state = {"last_adjustment_ts": self._old_ts(), "last_trigger_evidence_trade_id": 99}
        result, mock_redis = _patched_run(self._losing_s4_trades(), redis_state=state)

        s4 = result["per_strategy"]["S4"]
        assert s4["adjusted"] is True
        assert s4.get("skipped_stale_evidence") is not True
        mock_redis.set_feedback_regime_scale.assert_called_once()

    def test_applies_when_prior_state_has_no_evidence_id(self):
        # Backward-compat: a feedback state written before #122 has no evidence
        # id -> the guard must not block the (legitimate) adjustment.
        state = {"last_adjustment_ts": self._old_ts()}
        result, _ = _patched_run(self._losing_s4_trades(), redis_state=state)
        assert result["per_strategy"]["S4"]["adjusted"] is True

    def test_persists_evidence_id_on_apply(self):
        # Fresh (no prior state) -> applies AND records the evidence id for next time.
        result, mock_redis = _patched_run(self._losing_s4_trades())
        assert result["per_strategy"]["S4"]["adjusted"] is True
        written_state = mock_redis.set_feedback_state.call_args.args[0]
        assert written_state["last_trigger_evidence_trade_id"] == 100
```

- [ ] **Step 2 — Run the tests, confirm they fail.**

Run: `uv run pytest tests/workers/test_loss_feedback.py::TestStaleEvidenceGuard -v`
Expected: FAIL — `test_skips_reapply_on_same_evidence_after_cooldown` fails (it still adjusts / `skipped_stale_evidence` missing), and `test_persists_evidence_id_on_apply` fails (`last_trigger_evidence_trade_id` not in the written state).

- [ ] **Step 3 — Track the most-recent teaching trade id.** In `src/workers/performance.py`, inside `run_loss_feedback_check`, find this block:

```python
    fb = LossFeedback(cfg)
    # Record in chronological order (reverse the most-recent-first PG result).
    for t in reversed(trades):
        strategy = strategy_for_trade(t)
        exit_reason = t.get("exit_reason", "")
        if not _is_teaching_trade(exit_reason):
            continue
        budget = risk_budget_at_entry(t)
        if budget <= 0:
            continue
        fb.record_exit(strategy, exit_reason, float(t.get("net_pnl") or 0.0), budget)
```

and replace it with:

```python
    fb = LossFeedback(cfg)
    # #122: track the most-recent teaching trade id per strategy so the next
    # check can tell whether NEW evidence has arrived since the last ratchet.
    latest_teaching_trade_id: dict[str, int] = {}
    # Record in chronological order (reverse the most-recent-first PG result).
    for t in reversed(trades):
        strategy = strategy_for_trade(t)
        exit_reason = t.get("exit_reason", "")
        if not _is_teaching_trade(exit_reason):
            continue
        budget = risk_budget_at_entry(t)
        if budget <= 0:
            continue
        fb.record_exit(strategy, exit_reason, float(t.get("net_pnl") or 0.0), budget)
        _tid = t.get("id")
        if _tid is not None:
            # reversed(trades) is oldest-first, so the last write per strategy
            # is the most recent teaching trade.
            latest_teaching_trade_id[strategy] = int(_tid)
```

- [ ] **Step 4 — Add the stale-evidence guard on the trigger condition.** In the same function, find:

```python
            "decayed": False,
        }

        if outcome.triggered and cooldown_ok:
```

and replace it with:

```python
            "decayed": False,
        }

        # #122: don't re-ratchet on stale evidence. If the cooldown expired but
        # no NEW teaching trade closed since the last adjustment, `outcome` is
        # the same loss episode — a second step-down would compress
        # threshold/scale on the same loss, not a new one. Guard on the id of
        # the most-recent teaching trade observed. Missing id -> fail open.
        evidence_id = latest_teaching_trade_id.get(strategy)
        prev_evidence_id = state.get("last_trigger_evidence_trade_id")
        stale_evidence = (
            evidence_id is not None
            and prev_evidence_id is not None
            and evidence_id == prev_evidence_id
        )
        if outcome.triggered and cooldown_ok and stale_evidence:
            s_result["skipped_stale_evidence"] = True
            log.info(
                "Loss feedback for %s: trigger on same evidence (teaching trade %s) "
                "as last adjustment — skipping re-apply (#122)",
                strategy, evidence_id,
            )

        if outcome.triggered and cooldown_ok and not stale_evidence:
```

- [ ] **Step 5 — Persist the evidence id on apply.** In the same function, inside the trigger block, find:

```python
            redis.set_feedback_state(
                {
                    "last_adjustment_ts": now.isoformat(),
                    "reason": outcome.reason,
```

and replace it with:

```python
            redis.set_feedback_state(
                {
                    "last_adjustment_ts": now.isoformat(),
                    "last_trigger_evidence_trade_id": evidence_id,
                    "reason": outcome.reason,
```

- [ ] **Step 6 — Run the new tests, confirm they pass.**

Run: `uv run pytest tests/workers/test_loss_feedback.py::TestStaleEvidenceGuard -v`
Expected: PASS (all four).

- [ ] **Step 7 — Run the whole test module, confirm no regression.**

Run: `uv run pytest tests/workers/test_loss_feedback.py -v`
Expected: PASS (new class + all pre-existing tests — the `_make_trade` change adds `"id": None` to existing fixtures, which fails the guard open, so existing behavior is unchanged).

- [ ] **Step 8 — Commit.**

```bash
git add src/workers/performance.py tests/workers/test_loss_feedback.py
git commit -m "fix(#122): guard loss-feedback ratchet against stale evidence

The per-strategy ratchet re-applied a second identical step-down after the 4h
cooldown when no new teaching trade had closed (same EWMA/loss/PnL) — observed
S1 regime_scale 0.26->0.21->0.20 twice on the same episode (07-23). Fingerprint
the evidence by the most-recent teaching trade id, persist it in feedback:state,
and skip the re-apply when unchanged since the last ratchet. New teaching trade
= new evidence = allowed. Fails open when a trade has no id.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 9 — Full suite + PR.** `uv run pytest -q` (baseline-identical failures only), then open the PR with `closes #122` and a short root-cause + fix summary.

---

## Hand-back checklist (for the human reviewer)

- Guard keys on the most-recent teaching trade id per strategy; verify the "new teaching trade → re-apply allowed" path is genuinely exercised (`test_reapplies_when_new_teaching_trade_closed`) and the stale path is blocked with no Redis writes (`test_skips_reapply_on_same_evidence_after_cooldown`).
- Confirm recovery/decay branches are untouched (only the down-ratchet is guarded) and that a missing `id` fails open (backward-compat with pre-#122 feedback states).
- Note: the fix does not address the theoretical window-slide edge (a teaching trade dropping out of the 50-trade fetch window without a new one entering) — the reported bug is "no new trade closed", which the id fingerprint covers directly; the window-slide case would at worst delay a legitimate re-ratchet to the next teaching close (conservative, avoids over-ratcheting).
