# Sector Exposure Cap Implementation Plan

> **Status (2026-07-15):** All tasks implemented, tested, and MERGED to main (commit `ea436fd`). Shipped disabled (`max_sector_exposure: 0.0` in `config/trading.yaml`) — enabling (suggested 0.10) is a pending operator decision. Checkboxes below updated to reflect implementation status.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the already-implemented (but dormant) per-sector BUY exposure cap into the live portfolio path: sector map from config, cap value config-driven, disabled by default (0 = off; enabling is an operator flip).

**Architecture:** `ConstraintEnforcer._enforce_sector_exposure` (`src/portfolio/constraints.py:252`) is complete and tested-by-design — it never binds today only because the scheduler constructs the enforcer without a `sector_map` and the cap is a module constant. This plan: (1) makes the cap a constructor param with `<=0 = disabled`, (2) adds a `sectors:` map + `risk.max_sector_exposure` to trading.yaml, (3) passes both at the single construction site (`portfolio_scheduler.py:1392`).

**Tech Stack:** Python 3.11, PyYAML, pytest (`.venv/bin/pytest`).

---

## Context (read before Task 1)

Read `CLAUDE.md` first. Motivating evidence: 2026-07-10 (3 semis) and 2026-07-13
(9 semis + SOXX, −$167, all stopped in the SAME 14:07 cycle) — correlated sector
blocks enter together and get stopped together.

**Honest scope note (do not oversell in comments/docs):** at today's position
sizing (~$650/name) the semi block is ~6% of NAV, so a 25% — or even 15% — cap
would NOT have bound this morning. The cap becomes real protection as deployment
grows toward the 50% design (semis ≈ 20% of the watchlist → ~10-12% NAV possible),
and it is COMPLEMENTARY to the F9a vol-scaled stop redesign (separate, parked
workstream) — it limits concentration, it does not fix sub-σ stops. The suggested
operator flip value is 0.10.

Constraints:
- Branch `sector-cap-2026-07-13` off `main`. No merge, no deploy, no config-value
  flips: `max_sector_exposure` ships as `0.0` (disabled) — enabling is operator.
- Strict TDD. Full suite at the end: only the 10 known pre-existing failures
  (5 tests/api/test_weight_approval.py, 3 tests/workers/test_sec_edgar_ingestion.py,
  2 tests/workers/test_sentiment_worker.py::TestEnsembleWeightReading).
- Taxonomy note: the map below is deliberately coarse (11 groups). Known
  imperfections (NOK is telecom-equipment but correlates with semis) are accepted
  v1 tradeoffs — do NOT invent a finer taxonomy.

---

### Task 1: Config-driven cap in ConstraintEnforcer

**Files:**
- Modify: `src/portfolio/constraints.py` (`_MAX_SECTOR_PCT` at line 12; `__init__`;
  `_enforce_sector_exposure` lines 252-292)
- Test: `tests/portfolio/test_constraints.py` (append)

- [x] **Step 1: Write the failing tests**

Append to `tests/portfolio/test_constraints.py`, mirroring the file's existing
order/market fixture helpers (read the top of the file first and reuse its
`CombinedOrder`/`MarketSnapshot` builders — do not invent new ones):

```python
class TestSectorCapConfig:
    def _orders_two_semis(self):
        # Build two BUY orders in the same sector totalling 30% of a 100k NAV
        # using the file's existing order-builder helper.
        ...  # use existing helpers: 2 BUYs, 15k notional each, symbols NVDA, AMD

    def test_sector_cap_param_overrides_module_default(self):
        enforcer = ConstraintEnforcer(
            sector_map={"NVDA": "semis", "AMD": "semis"},
            max_sector_pct=0.20,
        )
        orders, market = self._orders_two_semis()
        result, violations = enforcer.enforce(orders, market, nav=100_000, allocations={})
        assert any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)
        total = sum(o.quantity * market.price_of(o.symbol) for o in result if o.side.value == "BUY")
        assert total <= 0.20 * 100_000 + 1e-6

    def test_sector_cap_zero_disables(self):
        enforcer = ConstraintEnforcer(
            sector_map={"NVDA": "semis", "AMD": "semis"},
            max_sector_pct=0.0,
        )
        orders, market = self._orders_two_semis()
        _, violations = enforcer.enforce(orders, market, nav=100_000, allocations={})
        assert not any(v.constraint_name == "MAX_SECTOR_EXPOSURE" for v in violations)

    def test_default_unchanged_without_param(self):
        """Backtests constructing ConstraintEnforcer(sector_map=...) without the
        new param keep the historical 0.25 behavior."""
        enforcer = ConstraintEnforcer(sector_map={"NVDA": "semis"})
        assert enforcer._max_sector_pct == 0.25
```

Complete `_orders_two_semis` with the file's real helpers before running.

- [x] **Step 2: RED**

Run: `.venv/bin/pytest tests/portfolio/test_constraints.py -q -k SectorCap`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'max_sector_pct'`.

- [x] **Step 3: Implement**

In `__init__`, add parameter `max_sector_pct: float = _MAX_SECTOR_PCT` (keeps the
module constant as the backward-compatible default) and store
`self._max_sector_pct = max_sector_pct`.

In `_enforce_sector_exposure`, change the guard and the two constant uses:

```python
        if self._sector_map is None or self._max_sector_pct <= 0:
            return orders, []

        cap = self._max_sector_pct * nav
```

and in the `ConstraintViolation(...)`: `threshold=self._max_sector_pct,`.

Update the class docstring line 48 ("≤ 25% NAV") to "≤ max_sector_pct × NAV
(default 0.25; ≤0 disables; live value from trading.yaml risk.max_sector_exposure)".

- [x] **Step 4: GREEN + commit**

Run: `.venv/bin/pytest tests/portfolio/test_constraints.py -q`
Expected: all PASS.

```bash
git add src/portfolio/constraints.py tests/portfolio/test_constraints.py
git commit -m "feat(risk): config-driven sector exposure cap (<=0 disables, default keeps 0.25)"
```

---

### Task 2: Sector map + cap value in trading.yaml

**Files:**
- Modify: `config/trading.yaml` (risk section + new top-level `sectors:` block)

- [x] **Step 1: Add the cap to the risk section** (after `max_portfolio_exposure`):

```yaml
  # Per-sector BUY exposure cap (fraction of NAV). 0 = DISABLED (current state).
  # Evidence: 2026-07-10 (3 semis) and 2026-07-13 (9 semis + SOXX, same cycle)
  # stopped out together. Suggested operator value when enabling: 0.10.
  # NOTE: complementary to the F9a stop redesign — caps concentration, does not
  # fix sub-sigma stops.
  max_sector_exposure: 0.0
```

- [x] **Step 2: Add the sector map** (new top-level block, after `symbols:`):

```yaml
# Sector map for the MAX_SECTOR_EXPOSURE constraint (coarse 11-group taxonomy;
# formalizes the watchlist comment blocks). Symbols missing here fall into the
# "unknown" bucket, which is capped as its own sector.
sectors:
  tech: [AAPL, MSFT, GOOGL, AMZN, META, CRM, ADBE, ORCL, NOW, SNOW, CSCO, PLTR, PANW, IBM, SAP, BABA, BIDU, JD, SONY, INFY, XLK]
  semis: [NVDA, AMD, AVGO, QCOM, TXN, INTC, MU, ASML, ARM, AMAT, TSM, MRVL, DELL, WDC, SOXX]
  financials: [JPM, BAC, GS, MS, WFC, C, AXP, MA, V, BRK.B, UBS, DB, HOOD, XLF]
  consumer: [WMT, COST, MCD, SBUX, NKE, HD, TSLA, GM, F, TM, PG]
  media: [DIS, CMCSA, NFLX, ROKU, RDDT]
  healthcare: [JNJ, PFE, MRK, UNH, ABBV, LLY, NVO, AZN, XLV]
  energy: [CVX, XOM, SHEL, BP, PBR, XLE]
  industrials: [BA, GE, CAT, MMM]
  materials: [RIO, VALE]
  telecom: [T, VZ, TMUS, ERIC, NOK]
  etf_broad: [SPY, QQQ, IWM, SPCX]
```

(Yes, the YAML shape is sector → list; Task 3's loader inverts it to
symbol → sector, which is what `ConstraintEnforcer` expects.)

- [x] **Step 3: Commit**

```bash
git add config/trading.yaml
git commit -m "feat(risk): sector map + max_sector_exposure config (shipped disabled)"
```

---

### Task 3: Loader + wiring in the scheduler

**Files:**
- Modify: `src/workers/portfolio_scheduler.py` (`_load_risk_config`; enforcer
  construction at line ~1392; new `_load_sector_map()`)
- Test: `tests/workers/test_portfolio_scheduler.py` (append)

- [x] **Step 1: Write the failing tests**

```python
class TestSectorMapLoader:
    def test_load_sector_map_inverts_yaml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "trading.yaml"
        cfg.write_text(
            "sectors:\n  semis: [NVDA, AMD]\n  tech: [AAPL]\n"
        )
        from src.workers import portfolio_scheduler as ps
        monkeypatch.setattr(ps, "_TRADING_YAML_PATH", str(cfg), raising=False)
        result = ps._load_sector_map()
        assert result == {"NVDA": "semis", "AMD": "semis", "AAPL": "tech"}

    def test_load_sector_map_absent_returns_none(self, tmp_path, monkeypatch):
        cfg = tmp_path / "trading.yaml"
        cfg.write_text("risk: {}\n")
        from src.workers import portfolio_scheduler as ps
        monkeypatch.setattr(ps, "_TRADING_YAML_PATH", str(cfg), raising=False)
        assert ps._load_sector_map() is None
```

BEFORE writing these, check how `_load_risk_config` locates trading.yaml (grep
`_load_risk_config` and the path constant it uses) and mirror the SAME mechanism
for `_load_sector_map` — the monkeypatch target above must be the real path
symbol; adjust the tests to whatever the file actually uses (env var, constant,
or hardcoded path). Do not introduce a second config-path convention.

- [x] **Step 2: RED**, then implement

(a) `_load_sector_map()` in the scheduler (module level, near `_load_risk_config`):

```python
def _load_sector_map() -> dict[str, str] | None:
    """Invert the trading.yaml `sectors:` block to {symbol: sector}.

    Fail-open (None) when the block is missing/unreadable: the enforcer treats
    None as 'sector pass disabled', matching pre-2026-07-13 behavior.
    """
    try:
        import yaml
        with open(_TRADING_YAML_PATH) as f:        # use the file's real path symbol
            raw = yaml.safe_load(f) or {}
        sectors = raw.get("sectors") or {}
        if not sectors:
            return None
        return {
            str(sym): str(sector)
            for sector, symbols in sectors.items()
            for sym in (symbols or [])
        }
    except Exception as exc:
        log.warning("Could not load sector map (%s) — sector cap disabled", exc)
        return None
```

(b) `_load_risk_config`: add `"max_sector_exposure"` to the returned dict
(default `0.0` when absent), following the existing keys' pattern.

(c) Construction site (~line 1392):

```python
        constraint_enforcer=ConstraintEnforcer(
            max_portfolio_exposure=_risk_cfg["max_portfolio_exposure"],
            max_single_asset_pct=_risk_cfg["max_single_asset_pct"],
            sector_map=_load_sector_map(),
            max_sector_pct=_risk_cfg.get("max_sector_exposure", 0.0),
        ),
```

(Read the actual current call first — if other kwargs were added by parallel
workstreams, preserve them.)

- [x] **Step 3: GREEN + commit**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py tests/portfolio/test_constraints.py -q`
Expected: PASS.

```bash
git add src/workers/portfolio_scheduler.py tests/workers/test_portfolio_scheduler.py
git commit -m "feat(risk): wire sector map + config cap into the live constraint enforcer"
```

---

### Task 4: Full suite + report

- [x] `.venv/bin/pytest -q` → only the 10 known pre-existing failures.
- [x] Report: branch + commits, test counts, explicit confirmation that
`max_sector_exposure` shipped as 0.0 (live behavior unchanged) and no deploy ran.

---

## Operator flip after review (NOT for the implementing agent)

1. Merge; `docker compose build worker beat && docker compose up -d worker beat`.
2. Enable: set `max_sector_exposure: 0.10` in trading.yaml → rebuild → verify the
   next cycles log no `MAX_SECTOR_EXPOSURE` at current sizing (expected: binds
   only as deployment grows).
3. Re-evaluate the value together with the F9a stop decision — the two levers
   address the same incident class from different sides.
