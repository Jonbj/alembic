# PO Legacy Paper Flatten Approval

**Document type:** PO Authorization for Legacy Paper Account Flatten  
**Date/Time (UTC):** 2026-06-23 12:48 UTC  
**Evidence directory:** `artifacts/controlled_paper_flatten_baseline_20260623_124833/`  
**PO Name:** Jonbj (Stefano Delgobbo — stefano.delgobbo@gmail.com)

---

## Purpose

Legacy Alpaca paper positions pre-date Controlled Paper Day 1 and must be flattened to create a clean baseline. These 16 DB trades / 6 Alpaca positions originate from testing sessions on 2026-06-18 and are classified as R-13 (existing open positions). Their PnL, fills, and exposure contaminate the Day 1 controlled paper baseline.

## Authorization Source

The PO (Jonbj / Stefano Delgobbo) has provided explicit operational authorization via the "Controlled Paper Account Flatten & Baseline Reset" task message on 2026-06-23, which requests:
> legacy Alpaca paper positions be closed to create a clean baseline for Day 1 controlled paper.

## Approval

- [x] **PO approves legacy paper account flatten**
- [x] **Alpaca paper only** — endpoint `https://paper-api.alpaca.markets`
- [x] **Close legacy paper positions** — 6 open (AMAT, CRM, IWM, ORCL, QQQ, XLK)
- [x] **Cancel legacy paper open orders** — currently 0 open orders
- [x] **Exclude flatten PnL from Day 1 controlled paper PnL**
- [x] **Flatten orders classified as LEGACY_FLATTEN, not S1/S4 strategy orders**
- [x] **Keep live trading unauthorized**
- [x] **Keep strategy live promotion unauthorized**
- [x] **Keep GLOBAL_LIVE_PROMOTION_ENABLED=False**
- [x] **Keep S1/S4 controlled paper scope only** (paper/supervised_paper, no live)
- [x] **Keep S2/S3/S7 excluded**

## PO Details

| Field | Value |
|-------|-------|
| PO Name | Jonbj (Stefano Delgobbo) |
| Authorization form | Explicit operational task instruction, 2026-06-23 |
| Timestamp | 2026-06-23 12:48 UTC |
| Reason | Remove legacy test positions from 2026-06-18 to create clean Day 1 baseline |
| Evidence directory | `artifacts/controlled_paper_flatten_baseline_20260623_124833/` |
| Prior sign-off reference | `artifacts/controlled_paper_day1_20260623_114625/PO_FINAL_SIGNOFF_RECORDED.md` |

## What This Approval Does NOT Include

| Item | Status |
|------|--------|
| Live trading | ❌ NOT authorized |
| Strategy live promotion | ❌ NOT authorized |
| GLOBAL_LIVE_PROMOTION_ENABLED=True | ❌ NOT authorized |
| S2/S3/S7 in scope | ❌ NOT authorized |
| Alpha/parameter changes | ❌ NOT authorized |
| Risk config changes | ❌ NOT authorized |
| P3/P4 | ❌ NOT started |
| Live account touch | ❌ PROHIBITED |
