# Alembic — Frontend & Operator Guide

**Last updated:** 2026-06-26 (rev 2)  
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

The React frontend (`frontend/src/pages/`) exposes the operator pages below. Authorization: login required for all pages.

| Page | File | API endpoints used | Operator usefulness |
|------|------|-------------------|---------------------|
| Overview | `Overview.tsx` | `/api/health`, `/api/admin/status` | Quick system status |
| Signals | `Signals.tsx` | `/api/signals/{symbol}`, `/history` | Live sentiment signals |
| Strategies | `Strategies.tsx` | `/api/strategies/*` | Strategy metrics, gates, lifecycle mode and authorization status |
| Trading | `Trading.tsx` | `/api/positions`, `/api/orders` | Positions, orders and true fills from filled orders |
| Performance | `Performance.tsx` | `/api/performance/pnl`, `/api/performance/daily`, `/api/performance/weekly`, `/api/trades/analytics/by-symbol`, `/api/trades/analytics/by-dimension`, `/weights/*` | P&L storico, breakdown giornaliero, Phase A trade analytics, report settimanale |
| News | `News.tsx` | `/api/news/recent`, `/api/news/source-quality` | Recent ingested articles and per-source quality funnel |
| LLM | `LLM.tsx` | `/api/llm/feedback`, `/api/llm/models`, `/api/weights/*` | Model feedback loop and dynamic ensemble weights |
| Auto-Improve | `AutoImprove.tsx` | `/api/feedback/status`, `/api/trades/analytics/counterfactual`, `/api/trades/analytics/counterfactual/status` | Feedback gate + counterfactual opportunity cost with worker freshness and raw skip counts |
| Operations | `Operations.tsx` | `/api/system/*`, `/api/config`, `/api/admin/*` | Unified System / Config / Admin operator surface |
| Quality | `Quality.tsx` | `/api/quality/metrics`, `/api/quality/sources` | QX-02 signal/extraction quality + **Source Funnel & P&L (S2-1, 2026-07-03)**: per-source funnel→latency→P&L table with removal-threshold verdicts (roadmap §7.4) and trace coverage |
| Labeling | `Labeling.tsx` | `/api/labeling/*` | QX-01 blind annotation UI (golden label set) |
| Validation | `Validation.tsx` | `/api/validation/*` | Paper-validation progress metrics |
| Backtest | `Backtest.tsx` | Backtest API | Strategy backtesting |
| Docs | `Docs.tsx` | Static | Documentation viewer |
| Login | `LoginPage.tsx` | `/api/auth/login` | Authentication |

`Trades.tsx` has been removed from the frontend. The legacy `/trades` route redirects to `Trading`. Order/fill operations are in `Trading`; closed-trade diagnostics and Phase A analytics are in `Performance`.

Trace links use one shared causal model: `News -> Signal -> Decision -> Order -> Performance`. Inline links remain available for fast navigation, and the `Trace` drawer shows the full chain with unavailable steps marked as not traced. Links are rendered only when the matching downstream id/count exists, so a trace should not lead to an empty list.

`DashboardPage.tsx` has been removed from the user-facing frontend. The legacy `/dashboard` route redirects to `Overview`; React pages are the primary monitoring surface. Grafana is no longer part of the local compose stack.

### 2.1 Pagina Performance — Tab disponibili

La pagina Performance (`/performance`) ha tre tab:

| Tab | Sorgente dati | Cosa mostra |
|-----|--------------|-------------|
| **P&L Storico** | `GET /api/performance/pnl` → Alpaca SDK | Cumulative P&L line chart, Portfolio Equity line chart, Monthly P&L Summary table, Trade Activity (last 30d) |
| **Giornaliero** | `GET /api/performance/daily` → tabella `trades` locale | P&L per giornata con filtro date (dal/al), preset 7d/14d/30d, grafico a barre verde/rosso, tabella espandibile per giorno con dettaglio trade (symbol, entry/exit price, qty, gross P&L, net P&L, motivo uscita) |
| **Analytics** | `GET /api/trades/analytics/by-symbol`, `GET /api/trades/analytics/by-dimension` | Phase A diagnostics by symbol, regime, hour, score bucket and hold time |
| **Report Settimanale** | `GET /api/performance/weekly` → Redis cache | Trade P&L 7d, analisi costi, capital efficiency, regime, feedback loop, infrastruttura, pesi LLM correnti/suggeriti |

**Nota:** "P&L Storico" usa l'equity Alpaca (variazione netta di conto), mentre "Giornaliero" usa i record `trades` locali con `net_pnl` calcolato da `entry_price`/`exit_price`. Piccole differenze numeriche sono normali (commissioni Alpaca, slippage).

#### Colonne della tabella "Dettaglio per Giornata"

| Colonna | Fonte | Significato |
|---------|-------|-------------|
| Data | `exit_time::date` | Giorno di chiusura trade (UTC) |
| Trade | `COUNT(*)` | Numero di trade chiusi in quella giornata |
| P&L Lordo | `SUM(COALESCE(gross_pnl, net_pnl))` | P&L prima dei costi di transazione |
| Costi | `SUM(gross_pnl − net_pnl)` | Erosione da slippage + spread stimati (sempre ≤ 0) |
| P&L Netto | `SUM(net_pnl)` | Risultato effettivo dopo i costi |
| W / L | `COUNT(net_pnl > 0)` / `COUNT(net_pnl < 0)` | Trade vincenti / perdenti |

Espandendo una riga giornata si vedono i singoli trade con: symbol, motivo uscita, entry/exit price, qty, P&L Lordo, Costi (`gross_pnl − net_pnl`), P&L Netto.

**KPI in cima al tab:**
- Riga 1: **P&L Lordo → Costi Transazione → P&L Netto** (progressione lordo→netto)
- Riga 2: Trade chiusi (W/L), Win rate, Giorni +/−

#### Come usare il tab Giornaliero

1. Selezionare il range con i campi **Dal / al** (formato italiano DD/MM/YYYY, clicking apre il calendar nativo)
2. Oppure usare i preset rapidi **7d / 14d / 30d**
3. Leggere i KPI in cima: riga 1 mostra la progressione lordo→costi→netto; riga 2 mostra trade stats
4. Usare il **grafico a barre** per identificare visivamente le giornate positive (verde) e negative (rosso)
5. Nella tabella "Dettaglio per Giornata", **cliccare su una riga** per espandere e vedere i singoli trade di quel giorno

**Esempio — query da CLI equivalente al tab Giornaliero:**
```bash
curl -H "X-API-Key: $ADMIN_API_KEY" \
  "http://localhost:8001/api/performance/daily?from_date=2026-06-24&to_date=2026-06-26"
```

---

### 2.2 P2-04 Cockpit — Frontend Coverage

The P2-04 operator cockpit is now partially surfaced in the frontend:

- `Overview.tsx` polls `GET /api/system/readiness` and shows high-level operational state.
- `Operations.tsx` groups the System tab (`/api/system/scheduler`, `/api/system/activity`, PEAD signals), Config tab and Admin tab.

**Remaining gap:** there is still no dedicated full 8-flag readiness matrix with direct runbook links for each unhealthy flag.

Use the `curl` commands from operations.md when a full readiness payload is required for preflight evidence.

### 2.3 Strategy Mode / Lifecycle — Frontend Coverage

`Strategies.tsx` now displays the lifecycle fields returned by `/api/strategies/*`:
- Current lifecycle mode per strategy
- `promotion_blocked`, `promotion_authorized`, and `live_authorized`
- Whether displayed metrics are `LIVE` or `BACKTEST`

Fail-closed rule: absent or false authorization fields must be treated as not authorized. Backtest gates are evidence only and do not authorize promotion or live trading.

### 2.4 Block 1 Product Decisions Reflected in Frontend

- LLM model names must come from the backend registry (`GET /api/llm/models` or `GET /api/admin/status`), not from hardcoded frontend lists.
- Sidebar Economy mode selects GLM-5.2 via canonical key `glm52`; legacy `glm` is accepted by the backend only as an alias.
- `LLM` weights use `GET /api/weights/current` for active weights and `GET /api/weights/suggestion` for pending suggestions. Stored weights for inactive models are ignored and surfaced as `dropped_models`.
- `Trading` Fills are derived from filled orders, not from local trade entry/exit rows.
- Operating mode changes require explicit confirmation before calling the write API.
- Labeling strength remains signed `-1..1` and is constrained by sentiment direction: positive > 0, negative < 0, neutral = 0.

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

# Clear kill-switch — ALWAYS via the API OTP flow (audit trail + cooldown).
# Never redis-cli DEL: it bypasses the recovery audit (see operations.md runbook).
curl -X POST -H "X-API-Key: $ADMIN_API_KEY" \
  http://localhost:8001/api/admin/killswitch/recovery-token
# then, with the returned token:
curl -X DELETE -H "X-API-Key: $ADMIN_API_KEY" \
  "http://localhost:8001/api/admin/killswitch?confirm_token=<token>"
```

### 3.3 Reading Strategy Mode

```bash
# Query strategy lifecycle table directly
docker compose exec postgres psql -U trading -d trading \
  -c "SELECT strategy_id, mode, promotion_blocked, updated_at FROM strategy_lifecycle ORDER BY strategy_id;"
```

Expected output for current authorized state:
- S1: `supervised_paper`, promotion_blocked=true (demoted P0-01; re-promotion requires PIT backtest + SPA + 90-day paper)
- S2: `disabled` (migration 025 seed; config: `research`, 0% allocation — options infra not implemented; do not enable)
- S3: `research`
- S4: `paper`, promotion_blocked=true
- S7: `research`

---

## 4. What Is NOT Authorized (2026-06-21)

| Action | Status | Blocker |
|--------|--------|---------|
| Live trading | NOT authorized | 90-day supervised_paper period not started; `GLOBAL_LIVE_PROMOTION_ENABLED=False`; PO sign-off required |
| Controlled paper trading | NOT authorized | P2-05 complete; Kimi P2 Audit complete (`P2_ACCEPTED_WITH_RUNTIME_MONITORING`); end-to-end dry-run and PO sign-off still required |
| Strategy promotions to `live` | NOT authorized | `GLOBAL_LIVE_PROMOTION_ENABLED = False` |
| Strategy promotions to `paper` | NOT authorized | No PO sign-off for any strategy currently in research |
| Setting `GLOBAL_LIVE_PROMOTION_ENABLED=True` | NOT authorized | See above |

Live trading authorization requires:
1. P2-05 closed (3 pending safety items)
2. Kimi P2 Acceptance Audit completed
3. 90 days of supervised_paper trading for S1
4. Explicit PO sign-off
5. `GLOBAL_LIVE_PROMOTION_ENABLED = True` set deliberately in `.env`
