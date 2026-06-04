# Alembic Paper Trading Log

## Start Date

**Official 90-day validation start: 2026-06-05**

The 4 critical bugs (pool leak, ensemble weights never read, LOO ICIR wrong grouping, duplicate BUY) were fixed and committed on 2026-06-04. The 90-day clock starts the following day so the system runs from a clean state with all fixes active.

The clock ends on **2026-09-03** (90 calendar days from 2026-06-05).

---

## Pre-Start Checklist

| Item | Status |
|------|--------|
| All 4 critical bugs fixed and verified in live logs | ✅ done (committed 2026-06-04) |
| DB migration `news_source` applied | ✅ done |
| Always-on host confirmed | Desktop, always on — acceptable for now |
| S1 threshold tuned if needed | Pending — see Tier 1 item 3 in NEXT_STEPS_V2.md |

The 90-day clock starts only once all rows above are checked. The first row still pending at 2026-06-05 is **S1 threshold tuning** — this may be addressed within the first week of the run.

---

## Metrics to Track

### Weekly metrics (track from day 1)

| Metric | Source | Acceptable Range |
|--------|--------|-----------------|
| Articles ingested/day | Worker logs | > 20 across all connectors |
| Scores generated/day | `signals` table | > 0 for every trading day |
| BUY orders placed/week | Alpaca orders | > 0 once threshold is tuned |
| Fill quality (slippage) | Alpaca fills vs signal price | < 15 bps average |
| Strategy weight drift | `weight_update_log` | Within 5% of target allocation |
| Daily PnL vs SPY | `portfolio_cycles` | Not trailing SPY by > 2σ over any 30-day window |
| Kill-switch activations | Redis + Telegram alerts | 0 from bugs; market-driven activations documented |
| Celery task error rate | Worker logs | < 2% per task type sustained |
| Forward-return worker | `sentiment_signals.forward_return` | Non-null for > 90% of signals after T+1 |

### 90-Day Go/No-Go Criteria

**PASS** (all must be true):
- System runs 90 consecutive calendar days without unhandled Python exceptions that abort a cycle
- No pool exhaustion events post-fix
- Ensemble weights are being read and rebalanced (visible in weekly weight suggestions)
- No duplicate BUY events observed after Bug 4 fix
- Live Sharpe ≥ −0.3 annualised
- All CRITICAL and HIGH issues (#1–#11) resolved before claiming pass

**FAIL** (any one disqualifies the run):
- Pool exhaustion observed post-fix
- Kill-switch triggered by a code bug (not market conditions)
- Celery task error rate > 10% sustained for > 3 consecutive trading days
- Duplicate orders observed post-Bug-4-fix
- System offline > 72 consecutive hours (host failure)

---

## Daily Log

| Date | Event | Notes |
|------|-------|-------|
| 2026-06-04 | Critical bugs #1–#4 fixed, `news_source` migration applied. 16 portfolio cycles completed pre-fix. | Bug 1: pool leak; Bug 2: weights never read; Bug 3: LOO ICIR wrong grouping; Bug 4: duplicate BUY. Fixes committed to `main`. |
