# Forensic Daily Report — 2026-07-21

**Analyst:** Trading Systems Forensic Analyst / Senior Backend Engineer / Quant Ops Reviewer (autonomous session)
**Generated:** 2026-07-22
**Scope:** Operational day 2026-07-21, timezone **UTC** (confirmed `timezone="UTC"`, `enable_utc=True` in `src/workers/celery_app.py:50-51`)
**Mode:** Read-only. No files modified except this report. No orders, no commits, no live pipeline re-runs.
**Trading mode:** **PAPER** (confirmed in running container: `ALPACA_BASE_URL=https://paper-api.alpaca.markets`; `config/trading.yaml` `execution.engine=portfolio`).

---

## 1. Executive Summary

The pipeline ran end-to-end on 2026-07-21 with no structural gaps: 180 news items ingested (14:01–19:45 UTC), 180 sentiment signals produced, 24 portfolio cycles executed at a clean 15-min cadence (14:07–19:52 UTC), 5 new positions opened and 8 positions closed. Both LLM models were **UP all day** (gpt-oss 178 responses, glm-5.2 177) — no Ollama downtime. However, **glm-5.2 eligibility collapsed to 23%** (40/177, avg confidence 0.284), forcing a **48% FinBERT fallback rate** (87/180 signals) and degrading the "ensemble" to a single model in a further 33% of cases. Only **19% of signals were true two-model ensembles**. Two of the day's five real entries were driven by defective signal provenance: **HOOD** was bought on a FinBERT-fallback +0.436 read of a generic "big stocks moving higher" roundup (closed same day, −$15.35), and **WDC** was bought at 16:37 while its `signal_id` FK points to a +0.363 FinBERT-fallback signal but the trade's recorded `signal_score` is −0.385 (a *different*, ensemble bearish signal) — the confirmed **signal_id↔score desync (#59)**, on the very name the system had reversal-sold two hours earlier on that same −0.385. WDC and MU were both re-bought **exactly 2h** after a sentiment-reversal SELL (cooldown boundary whipsaw). A partial trim of WDC at 18:22 stamped `exit_order_id` but left the trade open (`exit_time` NULL) — broker qty (1.400) now diverges from the trade record (2.981) with no realized PnL booked on the sold shares. Realized PnL for the day: **−$91.85** (8 exits). No circuit breaker or risk constraint fired; long-only was structurally respected; idempotency correctly suppressed 14 repeat BUY decisions. Operational hygiene concerns: 07-21 worker/backend logs were wiped by a 07-22 container restart, and a test harness toggled the kill-switch, mutated prod config and inserted/deleted 3 `TEST_STOP_*` rows in the prod `trades` table. **The system is currently HALTED** (kill-switch active, reason "test", no TTL, set 07-22 07:40).

## 2. Verdict

**ANOMALIE SIGNIFICATIVE** — *(anomalie significative, non "processo non affidabile")*.

The pipeline is operationally sound, auditable via the database, and did not misfire structurally. But real (paper) trades were executed on defective signal provenance: two of five entries (HOOD, WDC) rest on FinBERT-fallback signals the system was days away from prohibiting (PR #114, merged 07-22), the WDC trade exhibits the confirmed `signal_id↔score` desync, and a partial trim left an unreconciled position. These are functional defects that materially shaped the day's book, not cosmetic issues. Several are already remediated by PR #114 the following day — **live verification pending** on the first post-fix cycle.

---

## 3. Timeline (2026-07-21, UTC)

| Time (UTC) | Component | Event | Outcome |
|---|---|---|---|
| 14:01:30 | News ingest | First fetch of the day (gdelt + benzinga) | 180 items by 19:45 |
| 14:07:00 | Portfolio cycle #534 | S1+S4 run; IWM BUY (S1 momentum, wt 1.3%) | Trade #371 opened @294.03 |
| 14:22:00 | Portfolio cycle #535 | 5 SELLs: AMZN, SONY, IBM, TXN (S4 expired), GE (s1_weight_drop) | Trades #369,#370,#366,#365,#359 closed |
| 14:37:00 | Portfolio cycle #536 | WDC SELL sentiment_reversal (−0.385 < −0.35) | Trade #295 closed, net −1.74 |
| 15:22:00 | Portfolio cycle #539 | MU SELL sentiment_reversal (−0.375 < −0.35) | Trade #313 closed, net −4.20 |
| 15:37:00 | Portfolio cycle #540 | HOOD BUY (S4 +0.436 **FinBERT fallback**, wt 2.0%) | Trade #372 opened @107.77 |
| 16:37:01 | Portfolio cycle #544 | WDC BUY (labelled "S4+S1 −0.385", FK→+0.363 fallback, wt 2.7%) | Trade #373 opened @549.24 |
| 17:22:01 | Portfolio cycle #547 | MU BUY (S1 momentum, wt 0.6%) — re-entry 2h after reversal SELL | Trade #374 opened @975.958 |
| 18:22:00 | Portfolio cycle #551 | BA BUY (S4 +0.297 ensemble, wt 2.0%); WDC partial trim SELL | Trade #375 opened; #373 trimmed (unreconciled) |
| 18:52:00 | Portfolio cycle #553 | HOOD SELL ("S4 expired" citing stale 07-20 signal) | Trade #372 closed, net −15.35 |
| 19:52:00 | Portfolio cycle #557 | Last market-hours cycle | Clean cadence, no gaps |
| 22:30:00 | Risk report | EOD risk snapshot: NAV 109,846.90, exposure 26.9% | herfindahl=1.0 (degenerate), no alerts |
| 23:41:47 | Ops (after-hours) | KILLSWITCH_ACTIVATE "manual operator halt via API" + config mutations | Test/QA activity on prod |
| 23:42:07 | Ops (after-hours) | 3× `TEST_STOP_*` trades inserted (rows since deleted, ID gap 376–378) | Test-in-prod |

## 4. News Ingest

**Totals:** 180 items, 0 marked discarded, 0 future timestamps. Fetch window 14:01:30–19:45:43 UTC; published window 12:49–17:50 UTC (all within/near market hours, no stale-by-days items).

### By source
| Source | Items | Tickers | Discarded | Extraction method |
|---|---|---|---|---|
| alpaca_benzinga | 92 | 42 | 0 | source_metadata (provider-tagged) |
| gdelt_gkg | 88 | 21 | 0 | org_lookup (entity resolution) |

### By ticker (top)
| Ticker | Items | gdelt | benzinga | Note |
|---|---|---|---|---|
| MU | 22 | 16 | 6 | High-volume; **noise-tagged** (see [DAY-005]) |
| MS | 20 | 20 | 0 | All gdelt; "MS" is over-broad entity match |
| MSFT | 9 | 5 | 4 | |
| TSM | 8 | 8 | 0 | |
| BRKB | 7 | 7 | 0 | |
| GS | 7 | 6 | 1 | |
| NVDA | 7 | 0 | 7 | |

**Top news by signal impact (07-21):**
- **BA** — "Boeing Extends Winning Streak with Multiple Global Airline Deals" (16:23) → +0.297 ensemble → BA BUY (**well-grounded**).
- **MU** — "Micron Stock Surges Nearly 8% as Insatiable AI Memory Demand Fuels Rebound" (14:45) → +0.500 ensemble (**well-grounded**).
- **WDC** — "Micron, SanDisk Just Broke the Momentum Trade: SPMO Faces Its Worst Month" (12:58) → −0.385 ensemble (**correct bearish read, then ignored by the BUY**).
- **HOOD** — "Hasbro, Utz Brands, Park Aerospace And Other Big Stocks Moving Higher" (14:37) → +0.436 FinBERT fallback → HOOD BUY (**weak/generic basis**).

**Problems:** ticker mis-extraction on the gdelt `org_lookup` path (see [DAY-005]); no per-source dedup discards logged (dedup is enforced at insert via `uq_news_log_url_ticker` / `content_hash`, so cross-provider duplicates are silently rejected, not counted). **Confidence: High** on volumes; **Medium** on extraction-quality assessment (spot-checked, not exhaustively labelled).

## 5. LLM Model Performance

Source: `llm_responses` + `sentiment_signals` for 07-21. **Both models were UP all day — this is a model-quality/eligibility problem, not an availability/outage problem.**

| Model | Responses | Eligible | Eligible % | Avg confidence |
|---|---|---|---|---|
| gpt-oss:20b-cloud | 178 | 87 | 49% | 0.401 |
| glm-5.2:cloud | 177 | 40 | **23%** | **0.284** |

### Resulting signal composition (180 signals)
| model_id (final signal) | Count | Share | Meaning |
|---|---|---|---|
| finbert (fallback) | 87 | 48% | both models ineligible → deterministic fallback |
| ensemble:gpt-oss:20b-cloud | 53 | 29% | **only gpt-oss eligible** (glm dropped) |
| ensemble:glm-5.2:cloud+gpt-oss:20b-cloud | 34 | 19% | **true 2-model ensemble** |
| ensemble:glm-5.2:cloud | 6 | 3% | only glm eligible (gpt-oss dropped) |

Cross-check is internally consistent: gpt-oss eligible = 34+53 = 87 ✓; glm eligible = 34+6 = 40 ✓; neither = 87 → finbert ✓.

**Score distribution:** most extreme finals were FinBERT-fallback negatives — DELL/MU/INTC/BABA ≈ −0.62/−0.62/−0.62/−0.61. Most extreme ensemble positive = GM +0.60 (std 0.106). WDC ensemble −0.385 (std 0.247, high disagreement). **Functional verification:** `score = polarity × confidence` holds (e.g. DELL finbert 0.72 conf × ~−0.86 polarity ≈ −0.62). Low-confidence glm outputs correctly excluded from the ensemble (eligibility gate working). Duplicate news do **not** double-weight (one signal per symbol per cycle via `unique_signal_per_symbol_time`). LLMs are called offline in the worker, never in the cycle hot path — confirmed by architecture and by the fact the sentiment worker and portfolio cycle are separate beat jobs.

**Concern:** with only 19% true ensembles and 48% fallback, "ensemble variance" as a hallucination guard is largely inactive — half the live signals are single-source (finbert or one LLM). See [DAY-007].

## 6. Final Signals by Ticker (selected)

| Ticker | Score | Conf | ens_std | Model | Note |
|---|---|---|---|---|---|
| GM | +0.600 | 0.825 | 0.106 | 2-model ensemble | strongest bull, no position/trade |
| MU | +0.500 | 0.70 | 0.141 | 2-model ensemble | drove no S4 order (S1 momentum entry instead) |
| WDC | −0.385 | 0.70 | 0.247 | 2-model ensemble | triggered reversal SELL 14:37; high disagreement |
| WDC | +0.363 | 0.518 | 0.0 | **finbert fallback** | FK'd by BUY trade #373 (desync) |
| HOOD | +0.436 | 0.518 | 0.0 | **finbert fallback** | drove BUY #372 |
| BA | +0.297 | 0.70 | 0.177 | 2-model ensemble | drove BUY #375 (clean) |
| DELL/INTC/BABA | ≈ −0.62 | 0.72 | 0.0 | finbert fallback | no positions → no action |

203 signals landed as `SKIP_THRESHOLD` (score < 0.35/0.40 feedback threshold) — the vast majority of the book correctly filtered out.

## 7. Orders Generated / Executed

Decisions (`execution_decisions`, 07-21): **19 BUY, 9 SELL, 203 SKIP_THRESHOLD**. Actual broker submissions (order_id present) → 5 BUY fills + 9 SELL orders. **Idempotency held**: 14 BUY decisions (repeat WDC/MU targets across cycles) produced no order.

### Entries (5 real; `trades` 371–375)
| Trade | Symbol | Time | Strategy / basis | Qty | Notional | signal_score | FK signal | Status |
|---|---|---|---|---|---|---|---|---|
| 371 | IWM | 14:07 | S1 momentum (score 0.013) | 2.750 | $808.6 | — | none | open |
| 372 | HOOD | 15:37 | S4 **finbert fallback** +0.436 | 11.363 | $1224.6 | +0.436 | **NULL** | closed −15.35 |
| 373 | WDC | 16:37 | "S4+S1 −0.385" (combined 0.027) | 2.981 | $1637.33 | **−0.385** | **4427 (+0.363 finbert)** | open (trimmed, unreconciled) |
| 374 | MU | 17:22 | S1 momentum (score 0.006) | 0.372 | $363.13 | — | none | open |
| 375 | BA | 18:22 | S4 ensemble +0.297 | 5.958 | $1220.59 | +0.297 | 4509 (ensemble) | open |

### Exits (8; `trades`)
| Trade | Symbol | Exit time | exit_reason | net_pnl |
|---|---|---|---|---|
| 365 | TXN | 14:22 | portfolio_sell (S4 expired) | +6.24 |
| 369 | AMZN | 14:22 | portfolio_sell (S4 expired) | −11.88 |
| 370 | SONY | 14:22 | portfolio_sell (S4 expired) | −3.73 |
| 359 | GE | 14:22 | portfolio_sell (s1_weight_drop) | −24.43 |
| 366 | IBM | 14:22 | portfolio_sell (S4 expired) | −36.76 |
| 295 | WDC | 14:37 | sentiment_reversal | −1.74 |
| 313 | MU | 15:22 | sentiment_reversal | −4.20 |
| 372 | HOOD | 18:52 | portfolio_sell ("S4 expired", stale ref) | −15.35 |

**Plus 1 partial-trim SELL** (WDC decision 3484, order `bf7fe4b8`, 18:22) that reduced #373 from 2.981→1.400 shares but did **not** close/record the trade — see [DAY-004]. All orders were within market hours (14:07–18:52 UTC ⊂ 13:30–20:00). No duplicate/same-minute orders. No circuit breaker or risk constraint fired (`constraints_fired = []` in all 24 cycles).

## 8. PnL / Return

| Bucket | Value |
|---|---|
| Realized net PnL (8 exits) | **−$91.85** (gross −80.06, costs $11.79) |
| — from pre-07-21 positions (7 trades) | −$76.50 |
| — from 07-21 same-day roundtrip (HOOD) | −$15.35 |
| Unrealized on 07-21 entries still open (IWM, WDC, MU, BA) | **≈ −$48.4** (IWM +3.93, WDC −40.70, MU −15.99, BA +4.35) |
| Book NAV (22:30 risk report) | $109,846.90 |
| Gross exposure | 26.9% |

Costs on 07-21 exits total $11.79 (slippage/commission model). Per-strategy attribution is mixed (S4-expiry, s1_weight_drop, sentiment_reversal) and not cleanly separable from the current schema. **Note:** WDC unrealized (−$40.70) is on the *trimmed remainder* (1.400 sh); PnL on the ~1.58 trimmed shares is neither realized-booked nor represented — see [DAY-004]. `portfolio_monitor_snapshots` has **0 rows for 07-21**, so no intraday NAV/drawdown trajectory is reconstructable; only the single 22:30 EOD risk snapshot exists.

## 9. Buy/Sell Correctness Analysis

| Check | Result |
|---|---|
| Long-only structurally respected | ✅ all 5 entries long (WDC −0.385 still opened a *long*, not a short) |
| No pyramiding at fill level | ✅ 19 BUY decisions → 5 fills; repeat WDC/MU BUYs idempotently suppressed |
| No out-of-hours orders | ✅ all 14:07–18:52 UTC |
| No duplicate / same-minute orders | ✅ |
| Stop-loss respected | ✅ (none triggered on 07-21) |
| Sentiment-reversal SELLs used correct signal | ✅ WDC/MU reversal SELLs fired on the ensemble −0.385/−0.375 |
| Paper/live mode coherent | ✅ paper confirmed in running container |
| SELL reconciliation | ⚠️ 9 SELL decisions = 8 full exits + 1 partial trim (trim unreconciled — [DAY-004]) |
| BUY only when permitted | ❌ HOOD & WDC bought on **fallback** signals ([DAY-001], [DAY-002]) |
| Signal→order provenance integrity | ❌ WDC FK≠recorded score ([DAY-001]); HOOD entry has NULL signal_id |
| Reversal-rebuy discipline | ⚠️ WDC & MU re-bought at the exact 2h cooldown boundary ([DAY-003]) |

## 10. Anomalies

### [DAY-001] WDC BUY: signal_id↔score desync + fallback provenance (bug #59, live 07-21)
- **Tipo:** Bug — **Area:** Signal / Orders
- **Evidenza:**
  - tabella: `trades.id=373`, `sentiment_signals.id ∈ {4390, 4427}`, `execution_decisions.id=3443`
  - timestamp: entry 2026-07-21 16:37:01 UTC
  - query/fatti: trade #373 `signal_id=4427` → signal 4427 is **WDC +0.363, finbert, fallback_used=t**; but `trades.signal_score = −0.385`, which is signal **4390** (WDC ensemble, −0.385). Decision reason text also cites "−0.385 (ensemble)". FK, recorded score and reason describe **two different signals**.
- **Descrizione:** The trade is FK-linked to a bullish FinBERT-fallback signal, records a bearish ensemble score, and was opened on a name reversal-sold 2h earlier on that same −0.385. The actual BUY driver is ambiguous and the audit trail is internally contradictory.
- **Impatto:** Corrupts auditability/reproducibility of a live (paper) position now −$40.70 unrealized; the fallback signal that likely drove the buy is exactly the class PR #114 prohibits.
- **Severità:** Critical — **Confidenza:** High
- **Azione consigliata:** Verify PR #114 (commit 2a3250a, merged 07-22) actually (a) blocks BUYs on `fallback_used=True` signals and (b) writes `signal_score` from the same signal as `signal_id`. Backfill/annotate #373's provenance. Confirm on the first live post-fix cycle.
- **Test/monitor:** invariant test `trades.signal_score == sentiment_signals[trades.signal_id].score`; alert on any BUY whose FK signal has `fallback_used=True`.

### [DAY-002] HOOD BUY on FinBERT-fallback +0.436 from a generic "movers" roundup → −$15.35
- **Tipo:** Bug / Rischio — **Area:** LLM / Signal / Orders
- **Evidenza:** `trades.id=372` (entry 15:37, exit 18:52 portfolio_sell, net −15.35); decision 3372 reason "S4 news-driven: sentiment +0.436 (finbert)… FinBERT fallback (ensemble divergence)"; source article `news_log` HOOD = "Hasbro, Utz Brands, Park Aerospace And Other Big Stocks Moving Higher" (14:37).
- **Descrizione:** A fallback (single-source FinBERT) sentiment read of a generic multi-symbol "stocks moving higher" roundup passed the 0.35 threshold and generated a real BUY. `trades.signal_id` is NULL (no FK), so provenance is only recoverable via the decision row.
- **Impatto:** Real capital committed on a weak, non-idiosyncratic signal; largest same-day roundtrip loss of the day. Same fallback-BUY class as [DAY-001].
- **Severità:** High — **Confidenza:** High
- **Azione consigliata:** Same PR #114 fallback-BUY block; require non-NULL `signal_id` on every entry trade; consider a news-specificity gate (reject multi-symbol roundup articles for S4 entries).
- **Test/monitor:** alert on entry trades with NULL `signal_id`; daily count of fallback-driven BUYs (target 0 post-#114).

### [DAY-003] WDC & MU re-bought exactly 2h after a sentiment-reversal SELL (cooldown-boundary whipsaw)
- **Tipo:** Rischio — **Area:** Signal / Risk
- **Evidenza:** WDC sold 14:37 (reversal −0.385) → re-bought 16:37 (Δ=2h00m); MU sold 15:22 (reversal −0.375) → re-bought 17:22 (Δ=2h00m).
- **Descrizione:** The 2h reversal-rebuy cooldown (issues #67/#68) is *working* — but both names re-entered at the exact expiry of the window, WDC while its ensemble sentiment was still −0.385. S1 momentum and S4 sentiment disagree and the short cooldown permits immediate whipsaw.
- **Impatto:** Round-trips into names just exited on bearish sentiment; adds cost and drawdown risk without new information.
- **Severità:** Medium — **Confidenza:** High
- **Azione consigliata:** Consider lengthening the cooldown, or blocking S1 re-entry while a fresh contradictory S4 signal (< threshold) is still active for the symbol.
- **Test/monitor:** metric "re-entries within 3h of a reversal SELL on the same symbol".

### [DAY-004] Partial trim leaves trade #373 unreconciled (broker qty ≠ trade qty, unbooked PnL)
- **Tipo:** Bug — **Area:** Broker / PnL
- **Evidenza:** decision 3484 (WDC SELL, order `bf7fe4b8`, 18:22, reason "S1 momentum… weight 0.7%"); `trades.id=373` has `exit_order_id=bf7fe4b8` but `exit_time`/`exit_price`/`exit_reason` NULL and `qty=2.981`; broker position WDC = **1.400** shares.
- **Descrizione:** The single-entry→single-exit trade model can't represent a partial rebalance trim. The trim stamped `exit_order_id` without closing the trade, so ~1.58 sold shares have no realized PnL and the trade's qty is stale vs the broker.
- **Impatto:** PnL under-attribution and a reconciliation divergence between `trades` and the broker; a lingering half-closed row.
- **Severità:** High — **Confidenza:** High
- **Azione consigliata:** Support partial exits (split lots or a fills ledger); on trim, book realized PnL on the sold quantity and keep the trade open for the remainder, or reconcile qty to broker.
- **Test/monitor:** nightly reconcile `trades.qty (open)` vs broker positions; alert on `exit_order_id NOT NULL AND exit_time IS NULL`.

### [DAY-005] Ticker mis-extraction: unrelated articles tagged to MU/MS via gdelt org_lookup
- **Tipo:** Anomalia / Rischio — **Area:** News / Data
- **Evidenza:** `news_log` 07-21, ticker=MU, `extraction_method=org_lookup`: "Apple Stock Hits a New All-Time High", "This 40%-Yielding ETF Just Got 20% Cheaper", "Baystreet.ca – Small Gains for TSX Futures", "Bitcoin Hits One-Month High", "Why Is Galaxy Digital Stock Surging"; "Kimi Steals Spotlight, But Anthropic Cements Top Spot" tagged MU via source_metadata. MS = 20/20 gdelt (over-broad short-token match).
- **Descrizione:** Broad-market and unrelated stories are attached to MU/MS, diluting per-ticker sentiment aggregation. On 07-21 the *strong* MU signal still mapped to a relevant article, so no bad trade resulted — but the false-positive ticker rate is non-zero (the QX-01 concern in CLAUDE.md).
- **Impatto:** Noise in the signal store; latent risk of a wrong-ticker signal. Directly relevant to `false_positive_ticker_rate → 0` goal.
- **Severità:** Medium — **Confidenza:** Medium
- **Azione consigliata:** Tighten the deterministic resolver on the gdelt `org_lookup` path (require `$cashtag`/title mention for short/ambiguous tokens like MS); feed these into the QX-01 golden label set.
- **Test/monitor:** sample gdelt `org_lookup` items into the Labeling UI; track precision by extraction_method.

### [DAY-006] Test-in-prod: kill-switch toggled + prod config mutated + TEST_STOP_* rows in prod trades
- **Tipo:** Ambiguità / Rischio (Ops hygiene) — **Area:** Ops / Data
- **Evidenza:** `audit_log` 2026-07-21 23:41:47 `KILLSWITCH_ACTIVATE {"reason":"manual operator halt via API"}`; 23:41:48 config UPDATE `portfolio_drawdown=0.05` and `{"reason":"test-deep-merge-verified", max_position_pct=0.2}`; 23:42:07 INSERT trades 376/377/378 = `TEST_STOP_1/2/3`. Rows 376–378 now **absent** (deleted; ID gap remains).
- **Descrizione:** A test/QA run exercised kill-switch + config-deep-merge + stop-loss against the **production** DB after hours. Unlike the 07-11 incident, the test trade rows were cleaned up this time.
- **Impatto:** Prod config/kill-switch mutated by tests; audit noise; ID gap. Low blast radius on 07-21 (after market close), but the pattern is fragile.
- **Severità:** Medium — **Confidenza:** High
- **Azione consigliata:** Route these tests to a disposable/ephemeral DB; forbid `TEST_*` symbols in prod `trades` at the DB layer (CHECK/trigger); require an explicit reason for kill-switch and config mutations.
- **Test/monitor:** alert on any `trades.symbol LIKE 'TEST%'` in prod; alert on config UPDATE with `reason ILIKE '%test%'`.

### [DAY-007] glm-5.2 eligibility collapse → 48% FinBERT fallback, ensemble guard largely inactive
- **Tipo:** Rischio — **Area:** LLM
- **Evidenza:** `llm_responses` 07-21: glm-5.2 40/177 eligible (23%), avg_conf 0.284; gpt-oss 87/178 (49%). Final signals: 48% finbert, 33% single-model, only 19% true 2-model ensemble.
- **Descrizione:** Both models were up (no outage), but glm-5.2's low-confidence/ineligible output rate forces the pair to collapse to one model or to FinBERT nearly half the time. The "ensemble variance" hallucination guard is inactive for ~81% of signals.
- **Impatto:** S4 alpha quality and the ensemble safety net are degraded; consistent with the standing #59/ensemble-divergence backlog.
- **Severità:** High — **Confidenza:** High
- **Azione consigliata:** Escalate the pending pair-swap / 3rd-model decision (ensemble-divergence backlog); persist divergent raw outputs to diagnose glm-5.2's low eligibility; re-evaluate glm-5.2 membership.
- **Test/monitor:** daily per-model eligibility % and fallback rate; alert if any model < 30% eligible for a full session.

### [DAY-008] Degenerate herfindahl_index = 1.0 in EOD risk report (pre-existing)
- **Tipo:** Bug (metric) — **Area:** Risk
- **Evidenza:** `risk_reports` 2026-07-21 22:30: `herfindahl_index = 1.000000`, `combined_drawdown = 0.093765`, `total_exposure = 0.269274`, `alerts = []` — despite ~40 open positions.
- **Descrizione:** Concentration index reads a single-name value (1.0) for a diversified book; `combined_drawdown` (9.38%) is the known-misleading aggregate (per prior bug sweep, real ≈ 0.4%). Metrics-only; did not gate any decision (no alerts).
- **Impatto:** Risk dashboard reliability; masks true concentration/drawdown.
- **Severità:** Low — **Confidenza:** High
- **Azione consigliata:** Fix HHI computation (weights over market value across all positions); reconcile `combined_drawdown` against realized book drawdown.
- **Test/monitor:** unit test HHI on a known multi-position book (expect ≪ 1.0).

### [DAY-009] HOOD exit attributed to a stale 07-20 signal, not the 07-21 entry signal
- **Tipo:** Bug (provenance) — **Area:** Signal / Orders
- **Evidenza:** decision 3503 (18:52) HOOD SELL reason "[expired] S4 signal expired (age=24.3h, generated 2026-07-20 18:31 UTC, score=−0.150)"; but #372 was entered 07-21 15:37 on +0.436 (age at exit ≈ 3.25h, not expired).
- **Descrizione:** The expiry logic referenced an older, unrelated HOOD S4 signal to justify closing a position opened on a newer signal. The close may be reasonable, but the attribution is wrong.
- **Impatto:** Misleading exit provenance; complicates postmortem attribution.
- **Severità:** Medium — **Confidenza:** Medium
- **Azione consigliata:** Tie exit-expiry evaluation to the position's own entry signal, not the latest/oldest symbol signal.
- **Test/monitor:** assert exit "expired" reason references the same signal chain as the entry.

## 11. False Positives / Areas Confirmed Correct

- **Idempotency / no fill-level pyramiding:** 19 BUY decisions → 5 fills; repeated WDC (8×) and MU (7×) BUY targets across cycles created **no** extra orders. ✅
- **Cycle cadence:** 24 cycles at clean 15-min spacing 14:07–19:52 UTC, no gaps, both S1 and S4 run every cycle. ✅
- **No out-of-hours orders; no duplicate/same-minute orders.** ✅
- **No circuit breaker / risk constraint fired**; exposure 26.9% within limits. ✅
- **Long-only structurally intact** (the WDC −0.385 case opened a long, never a short). ✅
- **Sentiment scoring formula** `polarity × confidence` verified; low-confidence glm outputs correctly excluded. ✅
- **BA BUY well-grounded** (Boeing airline-deals article, +0.297 ensemble). ✅
- **News dedup:** 0 duplicates, 0 future timestamps, all fetches within market hours. ✅
- **SELL logic:** S4-expiry, s1_weight_drop and sentiment_reversal all fired with coherent, correctly-signed signals. ✅

## 12. Missing / Inaccessible Data

- **07-21 worker/backend/frontend logs:** unavailable. All containers restarted ~07-22 07:24 (`Up 16 minutes` at analysis time); `docker compose logs` only retains post-restart (07-22) output. Reconstruction is **DB-only**. (Recurring issue — see reference memory on log wipe by restart.) *Needed query if logs existed:* `docker compose logs worker --since "2026-07-21T13:00" --until "2026-07-21T21:00"`.
- **`portfolio_monitor_snapshots`:** 0 rows for 07-21 → no intraday NAV/drawdown/degradation trajectory.
- **`performance_metrics`:** empty → no daily composite IC/ICIR/drift for 07-21.
- **`fallback_counters`:** empty → Ollama/fallback health inferred from `sentiment_signals`/`llm_responses`, not from counters.
- **Per-share trim PnL (WDC #373):** not booked ([DAY-004]).

## 13. Immediate Recommendations

1. **Clear the current kill-switch** if the "test" halt was unintended — the system is **HALTED right now** (`system:halted_by_operator=1`, reason "test", set 07-22 07:40, **no TTL**). No orders will be placed until cleared. Verify before the next market open.
2. **Verify PR #114 live** (fallback-BUY block + signal_id↔score fix) on the first post-fix cycle; confirm [DAY-001]/[DAY-002] cannot recur.
3. **Reconcile WDC #373** ([DAY-004]) — book the trimmed-share PnL and align `trades.qty` to broker.
4. **Escalate glm-5.2 eligibility** ([DAY-007]) — 23% eligible is not viable for an ensemble member.
5. **Move QA/stop-loss tests off the prod DB** ([DAY-006]).

## 14. Tests / Monitors to Add

- Invariant: `trades.signal_score == score(trades.signal_id)`; block/alert BUYs whose FK signal is `fallback_used=True`.
- Entry trades must have non-NULL `signal_id`.
- Nightly reconcile: open `trades.qty` vs broker positions; alert on `exit_order_id NOT NULL AND exit_time IS NULL`.
- Daily per-model LLM eligibility % + fallback rate; alert if a model < 30% eligible for a session.
- Prod guard: reject `trades.symbol LIKE 'TEST%'`; alert on config UPDATE with test-flavored reason.
- Re-entry-within-3h-of-reversal-SELL counter.
- HHI unit test on a multi-position book (expect ≪ 1.0).
- Kill-switch state check with no-TTL alarm (halt without expiry should page).

## 15. Suggested Technical Tickets

| Ticket | Title | Severity | Related |
|---|---|---|---|
| T-2107-1 | Enforce & verify fallback-BUY block + signal_id↔score integrity live | Critical | [DAY-001][DAY-002], PR #114, #59 |
| T-2107-2 | Support partial exits / trim reconciliation in trade lifecycle | High | [DAY-004] |
| T-2107-3 | glm-5.2 eligibility remediation / pair-swap decision | High | [DAY-007], ensemble-divergence backlog |
| T-2107-4 | Tighten gdelt org_lookup ticker resolver (QX-01) | Medium | [DAY-005] |
| T-2107-5 | Route kill-switch/config/stop-loss tests off prod DB + DB guard on TEST_* | Medium | [DAY-006] |
| T-2107-6 | Exit-expiry must reference the position's own entry signal | Medium | [DAY-009] |
| T-2107-7 | Lengthen/condition reversal-rebuy cooldown | Medium | [DAY-003] |
| T-2107-8 | Fix herfindahl_index + combined_drawdown computation | Low | [DAY-008] |
| T-2107-9 | Persist portfolio_monitor_snapshots + retain worker logs across restarts | Low | §12 |

## 16. System State

- **Ollama Cloud:** **UP all day, 0 h downtime.** gpt-oss 178 responses, glm-5.2 177 (≈ every news item). The 48% fallback is driven by **eligibility/confidence**, not availability. glm-5.2 eligible 23% (avg conf 0.284); gpt-oss 49% (avg conf 0.401).
- **FinBERT fallback rate:** **48% of signals** (87/180). Of BUY decisions, HOOD and (via FK) WDC entered on fallback signals. True 2-model ensemble = 19% of signals; single-model = 33%.
- **Worker restarts:** all `alembic-*` containers restarted ~2026-07-22 07:24 UTC (post-target; wiped 07-21 logs). No evidence of a *07-21* worker restart in surviving data.
- **Kill-switch:** activated after-hours 07-21 23:41 ("manual operator halt via API", test-associated) and again 07-22 07:40 ("test"). **Currently ACTIVE / no TTL** — trading halted at analysis time.
- **Risk gates:** no circuit breaker/constraint fired on 07-21; exposure 26.9%; NAV $109,846.90; no alerts. `herfindahl_index` degenerate (1.0), `combined_drawdown` 9.38% (suspect).

---
*End of report. Read-only forensic analysis; no code changed, no orders placed, no commits.*
