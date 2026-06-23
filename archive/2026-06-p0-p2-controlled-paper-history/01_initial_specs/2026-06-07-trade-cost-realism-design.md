# Trade Cost Realism — Design Spec
**Date:** 2026-06-07  
**Status:** Approved  
**Scope:** Shared cost module, tier-based stop-loss, real cost accounting in live trades, cost analysis report, IC net-of-costs

---

## Problem

The system has two disconnected cost models:
1. **Backtest** uses `RealisticCostModel` (spread tiers + Almgren-Chriss impact + regulatory fees).
2. **Live paper trading** uses `entry_notional * 0.0005` (flat 5 bps hardcoded in `pg_store.py:417`) — understating costs by 4× for small-cap symbols with 20 bps real spread.
3. **Stop-loss** is fixed at 2% for all symbols. Small/mid-cap volatility (daily 1.5–3%) triggers stop-losses too frequently, generating buy → stop-loss → buy churn that accumulates friction costs.
4. **IC/ICIR** in backtest reports are gross-of-costs, making signal quality appear stronger than it is in practice.

---

## Architecture

Introduce a shared `src/costs/` module consumed by both live execution and the backtest IC calculator. The existing `src/backtest/costs/` module is **not modified** — it continues to serve the backtest engine's `Order`/`MarketSnapshot` typed interface.

```
src/costs/
├── __init__.py       # exports TradeCostCalculator, CostBreakdown
└── calculator.py     # core logic
```

All components read `config/cost_model.yaml` as the single source of truth for spread tiers, stop-loss percentages, and impact parameters.

---

## Section 1: `src/costs/calculator.py`

### `CostBreakdown` dataclass

```python
@dataclass
class CostBreakdown:
    spread_cost_bps: float       # roundtrip half-spread × 2
    impact_cost_bps: float       # Almgren-Chriss √(order_usd / adv_usd)
    regulatory_cost_usd: float   # SEC Section 31 + FINRA TAF (sells only)
    total_cost_bps: float        # spread_cost_bps + impact_cost_bps
    total_cost_usd: float        # (total_cost_bps / 10_000 × notional) + regulatory_cost_usd
```

### `TradeCostCalculator`

```python
class TradeCostCalculator:
    def __init__(self, config_path: Path = Path("config/cost_model.yaml"))
    def compute(symbol, notional, qty, fill_price, side, adv_usd=None) -> CostBreakdown
    def stop_loss_pct(symbol) -> float
```

**`compute()` logic:**
1. Look up `spread_bps` for `symbol` via tier (A/B/C/D). Round-trip = `spread_bps` (both legs combined).
2. Estimate market impact: `k × √(notional / adv_usd)` where `adv_usd` defaults to `10_000_000 × fill_price` (conservative fallback for symbols without live ADV data).
3. `total_cost_bps = spread_bps + impact_bps`
4. `total_cost_usd = (total_cost_bps / 10_000) × notional + regulatory_cost_usd`
5. Regulatory fees on sells only: `(sec_fee × qty × fill_price) + (finra_taf × qty)`

**`stop_loss_pct()` logic:**
- Reads tier for symbol from `cost_model.yaml`.
- Returns per-tier value. Falls back to module constant `STOP_LOSS_PCT = 0.02` if YAML unavailable.

---

## Section 2: `config/cost_model.yaml` changes

Add `stop_loss_pct` to each spread tier:

```yaml
spread_tiers:
  tier_a:
    symbols: [SPY, QQQ, IWM, VOO, VTI, GLD, TLT, IEF, SHY, AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA]
    spread_bps: 1.5
    stop_loss_pct: 0.020
  tier_b:
    symbols: [VEA, VWO, EWJ, LQD, HYG, TIP, DBC, VNQ, XLF, XLK, XLE, XLV, AMD, AVGO, QCOM, TXN, INTC, MU, ASML, ARM, AMAT, TSM, MRVL, DELL, CRM, ADBE, ORCL, NOW, SNOW, CSCO, JPM, BAC, GS, MS, WFC, C, AXP, MA, V, BRK.B, WMT, COST, MCD, SBUX, NKE, DIS, CMCSA, HD, NFLX, JNJ, PFE, MRK, UNH, ABBV, LLY, NVO, PG, BA, GE, GM, F, CAT, MMM, CVX, XOM, T, VZ, TMUS]
    spread_bps: 5.0
    stop_loss_pct: 0.035
  tier_c:
    symbols: []
    spread_bps: 10.0
    stop_loss_pct: 0.040
  tier_d:
    default: true
    spread_bps: 20.0
    stop_loss_pct: 0.050
```

Note: mega-cap individual equities (AAPL, MSFT, NVDA, etc.) are promoted to tier_a alongside ETFs, since they trade with sub-2 bps spreads. This corrects the previous default assignment of all non-ETF equities to tier_d.

---

## Section 3: Database migration `020_trade_cost_breakdown.sql`

```sql
ALTER TABLE trades
  ADD COLUMN cost_bps              NUMERIC,
  ADD COLUMN cost_usd              NUMERIC,
  ADD COLUMN spread_cost_bps       NUMERIC,
  ADD COLUMN impact_cost_bps       NUMERIC,
  ADD COLUMN regulatory_cost_usd   NUMERIC;
```

All columns are `NULLABLE`. Existing closed trades retain their `slippage_est` value and have `NULL` for the new columns. The weekly report skips `NULL` rows from cost analysis with an explicit note.

`slippage_est` is retained for backward compatibility and is populated with `cost_usd` on new trade closes.

`net_pnl` formula changes from:
```sql
gross_pnl - (entry_notional * 0.0005)
```
to:
```sql
gross_pnl - cost_usd
```

---

## Section 4: `src/store/pg_store.py` changes

`TradeCostCalculator` is injected into `PgStore.__init__()` with a default that reads `config/cost_model.yaml`. No change to the existing external interface.

`close_trade()` is updated:
1. After computing `gross_pnl`, call `cost_calc.compute(symbol, entry_notional, qty, exit_price, "SELL")`.
2. Persist all five breakdown columns.
3. Set `slippage_est = cost.total_cost_usd` for backward compatibility.
4. Set `net_pnl = gross_pnl - cost.total_cost_usd`.

The SQL query `_CLOSE_TRADE` is updated to include the new columns.

---

## Section 5: `src/workers/execution.py` changes

`TradeCostCalculator` is instantiated once per execution cycle (not per symbol).

Stop-loss logic change:
- Replace `stop_loss_pct` (module constant) with `cost_calc.stop_loss_pct(symbol)` for both entry stop computation and open-position stop check.
- `trading.yaml` `risk.stop_loss` acts as a global override: if the key exists in the YAML it always takes precedence over per-tier values (allows emergency override without code change).
- Module fallback `STOP_LOSS_PCT = 0.02` stays as last resort if YAML is unavailable.

---

## Section 6: `src/workers/performance.py` — cost analysis section

New section added to the weekly report, reading from `trades` where `cost_bps IS NOT NULL`:

| Metric | Formula |
|---|---|
| `avg_cost_bps` | `AVG(cost_bps)` over period |
| `total_cost_usd` | `SUM(cost_usd)` |
| `cost_drag_pct` | `SUM(cost_usd) / SUM(entry_notional)` |
| `annualized_cost_drag_bps` | `cost_drag_pct × (252 / weeks_sampled) × 10_000` |

Per-symbol breakdown: `symbol`, `avg_spread_cost_bps`, `avg_impact_cost_bps`, sorted descending by `avg_cost_bps`. Identifies which tickers drain most friction.

---

## Section 7: IC net-of-costs in backtest report

In the IC calculation module, before computing correlation between signal score and forward return:

```python
cost_bps = cost_calc.compute(symbol, notional=1.0, qty=1.0, fill_price=1.0, side="SELL").total_cost_bps
net_return = forward_return - (cost_bps / 10_000)
# IC netto computed on net_return
```

The `notional=1.0, fill_price=1.0` trick computes fractional cost (bps only, not USD). At this scale the market impact term is negligible (< 0.01 bps), so effectively `total_cost_bps ≈ spread_bps` — which is the dominant and most stable cost component for IC adjustment. This is the intended behavior: IC is adjusted for friction cost (spread), not for size-dependent impact.

New JSON output fields alongside existing gross fields:
```json
"ic_1h_net":    { "composite_ic": ..., "spearman_ic": ..., "weighted_hit_rate": ..., "brier_score": ..., "sample_count": ... },
"icir_1h_net":  { "icir": ..., "ic_mean": ..., "ic_std": ..., "newey_west_std": ..., "lag": ..., "sample_count": ... },
"ic_4h_net":    { ... },
"icir_4h_net":  { ... },
"ic_24h_net":   { ... },
"icir_24h_net": { ... }
```

Gross fields (`ic_1h`, `icir_1h`, etc.) are **not modified** — backward compatibility with existing report consumers.

---

## Testing

- `tests/costs/test_calculator.py`: unit tests for `TradeCostCalculator` covering all 4 tiers, both sides (BUY/SELL), regulatory fees on sells only, stop_loss_pct per tier, fallback behavior.
- `tests/store/test_pg_store.py`: existing `close_trade` tests updated to assert new cost columns are populated; assert `net_pnl = gross_pnl - cost_usd`.
- `tests/workers/test_execution.py`: assert stop-loss threshold is tier-based for tier_a and tier_d symbols.
- `tests/workers/test_performance.py`: assert cost analysis section present when trades have `cost_bps IS NOT NULL`.
- Backtest IC test: assert `ic_1h_net.composite_ic < ic_1h.composite_ic` (net is always ≤ gross).

---

## Out of Scope

- Fetching real-time ADV from Alpaca API (would improve impact estimate accuracy; deferred to future iteration).
- Retroactively backfilling `cost_bps` for closed trades (old data uses `slippage_est` as-is).
- UI changes to the dashboard (separate task).
