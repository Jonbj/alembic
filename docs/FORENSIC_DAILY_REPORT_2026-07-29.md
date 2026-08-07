# Forensic Daily Report — 2026-07-29

Analyst: Autonomous forensic session (Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer)
Mode: read-only, non-interactive. No code changed, no orders sent, no worker triggered by this session.
Trading mode confirmed: **PAPER** — `portfolio_monitor_snapshots.broker_environment = 'paper'`, `mode = 'paper'` at the 20:00 UTC snapshot; `ALPACA_BASE_URL=https://paper-api.alpaca.markets` in the worker container. `execution.engine=portfolio` (the legacy path logged `{'skipped': True, 'reason': 'engine=portfolio'}` on every tick — no `legacy_sentiment` orders).
Timezone: **UTC**, explicit in `src/workers/celery_app.py:51` (`timezone="UTC"`). No ambiguity. Market hours below: pre-market <13:30 UTC, market 13:30–20:00 UTC, post-market/batch >20:00 UTC.

---

## 1. Executive Summary

The day ran mechanically clean — 24/24 portfolio cycles on cadence 14:07→19:52 with zero gaps, no worker restarts, Ollama up 100% (370 requests, 185 per model, perfect 1:1 pairing, **zero** timeouts/errors and **zero** FinBERT fallbacks), all 13 broker orders inside market hours, no duplicate orders, no same-minute races, no SELL-on-positive-sentiment, no future timestamps, clean `signal_id`→score linkage on every trade. But underneath it, **the S4 entry gate has been silently switched off since 2026-07-28 17:22:05 UTC and was off for the entire 07-29 session** (DAY-001, Critical): the Redis key `feedback:entry_threshold:S4` expired on its 96h TTL, `_get_feedback_threshold()` fell back to `S4Config.min_score` = 0.10, and the gate is guarded by `if _fb_threshold > s4_config.min_score` — `0.10 > 0.10` is False, so the filter block is skipped entirely. The constant written to prevent exactly this (`_ENTRY_THRESHOLD_BASELINE` = 0.30, `portfolio_scheduler.py:2947`) is **dead code**, referenced only by a test. Proof: `SKIP_THRESHOLD` decisions went 146 (07-27) → 250 (07-28, last row 17:22:05) → **0** (07-29), and NVDA was bought for $1,272.95 on a sentiment score of **exactly +0.100** — the model's own reasoning said the effect was "modest and not directly tied to NVIDIA's core revenue" — then sold 2h15m later on a 0.000 re-read. The designed 0.30 baseline would have rejected it. Worse, the loss-feedback worker *reports* `S4 current_threshold: 0.3` all day (it uses a different fallback), so telemetry actively conceals the disarm (DAY-006). Second live problem: **the DB and the broker disagree on 4 positions** (NOK, MRVL, INTC, WDC) because broker-side d_hard GTC stop orders filled and were never reconciled back — ~$183 of realized loss unbooked, ~$2.1K of phantom exposure on the books, and the P0-05 pyramiding guard blocking re-entry on names the book no longer holds (DAY-002). The d_hard catastrophe shadow is breaching on 5 symbols, NOK continuously for 6 days at −24% (DAY-003) — the operator's own documented revisit trigger for the disabled protective stop, with no alert wired to it. Money: NAV −$522.38 (−0.48%) to $108,916.88; realized net **−$171.81** (S1 −$131.17, S4 −$40.65), dominated by the CAT exit (−$125.94, held 15 days to −16.2%).

## 2. Verdict

**Anomalie significative.**

Rationale: this is a step down from 07-28's "OK con warning". The order flow that *did* happen was individually well-behaved, but a primary risk control — the S4 entry threshold — was **not enforced at all** for the whole session, silently, with telemetry reporting the opposite, and it will stay off indefinitely because nothing rewrites the key once the threshold sits at baseline. Only one order (NVDA) slipped through today and it happened to make $0.73, but that is luck, not correctness: a $1,273 position was opened on a signal the system was designed to reject. Combined with a 4-symbol position-accounting divergence that is silently growing and a catastrophe-stop shadow breaching unattended for 6 days, the state of the risk rails — not the trades — is what fails this day.

---

## 3. Timeline — 2026-07-29 (UTC)

| Time | Component | Event | Source |
|---|---|---|---|
| (07-28 17:22:05) | portfolio_scheduler | **Last `SKIP_THRESHOLD` row ever written.** `feedback:entry_threshold:S4` expires between 17:22 and 17:37 → S4 gate disarmed from here on | `execution_decisions` max(created_at) for SKIP_THRESHOLD |
| 00:00–13:30 | worker | Overnight batch; `SPY benchmark fetch failed` (IEX subscription) repeats — 84 lines on the day, retries never succeed | worker logs |
| 07:11:00 | ingest (reuters) | Only reuters funnel write of the day: 4 fetched / 4 queued / 1 no-ticker → **0 rows in `news_log`** (9th consecutive day at 100% loss) | `ingestion_stats_daily` |
| 13:10:06 | ingest | Earliest `published_at` among items that later landed (benzinga) | `news_log` |
| 14:00:00 | performance | `run_loss_feedback_check`: S1 stale-evidence guard skips re-ratchet; **S4 reported `current_threshold: 0.3`** (false — enforcement was 0.10/off) | worker logs |
| 14:07:00 | portfolio-cycle | Cycle #670 (S1+S4, 47 orders considered). **F BUY** (S1 momentum, wt 1.1%, $694.88). P0-05 pyramiding guard: 48 symbols already hold open DB trades | `portfolio_cycles` #670, `execution_decisions` #4814, `trades` #558 |
| 14:07:07 | portfolio-cycle | MRVL + WDC logged `SKIP_STALE` (signals 21.1h old > 4h max_age) — correct | `execution_decisions` #4812/#4813 |
| 14:15:13 | LLM | First ensemble tick of the day (glm-5.2:cloud + gpt-oss:20b-cloud) | `llm_responses` |
| 14:22:00 | portfolio-cycle | **BA SELL** (`[expired]`, signal 24.3h old, entered 07-28 @220.35) → −$37.80. **QQQ SELL** (`[s1_weight_drop]`, entered 07-28) → −$5.23 | `execution_decisions` #4815/#4816, `trades` #548/#549 |
| 14:22:07 | broker | d_hard GTC stop placed for F (43 whole shares) — fractional-stop maintenance working | `/api/orders` |
| 14:30:00 | performance | **S1 loss-feedback triggered**: EWMA R −0.53, 10 consecutive losses, rolling P&L −$188.02 → threshold 0.30→0.00, regime scale 0.20→0.20 (S1 threshold 0.0 is *intentional*, see §11) | worker logs, `feedback:state:S1` |
| 14:37:00 | portfolio-cycle | **SNOW BUY** — S4, sentiment +0.542 (conf 0.78, ensemble), wt 2.0%, $1,274.05 | #4817, `trades` #559, signal 5514 |
| 14:52:00 | portfolio-cycle | **V BUY** — S4, sentiment +0.490 (conf 0.70, ensemble), wt 2.0%, $1,270.61 | #4818, `trades` #560, signal 5517 |
| 15:07:00 | portfolio-cycle | **NVDA BUY — sentiment +0.100 (conf 0.50)**, wt 2.0%, $1,272.95. Would have been rejected by the designed 0.30 gate. **DAY-001** | #4819, `trades` #561, signal 5523 |
| 15:16 / 15:30 | LLM | Strongest signals of the day land: RIO +0.500, **F +0.600 (conf 0.80)** — both already held, correctly blocked by P0-05 | `sentiment_signals` 5537/5538 |
| 17:01:28 | LLM | NVDA re-read: score **0.000** (conf 0.20) — thesis evaporates 1h54m after entry | `sentiment_signals` 5589 |
| 17:22:00 | portfolio-cycle | **NVDA SELL** `[whipsaw]` (weight→0; `anti_whipsaw_shadow: would_suppress=True, streak=1/2` — shadow only). Held 135 min (> `hold_minimum_minutes` 90 ✓) → +$0.73 | #4820, `trades` #561 |
| 18:45:12 | LLM | CAT ensemble **−0.510** (conf 0.73) | `sentiment_signals` 5652 |
| 18:52:06 | portfolio-cycle | **CAT SELL** — `sentiment_reversal: score -0.510 < threshold -0.35`. Position open since 07-14 → **−$125.94 (−16.2%)** | #4821, `trades` #310 |
| 19:07:00 | portfolio-cycle | **V SELL** `[expired]` (signal 4.4h > 4h max_age) → −$3.58. **CAT BUY decision recorded, no order** — reversal cooldown | #4823, #4822, `trades` #560 |
| 19:07–19:52 | portfolio-cycle | CAT BUY decision re-recorded 4× (19:07/19:22/19:37/19:52), **never submitted** — #68 2h reversal cooldown holds through the close ✓ | #4822–#4826 |
| 19:45:01 | ingest | Last funnel write (benzinga 655/328, gdelt 2032/177) | `ingestion_stats_daily` |
| 19:46:16 | LLM / ingest | Last news item + last ensemble tick of the day | `news_log`, `llm_responses` |
| 19:52:00 | portfolio-cycle | Cycle #693 — last of the day, no gaps in the 15-min grid | `portfolio_cycles` |
| 20:00:00 | market close | Snapshot: NAV $108,916.88, prev close $109,439.26, **change −$522.38**, unrealized −$153.00, exposure 28.36%, drawdown 1.09%, 47 open positions, `broker_environment=paper` | `portfolio_monitor_snapshots` |
| 20:00:00 | ingest/cycle | Ingest + cycle correctly self-skip with `reason: market_closed` | worker logs |
| 22:00:17 | performance | Forward-return worker: 1053 signals, updated 940, skipped_no_data 113, **errors 0** | worker logs |
| 22:30:01 | risk_monitor | Risk report #47: NAV 108,936.35, `combined_drawdown` **1.24%**, HHI 0.024, exposure 28.37% — but `per_strategy.portfolio.drawdown` **13.2%** → `RISK ALERT` fired. **DAY-004** (recurrence, escalated from 10.3%) | `risk_reports` #47 |
| 22:45:00 | performance | Counterfactual worker: **"No SKIP decisions pending"**, 0 processed — because the gate produced no SKIP_THRESHOLD rows. Downstream symptom of DAY-001 | worker logs |

---

## 4. News Ingest

### By source

| Source | Fetched | Queued | Duplicates | No-ticker | Stale | Parse fail | In `news_log` | Explicit drops (`news_queue_drops`, avg age) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gdelt_gkg | 2,032 | 177 | 64 | 1,839 | 0 | 0 | 105 | 61 (12.89h) |
| alpaca_benzinga | 655 | 328 | 2,978 | 0 | 0 | 0 | 80 | 197 (8.82h) |
| reuters | 4 | 4 | 0 | 1 | 0 | 0 | **0** | 0 |

Coverage: `news_log.created_at` spans **14:15:13 → 19:46:16 UTC only**. Ingest tasks self-skip with `reason: market_closed` outside the session, so overnight and pre-market news is structurally never ingested (DAY-011 — design limitation, not a fault).

Quality checks on the 185 ingested rows:
- **Future timestamps: 0.** All `published_at <= created_at`.
- **NULL tickers: 0.** `extraction_method` populated on 100% of rows (gdelt → `org_lookup` ×105, benzinga → `source_metadata` ×80), so QT-03 attribution is intact.
- **Ticker ambiguity: none found.** Spot-checked the top 12 tickers — all unambiguous large-caps, no `$cashtag`-dependent short/common-word symbols in the set.
- **Duplicates inside `news_log`: 1** — gdelt `MS`, identical `content_hash` ingested twice 4.5h apart (15:15:14 and 19:45:32). See DAY-007. The 80 benzinga rows from 34 distinct URLs and 105 gdelt rows from 78 URLs are *not* duplicates — they are the by-design one-row-per-ticker fan-out of multi-ticker articles.

### Top tickers by news volume

| Ticker | News | Ticker | News |
|---|---:|---|---:|
| MU | 20 | AMD | 7 |
| MS | 18 | DB | 7 |
| GS | 14 | AMZN | 6 |
| TSM | 8 | META | 6 |
| MSFT | 8 | GOOGL | 5 |
| NVDA | 8 | INFY | 5 |

### Top news by impact on the day's signal

| Item | Effect |
|---|---|
| SNOW analyst upgrade ("expected revenue lift from AI and increased customer spend") | +0.542 → BUY $1,274.05 |
| V — JP Morgan PT $400→$450 | +0.490 → BUY $1,270.61 |
| NVDA — Corning partnership ("modest and not directly tied to NVIDIA's core revenue") | **+0.100 → BUY $1,272.95** (DAY-001) |
| CAT — bearish item at 18:45 | −0.510 → forced `sentiment_reversal` exit, −$125.94 |
| F +0.600 (conf 0.80, strongest of day), RIO +0.500, WDC +0.520 | No S4 order — all already held, P0-05 blocked ✓ |

Problems found: reuters 100% loss (DAY-005), funnel↔`news_log`↔drops not reconcilable (DAY-009), 1 dedup miss (DAY-007).
Confidence in this section: **High** for what landed in `news_log`; **Low** for the fetched→queued funnel, which has no per-item audit trail.

---

## 5. LLM Model Performance

| Model | Requests | Errors | Timeouts | Invalid/refusal | `eligible=True` | Mean polarity | SD polarity | Mean confidence | Min/Max conf | conf ≥ 0.40 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| glm-5.2:cloud | 185 | 0 | 0 | 0 | 20 (10.8%) | −0.0108 | 0.2065 | **0.2422** | 0.05 / 0.95 | 25 (13.5%) |
| gpt-oss:20b-cloud | 185 | 0 | 0 | 0 | 20 (10.8%) | +0.0044 | 0.2236 | **0.3884** | 0.10 / 0.90 | 80 (43.2%) |

Perfect 1:1 pairing (185/185), first tick 14:15:13, last 19:46:16 — **Ollama up for 100% of the session, zero downtime.**

### Aggregation outcome (185 `sentiment_signals`)

| `model_id` | Count | Share | `fallback_used` | Mean \|score\| | Mean confidence | Mean ensemble_std | Max ensemble_std |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 120 | 64.9% | 0 | 0.0558 | 0.2863 | 0.0517 | 0.3889 |
| `single:gpt-oss:20b-cloud` | 60 | 32.4% | 60 | 0.1000 | 0.4950 | 0.0000 | — |
| `single:glm-5.2:cloud` | 5 | 2.7% | 5 | 0.1280 | 0.7700 | 0.0000 | — |
| `finbert` | **0** | 0.0% | — | — | — | — | — |

**Degraded-ensemble rate: 65/185 = 35.1%** (07-28: 37.8%). **FinBERT fallback rate: 0.0%** — no true deterministic fallback was needed all day. The degradation is not an availability problem: both models answered every time, but one of the two fell below the `ENSEMBLE_MIN_CONFIDENCE` 0.40 eligibility bar, collapsing the pair to a single read. glm-5.2's mean confidence of 0.24 is the structural driver (only 13.5% of its reads clear 0.40) — the same chronic quality issue carried in memory since the 06-29 pair swap, unchanged.

Score extremes and disagreement: strongest bull F +0.600, strongest bear PG −0.568. Highest ensemble divergence: ERIC `ensemble_std` 0.3889 on a −0.268 score (a genuine directional split that still produced a tradeable-looking number); MU flipped +0.420 (16:46, single:glm) → −0.360 (17:31, single:gpt-oss) within 45 minutes on two different single-model reads.

### Functional verification

| Question | Answer | Evidence |
|---|---|---|
| Is LLM output validated before entering the signal store? | **Yes** — structured JSON/function-calling parse, `polarity × confidence` scoring, eligibility gate at 0.40, `force_ineligible=result.fallback_used` | `src/workers/sentiment.py:572-576` |
| Does the ensemble handle high variance? | **Partially** — `ensemble_std` is computed and persisted, and a sub-2-model aggregate is tagged `single:` with `fallback_used=True` and gated downstream; but there is no *variance* threshold that discards a high-`std` ensemble read (ERIC at 0.389 was kept) | `_label_from_model_count`, `sentiment.py:215-236` |
| Do duplicate news weigh more than once? | **Yes, once today** — the gdelt MS duplicate produced 2 independent signals from 1 article (DAY-007) |`news_log`, `sentiment_signals` |
| Can one news item generate multiple signals? | **Yes, by design** — one row (and one signal) per resolved ticker on a multi-ticker article. Correct for a per-symbol signal store | `news_log` 80 rows / 34 URLs |
| Does low confidence actually reduce weight? | **Yes** — `score = polarity × confidence`; NVDA's 0.50 confidence halved a 0.20 polarity to 0.100 | `sentiment_signals` 5523 |
| Are models called offline / out of the trading loop? | **Yes** — all inference on the `inference` queue in `worker-inference`; the scheduler reads persisted rows only. No LLM call inside a cycle | `celery_app.py`, cycle logs |
| Can a hallucination reach a trading decision directly? | **Yes, materially more so today.** The 0.30 entry gate is the main dilution against a single bad read, and it was off (DAY-001). NVDA is the concrete instance: one ensemble read at +0.100 → a $1,273 order, no second confirmation required | DAY-001 |

---

## 6. Signals → Decisions

15 `execution_decisions` (8 BUY, 5 SELL, 2 SKIP_STALE, **0 SKIP_THRESHOLD**). 24 cycles ran `["S1","S4"]`, orders_count 47–50 per cycle, `constraints_fired: []` on every single cycle.

| Symbol | Signal id | Score | Conf | Model | Decision | Strategy | Outcome |
|---|---:|---:|---:|---|---|---|---|
| SNOW | 5514 | +0.543 | 0.78 | ensemble | BUY 14:37 | S4 | Submitted, filled |
| V | 5517 | +0.490 | 0.70 | ensemble | BUY 14:52 | S4 | Submitted, filled |
| NVDA | 5523 | **+0.100** | 0.50 | ensemble | BUY 15:07 | S4 | Submitted, filled — **should have been gated** |
| F | — | +0.0109 (wt) | — | S1 momentum | BUY 14:07 | S1 | Submitted, filled |
| CAT | — | +0.0117–0.0120 (wt) | — | S1 momentum | BUY ×4 19:07–19:52 | S1 | **Correctly not submitted** (reversal cooldown) |
| BA | — | — | — | — | SELL 14:22 | S4 | `[expired]` age 24.3h |
| QQQ | — | — | — | — | SELL 14:22 | S1 | `[s1_weight_drop]` |
| NVDA | — | 0.000 (5589) | 0.20 | ensemble | SELL 17:22 | S4 | `[whipsaw]`, shadow would_suppress=True |
| CAT | 5652 | −0.510 | 0.73 | ensemble | SELL 18:52 | S1 | `sentiment_reversal` < −0.35 |
| V | — | — | — | — | SELL 19:07 | S4 | `[expired]` age 4.4h |
| MRVL | — | −0.320 | — | — | SKIP_STALE 14:07 | — | 21.1h > 4h ✓ |
| WDC | — | −0.240 | — | — | SKIP_STALE 14:07 | — | 21.1h > 4h ✓ |

Controls applied / not applied:
- **Portfolio combiner: applied.** Both sleeves merged every cycle; `regime_mult` 0.7 (`regime:current` = sideways, VIX 18.21) on all decisions.
- **Entry threshold gate: NOT APPLIED** — zero SKIP_THRESHOLD rows, see DAY-001.
- **Pyramiding guard (P0-05): applied**, 48 symbols blocked at 14:07 (but see DAY-002 — 4 of those 48 are stale DB state).
- **Signal-age gate: applied** (2 SKIP_STALE, plus `[expired]` exits at 4h/24.3h).
- **Reversal cooldown (#68): applied** — CAT BUY suppressed 4 consecutive cycles.
- **Hold minimum (90 min) / exit persistence (2 cycles): respected** — NVDA held 135 min, SELL at the 2nd cycle after weight→0.
- **Circuit breaker / kill-switch: armed and correctly quiet.** `portfolio:peak_equity` 110,113.93 vs value 108,969.76 → 1.04% drawdown vs 5% cap. `system:halted_by_operator` absent. No operator halt.
- **Sector cap / exposure limits: not fired** (`constraints_fired: []` on all 24 cycles; exposure 28.4% vs ceiling).
- **Paper/live separation: unambiguous** — `broker_environment='paper'` persisted on every snapshot.

---

## 7. Orders Generated / Executed

All 13 broker orders, all within 14:07–19:07 UTC (inside market hours). Fills were near-instant (1–3s).

| # | Submitted | Symbol | Side | Qty | Fill px | Status | Strategy | Signal | Decision | Trade | Rationale |
|---|---|---|---|---:|---:|---|---|---|---|---|---|
| 1 | 14:07:07 | F | buy | 43.375156 | 16.02 | filled 14:07:08 | S1 | — | 4814 | 558 | momentum, wt 1.1% |
| 2 | 14:22:06 | BA | sell | 5.687120 | 213.82 | filled 14:22:07 | S4 | 5293 | 4537 | 548 | signal expired 24.3h |
| 3 | 14:22:06 | QQQ | sell | 1.091318 | 669.99 | filled 14:22:07 | S1 | — | 4577 | 549 | S1 weight → 0% |
| 4 | 14:22:07 | F | sell | **43** | — | **new (GTC stop)** | — | — | — | — | d_hard fractional stop |
| 5 | 14:37:08 | SNOW | buy | 4.485425 | 284.04 | filled 14:37:10 | S4 | 5514 | 4817 | 559 | sentiment +0.542 |
| 6 | 14:52:08 | V | buy | 3.436655 | 369.72 | filled 14:52:09 | S4 | 5517 | 4818 | 560 | sentiment +0.490 |
| 7 | 14:52:08 | SNOW | sell | **4** | — | **new (GTC stop)** | — | — | — | — | d_hard fractional stop |
| 8 | 15:07:07 | NVDA | buy | 6.603040 | 192.780913 | filled 15:07:08 | S4 | 5523 | 4819 | 561 | sentiment **+0.100** |
| 9 | 15:07:07 | V | sell | 3 | — | canceled | — | — | — | — | stop canceled before real SELL ✓ |
| 10 | 15:22:05 | NVDA | sell | 6 | — | canceled | — | — | — | — | stop canceled before real SELL ✓ |
| 11 | 17:22:05 | NVDA | sell | 6.603040 | 192.93 | filled 17:22:08 | S4 | 5523 | 4819 | 561 | whipsaw, weight → 0 |
| 12 | 18:52:07 | CAT | sell | 0.821012 | 792.256 | filled 18:52:07 | S1 | — | 2808 | 310 | sentiment_reversal −0.510 |
| 13 | 19:07:11 | V | sell | 3.436655 | 368.88 | filled 19:07:13 | S4 | 5517 | 4818 | 560 | signal expired 4.4h |

Anomalies in this table: none internally. No rejects, no partial fills, no duplicate order ids, no two orders in the same minute for the same symbol, no order without a decision row. The two `canceled` stop orders (#9, #10) are the **cancel-before-sell fix (#66 / PR #69) working correctly** — the GTC stop is pulled before the real SELL goes out, preventing the July-16 regression where GTC stops blocked scheduler SELLs.

Orders generated but **not** submitted: CAT BUY ×4 (19:07, 19:22, 19:37, 19:52) — correctly suppressed by the 2h reversal cooldown that started at 18:52 and would not expire until 20:52, after the close. Correct, and the decision rows make it auditable.

---

## 8. P&L / Return

### Account level (from `portfolio_monitor_snapshots`, 20:00 UTC = market close)

| Metric | Value |
|---|---:|
| NAV at close | $108,916.88 |
| Previous close equity | $109,439.26 |
| **NAV change on the day** | **−$522.38 (−0.48%)** |
| Cash | $78,034.39 |
| Gross exposure | 28.36% |
| Unrealized P&L (open book) | −$153.00 |
| Current drawdown | 1.09% (limit 5%) |
| Open positions | 47 |

### Realized, by strategy (`trades` with `exit_time` on 07-29)

| Strategy | Trades closed | Gross P&L | Net P&L | Slippage est. | Costs |
|---|---:|---:|---:|---:|---:|
| S1 | 2 | −$130.61 | **−$131.17** | $0.56 | $0.56 |
| S4 | 3 | −$39.01 | **−$40.65** | $1.64 | $1.64 |
| **Total** | **5** | **−$169.62** | **−$171.81** | **$2.20** | **$2.20** |

Entry-side costs on the 4 new positions: $1.98. Total explicit trading cost for the day: **$4.18** (~1.7–5.3 bps per trade — immaterial). No commissions modelled beyond `cost_usd`; regulatory cost fields are NULL.

### Realized, by ticker

| Ticker | Strategy | Entered | Exited | Entry px | Exit px | Qty | Net P&L | Exit reason | Opened |
|---|---|---|---|---:|---:|---:|---:|---|---|
| CAT | S1 | 2026-07-14 | 07-29 18:52 | 945.138 | 792.256 | 0.821012 | **−$125.94** | sentiment_reversal | before 07-29 |
| BA | S4 | 2026-07-28 | 07-29 14:22 | 220.345275 | 213.82 | 5.687120 | −$37.80 | signal expired | before 07-29 |
| QQQ | S1 | 2026-07-28 | 07-29 14:22 | 674.652 | 669.99 | 1.091318 | −$5.23 | S1 weight drop | before 07-29 |
| V | S4 | 07-29 14:52 | 07-29 19:07 | 369.72 | 368.88 | 3.436655 | −$3.58 | signal expired | **on 07-29** |
| NVDA | S4 | 07-29 15:07 | 07-29 17:22 | 192.780913 | 192.93 | 6.603040 | **+$0.73** | whipsaw | **on 07-29** |

- **P&L from positions opened before 07-29: −$168.96** (CAT + BA + QQQ) — 98.3% of the day's realized loss, and CAT alone is 73%.
- **P&L from positions opened on 07-29: −$2.85** (V + NVDA, both same-day round trips).
- **Unrealized on positions still open from 07-29 entries:** F and SNOW remain open; their marks are not pinned to the 07-29 close in any table (see §12).

Split realized (−$171.81) vs NAV change (−$522.38): the residual −$350.57 is mark-to-market on the 45 positions carried through the day. The 22:30 risk report's `daily_pnl` of **−$3,525.53** is inconsistent with both figures and is not usable — see DAY-004.

Slippage: $2.20 total across 5 exits, computed as `slippage_est` at submit-vs-fill. Fill latency 1–3s on every order; no adverse-selection signal.

---

## 9. Buy/Sell Correctness Analysis

| Check | Result | Evidence |
|---|---|---|
| BUY only when permitted | **FAIL (1 case)** | NVDA at +0.100 passed a gate that should have been 0.30 — DAY-001 |
| SELL/exit generated correctly | PASS | 5 exits, each with a distinct, logged mechanism (`expired`, `s1_weight_drop`, `whipsaw`, `sentiment_reversal`) |
| Stop-loss respected | **N/A by design** | protective stop is `stop_loss: 0.0` per the 2026-07-15 operator decision. But the documented revisit trigger is now met — DAY-003 |
| Signal flip respected | PASS | CAT −0.510 forced an immediate exit at the very next cycle |
| Max holding / signal age respected | PASS | BA cut at 24.3h, V at 4.4h, MRVL/WDC skipped at 21.1h — all against `max_signal_age_hours: 4` |
| Rebalance band respected | PASS | `constraints_fired: []`, no band breach on any of 24 cycles |
| No duplicate orders | PASS | 13 distinct order ids, no repeats |
| No opposing orders in the same window without rationale | PASS | NVDA buy 15:07 → sell 17:22 (135 min) and V buy 14:52 → sell 19:07 (255 min); both > 90 min hold minimum, both with a logged reason. No <30 min round trip |
| No orders on disallowed tickers | PASS | All 6 traded symbols in the tradable universe |
| No orders outside hours | PASS | All 13 between 14:07 and 19:07 UTC |
| No trade on stale data | PASS | Stale signals produced SKIP_STALE / `[expired]`, never an entry |
| No trade on invalid LLM output | PASS | Every trade's `signal_id` resolves to a persisted, parsed, non-fallback ensemble signal |
| No trade while circuit breaker active | PASS | Breaker never tripped (1.04% vs 5%) |
| No trade on a disabled strategy | PASS | Only S1 + S4 ran, both approved |
| Paper/live coherent | PASS | `broker_environment='paper'` on every snapshot |
| Celery retry idempotency | PASS | No duplicate order id, no double-fire; dedup is DB-backed |
| Order ↔ fill ↔ position reconciliation | **FAIL** | 4 symbols diverge between `trades` and the broker — DAY-002 |
| Pyramiding (>3 BUY without SELL) | PASS | Guard fired for 48 symbols; no symbol bought twice |
| SELL on positive sentiment (bug A5) | PASS | Every SELL had a non-positive or absent signal |
| `fallback_used=True` across all symbols (Ollama down) | PASS | 0% FinBERT; Ollama up all session |
| NO-ORDER (decision without order) | Expected only | CAT ×4, each explained by the reversal cooldown |
| Score < 0.05 generating an order | PASS | Lowest S4 score traded was 0.100 |
| Identical orders in the same minute (race) | PASS | None |

---

## 10. Anomalies Found

### [DAY-001] S4 entry-threshold gate silently disabled since 2026-07-28 17:22 UTC — off for the entire 07-29 session

* Tipo: **Bug**
* Area: Signal / Risk / Orders
* Evidenza:
  * file/log/tabella: `src/workers/portfolio_scheduler.py:1277-1299` (`_get_feedback_threshold`), `:2932-2947` (`_load_entry_threshold_baseline` / `_ENTRY_THRESHOLD_BASELINE`), `:3230` (gate condition); `execution_decisions`; Redis `feedback:entry_threshold:S4`
  * timestamp: gate last enforced `2026-07-28 17:22:05 UTC`; absent for all 24 cycles of 2026-07-29; still absent at the time of this report
  * snippet/query:
    ```
    -- last SKIP_THRESHOLD row ever written:
    SELECT max(created_at) FROM execution_decisions WHERE decision='SKIP_THRESHOLD';
    --> 2026-07-28 17:22:05.51589+00

    -- SKIP_THRESHOLD by day:  07-27: 146   07-28: 250   07-29: 0

    -- key is gone:
    redis-cli EXISTS feedback:entry_threshold:S4   --> 0
    redis-cli EXISTS feedback:entry_threshold      --> 0   (legacy bare key)

    -- the fallback:
    return _S4Cfg().min_score          # = 0.10
    -- the gate:
    if _fb_threshold is not None and _fb_threshold > s4_config.min_score:   # 0.10 > 0.10 -> False
    -- the floor that was supposed to prevent this, never referenced in production:
    grep -rn "_ENTRY_THRESHOLD_BASELINE" src/  --> only its own definition (line 2947)
    ```
* Descrizione: `feedback:entry_threshold:S4` carries a 96h TTL (`feedback_ttl_hours: 96`). It is only ever *rewritten* by a loss-feedback ratchet, recovery, or decay event. Once the S4 threshold settles back at baseline no branch rewrites it, so the key eventually expires on its own. When it does, `_get_feedback_threshold()` falls through the per-strategy key, then the legacy bare key, and returns `S4Config.min_score = 0.10`. The gate is then guarded by a strict `>` against that same 0.10, so the whole filter block — including the `SKIP_THRESHOLD` audit rows — is skipped. The result is not "gate at 0.10"; it is **no gate at all**, with only the ranker's own 0.10 prefilter left standing. Commit `b2c0f54` ("order-gate floor at baseline 0.30") added `_ENTRY_THRESHOLD_BASELINE = 0.30` with a docstring stating it exists "so the gate never drops to the min_score prefilter (0.10) and let weak signals trade" — but never wired it into `_get_feedback_threshold`. The only reference is `tests/workers/test_gate_drop_logging.py:139`, which asserts the constant's *value*, so the test suite is green while the protection does nothing.
* Impatto: the primary dilution control between a single LLM read and a live order is absent. Today it admitted one order: NVDA, $1,272.95 at sentiment +0.100 (conf 0.50) — a read whose own reasoning called the effect "modest and not directly tied to NVIDIA's core revenue" — which the designed 0.30 baseline would have rejected. It was flat-to-positive (+$0.73) purely by luck and was closed 2h15m later on a 0.000 re-read. The condition is **not self-healing**: it persists until the next S4 loss ratchet happens to rewrite the key. Every S4 signal ≥ 0.10 is currently tradeable, which is roughly a 3× widening of the intended entry funnel. Secondary damage: no `SKIP_THRESHOLD` rows means the Decision Log no longer explains no-trade cycles, and the 22:45 counterfactual worker reported "No SKIP decisions pending" — the measurement loop that would have detected this is starved by the same bug.
* Severità: **Critical**
* Confidenza: **High** (root cause reproduced end-to-end from code, Redis state, and the exact `SKIP_THRESHOLD` cutover timestamp)
* Azione consigliata: ticket — (a) apply `max(threshold_from_redis_or_default, _ENTRY_THRESHOLD_BASELINE)` in `_get_feedback_threshold` so an absent/expired key floors at 0.30 instead of 0.10; (b) change the gate guard from `>` to `>=` (or drop the comparison and always filter) so a threshold equal to `min_score` still filters and still writes audit rows; (c) have the loss-feedback worker refresh the key's TTL on every run even when the value is unchanged, so absence becomes a genuine anomaly rather than routine; (d) decide whether an absent key should hard-fail the S4 sleeve rather than fall back silently.
* Test/monitor consigliato: unit test asserting `_get_feedback_threshold` returns ≥ 0.30 with an empty Redis; unit test asserting a signal at exactly `min_score` is dropped; **alert if a market-hours cycle produces zero `SKIP_THRESHOLD` rows for N consecutive cycles**; alert if `feedback:entry_threshold:<S>` is missing during market hours.

### [DAY-002] `trades` and broker disagree on 4 positions — d_hard stop fills never reconciled

* Tipo: **Bug**
* Area: Broker / PnL / Data
* Evidenza:
  * file/log/tabella: `trades` (`exit_time IS NULL`) vs `/api/positions` (Alpaca truth, `src/api/routes/trading.py:30`); `/api/orders`
  * timestamp: oldest divergence 2026-07-16 19:48:19 (NOK); most recent 2026-07-28 13:58:03 (INTC) — i.e. it grew again the day before this report
  * snippet/query:
    ```
    SYM     DB_qty        BRK_qty       DIFF        unbooked stop fill
    NOK     41.563993     0.563993      41.000000   41 sh @ 10.31  2026-07-16 19:48:19  (entry 11.72)
    INTC     3.894841     0.894841       3.000000    3 sh @ 84.857 2026-07-28 13:58:03  (entry 95.95)
    WDC      2.981065     0.334697       2.646368    1 sh @ 482.81 2026-07-27 14:30:29  (entry 549.24) + 2 partials
    MRVL     1.551547     0.551547       1.000000    1 sh @ 195.18 2026-07-20 14:50:01  (entry 221.914)
    ```
    Every one of these fills carries `trade_id = None` and `origin_strategy = None` in `/api/orders` — they were placed by the fractional-stop maintainer (`src/portfolio/fractional_stop_orders.py`, `ALPACA_FRACTIONAL_STOP_ENABLED` default true), filled at the broker, and nothing wrote back to `trades`.
* Descrizione: the d_hard disaster stop is enforced as a real broker GTC sell for `floor(qty)` whole shares (Alpaca rejects brackets on fractional quantities). When one of those stops fills, the position is reduced at the broker but the corresponding `trades` row is left with `exit_time IS NULL` and its original full `qty`. What remains is a fractional "zombie stub" — NOK is now **0.564 shares worth $5.01** while the DB still models it as a 41.56-share, ~$370 position.
* Impatto: three concrete failures. (1) **Unbooked realized loss ≈ −$183** (NOK −$57.81, WDC −$66.43, INTC −$33.28, MRVL −$26.73, net of two small WDC partials) never attributed to S1/S4 — which means the loss-feedback ratchet, the LOO-ICIR weights, and every P&L-by-strategy table are computed on incomplete data. (2) **~$2,099 of phantom exposure** in DB-derived views (~1.9% of NAV, ~6.7% of the $31.2K book). (3) **The P0-05 pyramiding guard reads DB open trades** — at 14:07 it blocked BUY decisions for NOK, MRVL, INTC and WDC as "already has an open trade" when the book is effectively flat in those names, so the stale state is actively suppressing legitimate re-entries.
* Severità: **High**
* Confidenza: **High** (exact per-share arithmetic reconciles the divergence to a specific fill in every one of the 4 cases)
* Azione consigliata: ticket — extend the fill-reconciliation worker to match broker fills with no `trade_id` against open `trades` rows by symbol, book a partial exit (or close + reopen the stub), and attribute the P&L to the originating strategy. Backfill the 4 known cases. Separately decide the policy for sub-1-share stubs (auto-liquidate vs carry).
* Test/monitor consigliato: a daily reconciliation job asserting `sum(trades.qty WHERE exit_time IS NULL) == broker qty` per symbol, alerting on any non-zero delta; alert on any broker fill that cannot be matched to a `decision_id`.

### [DAY-003] d_hard catastrophe shadow breaching on 5 symbols — the operator's own revisit trigger for the disabled stop is met, unattended

* Tipo: **Rischio**
* Area: Risk
* Evidenza:
  * file/log/tabella: `stop_shadow_log` (`d_hard_breached`), `config/trading.yaml:172-182`, `/api/positions`
  * timestamp: NOK breaching continuously since 2026-07-24 14:07; MRVL and AMAT since 2026-07-28; AMD and CAT from 2026-07-29 14:07
  * snippet/query:
    ```
    SELECT symbol,count(*),min(cycle_ts),max(cycle_ts) FROM stop_shadow_log WHERE d_hard_breached GROUP BY 1;
     NOK  | 96 | 2026-07-24 14:07 | 2026-07-29 19:52
     MRVL | 43 | 2026-07-28 14:07 | 2026-07-29 19:52
     AMAT | 32 | 2026-07-28 14:22 | 2026-07-29 19:52
     AMD  | 21 | 2026-07-29 14:07 | 2026-07-29 19:52
     CAT  | 20 | 2026-07-29 14:07 | 2026-07-29 18:52
    ```
    Current unrealized: NOK −24.15%, MRVL −22.27%, AMAT −20.67%, AMD −18.16%. CAT exited today at −16.2%.
* Descrizione: `config/trading.yaml:180-181` states the condition for revisiting the 2026-07-15 decision to disable the protective stop verbatim: *"Revisit: if any position rides past -15/20% (d_hard shadow), wire d_hard to a real broker order (catastrophe-only), NOT the 2% noise stop."* Four positions are past −18%, one past −24%, and NOK has been in continuous breach for six consecutive trading days. The shadow table records all of it, but **nothing reads `d_hard_breached`** — grep shows the column is written by `portfolio_scheduler.py:1272` and consumed by no alert, no report, and no dashboard. CAT's −$125.94 exit today came from a `sentiment_reversal` that happened to arrive, not from any risk control.
* Impatto: the disable-the-stop decision was explicitly conditional on observing this signal, and the signal has fired without anyone being told. The book is carrying four positions in catastrophe territory with no floor under them. Note the interaction with DAY-002: the *broker-side* d_hard stops that did fire (NOK, MRVL, INTC) are the reason those names are effectively flat despite the DB — so the actual protection in force is inconsistent and invisible from either side.
* Severità: **High**
* Confidenza: **High** for the data; **Medium** on the remediation, which is a product decision, not a code fix.
* Azione consigliata: escalate to the operator as a decision item — the pre-agreed revisit trigger is met. Do not change stop config autonomously. In the meantime, wire an alert on `d_hard_breached`.
* Test/monitor consigliato: daily alert listing every position with `d_hard_breached=True` and its worst adverse excursion; add a "positions past −15%" tile to the risk dashboard.

### [DAY-004] Risk report drawdown metric divergent and escalating — ALERT fires on a number nothing else agrees with

* Tipo: **Bug**
* Area: Risk / Ops
* Evidenza:
  * file/log/tabella: `risk_reports` #46/#47, worker log 22:30:01
  * timestamp: 2026-07-29 22:30:01 UTC
  * snippet/query:
    ```
    RISK ALERT: Strategy portfolio drawdown 13.2% exceeds 10%
    Risk report stored (id=47): combined_dd=1.24% HHI=0.024 alerts=1
    per_strategy_metrics.portfolio: {drawdown: 0.1324, daily_pnl: -3525.53, sharpe: -5.32}
    -- same report's own combined_drawdown: 0.012429
    -- kill-switch truth: peak 110113.93 vs value 108969.76 -> 1.04%
    -- actual NAV move on the day: -522.38
    ```
* Descrizione: recurrence of DAY-001 from the 2026-07-28 report, escalated: the per-strategy `drawdown` field reads 13.2% (was 10.3% yesterday) while the same report's `combined_drawdown` says 1.24% and the real-time equity kill-switch measures 1.04%. The companion `daily_pnl` of −$3,525.53 contradicts the measured NAV change of −$522.38 by a factor of ~6.8. Three different drawdown numbers and two different daily-P&L numbers coexist in one system.
* Impatto: informational only — this metric gates nothing and the real kill-switch is correctly seeded and correctly quiet. But an ALERT-level line that is wrong by an order of magnitude and drifting worse each day trains operators to ignore the risk channel, which is exactly when a real breach gets missed.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — reconcile the per-strategy drawdown/`daily_pnl` computation against NAV history; until fixed, suppress the ALERT or relabel it as unvalidated telemetry.
* Test/monitor consigliato: assertion test that `per_strategy.portfolio.daily_pnl` matches `nav − previous_close_equity` within tolerance; same for drawdown vs `combined_drawdown`.

### [DAY-005] Reuters ingestion at 100% loss for a 9th consecutive day, plus a volume collapse

* Tipo: **Bug**
* Area: News / Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, `news_log`
  * timestamp: 2026-07-29 07:11:00 (only funnel write of the day)
  * snippet/query:
    ```
    SELECT day,fetched,queued,discarded_no_ticker FROM ingestion_stats_daily WHERE source='reuters';
     07-29 |  4 |  4 | 1     07-28 | 48 | 48 | 12    07-27 | 36 | 36 | 9
     07-26 | 16 | 16 | 4     07-25 | 24 | 24 | 6     07-23 |  4 |  4 | 1
     07-22 | 32 | 32 | 8     07-21 |  4 |  4 | 1
    SELECT count(*) FROM news_log WHERE source ILIKE '%reuters%';  --> 0  (all time)
    ```
* Descrizione: carried forward from the 07-28 report (DAY-002 there) and still unaddressed. A reuters funnel row is written daily, reporting items fetched and queued, yet **not one reuters row has ever reached `news_log`** — the count is zero over the entire table history. `RSS_INGESTION_ENABLED` is unset in the worker container (defaults off). New today: the volume dropped from 48 to 4 and the single write landed at 07:11 UTC, well outside the market-hours ingest window that governs the other two sources — suggesting an orphaned or externally-triggered task rather than the scheduled pipeline.
* Impatto: no trading impact (the items never enter the signal path), but the ingestion dashboard reports a source as live that contributes nothing, inflating perceived news coverage and hiding whichever step discards 100% of the output.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — identify what schedules the reuters task with `RSS_INGESTION_ENABLED` off, and either wire the source through to `news_log` or remove it from the funnel so the stats stop reporting a phantom source.
* Test/monitor consigliato: alert when a source reports `queued > 0` for a day but contributes 0 rows to `news_log`.

### [DAY-006] Loss-feedback telemetry reports an S4 threshold of 0.30 that is not the one being enforced

* Tipo: **Bug**
* Area: Ops / Signal
* Evidenza:
  * file/log/tabella: `src/workers/performance.py:1898` vs `src/workers/portfolio_scheduler.py:1298-1299`; worker logs, every 30 min on 07-29
  * timestamp: all day, e.g. `2026-07-29 14:00:00,024` and 21:30
  * snippet/query:
    ```
    # performance.py — reports 0.30 when the key is absent:
    current_threshold = redis.get_feedback_entry_threshold(strategy=strategy) or cfg["threshold_baseline"]   # -> 0.30
    # portfolio_scheduler.py — enforces 0.10 when the same key is absent:
    return _S4Cfg().min_score                                                                                # -> 0.10
    # observed log, every run: 'S4': {... 'current_threshold': 0.3 ...}
    ```
    Note the `or` also makes a legitimately stored `0.0` indistinguishable from an absent key in the telemetry path.
* Descrizione: the two components resolve a missing threshold key to different values. The loss-feedback worker's own telemetry — the thing an operator would consult — asserted `current_threshold: 0.3` on every one of its ~16 runs on 07-29, while the order gate was running at 0.10 and effectively disabled.
* Impatto: this is *why* DAY-001 went unnoticed for a day and a half. The observability surface confirms the control is healthy while it is off. Any monitor built on this field would have stayed green.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: fold into the DAY-001 ticket — extract a single shared resolver for the effective threshold and have both the gate and the telemetry call it; replace the `or` with an explicit `is None` check.
* Test/monitor consigliato: test asserting the enforced threshold and the reported threshold are equal for absent-key, zero-value, and set-value cases.

### [DAY-007] Content-hash dedup miss — one gdelt article scored twice

* Tipo: **Anomalia**
* Area: News
* Evidenza:
  * file/log/tabella: `news_log`
  * timestamp: 2026-07-29 15:15:14 and 19:45:32 (4h30m apart)
  * snippet/query:
    ```
    source=gdelt_gkg ticker=MS content_hash=76d265f5...4eae  count=2
    title: "AI compute demand set to exceed supply; US-China policy moves may bifurcate global market: Report"
    ```
* Descrizione: identical `content_hash` **and** identical ticker ingested twice, 4.5h apart — a genuine dedup escape, not the by-design one-row-per-ticker fan-out (which produces distinct tickers for the same hash). The item was scored twice and contributed two independent rows to MS's signal history. It is the only such case in the day's 185 rows.
* Impatto: minimal today (MS was not traded), but a re-ingested article double-counts in any per-symbol signal aggregation. The 4.5h gap suggests the dedup window is shorter than the source's own republication interval.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: ticket — check whether the content-hash dedup has a lookback window and widen it, or enforce a uniqueness constraint on `(content_hash, ticker)`.
* Test/monitor consigliato: daily count of `(content_hash, ticker)` groups with `count > 1`, alert above zero.

### [DAY-008] High confidence on zero-polarity reads

* Tipo: **Anomalia**
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals`
  * timestamp: 2026-07-29 18:00:09
  * snippet/query:
    ```
    id=5624 NVDA score=0.000 confidence=0.90 model=single:glm-5.2:cloud
    id=5589 NVDA score=0.000 confidence=0.20 model=ensemble
    id=5650 NVDA score=0.000 confidence=0.20 model=ensemble
    ```
* Descrizione: a model returned confidence 0.90 on a reading with zero directional content, while two ensemble reads on the same symbol the same afternoon returned confidence 0.20 for the same zero polarity. Since `score = polarity × confidence`, a zero polarity nulls the score either way, so nothing propagates — but the confidence field is not measuring the same thing across reads. It also matters that `eligible` and the degraded-ensemble decision are driven by that same confidence: a confidently-neutral read can win eligibility over a hesitant directional one.
* Impatto: none today. Relevant to the ongoing confidence-calibration question — glm-5.2's mean confidence is 0.24 with a 0.05–0.95 range, and this shows the tail is not well-anchored to content.
* Severità: **Low**
* Confidenza: **Medium**
* Azione consigliata: fold into the QX-01 calibration work — include confidence-vs-content coherence in the golden-label evaluation.
* Test/monitor consigliato: track the distribution of confidence conditional on `|polarity| < 0.05`.

### [DAY-009] Ingest funnel does not reconcile with `news_log` or the drop table

* Tipo: **Ambiguità**
* Area: News / Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` vs `news_log` vs `news_queue_drops`
  * timestamp: 2026-07-29 full day
  * snippet/query:
    ```
    benzinga: queued 328 | news_log 80 | explicit drops 197  -> 51 unaccounted
    gdelt:    queued 177 | news_log 105 | explicit drops  61  -> 11 unaccounted
    ```
* Descrizione: same gap as flagged on 07-28 (DAY-004 there), smaller in absolute terms. 62 items were queued and neither landed nor were recorded as dropped. Note this is measured against a `news_log` count that is itself for `created_at::date`, so a small part of the gap may be a boundary effect at the 19:46 cutoff.
* Impatto: the ingest funnel cannot be audited end-to-end; silent losses are indistinguishable from timing effects.
* Severità: **Low**
* Confidenza: **Medium**
* Azione consigliata: ticket — make every queued item terminate in exactly one recorded outcome (ingested / dropped with reason).
* Test/monitor consigliato: daily assertion `queued == ingested + dropped + carried_over`.

### [DAY-010] SPY benchmark fetch fails on a tight retry loop and never succeeds

* Tipo: **Anomalia**
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: worker logs
  * timestamp: throughout 2026-07-29 (84 lines)
  * snippet/query: `SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}` — bursts of 6 identical retries within ~2 seconds, repeating per minute in the overnight window
* Descrizione: known IEX/SIP subscription limitation, but the caller retries 6× in quick succession against an error that is permanent by nature, then repeats on the next tick. It never succeeds.
* Impatto: no trading impact; benchmark comparisons on the dashboard fall back to null. Log noise and pointless API calls against the rate budget.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: don't retry on a subscription-class error; cache the negative result for the day and log once.
* Test/monitor consigliato: none needed beyond a log-volume check.

### [DAY-011] News ingest runs only during market hours — no pre-market or overnight coverage

* Tipo: **Ambiguità**
* Area: News
* Evidenza:
  * file/log/tabella: worker logs, `news_log`
  * timestamp: `2026-07-29 20:00:00,418` — `run_news_ingestion_worker succeeded: {'skipped': True, 'reason': 'market_closed'}`; `news_log` spans 14:15:13–19:46:16 only
  * snippet/query: both `run_news_ingestion_worker` and `run_alpaca_ingestion_worker` self-skip on `market_closed`
* Descrizione: earnings releases, overnight wire items and pre-market moves are never ingested. By the time the first cycle runs at 14:07, the day's overnight news flow has been skipped entirely, and the 4h `max_signal_age_hours` means anything from before ~10:00 UTC could not be traded anyway.
* Impatto: a structural ceiling on S4's opportunity set rather than a fault. Worth stating explicitly because the S4 signal drought is repeatedly analysed without this constraint being named.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: none as a bug. Flag as an input to the S4 alpha discussion — pre-market ingestion with a session-open decision point is a design change, not a fix.
* Test/monitor consigliato: n/a.

### [DAY-012] Gap in the `trades` id sequence (553–557)

* Tipo: **Anomalia**
* Area: Data
* Evidenza:
  * file/log/tabella: `trades`
  * timestamp: between 2026-07-28 19:07 (id 552) and 2026-07-29 14:07 (id 558)
  * snippet/query: `SELECT id FROM trades WHERE id BETWEEN 553 AND 557;` → 0 rows
* Descrizione: five ids consumed with no surviving row. Postgres sequences are non-transactional, so a rolled-back insert consumes an id — this is the expected explanation and there is no evidence of data loss (order counts, fills and positions all reconcile for the period). Recorded for completeness only.
* Impatto: none identified.
* Severità: **Low**
* Confidenza: **Medium** (benign cause is likely but not positively proven)
* Azione consigliata: none unless a pattern emerges.
* Test/monitor consigliato: n/a.

---

## 11. False Positives and Areas Verified Correct

Things that looked wrong and are not:

1. **Zero `stop_loss` exits since 2026-07-14 is not a broken stop engine.** `config/trading.yaml:182` sets `stop_loss: 0.0` and `stop_loss_mode: fixed`, and `_stop_loss_breached_symbols` returns `{}` under exactly that combination — a deliberate 2026-07-15 operator decision backed by an OOS replay (no_protective −$56 vs fixed_2pct −$419). The absence is the design. (What *is* actionable is the revisit trigger — DAY-003.)
2. **`feedback:entry_threshold:S1 = 0.0` is intentional**, not a corrupted ratchet: `performance.py:1937-1938` forces `new_threshold = 0.0` for S1 with the comment "S1 has no discrete entry-threshold gate; persist state only." The order gate only ever reads the S4 key.
3. **#68 reversal cooldown works exactly as specified.** CAT was force-exited at 18:52 on a −0.510 reversal; the S1 momentum BUY decision then re-appeared at 19:07, 19:22, 19:37 and 19:52 and was suppressed every time, with each suppression written to `execution_decisions` for audit. No re-buy leaked.
4. **Cancel-before-sell (#66 / PR #69) works.** The V and NVDA GTC stop orders were canceled ahead of their real SELLs (15:07 and 15:22), so no stop order blocked a scheduler exit — the July-16 P0 regression did not recur.
5. **P0-05 pyramiding guard fired correctly**, blocking 48 symbols at 14:07. No symbol was bought twice; no BUY-BUY-BUY sequence anywhere.
6. **No `signal_id` ↔ score desync (#59).** Every trade's `signal_id` resolves to a `sentiment_signals` row whose score matches the decision score to 3 decimals (5514→+0.543, 5517→+0.490, 5523→+0.100, 5652→−0.510).
7. **No SELL on positive sentiment (bug A5).** All five exits had a non-positive or absent signal.
8. **Ollama fully healthy.** 370 requests, 185 per model, perfect pairing, zero errors, zero timeouts, zero FinBERT fallbacks. The 35.1% degraded-ensemble rate is a confidence-calibration issue, not availability.
9. **Cycle cadence perfect.** 24 cycles on the exact 15-minute grid from 14:07:00 to 19:52:00, no gaps, no double-fires, `constraints_fired: []` throughout.
10. **Kill-switch correctly seeded and correctly silent.** `portfolio:peak_equity` present at 110,113.93 (the 2026-07-22 initialization bug has not regressed), drawdown 1.04% vs the 5% cap.
11. **No worker restarts, no operator halt.** Last container start 2026-07-28 16:04:22, `RestartCount=0` on all containers, `system:halted_by_operator` absent.
12. **Batch jobs all clean**: forward returns 940 updated / 113 no-data / **0 errors**; risk report stored; counterfactual worker ran (with nothing to do — itself a DAY-001 symptom).
13. **No orders outside market hours, no duplicate orders, no same-minute races, no round trip under 30 minutes, no order with a score below 0.05.**

---

## 12. Missing or Inaccessible Data

| Gap | Consequence | Query/change that would close it |
|---|---|---|
| No LLM latency field | Per-model latency could not be reported (§5 shows request counts and error rates only) | Add `latency_ms` to `llm_responses`; today only `generated_at` exists |
| No per-signal raw model outputs for degraded reads | Cannot tell whether the 65 `single:` reads were near-miss or far-miss on the 0.40 eligibility bar | `llm_shadow_responses` exists but is not populated for this path |
| No end-of-day mark per position | Unrealized P&L per ticker for 07-29 is not recoverable; `/api/positions` returns **live** marks (fetched 2026-07-30 12:30 UTC), not the 07-29 close. Only the account-level aggregate (−$153.00 at 20:00) is pinned to the day | Persist a per-symbol close snapshot alongside `portfolio_monitor_snapshots` |
| `performance_metrics` table is empty (0 rows, all time) | No stored per-strategy return series; strategy attribution had to be recomputed from `trades` | Populate or remove |
| `stop_decisions` empty since 2026-07-14 17:52 | No stop-decision metadata (vol_at_entry / σ / k / trigger) for any position opened since — the Gap D noted in the 07-11 attribution audit | Expected while the protective stop is disabled; `stop_shadow_log` is the live substitute |
| Ingest funnel has no per-item audit | 62 queued items unaccounted (DAY-009) | Per-item outcome logging |
| Commission/regulatory cost fields NULL | Cost analysis limited to `cost_usd` / `slippage_est` | Populate `regulatory_cost_usd` from broker data |

---

## 13. Immediate Recommendations

1. **Restore the S4 entry gate today** (DAY-001). This is the only item that changes what the system will trade tomorrow morning. The minimal safe intervention is to re-set `feedback:entry_threshold:S4` to `0.30` in Redis, which restores enforcement immediately without a deploy — but it will expire again in 96h, so it is a stopgap, not the fix. **This session did not apply it** (read-only mandate); it needs an operator decision.
2. **Ship the floor fix and the `>`/`>=` fix together** (DAY-001 + DAY-006), with the shared-resolver refactor so telemetry can never again disagree with enforcement.
3. **Escalate DAY-003 to the operator as a decision, not a ticket.** The revisit trigger written into `config/trading.yaml` on 2026-07-15 has been met by four positions. The decision (wire d_hard as a real catastrophe stop, or accept the exposure explicitly) belongs to the PO.
4. **Backfill and then automate the 4-symbol reconciliation** (DAY-002) before any strategy-attribution or loss-feedback conclusion is drawn from `trades` — roughly $183 of realized loss is currently invisible to the ratchet that is supposed to learn from it.
5. **Silence or fix the risk-report drawdown ALERT** (DAY-004) before it desensitises the channel further; it has now fired two days running with a number nothing else in the system agrees with.

## 14. Tests and Monitors to Add

| # | Monitor / test | Catches |
|---|---|---|
| M-1 | Alert if a market-hours cycle writes **zero `SKIP_THRESHOLD` rows** for N consecutive cycles | DAY-001, the exact signature that would have caught this on 07-28 |
| M-2 | Alert if `feedback:entry_threshold:<strategy>` is missing during market hours | DAY-001 root cause |
| T-1 | Unit test: `_get_feedback_threshold` returns ≥ `threshold_baseline` with empty Redis | DAY-001 (a) |
| T-2 | Unit test: a signal at exactly `min_score` is dropped and produces a `SKIP_THRESHOLD` row | DAY-001 (b) |
| T-3 | Unit test: enforced threshold == reported threshold for absent / zero / set key | DAY-006 |
| M-3 | Daily reconciliation: per-symbol `sum(trades.qty WHERE exit_time IS NULL)` vs broker qty, alert on any delta | DAY-002 |
| M-4 | Alert on any broker fill with no matching `decision_id` | DAY-002 |
| M-5 | Daily alert listing positions with `d_hard_breached=True` and worst adverse excursion | DAY-003 |
| T-4 | Assertion: `per_strategy.portfolio.daily_pnl` ≈ `nav − previous_close_equity` | DAY-004 |
| M-6 | Alert when a source reports `queued > 0` but contributes 0 rows to `news_log` | DAY-005 |
| M-7 | Daily count of `(content_hash, ticker)` groups with `count > 1` | DAY-007 |
| M-8 | Track confidence distribution conditional on `|polarity| < 0.05` | DAY-008 |

## 15. Suggested Technical Tickets

| Ticket | Title | Severity | Findings |
|---|---|---|---|
| T-01 | S4 entry gate silently disarms on Redis key expiry; `_ENTRY_THRESHOLD_BASELINE` floor is dead code | Critical | DAY-001, DAY-006 |
| T-02 | Reconcile broker d_hard stop fills back into `trades`; backfill NOK/MRVL/INTC/WDC | High | DAY-002 |
| T-03 | Wire an alert on `stop_shadow_log.d_hard_breached`; escalate the disabled-stop revisit trigger to the PO | High | DAY-003 |
| T-04 | Risk report `per_strategy.drawdown` / `daily_pnl` diverge from NAV — fix or suppress the ALERT | Medium | DAY-004 |
| T-05 | Reuters source reports queued items but contributes zero rows to `news_log` (9 days) | Medium | DAY-005 |
| T-06 | Content-hash dedup escape on republished articles | Low | DAY-007 |
| T-07 | Make the ingest funnel reconcile end-to-end (every queued item gets one recorded outcome) | Low | DAY-009 |
| T-08 | Stop retrying SPY benchmark fetch on a permanent subscription error | Low | DAY-010 |
| T-09 | Add `latency_ms` to `llm_responses`; persist a per-symbol EOD mark | Low | §12 |

## 16. System Status

| Item | Status |
|---|---|
| **Ollama** | **Up 100%** of the session. 370 requests (185 glm-5.2:cloud + 185 gpt-oss:20b-cloud, perfect 1:1), first 14:15:13, last 19:46:16. **0 errors, 0 timeouts, 0 refusals. Downtime: 0h00m.** |
| **FinBERT fallback rate** | **0.0%** (0 of 185 signals). No true deterministic fallback was needed. |
| **Degraded-ensemble rate** | **35.1%** (65 of 185 tagged `single:`) — driven by glm-5.2's mean confidence of 0.242 against the 0.40 eligibility bar, not by availability. 07-28 was 37.8%. |
| **Active model pair** | `config:sentiment_llm_models = glm52,gptoss` — correct, no reset to "all". |
| **Worker restarts** | **None on 07-29.** All containers started 2026-07-28 (worker + worker-inference 16:04:22, api + beat + frontend 10:45:56), `RestartCount=0` across the board. postgres and redis up 8 days. |
| **Operator halt** | None. `system:halted_by_operator` absent; only `system:mode` present. |
| **Kill-switch** | Armed and quiet. Peak equity $110,113.93, value $108,969.76 → 1.04% drawdown vs 5% cap. |
| **Regime** | `sideways`, multiplier 0.7, VIX 18.21, no LLM disagreement. |
| **Celery beat** | Healthy — 24/24 portfolio cycles, ingest + execution self-skipping correctly on `market_closed`, all evening batch jobs ran on schedule. |
| **Broker environment** | **paper** (confirmed on every `portfolio_monitor_snapshots` row). |
| **Entry gate** | ⚠️ **DISABLED** since 2026-07-28 17:22:05 UTC — see DAY-001. Still disabled at the time of writing. |
