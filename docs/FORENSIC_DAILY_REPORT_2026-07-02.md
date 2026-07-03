# Forensic Daily Report — 2026-07-02

**Analyst:** Autonomous forensic session (Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Ops Reviewer)
**Scope:** end-to-end pipeline for 2026-07-02, UTC. Read-only. No code, DB, or broker state modified.
**Generated:** 2026-07-03

---

## 1. Executive Summary

News ingest → LLM sentiment → S1/S4 decisions → portfolio-cycle orders → Alpaca paper fills → positions worked correctly and idempotently on 2026-07-02: 127 news items ingested (4 sources), 127 sentiment signals generated, 4 orders (3 BUY + 1 SELL) submitted and filled 1:1, 3 positions still open, 1 trade closed for +$83.96 net. No duplicate orders, no pyramiding, no out-of-hours trading, no broker rejects, execution strictly paper (`paper-api.alpaca.markets`, `GLOBAL_LIVE_PROMOTION_ENABLED=False`). The single SELL was a correct, signal-expiry-driven exit, not the historical "SELL with positive sentiment" bug (already fixed 2026-06-29).

However, three structural problems surfaced that outrank the "everything worked" headline. **Critical:** a SanDisk (SNDK) news article was mistagged to AAPL by the source-metadata extraction path and produced a real, stored -0.485 sentiment signal for Apple — the deterministic resolver correctly flagged it `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` but that verdict does not gate the live signal store (enforcement is intentionally not yet on, per QX-01), so the bad signal was only kept out of a trade by an unrelated threshold filter. **High:** the daily risk report has fired the identical "exposure 100% exceeds 50%" ALERT on all 10 of the last 10 days because `total_exposure` is a hardcoded placeholder (`= 1.0`) rather than a computed value — the alert is permanently miscalibrated and cannot detect a real breach. **High:** Docker logs for the target date are unrecoverable — all four relevant containers were recreated at 2026-07-03 09:57 UTC, wiping stdout/stderr history, so error/exception evidence for 07-02 depends entirely on what made it into Postgres.

Additional notable finding: FinBERT fallback fired on 101/127 (79.5%) of signals on 07-02, driven entirely by ensemble divergence (std > 0.30) between the two Ollama models, not by timeouts or budget exhaustion — Ollama was up all day. This raises a real question about how much of the "LLM ensemble" is actually load-bearing versus FinBERT doing the work.

## 2. Verdict

**OK con warning.**

The pipeline executed correctly end-to-end for every trade that happened on 07-02 (auditable, idempotent, paper-only, no order/fill/position mismatches). The warning-level verdict is driven by: (a) a live demonstration of the exact ticker-misattribution risk the architecture doc calls "the worst-case error," currently caught only by luck/threshold coincidence, not by design; (b) a risk-monitoring alert that has cried wolf on every single day it has run, meaning it provides no real signal; and (c) a total loss of Docker log history for the audited date, which limits independent verification of anything not captured in Postgres.

---

## 3. Timeline — 2026-07-02 (UTC)

All timestamps UTC. Celery (`timezone="UTC", enable_utc=True`) and Postgres (`TimeZone=UTC`, all columns `TIMESTAMPTZ`) agree — **no storage-level timezone ambiguity**. See §16 for a *schedule*-level DST ambiguity that does not affect timestamp interpretation but does affect *when* the pipeline runs relative to actual NYSE hours.

| Time (UTC) | Component | Event | Source |
|---|---|---|---|
| 00:00–13:59 | Ingest | **No activity** — sentiment-worker/ingestion crontab is `*/15 14-21 Mon-Fri`; nothing scheduled before 14:00 UTC | `celery_app.py:66-72` |
| 14:00–14:18 | Ingest | First batch of the day: 92 `alpaca_benzinga`, 20 `gdelt_gkg`, 14 `marketaux`, 1 `cnbc` items fetched over the day, front-loaded — 9 alpaca_benzinga + 6 marketaux land in the 14:00 hour alone, sweeping the overnight backlog (avg. published→fetched lag 4h19m for alpaca_benzinga, up to 7h29m) | `news_log` |
| 14:02:21 | LLM | First `sentiment_signals` row of the day (AAPL, fallback, low confidence 0.058) | `sentiment_signals id=1573` |
| 14:07:07 | Decision | First portfolio-cycle tick; `portfolio_cycles id=257`, strategies_run=["S1","S4"], 0 orders | `portfolio_cycles` |
| 14:16–14:18 | News/Signal | 3-way fan-out of one MarketAux "SanDisk price prediction" article to AVGO/WDC/MU (`news_log id=1576-1578`) — vendor multi-tagging, not a pipeline dedup failure | `news_log` |
| 14:22:01 | Decision→Order | `execution_decisions id=825`: **SELL NKE** — "S4 signal expired (age=19.3h > max_age=4h, generated 2026-07-01 19:02 UTC, score=+0.387): weight 0.0% — no counter-signal found, position closed." Order `960a5751…` submitted 14:22:07.56, filled 14:22:08.29 @ $43.98 | `execution_decisions`, `orders`, `trades id=230` |
| 16:45:56 | LLM | AAPL signal `id=1619`, score -0.21, non-fallback (ensemble, std within bounds) — genuine ensemble output, distinct from the mistagged item below | `sentiment_signals` |
| 16:52–19:52 | Decision | AAPL evaluated 13 times, `SKIP_THRESHOLD` every time (aggregated signal_score oscillating -0.168/-0.21, never crosses ±0.30 feedback threshold) | `execution_decisions` |
| 17:45:19 | **News/Signal — anomaly** | `news_log id=1632` "Why Is Sandisk Stock Falling on Thursday?" ingested with **ticker=AAPL** (body is 100% about SanDisk/SNDK, no Apple content). Same article re-ingested 19s later correctly tagged `SNDK` (`id=1633`). Produces `sentiment_signals id=1632`: AAPL, score **-0.4851**, confidence 0.615, fallback (ensemble divergence) | `news_log`, `sentiment_signals` — see **[DAY-001]** |
| 19:16:56 | LLM | META signal `id=1658`, score +0.475 ("Meta's Cloud Plans") | `sentiment_signals` |
| 19:22:00 | Decision→Order | `execution_decisions id=1138/1139`: **BUY META** (+0.475, 5.0% weight) and **BUY NOW** (+0.354, 5.0% weight), both from `portfolio_cycles id=278` (orders_count=2). Orders submitted 19:22:08.8/.98, filled 19:22:11.2/11.6 | `execution_decisions`, `orders`, `trades id=231,232` |
| 19:46:11 | LLM | MU signal `id=1665`, score +0.404 ("Apple hardware price hikes → benefits Micron ASPs") | `sentiment_signals` |
| 19:52:00 | Decision→Order | `execution_decisions id=1166`: **BUY MU** (+0.404, 3.3% weight), `portfolio_cycles id=280` (orders_count=3). Order submitted 19:52:06.6, filled 19:52:06.6 | `execution_decisions`, `orders`, `trades id=233` |
| 19:52:06 | Decision | Last execution_decisions row of the day (id=1155, AAPL SKIP_THRESHOLD) | `execution_decisions` |
| 21:47:14 | Ingest | Last `news_log` row of the day (SOXX, alpaca_benzinga) — matches the `14-21` crontab upper bound | `news_log` |
| 22:00 | Worker | `forward-return-worker` scheduled (populates `sentiment_signals.forward_return`) — not independently verified this session (no direct query run) | `celery_app.py:74-78` |
| 22:30:00.02 | Risk | `risk_reports id=19` stored: nav=-578.52 (see §8/§16 for what this field actually means), total_exposure=1.000 (hardcoded placeholder), alert "Total portfolio exposure 100.0% exceeds 50%" — **identical alert fired on all 10 prior days sampled** | `risk_reports` — see **[DAY-003]** |
| — | Ops | **No `ingestion_stats_daily` rows exist for any date** (table has 0 rows total) — this planned per-source funnel table is unwired | `ingestion_stats_daily` — see **[DAY-006]** |
| — | Ops | Docker logs for worker/worker-inference/beat/api on 07-02 are **unrecoverable**: all 4 containers show `RestartCount=0`, `StartedAt=2026-07-03T09:57:22Z` — recreated this morning, prior stdout/stderr lost | `docker inspect` — see **[DAY-004]** |

## 4. News Ingest — Table by Source (2026-07-02)

| Source | Items | Discarded | Extraction method | Publish→Fetch lag (min/avg/max) | Notes |
|---|---:|---:|---|---|---|
| alpaca_benzinga | 92 | 0 | `source_metadata` | 00:30 / 04:19 / 07:29 | Dominant source; includes the AAPL/SanDisk mistag (id 1632) |
| gdelt_gkg | 20 | 0 | `org_lookup` | 04:17 / 05:13 / 06:02 | |
| marketaux | 14 | 0 | `source_metadata` | 05:34 / 06:25 / 07:19 | Disabled the following day (2026-07-03, FIX-01: 17-day evidence 0/20 winners) — still live on the audited date |
| cnbc (RSS) | 1 | 0 | `regex` | 05:16 | Disabled the following day (2026-07-03, FIX-02: 0 rows in 17 days) — still live on the audited date |
| **Total** | **127** | **0** | | | |

**Table by ticker (top 10 by signal count):** derivable from `sentiment_signals` — 89 distinct symbols received at least one signal; no single symbol dominated (max ~4-5 signals/symbol/day for the most newsworthy names). Full per-symbol breakdown available via `SELECT symbol, count(*) FROM sentiment_signals WHERE generated_at::date='2026-07-02' GROUP BY symbol ORDER BY 2 DESC` — not reproduced in full here for space.

**Top news by signal impact (|score| ranked):**

| Symbol | Score | Confidence | Fallback | Title | Source |
|---|---:|---:|---|---|---|
| RIVN | +0.641 | 0.825 | No | "Rivian Automotive, Tenax Therapeutics, Robinhood And Other Big Stocks Moving Higher On Thursday" | alpaca_benzinga |
| MS | +0.563 | 0.681 | Yes | "Corteva (NYSE:CTVA) Stock Price Expected to Rise, Mizuho Analyst Says" | gdelt_gkg |
| AAPL | +0.520 | 0.643 | Yes | "What's Behind Apple's Hardware Price Hikes as Memory Supplies Tighten?" | alpaca_benzinga |
| **AAPL** | **-0.485** | **0.615** | **Yes** | **"Why Is Sandisk Stock Falling on Thursday?" — mistagged, see [DAY-001]** | alpaca_benzinga |
| META | +0.475 | 0.700 | No | "Report On Meta's Cloud Plans Lifts Investor Sentiment" | alpaca_benzinga |
| IWM | -0.439 | 0.650 | No | "The Upside-Down Market: Why Small-Caps Are a Valuation Trap" | alpaca_benzinga |
| MU | +0.404 | 0.675 | No | "What's Behind Apple's Hardware Price Hikes…" (same event as AAPL, cross-tagged via gdelt_gkg org_lookup) | gdelt_gkg |
| NOW | +0.354 | 0.675 | No | "The Dow Just Had Its Best First Half Since 2021, but This Jobs Number Is Flashing Yellow" | marketaux |

**Problems found:** 1 ticker-misattribution ([DAY-001], Critical), 1 vendor multi-tagging fan-out of a single story to 3-5 tickers (AVGO/WDC/MU/AAPL/SNDK for the SanDisk story cluster — legitimate per-source behavior, not a pipeline bug, but inflates apparent "independent" news count). No stale news, no future-timestamped news, no missing required fields, no silent parse failures observed. `content_hash` is 0/127 populated for the day (0/1264 populated ever — see [DAY-006] area) so cross-source dedup cannot be measured directly; the live path relies on Redis TTL dedup (ephemeral, not queryable retroactively) plus a DB `UNIQUE(url, ticker)` backstop (0 constraint violations observed).

**Confidence:** High for counts/timestamps (direct DB query). Medium for "duplicates removed" (not measurable — see §12 missing data).

## 5. LLM Model Performance (2026-07-02)

| Model | Requests | Eligible (conf≥0.4) | Avg polarity | Avg confidence | Notes |
|---|---:|---:|---:|---:|---|
| kimi-k2.6:cloud | 26 | 24 (92%) | +0.100 | 0.508 | |
| glm-5.2:cloud | 26 | 20 (77%) | +0.171 | 0.519 | |
| FinBERT (fallback) | 101 signals | — | — | — | Fired on 101/127 (79.5%) of signals, **100% via "ensemble divergence" (std>0.30)**, 0% via "Ollama timeout", 0% via "budget exhausted" |

- **Successes/errors/timeouts:** 52 `llm_responses` rows (26×2 models) = ensemble ran fully for 26 news items; no timeout-reasoned fallback recorded anywhere on 07-02 → **Ollama was reachable and responsive all day**.
- **Latency:** not measurable — `llm_responses` stores no request/response duration column, and per-request timing would only exist in application logs, which are unrecoverable for 07-02 (see §12).
- **Score distribution** (`sentiment_signals`, all 127 rows, ensemble + fallback combined): min -0.485, max +0.641, mean +0.093, std of `ensemble_std` for non-fallback signals: 0.000–0.283 (avg 0.064) — i.e. the signals that *did* pass the divergence gate had tight agreement; the 101 that fell into fallback are exactly the ones where the two models disagreed sharply.
- **Budget:** `llm_budget` for 07-02: $0.053 spent, 15,736 input / 2,556 output tokens, `budget_exhausted=false`. Budget was never a factor.
- **Validation before signal store:** yes — `eligible` flag (confidence≥0.4) is recorded per model response, and the aggregator only trusts non-fallback ensemble output when `ensemble_std ≤ 0.30`; anything else routes to FinBERT. This worked exactly as designed on 07-02 — the finding is not that fallback fired, but that it fired on 4 out of 5 items (see [DAY-002]).
- **Duplicate news → duplicate signals?** No — `sentiment_signals` has `UNIQUE(symbol, generated_at)`, and 1:1 news→signal was observed (127 news, 127 signals, matching `news_log_id` FKs). The SanDisk-story fan-out (5 near-identical articles → 5 separate signals, different tickers) is the closest thing to "one event, multiple signals" and is a source-tagging artifact, not a pipeline duplication bug.
- **Confidence properly reduces weight?** Yes — `score = polarity × confidence` is applied consistently (verified via spot-check, e.g. AAPL id=1632: reasoning-implied polarity ≈ -0.79 × confidence 0.615 ≈ -0.485, matches stored score).
- **Offline/background only?** Confirmed — LLM calls happen exclusively inside `run_sentiment_worker` (Celery `inference` queue, concurrency=1, isolated from the order-submission path in `portfolio_scheduler.py`). No LLM call sits in the hot trading loop.
- **Hallucination risk reaching trading decisions directly?** Yes, demonstrated in practice by [DAY-001] — a fabricated-by-mistagging (not hallucinated by the LLM itself; the LLM correctly summarized the Sandisk article, the *ticker* was wrong before the LLM ever saw it) negative score reached the signal store and nearly reached a decision. The LLM's own reasoning was accurate for the text it was given; the failure is upstream (ticker attribution), not an LLM hallucination per se — but the net effect on the signal store is the same class of risk the architecture doc's hallucination-mitigation section is meant to cover.

**Confidence:** High for counts (direct queries). N/A for latency (unmeasurable).

## 6. Signals — Final Per-Ticker (2026-07-02, BUY/SELL-relevant only)

| Symbol | Signal score (causing) | Confidence | Decision | Order | Fill |
|---|---:|---:|---|---|---|
| NKE | +0.387 (generated 07-01 19:02, expired by 07-02 14:22) | 0.625 | SELL (signal-expiry, not sentiment reversal) | `960a5751…` | $43.98, 14:22:08 |
| META | +0.475 | 0.700 | BUY (5.0% weight) | `d6eb018d…` | $585.868, 19:22:11 |
| NOW | +0.354 | 0.675 | BUY (5.0% weight) | `fbfaa82f…` | $106.719, 19:22:11 |
| MU | +0.404 | 0.675 | BUY (3.3% weight) | `8c6548ef…` | $964.306, 19:52:06 |
| AAPL | -0.21 / -0.168 (blended, incl. the mistagged -0.485 item) | mixed | SKIP_THRESHOLD ×13 | none | none |

All other 84 symbols that received a signal on 07-02 were evaluated and skipped (`SKIP_THRESHOLD` — score below the 0.30 feedback threshold, or `SKIP_STALE` — signal older than `max_signal_age_hours=4`). No signal above threshold failed to produce a decision, and no decision was produced without a qualifying signal.

## 7. Orders Generated / Executed (2026-07-02)

| Order ID | Symbol | Side | Decision ID | Signal ID | Submitted | Filled | Fill price | Notional | Status | Engine |
|---|---|---|---:|---:|---|---|---:|---:|---|---|
| `960a5751-86ee-…` | NKE | SELL | 825 | 1526 | 14:22:07.556 | 14:22:08.291 | $43.98 | $2,418.62 (qty 54.994) | filled | portfolio (paper) |
| `d6eb018d-4ef2-…` | META | BUY | 1138 | 1658 | 19:22:08.782 | 19:22:11.214 | $585.868 | $2,358.10 (qty 4.025) | filled | portfolio (paper) |
| `fbfaa82f-2130-…` | NOW | BUY | 1139 | 1655 | 19:22:08.975 | 19:22:11.631 | $106.719 | $2,358.10 (qty 22.096) | filled | portfolio (paper) |
| `8c6548ef-b034-…` | MU | BUY | 1166 | 1665 | 19:52:06.608 | 19:52:06.619 | $964.306 | $1,578.97 (qty 1.637) | filled | portfolio (paper) |

- **Broker:** Alpaca **paper** (`ALPACA_BASE_URL=https://paper-api.alpaca.markets`, `ALPACA_PAPER_MODE` default true, `GLOBAL_LIVE_PROMOTION_ENABLED=False` hardcoded in `src/strategies/promotion.py:27`). Confirmed both at the config-default level and via the running container's actual env var.
- **Engine:** `config/trading.yaml: execution.engine=portfolio` → only `portfolio_scheduler.py` submits orders. `execution.py` (legacy) task still runs on its own crontab entry but is a self-gated no-op ("execution.engine=%s — legacy execution worker inactive").
- **Fill rate:** 4/4 (100%), all filled within 5 seconds of submission, no partial fills, no rejects, no cancellations.
- **Risk checks applied:** all 4 orders passed the `ConstraintEnforcer` chain (single-asset ≤10% NAV, per-strategy exposure, portfolio ≤50% NAV, sector ≤25%, correlation cluster) — none of the 4 individually exceeded any cap (weights 3.3–5.0%). No `constraints_fired` entries logged in any of the day's 24 `portfolio_cycles` rows.
- **No duplicate orders, no same-minute race-condition duplicates** (checked full order history, not just 07-02: 0 symbol+side+minute collisions).

## 8. PnL / Rendimento (2026-07-02)

| Category | Value | Source | Caveats |
|---|---:|---|---|
| Realized PnL, trades **closed on 07-02** | **+$83.96 net** (NKE; gross $85.27, costs $1.31) | `trades id=230` | 1 trade |
| Realized PnL, trades opened before 07-02 and closed on 07-02 | +$83.96 (same NKE trade — opened 07-01) | `trades id=230` | This is the *only* realized PnL event of the day |
| Realized PnL, trades opened AND closed on 07-02 | $0.00 (none — the 3 buys opened 07-02 are still open) | `trades` | — |
| Unrealized PnL, open positions (as of query time, 07-03) | META -$11.94, MU +$18.43, NOW -$8.82 → **net -$2.34** | live `/api/positions` (Alpaca) | This is a *current* snapshot (07-03), not a 07-02 EOD mark — no 07-02 EOD position-value snapshot exists in the DB (positions are not persisted, only fetched live from Alpaca; see discovery §10) |
| "Daily return" (`portfolio_daily_state` view, 2026-07-02) | +3.60% | view over `trades` grouped by `exit_time::date` | **Caveat:** this view derives `daily_return`/`net_pnl` purely from trades whose `exit_time` falls on that date (here, the single NKE trade) — it does **not** mark open positions to market and does **not** represent whole-portfolio daily return. On a day with 1 closed trade, "daily_return" is really "that one trade's return," not the fund's. |
| `risk_reports.nav` (2026-07-02, stored 22:30 UTC) | -578.52 | `risk_reports id=19` | **Not actual account NAV** — computed as `sum(net_pnl)` over a rolling 60-day window from `portfolio_daily_state` (comment in code: *"Approximate NAV from cumulative net_pnl (no cash tracking in DB yet)"*). Mislabeled field; do not read as broker equity. See [DAY-005]. |
| Slippage (est.) | $1.31 (NKE, `slippage_est`) | `trades` | Populated only for NKE (the closed trade); open trades have no exit slippage yet by definition |
| Commissions/costs | NKE: cost_bps 5.34, cost_usd $1.31, spread_cost_bps 5.0, impact_cost_bps 0.34, regulatory_cost_usd $0.063 | `trades` | Full tiered cost model populated for the one closed trade; not applicable to open trades |

**Missing data:** true portfolio-level daily return (mark-to-market of open + closed) is not computable from stored data — there is no EOD positions-with-price snapshot table (see discovery §10/§11). Would require: a scheduled job to snapshot `get_all_positions()` + market close prices into a new table, or reconstructing from Alpaca's own daily portfolio-history endpoint (not queried this session — out of read-only DB/log scope as given).

## 9. Buy/Sell Functional Correctness

| Check | Result | Evidence |
|---|---|---|
| BUY generated only when signal > threshold | ✅ Pass | All 3 BUYs had `abs(signal_score) ≥ 0.35`, well above the 0.30 feedback threshold |
| SELL/exit generated correctly | ✅ Pass | NKE sold on signal-expiry (19.3h > 4h max_age), correct per S4 rules, no counter-signal existed |
| Stop-loss respected | N/A this date | No stop-loss exits occurred 07-02 |
| Signal flip respected | ✅ Pass (n/a triggered) | No signal-reversal exit occurred 07-02; the one SELL was expiry-based, not flip-based |
| Max holding days / signal max-age (4h) respected | ✅ Pass | NKE closed specifically *because* it breached max_age |
| Rebalance band / hold-minimum (90 min anti-churn) respected | ✅ Pass | NKE was held 19h15m (07-01 19:07 → 07-02 14:22), far above the 90-min floor; no other exits this date |
| No duplicate orders | ✅ Pass | 0 collisions checked across full history |
| No contrary orders same interval without rationale | ✅ Pass | Every BUY/SELL decision row has a populated `reason` field with signal attribution |
| No orders on disallowed tickers | ✅ Pass (not independently cross-checked against full watchlist file, but all 4 traded symbols — NKE, META, NOW, MU — appear in `config/trading.yaml` universe context seen) | |
| No out-of-hours orders | ✅ Pass | All fills between 14:22–19:52 UTC (10:22am–3:52pm EDT), inside NYSE hours |
| No trade on stale data | ✅ Pass | Freshness gate (`max_signal_age_hours=4`) actively enforced — proven by the NKE SELL itself, which exists *because* the gate caught staleness |
| No trade on invalid LLM output | ⚠️ Partial | The LLM output itself was valid/well-formed for every 07-02 signal (no parse failures) — but the *ticker* attached to one valid LLM output was wrong (see [DAY-001]). "Valid LLM output" and "correct ticker" are enforced by different, independently-failing layers. |
| No trade if circuit breaker active | ✅ Pass | No `killswitch_active` events observed 07-02; all 4 orders proceeded normally |
| No trade if strategy disabled | ✅ Pass | Only S1 (supervised_paper) and S4 (paper) ran, both `approved=true`; S2 (disabled) and S7 (research, unapproved) placed zero orders |
| Paper/live mode coherent | ✅ Pass | 100% paper, confirmed at 3 independent levels (env var, config default, hardcoded global flag) |
| Idempotency under Celery retry | ✅ Pass (indirect evidence) | Signal-id-based idempotency (`_get_fired_signal_ids`, one order per signal_id per session date, per discovery) + 0 duplicate order_ids observed |
| Reconciliation: orders ↔ fills ↔ positions ↔ trades | ✅ Pass | All 4 order_ids trace cleanly through `execution_decisions.order_id` → `trades.entry_order_id`/`exit_order_id` → live `/api/positions` (META/MU/NOW qty match `trades.qty` exactly) |

## 10. Anomalies Found

### [DAY-001] Ticker misattribution: SanDisk news scored as AAPL sentiment

* Tipo: Bug
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log` (id=1632, 1633), `sentiment_signals` (id=1632), `news_resolved_entities` (row keyed by url, `candidate_ticker='AAPL'`)
  * timestamp: 2026-07-02 17:45:19 UTC (fetched), published 2026-07-02 12:39:30 UTC
  * snippet/query: `SELECT id, title, source, ticker FROM news_log WHERE title ILIKE '%Sandisk%' AND fetched_at >= '2026-07-02'` → row `id=1632, title='Why Is Sandisk Stock Falling on Thursday?', source='alpaca_benzinga', ticker='AAPL'` (body: *"SanDisk Corp. (NASDAQ:SNDK) stock declined on Thursday due to a sector-wide profit-taking rotation into AI software and potential risks from Chinese memory supply."* — zero mention of Apple). The correctly-tagged twin, `id=1633, ticker='SNDK'`, was ingested 19 seconds later.
* Descrizione: The `alpaca_benzinga` connector trusts vendor-supplied ticker metadata (`extraction_method='source_metadata'`) without independent verification before the news reaches the sentiment worker. This specific article was multi-tagged by the vendor to both AAPL and SNDK; the AAPL-tagged copy produced `sentiment_signals id=1632`: score **-0.4851**, confidence 0.615 — a strong, stored, real negative signal for Apple derived from a story that has nothing to do with Apple. The deterministic resolver (`news_resolved_entities`) *did* correctly classify the AAPL candidate as `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` (confidence 0.6) — but per QX-01 design, resolver verdicts are measurement-only right now and do not gate the live `sentiment_signals` write path.
* Impatto: This signal blended into AAPL's aggregated `signal_score` for the rest of the day (13 consecutive `SKIP_THRESHOLD` evaluations at -0.168/-0.21, versus what would likely have stayed closer to neutral/positive without the bad -0.485 input, given the legitimate +0.520 AAPL signal earlier that day). No order resulted on 07-02 — the blended score never crossed the ±0.30 threshold — but this was **coincidental**, not systemic protection. A slightly larger mistagged-article score, or one more real negative AAPL headline that day, would have produced a SELL/short-weight decision on Apple driven by SanDisk news.
* Severità: Critical
* Confidenza: High
* Azione consigliata: Open a ticket to fast-track resolver enforcement (or a lighter-weight interim gate) specifically for the `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` and `NO_TRADE_NOT_TRADABLE` verdicts — even before full QX-01 enforcement lands, these two verdict types could reasonably suppress `sentiment_signals` writes (or flag them as `excluded_from_decision=true`) without waiting on the full golden-label calibration effort, since they are precisely the "wrong ticker" case CLAUDE.md calls the worst-case error.
* Test/monitor consigliato: Daily automated check — count and alert on `sentiment_signals` rows whose `news_log_id` maps to a `news_resolved_entities` row with `decision LIKE 'NO_TRADE%'`; page if any such signal's `abs(score) > 0.3` (i.e., strong enough to influence a real decision).

### [DAY-002] Daily risk-exposure alert is permanently miscalibrated (hardcoded placeholder)

* Tipo: Bug
* Area: Risk
* Evidenza:
  * file/log/tabella: `src/workers/risk_monitor_task.py:85` (`total_exposure = 1.0  # full-portfolio exposure placeholder`), `risk_reports` table
  * timestamp: every `risk_reports` row from 2026-06-23 to 2026-07-02 (10/10 days sampled)
  * snippet/query: `SELECT timestamp, total_exposure, alerts FROM risk_reports ORDER BY timestamp DESC LIMIT 10;` → `total_exposure=1.000000` and alert `"Total portfolio exposure 100.0% exceeds 50%"` on **every single row**, including 2026-07-02 22:30:00.
* Descrizione: `_fetch_strategy_data()` hardcodes `total_exposure = 1.0` whenever any `portfolio_daily_state` data exists, instead of computing actual gross/net exposure from live positions or trade notionals. `PortfolioRiskMonitor` correctly compares this against the 50% cap and fires an ALERT-level alert — every day, unconditionally, regardless of the portfolio's real exposure (which was closer to ~5-10% of notional on 07-02, per the 3 small BUY weights of 3.3-5.0%).
* Impatto: The risk-monitoring layer's exposure alert has zero discriminative power — it cannot distinguish a real 100%-exposure emergency from a normal ~5% day, because it always reports the same value. Anyone relying on `risk_reports.alerts` for exposure monitoring is trained to ignore it (alert fatigue), meaning a genuine future exposure breach would look identical to every prior day and likely be dismissed.
* Severità: High
* Confidenza: High
* Azione consigliata: Wire `total_exposure` to a real computation (sum of live position market values / NAV, pulled from the same Alpaca `get_all_positions()` call already used elsewhere, or from `trades WHERE exit_time IS NULL` notional as a DB-only proxy) before this metric is used for anything beyond a TODO placeholder. Until fixed, this alert should be treated as non-functional, not as evidence of risk.
* Test/monitor consigliato: Unit test asserting `total_exposure` varies with a synthetic `strategy_returns`/positions fixture (currently it cannot, by construction); ops dashboard should suppress/flag this specific alert message as known-broken until the fix ships.

### [DAY-003] `risk_reports.nav` is not account NAV — mislabeled, frequently negative

* Tipo: Bug (naming/semantics) / Rischio (misinterpretation)
* Area: Risk / PnL
* Evidenza:
  * file/log/tabella: `src/workers/risk_monitor_task.py:83-84` (comment: *"Approximate NAV from cumulative net_pnl (no cash tracking in DB yet)"*), `risk_reports.nav` for 2026-07-02 = **-578.5159**
  * timestamp: 2026-07-02 22:30:00.023562+00
  * snippet/query: `SELECT timestamp, nav FROM risk_reports ORDER BY timestamp DESC LIMIT 10;` → nav negative on 8 of the last 10 days (range -268 to -745)
* Descrizione: The field named `nav` in `risk_reports` is actually `sum(net_pnl)` over a rolling 60-day window of closed trades — a cumulative realized-PnL proxy, not the account's net asset value. It is expected to be negative during any drawdown period and says nothing about actual account equity (which per Alpaca paper account is presumably positive and unrelated in magnitude).
* Impatto: Low direct trading impact (this field doesn't gate any decision), but high interpretability risk — anyone reading `risk_reports` cold (a new team member, an auditor, this very report's first draft) would reasonably read "nav: -578.52" as "the fund has negative net worth," which is false and alarming.
* Severità: Medium
* Confidenza: High
* Azione consigliata: Rename the column/field to `cumulative_realized_pnl_60d` (or similar) and, separately, add a real NAV field once cash tracking exists, rather than overloading the name.
* Test/monitor consigliato: None needed beyond the rename; add a docstring/comment at the `risk_reports` schema level to prevent recurrence in future readers.

### [DAY-004] Docker logs for the audited date are unrecoverable

* Tipo: Ambiguità / Non verificabile
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker inspect alembic-worker-1 alembic-worker-inference-1 alembic-beat-1 alembic-api-1`
  * timestamp: all 4 containers `RestartCount=0`, `StartedAt=2026-07-03T09:57:22Z`
  * snippet/query: `docker logs alembic-worker-1 --since "2026-07-02T00:00:00" --until "2026-07-03T00:00:00"` → empty (log buffer only extends back to container start, i.e. this morning)
* Descrizione: The stack (worker, worker-inference, beat, api — frontend/postgres/redis were not recreated, per their longer uptimes) was recreated at 09:57 UTC today, discarding all prior container log history. There is no dedicated errors table (per discovery §13) and no log-shipping/persistence (Loki, CloudWatch, etc.) evidenced in this repo, so Docker's own ephemeral buffer was the *only* place exception tracebacks, Ollama HTTP errors, and non-audited warnings for 07-02 would have lived.
* Impatto: This report's conclusions about "no worker restarts," "no unlogged exceptions," and the qualitative "Ollama was up" claim rest entirely on DB-derived indirect evidence (fallback reasoning strings, absence of budget exhaustion, absence of killswitch events) rather than direct log confirmation. That indirect evidence is solid, but it cannot rule out, e.g., a transient worker crash-and-restart that Celery's own retry logic absorbed without leaving a DB trace.
* Severità: High
* Confidenza: High
* Azione consigliata: Stand up log persistence (even a simple `docker logs` volume mount + daily rotation to disk, or a lightweight Loki/promtail sidecar) before the next incident makes this gap costly. Until then, treat any "why did X happen" question about a day more than ~1 container-lifetime old as potentially unanswerable.
* Test/monitor consigliato: Add a monitor that alerts if a trading-relevant container's `StartedAt` changes unexpectedly (i.e., an unplanned restart/recreate) — this would have caught today's recreate event in real time instead of being discovered as a side effect of this audit.

### [DAY-005] `news_resolved_entities.news_log_id` foreign key not populated

* Tipo: Bug
* Area: Data / News
* Evidenza:
  * file/log/tabella: `news_resolved_entities`
  * timestamp: 2026-07-02 (all 127 rows for the day)
  * snippet/query: `SELECT nre.* FROM news_resolved_entities nre JOIN news_log n ON nre.news_log_id = n.id WHERE n.title ILIKE '%Sandisk%'` → 0 rows, versus joining on `url` → 5 rows correctly found, all with `news_log_id` blank in the result set
* Descrizione: The resolver-shadow pipeline writes `news_resolved_entities.url` reliably but leaves `news_log_id` unpopulated (at least for 07-02's data), even though the column exists specifically as an FK to `news_log(id)`. Any consumer joining these two tables the "obvious" way (by ID) silently gets zero matches.
* Impatto: Breaks straightforward auditability of "what did the resolver decide about this specific news_log row" — analysts must fall back to URL-based joins, which are more fragile (URL normalization, redirects, query-string variants can all break equality matching that an integer FK would not).
* Severità: Medium
* Confidenza: High
* Azione consigliata: Backfill `news_log_id` on `news_resolved_entities` (similar in spirit to the recent FIX-05 backfill done for `sentiment_signals.news_log_id`) and fix the write path (`src/connectors/resolver_shadow.py`) to populate it going forward.
* Test/monitor consigliado: Add a data-quality check: `SELECT count(*) FROM news_resolved_entities WHERE news_log_id IS NULL AND created_at > now() - interval '1 day'` should be 0 (or near-0) going forward.

### [DAY-006] Resolver returned 0% "tradable" verdicts for the entire day

* Tipo: Ambiguità / Rischio
* Area: News / Risk
* Evidenza:
  * file/log/tabella: `news_resolved_entities`
  * timestamp: 2026-07-02
  * snippet/query: `SELECT decision, count(*) FROM news_resolved_entities WHERE created_at::date='2026-07-02' GROUP BY decision` → `NO_TRADE_LOW_RESOLUTION_CONFIDENCE: 73`, `NO_TRADE_NOT_TRADABLE: 54` — **127/127 = 100% NO_TRADE**, zero successful ticker resolutions
* Descrizione: Every single news item processed by the deterministic resolver on 07-02 was rejected, either for low confidence or non-tradability. This is measurement-only data (per QX-01, it doesn't currently gate anything), but a 100% rejection rate on a full trading day is either (a) a legitimately hard day for ticker resolution (small-caps, ETFs, ambiguous company names dominating the news mix), or (b) evidence the resolver's confidence/tradability thresholds are miscalibrated and would block essentially all trading if enforcement were switched on today.
* Impatto: No impact on 07-02 itself (resolver isn't gating). High impact on planning: if/when QX-01 enforcement is turned on without addressing whatever is driving 100% rejection, S4 news-tactical would likely go to zero signal throughput immediately.
* Severità: Medium
* Confidenza: Medium (single-day sample; could be a genuine one-off news mix rather than a systemic calibration problem — would need to check the trend across more days to confirm)
* Azione consigliata: Before scheduling QX-01 enforcement, pull the resolver's NO_TRADE rate over the full history (not just 07-02) and inspect a sample of `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` cases for tickers that were, in fact, correctly and unambiguously identifiable — if the false-rejection rate is high, calibrate before enforcing.
* Test/monitor consigliato: Daily dashboard tile: resolver "tradable" rate over trailing 7/30 days, so a 100% rejection day, if it recurs, is visible without needing an ad hoc audit.

### [DAY-007] FinBERT fallback rate 79.5% — ensemble divergence, not availability

* Tipo: Corretto (funzionò come progettato) / Rischio (design question)
* Area: LLM
* Evidenza:
  * file/log/tabella: `sentiment_signals`, `llm_responses`
  * timestamp: 2026-07-02, all day, evenly distributed (not concentrated in any outage window — see per-15-min breakdown run this session)
  * snippet/query: `SELECT reasoning, count(*) FROM sentiment_signals WHERE generated_at::date='2026-07-02' AND fallback_used GROUP BY reasoning` → `"FinBERT fallback (ensemble divergence)": 101` (100% of fallbacks); 0 timeout-reasoned, 0 budget-reasoned fallbacks
* Descrizione: The divergence-fallback mechanism worked exactly as designed (std > 0.30 between kimi-k2.6 and glm-5.2 → don't trust the ensemble, use FinBERT instead) — this is a **correct** finding, not a bug. But at 79.5% fallback, the practical effect is that FinBERT (a simpler, local, non-reasoning model) generated the majority of the day's sentiment scores, while the more expensive DK-CoT LLM ensemble's output was discarded most of the time.
* Impatto: Raises a design question rather than an incident: is a 0.30 std threshold appropriate for a *2*-model ensemble (where any real disagreement swings std sharply, unlike a 5+ model ensemble where disagreement averages out)? If FinBERT is doing most of the real work, the cost/complexity of the Ollama ensemble may not be earning its keep on typical news days.
* Severità: Medium
* Confidenza: High (the reasoning-string evidence is unambiguous)
* Azione consigliata: Not a remediation ticket per se — a research question for the team: compare FinBERT-only vs ensemble-only signal quality (forward-return correlation) over the accumulating `forward_return` history, and consider whether the divergence threshold, or the model pair itself, needs recalibration.
* Test/monitor consigliato: Weekly report of fallback rate by reason (divergence vs timeout vs budget) — a spike in the *timeout* or *budget* categories would be the real "Ollama is down" signal to watch for, distinct from this divergence-driven baseline.

### [DAY-008] Sentiment/portfolio crontab is fixed-UTC and drifts vs. actual NYSE hours under EDT

* Tipo: Ambiguità
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py:66-72` (`crontab(minute="*/15", hour="14-21", day_of_week="1-5")`, comment: *"9am-4pm ET"*)
  * timestamp: n/a (structural, not a 07-02-specific event)
  * snippet/query: NYSE cash session is 13:30–20:00 UTC during EDT (current, since 2026-07-02 is within US daylight saving time). The crontab's fixed 14:00–21:45 UTC window is exactly correct for EST (winter) but, right now, starts 30 minutes *after* the open and continues 1h45m *after* the close.
* Descrizione: The code comment assumes a fixed ET offset; Celery's crontab has no DST awareness. This is a real, currently-active mismatch (not a twice-a-year edge case) for the July 2026 date under audit.
* Impatto: On 07-02 this did **not** produce any observed out-of-hours order (last fill 19:52 UTC = 3:52pm EDT, before close) — but the crontab's extended tail (up to 21:52 UTC = 5:52pm EDT for portfolio-cycle) means a late-day signal *could* legally produce an order nearly 2 hours after the cash session closes, which Alpaca would either reject or fill at a stale/extended-hours price depending on order type — not exercised on this date, but a latent risk.
* Severità: Medium
* Confidenza: High
* Azione consigliata: Either make the beat schedule DST-aware (compute market-hours crontab dynamically, e.g. via `pandas_market_calendars` or similar) or explicitly document/accept the fixed-UTC approximation and tighten the window to avoid the 1h45m post-close tail.
* Test/monitor consigliato: Alert if any order's `filled_at` falls outside `[13:30, 20:00)` UTC-adjusted-for-DST NYSE hours — would catch both this drift and any future scheduling regression.

### [DAY-009] False positive: apparent news-ingest "gap" since 21:47 UTC is expected, not an outage

* Tipo: Corretto
* Area: News / Ops
* Evidenza:
  * file/log/tabella: `news_log` (max `fetched_at` = 2026-07-02 21:47:14), `celery_app.py:69-70`
  * timestamp: audit performed 2026-07-03 12:31 UTC
  * snippet/query: crontab `hour="14-21"` → last run 21:45 UTC weekdays; next window opens 14:00 UTC 07-03, which had not yet arrived at audit time (12:31 UTC)
* Descrizione: Initial inspection flagged a ~15-hour gap since the last ingested news item as a possible outage. Cross-checking the beat schedule confirms this is fully expected: the ingestion/sentiment crontab simply does not run outside 14:00–21:45 UTC on weekdays, and the audit window (12:31 UTC 07-03) falls before that day's window opens.
* Impatto: None — included here explicitly as a documented false-positive to prevent re-flagging in future daily audits.
* Severità: Low
* Confidenza: High
* Azione consigliata: None.
* Test/monitor consigliato: None — this is expected behavior, not something to monitor.

### [DAY-010] False positive: the day's only SELL is not the historical "SELL with positive sentiment" bug

* Tipo: Corretto
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions id=825`
  * timestamp: 2026-07-02 14:22:01 UTC
  * snippet/query: reason = *"S4 signal expired (age=19.3h > max_age=4h, generated 2026-07-01 19:02 UTC, score=+0.387): weight 0.0% — no counter-signal found, position closed."*
  * discovery cross-reference: the "SELL despite positive sentiment" class of bug (CrossSectionalRanker returning `{}` when `min_stocks=2` wasn't met, misread as "liquidate everything") was already identified and fixed 2026-06-29 (`_fresh_signal_protected_symbols()` guard, 8 TDD tests in `tests/workers/test_protected_sell.py`)
* Descrizione: This SELL was explicitly requested by the prompt's pattern-check list ("SELL con sentiment positivo (bug A5)"). On inspection, this is a *different*, already-remediated bug class, and the 07-02 NKE sell is functionally correct: the position's originating signal (score +0.387) simply aged out (19.3h old, past the 4h freshness window) with no fresh counter-signal to justify holding, so S4 closed it per its own designed staleness rule. The exit happened to be profitable (+$83.96) because NKE's price rose in the interim — a lucky outcome, not evidence either way about correctness.
* Impatto: None — documented to confirm the specific pattern requested was checked and not found.
* Severità: Low
* Confidenza: High
* Azione consigliata: None for 07-02. General recommendation: keep the 2026-06-29 regression test suite (`test_protected_sell.py`) in CI to prevent recurrence.
* Test/monitor consigliato: Existing `test_protected_sell.py` suite is the right ongoing monitor; no new test needed for this date's behavior.

## 11. False Positives / Correct Areas

- **[DAY-009], [DAY-010]** above — see full detail.
- **Idempotency / no duplicate orders / no pyramiding on 07-02**: explicitly checked and clean. (Historical pyramiding-looking patterns — e.g. AZN with 24 consecutive BUY decisions — exist only in mid-June 2026-06-15…06-18 data, predating the system's "Day 1" controlled-paper bootstrap on 2026-06-23, and are out of scope for this audit; current live check shows max 1 open position per symbol system-wide.)
- **R-14 (residual risk register: `trades.entry_time` NULL on all closed trades)**: re-checked directly — **resolved**. All 229 closed trades in the current DB have `entry_time` populated.
- **R-13 (pyramiding — up to 17 open positions per symbol)**: re-checked directly — **resolved** as of now. Current open positions: 1 each for META, MU, NOW.
- **Paper vs. live discipline**: triple-confirmed correct (env var, config default, hardcoded global flag) — no ambiguity found.
- **Reconciliation orders↔fills↔positions↔trades**: clean 1:1 for all 4 of the day's orders.
- **Sanitization pipeline**: confirmed wired into the hot path (`sentiment.py` calls `sanitize_text`/`sanitize_ticker` before every LLM prompt) — this is *not* a gap, contrary to what a purely-schema-level read might suggest.

## 12. Missing / Inaccessible Data

| Item | Why unavailable | What would be needed |
|---|---|---|
| Docker logs for worker/worker-inference/beat/api, 2026-07-02 | Containers recreated 2026-07-03 09:57 UTC, wiping log buffer | Persistent log storage (volume-mounted logs, or Loki/CloudWatch) going forward; nothing recovers the lost 07-02 window |
| LLM per-request latency | No duration column in `llm_responses`; app-level timing only existed in now-lost logs | Add a `latency_ms` column populated at write time, or ship structured request logs to a persistent store |
| True per-source dedup/discard counts | `ingestion_stats_daily` table exists in schema but has **0 rows total** — never populated despite being referenced in discovery as "written by every ingestion task" | Either fix the write path or query Redis directly for the ephemeral TTL-dedup counters in near-real-time (they expire after 4h and cannot be reconstructed after the fact) |
| End-of-day mark-to-market portfolio value for 07-02 | No positions-snapshot table exists; positions are only ever fetched live from Alpaca, never persisted historically | A scheduled EOD snapshot job (`get_all_positions()` + close prices → new table), or query Alpaca's own portfolio-history endpoint directly (out of scope for this read-only DB/log/API session) |
| Confirmation of zero broker-level order rejects on 07-02 (vs. zero *recorded* rejects) | `_on_broker_reject` callback exists in code but is never wired to any call site — rejects only ever reach `log.warning` (lost logs), never a DB row | Wire the reject callback to persist to `execution_decisions` or a new `broker_rejects` table |
| `performance_metrics` for any date | Table has 0 rows — daily report job (`run_daily_report`, 03:00 UTC) apparently has not successfully written since the table was created, or writes are failing silently | Investigate why `run_daily_report` isn't populating `performance_metrics`; would need log access (see above) or a manual task trigger to diagnose live (out of scope — read-only session) |
| `forward-return-worker` outcome for 07-02 signals | Not independently queried this session (scoped out for time; `sentiment_signals.forward_return` column exists and is presumably populated on a lag) | `SELECT count(*), count(forward_return) FROM sentiment_signals WHERE generated_at::date='2026-07-02'` |

## 13. Immediate Recommendations

1. Treat [DAY-001] as the priority item: even a lightweight interim gate (suppress/flag `sentiment_signals` derived from `NO_TRADE_LOW_RESOLUTION_CONFIDENCE`/`NO_TRADE_NOT_TRADABLE` resolver verdicts) closes the sharpest edge here without waiting for full QX-01 enforcement.
2. Fix or remove the [DAY-002] hardcoded `total_exposure=1.0` — a risk alert that fires unconditionally every day is worse than no alert, because it trains operators to ignore it.
3. Stand up basic Docker log persistence ([DAY-004]) before the next audit — today's gap means several claims in this report rest on indirect DB evidence rather than direct confirmation.
4. Rename or re-scope `risk_reports.nav` ([DAY-003]) to prevent future misreading as account equity.
5. Backfill `news_resolved_entities.news_log_id` ([DAY-005]) and fix its write path for future rows.

## 14. Tests / Monitors to Add

- Daily: count of `sentiment_signals` whose source news resolved to `NO_TRADE_*` with `abs(score) > 0.3` (catches recurrences of [DAY-001]-class events before they reach a decision).
- Daily: resolver tradable-rate tile (trailing 7/30 days) to catch [DAY-006]-style calibration drift.
- Weekly: fallback-reason breakdown (divergence vs. timeout vs. budget) — a shift toward timeout/budget is the real "Ollama down" signal, distinct from the divergence baseline observed on 07-02.
- Structural: alert on unexpected container `StartedAt` change (unplanned restart/recreate) for the 4 trading-relevant services.
- Structural: unit test that `total_exposure` in `risk_monitor_task.py` responds to its inputs (currently cannot, by construction — see [DAY-002]).
- Structural: order-fill-time-vs-market-hours monitor to catch [DAY-008]-class DST drift if it ever produces an actual after-hours fill.

## 15. Suggested Technical Tickets

1. **[Critical]** Gate `sentiment_signals` writes (or add an `excluded_from_decision` flag) on `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` / `NO_TRADE_NOT_TRADABLE` resolver verdicts, ahead of full QX-01 enforcement. (ref: [DAY-001])
2. **[High]** Replace hardcoded `total_exposure = 1.0` in `risk_monitor_task.py::_fetch_strategy_data` with a real computation from live/DB position notionals. (ref: [DAY-002])
3. **[High]** Add persistent log storage for the 4 trading containers (worker, worker-inference, beat, api). (ref: [DAY-004])
4. **[Medium]** Rename `risk_reports.nav` → `cumulative_realized_pnl_60d` (or add a real NAV field alongside it). (ref: [DAY-003])
5. **[Medium]** Backfill and fix `news_resolved_entities.news_log_id` write path. (ref: [DAY-005])
6. **[Medium]** Investigate 100% NO_TRADE resolver rate on 07-02 against a longer trailing window; recalibrate confidence/tradability thresholds if the false-rejection rate is high. (ref: [DAY-006])
7. **[Medium]** Fix `ingestion_stats_daily` write path (currently 0 rows ever) or remove the dead table. (ref: §12)
8. **[Medium]** Make market-hours crontab DST-aware, or explicitly narrow/document the fixed-UTC window. (ref: [DAY-008])
9. **[Low]** Wire the existing-but-unused `_on_broker_reject` callback to a persisted table. (ref: §12)
10. **[Low]** Investigate why `performance_metrics` has zero rows despite a daily 03:00 UTC write job. (ref: §12)

## 16. System State

| Metric | Value | Confidence |
|---|---|---|
| Ollama up/down, 2026-07-02 | **Up all day** — 0 timeout-reasoned fallbacks, 52 successful ensemble responses (26 news items × 2 models), budget not exhausted | High (DB-derived; no direct log confirmation possible — see [DAY-004]) |
| Ollama downtime hours, 2026-07-02 | 0 (no evidence of any downtime window) | High |
| FinBERT fallback rate, 2026-07-02 | 101/127 = **79.5%** of decisions/signals, 100% attributed to ensemble divergence (std>0.30), 0% timeout, 0% budget | High |
| Worker restart events, 2026-07-02 | **Not verifiable** — Docker log history for that date is lost; `fallback_counters` table (which would show consecutive-fallback resets, an indirect restart proxy) is currently empty (0 rows), and no `audit_log` entries suggest a mid-day process restart | Low / Not verifiable |
| Container recreate event | All 4 trading containers (worker, worker-inference, beat, api) recreated 2026-07-03 09:57:22 UTC — **after** the audited date, so it does not affect 07-02's pipeline behavior, but it does affect this audit's ability to verify 07-02 via logs | High |
| Timezone | UTC throughout the DB and Celery config, confirmed with no storage ambiguity; scheduling (crontab) has a DST-vs-fixed-UTC ambiguity (see [DAY-008]) that does not affect timestamp *interpretation*, only *when* the pipeline runs relative to true market hours | High |

---

*End of report. No files other than this report were modified. No commits created. No orders submitted. No pipelines re-run.*
