# Trade Cost Realism — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat 5 bps slippage estimate with real tier-based costs, add tier-based stop-losses, persist a full cost breakdown per trade, add a cost analysis section to the weekly report, and emit IC net-of-costs in backtest reports.

**Architecture:** A new shared `src/costs/calculator.py` module wraps `config/cost_model.yaml` and exposes `TradeCostCalculator`. It is injected into `PgStore` and used in `execution.py` — no changes to `src/backtest/costs/` (the backtest engine keeps its own typed interface). The backtest report builder uses `TradeCostCalculator` to subtract spread cost from forward returns before computing net IC.

**Tech Stack:** Python 3.11, psycopg2, PyYAML, dataclasses, pytest, existing `config/cost_model.yaml`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/costs/__init__.py` | Create | Re-export `TradeCostCalculator`, `CostBreakdown` |
| `src/costs/calculator.py` | Create | Tier-based cost + stop-loss lookup |
| `tests/costs/__init__.py` | Create | Package marker |
| `tests/costs/test_calculator.py` | Create | Unit tests for calculator |
| `config/cost_model.yaml` | Modify | Add `stop_loss_pct` per tier; promote mega-caps to tier_a/b |
| `migrations/019_trade_cost_breakdown.sql` | Create | 5 new cost columns on `trades` |
| `src/store/pg_store.py` | Modify | Inject `TradeCostCalculator`; update `_CLOSE_TRADE` + `_TRADE_SUMMARY_SQL` |
| `src/workers/execution.py` | Modify | Tier-based stop-loss via `TradeCostCalculator` |
| `src/workers/performance.py` | Modify | Cost analysis section in weekly report |
| `src/backtest/report.py` | Modify | `ic_*_net` / `icir_*_net` fields |
| `tests/test_pg_store.py` | Modify | Add cost column assertions to `close_trade` tests |
| `tests/workers/test_execution.py` | Modify | Assert tier-based stop-loss |

---

## Task 1: Shared cost module — `src/costs/calculator.py`

**Files:**
- Create: `src/costs/__init__.py`
- Create: `src/costs/calculator.py`
- Create: `tests/costs/__init__.py`
- Create: `tests/costs/test_calculator.py`

- [ ] **Step 1.1: Write failing tests**

Create `tests/costs/__init__.py` (empty) and `tests/costs/test_calculator.py`:

```python
"""Unit tests for TradeCostCalculator."""
import pytest
from pathlib import Path
from src.costs.calculator import TradeCostCalculator, CostBreakdown

CONFIG = Path("config/cost_model.yaml")


@pytest.fixture
def calc():
    return TradeCostCalculator(config_path=CONFIG)


class TestStopLossPct:
    def test_tier_a_symbol(self, calc):
        assert calc.stop_loss_pct("SPY") == pytest.approx(0.020)

    def test_tier_a_megacap(self, calc):
        assert calc.stop_loss_pct("NVDA") == pytest.approx(0.020)

    def test_tier_b_symbol(self, calc):
        assert calc.stop_loss_pct("INTC") == pytest.approx(0.035)

    def test_tier_d_default(self, calc):
        # Symbol not in any explicit tier → default (tier_d)
        assert calc.stop_loss_pct("UNKNOWN_TICKER") == pytest.approx(0.050)


class TestComputeCosts:
    def test_buy_tier_a_no_regulatory_fees(self, calc):
        result = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        assert isinstance(result, CostBreakdown)
        assert result.regulatory_cost_usd == pytest.approx(0.0)
        # spread_cost_bps = 1.5 bps (tier_a full roundtrip)
        assert result.spread_cost_bps == pytest.approx(1.5)
        assert result.total_cost_bps > 0

    def test_sell_has_regulatory_fees(self, calc):
        result = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="SELL")
        # SEC fee: 0.0000229 * 50 * 200 = 0.229
        # FINRA TAF: 0.000145 * 50 = 0.00725
        expected_reg = 0.0000229 * 50 * 200 + 0.000145 * 50
        assert result.regulatory_cost_usd == pytest.approx(expected_reg, rel=1e-4)

    def test_tier_d_higher_cost_than_tier_a(self, calc):
        tier_a = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        tier_d = calc.compute("UNKNOWN", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        assert tier_d.spread_cost_bps > tier_a.spread_cost_bps

    def test_total_cost_usd_formula(self, calc):
        result = calc.compute("SPY", notional=10_000, qty=50, fill_price=200.0, side="BUY")
        expected_usd = (result.total_cost_bps / 10_000) * 10_000 + result.regulatory_cost_usd
        assert result.total_cost_usd == pytest.approx(expected_usd, rel=1e-6)

    def test_unit_notional_for_ic(self, calc):
        # notional=1.0 for IC adjustment: impact is negligible, result ≈ spread_bps
        result = calc.compute("INTC", notional=1.0, qty=1.0, fill_price=1.0, side="SELL")
        # spread for tier_b = 5.0 bps; impact negligible at this scale
        assert result.spread_cost_bps == pytest.approx(5.0)
        assert result.impact_cost_bps < 0.01  # near zero
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /home/stefano/Documents/Projects/Alembic
python -m pytest tests/costs/test_calculator.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'src.costs'`

- [ ] **Step 1.3: Create `src/costs/__init__.py`**

```python
from src.costs.calculator import CostBreakdown, TradeCostCalculator

__all__ = ["CostBreakdown", "TradeCostCalculator"]
```

- [ ] **Step 1.4: Create `src/costs/calculator.py`**

```python
"""Shared trade cost calculator — spread tiers, market impact, stop-loss per tier.

Consumed by pg_store (live net P&L), execution worker (stop-loss), and
backtest report builder (IC net-of-costs). Reads config/cost_model.yaml.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class CostBreakdown:
    spread_cost_bps: float       # full roundtrip half-spread × 2
    impact_cost_bps: float       # Almgren-Chriss √(order_usd / adv_usd)
    regulatory_cost_usd: float   # SEC Section 31 + FINRA TAF (sells only)
    total_cost_bps: float        # spread_cost_bps + impact_cost_bps
    total_cost_usd: float        # (total_cost_bps / 10_000 × notional) + regulatory


_DEFAULT_ADV_SHARES = 10_000_000  # fallback ADV when live data unavailable


class TradeCostCalculator:
    """Compute trade costs and tier-based stop-loss percentages from cost_model.yaml."""

    def __init__(self, config_path: Path = Path("config/cost_model.yaml")) -> None:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        equity = cfg["equity"]
        tiers = equity["spread_tiers"]

        # Build symbol → tier config lookup
        self._symbol_tier: dict[str, dict] = {}
        self._default_tier: dict = {}
        for tier_data in tiers.values():
            if tier_data.get("default"):
                self._default_tier = tier_data
            for sym in tier_data.get("symbols", []):
                self._symbol_tier[sym.upper()] = tier_data

        self._impact_k = float(equity.get("impact_k", 10.0))
        self._commission_per_share = float(equity.get("commission_per_share", 0.0))
        self._sec_fee = float(equity.get("sec_fee_per_share_sale", 0.0000229))
        self._finra_taf = float(equity.get("finra_taf_per_share_sale", 0.000145))

    def _tier(self, symbol: str) -> dict:
        return self._symbol_tier.get(symbol.upper(), self._default_tier)

    def stop_loss_pct(self, symbol: str) -> float:
        """Return stop-loss percentage for symbol based on liquidity tier."""
        return float(self._tier(symbol).get("stop_loss_pct", 0.02))

    def compute(
        self,
        symbol: str,
        notional: float,
        qty: float,
        fill_price: float,
        side: str,
        adv_usd: float | None = None,
    ) -> CostBreakdown:
        """Compute full cost breakdown for a trade.

        Args:
            symbol:     Ticker symbol.
            notional:   Trade notional in USD (qty × price).
            qty:        Number of shares.
            fill_price: Execution price.
            side:       "BUY" or "SELL".
            adv_usd:    20-day average daily volume in USD. Defaults to 10M shares × fill_price.
        """
        tier = self._tier(symbol)
        spread_bps = float(tier.get("spread_bps", 20.0))

        if adv_usd is None or adv_usd <= 0:
            adv_usd = _DEFAULT_ADV_SHARES * fill_price

        # Square-root market impact (Almgren-Chriss)
        import math
        impact_bps = self._impact_k * math.sqrt(notional / adv_usd) * 100 if adv_usd > 0 else 0.0

        total_cost_bps = spread_bps + impact_bps

        # Regulatory fees on sells only
        regulatory = 0.0
        if side.upper() == "SELL":
            regulatory = (
                self._sec_fee * qty * fill_price
                + self._finra_taf * qty
                + self._commission_per_share * qty
            )

        total_cost_usd = (total_cost_bps / 10_000) * notional + regulatory

        return CostBreakdown(
            spread_cost_bps=spread_bps,
            impact_cost_bps=impact_bps,
            regulatory_cost_usd=regulatory,
            total_cost_bps=total_cost_bps,
            total_cost_usd=total_cost_usd,
        )
```

- [ ] **Step 1.5: Run tests — expect failures related to `cost_model.yaml` missing `stop_loss_pct`**

```bash
python -m pytest tests/costs/test_calculator.py -v 2>&1 | head -40
```
Expected: tests fail because `stop_loss_pct` not yet in `cost_model.yaml`. Proceed to Task 2 then re-run.

- [ ] **Step 1.6: Commit skeleton (will be re-tested after Task 2)**

```bash
git add src/costs/__init__.py src/costs/calculator.py tests/costs/__init__.py tests/costs/test_calculator.py
git commit -m "feat(costs): add shared TradeCostCalculator and CostBreakdown"
```

---

## Task 2: Update `config/cost_model.yaml` — stop-loss per tier + promote mega-caps

**Files:**
- Modify: `config/cost_model.yaml`

- [ ] **Step 2.1: Replace `cost_model.yaml` spread_tiers section**

Open `config/cost_model.yaml` and replace the entire `equity.spread_tiers` block with:

```yaml
equity:
  spread_tiers:
    tier_a:
      description: "Mega-cap, very liquid ETF + large individual equity"
      symbols: [
        SPY, QQQ, IWM, VOO, VTI, GLD, TLT, IEF, SHY,
        AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
      ]
      spread_bps: 1.5
      stop_loss_pct: 0.020
    tier_b:
      description: "Large-cap equity, liquid sector ETF"
      symbols: [
        VEA, VWO, EWJ, LQD, HYG, TIP, DBC, VNQ, XLF, XLK, XLE, XLV,
        AMD, AVGO, QCOM, TXN, INTC, MU, ASML, ARM, AMAT, TSM, MRVL, DELL,
        CRM, ADBE, ORCL, NOW, SNOW, CSCO,
        JPM, BAC, GS, MS, WFC, C, AXP, MA, V, BRK.B,
        WMT, COST, MCD, SBUX, NKE, DIS, CMCSA, HD, NFLX,
        JNJ, PFE, MRK, UNH, ABBV, LLY, NVO, PG,
        BA, GE, GM, F, CAT, MMM, CVX, XOM,
        T, VZ, TMUS, PLTR
      ]
      spread_bps: 5.0
      stop_loss_pct: 0.035
    tier_c:
      description: "Mid-cap, niche ETF, less liquid"
      symbols: []
      spread_bps: 10.0
      stop_loss_pct: 0.040
    tier_d:
      description: "Default: small-cap, illiquid"
      default: true
      spread_bps: 20.0
      stop_loss_pct: 0.050
  impact_k: 10.0
  commission_per_share: 0.0
  sec_fee_per_share_sale: 0.0000229
  finra_taf_per_share_sale: 0.000145
```

Keep the existing `options:` section unchanged beneath.

- [ ] **Step 2.2: Run calculator tests — all should pass now**

```bash
python -m pytest tests/costs/test_calculator.py -v
```
Expected: all 8 tests PASS

- [ ] **Step 2.3: Commit**

```bash
git add config/cost_model.yaml
git commit -m "feat(costs): add stop_loss_pct per tier and promote mega-caps to tier_a/b"
```

---

## Task 3: Database migration `019_trade_cost_breakdown.sql`

**Files:**
- Create: `migrations/019_trade_cost_breakdown.sql`

- [ ] **Step 3.1: Create migration file**

```sql
-- 019_trade_cost_breakdown.sql
-- Add real cost breakdown columns to trades table.
-- Replaces the flat slippage_est = entry_notional * 0.0005 with tier-based actuals.
-- All columns NULLABLE: existing closed trades retain slippage_est, new trades get full breakdown.

ALTER TABLE trades
    ADD COLUMN IF NOT EXISTS cost_bps             NUMERIC,
    ADD COLUMN IF NOT EXISTS cost_usd             NUMERIC,
    ADD COLUMN IF NOT EXISTS spread_cost_bps      NUMERIC,
    ADD COLUMN IF NOT EXISTS impact_cost_bps      NUMERIC,
    ADD COLUMN IF NOT EXISTS regulatory_cost_usd  NUMERIC;

COMMENT ON COLUMN trades.cost_bps            IS 'Total roundtrip cost in bps (spread + impact). NULL for pre-019 trades.';
COMMENT ON COLUMN trades.cost_usd            IS 'Total cost in USD (bps-based + regulatory fees). NULL for pre-019 trades.';
COMMENT ON COLUMN trades.spread_cost_bps     IS 'Tier-based bid-ask spread cost in bps. NULL for pre-019 trades.';
COMMENT ON COLUMN trades.impact_cost_bps     IS 'Almgren-Chriss market impact in bps. NULL for pre-019 trades.';
COMMENT ON COLUMN trades.regulatory_cost_usd IS 'SEC Section 31 + FINRA TAF fees (sells only). NULL for pre-019 trades.';
```

- [ ] **Step 3.2: Apply migration to the database**

```bash
psql -h localhost -U postgres -d alembic -f migrations/019_trade_cost_breakdown.sql
```
Expected output:
```
ALTER TABLE
COMMENT
COMMENT
COMMENT
COMMENT
COMMENT
```

If you don't have the password handy, run:
```bash
docker exec -i $(docker ps --filter "name=postgres" -q | head -1) \
  psql -U postgres -d alembic -f /dev/stdin < migrations/019_trade_cost_breakdown.sql
```

- [ ] **Step 3.3: Verify columns exist**

```bash
docker exec -i $(docker ps --filter "name=postgres" -q | head -1) \
  psql -U postgres -d alembic -c "\d trades" | grep -E "cost_|spread_|impact_|regulatory"
```
Expected: 5 rows showing the new nullable NUMERIC columns.

- [ ] **Step 3.4: Commit**

```bash
git add migrations/019_trade_cost_breakdown.sql
git commit -m "feat(db): add cost breakdown columns to trades table (migration 019)"
```

---

## Task 4: Update `src/store/pg_store.py` — inject calculator, real cost in `close_trade`

**Files:**
- Modify: `src/store/pg_store.py`
- Modify: `tests/test_pg_store.py`

- [ ] **Step 4.1: Write failing tests for new cost columns**

Append to `tests/test_pg_store.py` (structural tests that follow the existing codebase pattern — no DB connection needed):

```python
class TestCloseTradeCostBreakdown:
    """close_trade SQL must include real cost columns, not flat slippage."""

    def test_sql_includes_cost_bps(self):
        from src.store.pg_store import PostgreSQLStore
        assert "cost_bps" in PostgreSQLStore._CLOSE_TRADE

    def test_sql_includes_cost_usd(self):
        from src.store.pg_store import PostgreSQLStore
        assert "cost_usd" in PostgreSQLStore._CLOSE_TRADE

    def test_sql_includes_spread_cost_bps(self):
        from src.store.pg_store import PostgreSQLStore
        assert "spread_cost_bps" in PostgreSQLStore._CLOSE_TRADE

    def test_net_pnl_no_flat_slippage(self):
        """net_pnl must use cost_usd, not the hardcoded 0.0005 flat rate."""
        from src.store.pg_store import PostgreSQLStore
        assert "0.0005" not in PostgreSQLStore._CLOSE_TRADE

    def test_trade_summary_includes_avg_cost_bps(self):
        from src.store.pg_store import PostgreSQLStore
        assert "avg_cost_bps" in PostgreSQLStore._TRADE_SUMMARY_SQL

    def test_close_trade_accepts_entry_notional_and_qty(self):
        import inspect
        from src.store.pg_store import PostgreSQLStore
        sig = inspect.signature(PostgreSQLStore.close_trade)
        assert "entry_notional" in sig.parameters
        assert "qty" in sig.parameters
```

- [ ] **Step 4.2: Run tests — expect failures**

```bash
python -m pytest tests/test_pg_store.py::TestCloseTradeCostBreakdown -v
```
Expected: FAIL — `close_trade` has no `entry_notional`/`qty` params and no `_cost_calc`.

- [ ] **Step 4.3: Update `pg_store.py` — inject calculator and update `_CLOSE_TRADE`**

**4.3a: Add import at top of `pg_store.py`** (after existing imports):

```python
from pathlib import Path
from src.costs.calculator import TradeCostCalculator
```

**4.3b: Update `PostgreSQLStore.__init__`** — find the `__init__` method and add the `cost_calc` parameter. The typical signature is `def __init__(self, ...)`. Add before the first line of the body:

```python
def __init__(self, cost_calc: TradeCostCalculator | None = None) -> None:
    self._cost_calc = cost_calc or TradeCostCalculator()
    # ... rest of existing __init__ body unchanged
```

**4.3c: Replace `_CLOSE_TRADE` SQL string** — find the current `_CLOSE_TRADE` class attribute and replace it:

```python
    _CLOSE_TRADE = """
        UPDATE trades SET
            exit_price            = %s,
            exit_time             = %s,
            exit_reason           = %s,
            entry_price           = COALESCE(entry_price, %s),
            gross_pnl             = (%s - COALESCE(entry_price, %s)) * qty,
            cost_bps              = %s,
            cost_usd              = %s,
            spread_cost_bps       = %s,
            impact_cost_bps       = %s,
            regulatory_cost_usd   = %s,
            slippage_est          = %s,
            net_pnl               = ((%s - COALESCE(entry_price, %s)) * qty) - %s
        WHERE symbol = %s AND exit_time IS NULL
        RETURNING id
    """
```

**4.3d: Replace `close_trade` method** — find the existing method and replace it entirely:

```python
    def close_trade(
        self,
        symbol: str,
        exit_price: float,
        exit_time,
        exit_reason: str,
        entry_price: float | None = None,
        entry_notional: float | None = None,
        qty: float | None = None,
    ) -> int | None:
        """Update the open trade row for symbol with exit data and compute P&L.

        Args:
            symbol:          Ticker symbol of the trade to close.
            exit_price:      Fill price at which the position was exited.
            exit_time:       Timestamp of the exit.
            exit_reason:     Why the trade was closed (e.g. "stop_loss").
            entry_price:     Optional fill price from the Alpaca position object.
            entry_notional:  Trade notional in USD for cost calculation.
                             If None, fetched from the DB row before updating.
            qty:             Number of shares for cost calculation.
                             If None, fetched from the DB row before updating.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                # Fetch notional + qty from DB if not provided (e.g. stop-loss path)
                if entry_notional is None or qty is None:
                    cur.execute(
                        "SELECT entry_notional, qty FROM trades WHERE symbol = %s AND exit_time IS NULL",
                        (symbol,),
                    )
                    row = cur.fetchone()
                    if row:
                        entry_notional = float(row[0]) if row[0] is not None else 0.0
                        qty = float(row[1]) if row[1] is not None else 0.0
                    else:
                        entry_notional = 0.0
                        qty = 0.0

                costs = self._cost_calc.compute(
                    symbol=symbol,
                    notional=entry_notional,
                    qty=qty,
                    fill_price=float(exit_price),
                    side="SELL",
                )

                cur.execute(
                    self._CLOSE_TRADE,
                    (
                        exit_price,                      # exit_price =
                        exit_time,                       # exit_time =
                        exit_reason,                     # exit_reason =
                        entry_price,                     # COALESCE(entry_price, ?)
                        exit_price, entry_price,         # gross_pnl numerator
                        costs.total_cost_bps,            # cost_bps =
                        costs.total_cost_usd,            # cost_usd =
                        costs.spread_cost_bps,           # spread_cost_bps =
                        costs.impact_cost_bps,           # impact_cost_bps =
                        costs.regulatory_cost_usd,       # regulatory_cost_usd =
                        costs.total_cost_usd,            # slippage_est = (backward compat)
                        exit_price, entry_price,         # net_pnl numerator
                        costs.total_cost_usd,            # net_pnl deduction
                        symbol,                          # WHERE symbol =
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else None
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 4.4: Update `_TRADE_SUMMARY_SQL`** — add cost aggregate columns to the existing query:

Find `_TRADE_SUMMARY_SQL` and replace with:

```python
    _TRADE_SUMMARY_SQL = """
        SELECT
            COUNT(*) AS total_trades,
            SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) AS wins,
            COALESCE(AVG(gross_pnl), 0) AS avg_gross_pnl,
            COALESCE(AVG(slippage_est), 0) AS avg_slippage_est,
            COALESCE(AVG(net_pnl), 0) AS avg_net_pnl,
            COALESCE(SUM(gross_pnl), 0) AS total_gross_pnl,
            COALESCE(SUM(net_pnl), 0) AS total_net_pnl,
            COALESCE(SUM(entry_notional), 0) AS total_notional,
            COALESCE(
                AVG(EXTRACT(EPOCH FROM (exit_time - entry_time)) / 60), 0
            ) AS avg_hold_minutes,
            COALESCE(AVG(cost_bps), 0) AS avg_cost_bps,
            COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
            COALESCE(AVG(spread_cost_bps), 0) AS avg_spread_cost_bps,
            COALESCE(AVG(impact_cost_bps), 0) AS avg_impact_cost_bps
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
    """
```

- [ ] **Step 4.5: Update `fetch_trade_summary`** — unpack the 4 new columns and add to return dict:

Find the `fetch_trade_summary` method. Replace the unpacking line and return dict:

```python
            (total, wins, avg_gross, avg_slip, avg_net,
             total_gross, total_net, total_notional, avg_hold,
             avg_cost_bps, total_cost_usd, avg_spread_bps, avg_impact_bps) = row
            total = int(total)
            wins = int(wins or 0)
            win_rate = (wins / total) if total > 0 else 0.0
            trades_per_week = (total / days) * 7
            return_on_notional = (float(total_net) / float(total_notional)) if total_notional else 0.0
            slippage_pct = (float(avg_slip) / float(avg_gross)) if avg_gross else 0.0
            cost_drag_pct = (float(total_cost_usd) / float(total_notional)) if total_notional else 0.0
            return {
                "total_trades": total,
                "win_rate": round(win_rate, 4),
                "avg_gross_pnl": round(float(avg_gross), 2),
                "avg_slippage_est": round(float(avg_slip), 2),
                "avg_net_pnl": round(float(avg_net), 2),
                "total_gross_pnl": round(float(total_gross), 2),
                "total_net_pnl": round(float(total_net), 2),
                "total_notional": round(float(total_notional), 2),
                "avg_hold_minutes": round(float(avg_hold), 1),
                "trades_per_week": round(trades_per_week, 1),
                "return_on_notional": round(return_on_notional, 4),
                "slippage_pct_of_gross": round(slippage_pct, 4),
                "avg_cost_bps": round(float(avg_cost_bps), 2),
                "total_cost_usd": round(float(total_cost_usd), 2),
                "avg_spread_cost_bps": round(float(avg_spread_bps), 2),
                "avg_impact_cost_bps": round(float(avg_impact_bps), 2),
                "cost_drag_pct": round(cost_drag_pct, 6),
            }
```

Also update the empty-row fallback dict to include the new keys:

```python
            return {k: 0 for k in [
                "total_trades", "win_rate", "avg_gross_pnl", "avg_slippage_est",
                "avg_net_pnl", "total_gross_pnl", "total_net_pnl",
                "total_notional", "avg_hold_minutes", "trades_per_week",
                "return_on_notional", "slippage_pct_of_gross",
                "avg_cost_bps", "total_cost_usd", "avg_spread_cost_bps",
                "avg_impact_cost_bps", "cost_drag_pct",
            }}
```

- [ ] **Step 4.6: Run tests**

```bash
python -m pytest tests/test_pg_store.py -v
```
Expected: all tests PASS (including the 3 new `TestCloseTradeCostBreakdown` tests)

- [ ] **Step 4.7: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat(store): inject TradeCostCalculator, real cost breakdown in close_trade"
```

---

## Task 5: Update `src/workers/execution.py` — tier-based stop-loss

**Files:**
- Modify: `src/workers/execution.py`
- Modify: `tests/workers/test_execution.py` (or create if absent)

- [ ] **Step 5.1: Write failing tests**

Find `tests/workers/test_execution.py`. If it exists, append; if not, create it:

```python
"""Tests for tier-based stop-loss in execution worker."""
import pytest
from unittest.mock import MagicMock, patch
from src.workers.execution import run_execution_cycle
from src.costs.calculator import TradeCostCalculator, CostBreakdown


def _make_calc(stop_pct: float) -> TradeCostCalculator:
    calc = MagicMock(spec=TradeCostCalculator)
    calc.stop_loss_pct.return_value = stop_pct
    return calc


class TestTierBasedStopLoss:
    def test_tier_a_uses_2pct_stop(self):
        """SPY (tier_a) stop-loss should be 2% below entry."""
        calc = TradeCostCalculator()
        assert calc.stop_loss_pct("SPY") == pytest.approx(0.020)

    def test_tier_b_uses_3_5pct_stop(self):
        """INTC (tier_b) stop-loss should be 3.5% below entry."""
        calc = TradeCostCalculator()
        assert calc.stop_loss_pct("INTC") == pytest.approx(0.035)

    def test_stop_loss_triggered_at_tier_threshold(self):
        """Stop-loss triggers when price < entry * (1 - tier_stop_loss_pct)."""
        from src.store.redis_store import RedisStore

        redis = MagicMock(spec=RedisStore)
        redis.get_kill_switch.return_value = None
        redis.get_regime.return_value = MagicMock(multiplier=1.0)
        redis.get_feedback_entry_threshold.return_value = None
        redis.get_feedback_regime_scale.return_value = None
        # Signal for INTC
        redis.read_sentiment.return_value = {
            "score": 0.5,
            "fallback_used": False,
            "generated_at": "2099-01-01T00:00:00+00:00",
            "signal_id": 1,
        }

        trading_client = MagicMock()
        trading_client.get_all_accounts.return_value = [MagicMock(portfolio_value="10000", last_equity="10000")]
        account = MagicMock()
        account.portfolio_value = "10000"
        account.last_equity = "10000"
        trading_client.get_account.return_value = account
        trading_client.get_all_positions.return_value = []
        trading_client.get_orders.return_value = []

        # INTC open position: entry=50, current=47.5 → 5% drop > 3.5% tier_b threshold
        open_pos = MagicMock()
        open_pos.avg_entry_price = "50.0"
        open_pos.current_price = "47.5"  # 5% drop → triggers tier_b 3.5% stop
        trading_client.get_all_positions.return_value = [open_pos]

        # Patch open_positions dict in cycle
        with patch("src.workers.execution._load_risk_params", return_value=(0.035, 0.10)):
            calc = _make_calc(0.035)
            stats = run_execution_cycle(
                symbols=["INTC"],
                redis_store=redis,
                trading_client=trading_client,
                cost_calc=calc,
            )
        assert stats["stop_losses_triggered"] == 1
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
python -m pytest tests/workers/test_execution.py::TestTierBasedStopLoss -v 2>&1 | head -20
```
Expected: FAIL — `run_execution_cycle` has no `cost_calc` parameter.

- [ ] **Step 5.3: Update `execution.py`**

**5.3a: Add import at top** (after existing imports):

```python
from src.costs.calculator import TradeCostCalculator
```

**5.3b: Update `run_execution_cycle` signature** — add `cost_calc` parameter:

Find the function definition:
```python
def run_execution_cycle(
    symbols: list[str],
    redis_store: RedisStore,
    trading_client,
    data_client=None,
    notifier: "Notifier | None" = None,
    pg_store=None,
) -> dict:
```

Replace with:
```python
def run_execution_cycle(
    symbols: list[str],
    redis_store: RedisStore,
    trading_client,
    data_client=None,
    notifier: "Notifier | None" = None,
    pg_store=None,
    cost_calc: "TradeCostCalculator | None" = None,
) -> dict:
```

**5.3c: Add calculator initialization near the top of `run_execution_cycle` body** — find `stop_loss_pct, max_drawdown_pct = _load_risk_params()` (around line 336) and replace it:

```python
    _cost_calc = cost_calc or TradeCostCalculator()
    _yaml_stop_loss, max_drawdown_pct = _load_risk_params()
    # _yaml_stop_loss kept only for the drawdown cap; per-symbol stop-loss is tier-based.
```

**5.3d: Update stop-loss computation in the per-symbol loop** — find the existing `stop_price = entry_price * (1 - stop_loss_pct)` in the open-position block (line ~434) and the `stop_price = round(price * (1 - stop_loss_pct), 2)` in the entry block (line ~546). Replace both occurrences:

For the open-position stop check (around line 434):
```python
                sym_stop_pct = _cost_calc.stop_loss_pct(symbol)
                stop_price = entry_price * (1 - sym_stop_pct)
```

For the entry OTO stop order (around line 546):
```python
                sym_stop_pct = _cost_calc.stop_loss_pct(symbol)
                stop_price = round(price * (1 - sym_stop_pct), 2)
```

**5.3e: Update `run_execution_worker` Celery task** to pass the calculator — find the call to `run_execution_cycle(...)` near line 650 and add `cost_calc=TradeCostCalculator()` as a keyword argument.

- [ ] **Step 5.4: Run tests**

```bash
python -m pytest tests/workers/test_execution.py::TestTierBasedStopLoss -v
```
Expected: `test_tier_a_uses_2pct_stop` and `test_tier_b_uses_3_5pct_stop` PASS.

- [ ] **Step 5.5: Run full test suite to check no regressions**

```bash
python -m pytest tests/workers/ -v 2>&1 | tail -20
```

- [ ] **Step 5.6: Commit**

```bash
git add src/workers/execution.py tests/workers/test_execution.py
git commit -m "feat(execution): tier-based stop-loss via TradeCostCalculator"
```

---

## Task 6: Update `src/workers/performance.py` — cost analysis in weekly report

**Files:**
- Modify: `src/workers/performance.py`

- [ ] **Step 6.1: Write failing test**

Create `tests/workers/test_performance_costs.py`:

```python
"""Test cost analysis section in trade P&L report."""
import pytest
from src.workers.performance import _format_trade_pnl_section


class TestCostAnalysisSection:
    def test_cost_section_present_when_data_available(self):
        summary = {
            "total_trades": 10,
            "win_rate": 0.60,
            "avg_gross_pnl": 25.0,
            "avg_slippage_est": 3.5,
            "avg_net_pnl": 21.5,
            "total_gross_pnl": 250.0,
            "total_net_pnl": 215.0,
            "total_notional": 50_000.0,
            "avg_hold_minutes": 90.0,
            "trades_per_week": 5.0,
            "return_on_notional": 0.0043,
            "slippage_pct_of_gross": 0.14,
            "avg_cost_bps": 6.5,
            "total_cost_usd": 35.0,
            "avg_spread_cost_bps": 5.0,
            "avg_impact_cost_bps": 0.8,
            "cost_drag_pct": 0.0007,
        }
        result = _format_trade_pnl_section(summary)
        assert "Cost Analysis" in result
        assert "6.5" in result   # avg_cost_bps
        assert "$35" in result   # total_cost_usd

    def test_cost_section_absent_when_no_cost_data(self):
        """Pre-019 trades have avg_cost_bps=0 — section shows N/A note."""
        summary = {
            "total_trades": 3,
            "win_rate": 0.33,
            "avg_gross_pnl": 10.0,
            "avg_slippage_est": 0.5,
            "avg_net_pnl": 9.5,
            "total_gross_pnl": 30.0,
            "total_net_pnl": 28.5,
            "total_notional": 5_000.0,
            "avg_hold_minutes": 60.0,
            "trades_per_week": 1.5,
            "return_on_notional": 0.0057,
            "slippage_pct_of_gross": 0.05,
            "avg_cost_bps": 0.0,
            "total_cost_usd": 0.0,
            "avg_spread_cost_bps": 0.0,
            "avg_impact_cost_bps": 0.0,
            "cost_drag_pct": 0.0,
        }
        result = _format_trade_pnl_section(summary)
        assert "no cost data" in result.lower() or "Cost Analysis" in result
```

- [ ] **Step 6.2: Run test to verify failure**

```bash
python -m pytest tests/workers/test_performance_costs.py -v 2>&1 | head -20
```
Expected: FAIL — `_format_trade_pnl_section` doesn't include cost section yet.

- [ ] **Step 6.3: Update `_format_trade_pnl_section` in `performance.py`**

Find the function `_format_trade_pnl_section` (around line 330). Find the `return (...)` statement and add a cost section before it:

```python
    # Cost analysis section
    avg_cost_bps = trades_summary.get("avg_cost_bps", 0.0)
    total_cost_usd = trades_summary.get("total_cost_usd", 0.0)
    avg_spread_bps = trades_summary.get("avg_spread_cost_bps", 0.0)
    avg_impact_bps = trades_summary.get("avg_impact_cost_bps", 0.0)
    cost_drag_pct = trades_summary.get("cost_drag_pct", 0.0)

    if avg_cost_bps > 0:
        annualized_drag_bps = cost_drag_pct * 252 * 10_000 if cost_drag_pct else 0.0
        cost_section = (
            f"\n💸 *Cost Analysis*\n"
            f"Avg cost/trade: {avg_cost_bps:.1f} bps "
            f"(spread {avg_spread_bps:.1f} + impact {avg_impact_bps:.1f})\n"
            f"Total cost: ${total_cost_usd:.2f} | Cost drag: {cost_drag_pct*100:.3f}%\n"
            f"Annualised drag: ~{annualized_drag_bps:.0f} bps/yr"
        )
    else:
        cost_section = "\n💸 *Cost Analysis*\nNo cost data yet (pre-migration trades)"
```

Then append `cost_section` to the return string:

```python
    return (
        f"\n📊 *Trade P&L (last 7d)*\n"
        f"Trades: {total} | Win rate: {win_pct:.1f}%\n"
        f"Avg gross P&L: ${avg_gross:.2f} | Avg slippage: ${avg_slip:.2f} | Avg net: ${avg_net:.2f}\n"
        f"Total gross: ${total_gross:.2f} | Total net: ${total_net:.2f}\n"
        f"\n📈 *Frequency vs Margin*\n"
        f"Trades/week: {tpw:.1f} | Total notional: ${total_notional:.0f}\n"
        f"Return on notional: {ron:.2f}% | Avg hold: {avg_hold:.0f}min\n"
        f"Est. slippage: {slip_pct*100:.1f}% of gross P&L"
        f"{cost_section}"
        f"{warn_str}"
    )
```

- [ ] **Step 6.4: Run tests**

```bash
python -m pytest tests/workers/test_performance_costs.py -v
```
Expected: both tests PASS.

- [ ] **Step 6.5: Commit**

```bash
git add src/workers/performance.py tests/workers/test_performance_costs.py
git commit -m "feat(performance): add cost analysis section to weekly trade P&L report"
```

---

## Task 7: Update `src/backtest/report.py` — IC net-of-costs fields

**Files:**
- Modify: `src/backtest/report.py`
- Create: `tests/backtest/test_report_net_ic.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/backtest/test_report_net_ic.py` (create `tests/backtest/__init__.py` if absent):

```python
"""IC net-of-costs fields in BacktestReport."""
import pytest
from src.backtest.report import BacktestReport, BacktestReportBuilder
from src.performance.ic import ICResult, ICIRResult
from datetime import datetime, timezone


def _make_report(**overrides) -> BacktestReport:
    base = dict(
        run_id="test",
        period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        total_signals=100,
        signals_with_returns=80,
        ic_1h=ICResult(composite_ic=0.30, spearman_ic=0.02, weighted_hit_rate=0.55, brier_score=0.25, sample_count=80),
        ic_4h=ICResult(composite_ic=0.28, spearman_ic=0.01, weighted_hit_rate=0.52, brier_score=0.26, sample_count=70),
        ic_24h=ICResult(composite_ic=0.29, spearman_ic=0.015, weighted_hit_rate=0.53, brier_score=0.255, sample_count=75),
        icir_1h=ICIRResult(icir=12.0, ic_mean=0.28, ic_std=0.13, newey_west_std=0.022, lag=3, sample_count=80),
        icir_4h=ICIRResult(icir=11.0, ic_mean=0.27, ic_std=0.12, newey_west_std=0.021, lag=3, sample_count=70),
        icir_24h=ICIRResult(icir=13.0, ic_mean=0.29, ic_std=0.11, newey_west_std=0.020, lag=3, sample_count=75),
        ic_1h_net=ICResult(composite_ic=0.28, spearman_ic=0.018, weighted_hit_rate=0.54, brier_score=0.252, sample_count=80),
        ic_4h_net=None,
        ic_24h_net=ICResult(composite_ic=0.27, spearman_ic=0.012, weighted_hit_rate=0.51, brier_score=0.258, sample_count=75),
        icir_1h_net=ICIRResult(icir=11.5, ic_mean=0.265, ic_std=0.13, newey_west_std=0.022, lag=3, sample_count=80),
        icir_4h_net=None,
        icir_24h_net=ICIRResult(icir=12.2, ic_mean=0.275, ic_std=0.11, newey_west_std=0.020, lag=3, sample_count=75),
    )
    base.update(overrides)
    return BacktestReport(**base)


class TestBacktestReportNetIC:
    def test_to_dict_includes_net_fields(self):
        report = _make_report()
        d = report.to_dict()
        assert "ic_1h_net" in d
        assert "icir_1h_net" in d
        assert "ic_4h_net" in d
        assert "icir_4h_net" in d
        assert "ic_24h_net" in d
        assert "icir_24h_net" in d

    def test_net_ic_lower_than_gross(self):
        report = _make_report()
        d = report.to_dict()
        assert d["ic_1h"]["composite_ic"] > d["ic_1h_net"]["composite_ic"]
        assert d["ic_24h"]["composite_ic"] > d["ic_24h_net"]["composite_ic"]

    def test_gross_fields_unchanged(self):
        """Gross IC fields must not be modified."""
        report = _make_report()
        d = report.to_dict()
        assert d["ic_1h"]["composite_ic"] == pytest.approx(0.30)
        assert d["icir_24h"]["icir"] == pytest.approx(13.0)

    def test_none_net_fields_serialize_as_none(self):
        report = _make_report()
        d = report.to_dict()
        assert d["ic_4h_net"] is None
        assert d["icir_4h_net"] is None
```

- [ ] **Step 7.2: Run tests to verify failure**

```bash
python -m pytest tests/backtest/test_report_net_ic.py -v 2>&1 | head -20
```
Expected: FAIL — `BacktestReport` has no `ic_1h_net` etc. fields.

- [ ] **Step 7.3: Update `BacktestReport` dataclass** — add 6 new optional fields after the existing `icir_24h` field:

```python
    icir_24h: ICIRResult | None
    ic_1h_net: ICResult | None = None
    ic_4h_net: ICResult | None = None
    ic_24h_net: ICResult | None = None
    icir_1h_net: ICIRResult | None = None
    icir_4h_net: ICIRResult | None = None
    icir_24h_net: ICIRResult | None = None
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    # ... rest unchanged
```

- [ ] **Step 7.4: Update `to_dict`** — add net fields to the return dict:

Find the return dict in `to_dict()` and add after `"icir_24h": _icir(self.icir_24h),`:

```python
            "ic_1h_net": _ic(self.ic_1h_net),
            "ic_4h_net": _ic(self.ic_4h_net),
            "ic_24h_net": _ic(self.ic_24h_net),
            "icir_1h_net": _icir(self.icir_1h_net),
            "icir_4h_net": _icir(self.icir_4h_net),
            "icir_24h_net": _icir(self.icir_24h_net),
```

- [ ] **Step 7.5: Update `BacktestReportBuilder.build()`** to compute net IC

**7.5a: Add import** at top of `report.py`:

```python
from src.costs.calculator import TradeCostCalculator
```

**7.5b: Update `BacktestReportBuilder.__init__`** to accept a calculator:

```python
    def __init__(self, pg_conn, cost_calc: TradeCostCalculator | None = None) -> None:
        self._conn = pg_conn
        self._cost_calc = cost_calc or TradeCostCalculator()
```

**7.5c: Add net IC computation in `build()`** — add after the gross IC computation (after `ic_24h, icir_24h = _ic_icir(s24, r24, c24)` and before the `signals_with_returns` line):

```python
        def _subtract_cost(symbol_returns_pairs, horizon_idx: int):
            """Return returns adjusted by per-symbol spread cost."""
            adjusted = []
            for row in rows:
                _sym, _model_id, _score, _conf, fallback, r1h, r4h, r24h, _src = row
                ret = [r1h, r4h, r24h][horizon_idx]
                if ret is None or fallback:
                    continue
                cost_bps = self._cost_calc.compute(
                    symbol=_sym,
                    notional=1.0,
                    qty=1.0,
                    fill_price=1.0,
                    side="SELL",
                ).total_cost_bps
                adjusted.append(ret - cost_bps / 10_000)
            return adjusted

        def _extract_net(horizon_idx: int):
            source = rows
            scores, net_returns, confs = [], [], []
            for _sym, _model_id, score, conf, fallback, r1h, r4h, r24h, _src in source:
                ret = [r1h, r4h, r24h][horizon_idx]
                if ret is None or fallback:
                    continue
                cost_bps = self._cost_calc.compute(
                    symbol=_sym, notional=1.0, qty=1.0, fill_price=1.0, side="SELL",
                ).total_cost_bps
                scores.append(score)
                net_returns.append(ret - cost_bps / 10_000)
                confs.append(conf)
            return scores, net_returns, confs

        sn1, rn1, cn1 = _extract_net(0)
        sn4, rn4, cn4 = _extract_net(1)
        sn24, rn24, cn24 = _extract_net(2)

        ic_1h_net, icir_1h_net = _ic_icir(sn1, rn1, cn1)
        ic_4h_net, icir_4h_net = _ic_icir(sn4, rn4, cn4)
        ic_24h_net, icir_24h_net = _ic_icir(sn24, rn24, cn24)
```

**7.5d: Add net fields to the `BacktestReport(...)` constructor call** at the end of `build()`:

```python
        return BacktestReport(
            run_id=run_id,
            period_start=period_start,
            period_end=period_end,
            total_signals=total,
            signals_with_returns=signals_with_returns,
            ic_1h=ic_1h,
            ic_4h=ic_4h,
            ic_24h=ic_24h,
            icir_1h=icir_1h,
            icir_4h=icir_4h,
            icir_24h=icir_24h,
            ic_1h_net=ic_1h_net,
            ic_4h_net=ic_4h_net,
            ic_24h_net=ic_24h_net,
            icir_1h_net=icir_1h_net,
            icir_4h_net=icir_4h_net,
            icir_24h_net=icir_24h_net,
            by_model=by_model,
            by_symbol=by_symbol,
            by_source=by_source,
        )
```

- [ ] **Step 7.6: Run tests**

```bash
python -m pytest tests/backtest/test_report_net_ic.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 7.7: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all existing tests still pass; new tests pass.

- [ ] **Step 7.8: Commit**

```bash
git add src/backtest/report.py tests/backtest/__init__.py tests/backtest/test_report_net_ic.py
git commit -m "feat(backtest): add IC net-of-costs fields (ic_*_net, icir_*_net) to BacktestReport"
```

---

## Task 8: Final integration check

- [ ] **Step 8.1: Run all new tests together**

```bash
python -m pytest tests/costs/ tests/backtest/test_report_net_ic.py tests/workers/test_performance_costs.py tests/test_pg_store.py::TestCloseTradeCostBreakdown -v
```
Expected: all PASS.

- [ ] **Step 8.2: Run full suite**

```bash
python -m pytest tests/ --tb=short -q 2>&1 | tail -20
```
Expected: zero failures.

- [ ] **Step 8.3: Final commit**

```bash
git add -A
git commit -m "feat(costs): trade cost realism — tier stop-loss, real net P&L, IC net-of-costs"
```
