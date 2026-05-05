# Weight Approval Feedback Loop — Design Spec

**Date:** 2026-05-05  
**Status:** Approved  
**Feature:** Fase 2 — Auto-weight update cycle (suggestion → approval → audit)

---

## 1. Context

`run_weekly_weights()` (Celery beat, weekly) already computes LOO ICIR, applies guardrails, and stores a weight suggestion in Redis at `ensemble:weights:suggestion` (TTL 7 days). The current `POST /api/weights/approve` ignores this suggestion entirely and writes arbitrary weights directly to Redis. There is no audit trail.

This spec closes the loop.

---

## 2. Architecture & Data Flow

```
Celery beat (weekly)
  └─► run_weekly_weights()
        └─► Redis: ensemble:weights:suggestion  (TTL 7d)

Admin
  └─► GET  /api/weights/suggestion   ← reads Redis, shows diff + freeze status
  └─► POST /api/weights/approve       ← validates, applies, audits
        ├─► Redis: ensemble:weights:current  (TTL 30d)
        └─► PostgreSQL: weight_update_log

Celery beat (daily)
  └─► check_suggestion_expiry()
        └─► PostgreSQL: weight_update_log (source='expired')
```

**Files modified:**
- `src/api/routes/performance.py` — add `GET /suggestion`, redesign `POST /approve`
- `src/store/redis_store.py` — add `get_weight_suggestion()` method
- `src/workers/performance.py` — add `check_suggestion_expiry()` task
- `alembic/versions/XXXX_add_weight_update_log.py` — new migration
- `tests/api/test_weight_approval.py` — new test file

`run_weekly_weights()` is unchanged — it already writes the correct suggestion payload.

---

## 3. API Endpoints

### `GET /api/weights/suggestion`

Returns the current weight suggestion from Redis.

**Response 200:**
```json
{
  "suggested_weights": {"opus": 0.45, "sonnet": 0.35, "qwen": 0.20},
  "purified_icir":     {"opus": 0.31, "sonnet": 0.18, "qwen": 0.09},
  "freeze_reason":     null,
  "computed_at":       "2026-05-04T08:00:00+00:00",
  "expires_at":        "2026-05-11T08:00:00+00:00"
}
```

`freeze_reason` non-null is informational — the admin can see why the circuit breaker fired before deciding to override.

**Response 404:** No suggestion in Redis.

---

### `POST /api/weights/approve`

Applies the Redis suggestion (default) or admin-supplied override weights.

**Request body (all fields optional):**
```json
{
  "override_weights": {"opus": 0.50, "sonnet": 0.30, "qwen": 0.20},
  "note": "manual rebalance post-earnings"
}
```

**Approval logic:**
1. Read suggestion from Redis → `404` if absent
2. If `freeze_reason != null` and no `override_weights` → `403` with reason
3. If `override_weights` provided → bypass suggestion; validate sum=1.0 (±0.001) and per-weight bounds [0.10, 0.70]
4. Write `ensemble:weights:current` to Redis (TTL 30d)
5. Write row to `weight_update_log`; set `source = "suggestion" | "override"`

**Response 200:**
```json
{
  "applied_weights": {"opus": 0.45, "sonnet": 0.35, "qwen": 0.20},
  "source": "suggestion",
  "log_id": 42
}
```

---

## 4. PostgreSQL Schema

Migration: `alembic/versions/XXXX_add_weight_update_log.py`

```sql
CREATE TABLE weight_update_log (
    id                SERIAL PRIMARY KEY,
    applied_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    source            VARCHAR(20) NOT NULL,     -- 'suggestion' | 'override' | 'expired'
    applied_weights   JSONB NOT NULL,
    suggested_weights JSONB,                    -- null when source='expired'
    purified_icir     JSONB,
    freeze_reason     TEXT,
    note              TEXT,
    approved_by       TEXT                      -- SHA-256[:8] of api_key, never raw
);
```

`source='expired'` is written by `check_suggestion_expiry()` when a suggestion's TTL has elapsed without approval. This completes the audit trail.

`approved_by` stores a truncated SHA-256 hash of the API key — never the raw value.

---

## 5. Error Handling

| Condition | HTTP | Detail |
|-----------|------|--------|
| No suggestion in Redis | 404 | `"No weight suggestion available"` |
| `freeze_reason` present, no override | 403 | `"Weight update frozen: <reason>"` |
| `override_weights` sum ≠ 1.0 (±0.001) | 422 | `"Weights must sum to 1.0"` |
| Weight outside [0.10, 0.70] | 422 | `"Weight for opus=0.80 exceeds cap 0.70"` |
| Unknown model in override | 422 | `"Unknown model: gpt5"` |
| Redis unreachable | 503 | `"Cache unavailable"` |

---

## 6. Testing

All tests in `tests/api/test_weight_approval.py`. Redis and PostgreSQL are mocked.

| Test | Verifies |
|------|----------|
| `test_get_suggestion_ok` | 200 with correct payload from Redis |
| `test_get_suggestion_not_found` | 404 when Redis is empty |
| `test_approve_from_suggestion` | Applies suggestion, writes Redis + DB, `source="suggestion"` |
| `test_approve_frozen_returns_403` | `freeze_reason` present → 403 |
| `test_approve_override_bypasses_freeze` | `override_weights` with active freeze → 200 |
| `test_approve_override_invalid_sum` | Sum ≠ 1.0 → 422 |
| `test_approve_override_cap_exceeded` | Weight > 0.70 → 422 |
| `test_approve_logs_to_db` | Row written to `weight_update_log` |
| `test_expiry_task_logs_expired` | Celery task writes `source="expired"` |
