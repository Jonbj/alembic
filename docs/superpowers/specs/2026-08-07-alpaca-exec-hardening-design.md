# Alpaca Execution-Layer Hardening — Design Spec

**Date:** 2026-08-07
**Status:** Approved (operator) — pending spec review
**Origin:** alpaca-py doc audit (2026-08-07; memory `project_alpaca_doc_audit_2026_08_07`)
**Scope:** 4 active correctness/tooling fixes + 1 frozen tuning item (trailing stop)
**Freeze #171 (03/08→28/09):** §1/§2/§3/§4 are correctness/tooling (`freeze-ok`); §5 is tuning (frozen).
**Roadmap:** Part of #21 (Wayfinder roadmap map).

## Background

The alpaca-py audit found Alembic's API usage correct and coherent, with no deprecated
calls in use. It identified 4 correctness gaps + opportunities in the execution layer (the
submit-order / account-read path). The one-liners (TIF `day`→`gtc` on bracket/OTO legs, 3
twin-bug #192 `adjustment=`, pin `alpaca-py>=0.43.5`) were already fixed + deployed (commit
`71315b9`, worker rebuilt + verified baked). This spec covers the remaining design-issues
that are NOT one-liners.

The 5 points are independent subsystems. The operator chose an **umbrella spec** (one design
doc, per-point sections) → per-point implementation plans → per-point Wayfinder issues for
agents.

### Dependencies
- **§3 (client_order_id) must precede §4 (retry of `submit_order`):** retrying `submit_order`
  without broker-side idempotency risks double orders.
- §1, §2, §3 are independent of each other.
- §5 (trailing stop) is frozen — design only, backlog issue.

### Execution order for agents
§3 → §4 (dependency); §1, §2 independent (can go first). §2 auto-close stays default-off
until the operator flips it.

---

## §1 — `buying_power` / `multiplier` pre-flight gate

**Classification:** correctness / risk-control → `freeze-ok`. **Live-behavior change**
(alters order sizing) → operator sign-off.

**Problem:** `portfolio_scheduler.py:2071` reads `account.buying_power` but only logs it
(`:2072`); sizing uses `portfolio_value` (equity), not `buying_power`. `account.multiplier`
(Reg-T 1/2/4×) is never read. When `notional > buying_power` (margin exhausted /
`multiplier=1` cash / overnight 2× reached) → Alpaca rejects 422 silently mid-cycle (0 or
partial orders, no pre-alarm).

**Decision (operator):** cap notional to `buying_power` + alert. **Safe rollout:**
shadow-log first for one trading session, then flip to cap-live.

**Mechanism:**
- Pre-flight at the sizing step, after `get_account()` (`:2053`), using the already-fetched
  `buying_power` (`:2071`).
- **Phase 1 — shadow (default):** if `notional > buying_power` → write to Decision Log
  (`would_cap`, delta) + Telegram alert; **do not cap** (no behavior change). One trading
  session of shadow evidence.
- **Phase 2 — cap-live (flag flipped by operator):** cap `notional` to `buying_power`,
  re-round (whole-share for non-fractionable, fractional for fractionable), Decision Log
  (`capped`), Telegram alert.
- `account.multiplier` is **logged for observability only** — Alpaca's `buying_power` already
  embeds the Reg-T multiplier, so no separate multiplier math is needed (this refines the
  audit's over-cautious note).

**Guard edge:** if `buying_power` is None/0 (API hiccup) → **skip + alert** (never submit a
0-qty order, never cap to 0).

**Files:** `src/workers/portfolio_scheduler.py` (sizing step + 4 submit sites
`:2949/:3836/:3869/:3946`); `src/workers/execution.py:735` (legacy path — same gate, lower
priority).

**Config:** `buying_power_gate_mode` ∈ {`shadow`, `cap`, `off`} (default `shadow`).

**Testing:** unit test cap+rounding (fractionable vs whole-share), None/0 skip, shadow-vs-cap
branches; mock `get_account`.

**Success criteria:** zero silent 422 rejects; every cap event in Decision Log + Telegram;
shadow cycle produces evidence before the flip.

---

## §2 — Scheduled position reconciliation + alert + auto-close `genuinely_orphan`

**Classification:** correctness / tooling → `freeze-ok`. **Money-path DB write** (auto-close)
→ backup + operator sign-off + flag default-off.

**Problem:** `scripts/reconcile_open_trades_vs_broker.py` exists (read-only, idempotent, pure
`classify_positions` + `summarize`; categories `genuinely_orphan` / `over_held` /
`untracked_position` / `partially_wound_down_coheld` / `fully_held`) but is referenced **only
in tests**, never scheduled. Beat has `reconcile-fills-*` (fill↔order, populates
exit_price/pnl) but no position↔DB-trade-ledger reconcile. = class #121 "accounting DB
divergente".

**Decision (operator):** alert + auto-close `genuinely_orphan`. **Safe version:** auto-close
flag default-off + dry-run + backup; only `genuinely_orphan` (broker holds 0 → no broker SELL
→ DB force-close only); `over_held`/`untracked_position` alert-only.

**Mechanism:**
- **Beat task** `reconcile-positions-eod` → `crontab(hour=21, minute=35, day_of_week=1-5)`
  (after `reconcile-fills-evening` 21:30). New Celery task `run_reconcile_positions` in
  `src/workers/performance.py` (mirrors `run_reconcile_fills_intraday`), wrapping
  `classify_positions`.
- **Alert (always on):** Telegram on the three anomaly categories — `genuinely_orphan`,
  `over_held`, `untracked_position` (the other two, `fully_held` /
  `partially_wound_down_coheld`, are normal states → no alert).
- **Auto-close (flag-gated, default OFF):** only `genuinely_orphan`. Broker holds 0 → **no
  broker order**; it is a **DB force-close** of the trade row via `record_trade_exit`
  (`exit_reason="orphan_reconcile"`, `exit_price` recovered from the fills/orders ledger or
  last-known). `over_held` / `untracked_position` → **alerted only** (auto-closing those =
  broker orders = out of scope, riskier).
- **Safety gate:** `reconcile_autoclose_enabled=false` (default) +
  `reconcile_autoclose_dry_run=true` (default) → first runs only log what would be closed. Flip
  to live only after the operator reviews a dry-run. **Backup the `trades` table before the
  first live auto-close.**

**Files:** `src/workers/celery_app.py` (beat entry), `src/workers/performance.py` (new task),
`scripts/reconcile_open_trades_vs_broker.py` (add a `force_close_orphans()` callable; keep
`classify_positions` pure), `src/store/pg_store.py` (`record_trade_exit` reuse).

**Error handling:** classify is read-only until the autoclose flag; a classify error → alert,
never crashes the worker. Auto-close failure → per-trade error logged, continues, never bulk.

**Testing:** extend `tests/test_reconcile_open_trades.py` with `force_close_orphans` (mock DB,
assert `exit_reason` + idempotency + dry-run-no-write).

**Success criteria:** no stuck trade passes one EOD without a Telegram alert; auto-close (when
enabled) force-closes orphans idempotently; backup recoverable.

---

## §3 — `client_order_id` idempotency

**Classification:** correctness.

**Problem:** `client_order_id` is never used (grep 0). No broker-side dedup safety-net against
double-submit (the 34s race, loop-reversal, retry-resubmit).

**Decision (operator):** universal deterministic ID on all submit sites.

**Mechanism:**
- Universal deterministic ID `ambc-{purpose}-{symbol}-{cycle_ts}` (e.g.
  `ambc-buy-AAPL-20260807T1452`) on **all** live submit sites:
  `portfolio_scheduler.py:2949/3836/3869/3946` + `src/portfolio/fractional_stop_orders.py:192`
  + `execution.py:735`.
- `signal_id` folded where a signal exists (`ambc-buy-{symbol}-{signal_id}`).
- Fits Alpaca `client_order_id` constraints (≤1024 chars, `[a-zA-Z0-9-_]`).
- Helper `src/portfolio/order_id.py`: `build_client_order_id(purpose, symbol, cycle_ts,
  signal_id=None)`.

**NON-NEGOTIABLE verification spike (before relying on dedup):** confirm Alpaca's dedup
semantics — resubmit-window, and whether a duplicate `client_order_id` returns the original
order or a 409 — against docs + a sandbox resubmit. The audit flagged this as "widely
documented but not in the fetched reference." **Implementation gates on the spike confirming
dedup.**

**Error handling:** ID construction is pure string → no failure path; if Alpaca rejects the ID
format → fall back to no `client_order_id` (current behavior) + alert.

**Files:** 6 submit sites + `src/portfolio/order_id.py` (new).

**Testing:** unit test ID format/charset/uniqueness; integration test the dedup spike
(sandbox, 2× same ID → assert single fill).

**Success criteria:** a resubmitted order with the same `client_order_id` produces one fill,
not two; verified against Alpaca.

---

## §4 — Centralized retry/backoff  *(blocked_by §3)*

**Classification:** tooling → `freeze-ok`.

**Problem:** no central retry util. SDK retry = 3×3s fixed, only 429/504, no `Retry-After`,
no 502/503. A sustained 429 loses the whole cycle (15 min to next beat). Reusable patterns
exist at `src/connectors/gdelt_base.py` (exp backoff + 429) and `src/llm/client.py`.

**Decision (operator):** new `src/util/retry.py`; submit-fail+alert, reads-degrade.

**Mechanism:**
- New `src/util/retry.py`: `retry_transient(fn, *, max_attempts=4, base=2.0, cap=30.0)` —
  exponential backoff + jitter + respect `Retry-After` header, retry on 429/500-504 (modeled
  on `gdelt_base`).
- Wrap:
  - **reads** (`get_account`, `get_all_positions`, `get_stock_bars`, `get_snapshot`) → final
    failure: **degrade gracefully** (return None/stale + log), don't kill the cycle.
  - **`submit_order`** → retry **only after §3** (idempotency makes retry safe); final
    failure: **fail the cycle + Telegram alert** (never silent, never double-submit).

**Error handling:** `APIError` parsed for status + `Retry-After`; non-retryable (400/403/422)
→ fail immediately (no retry).

**Files:** `src/util/retry.py` (new); wrap call sites in `portfolio_scheduler.py`,
`performance.py`, `risk_monitor_task.py`, `execution.py`, `mobile_monitoring/builder.py`,
`src/portfolio/fractional_stop_orders.py`.

**Testing:** unit test backoff schedule + `Retry-After` respect (mock `APIError`); test
read-degrade vs submit-fail branches.

**Success criteria:** simulated 429-storm → cycle completes via retries or fails loudly (not
silent); no double-submit (gated on §3).

**Dependency:** the §4 Wayfinder issue is `blocked_by` the §3 issue.

---

## §5 — Trailing stop  *(TUNING → frozen by #171 until 28/09 — design only)*

**Classification:** tuning → **frozen** (NOT `freeze-ok`). Backlog issue, scheduled post-28/09,
flip = operator decision.

**Design (no implementation now):** replace the standalone `StopOrderRequest` at
`src/portfolio/fractional_stop_orders.py:185` with
`TrailingStopOrderRequest(trail_percent=…)`. Single-order (not a bracket leg) → 1:1 swap.
Addresses the audit finding that the static 2% stop = 0.26–0.53σ (stop-out on noise). See
stop-loss evidence + Kimi redesign handoff.

**Wayfinder issue:** `wayfinder:backlog`, `tier3`, scheduled post-freeze.

---

## Cross-cutting

### Agent handoff
- **Plans (writing-plans, next step):** one per point →
  `docs/superpowers/plans/2026-08-07-{buying-power,reconcile,coid,retry}.md`.
- **Wayfinder issues:** one per point, all `Part of #21`.
  - §1 buying_power gate — `tier2`, `ready-for-agent`, `freeze-ok`.
  - §2 position reconcile — `tier2`, `ready-for-agent`, `freeze-ok`.
  - §3 client_order_id — `tier2`, `ready-for-agent`, `freeze-ok`.
  - §4 retry/backoff — `tier3`, `ready-for-agent`, `freeze-ok`, **`blocked_by` §3 issue**.
  - §5 trailing stop — `wayfinder:backlog`, `tier3`, frozen (post-28/09).
- **Execution order:** §3 → §4; §1, §2 independent. §2 auto-close default-off.

### Verification spikes (gating)
- §3: Alpaca `client_order_id` dedup semantics (window, 409 vs original-order) — **must
  confirm before relying on dedup.**

### Out of scope
- Auto-close of `over_held` / `untracked_position` (would need broker orders — riskier,
  separate governance).
- §5 trailing-stop implementation (frozen).
- Retry of non-Alpaca calls (LLM, GDELT already have their own backoff).
- TIF / twin-bug / pin fixes (already deployed, commit `71315b9`).

### Risk summary
| § | Risk | Mitigation |
|---|------|-----------|
| §1 | live sizing change | shadow-log 1 cycle → flip; `freeze-ok` |
| §2 | money-path DB write | flag default-off + dry-run + backup; alert-only until flip |
| §3 | dedup unverified | verification spike gates reliance; fallback to no-coid |
| §4 | double-submit on retry | `blocked_by` §3; submit retry only after idempotency |
| §5 | tuning | frozen; backlog issue only |