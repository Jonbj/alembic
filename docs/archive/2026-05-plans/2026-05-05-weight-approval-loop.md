# Weight Approval Feedback Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the weight-update feedback loop: add `GET /api/weights/suggestion`, redesign `POST /api/weights/approve` to read from Redis and audit to PostgreSQL, and add a daily Celery task that logs expired suggestions.

**Architecture:** The weekly `run_weekly_weights()` task already stores a validated suggestion in Redis (`ensemble:weights:suggestion`, TTL 7 days). This plan adds the approval path: a new GET endpoint exposes the suggestion, the redesigned POST endpoint applies it (or an override) and logs every action to a new `weight_update_log` table. A daily Celery task catches suggestions that expire without being approved. FastAPI dependency injection is refactored so all three endpoints are independently testable.

**Tech Stack:** FastAPI, psycopg2, Redis (redis-py), Celery, pytest + httpx AsyncClient, hashlib

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `migrations/002_add_weight_update_log.sql` | Create | New audit table |
| `src/store/pg_store.py` | Modify | Add `log_weight_update()` |
| `src/store/redis_store.py` | Modify | Add `get_weight_suggestion()` |
| `src/api/deps.py` | Create | Shared FastAPI dependency factories (avoids circular import) |
| `src/api/main.py` | Modify | Wire lifespan → deps, re-export for backward compat |
| `src/api/routes/performance.py` | Rewrite | Use Depends, add GET/POST endpoints, fix wrong model IDs |
| `src/workers/performance.py` | Modify | Store snapshot key, add `check_suggestion_expiry` task |
| `src/workers/celery_app.py` | Modify | Add daily schedule for expiry task |
| `tests/api/test_weight_approval.py` | Create | All new endpoint tests |

---

## Task 1: SQL Migration — weight_update_log

**Files:**
- Create: `migrations/002_add_weight_update_log.sql`

- [ ] **Step 1: Write the migration**

Create `migrations/002_add_weight_update_log.sql`:

```sql
-- Migration 002: Weight update audit trail for Fase 2 approval loop
-- Created: 2026-05-05

CREATE TABLE IF NOT EXISTS weight_update_log (
    id                SERIAL PRIMARY KEY,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            VARCHAR(20) NOT NULL
                          CHECK (source IN ('suggestion', 'override', 'expired')),
    applied_weights   JSONB NOT NULL,
    suggested_weights JSONB,
    purified_icir     JSONB,
    freeze_reason     TEXT,
    note              TEXT,
    approved_by       TEXT    -- SHA-256[:8] of the API key, never raw
);

CREATE INDEX IF NOT EXISTS idx_weight_log_applied_at
    ON weight_update_log (applied_at DESC);
```

- [ ] **Step 2: Verify SQL syntax**

Run: `psql $DATABASE_URL -f migrations/002_add_weight_update_log.sql`

Expected: No errors. If DATABASE_URL is not set locally, skip and rely on Step 3 instead.

- [ ] **Step 3: Sanity-check the schema**

Run: `psql $DATABASE_URL -c "\d weight_update_log"`

Expected: 9 columns — `id`, `applied_at`, `source`, `applied_weights`, `suggested_weights`, `purified_icir`, `freeze_reason`, `note`, `approved_by`.

- [ ] **Step 4: Commit**

```bash
git add migrations/002_add_weight_update_log.sql
git commit -m "feat: add weight_update_log migration for audit trail"
```

---

## Task 2: PostgreSQLStore.log_weight_update()

**Files:**
- Modify: `src/store/pg_store.py` (add import + class constant + method)
- Modify: `tests/test_pg_store.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pg_store.py`:

```python
class TestLogWeightUpdate:
    """Test PostgreSQLStore.log_weight_update()."""

    def test_log_weight_update_returns_id(self):
        """log_weight_update executes INSERT RETURNING id and returns it."""
        import json
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (7,)
        mock_conn.cursor.return_value = mock_cursor

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        log_id = store.log_weight_update(
            source="suggestion",
            applied_weights={"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            suggested_weights={"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            purified_icir={"opus": 0.31, "qwen3.5:cloud": 0.18, "deepseek-v4-pro:cloud": 0.09},
            freeze_reason=None,
            note="test",
            approved_by="abcd1234",
        )

        assert log_id == 7
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args[0]
        # First arg is the SQL — must contain INSERT INTO weight_update_log
        assert "INSERT INTO weight_update_log" in call_args[0]
        # Second arg is the parameters tuple — source must be first
        assert call_args[1][0] == "suggestion"
        mock_conn.commit.assert_called_once()

    def test_log_weight_update_rollback_on_error(self):
        """log_weight_update rolls back on exception."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = Exception("DB error")
        mock_conn.cursor.return_value = mock_cursor

        store = PostgreSQLStore(conn=mock_conn, use_pool=False)
        with pytest.raises(Exception, match="DB error"):
            store.log_weight_update(
                source="suggestion",
                applied_weights={"opus": 1.0},
            )

        mock_conn.rollback.assert_called_once()
```

Also add `from unittest.mock import MagicMock` to the imports at the top of `tests/test_pg_store.py` (check if already present first).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pg_store.py::TestLogWeightUpdate -v`

Expected: FAIL with `AttributeError: type object 'PostgreSQLStore' has no attribute 'log_weight_update'`

- [ ] **Step 3: Add `import json` and the method to pg_store.py**

Add `import json` to the top of `src/store/pg_store.py` (after the existing imports).

Add the class constant and method to `PostgreSQLStore` (after the `_INSERT_SIGNAL` constant):

```python
_INSERT_WEIGHT_LOG = """
    INSERT INTO weight_update_log (
        source, applied_weights, suggested_weights,
        purified_icir, freeze_reason, note, approved_by
    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id
"""

def log_weight_update(
    self,
    source: str,
    applied_weights: dict,
    suggested_weights: dict | None = None,
    purified_icir: dict | None = None,
    freeze_reason: str | None = None,
    note: str | None = None,
    approved_by: str | None = None,
) -> int:
    """Write a row to weight_update_log and return the generated id."""
    conn = self._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                self._INSERT_WEIGHT_LOG,
                (
                    source,
                    json.dumps(applied_weights),
                    json.dumps(suggested_weights) if suggested_weights is not None else None,
                    json.dumps(purified_icir) if purified_icir is not None else None,
                    freeze_reason,
                    note,
                    approved_by,
                ),
            )
            log_id: int = cur.fetchone()[0]
        conn.commit()
        return log_id
    except Exception:
        conn.rollback()
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pg_store.py::TestLogWeightUpdate -v`

Expected: PASS (2 tests)

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `pytest tests/test_pg_store.py -v`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/store/pg_store.py tests/test_pg_store.py
git commit -m "feat: add PostgreSQLStore.log_weight_update for weight audit trail"
```

---

## Task 3: RedisStore.get_weight_suggestion()

**Files:**
- Modify: `src/store/redis_store.py` (add method under ENSEMBLE WEIGHTS section)
- Modify: `tests/test_redis_store.py` (add test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_redis_store.py`:

```python
class TestGetWeightSuggestion:
    """Test RedisStore.get_weight_suggestion()."""

    def test_returns_dict_when_key_exists(self):
        import json
        payload = {"suggested_weights": {"opus": 0.45}, "freeze_reason": ""}
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(payload).encode()

        store = RedisStore(redis_client=mock_redis)
        result = store.get_weight_suggestion()

        assert result == payload
        mock_redis.get.assert_called_once_with("ensemble:weights:suggestion")

    def test_returns_none_when_key_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_weight_suggestion() is None

    def test_returns_none_on_corrupted_json(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not-valid-json"

        store = RedisStore(redis_client=mock_redis)
        assert store.get_weight_suggestion() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_redis_store.py::TestGetWeightSuggestion -v`

Expected: FAIL with `AttributeError: 'RedisStore' object has no attribute 'get_weight_suggestion'`

- [ ] **Step 3: Add the method to RedisStore**

Add under the `# ENSEMBLE WEIGHTS` section in `src/store/redis_store.py`, after `set_ensemble_weights`:

```python
def get_weight_suggestion(self) -> dict | None:
    """Get current weight suggestion from Redis. Returns None if absent or corrupted."""
    raw = self._r.get("ensemble:weights:suggestion")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_redis_store.py::TestGetWeightSuggestion -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Run full test suite for regressions**

Run: `pytest tests/test_redis_store.py -v`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/store/redis_store.py tests/test_redis_store.py
git commit -m "feat: add RedisStore.get_weight_suggestion"
```

---

## Task 4: deps.py + main.py Refactor

Performance routes cannot import from `src/api/main.py` (circular import: `main → routes → main`). This task creates `src/api/deps.py` as a shared dependency module, wires it into `main.py`, and refactors `performance.py` to use proper FastAPI `Depends()`.

**Files:**
- Create: `src/api/deps.py`
- Modify: `src/api/main.py`
- Modify: `src/api/routes/performance.py`

- [ ] **Step 1: Create `src/api/deps.py`**

```python
"""FastAPI dependency factories (shared by routes, avoids circular import with main.py)."""
from __future__ import annotations

from typing import Optional

from redis import Redis

_redis_client: Optional[Redis] = None


def get_redis_store():
    """FastAPI dependency: RedisStore backed by the app-lifecycle Redis client."""
    from src.store.redis_store import RedisStore
    if _redis_client is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Cache unavailable")
    return RedisStore(_redis_client)


def get_pg_store():
    """FastAPI dependency: PostgreSQLStore (new connection from pool per request)."""
    from src.store.pg_store import PostgreSQLStore
    return PostgreSQLStore()
```

- [ ] **Step 2: Update `src/api/main.py`**

Replace the existing file with:

```python
"""FastAPI application with lifespan for Redis connection management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from redis import Redis

from src.api import deps
from src.config import config

# Re-export dependency functions so existing tests can still do:
#   from src.api.main import app, get_redis_store, get_pg_store
from src.api.deps import get_pg_store, get_redis_store  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Open Redis connection on startup, close on shutdown."""
    deps._redis_client = Redis.from_url(config.REDIS_URL)
    yield
    deps._redis_client.close()
    deps._redis_client = None


app = FastAPI(
    title="LLM Trading Signal API",
    description="Control plane for LLM-based algorithmic trading system",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "backtest"}


from src.api.routes import admin, performance, signals  # noqa: E402

app.include_router(signals.router)
app.include_router(admin.router)
app.include_router(performance.router)
```

- [ ] **Step 3: Rewrite `src/api/routes/performance.py`**

Replace the entire file with:

```python
"""Performance and weights endpoints."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.api.deps import get_pg_store, get_redis_store
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api")

_WEIGHT_MIN = 0.10
_WEIGHT_MAX = 0.70


class ApproveWeightsRequest(BaseModel):
    override_weights: dict[str, float] | None = None
    note: str | None = None


def _validate_override_weights(weights: dict[str, float]) -> dict[str, float]:
    from src.config import config
    known = set(config.MODEL_COSTS.keys())
    for model_id, w in weights.items():
        if model_id not in known:
            raise HTTPException(status_code=422, detail=f"Unknown model: {model_id}")
        if w < _WEIGHT_MIN:
            raise HTTPException(
                status_code=422,
                detail=f"Weight for {model_id}={w} below floor {_WEIGHT_MIN}",
            )
        if w > _WEIGHT_MAX:
            raise HTTPException(
                status_code=422,
                detail=f"Weight for {model_id}={w} exceeds cap {_WEIGHT_MAX}",
            )
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise HTTPException(
            status_code=422, detail=f"Weights must sum to 1.0 (got {total:.4f})"
        )
    return weights


@router.get("/performance/latest")
async def get_latest_performance(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    raw = redis._r.get("performance:latest_report")
    if raw is None:
        raise HTTPException(status_code=404, detail="No performance report available yet")
    return json.loads(raw)


@router.get("/weights/current")
async def get_current_weights(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    raw = redis._r.get("ensemble:weights:current")
    if raw is None:
        return {
            "weights": {
                "opus": 0.34,
                "qwen3.5:cloud": 0.33,
                "deepseek-v4-pro:cloud": 0.33,
            },
            "source": "default",
        }
    return json.loads(raw)


@router.get("/weights/suggestion")
async def get_weight_suggestion(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No weight suggestion available")
    computed_at = datetime.fromisoformat(suggestion["computed_at"])
    suggestion["expires_at"] = (computed_at + timedelta(days=7)).isoformat()
    return suggestion


@router.post("/weights/approve")
async def approve_weights(
    body: ApproveWeightsRequest,
    api_key: Annotated[str, Depends(require_api_key)],
    redis: Annotated[RedisStore, Depends(get_redis_store)],
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> dict:
    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No weight suggestion available")

    if suggestion.get("freeze_reason") and body.override_weights is None:
        raise HTTPException(
            status_code=403,
            detail=f"Weight update frozen: {suggestion['freeze_reason']}",
        )

    if body.override_weights is not None:
        weights = _validate_override_weights(body.override_weights)
        source = "override"
    else:
        weights = suggestion["suggested_weights"]
        source = "suggestion"

    redis.set_ensemble_weights(weights, source=source)
    redis._r.delete("ensemble:weights:suggestion:snapshot")

    approved_by = hashlib.sha256(api_key.encode()).hexdigest()[:8]
    log_id = pg.log_weight_update(
        source=source,
        applied_weights=weights,
        suggested_weights=suggestion.get("suggested_weights"),
        purified_icir=suggestion.get("purified_icir"),
        freeze_reason=suggestion.get("freeze_reason") or None,
        note=body.note,
        approved_by=approved_by,
    )

    return {"applied_weights": weights, "source": source, "log_id": log_id}
```

- [ ] **Step 4: Run existing API tests to verify nothing is broken**

Run: `pytest tests/api/test_api.py -v`

Expected: All existing tests pass (the `get_redis_store` re-export from main.py makes this work).

- [ ] **Step 5: Commit**

```bash
git add src/api/deps.py src/api/main.py src/api/routes/performance.py
git commit -m "refactor: extract FastAPI deps to deps.py, wire performance routes to Depends"
```

---

## Task 5: Tests for the New Endpoints

**Files:**
- Create: `tests/api/test_weight_approval.py`

- [ ] **Step 1: Write all tests**

Create `tests/api/test_weight_approval.py`:

```python
"""Tests for GET /api/weights/suggestion and POST /api/weights/approve."""

import hashlib
import json
import os
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/test_db")

from src.api.main import app, get_pg_store, get_redis_store

API_KEY = "test-api-key-for-testing-only-12345678"

SAMPLE_SUGGESTION = {
    "suggested_weights": {
        "opus": 0.45,
        "qwen3.5:cloud": 0.35,
        "deepseek-v4-pro:cloud": 0.20,
    },
    "purified_icir": {
        "opus": 0.31,
        "qwen3.5:cloud": 0.18,
        "deepseek-v4-pro:cloud": 0.09,
    },
    "freeze_reason": "",
    "computed_at": "2026-05-04T08:00:00+00:00",
}


def make_redis_mock(suggestion=SAMPLE_SUGGESTION):
    store = MagicMock()
    store.get_weight_suggestion.return_value = suggestion
    store.set_ensemble_weights = MagicMock()
    store._r = MagicMock()
    return store


def make_pg_mock():
    store = MagicMock()
    store.log_weight_update.return_value = 42
    return store


@pytest.mark.asyncio
async def test_get_suggestion_ok():
    """GET /api/weights/suggestion returns 200 with payload + computed expires_at."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/weights/suggestion")
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested_weights"]["opus"] == pytest.approx(0.45)
    assert "expires_at" in data
    assert data["expires_at"].startswith("2026-05-11")


@pytest.mark.asyncio
async def test_get_suggestion_not_found():
    """GET /api/weights/suggestion returns 404 when Redis has no suggestion."""
    redis = make_redis_mock(suggestion=None)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/weights/suggestion")
    app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_from_suggestion():
    """POST /approve with empty body applies suggestion, source='suggestion', returns log_id."""
    redis = make_redis_mock()
    pg = make_pg_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    app.dependency_overrides[get_pg_store] = lambda: pg
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "suggestion"
    assert data["log_id"] == 42
    redis.set_ensemble_weights.assert_called_once_with(
        SAMPLE_SUGGESTION["suggested_weights"], source="suggestion"
    )
    redis._r.delete.assert_called_once_with("ensemble:weights:suggestion:snapshot")
    pg.log_weight_update.assert_called_once()


@pytest.mark.asyncio
async def test_approve_frozen_returns_403():
    """POST /approve without override_weights when freeze_reason is set → 403."""
    frozen = {**SAMPLE_SUGGESTION, "freeze_reason": "VIX > 40"}
    redis = make_redis_mock(suggestion=frozen)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 403
    assert "VIX > 40" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_override_bypasses_freeze():
    """POST /approve with override_weights succeeds even when freeze_reason is set."""
    frozen = {**SAMPLE_SUGGESTION, "freeze_reason": "VIX > 40"}
    redis = make_redis_mock(suggestion=frozen)
    pg = make_pg_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    app.dependency_overrides[get_pg_store] = lambda: pg
    override = {"opus": 0.50, "qwen3.5:cloud": 0.30, "deepseek-v4-pro:cloud": 0.20}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": override},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["source"] == "override"
    assert resp.json()["applied_weights"] == override


@pytest.mark.asyncio
async def test_approve_override_invalid_sum():
    """POST /approve with weights summing to ≠ 1.0 → 422."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    bad = {"opus": 0.50, "qwen3.5:cloud": 0.30, "deepseek-v4-pro:cloud": 0.30}  # sum=1.1
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": bad},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert "sum to 1.0" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_override_cap_exceeded():
    """POST /approve with weight > 0.70 → 422."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    bad = {"opus": 0.80, "qwen3.5:cloud": 0.10, "deepseek-v4-pro:cloud": 0.10}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": bad},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert "cap" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_unknown_model():
    """POST /approve with an unknown model id → 422."""
    redis = make_redis_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    bad = {"opus": 0.50, "gpt5": 0.50}  # gpt5 is not in config.MODEL_COSTS
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/weights/approve",
            json={"override_weights": bad},
            headers={"X-API-Key": API_KEY},
        )
    app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert "gpt5" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_approve_logs_approved_by_hash():
    """POST /approve stores approved_by as SHA-256[:8] of the api key, never raw."""
    redis = make_redis_mock()
    pg = make_pg_mock()
    app.dependency_overrides[get_redis_store] = lambda: redis
    app.dependency_overrides[get_pg_store] = lambda: pg
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    call_kwargs = pg.log_weight_update.call_args.kwargs
    expected_hash = hashlib.sha256(API_KEY.encode()).hexdigest()[:8]
    assert call_kwargs["approved_by"] == expected_hash
    assert API_KEY not in str(call_kwargs)


@pytest.mark.asyncio
async def test_approve_no_suggestion_returns_404():
    """POST /approve when Redis has no suggestion → 404."""
    redis = make_redis_mock(suggestion=None)
    app.dependency_overrides[get_redis_store] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/weights/approve", json={}, headers={"X-API-Key": API_KEY})
    app.dependency_overrides.clear()

    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they all pass**

Run: `pytest tests/api/test_weight_approval.py -v`

Expected: All 10 tests PASS.

- [ ] **Step 3: Run full API test suite for regressions**

Run: `pytest tests/api/ -v`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_weight_approval.py
git commit -m "test: add full test coverage for weight suggestion and approval endpoints"
```

---

## Task 6: Expiry Task — Snapshot Key + check_suggestion_expiry

When a suggestion is approved, the snapshot is deleted (preventing false expiry logs). When it expires naturally, the daily task picks it up from the snapshot and logs `source='expired'`.

**Files:**
- Modify: `src/workers/performance.py` (store snapshot, add new task)
- Modify: `src/workers/celery_app.py` (add daily beat entry)
- Modify: `tests/workers/test_performance_worker.py` (add expiry tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/workers/test_performance_worker.py`:

```python
class TestCheckSuggestionExpiry:
    """Tests for check_suggestion_expiry Celery task."""

    def test_logs_expired_when_suggestion_gone_and_snapshot_present(self):
        """If snapshot exists but suggestion key is gone, logs source='expired'."""
        import json
        from unittest.mock import MagicMock, patch

        snapshot = {
            "suggested_weights": {"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            "purified_icir": {"opus": 0.31},
            "freeze_reason": "",
            "computed_at": "2026-05-04T08:00:00+00:00",
        }

        mock_redis_client = MagicMock()
        mock_redis_client.get.side_effect = lambda key: (
            json.dumps(snapshot).encode() if key == "ensemble:weights:suggestion:snapshot"
            else None  # suggestion key is gone (expired)
        )

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        mock_pg.log_weight_update.assert_called_once()
        call_kwargs = mock_pg.log_weight_update.call_args.kwargs
        assert call_kwargs["source"] == "expired"
        assert call_kwargs["note"] == "Suggestion expired without approval"
        mock_redis_client.delete.assert_called_once_with("ensemble:weights:suggestion:snapshot")

    def test_does_nothing_when_no_snapshot(self):
        """If no snapshot exists, task exits silently."""
        from unittest.mock import MagicMock, patch

        mock_redis_client = MagicMock()
        mock_redis_client.get.return_value = None

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        mock_pg.log_weight_update.assert_not_called()

    def test_does_nothing_when_suggestion_still_active(self):
        """If both snapshot and suggestion exist, suggestion hasn't expired yet."""
        import json
        from unittest.mock import MagicMock, patch

        snapshot = {"suggested_weights": {}, "purified_icir": {}, "freeze_reason": "", "computed_at": "2026-05-04T08:00:00+00:00"}
        suggestion = snapshot.copy()

        mock_redis_client = MagicMock()
        mock_redis_client.get.return_value = json.dumps(snapshot).encode()  # both keys exist

        mock_redis_store = MagicMock()
        mock_redis_store._r = mock_redis_client

        mock_pg = MagicMock()

        with patch("src.workers.performance.RedisStore", return_value=mock_redis_store), \
             patch("src.workers.performance.PostgreSQLStore", return_value=mock_pg):
            from src.workers.performance import check_suggestion_expiry
            check_suggestion_expiry()

        mock_pg.log_weight_update.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/workers/test_performance_worker.py::TestCheckSuggestionExpiry -v`

Expected: FAIL with `ImportError` or `AttributeError` — `check_suggestion_expiry` does not exist yet.

- [ ] **Step 3: Update run_weekly_weights to also store the snapshot key**

In `src/workers/performance.py`, inside `run_weekly_weights()`, after the block that calls `redis._r.setex("ensemble:weights:suggestion", ...)`, add:

```python
        # Snapshot key: 9d TTL (2d buffer) — read by check_suggestion_expiry
        # if the 7d suggestion key expires before being approved.
        # Deleted by POST /api/weights/approve on successful approval.
        redis._r.setex(
            "ensemble:weights:suggestion:snapshot",
            86400 * 9,
            json.dumps(suggestion),
        )
```

- [ ] **Step 4: Add the check_suggestion_expiry task to performance.py**

Append to `src/workers/performance.py`:

```python
@app.task(name="src.workers.performance.check_suggestion_expiry")
def check_suggestion_expiry():
    """Daily: log weight suggestions that expired without being approved.

    Checks for the snapshot key (9d TTL) left by run_weekly_weights. If the
    snapshot exists but the original suggestion key (7d TTL) is gone, the
    suggestion expired without an admin approving it. Log source='expired'.
    The snapshot is also deleted by POST /api/weights/approve on success, so
    if we reach here the suggestion was never approved.
    """
    redis = RedisStore()

    snapshot_raw = redis._r.get("ensemble:weights:suggestion:snapshot")
    if snapshot_raw is None:
        return  # no pending suggestion

    if redis._r.get("ensemble:weights:suggestion") is not None:
        return  # suggestion still active, nothing to do

    # suggestion key gone + snapshot present → expired without approval
    snapshot = json.loads(snapshot_raw)
    pg = PostgreSQLStore()
    pg.log_weight_update(
        source="expired",
        applied_weights=snapshot.get("suggested_weights", {}),
        suggested_weights=snapshot.get("suggested_weights"),
        purified_icir=snapshot.get("purified_icir"),
        freeze_reason=snapshot.get("freeze_reason") or None,
        note="Suggestion expired without approval",
    )
    redis._r.delete("ensemble:weights:suggestion:snapshot")
    log.info("Weight suggestion expired without approval - logged to audit trail")
```

- [ ] **Step 5: Add the daily schedule to celery_app.py**

In `src/workers/celery_app.py`, add to `app.conf.beat_schedule`:

```python
    # Daily expiry check: log weight suggestions that were never approved
    "check-suggestion-expiry": {
        "task": "src.workers.performance.check_suggestion_expiry",
        "schedule": crontab(hour=5, minute=0),
    },
```

- [ ] **Step 6: Run the new tests**

Run: `pytest tests/workers/test_performance_worker.py::TestCheckSuggestionExpiry -v`

Expected: All 3 tests PASS.

- [ ] **Step 7: Run the full worker test suite for regressions**

Run: `pytest tests/workers/ -v`

Expected: All tests pass.

- [ ] **Step 8: Run the complete test suite**

Run: `pytest -v --tb=short`

Expected: All tests pass. No regressions across all modules.

- [ ] **Step 9: Commit**

```bash
git add src/workers/performance.py src/workers/celery_app.py tests/workers/test_performance_worker.py
git commit -m "feat: add check_suggestion_expiry task and snapshot key for expiry audit"
```

---

## Final Verification

- [ ] **Run full test suite one final time**

Run: `pytest -v --tb=short 2>&1 | tail -20`

Expected: All tests green, 0 failures.

- [ ] **Verify beat schedule has 5 tasks**

```python
python -c "
from src.workers.celery_app import app
for name in app.conf.beat_schedule:
    print(name)
"
```

Expected output:
```
sentiment-worker
performance-daily
performance-weekly
drift-detection
check-suggestion-expiry
```

- [ ] **Final commit (if anything was tweaked)**

```bash
git add -p
git commit -m "fix: final adjustments from integration review"
```
