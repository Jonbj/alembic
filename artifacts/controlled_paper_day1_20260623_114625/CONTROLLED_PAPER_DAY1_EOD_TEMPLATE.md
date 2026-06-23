# CONTROLLED_PAPER_DAY1_EOD_REPORT

**Template generated:** 2026-06-23T11:50 UTC  
**To be completed by:** Operator (Jonbj) at market close (~20:00 UTC)  
**Evidence directory:** `artifacts/controlled_paper_day1_20260623_114625/`

---

## 1. Date / Session

| Item | Value |
|------|-------|
| Date | 2026-06-23 |
| Session | Day 1 — Controlled Paper |
| Market open | 13:30 UTC (09:30 EDT) |
| Market close | 20:00 UTC (16:00 EDT) |
| Report completed | __________ UTC |
| Operator | __________ |

---

## 2. Strategies Active

| Strategy | Mode | Approved | Cycles Participated | Notes |
|----------|------|----------|---------------------|-------|
| S1 | supervised_paper | true | __________ | |
| S4 | paper | true | __________ | |
| S2 | disabled | false | 0 (excluded) | |
| S7 | R&D | N/A | 0 (excluded) | |

---

## 3. Readiness Summary

| Time | stale_signals | worker_beat_lag | killswitch | db | redis |
|------|--------------|-----------------|------------|-----|-------|
| Pre-market (11:50 UTC) | true | true | false | ✅ | ✅ |
| At market open (13:30 UTC) | __________ | __________ | false | ✅ | ✅ |
| At market close (20:00 UTC) | __________ | __________ | false | ✅ | ✅ |

**stale_signals resolved at:** __________ UTC  
**worker_beat_lag resolved at:** __________ UTC (if applicable)

---

## 4. Decisions Summary

| Metric | Value |
|--------|-------|
| Total decisions at start of day | 356 |
| New decisions Day 1 | __________ |
| BUY decisions | __________ |
| SELL decisions | __________ |
| SKIP decisions | __________ |
| Decisions without reason | __________ (must be 0) |
| S2/S3/S7 decisions | __________ (must be 0) |
| Unexplained decisions | __________ (must be 0) |

**Decision quality issues:** (list any)

---

## 5. Orders Summary

| Metric | Value |
|--------|-------|
| Orders submitted | __________ |
| Orders accepted (paper) | __________ |
| Orders rejected | __________ |
| Partial fills | __________ |
| Zero-order case? | YES / NO |
| Zero-order reason (if YES) | __________ |

**Paper order IDs:** (list or see `day1_orders_after.json`)

---

## 6. Fills / Positions

| Metric | Value |
|--------|-------|
| Open positions at start | 16 (prior sessions) |
| New positions opened Day 1 | __________ |
| Positions closed Day 1 | __________ |
| Open positions at close | __________ |
| Pyramiding events (new pos on existing symbol) | __________ (should be 0 — BUG-5 guard) |

**New symbols entered (if any):** __________

---

## 7. PnL Gross / Net

> ⚠️ Do not invent fills. Only complete if real fill prices are available.

| Metric | Value |
|--------|-------|
| Gross PnL Day 1 | __________ USD |
| Estimated costs (slippage + spread) | __________ USD |
| Net PnL Day 1 | __________ USD |
| Open position unrealized | __________ USD |
| Notes | |

---

## 8. Costs / Slippage

| Metric | Value |
|--------|-------|
| Estimated commission | 0 (Alpaca paper: commission-free) |
| Estimated slippage | __________ |
| Total cost estimate | __________ |

---

## 9. Risk / Exposure

| Check | Value | Limit | Status |
|-------|-------|-------|--------|
| Total portfolio exposure | __________ % | 50% | ✅ / ⚠️ |
| Max single position | __________ % | 10% | ✅ / ⚠️ |
| Drawdown intraday | __________ % | 5% | ✅ / ⚠️ |
| VIX (if available) | __________ | 40 trigger | ✅ / ⚠️ |
| Regime multiplier | __________ | | |

---

## 10. Alerts / Warnings

List any alerts fired during Day 1:

| Time | Alert | Severity | Resolved? |
|------|-------|----------|-----------|
| | | | |

Worker log errors: (paste from `docker logs alembic-worker-1 --since=today`)

---

## 11. Kill-Switch Status

| Check | Time | Value |
|-------|------|-------|
| At market open | 13:30 UTC | false |
| At market close | 20:00 UTC | __________ |
| Any activation during day? | | YES / NO |
| If YES — reason and resolution | | __________ |

---

## 12. Data Freshness

| Metric | Value |
|--------|-------|
| stale_signals at first cycle | __________ |
| Signals used by S4 | __________ |
| Last signal age at first cycle | __________ min |
| Signal source (LLM models) | ensemble: kimi-k2.6:cloud + qwen3.5:cloud |
| News articles ingested | __________ |

---

## 13. Exceptions

List any unexpected events, errors, or anomalies during Day 1:

1. __________
2. __________
3. __________

Broker responses (unexpected rejects, partial fills):

---

## 14. Stop Criteria Hit?

| Criterion | Hit? | Notes |
|-----------|------|-------|
| Exposure > 50% | YES / NO | |
| Drawdown > 5% | YES / NO | |
| VIX spike | YES / NO | |
| Kill-switch activated | YES / NO | |
| Live endpoint detected | YES / NO | |
| S2/S3/S7 active | YES / NO | |
| Broker cascade reject | YES / NO | |
| Redis flush event | YES / NO | |

**If any stop criteria hit:** document action taken.

---

## 15. Recommendation for Day 2

Based on Day 1 results:

- [ ] Continue Day 2 with current configuration
- [ ] Investigate before Day 2 (list issues below)
- [ ] Pause paper trading pending remediation
- [ ] Escalate to PO

**Issues to address before Day 2:** (if any)

---

## 16. Non-Authorizations

This report confirms that during Controlled Paper Day 1:

- Live trading was NOT conducted
- Strategy live promotion was NOT performed
- GLOBAL_LIVE_PROMOTION_ENABLED remained False
- Live credentials were NOT used
- Live Alpaca endpoint was NOT contacted
- S2/S3/S7 were NOT active
- P3/P4 were NOT started

**Operator signature:** __________  
**Date/Time:** __________ UTC
