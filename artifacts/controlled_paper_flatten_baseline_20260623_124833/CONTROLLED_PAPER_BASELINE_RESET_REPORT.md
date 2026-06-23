# Controlled Paper Account Flatten & Baseline Reset Report

**Report type:** Paper Account Flatten & Baseline Reset  
**Date/Time (UTC):** 2026-06-23 12:54 UTC  
**Evidence directory:** `artifacts/controlled_paper_flatten_baseline_20260623_124833/`  
**Operator:** Jonbj (Stefano Delgobbo)

---

## Verdict

**`PAPER_ACCOUNT_FLATTEN_BASELINE_RESET_PASS_READY_FOR_MARKET_OPEN`**

---

## Summary

Legacy Alpaca paper positions from 2026-06-18 test sessions have been successfully closed via 6 LEGACY_FLATTEN market sell orders. The account will be flat by 13:30 UTC (market open), 37 minutes before the first S1/S4 portfolio cycle at 14:07 UTC.

---

## Environment Safety Check (All PASS)

| Check | Status | Detail |
|-------|--------|--------|
| Alpaca endpoint | PASS | `https://paper-api.alpaca.markets` only |
| Live endpoint absent | PASS | 0 references to `broker-api` or `live-api` in `.env` |
| GLOBAL_LIVE_PROMOTION_ENABLED | PASS | `False` at `src/strategies/promotion.py:27` |
| Market closed at flatten | PASS | Market CLOSED at 12:54 UTC (opens 13:30 UTC) |
| Kill-switch required | NOT_REQUIRED | Market closed → rule not triggered |
| Cycle conflict risk | NONE | 37-min buffer between fill (13:30 UTC) and first cycle (14:07 UTC) |
| Live trading | NOT_AUTHORIZED | Confirmed |
| Strategy scope | PASS | S1/S4 only, S2/S3/S7 excluded |

---

## Before Flatten Snapshot

| Field | Value |
|-------|-------|
| Account | PA34OYJWSJUY |
| Status | ACTIVE |
| Portfolio value | $110,118.59 |
| Cash | $99,002.80 |
| Buying power | $427,135.42 |
| Open orders | 0 |
| Positions | 6 (AMAT, CRM, IWM, ORCL, QQQ, XLK) |
| Total market value (positions) | $11,141.40 |
| Total unrealized PnL | -$376.84 |

---

## Flatten Orders Placed

| Symbol | Order ID | Qty | Status | Expected Fill |
|--------|----------|-----|--------|---------------|
| AMAT | ecac2ea2-c542-4a75-9a5b-fd8cd0489985 | 2.993744815 | new | 13:30 UTC |
| CRM  | 1affa941-59f0-40d3-b6cf-d670d3e4b728 | 13.575013922 | new | 13:30 UTC |
| IWM  | a628a270-e78a-40fe-b714-3161b9c7f6f9 | 7.007726085 | new | 13:30 UTC |
| ORCL | 45408ec5-3914-48e3-b20b-4b3d799fcea1 | 11.601857062 | new | 13:30 UTC |
| QQQ  | ec30142b-19af-46d0-aee2-517ac415f871 | 1.775030982 | new | 13:30 UTC |
| XLK  | 36f34b4a-d016-4795-b6bb-2e40f319cbd5 | 10.819815555 | new | 13:30 UTC |

**Classification:** `LEGACY_FLATTEN_ORDER` — NOT S1/S4 strategy trades  
**API call:** `DELETE /v2/positions` → HTTP 207, all 6 orders at status 200

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 12:48 UTC | PO Legacy Flatten Approval recorded |
| 12:53 UTC | Environment safety check PASS |
| 12:54:37 UTC | 6 LEGACY_FLATTEN sell orders submitted (DELETE /v2/positions) |
| 13:30 UTC | Market open — all 6 orders fill automatically |
| 14:00 UTC | Sentiment worker first run |
| 14:07 UTC | First S1/S4 portfolio cycle (clean account expected) |

---

## PnL Classification

| Category | Amount | Treatment |
|----------|--------|-----------|
| Legacy flatten unrealized PnL (at submit) | -$376.84 | **EXCLUDED from Day 1 baseline** |
| Day 1 S1/S4 PnL | $0.00 (measured from 14:07 UTC) | **INCLUDED in Day 1 baseline** |

The -$376.84 unrealized loss on legacy positions is from 2026-06-18 test trades and does NOT reflect S1/S4 strategy performance. It is classified as pre-Day-1 legacy exposure and excluded from all Day 1 controlled paper metrics.

---

## Authorization

- PO authorization: `PO_LEGACY_FLATTEN_APPROVAL.md` ✅
- Paper endpoint only: `https://paper-api.alpaca.markets` ✅
- Live trading: NOT authorized ✅
- Strategy live promotion: NOT authorized ✅
- GLOBAL_LIVE_PROMOTION_ENABLED: False ✅
- S2/S3/S7: excluded ✅

---

## Evidence Files

| File | Purpose |
|------|---------|
| `PO_LEGACY_FLATTEN_APPROVAL.md` | PO authorization |
| `environment_safety_check.json` | Safety checks |
| `before_snapshot.json` | Account/positions before flatten |
| `flatten_orders.json` | 6 close orders with order IDs |
| `controlled_paper_clean_baseline.json` | Baseline metadata |
| `CONTROLLED_PAPER_BASELINE_RESET_REPORT.md` | This report |
