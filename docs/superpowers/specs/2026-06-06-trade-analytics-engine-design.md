# Trade Analytics Engine — Design Spec

**Date:** 2026-06-06  
**Status:** Approved  
**Scope:** Phase A of the P&L Improvement Roadmap — multi-dimensional trade analytics surfaced in the frontend, plus real-time postmortem diagnosis on losing trades

---

## Context

The system already records closed trades in the `trades` table (entry price, exit price, P&L, signal_id, regime_mult, timestamps). `postmortem.py` exists with 10 diagnosis categories but is dead code — never called. This phase wires it and adds analytics views across 5 dimensions.

---

## Approach: Analytics-on-Read (no new tables except one column)

All analytics are computed on-the-fly via SQL GROUP BY queries. No materialized tables, no separate time-series store. At current paper-trading volume, PostgreSQL aggregation with existing indexes is sufficient.

One new column: `trades.postmortem_diagnosis TEXT` (nullable) — written at trade close for losses only.

---

## Section 1: Analytics Dimensions

All computed from `trades` + JOIN to `sentiment_signals` on `signal_id`.

| Dimension | Source | Output columns |
|---|---|---|
| Per-symbol | `trades.symbol` | symbol, trade_count, win_rate, avg_net_pnl, total_net_pnl |
| Per-regime | `trades.regime_mult` bucketed | regime_label, trade_count, win_rate, avg_net_pnl, total_net_pnl |
| Time-of-day | `EXTRACT(HOUR FROM trades.entry_time AT TIME ZONE 'America/New_York')` | hour (9–16), trade_count, win_rate, avg_net_pnl |
| Score bucket | `sentiment_signals.score` in 0.1-wide bins | score_range, trade_count, win_rate, avg_net_pnl |
| Hold time | `exit_time - entry_time` bucketed | hold_bucket (<1h / 1–4h / 4h+ / overnight), trade_count, win_rate, avg_net_pnl |

Regime multiplier bucketing:
- ≤ 0.6 → "bear"
- 0.6–0.9 → "caution"
- 0.9–1.1 → "neutral"
- 1.1–1.35 → "bull"
- > 1.35 → "strong_bull"

Hold-time bucketing:
- < 1 hour → "<1h"
- 1–4 hours → "1–4h"
- 4–8 hours → "4–8h"
- > 8 hours and intraday → "extended"
- crosses midnight → "overnight"

---

## Section 2: Backend

### Migration

```sql
-- migrations/017_trade_analytics.sql
ALTER TABLE trades ADD COLUMN IF NOT EXISTS postmortem_diagnosis TEXT;
```

### New SQL queries in `pg_store.py`

Five new methods, each returns `list[dict]`:

```python
fetch_analytics_by_symbol(limit_days: int = 90) -> list[dict]
fetch_analytics_by_regime(limit_days: int = 90) -> list[dict]
fetch_analytics_by_hour(limit_days: int = 90) -> list[dict]
fetch_analytics_by_score_bucket(limit_days: int = 90) -> list[dict]
fetch_analytics_by_hold_time(limit_days: int = 90) -> list[dict]
```

Each query filters `WHERE exit_time IS NOT NULL AND entry_time >= NOW() - INTERVAL '%s days'`.

One additional method:
```python
fetch_trade_with_signal(trade_id: int) -> dict | None
```
Returns trade row joined with signal score/regime_mult — used by the postmortem endpoint.

### Postmortem wiring in `execution.py`

After `close_trade()` succeeds:

```python
if net_pnl < config.MIN_TRADE_PNL_THRESHOLD:
    trade_data = pg_store.fetch_trade_with_signal(trade_id)
    if trade_data:
        diagnosis = diagnose_loss(trade_data)
        pg_store.write_postmortem(trade_id, diagnosis)
```

`diagnose_loss()` imported from `src.performance.postmortem`. Returns a string label (e.g. `"LOW_SCORE_ENTRY"`, `"ADVERSE_REGIME"`, `"HIGH_VOLATILITY_EXIT"`).

New `pg_store` method:
```python
write_postmortem(trade_id: int, diagnosis: str) -> None
    # UPDATE trades SET postmortem_diagnosis = %s WHERE id = %s
```

### New API routes in `src/api/routes/trading.py`

```
GET /api/trades/analytics/by-symbol?days=90
GET /api/trades/analytics/by-dimension?dim=regime|hour|score|holdtime&days=90
GET /api/trades/postmortem/{trade_id}
```

`by-dimension` dispatches to the correct `fetch_analytics_by_*` method based on the `dim` query param.

---

## Section 3: Frontend

### Analytics Tab on `/trades` page

The existing Trades page (`frontend/src/pages/Trades.tsx`) gets a second tab "Analytics" alongside the existing trade table tab ("Trades").

Tab content — five panels in a 2-column grid:

1. **By Symbol** — horizontal bar chart, `total_net_pnl` per symbol, green/red fill based on sign
2. **By Hour of Day** — color table (9–16 EST): each cell shows win rate with background color (green spectrum for >50%, red for <50%)
3. **By LLM Score** — vertical bar chart, `avg_net_pnl` per 0.1-wide score bin; validates that higher scores → better outcomes
4. **By Hold Duration** — vertical bar chart, `avg_net_pnl` per hold bucket
5. **By Regime** — vertical bar chart, `avg_net_pnl` per regime label

New API client file: `frontend/src/api/analytics.ts`

Exports:
```typescript
interface DimensionRow {
  label: string;
  trade_count: number;
  win_rate: number;
  avg_net_pnl: number;
  total_net_pnl?: number;
}

fetchAnalyticsBySymbol(days?: number): Promise<DimensionRow[]>
fetchAnalyticsByDimension(dim: 'regime' | 'hour' | 'score' | 'holdtime', days?: number): Promise<DimensionRow[]>
```

### Postmortem in trade row expand

In the existing trade table row expand (already implemented), if `postmortem_diagnosis` is non-null, show it as a small badge/chip with a warning color. Example: `LOW_SCORE_ENTRY` displayed in amber.

No new routes in `App.tsx` required.

---

## Architecture Notes

- All new SQL goes in `pg_store.py` following existing patterns (sync psycopg2 methods)
- `diagnose_loss()` in `postmortem.py` is called synchronously inside `execution.py` after `close_trade()` — it is CPU-only (no I/O), so blocking is acceptable (<1ms)
- `limit_days` defaults to 90 everywhere; frontend hardcodes this for now (no user-facing date picker in this phase)
- No changes to the production execution hot path — postmortem runs only on trade close, not on every tick

---

## Out of Scope

- Phase B: feedback loop on consecutive losses (will be designed separately)
- Phase C: counterfactual analysis for SKIP decisions
- Date range picker in the analytics UI
- Export to CSV
- Alerting based on analytics
