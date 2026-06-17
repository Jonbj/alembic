# Trade Analytics Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-dimensional P&L analytics (per symbol, regime, hour, score bucket, hold time) to the trading system, wire `postmortem.py` for real-time loss diagnosis, and surface everything in a new Analytics tab on the Trades frontend page.

**Architecture:** Analytics-on-read — five SQL GROUP BY queries on the existing `trades` table (no materialized tables). One new column `trades.postmortem_diagnosis TEXT` written at trade close for losses that exceed the trigger threshold. Three new API endpoints serve analytics data to the frontend.

**Tech Stack:** PostgreSQL (psycopg2), FastAPI, React + recharts (already installed), TypeScript.

---

## File Map

| Action | Path |
|--------|------|
| Create | `migrations/017_trade_analytics.sql` |
| Modify | `src/store/pg_store.py` — add 7 new methods, update `_CLOSE_TRADE` SQL + `close_trade()`, update `fetch_trades()` SELECT |
| Modify | `src/workers/execution.py` — wire postmortem after `close_trade()` |
| Modify | `src/api/routes/trading.py` — 3 new endpoints |
| Create | `frontend/src/api/analytics.ts` |
| Modify | `frontend/src/api/trades.ts` — add `postmortem_diagnosis` to `Trade` interface |
| Modify | `frontend/src/pages/Trades.tsx` — add Analytics tab + 5 charts + postmortem badge |
| Modify | `tests/test_pg_store.py` — tests for new methods |
| Modify | `tests/api/test_trading_routes.py` — tests for new endpoints |
| Create | `tests/workers/test_execution_postmortem.py` — postmortem wiring tests |

---

## Task 1: Migration + `close_trade` returns ID + `postmortem_diagnosis` in `fetch_trades`

**Files:**
- Create: `migrations/017_trade_analytics.sql`
- Modify: `src/store/pg_store.py` (lines ~312–387, ~411)
- Modify: `frontend/src/api/trades.ts`
- Test: `tests/test_pg_store.py`

- [ ] **Step 1: Write failing test — `close_trade` must return an int**

Add this class to `tests/test_pg_store.py` after the existing `TestCloseTrade` class:

```python
class TestCloseTradeReturnsId:
    def test_close_trade_returns_trade_id(self):
        """close_trade must return the id of the updated row (RETURNING id)."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = (99,)

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.close_trade(
            symbol="TSLA",
            exit_price=205.0,
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="stop_loss",
            entry_price=200.0,
        )
        assert result == 99
        sql = mock_cur.execute.call_args[0][0]
        assert "RETURNING id" in sql

    def test_close_trade_returns_none_when_no_open_trade(self):
        """Returns None if no open trade row matched (fetchone returns None)."""
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.close_trade(
            symbol="AAPL",
            exit_price=180.0,
            exit_time=datetime(2026, 6, 5, 16, tzinfo=timezone.utc),
            exit_reason="take_profit",
        )
        assert result is None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/test_pg_store.py::TestCloseTradeReturnsId -v
```

Expected: FAIL — `AssertionError` on `result == 99` (currently returns None).

- [ ] **Step 3: Create migration file**

Create `migrations/017_trade_analytics.sql`:

```sql
-- Phase A: Trade Analytics Engine
ALTER TABLE trades ADD COLUMN IF NOT EXISTS postmortem_diagnosis TEXT;
```

- [ ] **Step 4: Update `_CLOSE_TRADE` SQL and `close_trade()` in `src/store/pg_store.py`**

Replace the existing `_CLOSE_TRADE` constant (around line 312):

```python
    _CLOSE_TRADE = """
        UPDATE trades SET
            exit_price   = %s,
            exit_time    = %s,
            exit_reason  = %s,
            entry_price  = COALESCE(entry_price, %s),
            gross_pnl    = (%s - COALESCE(entry_price, %s)) * qty,
            slippage_est = entry_notional * 0.0005,
            net_pnl      = ((%s - COALESCE(entry_price, %s)) * qty) - (entry_notional * 0.0005)
        WHERE symbol = %s AND exit_time IS NULL
        RETURNING id
    """
```

Replace the `close_trade` method body (around lines 350–387):

```python
    def close_trade(
        self,
        symbol: str,
        exit_price: float,
        exit_time,
        exit_reason: str,
        entry_price: float | None = None,
    ) -> int | None:
        """Update the open trade row for symbol with exit data and compute P&L.

        Returns the id of the updated row, or None if no open trade was found.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    self._CLOSE_TRADE,
                    (exit_price, exit_time, exit_reason,
                     entry_price,
                     exit_price, entry_price,
                     exit_price, entry_price,
                     symbol),
                )
                row = cur.fetchone()
            conn.commit()
            return int(row[0]) if row else None
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 5: Add `postmortem_diagnosis` to `fetch_trades()` SELECT**

In `src/store/pg_store.py`, find the `fetch_trades` method (around line 389). Replace the SELECT inside it:

```python
                cur.execute(
                    f"""SELECT id, symbol, signal_id, decision_id, entry_order_id,
                               entry_price, entry_time, entry_notional, score, regime_mult,
                               exit_price, exit_time, exit_reason, qty,
                               gross_pnl, slippage_est, net_pnl, postmortem_diagnosis, created_at
                        FROM trades {where}
                        ORDER BY entry_time DESC LIMIT %s""",
                    params,
                )
```

- [ ] **Step 6: Add `postmortem_diagnosis` to the `Trade` interface in `frontend/src/api/trades.ts`**

Add one field after `net_pnl`:

```typescript
  net_pnl: number | null
  postmortem_diagnosis: string | null
  created_at: string
```

- [ ] **Step 7: Run tests to confirm they pass**

```bash
pytest tests/test_pg_store.py::TestCloseTradeReturnsId -v
pytest tests/test_pg_store.py::TestCloseTrade -v
```

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add migrations/017_trade_analytics.sql src/store/pg_store.py frontend/src/api/trades.ts tests/test_pg_store.py
git commit -m "feat(analytics): add postmortem_diagnosis column + close_trade returns id"
```

---

## Task 2: Five analytics fetch methods in `pg_store.py`

**Files:**
- Modify: `src/store/pg_store.py` (append after `reconcile_trade_fills`)
- Test: `tests/test_pg_store.py`

- [ ] **Step 1: Write failing tests for analytics methods**

Add to `tests/test_pg_store.py`:

```python
class TestFetchAnalyticsBySymbol:
    def test_returns_list_of_dicts_with_expected_keys(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("label",), ("trade_count",), ("win_rate",),
            ("avg_net_pnl",), ("total_net_pnl",),
        ]
        mock_cur.fetchall.return_value = [("NVDA", 5, 0.6, 12.5, 62.5)]

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        rows = store.fetch_analytics_by_symbol(limit_days=90)
        assert isinstance(rows, list)
        assert rows[0]["label"] == "NVDA"
        assert rows[0]["trade_count"] == 5
        assert "win_rate" in rows[0]
        assert "avg_net_pnl" in rows[0]
        assert "total_net_pnl" in rows[0]

    def test_rollback_on_error(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception):
            store.fetch_analytics_by_symbol()
        mock_conn.rollback.assert_called_once()


class TestFetchAnalyticsByDimension:
    """Smoke-tests for the four dimension-based analytics methods."""

    def _make_store(self, rows):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.description = [
            ("label",), ("trade_count",), ("win_rate",), ("avg_net_pnl",), ("total_net_pnl",),
        ]
        mock_cur.fetchall.return_value = rows
        return PostgreSQLStore(conn=mock_conn, use_pool=False)

    def test_fetch_analytics_by_regime(self):
        store = self._make_store([("neutral", 3, 0.67, 8.0, 24.0)])
        rows = store.fetch_analytics_by_regime()
        assert rows[0]["label"] == "neutral"

    def test_fetch_analytics_by_hour(self):
        store = self._make_store([("10", 2, 0.5, 5.0, 10.0)])
        rows = store.fetch_analytics_by_hour()
        assert rows[0]["label"] == "10"

    def test_fetch_analytics_by_score_bucket(self):
        store = self._make_store([("0.3–0.4", 4, 0.75, 11.0, 44.0)])
        rows = store.fetch_analytics_by_score_bucket()
        assert rows[0]["label"] == "0.3–0.4"

    def test_fetch_analytics_by_hold_time(self):
        store = self._make_store([("<1h", 6, 0.5, 7.0, 42.0)])
        rows = store.fetch_analytics_by_hold_time()
        assert rows[0]["label"] == "<1h"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_pg_store.py::TestFetchAnalyticsBySymbol tests/test_pg_store.py::TestFetchAnalyticsByDimension -v
```

Expected: FAIL — `AttributeError: 'PostgreSQLStore' object has no attribute 'fetch_analytics_by_symbol'`.

- [ ] **Step 3: Add the SQL constants and five methods to `src/store/pg_store.py`**

Insert before the `log_weight_update` method (around line 889):

```python
    # -------------------------------------------------------------------------
    # Trade analytics (Phase A)
    # -------------------------------------------------------------------------

    _ANALYTICS_BASE_FILTER = (
        "WHERE exit_time IS NOT NULL"
        "  AND exit_time >= now() - (%s || ' days')::interval"
    )

    _ANALYTICS_BY_SYMBOL = """
        SELECT
            symbol AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY symbol
        ORDER BY total_net_pnl DESC
    """

    _ANALYTICS_BY_REGIME = """
        SELECT
            CASE
                WHEN regime_mult <= 0.6  THEN 'bear'
                WHEN regime_mult <= 0.9  THEN 'caution'
                WHEN regime_mult <= 1.1  THEN 'neutral'
                WHEN regime_mult <= 1.35 THEN 'bull'
                ELSE 'strong_bull'
            END AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY label
        ORDER BY avg_net_pnl DESC
    """

    _ANALYTICS_BY_HOUR = """
        SELECT
            EXTRACT(HOUR FROM entry_time AT TIME ZONE 'America/New_York')::int::text AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY label
        ORDER BY label::int
    """

    _ANALYTICS_BY_SCORE_BUCKET = """
        SELECT
            TO_CHAR(FLOOR(ss.score * 10) * 0.1::numeric, 'FM0.0') || '–' ||
            TO_CHAR((FLOOR(ss.score * 10) * 0.1::numeric + 0.1), 'FM0.0') AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN t.net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(t.net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(t.net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades t
        JOIN sentiment_signals ss ON ss.id = t.signal_id
        WHERE t.exit_time IS NOT NULL
          AND t.exit_time >= now() - (%s || ' days')::interval
          AND t.signal_id IS NOT NULL
        GROUP BY FLOOR(ss.score * 10)
        ORDER BY FLOOR(ss.score * 10)
    """

    _ANALYTICS_BY_HOLD_TIME = """
        SELECT
            CASE
                WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 3600
                    THEN '<1h'
                WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 14400
                    THEN '1-4h'
                WHEN EXTRACT(EPOCH FROM (exit_time - entry_time)) < 28800
                    THEN '4-8h'
                WHEN DATE(exit_time AT TIME ZONE 'America/New_York')
                   > DATE(entry_time AT TIME ZONE 'America/New_York')
                    THEN 'overnight'
                ELSE 'extended'
            END AS label,
            COUNT(*) AS trade_count,
            ROUND(
                COALESCE(
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)::numeric
                    / NULLIF(COUNT(*)::numeric, 0), 0
                ), 4
            ) AS win_rate,
            ROUND(COALESCE(AVG(net_pnl), 0)::numeric, 2) AS avg_net_pnl,
            ROUND(COALESCE(SUM(net_pnl), 0)::numeric, 2) AS total_net_pnl
        FROM trades
        WHERE exit_time IS NOT NULL
          AND exit_time >= now() - (%s || ' days')::interval
        GROUP BY label
        ORDER BY avg_net_pnl DESC
    """

    def _fetch_analytics(self, sql: str, limit_days: int) -> list[dict]:
        """Shared executor for all analytics queries."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (str(limit_days),))
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            conn.rollback()
            raise

    def fetch_analytics_by_symbol(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by symbol."""
        return self._fetch_analytics(self._ANALYTICS_BY_SYMBOL, limit_days)

    def fetch_analytics_by_regime(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by regime multiplier bucket."""
        return self._fetch_analytics(self._ANALYTICS_BY_REGIME, limit_days)

    def fetch_analytics_by_hour(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by hour of day (EST, 9–16)."""
        return self._fetch_analytics(self._ANALYTICS_BY_HOUR, limit_days)

    def fetch_analytics_by_score_bucket(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by 0.1-wide LLM score bins."""
        return self._fetch_analytics(self._ANALYTICS_BY_SCORE_BUCKET, limit_days)

    def fetch_analytics_by_hold_time(self, limit_days: int = 90) -> list[dict]:
        """Return P&L metrics grouped by hold duration bucket."""
        return self._fetch_analytics(self._ANALYTICS_BY_HOLD_TIME, limit_days)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_pg_store.py::TestFetchAnalyticsBySymbol tests/test_pg_store.py::TestFetchAnalyticsByDimension -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat(analytics): add five analytics fetch methods to pg_store"
```

---

## Task 3: `fetch_trade_with_signal` and `write_postmortem` in `pg_store.py`

**Files:**
- Modify: `src/store/pg_store.py`
- Test: `tests/test_pg_store.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_pg_store.py`:

```python
class TestFetchTradeWithSignal:
    def test_returns_dict_with_signal_fields(self):
        from datetime import datetime, timezone
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        now = datetime(2026, 6, 5, 15, tzinfo=timezone.utc)
        mock_cur.description = [
            ("id",), ("symbol",), ("entry_time",), ("exit_time",),
            ("entry_price",), ("exit_price",), ("net_pnl",),
            ("score",), ("regime_mult",), ("exit_reason",),
            ("confidence",), ("ensemble_std",), ("signal_generated_at",),
            ("postmortem_diagnosis",),
        ]
        mock_cur.fetchone.return_value = (
            7, "NVDA", now, now, 200.0, 195.0, -5.0,
            0.45, 1.0, "stop_loss",
            0.6, 0.1, now, None,
        )

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.fetch_trade_with_signal(trade_id=7)
        assert result is not None
        assert result["symbol"] == "NVDA"
        assert result["confidence"] == 0.6
        assert result["postmortem_diagnosis"] is None

    def test_returns_none_when_not_found(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        result = store.fetch_trade_with_signal(trade_id=999)
        assert result is None


class TestWritePostmortem:
    def test_issues_update_with_diagnosis(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        store.write_postmortem(trade_id=7, diagnosis="low_confidence_passed")

        sql = mock_cur.execute.call_args[0][0]
        params = mock_cur.execute.call_args[0][1]
        assert "UPDATE trades" in sql
        assert "postmortem_diagnosis" in sql
        assert params[0] == "low_confidence_passed"
        assert params[1] == 7
        mock_conn.commit.assert_called_once()

    def test_rollback_on_error(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.execute.side_effect = Exception("DB error")

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception):
            store.write_postmortem(trade_id=7, diagnosis="unknown")
        mock_conn.rollback.assert_called_once()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_pg_store.py::TestFetchTradeWithSignal tests/test_pg_store.py::TestWritePostmortem -v
```

Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Add `fetch_trade_with_signal` and `write_postmortem` to `src/store/pg_store.py`**

Insert after `fetch_analytics_by_hold_time` (still before `log_weight_update`):

```python
    _FETCH_TRADE_WITH_SIGNAL = """
        SELECT
            t.id, t.symbol, t.entry_time, t.exit_time,
            t.entry_price, t.exit_price, t.net_pnl,
            t.score, t.regime_mult, t.exit_reason,
            ss.confidence, ss.ensemble_std,
            ss.generated_at AS signal_generated_at,
            t.postmortem_diagnosis
        FROM trades t
        LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
        WHERE t.id = %s
    """

    def fetch_trade_with_signal(self, trade_id: int) -> dict | None:
        """Return a trade row joined with its signal's confidence/ensemble_std."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(self._FETCH_TRADE_WITH_SIGNAL, (trade_id,))
                row = cur.fetchone()
                if row is None:
                    return None
                cols = [d[0] for d in cur.description]
                return dict(zip(cols, row))
        except Exception:
            conn.rollback()
            raise

    def write_postmortem(self, trade_id: int, diagnosis: str) -> None:
        """Store postmortem diagnosis for a closed trade."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE trades SET postmortem_diagnosis = %s WHERE id = %s",
                    (diagnosis, trade_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_pg_store.py::TestFetchTradeWithSignal tests/test_pg_store.py::TestWritePostmortem -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat(analytics): add fetch_trade_with_signal and write_postmortem to pg_store"
```

---

## Task 4: Wire postmortem in `execution.py`

**Files:**
- Modify: `src/workers/execution.py`
- Create: `tests/workers/test_execution_postmortem.py`

- [ ] **Step 1: Write failing test**

Create `tests/workers/test_execution_postmortem.py`:

```python
"""Tests for postmortem wiring in the execution worker."""
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


def _make_signal(score=0.45, confidence=0.55, ensemble_std=0.05,
                 generated_at="2026-06-05T14:00:00+00:00"):
    return {
        "score": score,
        "confidence": confidence,
        "ensemble_std": ensemble_std,
        "fallback_used": False,
        "generated_at": generated_at,
        "signal_id": 7,
    }


class TestMaybePostmortem:
    """_maybe_postmortem writes diagnosis when loss exceeds trigger threshold."""

    def test_writes_diagnosis_on_qualifying_loss(self):
        from src.workers.execution import _maybe_postmortem

        mock_pg = MagicMock()
        signal = _make_signal(score=0.55, confidence=0.35, ensemble_std=0.05)

        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=7,
            signal=signal,
            score=0.55,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=96.0,   # 4% loss — triggers postmortem
            tick_time=datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc),
        )

        mock_pg.write_postmortem.assert_called_once()
        call_args = mock_pg.write_postmortem.call_args[0]
        assert call_args[0] == 7                    # trade_id
        assert isinstance(call_args[1], str)        # diagnosis string

    def test_skips_diagnosis_on_small_loss(self):
        from src.workers.execution import _maybe_postmortem

        mock_pg = MagicMock()
        signal = _make_signal(score=0.45, confidence=0.6, ensemble_std=0.05)

        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=8,
            signal=signal,
            score=0.45,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=99.5,  # 0.5% loss — below all thresholds
            tick_time=datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc),
        )

        mock_pg.write_postmortem.assert_not_called()

    def test_handles_write_postmortem_exception_silently(self):
        from src.workers.execution import _maybe_postmortem

        mock_pg = MagicMock()
        mock_pg.write_postmortem.side_effect = Exception("DB error")
        signal = _make_signal(score=0.55, confidence=0.35)

        # Must not raise
        _maybe_postmortem(
            pg_store=mock_pg,
            trade_id=9,
            signal=signal,
            score=0.55,
            regime_mult=1.0,
            entry_price=100.0,
            exit_price=96.0,
            tick_time=datetime(2026, 6, 5, 15, 30, tzinfo=timezone.utc),
        )


class TestRegimeLabel:
    def test_regime_label_mapping(self):
        from src.workers.execution import _regime_label
        assert _regime_label(0.5) == "risk_off"
        assert _regime_label(0.75) == "uncertain"
        assert _regime_label(1.0) == "risk_on"
        assert _regime_label(1.2) == "risk_on"
        assert _regime_label(1.5) == "risk_on"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/workers/test_execution_postmortem.py -v
```

Expected: FAIL — `ImportError: cannot import name '_maybe_postmortem'`.

- [ ] **Step 3: Add imports to `src/workers/execution.py`**

Add near the top of the file (after existing imports, before the `app = ...` line):

```python
from src.performance.postmortem import TradeContext, diagnose_loss, should_trigger_postmortem
```

- [ ] **Step 4: Add `_regime_label` and `_maybe_postmortem` helpers to `src/workers/execution.py`**

Insert after the existing `_write_decision` helper (search for `def _write_decision`):

```python
def _regime_label(regime_mult: float) -> str:
    """Convert a numeric regime multiplier to the string label expected by TradeContext."""
    if regime_mult <= 0.6:
        return "risk_off"
    if regime_mult <= 0.9:
        return "uncertain"
    return "risk_on"


def _maybe_postmortem(
    pg_store,
    trade_id: int,
    signal: dict,
    score: float,
    regime_mult: float,
    entry_price: float,
    exit_price: float,
    tick_time,
) -> None:
    """Run postmortem diagnosis on a losing trade and persist the result.

    Silently skips if the loss is below the trigger thresholds to avoid
    writing a diagnosis for every tiny dip.
    """
    loss_pct = (entry_price - exit_price) / entry_price if entry_price > 0 else 0.0
    confidence = float(signal.get("confidence", 0.5))
    ensemble_std = float(signal.get("ensemble_std", 0.0))

    if not should_trigger_postmortem(loss_pct, score, ensemble_std):
        return

    signal_age_min = 0.0
    generated_at = signal.get("generated_at")
    if generated_at:
        try:
            from datetime import timezone as _tz
            sig_dt = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
            if sig_dt.tzinfo is None:
                sig_dt = sig_dt.replace(tzinfo=_tz.utc)
            signal_age_min = (tick_time - sig_dt).total_seconds() / 60
        except Exception:
            pass

    ctx = TradeContext(
        loss_pct=loss_pct,
        signal_score=score,
        signal_confidence=confidence,
        ensemble_std=ensemble_std,
        regime=_regime_label(regime_mult),
        reasoning_summary="",
        signal_age_minutes=signal_age_min,
    )
    diagnosis = diagnose_loss(ctx)
    try:
        pg_store.write_postmortem(trade_id, diagnosis)
    except Exception as pm_exc:
        log.warning("Failed to write postmortem for trade %s: %s", trade_id, pm_exc)
```

- [ ] **Step 5: Wire `_maybe_postmortem` after the stop-loss `close_trade` call in `run_execution_cycle`**

Find the stop-loss section in `src/workers/execution.py` (around line 330). Replace the `pg_store.close_trade(...)` call block with:

```python
                        trade_id: "int | None" = None
                        if pg_store is not None:
                            try:
                                trade_id = pg_store.close_trade(
                                    symbol=symbol,
                                    exit_price=current_price,
                                    exit_time=tick_time,
                                    exit_reason="stop_loss",
                                    entry_price=entry_price,
                                )
                            except Exception as trade_exc:
                                log.warning("Failed to close trade record for %s: %s", symbol, trade_exc)

                        if trade_id is not None and pg_store is not None:
                            _maybe_postmortem(
                                pg_store=pg_store,
                                trade_id=trade_id,
                                signal=signal,
                                score=score,
                                regime_mult=regime_mult,
                                entry_price=entry_price,
                                exit_price=current_price,
                                tick_time=tick_time,
                            )
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
pytest tests/workers/test_execution_postmortem.py -v
```

Expected: all PASS.

- [ ] **Step 7: Run full test suite to check no regressions**

```bash
pytest tests/ -x -q 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/workers/execution.py tests/workers/test_execution_postmortem.py
git commit -m "feat(analytics): wire postmortem diagnosis after stop-loss close in execution worker"
```

---

## Task 5: New API routes for analytics and postmortem

**Files:**
- Modify: `src/api/routes/trading.py`
- Test: `tests/api/test_trading_routes.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/api/test_trading_routes.py`:

```python
from src.api.deps import get_pg_store


class TestAnalyticsRoutes:
    def setup_method(self):
        app.dependency_overrides[require_api_key] = lambda: "test-key"

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_get_analytics_by_symbol(self):
        mock_pg = MagicMock()
        mock_pg.fetch_analytics_by_symbol.return_value = [
            {"label": "NVDA", "trade_count": 3, "win_rate": 0.67,
             "avg_net_pnl": 12.5, "total_net_pnl": 37.5}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/analytics/by-symbol?days=90")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["label"] == "NVDA"

    def test_get_analytics_by_dimension_regime(self):
        mock_pg = MagicMock()
        mock_pg.fetch_analytics_by_regime.return_value = [
            {"label": "neutral", "trade_count": 2, "win_rate": 0.5,
             "avg_net_pnl": 5.0, "total_net_pnl": 10.0}
        ]
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/analytics/by-dimension?dim=regime")
        assert resp.status_code == 200
        assert resp.json()[0]["label"] == "neutral"

    def test_get_analytics_by_dimension_invalid_dim(self):
        app.dependency_overrides[get_pg_store] = lambda: MagicMock()

        tc = TestClient(app)
        resp = tc.get("/api/trades/analytics/by-dimension?dim=unknown")
        assert resp.status_code == 422

    def test_get_postmortem_returns_trade_dict(self):
        from datetime import datetime, timezone
        now = datetime(2026, 6, 5, 15, tzinfo=timezone.utc)
        mock_pg = MagicMock()
        mock_pg.fetch_trade_with_signal.return_value = {
            "id": 7, "symbol": "NVDA", "net_pnl": -5.0,
            "postmortem_diagnosis": "low_confidence_passed",
            "entry_time": now, "exit_time": now,
        }
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/postmortem/7")
        assert resp.status_code == 200
        assert resp.json()["postmortem_diagnosis"] == "low_confidence_passed"

    def test_get_postmortem_404_when_not_found(self):
        mock_pg = MagicMock()
        mock_pg.fetch_trade_with_signal.return_value = None
        app.dependency_overrides[get_pg_store] = lambda: mock_pg

        tc = TestClient(app)
        resp = tc.get("/api/trades/postmortem/999")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/api/test_trading_routes.py::TestAnalyticsRoutes -v
```

Expected: FAIL — 404 for all analytics routes (routes don't exist yet).

- [ ] **Step 3: Add routes to `src/api/routes/trading.py`**

Add these imports at the top if not already present:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

Append to the router (after the existing `get_decisions` endpoint):

```python
@router.get("/trades/analytics/by-symbol")
def get_analytics_by_symbol(
    pg: Annotated[object, Depends(get_pg_store)],
    days: int = Query(default=90, ge=1, le=365),
) -> list[dict]:
    """P&L metrics grouped by symbol."""
    return pg.fetch_analytics_by_symbol(limit_days=days)


@router.get("/trades/analytics/by-dimension")
def get_analytics_by_dimension(
    pg: Annotated[object, Depends(get_pg_store)],
    dim: str = Query(pattern="^(regime|hour|score|holdtime)$"),
    days: int = Query(default=90, ge=1, le=365),
) -> list[dict]:
    """P&L metrics grouped by the requested dimension."""
    dispatch = {
        "regime":   pg.fetch_analytics_by_regime,
        "hour":     pg.fetch_analytics_by_hour,
        "score":    pg.fetch_analytics_by_score_bucket,
        "holdtime": pg.fetch_analytics_by_hold_time,
    }
    return dispatch[dim](limit_days=days)


@router.get("/trades/postmortem/{trade_id}")
def get_postmortem(
    trade_id: int,
    pg: Annotated[object, Depends(get_pg_store)],
) -> dict:
    """Return trade detail with postmortem_diagnosis (or null if not computed)."""
    row = pg.fetch_trade_with_signal(trade_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if row.get("entry_time") is not None:
        row["entry_time"] = row["entry_time"].isoformat() if hasattr(row["entry_time"], "isoformat") else row["entry_time"]
    if row.get("exit_time") is not None:
        row["exit_time"] = row["exit_time"].isoformat() if hasattr(row["exit_time"], "isoformat") else row["exit_time"]
    if row.get("signal_generated_at") is not None:
        row["signal_generated_at"] = row["signal_generated_at"].isoformat() if hasattr(row["signal_generated_at"], "isoformat") else row["signal_generated_at"]
    return row
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/api/test_trading_routes.py::TestAnalyticsRoutes -v
```

Expected: all PASS.

- [ ] **Step 5: Run full API test suite**

```bash
pytest tests/api/ -v -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/trading.py tests/api/test_trading_routes.py
git commit -m "feat(analytics): add analytics and postmortem API endpoints"
```

---

## Task 6: Frontend analytics API client

**Files:**
- Create: `frontend/src/api/analytics.ts`

- [ ] **Step 1: Create `frontend/src/api/analytics.ts`**

```typescript
import { apiFetch } from './client'

export interface DimensionRow {
  label: string
  trade_count: number
  win_rate: number
  avg_net_pnl: number
  total_net_pnl: number
}

export type AnalyticsDim = 'regime' | 'hour' | 'score' | 'holdtime'

export const fetchAnalyticsBySymbol = (days = 90) =>
  apiFetch<DimensionRow[]>(`/api/trades/analytics/by-symbol?days=${days}`)

export const fetchAnalyticsByDimension = (dim: AnalyticsDim, days = 90) =>
  apiFetch<DimensionRow[]>(`/api/trades/analytics/by-dimension?dim=${dim}&days=${days}`)
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/stefano/Documents/Projects/Alembic/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/analytics.ts
git commit -m "feat(analytics): add analytics API client (frontend)"
```

---

## Task 7: Analytics tab in `Trades.tsx` + postmortem badge

**Files:**
- Modify: `frontend/src/pages/Trades.tsx`

- [ ] **Step 1: Replace `frontend/src/pages/Trades.tsx` with the version that includes an Analytics tab**

The new file adds:
1. A `view` state (`'trades' | 'analytics'`) and tab buttons at the top
2. An `AnalyticsPanel` sub-component that renders 5 `recharts` charts
3. A postmortem badge in the row expand panel

```tsx
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, Cell,
  XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer,
} from 'recharts'
import { fetchTrades, fetchTradesSummary, type Trade, type TradeStatus, type SummaryPeriod } from '@/api/trades'
import { fetchAnalyticsBySymbol, fetchAnalyticsByDimension, type DimensionRow } from '@/api/analytics'

const PERIODS: SummaryPeriod[] = [7, 30, 90]

function fmt(v: number | null, prefix = '$') {
  if (v == null) return '—'
  return `${prefix}${v.toFixed(2)}`
}

function fmtPct(v: number | null) {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function holdLabel(mins: number | null) {
  if (mins == null) return '—'
  if (mins < 60) return `${Math.round(mins)}m`
  return `${(mins / 60).toFixed(1)}h`
}

const card = (label: string, value: string, color?: string) => (
  <div style={{ background: '#1e293b', borderRadius: 8, padding: '14px 16px' }}>
    <div style={{ fontSize: 12, color: '#64748b', marginBottom: 4 }}>{label}</div>
    <div style={{ fontSize: 20, fontWeight: 700, color: color ?? 'white' }}>{value}</div>
  </div>
)

function AnalyticsChart({ title, data, dataKey = 'avg_net_pnl', colorBySign = true }: {
  title: string
  data: DimensionRow[]
  dataKey?: keyof DimensionRow
  colorBySign?: boolean
}) {
  if (!data.length) {
    return (
      <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>{title}</div>
        <div style={{ color: '#64748b', fontSize: 13 }}>No data yet</div>
      </div>
    )
  }
  return (
    <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{title}</div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
          <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, String(dataKey)]} />
          <Bar dataKey={String(dataKey)}>
            {data.map((row, i) => (
              <Cell
                key={i}
                fill={!colorBySign || Number(row[dataKey]) >= 0 ? '#22c55e' : '#ef4444'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function AnalyticsPanel({ days }: { days: number }) {
  const { data: bySymbol = [] } = useQuery({
    queryKey: ['analytics-symbol', days],
    queryFn: () => fetchAnalyticsBySymbol(days),
    refetchInterval: 300000,
  })
  const { data: byRegime = [] } = useQuery({
    queryKey: ['analytics-regime', days],
    queryFn: () => fetchAnalyticsByDimension('regime', days),
    refetchInterval: 300000,
  })
  const { data: byHour = [] } = useQuery({
    queryKey: ['analytics-hour', days],
    queryFn: () => fetchAnalyticsByDimension('hour', days),
    refetchInterval: 300000,
  })
  const { data: byScore = [] } = useQuery({
    queryKey: ['analytics-score', days],
    queryFn: () => fetchAnalyticsByDimension('score', days),
    refetchInterval: 300000,
  })
  const { data: byHold = [] } = useQuery({
    queryKey: ['analytics-hold', days],
    queryFn: () => fetchAnalyticsByDimension('holdtime', days),
    refetchInterval: 300000,
  })

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <AnalyticsChart title="Net P&L by Symbol" data={bySymbol} dataKey="total_net_pnl" />
      <AnalyticsChart title="Avg Net P&L by Regime" data={byRegime} />
      <AnalyticsChart title="Avg Net P&L by Hour (EST)" data={byHour} />
      <AnalyticsChart title="Avg Net P&L by LLM Score Bucket" data={byScore} />
      <AnalyticsChart title="Avg Net P&L by Hold Duration" data={byHold} />
    </div>
  )
}

export default function Trades() {
  const [period, setPeriod] = useState<SummaryPeriod>(7)
  const [view, setView] = useState<'trades' | 'analytics'>('trades')
  const [statusFilter, setStatusFilter] = useState<TradeStatus>('all')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: summary } = useQuery({
    queryKey: ['trades-summary', period],
    queryFn: () => fetchTradesSummary(period),
    refetchInterval: 120000,
  })

  const { data: trades = [], isLoading } = useQuery({
    queryKey: ['trades', statusFilter, period],
    queryFn: () => fetchTrades(undefined, statusFilter, 200),
    refetchInterval: 120000,
  })

  const filtered = useMemo(() =>
    (trades as Trade[]).filter((t: Trade) =>
      !symbolFilter || t.symbol.toLowerCase().includes(symbolFilter.toLowerCase())
    ), [trades, symbolFilter])

  const cumulativeData = useMemo(() => {
    const closed = filtered
      .filter(t => t.exit_time && t.net_pnl != null)
      .sort((a, b) => (a.exit_time! > b.exit_time! ? 1 : -1))
    let cum = 0
    return closed.map(t => {
      cum += t.net_pnl!
      return { date: t.exit_time!.slice(0, 10), cumulative: parseFloat(cum.toFixed(2)) }
    })
  }, [filtered])

  const lineColor = (cumulativeData.at(-1)?.cumulative ?? 0) >= 0 ? '#22c55e' : '#ef4444'
  const totalNetPnl = summary?.total_net_pnl ?? 0

  const tabBtn = (label: string, v: 'trades' | 'analytics') => (
    <button
      key={v}
      onClick={() => setView(v)}
      style={{
        padding: '6px 16px', borderRadius: 6, border: 'none', cursor: 'pointer',
        background: view === v ? '#3b82f6' : '#334155',
        color: 'white', fontSize: 13, fontWeight: view === v ? 600 : 400,
      }}
    >{label}</button>
  )

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Trades</h2>

      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {PERIODS.map(p => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            style={{
              padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
              background: period === p ? '#3b82f6' : '#334155',
              color: 'white', fontSize: 13,
            }}
          >{p}d</button>
        ))}
        <div style={{ flex: 1 }} />
        {tabBtn('Trades', 'trades')}
        {tabBtn('Analytics', 'analytics')}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {card('Total Trades', String(summary?.total_trades ?? '—'))}
        {card('Win Rate', fmtPct(summary?.win_rate ?? null))}
        {card('Avg Net P&L', fmt(summary?.avg_net_pnl ?? null))}
        {card('Total Net P&L', fmt(totalNetPnl), totalNetPnl >= 0 ? '#22c55e' : '#ef4444')}
      </div>

      {view === 'analytics' ? (
        <AnalyticsPanel days={period} />
      ) : (
        <>
          {cumulativeData.length > 0 && (
            <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, marginBottom: 24 }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Cumulative Net P&L</div>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={cumulativeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                  <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, 'Cumulative']} />
                  <Line type="monotone" dataKey="cumulative" stroke={lineColor} dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              value={symbolFilter}
              onChange={e => setSymbolFilter(e.target.value)}
              placeholder="Filter symbol…"
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: 'white', fontSize: 13, width: 140 }}
            />
            {(['all', 'open', 'closed'] as TradeStatus[]).map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                style={{
                  padding: '4px 12px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  background: statusFilter === s ? '#3b82f6' : '#334155',
                  color: 'white', fontSize: 13, textTransform: 'capitalize',
                }}
              >{s}</button>
            ))}
          </div>

          {isLoading ? (
            <div style={{ color: '#64748b', padding: 20 }}>Loading…</div>
          ) : (
            <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
              <div style={{
                display: 'grid',
                gridTemplateColumns: '8% 10% 10% 7% 7% 9% 9% 7% 9% 12% 12%',
                padding: '8px 12px', background: '#0f172a',
                fontSize: 11, color: '#64748b', fontWeight: 600, textTransform: 'uppercase',
              }}>
                {['Symbol', 'Entry', 'Exit', 'Score', 'Regime', 'Entry $', 'Exit $', 'Hold', 'Net P&L', 'Exit Reason', 'Decision'].map(h => (
                  <span key={h}>{h}</span>
                ))}
              </div>
              {filtered.map((t: Trade) => (
                <div key={t.id}>
                  <div
                    onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '8% 10% 10% 7% 7% 9% 9% 7% 9% 12% 12%',
                      padding: '8px 12px', fontSize: 13, cursor: 'pointer',
                      borderTop: '1px solid #0f172a',
                      background: expandedId === t.id ? '#0f172a' : 'transparent',
                    }}
                  >
                    <span style={{ fontWeight: 600 }}>{t.symbol}</span>
                    <span style={{ color: '#94a3b8' }}>{t.entry_time.slice(0, 10)}</span>
                    <span style={{ color: '#94a3b8' }}>{t.exit_time?.slice(0, 10) ?? '—'}</span>
                    <span>{t.score.toFixed(2)}</span>
                    <span>{t.regime_mult.toFixed(2)}×</span>
                    <span>{fmt(t.entry_price)}</span>
                    <span>{fmt(t.exit_price)}</span>
                    <span>{holdLabel(t.exit_time ? ((new Date(t.exit_time).getTime() - new Date(t.entry_time).getTime()) / 60000) : null)}</span>
                    <span style={{ color: (t.net_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                      {fmt(t.net_pnl)}
                    </span>
                    <span style={{ color: '#94a3b8', fontSize: 12 }}>{t.exit_reason ?? '—'}</span>
                    <span style={{ color: '#94a3b8', fontSize: 12 }}>ID {t.decision_id ?? '—'}</span>
                  </div>
                  {expandedId === t.id && (
                    <div style={{ padding: '8px 12px 12px', background: '#0f172a', fontSize: 12, color: '#94a3b8' }}>
                      <span>signal_id: {t.signal_id ?? '—'}</span>
                      {' | '}
                      <span>order: {t.entry_order_id}</span>
                      {' | '}
                      <span>notional: {fmt(t.entry_notional)}</span>
                      {' | '}
                      <span>slippage est: {fmt(t.slippage_est)}</span>
                      {' | '}
                      <span>gross P&L: {fmt(t.gross_pnl)}</span>
                      {t.postmortem_diagnosis && (
                        <>
                          {' | '}
                          <span style={{
                            display: 'inline-block',
                            background: '#78350f',
                            color: '#fbbf24',
                            borderRadius: 4,
                            padding: '1px 6px',
                            fontSize: 11,
                            fontWeight: 600,
                          }}>
                            ⚠ {t.postmortem_diagnosis}
                          </span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {filtered.length === 0 && (
                <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>No trades found.</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles without errors**

```bash
cd /home/stefano/Documents/Projects/Alembic/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 3: Run full Python test suite one final time**

```bash
cd /home/stefano/Documents/Projects/Alembic && pytest tests/ -x -q 2>&1 | tail -10
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Trades.tsx
git commit -m "feat(analytics): add Analytics tab with 5 charts and postmortem badge to Trades page"
```

---

## Self-Review

**Spec coverage:**
- ✅ Five analytics dimensions (by-symbol, regime, hour, score bucket, hold time)
- ✅ `postmortem.py` wired to execution cycle on trade close
- ✅ `postmortem_diagnosis` column (migration 017)
- ✅ `close_trade()` returns id (needed by postmortem wiring)
- ✅ Three API endpoints (by-symbol, by-dimension, postmortem/{id})
- ✅ Analytics tab on Trades page with 5 charts
- ✅ Postmortem badge in expanded row
- ✅ `fetch_trade_with_signal` for postmortem endpoint
- ✅ `write_postmortem` for storing diagnosis
- ✅ `should_trigger_postmortem` gate — small losses don't get a diagnosis

**Type consistency:**
- `fetch_analytics_by_*` all return `list[dict]` with keys `label, trade_count, win_rate, avg_net_pnl, total_net_pnl` — matches `DimensionRow` interface
- `close_trade()` return type `int | None` — matches usage in Task 4
- `_maybe_postmortem` signature matches its callers
- `TradeContext` fields — matches existing `postmortem.py` dataclass

**No placeholders:** All steps contain complete code.
