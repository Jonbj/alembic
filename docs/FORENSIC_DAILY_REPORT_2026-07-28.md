# Forensic Daily Report — 2026-07-28

Analyst: Autonomous forensic session (Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer)
Mode: read-only, non-interactive. No code changed, no orders sent, no worker triggered by this session.
Trading mode confirmed: **PAPER** (`ALPACA_BASE_URL=https://paper-api.alpaca.markets`), `execution.engine=portfolio` (only `portfolio-cycle` submits orders — confirmed no `legacy_sentiment` path fired today).
Timezone: **UTC**, confirmed explicitly in `src/workers/celery_app.py:51` (`timezone="UTC"`). No ambiguity. Market hours used below: pre-market <13:30 UTC, market hours 13:30–20:00 UTC, post-market/batch >20:00 UTC.

---

## 1. Executive Summary

Portfolio cycles (`S1`+`S4`) ran every 15 min from 14:07 to 19:52 UTC without gaps, despite an **unexplained mid-day restart of `worker`+`worker-inference` at 16:04 UTC** (no corresponding git deploy found) — no cycle was lost, state is DB-backed so the restart was safe. 4 trades opened (BA, QQQ, SOXX, MU — all low-conviction, $329–$1,253 notional), 6 trades closed (all SELL via `sentiment_reversal`/`portfolio_sell`/`s1_weight_drop`, no live stop-outs), realized P&L −$132.65, but the book had a genuinely bad **−2.9% NAV day (−$3,187.82)**, driven by unrealized mark-to-market, not by today's trades. The Ollama ensemble (glm-5.2+gpt-oss) ran all day with **zero timeouts/errors** and a 1:1 request pairing, but **38.7% of ticks still fell back to FinBERT** because individual-model confidence is chronically below the 0.4 eligibility threshold (mean confidence 0.39/0.25) — a known, still-unresolved quality issue. A **known misleading-metric bug recurs**: the 22:30 UTC risk report logged `RISK ALERT: Strategy portfolio drawdown 10.3% exceeds 10%` while the report's own `combined_drawdown` field said 1.02% and the real-time equity kill-switch (cap 5%, correctly seeded post-2026-07-22 fix) measured ~0.6% — same divergent-metric bug flagged in the 2026-07-22 sweep, now escalated to ALERT level, never enforced (informational only). A **daily "reuters" RSS ingestion-stats row has been appearing every day since at least 07-21** (fetched/queued ~48/day) while `RSS_INGESTION_ENABLED` is unset (defaults off) in the worker container and **zero reuters items have ever reached `news_log`** — either a stale/orphaned task or a manual invocation artifact; needs engineering confirmation. Cross-referencing `sentiment_reversal` cooldown behavior on MU shows the **#68 fix is working correctly** (re-buy blocked for exactly 2h00m after a reversal-forced SELL). No pyramiding, no duplicate orders, no SELL-on-positive-sentiment, no future timestamps, no ticker-ambiguity issues found.

## 2. Verdict

**OK con warning.**

Rationale: no correctness-breaking bug found in today's order flow (buy/sell logic, cooldowns, pyramiding guard, kill-switch all behaved as designed); but (a) a pre-existing misleading risk metric fired at ALERT severity today, (b) a news source appears to be silently discarding 100% of its output daily, (c) an unexplained infra restart occurred mid-session, and (d) ensemble confidence quality remains structurally poor (~39% fallback). None of these altered today's actual trading decisions incorrectly, but items (a)-(c) reduce auditability/trust and should be resolved before drawing conclusions from the risk dashboard or news coverage metrics.

---

## 3. Timeline — 2026-07-28 (UTC)

| Time | Component | Event | Source |
|---|---|---|---|
| 00:00–13:30 | worker | Routine overnight tasks (SPY benchmark fetch retried repeatedly, known IEX-subscription warning, no impact) | worker logs |
| 10:45:56 | api, beat | Containers already running (started earlier, unrelated to today) | `docker inspect` |
| 14:01:20 | ingest | First `alpaca_benzinga` news item fetched | news_log |
| 14:00–19:46 | ingest | 117 gdelt_gkg + 96 alpaca_benzinga items land in `news_log` (15-min cadence) | news_log |
| 14:01–19:46 | LLM | glm-5.2:cloud + gpt-oss:20b-cloud run in lockstep (216/217 requests each), 0 errors/timeouts | llm_responses |
| 14:07:00 | portfolio-cycle | First cycle of the day (`S1`+`S4`, 47 orders considered); BA BUY (S4, sentiment +0.523, wt 2.0%) | portfolio_cycles #646, execution_decisions #4537, trades #548 |
| 14:22:00 | portfolio-cycle | 4 SELLs in one cycle: CRM (signal expired 19.4h old), NVDA (whipsaw-shadow, not enforced), ARM (S1 weight→0, position held since 07-14), QQQ (S1 weight→0, held since 07-16) | execution_decisions #4547–4550, trades #308,#358,#500,#501 |
| 14:37:00 | portfolio-cycle | SOXX SELL, `sentiment_reversal` score −0.360 < −0.35 threshold | execution_decisions #4562, trade #357 |
| 14:52:00 | portfolio-cycle | QQQ BUY (S1 momentum, wt 1.2%) — **30 min after** its own 14:22 SELL; SOXX BUY decision recorded but not submitted (reversal cooldown active) | execution_decisions #4577/#4578, trade #549 |
| 14:52–17:07 | portfolio-cycle | SOXX BUY decision re-recorded every cycle (9×) with no order submitted (blocked by #68 reversal cooldown until 16:37, then likely gated by aggregate stop-risk budget/notional check afterward — not conclusively isolated) | execution_decisions |
| 16:04:22 | worker, worker-inference | **Containers restarted** (StartedAt 16:04:22Z); no corresponding commit merged on 07-28 | `docker inspect`, git log |
| 16:07:07 | worker | First cycle after restart; dedup state intact (`signal_id=5293 for BA already fired today — skipping`), confirms DB-backed idempotency survived the restart | worker logs |
| 17:07:00 | portfolio-cycle | MU SELL, `sentiment_reversal` score −0.395 < −0.35 | execution_decisions #4775, trade #374 |
| 17:22:00 | portfolio-cycle | SOXX BUY finally submitted (45 min after its 2h reversal-cooldown expired); MU BUY decision starts repeating every cycle, not submitted | trade #551 |
| 17:22–18:52 | portfolio-cycle | MU BUY decision recorded every cycle (7×), blocked by #68 reversal cooldown | execution_decisions |
| 19:07:00 | portfolio-cycle | MU BUY submitted **exactly 2h00m00s** after the 17:07 reversal SELL — reversal cooldown expiring precisely on schedule | trade #552 |
| 19:37–19:52 | worker | P0-05 pyramiding guard fires for ~35 symbols (most of book already holds a position) — expected end-of-session behavior | worker logs |
| 20:00 | market close | (Trading window ends per spec; portfolio cycles continue logging through 19:52 last observed decision) | portfolio_cycles |
| 22:00:15 | worker | Forward-return worker: 898 updated, 111 skipped_no_data, 0 errors | worker logs |
| 22:30:00 | risk_monitor_task | Risk report #46: NAV $109,458.73, `combined_drawdown` 1.02%, `herfindahl` 0.023, exposure 29.3%, but per-strategy `drawdown` field 10.3% → **RISK ALERT fired** (see §10 DAY-001) | risk_reports #46 |
| 22:45:06 | worker | Counterfactual worker: 250 decisions updated, 0 errors | worker logs |

---

## 4. News Ingest — Table by Source

| Source | Fetched (funnel) | Queued (funnel) | Duplicates (funnel) | Discarded-no-ticker | In `news_log` | Explicit drops (`news_queue_drops`, avg age) |
|---|---:|---:|---:|---:|---:|---:|
| gdelt_gkg | 2,505 | 189 | 141 | 2,253 | 117 | 33 (2.12h) |
| alpaca_benzinga | 662 | 363 | 2,983 | 0 | 96 | 73 (2.23h) |
| reuters | 48 | 48 | 0 | 12 | **0** | 0 |

Observations:
- GDELT's 90% no-ticker discard rate is expected/by-design (firehose source, strict deterministic ticker resolver per `docs/Alembic_ticker_sentiment_design.docx`).
- Benzinga's 2,983 "duplicates" vs 363 queued (89% dedup) is high but plausible for a 15-min-cadence poller with overlapping fetch windows against the same underlying wire.
- **Gap not reconciled**: funnel "queued" (363 benzinga / 189 gdelt) vs actual `news_log` rows (96 / 117) vs explicit `news_queue_drops` (73 / 33) leaves ~194 (benzinga) / ~39 (gdelt) items unaccounted for — neither ingested nor logged as dropped. See DAY-004.
- **Reuters: 100% loss.** 48 fetched/queued, 0 discarded-no-ticker beyond 12, yet 0 rows in `news_log` — and this is not a one-day blip (same pattern 07-21 through 07-29). See DAY-002.

### Top tickers by news volume (2026-07-28)

| Ticker | News count |
|---|---:|
| MS | 39 |
| MU | 23 |
| NVDA | 14 |
| GS | 12 |
| AMD | 12 |
| DB | 7 |
| AMZN | 7 |
| MSFT | 6 |
| TSM | 6 |
| META | 6 |
| AXP | 6 |

No future-timestamped news, no out-of-hours anomalies, no ticker-ambiguity cases found in a spot check of the top tickers (all unambiguous large-caps). Highest-impact items on today's trading: the BA article behind the 14:07 BUY (sentiment +0.523, "Record backlog and 2026 free cash-flow guidance...") and the two `sentiment_reversal` triggers on SOXX (−0.360) and MU (−0.395).

**Confidence of this section: High** (funnel counters + `news_log` + `news_queue_drops` cross-checked directly against Postgres).

---

## 5. LLM Model Performance

| Model | Requests | Eligible (conf ≥0.4) | Eligibility rate | Mean polarity | Mean confidence | Errors/timeouts |
|---|---:|---:|---:|---:|---:|---:|
| glm-5.2:cloud | 216 | 27 | 12.5% | −0.058 | 0.249 | 0 |
| gpt-oss:20b-cloud | 217 | 27 | 12.4% | −0.054 | 0.391 | 0 |

| Ensemble output | Count | Mean score (polarity×confidence) | Mean confidence |
|---|---:|---:|---:|
| ensemble (both eligible) | 133 | −0.016 | 0.276 |
| single-model fallback (gpt-oss only) | 74 | −0.062 | 0.515 |
| single-model fallback (glm-5.2 only) | 8 | +0.066 | 0.588 |
| finbert (deterministic, both models ineligible) | 2 | +0.065 | 0.174 |

**Overall fallback rate 2026-07-28: 38.7%** (84/217 — improved vs the ~70-86% seen after the late-June GLM-5.2 swap, but still far from healthy; per-model eligibility of ~12% means the vast majority of individual model calls fall below the 0.4 confidence gate and never count toward the ensemble on their own).

Score extremes today: AMD +0.6375 (conf 0.85, fallback), BA +0.523 (conf 0.775, eligible — this is the one that drove the BA BUY), MU −0.395/−0.33 (drove the sentiment-reversal SELL), SOXX −0.360 (drove its sentiment-reversal SELL).

Functional checks:
- **Validation before signal store**: confirmed — `eligible` flag (confidence ≥ 0.4) is computed and persisted per-model in `llm_responses` before ensemble aggregation; `fallback_used` is a separate persisted flag on `sentiment_signals`.
- **Ensemble handles high variance**: `ensemble.py` computes `ensemble_std` across eligible models and would flag divergence past a threshold; today's `ensemble_std` was low (~0.28 mean confidence, no outlier disagreement observed in the extremes table above).
- **Duplicate news weighting**: not directly testable from today's data without joining `news_log.content_hash` to `sentiment_signals.news_log_id`; flagged as untested (see §12).
- **Confidence lowering weight**: confirmed by design (`score = polarity × confidence` per CLAUDE.md and observed in `sentiment_signals.score` vs `llm_responses.polarity`).
- **Offline/background execution**: confirmed — all LLM calls happen in `worker-inference` (Celery, queue=inference), never inside `portfolio_scheduler`'s per-tick loop.
- **Hallucination reaching decisions directly**: mitigated by the eligibility gate + fallback to FinBERT, but **not eliminated** — a single eligible model's polarity (e.g., BA's glm-5.2/gpt-oss ensemble at +0.523) can directly become the deciding S4 signal with no secondary/supervisor cross-check visible in this pipeline for today's trades.

**Confidence: High** on the counts/rates; **Medium** on the "no hallucination reached a decision today" claim (not independently fact-checked against the BA news content).

---

## 6. Signals — Final per Ticker (symbols with a BUY/SELL decision today)

| Ticker | Driving strategy | Signal/score | Decision | Outcome |
|---|---|---:|---|---|
| BA | S4 (sentiment) | +0.523 (eligible ensemble) | BUY | Order filled, trade #548 opened |
| CRM | S4 (signal expiry) | +0.560 (stale, 19.4h > 4h max) | SELL | Position closed (no counter-signal) |
| NVDA | S4 (whipsaw, shadow) | +0.030 | SELL | Closed; anti-whipsaw damping would have suppressed (shadow-only, not enforced) |
| ARM | S1 (weight→0) | n/a | SELL | Position closed after 14 days held |
| QQQ | S1 (weight→0, then momentum) | n/a → +0.0117 | SELL then BUY (30 min later) | Round-trip; re-bought same day |
| SOXX | S4 (reversal) → S1 (momentum) | −0.360 → +0.009 | SELL then BUY (2h45m later) | Reversal cooldown respected, then re-entered |
| MU | S4 (reversal) → S1 (momentum) | −0.395 → +0.0052 | SELL then BUY (exactly 2h00m later) | Reversal cooldown enforced precisely |

**Confidence: High** — directly read from `execution_decisions`/`trades`.

---

## 7. Orders Generated / Executed

| Trade ID | Symbol | Side | Decision time | Order submitted | Fill time | Qty | Entry price | Entry notional | Strategy | Rationale |
|---|---|---|---|---|---|---:|---:|---:|---|---|
| 548 | BA | BUY | 14:07:00 | e1e9ae57… | 14:07:00 | 5.687 | $220.35 | $1,253.14 | S4 | Sentiment +0.523 |
| 549 | QQQ | BUY | 14:52:00 | 634b93b2… | 14:52:00 | 1.091 | $674.65 | $736.27 | S1 | Momentum wt 1.2% |
| 551 | SOXX | BUY | 17:22:00 | 5b99e226… | 17:22:00 | 1.155 | $494.14 | $570.57 | S1 | Momentum wt 0.9% |
| 552 | MU | BUY | 19:07:00 | 53fc7a65… | 19:07:00 | 0.398 | $827.12 | $329.25 | S1 | Momentum wt 0.5% |
| 308 | ARM | SELL (exit) | 14:22:00 | be00fe18… | 14:22:00 | 0.206 | exit $243.08 | — | S1 (opened 07-14) | Weight→0 |
| 358 | QQQ | SELL (exit) | 14:22:00 | d28a115c… | 14:22:00 | 1.084 | exit $669.70 | — | S1 (opened 07-16) | Weight→0 |
| 500 | NVDA | SELL (exit) | 14:22:00 | 6b65a41f… | 14:22:00 | 6.360 | exit $193.47 | — | S4 (opened 07-27) | Whipsaw-shadow, expiry |
| 501 | CRM | SELL (exit) | 14:22:00 | c9a561ef… | 14:22:00 | 7.058 | exit $181.51 | — | S4 (opened 07-27) | Signal expired |
| 357 | SOXX | SELL (exit) | 14:37:00 | f6920ed9… | 14:37:00 | 1.130 | exit $485.48 | — | S4 (opened 07-16) | sentiment_reversal |
| 374 | MU | SELL (exit) | 17:07:00 | 4c3d6d32… | 17:07:00 | 0.372 | exit $822.37 | — | S4 (opened 07-21) | sentiment_reversal |

All 10 orders show `status: filled` in the `/api/orders` feed, submitted-at ≈ filled-at (paper engine, no slippage-relevant latency). No rejects, no cancels found today. **23 additional BUY decisions were logged but never submitted** (SOXX ×9, MU ×7, plus ~35 P0-05 pyramiding-guard skips at 19:37/19:52) — all correctly gated, not silent failures (each has an explicit reason in `execution_decisions.reason` or worker logs).

**Confidence: High.**

---

## 8. PnL / Rendimento

| Metric | Value | Source |
|---|---:|---|
| Realized net P&L, trades closed 2026-07-28 | **−$132.65** | sum of 6 `trades.net_pnl` rows, cross-checked against `portfolio_daily_state.net_pnl` for 2026-07-28 (exact match) |
| Daily portfolio return (`portfolio_daily_state.daily_return`) | **−2.91%** | portfolio_daily_state |
| Implied daily P&L on $109,458.73 NAV | **≈ −$3,187.82** (matches `risk_reports.per_strategy_metrics.portfolio.daily_pnl` exactly) | risk_reports #46 |
| `combined_drawdown` (risk report, cross-strategy) | 1.02% | risk_reports #46 |
| Per-strategy "portfolio" `drawdown` field (60-day peak-to-trough) | 10.3% | risk_reports #46 |
| Real-time equity kill-switch drawdown (peak $110,113.93 vs current NAV) | ≈0.6–1.0% | Redis `portfolio:peak_equity` + risk_reports NAV |
| Current unrealized P&L across 48 open positions (live snapshot, not EOD 07-28) | +$268.84 (25 winners / 23 losers) | `/api/positions` |
| Total exposure | 29.3% | risk_reports #46 |
| Herfindahl (concentration) | 0.023 | risk_reports #46 |

**The −2.91% daily NAV move is not explained by the 6 realized trades alone** (−$132.65 of the −$3,187.82). The remainder (~−$3,055) is unrealized mark-to-market on the existing 48-position book — **not independently verified against Alpaca historical closes in this session**; the daily_return figure is trusted from `portfolio_daily_state` but its exact construction (whole-book MTM vs realized-only) was not re-derived line-by-line. Flagged as a data-completeness gap: no query was run to attribute the −$3,055 unrealized swing to specific symbols for 2026-07-28 close-to-close (today's `unrealized_pl` in §"Current unrealized P&L" reflects the live/current snapshot, one day later, and is not usable as a proxy for 07-28's EOD mark).

**Slippage/costs**: `cost_usd` on the 6 exits ranged $0.15–$1.21 (SOXX highest at $1.21, MU $0.19) — immaterial in dollar terms relative to the realized losses on those same trades (e.g. MU −$57.34 net vs $0.19 cost).

**Confidence: Medium** — realized P&L is High confidence (directly reconciled); the unrealized/mark-to-market attribution for the −2.9% day is Low confidence (not independently reconstructed).

---

## 9. Buy/Sell Correctness Analysis

| Check | Result |
|---|---|
| BUY only when allowed (no pyramiding) | **Pass** — P0-05 guard fired ~35+ times today, all correctly skipping BUYs where an open DB trade already existed |
| SELL/exit generated correctly | **Pass** — all 6 exits have an explicit, sensible `exit_reason`/mechanism (`sentiment_reversal` ×2, `portfolio_sell`/weight-drop ×4) |
| Stop-loss respected | **Pass (no stop-outs today)** — no rows in `stop_decisions` or `trades.exit_reason='stop_loss'` for 07-28; all exits were signal/weight-driven |
| Signal flip respected | **Pass** — MU and SOXX both flipped S4-bearish→S1-bullish only after the #68 reversal cooldown (2h) elapsed |
| Max holding days | **Not verifiable** — no explicit `max_holding_days` config found enforced in the scheduler; ARM (14 days) and QQQ (12 days) were closed via weight-drop, not a holding-period rule. Flag as ambiguity (§12). |
| Rebalance band respected | **Plausible but not conclusively isolated** — SOXX/MU BUY decisions recurred for hours before executing; cooldown expiry explains most of the delay, but SOXX's extra 45-min gap after its cooldown expired was not root-caused (candidate: aggregate stop-risk budget or `_MIN_ORDER_NOTIONAL=$100` gate, not confirmed) |
| No duplicate orders | **Pass** — no duplicate `order_id` values, no duplicate (tick_time, symbol) decision rows |
| No contrary orders without rationale | **Pass** — every SELL→BUY flip on the same symbol (QQQ, SOXX, MU) has an explicit, distinct rationale logged |
| No orders on disallowed tickers | **Pass** — all traded tickers are on the known watchlist |
| No orders outside expected hours | **Pass** — all decisions between 14:07 and 19:52 UTC, inside the 13:30–20:00 market-hours window |
| No trade on stale data | **Pass** — SKIP_STALE fired correctly 4× (INTC, SOXX ×2 at >90h and >4h staleness) |
| No trade on invalid LLM output | **Pass** — eligibility gate + fallback observed working; no invalid/malformed sentiment reached a decision |
| No trade while circuit breaker active | **Pass** — `killswitch_active` / `system:halted_by_operator` both unset all day (verified via Redis) |
| No trade on disabled strategy | **Pass** — only S1/S4 ran, matching `strategy_lifecycle` expectations (not independently re-verified against that table this session) |
| Paper/live coherence | **Pass** — `ALPACA_BASE_URL=paper-api.alpaca.markets`, `execution.engine=portfolio` |
| Idempotency under Celery retry | **Pass** — explicit dedup log observed post-restart (`signal_id=5293 for BA already fired today — skipping`) |
| Reconciliation orders↔fills↔positions | **Pass for today's 10 orders** — all `filled`, `trade_id` populated, matches `/api/positions` current holdings for BA/QQQ/SOXX/MU |

---

## 10. Anomalies Found

### [DAY-001] Risk-report drawdown ALERT computed from a different metric than the report's own headline drawdown

* Tipo: Bug (recurring/known, unresolved)
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports` id=46; `src/workers/risk_monitor_task.py`
  * timestamp: 2026-07-28 22:30:00 UTC
  * snippet/query: `combined_drawdown=0.010156`, `per_strategy_metrics.portfolio.drawdown=0.10340974263070817`, `alerts=[{"level":"ALERT","message":"Strategy portfolio drawdown 10.3% exceeds 10%"}]`; real-time kill-switch peak $110,113.93 vs NAV $109,458.73 → ~0.6-1.0%
* Descrizione: The ALERT-level log line reads as "today's portfolio is down 10.3%," but the same report's `combined_drawdown` (1.02%) and the independently-computed real-time equity kill-switch drawdown (~0.6-1%, cap 5%, correctly seeded per the 2026-07-22 fix) both say the real number is roughly 1%. The 10.3% figure is a 60-day peak-to-trough on the `portfolio_daily_state` return series and is a legitimate (if noisy) number in isolation, but presented as an "ALERT...exceeds 10%" it is operationally misleading. This is the same discrepancy flagged in the 2026-07-22 Bug Sweep memory ("combined_drawdown fuorviante 9.38% vs reale 0.4%"), still unresolved 6 days later, now for the first time crossing the 10% ALERT threshold.
* Impatto: Risk-alert fatigue / loss of trust in the risk dashboard; an operator seeing "ALERT: drawdown 10.3%" next to "combined_drawdown 1.02%" in the same JSON has no way to know which number to trust without reading the code. No automated action is currently gated on this alert (informational only), so no trading impact today, but if this alert is ever wired to an automated response, it would fire based on the wrong metric.
* Severità: High
* Confidenza: High
* Azione consigliata: Either rename the per-strategy field/alert message to something unambiguous (e.g. "60-day peak-to-trough drawdown") or align it with `combined_drawdown`'s methodology; do not let two different "drawdown" numbers coexist unlabeled in the same report.
* Test/monitor consigliato: Unit test asserting `risk_reports.alerts` messages reference the same drawdown value as `combined_drawdown`, or a naming/units test that fails if a report contains two differently-scaled fields both called "drawdown."

### [DAY-002] Reuters RSS source queues items daily but zero ever reach `news_log`

* Tipo: Anomalia / possibile Bug (silent data loss), da confermare
* Area: News / Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` (source='reuters'); `news_log` (source column); `src/workers/ingestion.py:722-758` (`run_rss_ingestion_worker`)
  * timestamp: recurring 07-21, 07-22, 07-23, 07-25, 07-26, 07-27, 07-28 (irregular times: 08:31, 14:14, 15:15, 21:16, 23:03, 23:43 — not a fixed cadence)
  * snippet/query: `SELECT source, day, updated_at FROM ingestion_stats_daily` shows `reuters | 2026-07-28 | 48 fetched | 48 queued | 0 duplicates | 12 discarded_no_ticker`; `SELECT source, count(*) FROM news_log WHERE fetched_at::date='2026-07-28' GROUP BY source` returns only `gdelt_gkg`/`alpaca_benzinga`, never `reuters`, on every day checked
* Descrizione: `run_rss_ingestion_worker` early-returns `{"skipped": True}` if `RSS_INGESTION_ENABLED` is unset or "0" (confirmed unset in the running `worker` container via `printenv`), per a comment referencing "FIX-02: dead feeds, 0 news in 17d." Yet `ingestion_stats_daily` shows real, non-zero reuters activity every day this week at irregular hours inconsistent with any fixed beat schedule found in `celery_app.py`. Either (a) the task is being invoked through a path this session didn't find (env var differs at invocation time, a different container, or a manual/ad-hoc call — possibly by a prior forensic/debugging session), or (b) items are queued to Redis `news:queue` and then silently dropped downstream before reaching `news_log`. Not root-caused in this read-only session.
* Impatto: If real, up to ~48 news items/day (Reuters business-news RSS) are fetched and never scored or reflected in any signal — a silent, unmonitored gap in news coverage; if it's a leftover manual-invocation artifact, it's contaminating `ingestion_stats_daily` with non-representative data that could mislead future forensic sessions (including this one).
* Severità: Medium
* Confidenza: Medium (the "0 items ever land in news_log" fact is High confidence; the root cause is not determined)
* Azione consigliata: Engineering to confirm (1) what actually invokes `run_rss_ingestion_worker` in production (beat schedule, cron, or manual), (2) the live value of `RSS_INGESTION_ENABLED` at invocation time, (3) whether `redis_client.rpush("news:queue", ...)` items tagged `source="reuters"` are being consumed and silently discarded by the sentiment worker's ticker/eligibility filters, or never consumed at all.
* Test/monitor consigliato: Alert if any source in `ingestion_stats_daily` has `queued > 0` but `news_log` has 0 rows for that source+day, checked daily.

### [DAY-003] Unexplained mid-session restart of `worker` + `worker-inference` at 16:04 UTC

* Tipo: Ambiguità / Rischio operativo
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect alembic-worker-1 --format '{{.State.StartedAt}}'` → `2026-07-28T16:04:22Z`; `RestartCount=0`; `git log --since/--until 2026-07-28` → no commits that day
  * timestamp: 2026-07-28 16:04:22–16:04:27 UTC (between the 15:52 and 16:07 portfolio cycles)
* Descrizione: Both `worker` and `worker-inference` (but not `beat` or `api`, which started earlier at 10:45 UTC) show a container start time mid-way through market hours, with `RestartCount=0` (suggesting a deliberate stop/start rather than a Docker auto-restart-on-crash). No corresponding commit was merged to `main` on 2026-07-28, so this wasn't a code deploy tracked by this session's `git log`. No portfolio cycle was skipped (646→647→…→669 all present, 15-min cadence intact) and DB-backed idempotency correctly prevented re-firing already-fired signals after the restart.
* Impatto: No observed trading impact today (idempotency held), but an unexplained mid-session infra restart during market hours is exactly the kind of event that *could* cause a missed cycle or a race window on the kill-switch check, and it isn't logged/alerted anywhere. Right now this only shows up by manually diffing container start times against `git log`.
* Severità: Low (no realized impact today) / Medium (as a monitoring gap)
* Confidenza: Medium (restart is certain; cause is unknown)
* Azione consigliata: Ask the operator/on-call whether a manual restart was performed on 07-28 ~16:00 UTC (e.g. env var change, out-of-band redeploy); if not, treat as an unexplained crash-restart and investigate OOM/exception logs around 16:04.
* Test/monitor consigliato: Alert on any `worker`/`worker-inference` container restart during market hours (13:30–20:00 UTC) that isn't correlated with a merged deploy commit within the preceding hour.

### [DAY-004] ~194 (benzinga) / ~39 (gdelt) queued news items per day not reconciled between funnel stats, `news_log`, and `news_queue_drops`

* Tipo: Ambiguità / possibile Bug, dati mancanti per la conferma
* Area: News / Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` (queued=363 benzinga / 189 gdelt) vs `news_log` (96 / 117) vs `news_queue_drops` (73 / 33)
  * timestamp: 2026-07-28, all-day aggregate
* Descrizione: 363 (benzinga) − 96 (landed) − 73 (explicit drop) = 194 items unaccounted for; 189 (gdelt) − 117 − 33 = 39 unaccounted. These items are neither in `news_log` nor in the explicit `news_queue_drops` audit table, so there's no record of what happened to them between being pushed to the Redis `news:queue` and the end of the pipeline.
* Impatto: Reduces auditability of the news pipeline — cannot currently answer "what happened to every fetched item" for ~15-20% of benzinga/gdelt volume without further instrumentation.
* Severità: Medium
* Confidenza: Medium (the arithmetic gap is High confidence; whether this represents a real bug vs an un-instrumented-but-benign step, e.g. `unique_signal_per_symbol_time` constraint collisions, is not determined)
* Azione consigliata: Add explicit accounting at every drop point in the sentiment worker's consume loop (unique-constraint conflicts on `news_log`, NO_TRADE ticker-resolver rejections, etc.) so `fetched = queued_to_log + queued_dropped + queued_rejected_by_X` always reconciles.
* Test/monitor consigliato: Daily reconciliation check: `fetched - news_log_count - news_queue_drops_count == 0` per source; alert if non-zero beyond a small tolerance.

### [DAY-005] `stop_decisions` table has not been written to since 2026-07-14

* Tipo: Corretto (con nota) / debito tecnico
* Area: Risk / Data
* Evidenza:
  * file/log/tabella: `SELECT cycle_ts::date, count(*) FROM stop_decisions GROUP BY 1` → last rows 2026-07-13/07-14; `trades` table for 2026-07-28 (#548,#549,#551,#552) all have `stop_strategy`, `stop_mode='fixed'`, `stop_vol_at_entry`, `stop_k`, `stop_floor`, `stop_cap` populated directly on the `trades` row
* Descrizione: The dedicated `stop_decisions` audit table appears to have been an early/POC persistence path (matches the 07-13/07-14 work referenced in memory as the Kimi stop-loss redesign) superseded by storing stop metadata directly on `trades`. Today's trades correctly carry stop metadata on the `trades` row itself, so this is **not a functional gap for today's stop-loss logic** — but the dormant table is a piece of schema debt that could mislead a future audit into thinking stop-decision logging stopped working.
* Impatto: None on today's correctness; risk of future confusion / wasted investigation time.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: Either resume writing to `stop_decisions` per-cycle (if it was meant to capture rejected/candidate stops, not just executed ones) or drop/document it as superseded.
* Test/monitor consigliato: None required; documentation fix (schema comment or ADR) suffices.

### [DAY-006] `score` column is semantically overloaded across `sentiment_signals`, `execution_decisions`, and `trades`

* Tipo: Ambiguità
* Area: Data
* Evidenza:
  * file/log/tabella: `sentiment_signals.score` = polarity×confidence (e.g. BA +0.523); `execution_decisions.score` / `trades.score` = **portfolio allocation weight** (e.g. BA 0.02, MU 0.0052) — a different unit entirely; the actual sentiment score for S4 trades is in `execution_decisions.signal_score`/`trades.signal_score`
* Descrizione: Cross-table queries or dashboards that naively join/compare "score" columns across these three tables will silently mix sentiment polarity×confidence with portfolio weight fractions — both are small decimals in similar ranges (e.g. 0.005–0.6), so the mistake would not be obvious from the data alone. This also affects how the "Score < 0.05 that generated orders" check (per this report's brief) must be interpreted: several BUYs today have `trades.score` of 0.005–0.02, but that is the *portfolio weight*, not a weak sentiment score — not itself an anomaly.
* Impatto: Risk of misinterpretation in ad-hoc analysis/reporting (including in this very report if not called out).
* Severità: Low
* Confidenza: High
* Azione consigliata: Rename `execution_decisions.score`/`trades.score` to `allocation_weight` (or similar) in a future migration, or at minimum document the distinction prominently next to the column.
* Test/monitor consigliato: None required beyond documentation.

---

## 11. False Positives / Areas Confirmed Correct

- **#68 reversal cooldown (S4 sentiment_reversal → any-strategy re-buy block)**: working exactly as designed. MU's re-entry fired at precisely 2h00m00s after its reversal SELL; SOXX's re-entry was delayed beyond its 2h cooldown (not a violation — cooldown is a floor, not a fixed re-entry time).
- **P0-05 pyramiding guard**: fired dozens of times today, always correctly (never blocked a legitimate first entry, never allowed a duplicate).
- **Peak-equity kill-switch (fixed 2026-07-22)**: correctly seeded and computing a sane ~0.6-1% drawdown all day; did not need to fire, and the code path (`_peak_and_drawdown`) shows the fix from the 2026-07-22 bug is still in place and functioning.
- **SKIP_STALE**: fired correctly 4 times for genuinely stale signals (>4h, one case >90h) — no stale-data trade slipped through.
- **No SELL-on-positive-sentiment (bug-A5 pattern)**: not observed — both `sentiment_reversal` SELLs (SOXX, MU) had clearly negative signal_score.
- **No roundtrip-under-30-min pathology beyond QQQ's exact-30-min flip**, which is explained (S1 weight noise, not a bug in the gating logic — see DAY note below, no separate finding filed since the underlying mechanism, S1's lack of its own re-entry cooldown, is already tracked as a config decision, `s1_reentry_cooldown_enabled: false`, not a bug).
- **Idempotency across the 16:04 restart**: confirmed via the explicit "already fired today — skipping" log line.
- **Paper/live separation**: unambiguous and correctly configured.

---

## 12. Missing / Inaccessible Data

- **Unrealized MTM attribution for the −2.9% NAV day**: no query was run to reconstruct which symbols drove the ~−$3,055 unrealized swing on 2026-07-28 close-to-close (would require Alpaca historical bar closes for all 48 positions at 07-27 close vs 07-28 close — not fetched this session).
- **Duplicate-news-weighting test**: whether the same underlying story (same `content_hash`) generated more than one `sentiment_signals` row today was not directly joined/verified.
- **`strategy_lifecycle` cross-check**: assumed S1/S4 are `approved=True`/enabled from `portfolio_cycles.strategies_run`, but the `strategy_lifecycle` table itself was not queried this session to confirm no stale/mismatched lifecycle state.
- **Root cause of SOXX's 45-min post-cooldown delay** before order submission (candidate causes: `_MIN_ORDER_NOTIONAL=$100` gate, aggregate stop-risk budget exhaustion — neither confirmed nor ruled out).
- **Root cause of DAY-002 (reuters) and DAY-004 (queued-vs-logged gap)** — flagged as questions for engineering, not resolved by log/DB inspection alone within this session's scope.

---

## 13. Immediate Recommendations

1. Fix or relabel the risk-alert drawdown metric (DAY-001) before the next time it fires — an ALERT that contradicts its own report's headline number is actively harmful to operator trust.
2. Get a same-day answer on whether the 16:04 UTC worker restart (DAY-003) was manual/expected; if not, treat as an incident.
3. Confirm with engineering whether `run_rss_ingestion_worker` is intentionally running anywhere in production (DAY-002) — if yes, fix the news_log write path; if no, find and stop whatever is invoking it, since it's polluting `ingestion_stats_daily`.

## 14. Tests / Monitors to Add

- Daily reconciliation: `fetched == queued_to_news_log + queued_to_drops + queued_rejected(reason)` per source (DAY-004).
- Alert on any source with `queued > 0` and `news_log` rows `== 0` for the same day (DAY-002).
- Consistency check across all "drawdown" fields in a single `risk_reports` row before allowing an ALERT to fire (DAY-001).
- Container-restart-during-market-hours monitor, cross-referenced against merged-commit timestamps (DAY-003).

## 15. Suggested Technical Tickets

- "Risk alert drawdown metric contradicts combined_drawdown in the same report" (DAY-001, High) — likely a re-open/escalation of the 2026-07-22 Bug Sweep finding, not a new issue.
- "Reuters RSS ingestion-stats active with 0% news_log yield" (DAY-002, Medium).
- "News funnel queued-vs-logged gap has no reconciliation instrumentation" (DAY-004, Medium).
- "Unexplained worker/worker-inference restart mid-session, no deploy correlation" (DAY-003, Low/Medium, ops-tracking only).
- "stop_decisions table dormant since 07-14 — document or resume" (DAY-005, Low).
- "score column naming collision across sentiment_signals/execution_decisions/trades" (DAY-006, Low, documentation).

## 16. System State

- **Ollama**: up all day, 0 errors/timeouts/refusals observed in `worker`/`worker-inference` logs for either `glm-5.2:cloud` or `gpt-oss:20b-cloud`. **0 hours of downtime detected.**
- **FinBERT fallback rate**: 38.7% of sentiment_signals today (84/217) — driven by per-model confidence chronically below the 0.4 eligibility threshold, not by Ollama outages.
- **Worker restart events**: `worker` + `worker-inference` restarted once, at 16:04:22 UTC (unexplained, see DAY-003); `RestartCount=0` on the container (not an auto-restart-on-crash counter increment). `beat` and `api` were not restarted today (both up since 10:45 UTC the same day, before this analysis window).
