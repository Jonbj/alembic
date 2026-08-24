# Weekly Findings — Week 34, 2026 (Aug 17-20)

## Week Overview

- **Date range**: Monday Aug 17 – Thursday Aug 20, 2026 (Friday Aug 21 report not yet generated at time of analysis)
- **Reports analyzed**: 4 daily alpha-miss reports
  - `docs/ALPHA_MISS_REPORT_2026-08-17.md` (13 movers, 9 misses)
  - `docs/ALPHA_MISS_REPORT_2026-08-18.md` (22 movers, 6 misses)
  - `docs/ALPHA_MISS_REPORT_2026-08-19.md` (24 movers, 8 misses)
  - `docs/ALPHA_MISS_REPORT_2026-08-20.md` (9 movers, 4 misses)
- **Logs analyzed**: 5 daily logs (Aug 17-21)
- **Total movers ≥3%**: 68
- **Total misses**: 27
- **Overall miss rate**: 39.7%

## Summary Statistics

| Metric | Aug 17 | Aug 18 | Aug 19 | Aug 20 | Week Total |
|--------|--------|--------|--------|--------|------------|
| Movers ≥3% | 13 | 22 | 24 | 9 | 68 |
| Captured | 4 | 16 | 16 | 5 | 41 |
| Missed | 9 | 6 | 8 | 4 | 27 |
| NO_NEWS | 2 | 1 | 6 | 2 | 11 |
| THIN_NEUTRAL | 5 | 2 | 2 | 1 | 10 |
| WRONG_SIGN | 2 | 0 | 0 | 1 | 3 |
| FILTERED | 0 | 3 | 0 | 0 | 3 |
| Cross-sectional σ | 2.12 | 2.84 | — | — | — |
| NAV change | — | -$293 | -$80 | -$246 | — |
| S4 economic P&L | -$119 | -$314 | -$469 | -$478 | — |
| S4 within ±$200? | YES | NO | NO | NO | 3/4 days OUT |
| Zero-news symbols | 38/96 | 40/96 | 40/96 | 41/96 | ~40% avg |

## Miss Cause Distribution

```
NO_NEWS       ████████████████████████  11/27 (40.7%)
THIN_NEUTRAL  ████████████████████      10/27 (37.0%)
WRONG_SIGN    ███████                    3/27 (11.1%)
FILTERED      ███████                    3/27 (11.1%)
```

## Quantified Missed Alpha

| Cause | Estimated Cost |
|-------|---------------|
| NO_NEWS (accessible bullish) | $639.17+ |
| FILTERED (long-only blocks) | $485.69 (theoretical) |
| F-030 (late entry MTM loss) | $52.22 |
| THIN_NEUTRAL (below gate) | $79.93 (PFE only; others $0 or non-estimable) |
| WRONG_SIGN | $0 (all bearish on long-only) |
| **Total quantified** | **$1,256.01+** |

## Findings and GitHub Issues

### Issue #324 — F-001: Zero news coverage on 40% of watchlist
- **Category**: Bug / Data quality
- **Severity**: High — dominant miss cause (11/27 misses, $639+ lost alpha)
- **Aggravating factor**: Zero news also blocks exit signals on held positions in loss (GE, DELL, WDC)
- **URL**: https://github.com/Jonbj/alembic/issues/324

### Issue #325 — F-002: 11 legacy positions without stop_strategy
- **Category**: Bug / Data attribution
- **Severity**: Medium — 14+ sessions of non-attributable P&L, 58% of NAV on Aug 17
- **URL**: https://github.com/Jonbj/alembic/issues/325

### Issue #326 — F-040: Long-only constraint blocks above-gate bearish signals
- **Category**: Design decision / Structural observation
- **Severity**: Decision ticket — $485.69 theoretical opportunity on single day
- **Note**: Long-only is declared design (CLAUDE.md), not a bug. Issue is for operator decision on whether to build short-side capability.
- **URL**: https://github.com/Jonbj/alembic/issues/326

### Issue #327 — F-030: S4 entries late at high day-range percentiles
- **Category**: Bug / Strategy performance
- **Severity**: Medium — $52.22 MTM loss from late entries on Aug 19, recurring pattern
- **URL**: https://github.com/Jonbj/alembic/issues/327

### Issue #328 — Fallback WRONG_SIGN and multi-ticker fan-out
- **Category**: Bug / Signal quality
- **Severity**: Medium — 2 WRONG_SIGN + 4 fan-out misses; fallback model sign errors; risk of wrong-way entry
- **URL**: https://github.com/Jonbj/alembic/issues/328

### Issue #330 — Git push failures on automated analysis job
- **Category**: Bug / CI-CD
- **Severity**: Medium — 2/4 daily reports not on remote repository
- **URL**: https://github.com/Jonbj/alembic/issues/330

### Issue #329 — S4 economic P&L outside ±$200 band for 3 consecutive days
- **Category**: Monitoring / Decision point
- **Severity**: High — S4 at -$478 vs ±$200 tolerance, may trigger kill criterion (#179)
- **URL**: https://github.com/Jonbj/alembic/issues/329

## Findings Already Tracked (No New Issue Created)

The following recurring patterns were observed this week but are already covered by existing open issues:

- **F-020** (org_lookup false positives on MS): 19/19 news rows for MS on Aug 20 were via `org_lookup` about third-party companies → tracked by **Issue #243**
- **F-009** (gate threshold blocks below-0.30 signals): AVGO on Aug 18 (-0.189), PFE on Aug 19 (0.12), AVGO on Aug 19 (-0.158) → tracked by **Issue #289** (post-freeze gate evaluation)
- **F-031** (anti-pyramiding guard blocks incremental entry on held positions): MRVL signal +0.585 on Aug 20 did not produce a top-up → tracked by **Issue #230**
- **#277** (no intraday bars at eligible cycle for counterfactual estimation): SPCX, ADBE non-estimable → tracked by existing issue #277

## Key Patterns This Week

1. **Semiconductor rout (Aug 18-19)**: 2.84σ dispersion day — largest in observation window. 14/16 captured movers were S1 semi/hardware positions held for weeks, all losing via MTM. The book's sector concentration amplified the rout.

2. **NO_NEWS dominance**: 11/27 misses (40.7%) had zero news coverage. This is the dominant alpha-miss cause this week, with $639+ in quantified lost alpha on bullish movers that a long-only book could have captured.

3. **Long-only as binding constraint**: For the first time, 3 signals with correct sign and above-gate magnitude were filtered purely by the long-only design (F-040). The pipeline works end-to-end, but the strategy cannot monetize bearish signals.

4. **S4 deterioration**: S4 economic P&L went from -$119 to -$478 over 4 days, breaching the ±$200 tolerance for 3 consecutive days. Late entries (F-030) and sentiment-reversal exits on volatile days are contributing factors.

5. **Signal quality issues**: Fallback model WRONG_SIGN returned after absence — 2 cases on Aug 17 (INFY +0.42, MSFT +0.30), both from fallback single-model signals overriding correct-sign ensemble signals. Multi-ticker fan-out articles continue to generate irrelevant signals.

## Recommendations for Next Week

1. **Monitor S4 kill criterion**: With 3 consecutive days outside ±$200, the operator should evaluate whether to trigger the pre-registered kill criterion (#179)
2. **Prioritize GDELT DOC activation (#159)**: This is the highest-impact fix for the NO_NEWS problem — $639+ weekly alpha is being lost to coverage gaps
3. ~~**Rebase and push local commits**: The Aug 18-19 reports need manual sync to remote (issue #330)~~ — **already done**; all five reports are on `main` (`f7b28d2`, `3646502`, `58a29f0`, `a034c36`). The live residue is the root cause, now #336.
4. **Watch for WRONG_SIGN on fallback signals**: If fallback signals continue generating above-gate wrong-sign scores, consider disabling fallback-only entries
5. **Track the semiconductor concentration**: The book's heavy S1 exposure to semiconductors amplified both gains (Aug 17) and losses (Aug 18-19) — sector concentration risk should be quantified

---

# Opus Retry Pass — Aug 22, 2026

The first pass (issues #324-#330) was performed on a non-Opus model. This pass re-derived the week's findings from the **primary evidence** rather than the narrative reports: `docs/evidence/dossier/2026-08-{17,18,19,20}.json`, the five run logs, and the live source tree.

The seven original issues were **substantially correct on the findings the daily reports surfaced**. Every new finding below came from evidence the daily reports either omitted or did not connect, which is itself the first finding.

## New issues opened in this pass

| # | Title | Category | Severity | Source of the miss |
|---|-------|----------|----------|--------------------|
| [#333](https://github.com/Jonbj/alembic/issues/333) | Aug 20 report omits 3 of 4 S4 entries and 3 of 4 exits, including the day's largest loss (HOOD −$60.32) — no report/dossier reconciliation | Bug / Evidence integrity | **High** | Only visible by diffing the dossier JSON against the report prose |
| [#334](https://github.com/Jonbj/alembic/issues/334) | S4 same-session exits fire on a deterministic 105-minute clock (90-min hold guard + one 15-min cycle) — 5 occurrences, −$10.91 | Decision / Strategy cadence | **High** | Required cross-referencing `ore_tenuta` across four dossiers against `_HOLD_MINIMUM_MINUTES` in source |
| [#335](https://github.com/Jonbj/alembic/issues/335) | S4 opened a long into WMT's −9.16% earnings crash on a +0.318 score; no pre-trade price-action or earnings-calendar guard | Bug / Entry admissibility | **High** | The one wrong-way signal this week that reached capital; #328 recorded the week's WRONG_SIGN cost as "$0 verified" |
| [#336](https://github.com/Jonbj/alembic/issues/336) | Alpha-miss cron inherits whatever branch is checked out: 2 of 5 runs never committed (corrects #330's accounting to 4-of-5) | Bug / CI-CD | Medium | Second failure mode in the same logs, distinct from the push rejections #330 captured |

## Corrections posted to existing issues

| Issue | Correction |
|-------|-----------|
| [#327](https://github.com/Jonbj/alembic/issues/327#issuecomment-5379926759) | HOOD realised **−$60.32** on Aug 20, not the −$50.16 MTM recorded. Proposed fix #4 is unsound as written: `entry_percentile` is **direction-blind**, and would have rated WMT (0.287) and NVDA (0.376) — the session's two worst entries — as *early*. `quota_movimento_precedente_al_segnale` is the correct instrument (WMT scored 0.921). |
| [#328](https://github.com/Jonbj/alembic/issues/328#issuecomment-5379925569) | "$0 verified cost on all WRONG_SIGN cases this week" omits WMT, the only case that cleared the gate and moved capital. Its own proposed fix #4 is the missing control; carried forward as #335. |
| [#329](https://github.com/Jonbj/alembic/issues/329#issuecomment-5379926827) | Aug 20's −$78.57 was **not** driven by WMT (the only profitable trade of the four, +$2.38) but by HOOD (−$60.32) and NOW (−$19.60). Mechanism ranking updated to include the 105-minute exit clock (#334). |
| [#330](https://github.com/Jonbj/alembic/issues/330#issuecomment-5379925512) | "Aug 17 report pushed successfully" is wrong — it was never committed. Week's failure count is 4 of 5, across two failure modes. "Manual fix needed now" is already resolved. |

## Corrected Aug 20 trade record

The Aug 20 report narrates WMT alone. The dossier records eight book events:

| | Symbol | Time UTC | pct | net P&L | Exit reason | Held | drift post-exit |
|---|--------|----------|-----|---------|-------------|------|-----------------|
| IN | NVDA | 15:22 | 0.376 | — | — | — | — |
| IN | WMT | 16:37 | 0.287 | — | — | — | — |
| IN | NOW | 16:52 | 0.914 | — | — | — | — |
| IN | AVGO | 17:07 | 0.181 (`denominatore_degenere: true`) | — | — | — | — |
| OUT | HOOD | — | — | **−$60.32** | `portfolio_sell` | 22.25h | −3.36 |
| OUT | NVDA | — | — | −$1.03 | `portfolio_sell` | 1.75h | −2.69 |
| OUT | WMT | — | — | +$2.38 | `sentiment_reversal` | 1.00h | −7.00 |
| OUT | NOW | — | — | −$19.60 | `portfolio_sell` | 1.75h | **+3.57** |
| | | | | **−$78.57** | | | |

## The 105-minute exit clock

Five of the six same-session S4 round trips this week were held for **exactly 1.75h**:

| Date | Symbol | Held | Exit reason | net P&L |
|------|--------|------|-------------|---------|
| 08-18 | HD | 1.75h | `portfolio_sell` | +$2.69 |
| 08-18 | NVDA | 1.75h | `portfolio_sell` | +$3.12 |
| 08-19 | HD | 1.75h | `portfolio_sell` | +$3.91 |
| 08-20 | NVDA | 1.75h | `portfolio_sell` | −$1.03 |
| 08-20 | NOW | 1.75h | `portfolio_sell` | −$19.60 |
| 08-20 | WMT | 1.00h | `sentiment_reversal` (bypasses the guard) | +$2.38 |

105 min = `_HOLD_MINIMUM_MINUTES = 90` (`src/workers/portfolio_scheduler.py:1686`) + one 15-min cycle. The hold-minimum guard has become a de-facto holding period: positions sell at the first cycle after it expires. Profile matches #61 — many tiny wins, occasional large losses. Aug 20 alone (−$78.57) produced 91% of the cumulative loss #61 measured across 112 historical same-day exits (−$86.45).

## Findings deliberately NOT given a new issue

| Finding | Why not |
|---------|---------|
| **Sector concentration**: 14/16 captured movers on Aug 18 were semis, −$413.87 MTM in one day | Already tracked. #29 (flip `max_sector_exposure` 0.10; confirmed `0.0` at `config/trading.yaml:263`) and #165 (S1 book never rotates, 07-14 semis cohort). #29 already documents the cap is forward-only ("Scala solo NEW BUY"), so it would not have prevented this. Evidence added here rather than duplicated. |
| **`quota_*` metrics exceed 1.0 on 6 of 10 entries** (HD 4.51, AVGO 3.50, HOOD 1.94, NOW 1.65, NVDA `quota_nel_gap` −1.13) | **Checked and dropped — not a defect.** Values >1 are legitimate by design; `tests/analysis/test_dossier_book.py:230` asserts 1.2 explicitly. `denominatore_degenere` correctly flags the truly uninterpretable cases. |
| **S4 declares `RebalanceFrequency.DAILY`** (`src/strategies/s4/config.py:40`) while the live path re-ranks every 15 min | Not an oversight — `portfolio_scheduler.py:500-506` documents the exclusion of S4 from `_REBALANCE_CLOCK_STRATEGIES` deliberately and names it an operator decision. Folded into #334 as the decision it already is, not filed as a bug. |
| **HOOD flip**: strong bearish above-gate signal (−0.435) on Aug 18, long entry on Aug 19 at percentile 0.866 | News genuinely changed between sessions (−4.90% then +4.63%). No defensible defect claim; the entry-timing half is already #327. |
| **NOW**: a `NO_NEWS` miss on Aug 19 ($141.95), bought by S4 on Aug 20 at percentile 0.914 and closed at −$19.60 | Not a separate mechanism — it is #324 and #334 intersecting. Recorded in #333 as narrative context the report failed to connect. |
| **TSLA entry date typo** ("07-18" for 08-18) in the Aug 19 report §4 | Cosmetic; no downstream consumer. |

## Assessment of the original seven

#324, #325, #326 are accurate and well-scoped — no changes. #327, #328, #329, #330 each had a factual error or a material omission, corrected in-thread above rather than by re-filing. The systematic weakness of the first pass was that it **worked from the daily reports' prose and not from the dossier JSON**, so wherever a report omitted or misattributed something, the issue inherited it. #333 exists to close that gap structurally.

---

*Generated by weekly findings cron job — Saturday Aug 22, 2026 09:00 UTC*
*First pass performed on a non-Opus model (Claude Code Opus unavailable — session limit reached, resets 1pm Europe/Rome) — issues #324-#330*
*Second pass (Opus retry) — Saturday Aug 22, 2026: verification, corrections and issues #333-#336*