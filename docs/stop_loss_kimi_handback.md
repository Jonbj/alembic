# Stop-Loss Redesign — Kimi Autonomous Run Handback

**Date:** 2026-07-11  
**Branch:** `stop-loss-redesign` (ahead of `main`)  
**Spec:** `docs/superpowers/plans/2026-07-11-stop-loss-redesign.md`  

## 1. What was implemented

| Phase | Scope | Status | Key files |
|---|---|---|---|
| 1 | Migration 034 — freeze-at-entry columns, `stop_decisions`, `stop_shadow_log` | ✅ Applied to live DB; committed earlier | `migrations/034_stop_loss_redesign.sql` |
| 2 | Gap A — write SELL `execution_decisions` row on stop fire | ✅ Committed earlier | `src/workers/portfolio_scheduler.py` |
| 3 | `StopPolicy` deep module + freeze-at-entry + fire log + shadow log | ✅ Fixed review findings and committed | `src/portfolio/stop_policy.py`, `src/store/pg_store.py`, `src/workers/portfolio_scheduler.py`, tests |
| 4 | Vol-scaled protective stop + stop-risk sizing (flag-off) | ✅ Committed | `src/workers/portfolio_scheduler.py`, `config/trading.yaml` |
| 5 | Decouple S1↔S4 ratchet + risk-normalize | 🟡 Infrastructure ready; performance.py wiring pending | `src/portfolio/loss_feedback.py`, `src/store/redis_store.py`, `src/workers/portfolio_scheduler.py` |
| 6 | Historical replay script + gates | ✅ Committed | `scripts/replay_stop_loss.py` |
| 7 | Canary runbook | ✅ This doc (§4) | `docs/stop_loss_kimi_handback.md` |

## 2. Test results

Focused stop-loss suite (local, no live DB):

```text
271 passed, 5 skipped, 34 warnings in 2.48s
```

Store/migration tests skipped because this environment has no reachable test DB. The live DB migration was applied manually with `psycopg2`.

Known unrelated failures in the full worker suite (pre-existing):

- `tests/workers/test_sec_edgar_ingestion.py` × 3
- `tests/workers/test_sentiment_worker.py::TestEnsembleWeightReading` × 2

These do not touch stop-loss code.

## 3. Key design decisions / fixes applied during review

1. **Sigma fallback hierarchy** — completed: `bars_df → last_good → asset_median → tier → default`. `last_good` is injected as a callable; production wiring can attach a Redis/cache lookup.
2. **Bar-count rule** — now uses the spec's `≥ 21` rule (not `max(fast,slow)+2`).
3. **`save_frozen_stop(trade_id, frozen)`** — added to `PostgreSQLStore` with round-trip test.
4. **Single `StopPolicy` instance per cycle** — `_stop_loss_breached_symbols`, `_build_stop_shadow_rows`, and `_submit_portfolio_orders` reuse one policy instead of creating many.
5. **`_num()` helper extracted** — no more duplicated coercion logic.
6. **`d_hard` reuse** — broker disaster stop uses the shared policy instance.
7. **Stop-risk sizing** — caps BUY qty/notional as `NAV * B_strat / (d_init + gap_buffer)`. Default `stop_loss_mode=fixed`, so live behavior is unchanged until an operator flips the flag.

## 4. Canary / enablement runbook

### 4.1 Before touching the live flag

1. Run attribution audit:
   ```bash
   .venv/bin/python scripts/audit_stop_loss_attribution.py
   ```
   Expect: 100% attribution (already verified).

2. Build a daily-close CSV for held names:
   ```bash
   .venv/bin/python scripts/replay_stop_loss.py \
       --start 2026-07-01 --end 2026-07-10 \
       --bars-csv data/daily_close.csv --mode report
   ```
   Gate must be **PASS** before live enablement.

### 4.2 Enable shadow log only

In `config/trading.yaml`:

```yaml
risk:
  stop_loss_mode: fixed          # keep fixed execution
  stop_shadow_enabled: true      # start measurement
```

Deploy. Let it run for at least 3 market days.

### 4.3 Validate shadow divergence

Query:

```sql
SELECT symbol, COUNT(*) AS cycles,
       SUM(CASE WHEN would_breach_fixed AND NOT would_breach_vol_scaled THEN 1 ELSE 0 END) AS avoided,
       SUM(CASE WHEN NOT would_breach_fixed AND would_breach_vol_scaled THEN 1 ELSE 0 END) AS missed
FROM stop_shadow_log
WHERE cycle_ts >= now() - interval '3 days'
GROUP BY symbol;
```

Acceptance: `avoided > missed` for high-vol names (PANW/WDC/DELL) and no large missed exits.

### 4.4 Flip to `vol_scaled` on paper

```yaml
risk:
  stop_loss_mode: vol_scaled
  stop_shadow_enabled: true
```

Run on **paper only** until replay gate re-passes with live fills.

### 4.5 Go-live criteria

- Replay gate PASS on last 20+ closed trades.
- Paper P&L not materially worse than fixed mode over ≥ 1 week.
- No increase in max daily drawdown.
- Operator sign-off in `strategy_lifecycle` PO (memory `project_p2_acceptance_audit.md`).

## 5. Remaining work

- **Phase 5 completion:** wire `src/portfolio/loss_feedback.py` into `src/workers/performance.py::run_loss_feedback_check`. Group closed trades by `stop_strategy`, read/write per-strategy EWMA-R state in Redis (`feedback:state:S*`), and adjust per-strategy `feedback:entry_threshold:S*` / `feedback:regime_scale:S*`. Update `tests/workers/test_loss_feedback.py` accordingly.
- **Aggregate stop-risk budget:** current implementation only enforces per-position budget. Aggregate sleeve budget (75–100 bp) is not yet wired.
- **last_good production lookup:** `StopPolicy` accepts a callable but the scheduler does not yet inject one. A Redis-backed lookup (last 5 sessions' `stop_vol_at_entry` per symbol) is the intended fill.
- **d_hard for fractionable positions:** spec calls for a synthetic per-cycle `d_hard` check in addition to the protective check. Since the protective trigger is strictly tighter for longs, this is redundant for exits, but should still be logged for audit.

## 6. Commits on `stop-loss-redesign`

```text
7cc6a91 feat(stop-loss): Phase 3 — StopPolicy deep module, freeze-at-entry, fire log, shadow log
f9e4f11 feat(stop-loss): Phase 4 — stop-risk sizing behind fixed-mode default
de2e915 feat(stop-loss): Phase 5 scaffolding — per-strategy feedback keys + risk-normalized R helper
4c4440e feat(stop-loss): Phase 6 — replay script + per-strategy feedback unit tests
```

Phases 1 and 2 were already on `main` before this run started.

## 7. How to merge

```bash
git checkout main
git merge stop-loss-redesign
# Resolve only if conflicts; no expected conflicts.
git push origin main
```

After merge, run the live migration if this branch is deployed to a fresh DB:

```bash
DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
    .venv/bin/python scripts/apply_migrations.py
```

The production DB already has migration 034 applied, so this is only needed for new environments.

---

🤖 Generated with [Claude Code](https://claude.com/code)
