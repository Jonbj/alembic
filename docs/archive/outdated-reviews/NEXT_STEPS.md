# Alembic — Next Steps (as of 2026-06-03)

## Current State

- **Phase G complete**: T-601–T-605 done (risk monitor, portfolio scheduler, decay monitor, docs)
- **Paper trading**: Live on Alpaca, but 95% cash — S1 signals too conservative to generate BUYs
- **Tests**: 1732 passing
- **Open GitHub issues**: 19 total — 4 CRITICAL, 7 HIGH (pre-live-blocker), 8 MEDIUM/LOW
- **Roadmap position**: Phase E (S4 refactor) and Phase F (portfolio combiner) not yet done
- **Blocker**: No always-on host chosen — 90-day paper run cannot be counted without continuity

---

## Tier 1 — Fix Critical Bugs (this week, BLOCKING)

The 4 CRITICAL issues from the May-19 architecture review make current paper trading results unreliable.
Fix these before interpreting any metrics.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 1 | **#1 — PostgreSQL pool leak** | `pg_store.py` leaks a handle on every method call — exhausts connection pool in ~20 writes/session. Fix: ensure `conn.close()` in a `finally` block or use a context manager on every acquire. | S |
| 2 | **#2 — Ensemble weights never read** | `EnsembleAggregator` writes weights to Redis but reads hardcoded equal weights. Fix: read the per-model weights from Redis before aggregation. | S |
| 3 | **#3 — LOO ICIR wrong grouping** | `performance.py` groups by aggregate `model_id` instead of per-model, so LOO ICIR and rebalancing never work. Fix: group by individual model identifier. | S |
| 4 | **#4 — Duplicate BUY orders** | `execution.py` places a new BUY on the next tick while the Alpaca fill is still pending. Fix: check for any open/pending order on a symbol before submitting a new one (not just open positions). | S |

**Go/no-go**: Do not draw any conclusions from current paper trading PnL until items 1–4 are fixed.

---

## Tier 2 — Paper Trading Infrastructure (this week)

With bugs fixed, set up the 90-day paper run properly.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 5 | **Choose an always-on host** | A laptop or desktop that sleeps breaks the run. Options: small VPS (Hetzner CX21, ~€4/mo), cloud VM, or a dedicated home server. Alembic stack needs ~1GB RAM. This is the single biggest unresolved operational blocker. | S |
| 6 | **Define paper trading metrics to track** | Commit a file (or extend this doc) with the exact metrics, measurement frequency, and acceptable ranges: execution rate (orders placed / signals fired), fill quality (slippage), strategy allocation drift vs target, drawdown, and Celery task error rate. | S |
| 7 | **Define go/no-go criteria for 90-day pass** | Explicit pass conditions: (a) system runs 90 consecutive days without unhandled crashes, (b) live vs backtest PnL within 1σ of backtest distribution, (c) all Celery tasks < 2% error rate, (d) no kill-switch activations from bugs (only from market conditions). | S |
| 8 | **Run `scripts/migrate_add_news_source.py`** | Pending migration needed for `news_source` column in reports. Required for accurate per-source breakdown. See [[pending-migration]] memory. | S |

---

## Tier 3 — S1 Signal Tuning (this week)

Portfolio is 95% cash because S1 generates very few BUY signals. Either the threshold is too high or signal strength is genuinely low.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 9 | **Diagnose S1 signal distribution** | Run `SELECT score, symbol, generated_at FROM signals ORDER BY generated_at DESC LIMIT 100` to see actual score values. Compare to `ENTRY_THRESHOLD=0.3` in `execution.py:46`. If most scores are 0.1–0.25, the threshold needs tuning. | S |
| 10 | **Lower ENTRY_THRESHOLD or tune S1 lookback** | If scores are systematically below threshold, lower threshold to 0.15–0.20 (consistent with backtest IC). If S1's 12-1 lookback is being applied differently in live vs backtest, realign. Document any change with the backtest Sharpe at the new threshold. | S |
| 11 | **Add signal distribution logging** | Add a daily Celery task or extend the daily report to log the distribution of scores (mean, median, p5, p95) per strategy. This gives ongoing visibility without manual SQL queries. | S |

---

## Tier 4 — HIGH Pre-Live Blockers (next 2 weeks)

Fix before switching to a live Alpaca account. These are issues #5–#11 from the architecture review.

| # | Issue | Description | Complexity |
|---|-------|-------------|------------|
| 12 | **#5 — Kill-switch TTL** | Kill-switch set by drawdown cap has no TTL — system stays halted the next session even after market recovery. Add a 1-business-day TTL or an explicit reset path. | S |
| 13 | **#6 — Regime default fail-open** | Missing regime key defaults to bull multiplier (1.0×). On macro stress, if regime detection fails, system over-trades. Fix: default to NEUTRAL (0.75×) or RISK_OFF (0.5×) if key absent. | S |
| 14 | **#7 — Portfolio concentration cap** | One macro tick can deploy 100% of portfolio into a single name. Add a per-tick notional cap (e.g. `MAX_CYCLE_NOTIONAL_PCT = 0.20` exists in `execution.py:48` — verify it's enforced across all order paths). | S |
| 15 | **#8 — Software stop-loss at 15min** | Stop-loss is polled every 15 min — in a fast-moving market, a position can blow past 2% stop. Implement Alpaca bracket orders (OCA groups) at order submission time. | M |
| 16 | **#9 — Unauthenticated GET endpoints** | Strategy configs/signals readable by anyone with the URL. Either add auth to GET endpoints or serve only aggregate/non-sensitive data publicly. | S |
| 17 | **#10 — lpop irrevocable** | `SentimentWorker` uses `lpop` — items lost on task timeout. Replace with `lrange` + delete-after-processing, or use a proper Celery result backend with retry. | S |
| 18 | **#11 — ICIR guardrail accepts anti-predictive ensemble** | Weight guardrail G3 allows an ensemble where all models have negative IC, as long as variance is low. Add a floor: if ensemble IC < −0.02, refuse the weights and keep previous. | S |

---

## Tier 5 — Phase E: S4 Refactor (T-401/T-402/T-403) (weeks 1–2 of July)

Required by the roadmap before Phase F. S4 currently uses a threshold signal (`score > 0.30 → buy`) instead of cross-sectional ranking. This needs to change before combining with S1/S2.

| # | Task | Description | Complexity |
|---|------|-------------|------------|
| 19 | **T-401 — S4 cross-sectional ranking** | Change S4 from `score > 0.30 → BUY` to `rank top 5 tickers by score → equal weight in 10% bucket`. Output: `(ticker, as_of, signal, weight)`. | S |
| 20 | **T-402 — S4 BaseStrategy wrapper** | Wrap S4 signal+sizing in `BaseStrategy` interface so it can be plugged into the `PortfolioOrchestrator`. | S |
| 21 | **T-403 — S4 backtest + gate run** | Backtest S4 on news replay (GDELT historical). S4 enters portfolio at 10% regardless of gate result (it's a tactical sleeve), but document gate scores. | M |

---

## Tier 6 — Phase F: Portfolio Combiner (T-501–T-505) (July)

The current `PortfolioOrchestrator` runs strategies independently and merges their outputs. Phase F adds proper allocation, risk parity, and constraints across strategies.

| # | Task | Description | Complexity |
|---|------|-------------|------------|
| 22 | **T-501 — Portfolio combiner base** | Aggregate S1+S2+S4 strategy outputs with fixed allocation percentages (S1: 50%, S2: 40%, S4: 10%). Input: list of `StrategyOutput`; output: final target weights. | M |
| 23 | **T-502 — Risk parity overlay** | Replace fixed allocation with risk parity (equal risk contribution). Compare combined Sharpe with and without risk parity on historical data. | M |
| 24 | **T-503 — Cross-strategy constraint enforcer** | Enforce max single-asset exposure (15%), max sector (30%), max correlation cluster. Log which strategy caused each violation. | M |
| 25 | **T-504 — Vol targeting overlay** | Apply vol targeting (10% annualised target) to the combined portfolio after constraints. Verify realised vol matches target in backtest. | S |
| 26 | **T-505 — Full multi-strategy backtest** | Backtest S1+S2+S4 combined with Phase F infrastructure. Target: OOS Sharpe ≥ 0.8, max DD ≤ 18%, diversification ratio > 1.3. | M |

---

## Tier 7 — MEDIUM Bugs (fix opportunistically, not blocking)

These are issues #12–#19. Not blocking paper trading validity, but worth fixing before go-live.

| # | Issue | Description | Complexity |
|---|-------|-------------|------------|
| 27 | **#14 — Celery task collision** | All `*/15` tasks fire at the same minute; execution reads the previous tick's signal. Stagger task schedules: ingestion at :00, sentiment at :05, execution at :12. | S |
| 28 | **#13 — Silent no-op on bearish signal** | Bearish signal on held position produces no action and no log. Either close the position or log explicitly. | S |
| 29 | **#17 — Weight renorm pushes outside bounds** | `compute_new_weights` renormalisation can violate floor/cap after constraint enforcement. Fix: clip to [floor, cap] after renorm. | S |
| 30 | **#16 — Last-write-wins on signal** | Strong signal overwritten by weak follow-up signal. Use max-score semantics or a TTL-windowed max. | S |
| 31 | **#15 — Article dedup** | Same article processed 3× from different connectors. Enhance dedup to normalise URL (strip tracking params, canonicalise domain). | S |
| 32 | **#12 — Drawdown anchor** | Drawdown cap anchored to overnight close instead of session-open equity. Change anchor to session-open account value. | S |
| 33 | **#18 — Dedup TTL mismatch** | TTL is 2h in code, 4h in docs. Align both to the same value. | S |
| 34 | **#19 — UNKNOWN signal key** | `signal:UNKNOWN:sentiment` written when `asset_tags` is empty. Guard with `if not ticker or ticker == "UNKNOWN": return`. | S |

---

## Tier 8 — Observability & Monitoring

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 35 | **Per-strategy PnL tracking** | Today `portfolio_cycles` only records combined portfolio value. Add per-strategy PnL attribution so we can see which strategy contributes and whether S1/S2/S4 are meeting their individual targets. | M |
| 36 | **Paper trading daily report** | Verify `run_daily_report` Celery task generates correct output with real paper trading data (not just synthetic). Confirm Telegram delivery and format. | S |
| 37 | **Execution rate dashboard panel** | Add Grafana panel showing: signals received / orders placed / orders filled per day. Ratio should be > 0 if signals are healthy. Currently it's nearly zero from 95% cash. | S |
| 38 | **Alert on consecutive failed tasks** | Add N-consecutive-failure counter per task type in Redis (TTL 1h). If any task fails 3× in a row, send CRITICAL Telegram alert. | S |

---

## Tier 9 — S3 R&D Tuning (post-Phase F)

S3 (cross-sectional equity momentum) failed gates 3 & 5 with OOS Sharpe 0.15. Per roadmap decision (01/06/2026), it's a R&D sleeve. Do not invest time here until Phase F is complete.

| # | Item | Description | Complexity |
|---|------|-------------|------------|
| 39 | **S3 sensitivity analysis** | Test long-only variant, shorter lookbacks (3m, 6m), smaller universe (top 30 liquids), beta-adjusted vs raw momentum. Re-run gate suite. Only if results are promising does S3 enter portfolio. | M |

---

## Paper Trading: Metrics & Go/No-Go Criteria

### Metrics to track (weekly cadence)

| Metric | Source | Target |
|--------|--------|--------|
| Execution rate | `portfolio_cycles` | > 0 BUY orders/week once Tier 1 fixed |
| Fill quality | Alpaca order fills vs signal price | < 15 bps average slippage |
| Strategy weight drift | `weight_update_log` | Within 5% of target allocation |
| Daily PnL vs benchmark (SPY) | `portfolio_cycles` | Not trailing SPY by > 2σ over 30 days |
| Kill-switch activations | Redis logs | 0 (from bugs), market-driven activations documented |
| Celery task error rate | Worker logs | < 2% per task type |
| Signal→Order latency | Logs | < 1 execution cycle (15 min) |

### 90-Day Go/No-Go Criteria

**Pass** (all must be true):
- System runs 90 consecutive calendar days without unhandled Python exceptions that abort a cycle
- No pool exhaustion events (Tier 1, item 1 fixed and confirmed)
- Ensemble weights are being read and rebalanced (Tier 1, items 2–3 fixed and verified in logs)
- No duplicate BUY events observed (Tier 1, item 4 confirmed)
- Live Sharpe ≥ −0.3 annualised (paper trading; we're not trying to make money yet, we're validating execution)
- All CRITICAL and HIGH issues resolved

**Fail** (any disqualifies the run):
- Pool exhaustion observed post-fix (indicates deeper leak)
- Kill-switch triggered by a bug (not market conditions)
- Celery task error rate > 10% sustained for > 3 days
- Duplicate orders observed post-fix

---

## Recommended Execution Order

```
Week 1:  Tier 1 (4 critical bugs) + Tier 2 (host + metrics definition)
Week 2:  Tier 3 (S1 signal tuning) + Tier 4 items 12-14 (TTL, regime default, concentration cap)
Week 3:  Tier 4 items 15-18 (bracket orders, auth, lpop, ICIR guardrail)
Week 4:  Tier 5 (S4 refactor T-401/T-402)
Week 5:  Tier 5 (T-403 S4 backtest) + Tier 7 quick bugs (stagger tasks, silent no-op, weight clip)
Weeks 6-9: Tier 6 (Phase F portfolio combiner T-501–T-505)
Ongoing: Tier 8 (observability — add panels and alerts as Phase F work proceeds)
Post-90d: Tier 9 (S3 R&D, only if motivated by results)
```

The 90-day paper run clock should not start until Tier 1 bugs are fixed and the host is deployed (items 1–8 above).
