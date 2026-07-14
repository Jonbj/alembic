# Stop-Loss Redesign — Implementation Plan & Spec

**Date:** 2026-07-11
**Status:** Design locked, ready to implement
**Implementer:** Kimi 2.7-code (external coding agent)
**Predecessor docs:** `docs/stop_loss_review_prompt.md` (doubts sent to ChatGPT), `docs/AS-IS_FINDINGS_2026-07-10.md` (F9a), memory `project-stop-loss-attribution-audit.md`
**Audit script:** `scripts/audit_stop_loss_attribution.py`

> Self-contained spec. The implementer has repo access but no conversation context.
> Every `file:line` reference is verified against the current `main` branch.
> Respect the **Non-negotiable invariants** (§7) absolutely. Respect the project's
> **measure-before-enforce** discipline (CLAUDE.md "QX-01"): scoring/risk changes
> ship behind flags, measured, then enabled.

---

## 1. TL;DR

The fixed 2% stop-loss fires on noise for high-vol names (PANW/WDC/DELL: 2% = 0.26–0.53σ,
moves >2% on 65–72% of days). Redesign it as a **volatility-scaled protective stop,
frozen at entry, with stop-risk sizing**, behind a flag, measured before live.
Separate the protective stop (synthetic, per-cycle, uniform) from a broker disaster
stop. Decouple the loss-feedback ratchet per strategy so the stop's effect is
interpretable. **Attribution of `exit_reason` is already 100%** (verified — the
scheduler writes it at submit-time; `reconcile_trade_fills` never touches it), so
the real prerequisite is persisting **stop-decision metadata** (vol_at_entry, k,
trigger price), not building exit-intent reason propagation.

---

## 2. System context (minimal)

- Alpha Miner ATS: offline LLM sentiment → Redis/PostgreSQL → execution engine reads
  pre-computed signals. **Never an LLM in the hot path** (the 15-min cycle is hot).
- Active order path: `execution.engine=portfolio`. `run_portfolio_cycle` (Celery beat,
  every 15 min during market hours) → orchestrator merges strategy target weights →
  vol-targeter → constraint enforcer → submit orders.
- Broker: Alpaca via `alpaca-py` (paper/live share code path; switch in
  `config/trading.yaml` → `execution.engine`). **Alpaca rejects bracket legs on
  notional/fractional orders (error 42210000)**, so the stop is **synthetic per-cycle**
  (each cycle checks prices and force-closes breached positions). Whole-share orders
  can attach a broker bracket (`ALPACA_STOP_LOSS_PCT`).
- Strategies in scope: S1 (Time-Series Momentum, MONTHLY rebalance, cross-sectional
  z-score of vol-normalized momentum, lookbacks 21/63/126/252d), S4 (news-sentiment,
  event-driven, short horizon), S7 (PEAD, not yet live). S2 VRP exists.
- Loss-feedback ratchet raises `feedback:entry_threshold` (a hard S4 entry gate)
  after losing streaks / rolling-P&L drawdown. `feedback:regime_scale` is written but
  **not read** in the portfolio path (orphaned, F8).

---

## 3. The problem (evidence)

**Case 2026-07-10 (PANW):** S1 bought PANW @ 337.52 (notional ~$650, regime_mult 0.7)
on strong long-lookback momentum (252d +58%, 63d +95%). 30 min later price = 328.01;
the 2% stop fired (threshold 330.77). Net loss −$19.64. PANW closed the day at 325.82
(intraday swing −3.5%, normal for a +95%/63d name). The −6% 5d trend was noise against
the annual uptrend.

**Day 2026-07-10 aggregate:** 6 closed trades, net −$5.68. All 4 losses = S1 momentum;
both wins = S4 news. 3 stop_losses (PANW/WDC/DELL) entered the same 14:07 S1 cycle,
stopped within 30–60 min on −3.6% to −4% intraday dips. Stop 2% in σ terms:
PANW 0.53σ / DELL 0.53σ / WDC 0.26σ (fires on 65–72% of trading days). WDC recovered
to −0.3% from entry by close (+1.9% above exit) → confirmed noise stop-out. Direct
P&L benefit of the stop ~neutral (~0.6% saved); **systemic cost > benefit** (3 ratchet
hits + 3 cooldown lockouts). Without the 3 S1 stop-outs the day would have been net ~+$28.

**Root causes:** (a) 2% stop sub-σ for high-vol names; (b) horizon mismatch — S1 is
monthly, stop calibrated on 15-min intraday noise; (c) correlated high-beta cluster
in one cycle.

---

## 4. Verified current implementation (facts the implementer can trust)

All `file:line` verified on `main` (2026-07-11).

**Stop breach check — `src/workers/portfolio_scheduler.py`**
- `_stop_loss_breached_symbols(positions, entry_prices, market, stop_loss_pct) -> set[str]`
  at `:536-579`. Logic: `if price <= entry * (1.0 - stop_loss_pct)` → add sym. Returns a
  **set** (no per-symbol price/trigger data).
- Call site `:1117-1120`:
  `stop_loss_sells = _stop_loss_breached_symbols(alpaca_positions, alpaca_entry_prices, market, _risk_cfg.get("stop_loss", 0.02))`
- `_risk_cfg` loaded by `_load_risk_config` (`:512-533`), default `stop_loss: 0.02`.
- `alpaca_entry_prices` = broker's **blended avg entry** (real fills, not signal price).

**Stop submit — `portfolio_scheduler.py:1549-1570`**
- Submits a market SELL (qty = held), appends to `submitted_orders` with
  `{"reason": "stop_loss"}` (`:1565`), then `_mark_stop_loss_today` (`:1568`).
- **Does NOT write an `execution_decisions` SELL row** (unlike sentiment_reversal at
  `:1606-1617`). → Decision Log is silent on stops (Gap A: 0/11 coverage, audited).

**Trade exit write — `pg_store.py:899-926` `record_trade_exit(symbol, exit_order_id, exit_time, exit_reason)`**
- `UPDATE trades SET exit_order_id, exit_time, exit_reason WHERE symbol=%s AND exit_time IS NULL RETURNING id`.
- Called for all sells at `portfolio_scheduler.py:1661` with
  `exit_reason=sub.get("reason", "portfolio_sell")`. So **stop_loss exit_reason is
  written at submit-time**, keyed by symbol (one open trade per symbol — pyramiding
  guard P0-05 enforces this since 2026-07-01; verified: zero concurrent same-symbol
  overlap, zero duplicate open symbols).

**Reconcile — `pg_store.py:1168-1278` `reconcile_trade_fills(trading_client)`**
- Reconciles entry fills (entry_price NULL) and exit fills (exit_order_id NOT NULL,
  exit_price NULL). **Never reads or writes `exit_reason`.** Fills exit_price,
  gross_pnl, net_pnl, costs. Called by `run_daily_report` (performance.py:679,759).

**Cooldown — `portfolio_scheduler.py:440-473`**
- `_mark_stop_loss_today` writes `stop_loss_today:{symbol}` with TTL → midnight UTC.
- `_get_stop_loss_cooldown_symbols` reads them; blocks re-BUY same day (`:1305`, `:2221`).
- Intentional anti-churn. **Preserve current behavior in this phase.**

**Broker bracket (whole-share only) — `portfolio_scheduler.py:2268-2276`**
- `if ... not is_fractionable:` attaches `StopLossRequest(stop_price=sl_price)` using
  `ALPACA_STOP_LOSS_PCT` (`config.py:154-156`, env-overridable, default 0.03).
- Fractionable: no broker stop, only the synthetic per-cycle check.

**Vol data in scope at the stop call site — confirmed**
- `bars_df` (close pivoted by timestamp×symbol) is built at `:973-985` and is in scope
  at `:1119`. `pct_change()` already computed at `:1145`. So per-symbol daily vol is
  available with no extra fetch. **Caveat:** held symbols not in the active strategy
  universe are NOT in `bars_df` → need a fallback (see §8.3 fallback hierarchy).

**Legacy path — `src/workers/execution.py`** (dormant, `engine=legacy_sentiment`)
- Stop is per-symbol by **liquidity tier**, not vol: `config/cost_model.yaml`
  (tier_a 2% mega-cap, tier_b 3.5% large, tier_c 4% mid, tier_d 5% small). `risk.stop_loss`
  is dead in the legacy path. **Do not change legacy behavior in this phase** (§7.6).

**Origin strategy — derived at read-time, NOT stored**
- `src/api/routes/trading.py:96-103`: `origin = "S4" if trace.signal_id else "S1" if
  (decision_id or trade_id) else None`. No `strategy`/`origin_strategy` column on
  `trades` or `execution_decisions`. **For `k_s` selection, derive the same way at
  entry and FREEZE it on the trade** (§8.2).

**Config validation — `src/api/routes/config_routes.py`**
- `_RISK_BOUNDS` (`:18-27`): `"stop_loss": (0.001, 0.10)`.
- `_validate_risk` (`:34-52`): 422 if a risk param is outside bounds.
- `_detect_risk_weakening` (`:54-72`) + `_check_risk_weakening` (`:72-86`): raising
  `stop_loss` etc. requires a `reason` query param.
- `_EDITABLE_RISK_FIELDS` (`:28`) lists editable fields incl. `stop_loss`.

**Pinning tests**
- `tests/workers/test_day1_fixes.py:125-183` — **8 tests** pin
  `_stop_loss_breached_symbols` (set return, 0.02 threshold). Must be updated to the new
  signature; the `mode=fixed` path must reproduce the 2% threshold so they can assert
  fixed-mode behavior.
- `tests/workers/test_risk_config_unification.py:14` — pins `stop_loss: 0.02` in YAML.
- `tests/workers/test_execution_risk_params.py:43` — `calc.stop_loss_pct("SPY") == 0.020`
  (legacy `execution.py` calc; leave unless StopPolicy replaces that calc).
- `tests/test_p0_08_config_validation.py` — `_RISK_BOUNDS` validation; extend for new keys.

**Migration framework**
- Plain SQL files in `migrations/` (numbered `001`…`033`), applied by
  `migrations/apply_migrations.py`. **Next migration number: `034`.**

**DB** — Postgres `alembic-postgres-1`, `DATABASE_URL=postgresql://trading:trading@localhost:5432/trading` (or `postgres:5432` in-container). `trades` and `execution_decisions` schemas are as the implementer will find them; do not assume columns beyond those listed here without checking `\d`.

---

## 5. Corrected understanding (vs. the ChatGPT prompt)

The prompt's premise — *"the synthetic path does NOT write exit_reason='stop_loss';
reconcile_trade_fills assigns it a posteriori"* — is **false** (§4). The scheduler
writes `exit_reason` at submit-time; reconcile only fills prices. The audit
(`scripts/audit_stop_loss_attribution.py`) confirms: **attribution gate = 100%** (excl.
16 `LEGACY_FLATTEN`), exit_reason never NULL, all 11 `stop_loss` trades fully reconciled.

Therefore ChatGPT's prescribed passo-zero ("build explicit exit-intent propagation +
≥99% attribution gate") is **already satisfied for the reason dimension**. Do NOT build
a large exit-intent pipeline for reason attribution.

**The real prerequisite is Gap D — persist stop-decision metadata** (vol_at_entry,
σ_eff, k, floor, cap, trigger vs observed price, price_source, origin strategy),
because without it neither the new vol-scaled stop nor the false-stop / MAE
measurement is possible.

**Pragmatism confirmed by data (vs. ChatGPT's maximalist scope):**
- One-position-per-symbol now holds (pyramiding guard) → **virtual-sleeve accounting
  is NOT needed for v1**. A per-symbol stop keyed to the (single, frozen) entry
  strategy is viable.
- Keep the protective stop **synthetic and uniform** (do not migrate to broker even
  if Alpaca now supports fractional simple stops — that re-introduces the
  path-dependent fractional/whole-share inconsistency). Broker = disaster stop only.

---

## 6. Converged design

### 6.1 Three-layer separation (do NOT collapse into one "stop_loss")

| Layer | What | Where | Semantics |
|---|---|---|---|
| **Strategy exit** | normal rebalance / sentiment-reversal | orchestrator + reversal path | "the thesis is done" |
| **Protective stop** | vol-scaled, frozen at entry, never widens | synthetic per-cycle (`StopPolicy`) | "cut a wrong-sized position" |
| **Broker disaster stop** | wider hard limit | broker bracket (whole-share) / synthetic equivalent (fractionable) | "catastrophe backstop" |

Rename in config/docs: `strategy_protective_stop` vs `broker_disaster_stop`. Do not
"align" the old 2%/3% to one value — they are different concepts.

### 6.2 Protective stop formula (vol-scaled, frozen at entry)

```
σ_eff(sym) = max( EWMA20(daily returns), 0.8 · STD63(daily returns) )   # daily, NOT annualized
                                                                      
# computed AT ENTRY and FROZEN on the trade row; stop never widens
d_init(sym, strat) = clip( k_strat · σ_eff_at_entry,  floor_strat,  cap_strat )
trigger_price(long) = entry_price · (1 − d_init)        # monotonic non-increasing (frozen)
breach if observed_price <= trigger_price
```

Strategy params (engineering priors; calibrate on MAE later — §6.5):
- S1: k=3.5, floor=6%, cap=12%
- S4: k=2.0, floor=3%, cap=8%
- S7: k=2.5, floor=4%, cap=10%
- default: k=3.0, floor=4%, cap=12%

**Horizon enters via `k_strat`/floor/cap (calibrated on each strategy's MAE), NOT via
`√holding_days`.** A √21 multiplier would give ~25% stops — non-functional. Do not use
`k·σ·√H`.

### 6.3 σ_eff fallback hierarchy (held symbols may be outside the active universe)

1. current valid σ_eff from `bars_df` (if symbol present, ≥21 bars)
2. last-good σ_eff for the symbol (≤5 sessions; persist in a small `stop_vol_history`
   table or Redis — implementer's choice, see Phase 1)
3. median σ_eff per asset class (config-driven map; start coarse: equity / ETF)
4. liquidity-tier table (`config/cost_model.yaml`) as a weak proxy
5. conservative default: k=3.0, floor=4%, cap=12% (default strategy params)

Log which fallback was used in `stop_decisions.price_source` / a `vol_source` field.

### 6.4 Stop-risk sizing (the piece that makes a wider stop safe)

A wider stop on the same notional = bigger $ loss feeding the ratchet. Size down as
the stop widens so monetary risk per position is bounded:

```
Notional(sym, strat) ≤ NAV · B_strat / ( d_init + gap_buffer )
```
- `B_strat` = per-position loss budget in bp of NAV (start 10–15 bp; e.g. 12 bp)
- aggregate open-stop risk per sleeve ≤ 75–100 bp
- `gap_buffer` = max(0.5%, 95th-pct adverse gap for the symbol) — covers overnight gap

Wire this in the **order-sizing path** (where target weights → qty, after
vol-targeter, before submit), NOT in the breach check. A wider `d_init` → smaller qty.
This is what lets the vol-scaled stop reduce false stops without exploding per-stop loss.

### 6.5 k calibration (later; out of scope for initial implementation)

`k_strat` should ultimately be calibrated on each strategy's **MAE distribution** of
winning trades: `k = quantile_q( σ_entry / MAE_trade )`. For the initial implementation
ship the engineering priors above; calibration runs once Phase 6 (replay) produces the
MAE data. Do NOT block initial implementation on calibration.

### 6.6 Broker disaster stop (separate, wider)

```
d_hard = clip( max( 1.5 · d_init, 5 · σ_eff_current ), floor=12%, cap=20% )
```
- Whole-share: replace the `ALPACA_STOP_LOSS_PCT=0.03` bracket with `d_hard`.
- Fractionable: keep synthetic per-cycle equivalent (Alpaca still rejects brackets on
  notional/fractional). Re-test fractional simple-stop support separately (§11) but do
  NOT migrate the protective stop to broker.

---

## 7. Non-negotiable invariants

1. **No LLM / no remote API in the hot path.** The stop check runs every 15 min in the
   cycle — must use only local data (bars_df, Redis, Postgres).
2. **Protective stop always synthetic, per-cycle, uniform** across fractionable and
   whole-share. Never migrate it to broker. Broker = disaster stop only.
3. **Stop never widens.** For a long, `trigger_price` is monotonic non-increasing.
   Freeze `σ_eff`, `k`, `floor`, `cap`, `d_init` at entry on the trade row. (Trailing is
   a later phase; until then a frozen `d_init` makes "never widens" hold by construction.)
4. **One position per symbol** (pyramiding guard P0-05). The stop assumes it; do not
   break the guard. `record_trade_exit`'s symbol-keyed match is safe under this invariant.
5. **Behind flags; no behavior change by default.** `stop_loss_mode: fixed` is the
   default → identical to today's 2% until explicitly switched to `vol_scaled`. The
   shadow log never sends orders.
6. **Legacy path (`execution.py`, `engine=legacy_sentiment`) unchanged behavior.** Add
   the shared `StopPolicy` module; do NOT wire it into legacy in this phase.
7. **Cooldown preserved** (`stop_loss_today` → midnight UTC). The S1 whipsaw concern
   (block until next rebalance / re-entry threshold) is a noted LATER sub-task; keep
   current behavior in this phase.
8. **`exit_reason` attribution stays at submit-time.** Do not move it to reconcile.
9. **Measure before enforce (QX-01).** No live stop measurement until the audit gate
   (≥99% attribution — already PASS) AND the replay gates (§10) are met. Shadow-only
   until gates pass.
10. **All existing tests must pass** except the 8 `test_day1_fixes` tests that pin the
    old signature — update those. `scripts/audit_stop_loss_attribution.py` must stay green.

---

## 8. Phased implementation

Each phase is independently shippable. Phases 1–4 are pure code (no measurement gate).
Phase 5 is the live-gating refactor. Phases 6–7 are measurement/ops.

### Phase 1 — Migration 034 (schema)

**File:** `migrations/034_stop_loss_redesign.sql`

```sql
-- Freeze-at-entry stop params on each trade (NULL for pre-migration open trades →
-- those use the legacy fixed-2% fallback in StopPolicy).
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_strategy        TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_mode            TEXT;       -- fixed|vol_scaled
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_vol_at_entry   DOUBLE PRECISION;  -- σ_eff frozen
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_k             DOUBLE PRECISION;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_floor        DOUBLE PRECISION;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_cap          DOUBLE PRECISION;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_d_init       DOUBLE PRECISION;  -- clipped distance
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_vol_source   TEXT;       -- bars_df|last_good|asset_median|tier|default

-- One row per stop FIRE (low volume; the actual closes).
CREATE TABLE IF NOT EXISTS stop_decisions (
  id              BIGSERIAL PRIMARY KEY,
  trade_id        BIGINT REFERENCES trades(id),
  symbol          TEXT NOT NULL,
  strategy        TEXT,
  mode            TEXT NOT NULL,             -- fixed|vol_scaled
  entry_price     DOUBLE PRECISION,
  observed_price  DOUBLE PRECISION,
  trigger_price   DOUBLE PRECISION,
  d_init          DOUBLE PRECISION,
  vol_at_entry    DOUBLE PRECISION,
  sigma_eff       DOUBLE PRECISION,
  k               DOUBLE PRECISION,
  floor           DOUBLE PRECISION,
  cap             DOUBLE PRECISION,
  price_source    TEXT,                       -- market.prices|bid|...
  vol_source      TEXT,                       -- see fallback hierarchy
  exit_order_id   TEXT,
  cycle_ts       TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stop_decisions_symbol_ts ON stop_decisions(symbol, cycle_ts);

-- Per-cycle shadow log (high volume; only when risk.stop_shadow_enabled=true).
-- Logs BOTH fixed and vol_scaled triggers for every held position each cycle.
CREATE TABLE IF NOT EXISTS stop_shadow_log (
  id                       BIGSERIAL PRIMARY KEY,
  cycle_ts                 TIMESTAMPTZ NOT NULL,
  symbol                   TEXT NOT NULL,
  strategy                 TEXT,
  entry_price              DOUBLE PRECISION,
  observed_price           DOUBLE PRECISION,
  vol_at_entry             DOUBLE PRECISION,
  sigma_eff                DOUBLE PRECISION,
  vol_source               TEXT,
  d_init_fixed             DOUBLE PRECISION,   -- legacy 2% (or risk.stop_loss)
  trigger_fixed            DOUBLE PRECISION,
  would_breach_fixed       BOOLEAN,
  d_init_vol_scaled        DOUBLE PRECISION,
  trigger_vol_scaled       DOUBLE PRECISION,
  would_breach_vol_scaled  BOOLEAN,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stop_shadow_symbol_ts ON stop_shadow_log(symbol, cycle_ts);
```

Register the migration in `migrations/apply_migrations.py` (follow the existing pattern
— check how 033 is wired). Add an `idempotent` note (all `IF NOT EXISTS`).

**Tests:** `tests/store/test_pg_store.py` (or equivalent) — assert the new columns exist
and `stop_decisions`/`stop_shadow_log` are insertable. Add a `migrations/` smoke test if
the repo has one (check `tests/` for a migrations test pattern).

---

### Phase 2 — Gap A: write SELL `execution_decision` on stop-loss

**Objective:** the Decision Log shows stop exits (today 0/11).

**File:** `src/workers/portfolio_scheduler.py:1549-1570`

Extend `_stop_loss_breached_symbols` (`:536-579`) to return per-symbol decision data
instead of a bare set. New return: `dict[str, dict]` with keys
`{entry, observed, trigger, pct, strategy}` (strategy derived per §4: S4 if the held
position has a signal_id, else S1 — read from the open trade row / `alpaca_entry_prices`
context; if unavailable, `None`). **Keep the function name** but change its return type;
update all call sites (`:1119, :1168, :1175, :1551, :1575`) to iterate the dict.

In the stop submit block (`:1551-1570`), mirror the sentiment_reversal decision write
(`:1606-1617`):

```python
# after submitting the SELL and getting resp.id:
_pg_sl = PostgreSQLStore()
_pg_sl.write_execution_decision(
    tick_time=ts, symbol=sym, signal_id=<entry signal_id or None>, score=0.0,
    signal_score=None, regime_mult=_regime_mult, ema_pass=True,
    decision="SELL", order_id=str(resp.id),
    reason=f"stop_loss: {sym} px {observed:.2f} <= trigger {trigger:.2f} "
           f"(d_init {pct:.2%}, mode {mode}, strat {strategy})",
)
_pg_sl.close()
```

`exit_reason` in `submitted_orders` stays `"stop_loss"` (it already is).

**Tests:** add `tests/workers/test_stop_loss_decision_log.py` — submit a stop, assert a
`execution_decisions` row with `decision='SELL'` and `reason LIKE 'stop_loss:%'` exists.
Update `tests/workers/test_day1_fixes.py:125-183` to the new dict return (assert the
fixed-mode 2% threshold still breaches correctly).

---

### Phase 3 — Gap D: `StopPolicy` deep module + freeze-at-entry + fire log + shadow log

**Objective:** the real prerequisite — persist stop-decision metadata so the new stop
and the false-stop/MAE measurement are possible.

**New file:** `src/portfolio/stop_policy.py` (deep module — small interface, all stop
logic behind it; testable through the interface).

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class FrozenStop:
    """Stop params frozen at entry; persisted on the trade row."""
    strategy: str | None
    mode: str                 # "fixed" | "vol_scaled"
    vol_at_entry: float | None
    sigma_eff: float | None
    k: float | None
    floor: float | None
    cap: float | None
    d_init: float | None
    vol_source: str | None

@dataclass
class StopDecision:
    symbol: str
    strategy: str | None
    mode: str
    entry_price: float
    observed_price: float
    trigger_price: float
    d_init: float
    vol_at_entry: float | None
    sigma_eff: float | None
    k: float | None
    floor: float | None
    cap: float | None
    price_source: str
    vol_source: str | None
    breached: bool
    cycle_ts: datetime

class StopPolicy:
    """One policy, two modes. Protective stop is always synthetic per-cycle.

    Interface (the test surface):
      freeze(symbol, strategy, entry_price, bars_df, cycle_ts) -> FrozenStop
      compute(symbol, entry_price, observed_price, frozen, cycle_ts, price_source) -> StopDecision
      d_hard(symbol, frozen, sigma_eff_current) -> float          # broker disaster stop
    """
    def __init__(self, risk_cfg: dict, bars_df): ...
    def freeze(self, symbol, strategy, entry_price, cycle_ts) -> FrozenStop: ...
    def compute(self, symbol, entry_price, observed_price, frozen, cycle_ts, price_source="market.prices") -> StopDecision: ...
    def d_hard(self, symbol, frozen, sigma_eff_current) -> float: ...
```

**`freeze()` rules:**
- `mode = risk_cfg.get("stop_loss_mode", "fixed")`.
- `strategy` derived at entry (S4 if the entry has a `signal_id`, else S1; pass it in
  from the caller — the caller knows whether it's writing an S4 signal-driven BUY or an
  S1 momentum BUY).
- If `mode == "fixed"`: `d_init = risk_cfg["stop_loss"]` (0.02), vol fields None.
- If `mode == "vol_scaled"`: compute `σ_eff` per §6.2 from `bars_df` (fallback §6.3),
  `d_init = clip(k_strat · σ_eff, floor, cap)`, `vol_source` recorded.
- Returns `FrozenStop` to persist on the trade row at `open_trade`.

**`compute()` rules:**
- `trigger = entry_price · (1 − frozen.d_init)` (long). `breached = observed <= trigger`.
- Uses ONLY the frozen `d_init` → **never widens**. Current σ is NOT used to recompute
  the protective trigger (only `d_hard` uses current σ).
- If `frozen is None` (pre-migration open trade, or `mode=fixed`): fall back to legacy
  fixed `risk_cfg["stop_loss"]`.

**`d_hard()` rules:** per §6.6: `clip(max(1.5·d_init, 5·σ_eff_current), 0.12, 0.20)`.

**Wire points:**
1. **Entry freeze** — `portfolio_scheduler.py` BUY submit path (`:1649-1659` `open_trade`):
   before/after `open_trade`, call `StopPolicy.freeze(...)` and persist the `FrozenStop`
   fields onto the trade row. Extend `open_trade` (`pg_store.py:764`) to accept the
   frozen stop params (add kwargs; `INSERT_TRADE` adds the new columns).
2. **Stop check** — replace the `_stop_loss_breached_symbols` call (`:1119`) with:
   for each held symbol, load its `FrozenStop` from the open trade row (one query),
   `StopPolicy.compute(...)`, collect `StopDecision`s. `breached` drives the SELL.
3. **Fire log** — in the stop submit block (Phase 2 location), insert a `stop_decisions`
   row from the `StopDecision` (+ `exit_order_id`).
4. **Shadow log** — when `risk.stop_shadow_enabled=true`, for EVERY held position each
   cycle (not only breached), compute both fixed and vol_scaled `StopDecision`s and
   insert a `stop_shadow_log` row. **Never sends orders.** Logs both triggers so Phase 6
   can compare.
5. **Disaster stop** — `portfolio_scheduler.py:2268-2276`: replace `ALPACA_STOP_LOSS_PCT`
   with `StopPolicy.d_hard(...)` for the whole-share bracket. Fractionable: synthetic
   per-cycle `d_hard` check (in addition to the protective check).

**`pg_store.py` additions:** `save_frozen_stop(trade_id, frozen)`, `load_frozen_stop(symbol)`
(reads the open trade row's stop_* columns), `insert_stop_decision(decision, exit_order_id)`,
`insert_stop_shadow(rows)`. All use the connection pattern of existing methods.

**Tests:** `tests/portfolio/test_stop_policy.py` (NEW — the interface test surface):
- `mode=fixed` reproduces the 2% threshold (parity with legacy) → keeps `test_day1_fixes`
  assertions valid in fixed mode.
- `mode=vol_scaled`: `d_init = clip(k·σ, floor, cap)`; high-vol name hits cap, low-vol
  hits floor.
- **never-widens**: two `compute()` calls with rising current σ → same `trigger`
  (frozen `d_init`).
- fallback hierarchy: symbol absent from `bars_df` → `vol_source` reflects the tier used.
- `d_hard` ≥ `d_init` and clipped to [12%, 20%].
- `freeze` then `compute` round-trips.

---

### Phase 4 — Vol-scaled protective stop + stop-risk sizing (the core, behind flag)

**Objective:** ship the new stop, default-off, measurable via the shadow log.

This phase = flip the wiring from Phase 3's `mode=fixed` default to supporting
`mode=vol_scaled`, gated by config.

**Config** (§9) — add `stop_loss_mode`, `stop_strategy_params`, σ lookbacks,
stop-risk sizing budgets, `stop_shadow_enabled`, `broker_disaster_stop`.

**Stop-risk sizing** — wire in the order-sizing path (where `target_weight → qty`).
After vol-targeter and regime_mult, compute:
```
max_notional = NAV · B_strat / (d_init + gap_buffer)
qty = min(target_qty, max_notional / price)
```
`d_init` from `StopPolicy.freeze(...)` called at order-construction time (same call
that persists the frozen stop). A wider `d_init` → smaller qty. Respect the aggregate
per-sleeve budget (75–100 bp). Do NOT let stop-risk sizing override the hard
`max_single_asset_pct` / `max_portfolio_exposure` caps.

**Do NOT enable `vol_scaled` in `config/trading.yaml`** — leave `stop_loss_mode: fixed`
as the shipped default. Enable only in shadow first (Phase 6), then paper, then canary.

**Tests:**
- Order-sizing: a high-vol symbol gets a smaller qty than a low-vol symbol at equal
  target weight (risk-equalized).
- Aggregate open-stop risk ≤ budget across a multi-position book.
- End-to-end cycle test with `stop_loss_mode: vol_scaled` + `stop_shadow_enabled: true`:
  shadow log rows written, NO orders differ from `fixed` mode (shadow is read-only on
  execution) — i.e., with shadow on and `mode=fixed`, behavior is identical to today.

---

### Phase 5 — Decouple ratchet S1↔S4 + risk-normalize (gates live promotion)

**Objective:** the loss-feedback ratchet is cross-strategy and count-based → it makes
the stop's effect un-interpretable. A loss in S1 must NOT raise S4's entry threshold.
Independently fixes F8 / the underdeployment loop.

**Current state (verified):**
- `performance.py` writes `feedback:entry_threshold` and `feedback:regime_scale`
  (`:1607-1608`, `:1728-1729`) on trigger.
- `portfolio_scheduler.py:582-600` `_get_feedback_threshold` reads
  `feedback:entry_threshold` (single key) as the S4 hard gate.
- `feedback:regime_scale` is written but never read in the portfolio path (F8).

**Redesign:**
- **Per-strategy keys:** `feedback:entry_threshold:S1`, `:S4`, `:S7`. `_get_feedback_threshold`
  reads the key for the strategy whose signal is being evaluated. (S1 has no discrete
  signal/threshold gate today — S1 is continuous rebalance — so the S1 key may be a
  no-op initially; document this. The decoupling's main value is that S1 losses stop
  poisoning S4.)
- **Magnitude-based, not count-based:** track an EWMA of R-multiples
  `R_j = net_pnl_j / risk_budget_j_at_entry` per strategy, where `risk_budget_j_at_entry`
  = `d_init · notional` (the frozen stop distance × notional). The ratchet raises the
  threshold when the EWMA of R drops below a band, decays back on wins. A loss of −0.2R
  and a loss of −3R no longer count equally.
- **Exit-reason filter:** only `stop_loss` and `portfolio_sell` (realized strategy
  losses) teach the ratchet. `LEGACY_FLATTEN`, operational exits, and `sentiment_reversal`
  (capital protection, not thesis failure) do NOT. Use the `exit_reason` on the closed
  trade (already attributed, §5).
- **Keep TTL** (48h) and the decay-back-on-wins behavior.

**Files:** `src/workers/performance.py` (write side), `src/workers/portfolio_scheduler.py:582-600`
(read side), `src/store/redis_store.py` (key helpers). Add a migration-free Redis key
schema change (keys are runtime, no SQL).

**This phase gates live promotion (Phase 7):** the canary is interpretable only once the
ratchet is per-strategy, so an S1 stop-out does not throttle S4. Ship Phase 5 to paper
before the canary.

**Tests:**
- An S1 loss raises `feedback:entry_threshold:S1` but NOT `:S4`.
- An S1 loss of −3R raises the S1 threshold more than a −0.2R loss (magnitude).
- A `LEGACY_FLATTEN` exit does not move any threshold.
- `sentiment_reversal` exit does not move any threshold.
- Decay: after wins, threshold decays toward baseline.

---

### Phase 6 — 15-min historical replay + measurement gates

**Objective:** prove the vol-scaled stop beats fixed 2% before paper.

**Why 15-min:** the synthetic stop checks every 15 min. Daily bars cannot reproduce
intra-cycle breach-and-recover. The live `stop_shadow_log` (Phase 3) captures real
observed prices + real held set; supplement with an **offline replay** from Alpaca
historical 15-min (or finer) bars.

**New file:** `scripts/replay_stop_loss.py` (read-only/idempotent, follows the
`validate_ticker_sentiment.py` pattern).

**Replay:** for each historical held position (from `trades` entry→exit windows), walk
the 15-min price path; compute fixed and vol_scaled triggers (frozen at entry from the
σ_eff that would have been computed then); log breach times; classify:
- **false stop** (S1): stopped but price returns above entry (or above exit, or positive
  P&L) before the next rebalance / signal invalidation.
- **false stop** (S4): stopped but price turns positive within the event window.
- **MAE/MFE** (vol-normalized), time-to-stop, trigger-to-fill slippage, gap loss beyond
  threshold, turnover/costs.
- **benefit**: further loss avoided, drawdown avoided, % stops after which price
  continues down ≥1R, expected shortfall, max loss/trade, portfolio drawdown, left-tail P&L.
- **systemic**: avg deployment, entries blocked by ratchet, turnover, cash, concentration,
  open-stop risk, net P&L per strategy.

**Compare variants:** 2%, 3%, 5%, 7%, vol_scaled (k=2.5/3/3.5/4), ATR(14)×k, no
protective (strategy-invalidation only), strategy-exit-only. **Walk-forward** (do not
select and evaluate on the same period).

**Exclude** the M7 trades (`net_pnl` NULL because entry fill was never reconciled before
exit reconcile — 10% of closed; see audit). Either exclude or back-fill entries first.

**Gates (the "measure before enforce" pass criteria):** on walk-forward OOS history,
- false-stop reduction ≥ 40% vs fixed 2%
- median net P&L > fixed 2%
- delta P&L positive in ≥ 70–75% of bootstrap resamples
- portfolio max-DD not > 10% worse
- ES95 not > 10% worse
- costs/slippage included
- open-stop risk within budget
- result not dependent on 1–2 names
Do not require all metrics improve — require return/costs improve without material tail
deterioration. **Do not enable `vol_scaled` live until these pass.**

---

### Phase 7 — Canary live (S1, 10% risk budget) → expand

**Objective:** safe live rollout.

- Enable the new stop on paper for **S1 only**, 10% risk budget, limited symbol set.
- Old fixed stop runs in **shadow** (logged, not executed) for direct comparison.
- Config rollback must not require a deploy (flag in `config/trading.yaml` → restart).
- Independent kill switch.
- Expand only after ≥ 20 exit events AND zero serious operational anomalies (partial
  fills, gaps, restart/duplicate-cycle, orphan orders).
- Low trade count → historical replay (Phase 6) gives the statistical validation;
  the canary validates **operability**, not statistics.

---

## 9. Config keys & validation

**`config/trading.yaml` — `risk:` section** (add; default keeps current behavior):

```yaml
risk:
  stop_loss: 0.02                      # legacy fixed (mode=fixed)
  stop_loss_mode: fixed                # fixed | vol_scaled  (ship: fixed)
  stop_strategy_params:
    S1: {k: 3.5, floor: 0.06, cap: 0.12}
    S4: {k: 2.0, floor: 0.03, cap: 0.08}
    S7: {k: 2.5, floor: 0.04, cap: 0.10}
    default: {k: 3.0, floor: 0.04, cap: 0.12}
  stop_sigma_lookback_fast: 20         # EWMA window
  stop_sigma_lookback_slow: 63         # STD window
  stop_sigma_ewma_floor_ratio: 0.8     # σ_eff = max(EWMA20, 0.8·STD63)
  stop_risk_budget_bp_per_pos: 12      # 12bp NAV per position
  stop_risk_budget_bp_aggregate: 100   # 100bp per sleeve
  stop_gap_buffer_pct: 0.005           # min gap buffer (0.5%)
  stop_shadow_enabled: false
  broker_disaster_stop:
    multiplier: 1.5
    sigma_multiple: 5.0
    floor_pct: 0.12
    cap_pct: 0.20
```

**`src/api/routes/config_routes.py`:**
- Extend `_RISK_BOUNDS` with the new scalar keys, e.g.:
  - `stop_loss_mode`: not in bounds (enum; validate against `{fixed, vol_scaled}`).
  - per-strategy `k`: (1.0, 6.0); `floor`: (0.01, 0.20); `cap`: (0.02, 0.30).
  - `stop_risk_budget_bp_per_pos`: (1, 50); `_aggregate`: (10, 300).
  - `broker_disaster_stop.floor_pct`/`cap_pct`: (0.05, 0.30).
- Add validation: for each strategy in `stop_strategy_params`, `floor < cap` and
  `k > 0`. 422 otherwise.
- Add the new keys to `_EDITABLE_RISK_FIELDS` (`:28`).
- Note the existing `stop_loss` cap (0.10): under `mode=fixed` keep (0.001, 0.10); under
  `mode=vol_scaled` the operative cap is the per-strategy `cap`, not `risk.stop_loss`.
  Keep `_detect_risk_weakening` working for `stop_loss`; document that switching
  `stop_loss_mode` to `vol_scaled` is itself a control change requiring a `reason`.

**Tests:** extend `tests/test_p0_08_config_validation.py` for the new keys + floor<cap +
the enum validation. Extend `tests/workers/test_risk_config_unification.py` for the new
YAML keys.

---

## 10. Measure-before-enforce gates (QX-01) — acceptance criteria

Before any live (paper or canary) enablement of `vol_scaled`:
1. **Attribution gate** — `scripts/audit_stop_loss_attribution.py` exits 0 (≥99%).
   Already PASS. Re-run after each phase; must stay green.
2. **Shadow divergence** — ≥ 30 sessions AND ≥ 30 divergence events between fixed and
   vol_scaled in `stop_shadow_log` (the divergence count matters more than session count
   at low trade frequency).
3. **Replay gates** (Phase 6) — all listed gates pass on walk-forward OOS.
4. **Ratchet decoupled** (Phase 5) — on paper, before canary.
5. **Operability** (canary) — ≥ 20 exits, zero serious anomalies.

---

## 11. Out of scope / explicitly deferred

- **Virtual sleeve accounting** — one-position-per-symbol holds (pyramiding guard);
  not needed for v1.
- **Trailing stop** — after +1R profit; a later phase. Until then, frozen `d_init`.
- **Migrating the protective stop to broker** (fractional simple stops) — do NOT. Keep
  it synthetic/uniform. Re-test Alpaca fractional simple-stop support as a *separate*
  empirical check (the 42210000 may be bracket/notional-specific), but only the disaster
  stop may use broker.
- **Changing legacy path (`execution.py`) behavior** — add `StopPolicy`, don't wire it
  into legacy this phase.
- **Entry filter** (deceleration / short-term reversal — the +95%/−6.3% case) — a
  separate workstream; not a stop problem.
- **S1 cooldown → next-rebalance** — the midnight-UTC cooldown risks S1 whipsaw
  (re-buy next day); noted, deferred. Keep current behavior.
- **S7 k MAE calibration** — S7 not live; use the prior until MAE data exists.
- **`√holding_days` multiplier** — rejected (§6.2); do not implement.

---

## 12. Acceptance checklist (per phase)

- [ ] **P1** `034_stop_loss_redesign.sql` applies cleanly (idempotent); new columns/tables exist.
- [ ] **P2** Stop exit writes an `execution_decisions` SELL row; Decision Log shows stops.
- [ ] **P3** `StopPolicy` interface tested; freeze-at-entry persisted on new trades;
      `stop_decisions` row on every fire; `stop_shadow_log` rows when flag on (no orders).
      Never-widens test passes. `mode=fixed` reproduces 2%.
- [ ] **P4** `vol_scaled` mode + stop-risk sizing wired; wider `d_init` → smaller qty;
      default stays `fixed`; full suite green.
- [ ] **P5** S1 loss moves only `:S1` threshold; magnitude-based; operational exits
      excluded; decays on wins.
- [ ] **P6** `replay_stop_loss.py` runs; all gates pass on walk-forward OOS.
- [ ] **P7** S1 canary, 10% budget, ≥20 exits, zero anomalies, old stop in shadow.
- [ ] `scripts/audit_stop_loss_attribution.py` green after every phase.
- [ ] No LLM / remote call added to the 15-min cycle.
- [ ] All tests pass except the 8 updated `test_day1_fixes` assertions.

---

## 13. Implementation order for Kimi (one shot)

Implement in this order; each phase's tests must pass before the next:
1. Phase 1 (migration 034) → 2. Phase 2 (Gap A) → 3. Phase 3 (StopPolicy + freeze + logs)
→ 4. Phase 4 (vol_scaled + sizing, flag-off) → 5. Phase 5 (ratchet decouple)
→ 6. Phase 6 (replay harness + gates) → 7. Phase 7 (canary runbook).

Phases 1–4 are the code; 5 is the gating refactor; 6–7 are measurement/ops. Do NOT flip
`stop_loss_mode` to `vol_scaled` in `config/trading.yaml` — leave it `fixed` until Phase
6 gates pass. Commit per phase with conventional commits (`feat(stop): ...`,
`refactor(ratchet): ...`, etc.). Run `scripts/audit_stop_loss_attribution.py` and the
full test suite after each phase.