# #75 — /api/orders qty:"None" + degenerate herfindahl_index — Execution Spec

> **For the executing agent (minimax):** You have NO prior context on this repo. Read this whole document once, then execute both tasks exactly as written, on ONE git branch with ONE PR that closes #75. Do NOT improvise beyond this spec. A human reviewer will review the PR before merge — your job is to execute and hand back, not to merge.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — an LLM-based paper-trading system. Both fixes here are **low-risk** (an API display bug and a reporting metric) — no order execution, no sizing, no kill-switch, no sentiment scoring.

**Goal:** Close GitHub issue #75, which bundles two small independent bugs from the 2026-07-15 forensic report:
- **A** — `/api/orders` serializes `qty` as the literal string `"None"` for notional-only orders (should be JSON `null`).
- **B** — `risk_reports.herfindahl_index` is a constant `1.0` (degenerate) because the risk monitor feeds it `{"portfolio": 1.0}` instead of real per-symbol weights.

**Tech stack:** Python 3, FastAPI + `fastapi.testclient.TestClient`, pytest (run via `uv run pytest`), Alpaca SDK, PostgreSQL. `uv.lock` unchanged — no dependency work.

**Branch:** `fix/75-orders-qty-null-and-herfindahl`

---

## Session protocol

1. **Test runner:** always `uv run pytest <path> -v`; `uv run pytest -q` for the full suite. Never bare `pytest`.
2. **TDD, strictly:** write the failing test → run it and SEE it fail → minimal implementation → run it and SEE it pass → run the file's module → commit. Do both bugs as separate commits on the same branch.
3. **One branch + one PR** (name above). PR body must contain `closes #75` and a 2-3 line summary of both fixes.
4. **Touch only these files:** `src/api/routes/trading.py`, `tests/api/test_trading_routes.py`, `src/portfolio/risk_monitor.py`, `src/workers/risk_monitor_task.py`, `tests/portfolio/test_risk_monitor.py`, `tests/workers/test_risk_monitor_task.py`. Nothing else.
5. **No DB migrations, no config changes.**
6. **Never delete/weaken an existing test.** Both changes are additive/backward-compatible; existing tests must stay green untouched.
7. **Full-suite gate before the PR:** capture the baseline first (`uv run pytest -q 2>&1 | tail -5`). Known pre-existing failures in this repo (NOT yours): `tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` (issue #112) and a flaky `tests/api/test_strategies_routes.py::test_get_s1_backtest_returns_equity_curve`.
8. **Do not deploy, do not restart containers, do not push to `main`.** PR only.

---

## BUG A — `/api/orders` serializes `qty` as the string `"None"`

### Root cause (verified)
`src/api/routes/trading.py` line 76 serializes every order's qty as `"qty": str(o.qty)`. A notional-only order (sized by dollar amount, not share count) has `o.qty is None`, so `str(None)` produces the literal string `"None"`. It should be JSON `null`. The adjacent field already does the right thing: line 77 is `"filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None`.

### Files
- Modify: `src/api/routes/trading.py`
- Test: `tests/api/test_trading_routes.py`

### Steps

- [ ] **Step A1 — Write the failing test.** Append to `tests/api/test_trading_routes.py` (its top already imports `MagicMock`, `TestClient`, `app`, `require_api_key`, `get_alpaca_trading_client`, `get_pg_store`, and defines `_skip_auth`):

```python
def test_get_orders_serializes_none_qty_as_null():
    """#75: a notional-only order has qty=None; it must serialize as JSON null,
    not the literal string "None"."""
    from datetime import datetime, timezone

    mock_order = MagicMock()
    mock_order.id = "ntl-1"
    mock_order.symbol = "AAPL"
    mock_order.side.value = "buy"
    mock_order.qty = None  # notional-only order
    mock_order.filled_avg_price = "177.53"
    mock_order.status.value = "filled"
    mock_order.filled_at = datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc)
    mock_order.submitted_at = datetime(2026, 5, 18, 13, 55, tzinfo=timezone.utc)

    mock_client = MagicMock()
    mock_client.get_orders.return_value = [mock_order]
    mock_pg = MagicMock()
    mock_pg.fetch_order_trace.return_value = {}
    app.dependency_overrides[get_alpaca_trading_client] = lambda: mock_client
    app.dependency_overrides[get_pg_store] = lambda: mock_pg
    app.dependency_overrides[require_api_key] = _skip_auth

    tc = TestClient(app)
    resp = tc.get("/api/orders")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["qty"] is None
    assert data[0]["qty"] != "None"
```

- [ ] **Step A2 — Run it, confirm it fails.**

Run: `uv run pytest tests/api/test_trading_routes.py::test_get_orders_serializes_none_qty_as_null -v`
Expected: FAIL — `assert 'None' is None` (the current code emits the string `"None"`).

- [ ] **Step A3 — Fix.** In `src/api/routes/trading.py`, find:

```python
            "qty": str(o.qty),
```

and replace it with:

```python
            "qty": str(o.qty) if o.qty is not None else None,
```

- [ ] **Step A4 — Run it, confirm it passes.**

Run: `uv run pytest tests/api/test_trading_routes.py -v`
Expected: PASS (new test + all pre-existing trading-route tests, including `test_get_orders_returns_list` which uses a non-None qty and must still serialize `"10"`).

- [ ] **Step A5 — Commit.**

```bash
git add src/api/routes/trading.py tests/api/test_trading_routes.py
git commit -m "fix(#75): serialize notional-only order qty as null, not \"None\"

/api/orders did str(o.qty) which turns a None qty (notional-only orders) into
the literal string \"None\". Emit JSON null instead, matching the adjacent
filled_avg_price handling.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## BUG B — `herfindahl_index` is a constant 1.0 (measures nothing)

### Root cause (verified)
`compute_risk_report` (`src/workers/risk_monitor_task.py`) builds `current_weights = {"portfolio": 1.0}` (a single synthetic strategy), and `PortfolioRiskMonitor.compute_report` computes `hhi = _herfindahl(current_weights)`. The Herfindahl index of a single 1.0 weight is `1.0² = 1.0`, always — it never measures per-symbol concentration. The `current_weights` dict must stay `{"portfolio": 1.0}` because it also drives the per-strategy metrics and weight-drift alerts (which expect strategy keys), so the fix supplies the HHI separately from real per-symbol notional weights, mirroring how `combined_drawdown_override` was added for #107.

### Files
- Modify: `src/portfolio/risk_monitor.py` (add `herfindahl_override` to `compute_report`)
- Modify: `src/workers/risk_monitor_task.py` (add `_fetch_position_weights`; wire the override)
- Test: `tests/portfolio/test_risk_monitor.py`, `tests/workers/test_risk_monitor_task.py`

### Steps

- [ ] **Step B1 — Write the failing tests.**

Append to `tests/portfolio/test_risk_monitor.py` (it already has `_make_report`, which forwards `**kwargs` to `compute_report`):

```python
class TestHerfindahlOverride:
    """#75: HHI must come from real per-symbol weights, supplied via override."""

    def test_override_used_when_provided(self):
        report = _make_report(herfindahl_override=0.25)
        assert report.herfindahl_index == 0.25

    def test_falls_back_to_current_weights_without_override(self):
        # No override -> keeps the existing {"portfolio": 1.0} behavior (1.0).
        report = _make_report()
        assert report.herfindahl_index == pytest.approx(1.0)
```

Append to `tests/workers/test_risk_monitor_task.py`:

```python
class TestFetchPositionWeights:
    """#75: per-symbol notional weights for a meaningful concentration metric."""

    def test_normalizes_by_gross(self):
        from unittest.mock import MagicMock, patch
        from src.workers.risk_monitor_task import _fetch_position_weights

        p1 = MagicMock(); p1.symbol = "AAPL"; p1.market_value = "3000"
        p2 = MagicMock(); p2.symbol = "MSFT"; p2.market_value = "1000"
        client = MagicMock()
        client.get_all_positions.return_value = [p1, p2]
        with patch("alpaca.trading.client.TradingClient", return_value=client):
            weights = _fetch_position_weights()
        assert weights == {"AAPL": 0.75, "MSFT": 0.25}

    def test_empty_on_broker_error(self):
        from unittest.mock import patch
        from src.workers.risk_monitor_task import _fetch_position_weights

        with patch("alpaca.trading.client.TradingClient", side_effect=RuntimeError("down")):
            assert _fetch_position_weights() == {}
```

- [ ] **Step B2 — Run them, confirm they fail.**

Run: `uv run pytest tests/portfolio/test_risk_monitor.py::TestHerfindahlOverride tests/workers/test_risk_monitor_task.py::TestFetchPositionWeights -v`
Expected: FAIL — `compute_report() got an unexpected keyword argument 'herfindahl_override'` and `cannot import name '_fetch_position_weights'`.

- [ ] **Step B3 — Add the `herfindahl_override` parameter.** In `src/portfolio/risk_monitor.py`, find the `compute_report` signature line:

```python
        combined_drawdown_override: float | None = None,
```

and replace it with:

```python
        combined_drawdown_override: float | None = None,
        herfindahl_override: float | None = None,
```

Then find:

```python
        hhi = _herfindahl(current_weights)
```

and replace it with:

```python
        if herfindahl_override is not None:
            hhi = herfindahl_override
        else:
            hhi = _herfindahl(current_weights)
```

- [ ] **Step B4 — Add `_fetch_position_weights` and wire the override.** In `src/workers/risk_monitor_task.py`, add this new module-level function right before `def _store_risk_report(pg, report) -> int:` (the other `_fetch_*` helpers already sit above it):

```python
def _fetch_position_weights() -> dict[str, float]:
    """Per-symbol portfolio weights (|market value| / gross) from Alpaca, for a
    meaningful concentration (Herfindahl) metric. #75: the report previously fed
    {"portfolio": 1.0}, making HHI a constant 1.0 that measured nothing. Returns
    {} on any broker error / no positions → caller falls back to the old value.
    """
    from alpaca.trading.client import TradingClient

    from src.config import config

    try:
        client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        market_values = {
            p.symbol: abs(float(p.market_value)) for p in client.get_all_positions()
        }
        gross = sum(market_values.values())
        if gross <= 0:
            return {}
        return {sym: mv / gross for sym, mv in market_values.items()}
    except Exception as e:
        log.warning("Could not fetch position weights for HHI (#75): %s", e)
        return {}
```

Then, in `compute_risk_report`, find:

```python
        report = monitor.compute_report(
            strategy_returns=strategy_returns,
            current_weights=current_weights,
            total_exposure=total_exposure,
            nav=nav,
            combined_drawdown_override=equity_dd,
        )
```

and replace it with:

```python
        from src.portfolio.risk_monitor import _herfindahl

        position_weights = _fetch_position_weights()
        hhi_override = _herfindahl(position_weights) if position_weights else None

        report = monitor.compute_report(
            strategy_returns=strategy_returns,
            current_weights=current_weights,
            total_exposure=total_exposure,
            nav=nav,
            combined_drawdown_override=equity_dd,
            herfindahl_override=hhi_override,
        )
```

- [ ] **Step B5 — Run the tests, confirm they pass.**

Run: `uv run pytest tests/portfolio/test_risk_monitor.py tests/workers/test_risk_monitor_task.py -v`
Expected: PASS (new classes + all pre-existing tests in both files). Also import-check: `uv run python -c "import src.workers.risk_monitor_task"` → no error.

- [ ] **Step B6 — Commit.**

```bash
git add src/portfolio/risk_monitor.py src/workers/risk_monitor_task.py tests/portfolio/test_risk_monitor.py tests/workers/test_risk_monitor_task.py
git commit -m "fix(#75): compute herfindahl_index from real per-symbol weights

HHI was _herfindahl({\"portfolio\": 1.0}) == 1.0 always. Add a herfindahl_override
to compute_report and feed it per-symbol notional weights from Alpaca, so the
concentration metric is meaningful. Fails open to the old value when the broker
is unreachable. Per-strategy metrics keep using current_weights.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step B7 — Full suite + PR.** `uv run pytest -q` (baseline-identical failures only), then open the PR with `closes #75` and a short summary of both fixes.

---

## Hand-back checklist (for the human reviewer)

- **Bug A:** verify the non-None path is unchanged (`test_get_orders_returns_list` still asserts `"10"`), and null is emitted only when `o.qty is None`.
- **Bug B:** verify `current_weights` (per-strategy metrics / weight-drift alerts) is untouched — only the HHI value changed. Confirm the fail-open path (broker error → `_fetch_position_weights()` returns `{}` → `hhi_override=None` → old `_herfindahl(current_weights)` behavior). Note the second `get_all_positions()` call per daily run is an accepted minor cost for isolation (mirrors #107's separate `_fetch_equity_curve` helper); a future refactor could fold it into `_fetch_account_state`.
