# Alembic — Frontend & Operator Guide

**Last updated:** 2026-06-21  
**Scope:** P2-04 operator surfaces and frontend page inventory  
**Authorization:** Live trading NOT authorized. `GLOBAL_LIVE_PROMOTION_ENABLED = False`.

---

## 1. Operator API Surfaces (P2-04)

These are the canonical operator touchpoints. All require `X-API-Key` header.

### 1.1 System Readiness — `GET /api/system/readiness`

Returns a health snapshot of the entire system. **HTTP 200 does NOT mean healthy** — always inspect the body flags.

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/readiness
```

**Response schema:**

| Key | Type | Healthy value | Action when unhealthy |
|-----|------|--------------|----------------------|
| `redis_healthy` | bool | `true` | Redis is down — see [Runbook: Redis Down] in operations.md |
| `redis_writeable` | bool | `true` | Redis up but persistence misconfigured (AOF/RDB MISCONF) — see [Runbook: Redis MISCONF] |
| `db_healthy` | bool | `true` | PostgreSQL unreachable — check `docker compose ps postgres` |
| `killswitch_active` | bool | `false` | Trading halted — intentional or automatic drawdown trigger |
| `stale_signals` | bool | `false` | No fresh sentiment signals in last 2h — check sentiment worker |
| `worker_beat_lag` | bool | `false` | No portfolio cycle in last 60 min — check portfolio-cycle beat task |
| `last_signal_age_minutes` | float\|null | < 120 | Minutes since newest sentiment signal |
| `last_cycle_age_minutes` | float\|null | < 60 | Minutes since newest portfolio cycle |

**Key MISCONF pattern:** `redis_healthy=true` + `redis_writeable=false` = AOF/RDB persistence error. Fix: `redis-cli CONFIG SET appendonly no` or restart Redis with persistence re-enabled.

### 1.2 Execution Decisions — `GET /api/system/decisions`

Returns recent BUY/SELL/SKIP decisions from the `execution_decisions` audit table (local DB, not live broker).

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" "http://localhost:8001/api/system/decisions?limit=20"
```

**Response schema (per item):**

| Field | Description |
|-------|-------------|
| `tick_time` | ISO timestamp of the decision tick |
| `symbol` | Ticker symbol |
| `decision` | `BUY`, `SELL`, `SKIP`, `HALT` |
| `reason` | Human-readable reason string |
| `score` | Sentiment score at decision time |
| `price` | Price at decision time |

Default `limit=30`. Increase via `?limit=N`.

### 1.3 Scheduler Status — `GET /api/system/scheduler`

Returns the beat schedule with last-run timestamps from DB.

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/scheduler
```

### 1.4 Activity Log — `GET /api/system/activity`

Returns a unified chronological event log aggregating portfolio cycles, sentiment runs, news ingestion events, and trade decisions from the last 24h.

```bash
curl -H "X-API-Key: $ADMIN_API_KEY" "http://localhost:8001/api/system/activity?limit=50"
```

### 1.5 Kill-Switch — `POST /api/admin/killswitch`

Immediately halts all trading. Sets Redis key `killswitch_active=1`.

```bash
curl -X POST -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": true}' \
  http://localhost:8001/api/admin/killswitch
```

---

## 2. Frontend Page Inventory

The React frontend (`frontend/src/pages/`) exposes 16 pages. Authorization: login required for all pages.

| Page | File | API endpoints used | Operator usefulness |
|------|------|-------------------|---------------------|
| Overview | `Overview.tsx` | `/api/health`, `/api/admin/status` | Quick system status |
| Dashboard | `DashboardPage.tsx` | Multi-endpoint | P&L + activity summary |
| Signals | `Signals.tsx` | `/api/signals/{symbol}`, `/history` | Live sentiment signals |
| Strategies | `Strategies.tsx` | `/api/config` | Strategy allocation view |
| Trading | `Trading.tsx` | `/api/admin/mode`, `/api/admin/killswitch` | Mode control + kill-switch |
| Trades | `Trades.tsx` | `/api/trades/*`, `/analytics/*` | Trade analytics + P&L |
| Performance | `Performance.tsx` | `/api/performance/latest`, `/weights/*` | IC, weights, drift |
| News | `News.tsx` | `/api/news/recent` | Recent ingested articles |
| LLM | `LLM.tsx` | `/api/llm/feedback` | Model feedback loop |
| Auto-Improve | `AutoImprove.tsx` | `/api/feedback/status` | Phase B loss feedback |
| Config | `Config.tsx` | `/api/config` (GET/POST) | System config editor |
| System Log | `SystemLog.tsx` | `/api/system/activity` | Unified event log |
| Admin | `Admin.tsx` | `/api/admin/*` | Kill-switch + mode admin |
| Backtest | `Backtest.tsx` | Backtest API | Strategy backtesting |
| Docs | `Docs.tsx` | Static | Documentation viewer |
| Login | `LoginPage.tsx` | `/api/auth/login` | Authentication |

### 2.1 P2-04 Cockpit — Frontend Gap

The P2-04 operator cockpit (`/api/system/readiness`) is **API-available but has no dedicated UI page**. No frontend component currently polls `GET /api/system/readiness` and renders the 8-key health flags visually.

**Current workaround:** Use `curl` commands from operations.md runbooks.

**What a future cockpit UI page would show:**
- Red/green indicators for each of the 8 health flags
- Last-updated timestamp
- Direct links to runbooks for each unhealthy flag
- Auto-refresh every 60 seconds

This gap is acceptable for supervised_paper mode (operator manually polls) but should be addressed before controlled paper trading.

### 2.2 Strategy Mode / Lifecycle — Frontend Gap

The strategy lifecycle state machine (research → paper → supervised_paper → live) has no frontend display. The `Strategies.tsx` page shows allocation percentages from config but does NOT show:
- Current lifecycle mode per strategy
- Promotion prerequisites and remaining blockers
- Whether a strategy is in `promotion_blocked` state

**Current workaround:** Query `strategy_lifecycle` table directly or read `docs/strategies.md`.

---

## 3. Operator Workflow Reference

### 3.1 Morning Health Check (daily, before market open)

```bash
# 1. Check system readiness
curl -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/system/readiness | jq .

# 2. Check last portfolio cycle
curl -H "X-API-Key: $ADMIN_API_KEY" "http://localhost:8001/api/system/decisions?limit=5" | jq .

# 3. Check all containers healthy
docker compose ps

# 4. Check beat tasks running
docker compose logs --tail=20 beat
```

### 3.2 Confirming Kill-Switch State

```bash
# Check current state
docker compose exec redis redis-cli GET killswitch_active

# Clear kill-switch (manual)
docker compose exec redis redis-cli DEL killswitch_active

# Or via API
curl -X POST -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"active": false}' \
  http://localhost:8001/api/admin/killswitch
```

### 3.3 Reading Strategy Mode

```bash
# Query strategy lifecycle table directly
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT strategy_id, mode, promotion_blocked, updated_at FROM strategy_lifecycle ORDER BY strategy_id;"
```

Expected output for current authorized state:
- S1: `supervised_paper`, promotion_blocked=false
- S2: `paper`
- S3: `research`
- S4: `paper`, promotion_blocked=true
- S7: `research`

---

## 4. What Is NOT Authorized (2026-06-21)

| Action | Status | Blocker |
|--------|--------|---------|
| Live trading | NOT authorized | P2-05 open; Kimi P2 Audit not completed; PO sign-off required |
| Controlled paper trading | NOT authorized | P2-05 must be resolved first |
| Strategy promotions to `live` | NOT authorized | `GLOBAL_LIVE_PROMOTION_ENABLED = False` |
| Strategy promotions to `paper` | NOT authorized | No PO sign-off for any strategy currently in research |
| Setting `GLOBAL_LIVE_PROMOTION_ENABLED=True` | NOT authorized | See above |

Live trading authorization requires:
1. P2-05 closed (3 pending safety items)
2. Kimi P2 Acceptance Audit completed
3. 90 days of supervised_paper trading for S1
4. Explicit PO sign-off
5. `GLOBAL_LIVE_PROMOTION_ENABLED = True` set deliberately in `.env`
