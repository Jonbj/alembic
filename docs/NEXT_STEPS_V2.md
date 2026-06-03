# Alembic — Next Steps V2 (as of 2026-06-04)

## Current State

| Item | Status |
|------|--------|
| **Tests** | 1766 passing |
| **Critical bugs (#1–#4)** | ✅ Fixed (committed 2026-06-03) |
| **UI bugs (6 items)** | ✅ Fixed (committed 2026-06-03) |
| **Paper trading** | Live on Alpaca — but still ~95% cash (S1 signals below threshold) |
| **GitHub issues** | 19 open — fixed issues not yet closed, 15 legitimately open |
| **Roadmap position** | Phase G (T-601–T-605 done) → blocked on 90-day run start |
| **90-day clock** | **NOT STARTED** — blocked on: always-on host + S1 threshold |

---

## What Happened Since V1 (2026-06-03 sprint)

The 4 CRITICAL bugs are now fixed and committed:
- **Bug 1** (`pg_store.py` pool leak): `finally pg.close()` + context manager everywhere
- **Bug 2** (ensemble weights never read): weights now read from Redis before aggregation
- **Bug 3** (LOO ICIR wrong grouping): per-model grouping restored
- **Bug 4** (duplicate BUY): pending-order check before submission; weight normalization in orchestrator

**Action required**: Close GitHub issues #1–#4 manually (fixes are in `main`, issues remain open).

---

## Tier 0 — Immediate Cleanup (today, 1 hour)

Before anything else, close the resolved issues and re-triage the board.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 0a | **Close GitHub issues #1–#4** | All 4 CRITICAL bugs are fixed. Close these to avoid stale board noise. Add a comment linking to the fix commit. | S |
| 0b | **Verify fixes are running in paper trading** | Check worker logs for absence of pool exhaustion, confirm weights are being read from Redis, confirm no duplicate BUY log entries. Can do via `docker logs` or Telegram daily report output. | S |
| 0c | **Run pending DB migration** | Execute `scripts/migrate_add_news_source.py`. Required for `news_source` column in reports — the column is missing from the live DB. Do this before the next daily report runs. | S |

---

## Tier 1 — Unblock the 90-Day Paper Run (this week, BLOCKING)

The 90-day validation clock cannot start until these items are done.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 1 | **Choose an always-on host** | A laptop that sleeps or a dev machine that reboots breaks the run and invalidates continuity. Options: Hetzner CX21 (~€4/mo, 2 vCPU, 2 GB RAM — sufficient), a home server with UPS, or a cloud VM. Stack needs ~1 GB RAM + persistent Redis + Postgres. This is the single biggest operational blocker. | S |
| 2 | **Diagnose S1 signal distribution** | Run `SELECT score, symbol, generated_at FROM signals ORDER BY generated_at DESC LIMIT 200` on the live DB. Compare score distribution to `ENTRY_THRESHOLD=0.3` in `execution.py:46`. If p95 of scores is below 0.25, the threshold needs tuning, not the model. | S |
| 3 | **Tune ENTRY_THRESHOLD or S1 sizing** | If scores are systematically 0.05–0.20, lower threshold to 0.15 and verify the change against the backtest IC (0.3 threshold was calibrated on synthetic data, not live GDELT replay). Document the new threshold with the backtest Sharpe at that level before changing live config. | S |
| 4 | **Define 90-day start date and commit it** | Once host is live and S1 is generating orders, record the official start date in `docs/paper_trading_log.md` (create if absent). The 90-day clock only starts when all Tier 0 + Tier 1 items are complete. | S |

---

## Tier 2 — S1 Signal Quality (this week)

S1 is 95% cash. Even after threshold tuning, the signal infrastructure needs visibility.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 5 | **Add signal distribution to daily report** | Extend `run_daily_report` (in `src/workers/performance.py`) to include per-strategy signal distribution: mean, p5, p25, p75, p95 of scores from the last 24h. This replaces manual SQL queries and gives the Telegram daily message something useful to report while cash. | S |
| 6 | **Confirm ingestion pipeline is feeding live data** | Verify that all three ingestion workers (GDELT, MarketAux, Alpaca/Benzinga) are logging article counts > 0 every cycle. A silent ingestion failure would keep signals stale without an obvious error. Check via `celery inspect active` or worker logs. | S |
| 7 | **Stagger Celery task start times (issue #14)** | In `celery_app.py`, all `*/15` tasks fire at the same minute. Fix: ingestion at `:00`, sentiment at `:05`, execution at `:12`. Currently execution reads the previous cycle's signal because it fires before sentiment finishes. This is a silent correctness bug during paper trading. | S |

---

## Tier 3 — HIGH Pre-Live Blockers (weeks 1–2, fix before live account)

These 7 issues (#5–#11) are not blocking paper trading validity but MUST be fixed before switching to a live Alpaca account. Work through them in parallel with the 90-day run.

| # | Issue | Description | Complexity |
|---|-------|-------------|------------|
| 8 | **#5 — Kill-switch TTL** | Kill-switch set by drawdown cap has no TTL. System stays halted at next session open even after market recovers. Fix: add a 1-business-day TTL on the Redis key, or an explicit Telegram-confirmed reset command. | S |
| 9 | **#6 — Regime fail-open** | Missing regime key in Redis defaults to bull multiplier (1.0×). On macro stress, if regime detection fails or Redis is unavailable, system over-trades. Fix: default to `NEUTRAL` (0.75×) when key is absent. | S |
| 10 | **#7 — Portfolio concentration cap** | `MAX_CYCLE_NOTIONAL_PCT = 0.20` exists in `execution.py:48` but verify it's enforced on every code path (including the portfolio orchestrator path). One macro tick can still deploy >20% of NAV into a single name if the orchestrator bypasses the execution worker. | S |
| 11 | **#8 — Broker-side bracket orders** | Stop-loss is polled every 15 min. In fast-moving markets, a position can blow past the 2% stop before the next poll. Fix: submit Alpaca bracket orders (OCA group: take-profit + stop-loss) at order submission time. Requires changes to `execution.py` order construction. | M |
| 12 | **#9 — Unauthenticated GET endpoints** | Strategy configs and signal data are readable by anyone with the API URL. Add HTTP Basic Auth (or API key header) to all GET endpoints in `src/api/`. Minimum: protect `/signals`, `/weights`, `/strategy-config`. | S |
| 13 | **#10 — `lpop` irrevocable message loss** | `SentimentWorker` uses `lpop` — items lost permanently on task timeout. Replace with `lrange` + delete-after-processing, or use a Celery result backend with retry. Under high load or transient timeout, current approach silently drops news items. | S |
| 14 | **#11 — ICIR guardrail accepts anti-predictive ensemble** | Guardrail G3 allows weights even when all individual model ICs are negative, as long as ensemble variance is low. Fix: add a floor — if ensemble IC < −0.02 for 3 consecutive weeks, refuse the new weights and revert to previous. | S |

---

## Tier 4 — Observability & Monitoring (ongoing during paper run)

Without visibility, the 90-day paper run produces no useful signal about what's working.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 15 | **Per-strategy PnL attribution** | `portfolio_cycles` records combined portfolio value only. Add a `strategy_pnl` table or Redis key tracking per-strategy notional PnL: total invested, total returned, realised + unrealised per strategy. Needed to know if S1, S2, S4 are individually on track. | M |
| 16 | **Execution funnel metrics in daily report** | Track the full funnel daily: articles ingested → scored → above threshold → orders placed → orders filled. A ratio of 0 at "orders placed" means the signal pipeline is healthy but the threshold is too high. A ratio of 0 at "articles scored" means ingestion is broken. | S |
| 17 | **N-consecutive-failure alerting** | Add a Redis counter per Celery task type. If any task fails 3× in a row within a 1h window, send a CRITICAL Telegram alert (different from the per-failure warning). Prevents silent degradation over weekends or during low-traffic periods. | S |
| 18 | **Paper trading weekly snapshot** | Every Monday morning, send a Telegram message with the 7-day summary: trades placed, fills, slippage, PnL vs SPY (even if 0 for now), and any constraint violations from the orchestrator. This is the weekly go/no-go health check during the 90-day run. | S |
| 19 | **Grafana execution-rate panel** | Add a Grafana panel showing daily: signals received / orders placed / orders filled. Even with 95% cash, this panel should show non-zero "signals received" when the pipeline is healthy. Currently there is no way to distinguish "no signals" from "signals below threshold" at a glance. | S |

---

## Tier 5 — MEDIUM Bugs (fix opportunistically, not blocking)

These are issues #12–#19. Not blocking paper trading, but worth fixing before go-live.

| # | Issue | Description | Complexity |
|---|-------|-------------|------------|
| 20 | **#13 — Silent no-op on bearish signal** | Bearish signal on a held long position produces no action and no log. Add explicit logging: either close the position (if bearish score crosses a threshold) or log "bearish signal received, holding position, score=X". | S |
| 21 | **#17 — Weight renorm pushes outside bounds** | `compute_new_weights` renormalisation can push values outside `[floor, cap]` after constraint enforcement. Fix: clip to `[floor, cap]` after every renorm step. | S |
| 22 | **#16 — Last-write-wins on signal** | Strong conviction signal overwritten by weak follow-up signal within the same 30-min window. Fix: use max-score semantics within a TTL window, or append-and-aggregate rather than overwrite. | S |
| 23 | **#15 — Article dedup insufficient** | Same article processed 3× from different connectors. Enhance URL dedup: strip tracking parameters, canonicalize domain (e.g. `www.` prefix, protocol), use normalized URL as the Redis dedup key. | S |
| 24 | **#12 — Drawdown anchor** | Drawdown cap anchored to overnight close instead of session-open equity. A gap-up open inflates the available budget; a gap-down open triggers premature halt. Change anchor to session-open account value (fetch from Alpaca at 14:00 UTC daily). | S |
| 25 | **#18 — Dedup TTL mismatch** | TTL is 2h in code, documented as 4h. Align to 4h everywhere (code + docs + Redis key TTL). | S |
| 26 | **#19 — UNKNOWN signal key** | `signal:UNKNOWN:sentiment` written when `asset_tags` is empty. Guard: `if not ticker or ticker == "UNKNOWN": return`. | S |

---

## Tier 6 — Phase E: S4 Refactor (weeks 3–4)

Required by the roadmap before Phase F. S4 currently uses a threshold signal (`score > 0.30 → buy`) instead of cross-sectional ranking. This must change before the portfolio combiner can weight it properly.

| # | Task | Description | Complexity |
|---|------|-------------|------------|
| 27 | **T-401 — S4 cross-sectional ranking** | Change S4 from `score > 0.30 → BUY` to `rank top 5 tickers by score → equal weight in 10% bucket`. Output: `(ticker, as_of, signal, weight)`. This makes S4 signal-generating even in a low-sentiment environment (there are always 5 tickers ranked highest). | S |
| 28 | **T-402 — S4 BaseStrategy wrapper** | Wrap S4 signal+sizing in `BaseStrategy` interface. The `PortfolioOrchestrator._extract_target_weights()` already has a code path for S4 via `compute_target_weights()` — this task ensures S4 populates that interface correctly. | S |
| 29 | **T-403 — S4 backtest + gate run** | Backtest S4 on GDELT historical news replay. S4 enters the combined portfolio at 10% regardless of gate result (it's the tactical/news-driven sleeve), but document gate scores for the record. | M |

---

## Tier 7 — Phase F: Portfolio Combiner (July)

The `PortfolioOrchestrator` already exists and implements the weight-then-order contract. Phase F adds proper allocation, risk parity, and cross-strategy constraints on top of it.

| # | Task | Description | Complexity |
|---|------|-------------|------------|
| 30 | **T-501 — Portfolio combiner: fixed allocation** | Aggregate S1+S2+S4 strategy outputs with fixed allocation percentages (S1: 50%, S2: 40%, S4: 10%). The orchestrator already does allocation-weighted merging — this task wires in the registry with the correct allocation percentages and validates the behavior end-to-end. | M |
| 31 | **T-502 — Risk parity overlay** | Replace fixed allocation with risk parity (equal risk contribution across strategies). Compare combined Sharpe with and without risk parity on historical data. | M |
| 32 | **T-503 — Cross-strategy constraint enforcer** | Max single-asset exposure (15%), max sector (30%), max correlation cluster. Log which strategy caused each violation. The `ConstraintEnforcer` in `src/portfolio/constraints.py` has the infrastructure — this task adds the cross-strategy rules. | M |
| 33 | **T-504 — Vol targeting overlay** | Apply vol targeting (10% annualised target) to the combined portfolio after constraints. `PortfolioVolTargeter` exists — wire it into the live execution path. | S |
| 34 | **T-505 — Full multi-strategy backtest** | Backtest S1+S2+S4 combined with Phase F infrastructure. Target: OOS Sharpe ≥ 0.8, max DD ≤ 18%, diversification ratio > 1.3. | M |

---

## Tier 8 — S3 R&D (post-Phase F, no earlier)

S3 failed gates 3 & 5 with OOS Sharpe 0.15. Per roadmap decision (2026-06-01), it is a R&D sleeve. Do not invest time here until Phase F is complete and the combined system is validated.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 35 | **S3 sensitivity analysis** | Test: long-only variant, shorter lookbacks (3m, 6m), smaller universe (top 30 by liquidity), beta-adjusted vs raw momentum. Re-run gate suite. Only if results are promising does S3 enter the portfolio. | M |

---

## Paper Trading: Metrics & Go/No-Go Criteria

### Weekly metrics (track from day 1 of the run)

| Metric | Source | Acceptable Range |
|--------|--------|-----------------|
| Articles ingested/day | Worker logs | > 20 across all connectors |
| Scores generated/day | `signals` table | > 0 for every trading day |
| BUY orders placed/week | Alpaca orders | > 0 once threshold is tuned (Tier 1 item 3) |
| Fill quality (slippage) | Alpaca fills vs signal price | < 15 bps average |
| Strategy weight drift | `weight_update_log` | Within 5% of target allocation |
| Daily PnL vs SPY | `portfolio_cycles` | Not trailing SPY by > 2σ over any 30-day window |
| Kill-switch activations | Redis + Telegram alerts | 0 from bugs; market-driven activations documented |
| Celery task error rate | Worker logs | < 2% per task type sustained |
| Forward-return worker | `sentiment_signals.forward_return` | Non-null for > 90% of signals after T+1 |

### 90-Day Go/No-Go Criteria

**PASS** (all must be true):
- System runs 90 consecutive calendar days without unhandled Python exceptions that abort a cycle
- No pool exhaustion events post-fix (Bug 1 resolved and confirmed in logs)
- Ensemble weights are being read and rebalanced (Bug 2 resolved and visible in weekly weight suggestions)
- No duplicate BUY events observed after Bug 4 fix
- Live Sharpe ≥ −0.3 annualised (we are validating execution, not targeting profit yet)
- All CRITICAL and HIGH issues (#1–#11) resolved before claiming pass

**FAIL** (any one disqualifies the run):
- Pool exhaustion observed post-fix (indicates a deeper leak)
- Kill-switch triggered by a code bug (not market conditions)
- Celery task error rate > 10% sustained for > 3 consecutive trading days
- Duplicate orders observed post-Bug-4-fix
- System offline > 72 consecutive hours (host failure)

---

## Recommended Execution Order

```
Week 1 (now):   Tier 0 (cleanup) + Tier 1 (unblock 90-day run) + Tier 2 (S1 tuning)
                → 90-day paper clock STARTS when host is up and S1 generating BUYs

Week 2:         Tier 3 items 8–10 (kill-switch TTL, regime default, concentration cap)
                + Tier 4 items 17–19 (alerting, weekly snapshot, Grafana panel)

Week 3:         Tier 3 items 11–14 (bracket orders, auth, lpop fix, ICIR guardrail)
                + Tier 5 quick MEDIUM bugs (items 20–26, all S complexity)

Week 4:         Tier 6 — T-401/T-402 (S4 cross-sectional ranking + BaseStrategy wrapper)

Week 5:         Tier 6 — T-403 (S4 backtest + gate run)

Weeks 6–9:      Tier 7 — Phase F (T-501–T-505, portfolio combiner)

Ongoing:        Tier 4 observability improvements as Phase F work proceeds

Post-90d:       Tier 8 — S3 R&D sensitivity analysis (only if motivated by results)
Post-90d:       Phase H — live trading decision (small scale, 5–10k€)
```

**The 90-day paper run clock should not start until Tier 0, Tier 1 (host + S1 tuning), and item 7 (Celery stagger) are all complete.**

---

## Changes from V1 (2026-06-03)

- **Tier 1 (critical bugs)**: Moved to "completed" — all 4 fixed and committed
- **New Tier 0**: Added immediate cleanup (close GitHub issues, verify fixes in prod, run migration)
- **Tier 1 (now)**: Reframed as "unblock 90-day run" — host choice and S1 threshold diagnosis
- **Tier 2**: S1 signal quality + Celery stagger (issue #14) promoted — blocking paper run quality
- **Observability (Tier 4)**: Expanded — execution funnel metrics and weekly snapshot added
- **All tier numbers shifted** due to promotions; Phase E/F/G structure unchanged
