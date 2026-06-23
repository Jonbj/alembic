# Approval Governance Diff

## Before
| strategy_id | mode | approved | updated_at |
|-------------|------|----------|------------|
| S1 | supervised_paper | **false** | 2026-06-21 08:50:06 |
| S2 | disabled | true | 2026-06-21 08:50:06 |
| S4 | paper | **false** | 2026-06-21 08:50:06 |

## After (`UPDATE 2` — 2026-06-23T11:24:24Z)
| strategy_id | mode | approved | updated_at |
|-------------|------|----------|------------|
| S1 | supervised_paper | **true** ← | 2026-06-23 11:24:24 ← |
| S2 | disabled | true (unchanged) | 2026-06-21 08:50:06 (unchanged) |
| S4 | paper | **true** ← | 2026-06-23 11:24:24 ← |

## What Changed
- S1: approved false→true, updated_at refreshed
- S4: approved false→true, updated_at refreshed
- S2: UNCHANGED (pre-existing inconsistency from preflight, not touched)

## What Did NOT Change
- mode: UNCHANGED for all strategies ✅
- target_mode: UNCHANGED (null) ✅
- promoted_by / promoted_at: UNCHANGED (null) ✅
- gate_report_id: UNCHANGED ✅
- S2/S7: NOT touched by this UPDATE ✅
- GLOBAL_LIVE_PROMOTION_ENABLED: False (hardcoded) ✅
- live_authorized: not in lifecycle table (enforced in API layer) ✅
- promotion_blocked: not in lifecycle table (enforced in API layer) ✅
