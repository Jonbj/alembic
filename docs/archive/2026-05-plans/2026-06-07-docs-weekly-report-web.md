# Docs Rewrite + Weekly Report Web Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Riscrivere completamente `Docs.tsx` con teoria delle strategie, flusso segnale e come le strategie intervengono sui segnali; (2) Rendere il report settimanale con le metriche sui costi disponibile anche via web (API + tab Performance), non solo su Telegram.

**Architecture:** Il weekly report viene costruito in `run_weekly_weights()` come dict strutturato e scritto in Redis (`performance:weekly_report`, TTL 9d). Un nuovo endpoint `GET /api/performance/weekly` lo espone. Il frontend aggiunge un tab "Weekly Report" alla pagina Performance. Docs.tsx viene riscritto da zero con sezioni su teoria strategia, flusso segnale S1/S4 e constraint applicati.

**Tech Stack:** Python/FastAPI (backend), Redis JSON storage, React/TypeScript (frontend), Recharts (grafici esistenti)

---

## File Structure

**Backend:**
- Modify: `src/workers/performance.py` — aggiunge `_build_weekly_structured()` e lo chiama in `run_weekly_weights()`
- Modify: `src/api/routes/performance.py` — aggiunge `GET /api/performance/weekly`

**Frontend:**
- Modify: `frontend/src/api/performance.ts` — aggiunge `fetchWeeklyReport()` e interfacce TypeScript
- Modify: `frontend/src/pages/Performance.tsx` — aggiunge tab "Weekly Report" con le sezioni costi
- Modify: `frontend/src/pages/Docs.tsx` — riscrittura completa

**Tests:**
- Modify: `tests/api/test_api.py` — aggiunge test per `/api/performance/weekly`

---

## Task 1: Backend — `_build_weekly_structured()` + Redis storage

**Files:**
- Modify: `src/workers/performance.py` (dopo `_format_infrastructure_section`, prima di `run_daily_report`)

- [ ] **Step 1: Aggiungere la funzione `_build_weekly_structured()`**

Inserire dopo la funzione `_format_infrastructure_section` (riga ~544) e prima di `run_daily_report` (riga ~547) in `src/workers/performance.py`:

```python
def _build_weekly_structured(
    new_weights: dict,
    current_weights: dict,
    freeze_reason: str,
    purified_icir: dict,
    pg: "PostgreSQLStore",
    redis: "RedisStore",
) -> dict:
    """Build structured weekly report dict for the web API (JSON-serializable)."""
    data: dict = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "weights": {
            "current": current_weights,
            "suggested": new_weights,
            "purified_icir": purified_icir,
            "freeze_reason": freeze_reason,
        },
        "trade_pnl": {},
        "capital_efficiency": {},
        "regime": {},
        "feedback": {},
        "infrastructure": {},
    }

    try:
        ts = pg.fetch_trade_summary(days=7)
        data["trade_pnl"] = {k: ts.get(k, 0) for k in [
            "total_trades", "win_rate", "avg_net_pnl", "avg_gross_pnl",
            "avg_slippage_est", "total_net_pnl", "total_gross_pnl",
            "total_notional", "trades_per_week", "avg_hold_minutes",
            "slippage_pct_of_gross", "return_on_notional",
            "avg_cost_bps", "total_cost_usd", "avg_spread_cost_bps",
            "avg_impact_cost_bps", "cost_drag_pct",
        ]}
    except Exception as e:
        log.warning("weekly_structured: trade_pnl fetch failed: %s", e)

    try:
        open_trades = pg.fetch_trades(status="open", limit=20)
        pv = float(redis._r.get("portfolio:value") or 0)
        deployed = sum(float(t.get("entry_notional") or 0) for t in open_trades)
        n_open = len(open_trades)
        depl_pct = deployed / pv if pv > 0 else 0.0
        cash_pct = 1.0 - depl_pct
        data["capital_efficiency"] = {
            "portfolio_value_usd": pv,
            "deployed_notional": deployed,
            "n_open_positions": n_open,
            "deployment_pct": depl_pct,
            "cash_pct": cash_pct,
            "annual_cash_drag_pct": cash_pct * 0.045 * 100,
            "efficiency_ratio": (deployed / (pv * 0.50)) if pv > 0 else 0.0,
        }
    except Exception as e:
        log.warning("weekly_structured: capital_efficiency fetch failed: %s", e)

    try:
        regime_state = redis.get_regime()
        _MULTS = {"bull": 1.0, "sideways": 0.7, "bear": 0.4, "high_vol": 0.2}
        label = str(getattr(regime_state, "regime", "unknown") if regime_state else "unknown")
        mult = float(getattr(regime_state, "multiplier", _MULTS.get(label, 0.2)) if regime_state else 0.2)
        conf = float(getattr(regime_state, "confidence", 0.0) if regime_state else 0.0)
        data["regime"] = {
            "label": label,
            "multiplier": mult,
            "confidence": conf,
            "deployment_ceiling_pct": 0.10 * mult * 5,
            "regime_discount_pct": (1.0 - mult) * 100,
        }
    except Exception as e:
        log.warning("weekly_structured: regime fetch failed: %s", e)

    try:
        import yaml
        from pathlib import Path
        _TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
        with open(_TRADING_YAML) as f:
            cfg_yaml = yaml.safe_load(f) or {}
        fb_cfg = cfg_yaml.get("loss_feedback", {})
        baseline = float(fb_cfg.get("threshold_baseline", 0.30))
        recovery_win_streak = int(fb_cfg.get("recovery_win_streak", 5))
        current_thr = redis.get_feedback_entry_threshold() or baseline
        current_scale = redis.get_feedback_regime_scale() or 1.0
        fb_state = redis.get_feedback_state() or {}
        data["feedback"] = {
            "threshold_baseline": baseline,
            "current_threshold": current_thr,
            "current_scale": current_scale,
            "is_elevated": current_thr > baseline + 0.001,
            "consecutive_wins": int(fb_state.get("consecutive_wins") or 0),
            "recovery_win_streak": recovery_win_streak,
            "last_adjustment_ts": fb_state.get("last_adjustment_ts", ""),
        }
    except Exception as e:
        log.warning("weekly_structured: feedback fetch failed: %s", e)

    try:
        import yaml
        from pathlib import Path
        _TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
        with open(_TRADING_YAML) as f:
            cfg_yaml = yaml.safe_load(f) or {}
        annual_fixed = float(cfg_yaml.get("infrastructure", {}).get("annual_fixed_cost_usd", 1440.0))
        llm_30d = pg.fetch_llm_budget_period(days=30)
        monthly_fixed = annual_fixed / 12
        monthly_llm = float(llm_30d)
        monthly_total = monthly_fixed + monthly_llm
        annual_total = annual_fixed + monthly_llm * 12
        data["infrastructure"] = {
            "monthly_fixed_usd": monthly_fixed,
            "monthly_llm_usd": monthly_llm,
            "monthly_total_usd": monthly_total,
            "annual_total_usd": annual_total,
            "breakevens": {str(p): annual_total / (p / 100) for p in [5, 10, 15]},
        }
    except Exception as e:
        log.warning("weekly_structured: infrastructure fetch failed: %s", e)

    return data
```

- [ ] **Step 2: Chiamare `_build_weekly_structured()` in `run_weekly_weights()`**

In `run_weekly_weights()`, subito dopo la riga:
```python
asyncio.run(notifier.send_alert(message, level="info"))
```
e prima di:
```python
log.info(f"Weekly weights computed. Suggestion stored in Redis.")
```
Aggiungere:

```python
        # Store structured weekly report for web API (TTL 9d, same as snapshot)
        try:
            weekly_structured = _build_weekly_structured(
                new_weights=new_weights,
                current_weights=current_weights,
                freeze_reason=freeze_reason,
                purified_icir=purified_icir,
                pg=pg,
                redis=redis,
            )
            redis._r.setex(
                "performance:weekly_report",
                86400 * 9,
                json.dumps(weekly_structured),
            )
        except Exception as e:
            log.warning("Failed to store structured weekly report: %s", e)
```

- [ ] **Step 3: Verify syntax**

```bash
python -m py_compile src/workers/performance.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/workers/performance.py
git commit -m "feat(performance): store structured weekly report in Redis for web API"
```

---

## Task 2: Backend — `GET /api/performance/weekly` endpoint

**Files:**
- Modify: `src/api/routes/performance.py`

- [ ] **Step 1: Write the failing test**

In `tests/api/test_api.py`, aggiungere:

```python
def test_weekly_report_not_found(client, mock_redis):
    """Returns 404 when no weekly report is in Redis."""
    mock_redis.get.return_value = None
    resp = client.get("/api/performance/weekly", headers={"X-API-Key": "test-key-" + "x" * 26})
    assert resp.status_code == 404

def test_weekly_report_returns_data(client, mock_redis):
    """Returns structured weekly report when present in Redis."""
    import json
    mock_redis.get.return_value = json.dumps({
        "computed_at": "2026-06-07T04:00:00+00:00",
        "weights": {"current": {}, "suggested": {}, "purified_icir": {}, "freeze_reason": ""},
        "trade_pnl": {"total_trades": 5, "win_rate": 0.6},
        "capital_efficiency": {"portfolio_value_usd": 10000.0},
        "regime": {"label": "bull", "multiplier": 1.0},
        "feedback": {"is_elevated": False},
        "infrastructure": {"monthly_total_usd": 120.0},
    })
    resp = client.get("/api/performance/weekly", headers={"X-API-Key": "test-key-" + "x" * 26})
    assert resp.status_code == 200
    data = resp.json()
    assert data["trade_pnl"]["total_trades"] == 5
    assert data["regime"]["label"] == "bull"
```

- [ ] **Step 2: Aggiungere l'endpoint in `src/api/routes/performance.py`**

Dopo `get_latest_performance` (riga ~68), aggiungere:

```python
@router.get("/performance/weekly")
async def get_weekly_report(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    """Return latest structured weekly report (computed Monday 04:00 UTC, TTL 9d)."""
    raw = redis._r.get("performance:weekly_report")
    if raw is None:
        raise HTTPException(status_code=404, detail="No weekly report available yet")
    return json.loads(raw)
```

Aggiungere `import json` in cima se non già presente (verificare con `grep "^import json" src/api/routes/performance.py`).

- [ ] **Step 3: Verify syntax**

```bash
python -m py_compile src/api/routes/performance.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/api/routes/performance.py tests/api/test_api.py
git commit -m "feat(api): add GET /api/performance/weekly endpoint for web weekly report"
```

---

## Task 3: Frontend — API client + Weekly Report tab in Performance

**Files:**
- Modify: `frontend/src/api/performance.ts`
- Modify: `frontend/src/pages/Performance.tsx`

- [ ] **Step 1: Aggiungere interfacce e fetch in `frontend/src/api/performance.ts`**

Sostituire il contenuto del file con:

```typescript
import { apiFetch } from './client'

export interface PnLData {
  daily: { date: string; equity: number; profit_loss: number }[]
  monthly: { month: string; pnl: number }[]
}

export interface WeeklyTradePnL {
  total_trades: number
  win_rate: number
  avg_net_pnl: number
  avg_gross_pnl: number
  avg_slippage_est: number
  total_net_pnl: number
  total_gross_pnl: number
  total_notional: number
  trades_per_week: number
  avg_hold_minutes: number
  slippage_pct_of_gross: number
  return_on_notional: number
  avg_cost_bps: number
  total_cost_usd: number
  avg_spread_cost_bps: number
  avg_impact_cost_bps: number
  cost_drag_pct: number
}

export interface WeeklyReport {
  computed_at: string
  weights: {
    current: Record<string, number>
    suggested: Record<string, number>
    purified_icir: Record<string, number>
    freeze_reason: string
  }
  trade_pnl: Partial<WeeklyTradePnL>
  capital_efficiency: {
    portfolio_value_usd: number
    deployed_notional: number
    n_open_positions: number
    deployment_pct: number
    cash_pct: number
    annual_cash_drag_pct: number
    efficiency_ratio: number
  }
  regime: {
    label: string
    multiplier: number
    confidence: number
    deployment_ceiling_pct: number
    regime_discount_pct: number
  }
  feedback: {
    threshold_baseline: number
    current_threshold: number
    current_scale: number
    is_elevated: boolean
    consecutive_wins: number
    recovery_win_streak: number
    last_adjustment_ts: string
  }
  infrastructure: {
    monthly_fixed_usd: number
    monthly_llm_usd: number
    monthly_total_usd: number
    annual_total_usd: number
    breakevens: Record<string, number>
  }
}

export const fetchPnL = (period = '6M') =>
  apiFetch<PnLData>(`/api/performance/pnl?period=${period}`)

export const fetchWeeklyReport = () =>
  apiFetch<WeeklyReport>('/api/performance/weekly')
```

- [ ] **Step 2: Aggiungere tab Weekly Report in `frontend/src/pages/Performance.tsx`**

In cima al file, aggiungere l'import:
```typescript
import { fetchPnL, fetchWeeklyReport } from '@/api/performance'
```
(sostituisce l'import esistente `import { fetchPnL } from '@/api/performance'`)

Poi aggiungere la query per il weekly report dopo la query `tradeSummary` esistente:
```typescript
  const { data: weekly, isLoading: weeklyLoading } = useQuery({
    queryKey: ['weekly-report'],
    queryFn: fetchWeeklyReport,
    retry: false,
  })
```

Aggiungere state per il tab attivo, dopo gli `useState` esistenti:
```typescript
  const [activeTab, setActiveTab] = useState<'pnl' | 'weekly'>('pnl')
```

Aggiungere il tab switcher prima del contenuto principale (dopo il `<h2>Performance</h2>`), prima dei selettori di periodo:
```tsx
      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20 }}>
        {(['pnl', 'weekly'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            style={{
              padding: '6px 16px',
              borderRadius: 6,
              border: 'none',
              background: activeTab === t ? 'var(--blue)' : '#1e293b',
              color: activeTab === t ? 'white' : '#94a3b8',
              fontSize: 13,
              fontWeight: activeTab === t ? 600 : 400,
              cursor: 'pointer',
            }}
          >
            {t === 'pnl' ? 'P&L Storico' : 'Report Settimanale'}
          </button>
        ))}
      </div>
```

Avvolgere il contenuto P&L esistente (dai grafici fino alla fine del return) in:
```tsx
      {activeTab === 'pnl' && (
        <>
          {/* tutto il contenuto P&L esistente */}
        </>
      )}
      {activeTab === 'weekly' && (
        <WeeklyReportTab weekly={weekly} isLoading={weeklyLoading} />
      )}
```

- [ ] **Step 3: Aggiungere il componente `WeeklyReportTab` in fondo a `Performance.tsx`** (prima del `export default`)

```tsx
function WeeklyReportTab({
  weekly,
  isLoading,
}: {
  weekly: import('@/api/performance').WeeklyReport | undefined
  isLoading: boolean
}) {
  const card: React.CSSProperties = {
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: 8,
    padding: '16px 20px',
    marginBottom: 16,
  }
  const h3: React.CSSProperties = { margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: 'white' }
  const row: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid #1e293b', fontSize: 13 }
  const label: React.CSSProperties = { color: '#94a3b8' }
  const value: React.CSSProperties = { color: 'white', fontWeight: 500 }
  const pct = (v: number | undefined) => v != null ? `${(v * 100).toFixed(2)}%` : '—'
  const usd = (v: number | undefined) => v != null ? `$${v.toFixed(2)}` : '—'
  const bps = (v: number | undefined) => v != null ? `${v.toFixed(1)} bps` : '—'
  const num = (v: number | undefined, d = 1) => v != null ? v.toFixed(d) : '—'

  if (isLoading) return <div style={{ color: '#94a3b8', padding: 24 }}>Caricamento report settimanale…</div>
  if (!weekly) return (
    <div style={{ color: '#94a3b8', padding: 24, textAlign: 'center' }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
      <div>Nessun report settimanale disponibile.</div>
      <div style={{ fontSize: 12, marginTop: 8 }}>Il report viene calcolato ogni lunedì alle 04:00 UTC da <code>run_weekly_weights</code>.</div>
    </div>
  )

  const tp = weekly.trade_pnl
  const ce = weekly.capital_efficiency
  const rg = weekly.regime
  const fb = weekly.feedback
  const inf = weekly.infrastructure
  const wt = weekly.weights

  const computedDate = weekly.computed_at
    ? new Date(weekly.computed_at).toLocaleString('it-IT', { dateStyle: 'medium', timeStyle: 'short' })
    : '—'

  return (
    <div>
      <div style={{ color: '#64748b', fontSize: 12, marginBottom: 16 }}>
        Aggiornato: {computedDate} · Scade dopo 9 giorni
      </div>

      {/* Trade P&L */}
      <div style={card}>
        <h3 style={h3}>📊 Trade P&L (ultimi 7 giorni)</h3>
        {(tp.total_trades ?? 0) === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>Nessun trade chiuso nel periodo.</div>
        ) : (
          <>
            <div style={row}><span style={label}>Trade totali</span><span style={value}>{tp.total_trades}</span></div>
            <div style={row}><span style={label}>Win rate</span><span style={value}>{pct(tp.win_rate)}</span></div>
            <div style={row}><span style={label}>P&L netto medio</span><span style={{ ...value, color: (tp.avg_net_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>{usd(tp.avg_net_pnl)}</span></div>
            <div style={row}><span style={label}>P&L lordo medio</span><span style={value}>{usd(tp.avg_gross_pnl)}</span></div>
            <div style={row}><span style={label}>Slippage medio</span><span style={value}>{usd(tp.avg_slippage_est)}</span></div>
            <div style={row}><span style={label}>P&L netto totale</span><span style={{ ...value, color: (tp.total_net_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>{usd(tp.total_net_pnl)}</span></div>
            <div style={row}><span style={label}>Notional totale</span><span style={value}>${(tp.total_notional ?? 0).toFixed(0)}</span></div>
            <div style={row}><span style={label}>Trade/settimana</span><span style={value}>{num(tp.trades_per_week)}</span></div>
            <div style={row}><span style={label}>Hold medio</span><span style={value}>{num(tp.avg_hold_minutes, 0)} min</span></div>
            <div style={row}><span style={label}>Return on notional</span><span style={value}>{pct(tp.return_on_notional)}</span></div>
          </>
        )}
      </div>

      {/* Cost Analysis */}
      <div style={card}>
        <h3 style={h3}>💸 Analisi Costi</h3>
        {(tp.avg_cost_bps ?? 0) === 0 ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>Nessun dato costi disponibile (trade pre-migration 019).</div>
        ) : (
          <>
            <div style={row}><span style={label}>Costo medio/trade</span><span style={value}>{bps(tp.avg_cost_bps)}</span></div>
            <div style={row}><span style={label}>  di cui spread</span><span style={{ ...label, paddingLeft: 16 }}>{bps(tp.avg_spread_cost_bps)}</span></div>
            <div style={row}><span style={label}>  di cui market impact</span><span style={{ ...label, paddingLeft: 16 }}>{bps(tp.avg_impact_cost_bps)}</span></div>
            <div style={row}><span style={label}>Costo totale (7d)</span><span style={value}>{usd(tp.total_cost_usd)}</span></div>
            <div style={row}><span style={label}>Cost drag (giornaliero)</span><span style={value}>{pct(tp.cost_drag_pct)}</span></div>
            <div style={row}><span style={label}>Cost drag annualizzato</span><span style={{ ...value, color: '#f59e0b' }}>~{((tp.cost_drag_pct ?? 0) * 252 * 100).toFixed(0)} bps/anno</span></div>
          </>
        )}
      </div>

      {/* Capital Efficiency */}
      <div style={card}>
        <h3 style={h3}>💰 Efficienza Capitale</h3>
        <div style={row}><span style={label}>Valore portafoglio</span><span style={value}>${(ce.portfolio_value_usd ?? 0).toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span></div>
        <div style={row}><span style={label}>Capitale deployato</span><span style={value}>{pct(ce.deployment_pct)} ({ce.n_open_positions ?? 0} posizioni)</span></div>
        <div style={row}><span style={label}>Capitale idle (cash)</span><span style={value}>{pct(ce.cash_pct)}</span></div>
        <div style={row}><span style={label}>Cash drag annuo stimato</span><span style={{ ...value, color: '#f59e0b' }}>{num(ce.annual_cash_drag_pct, 1)}% (costo opportunità vs T-bill 4.5%)</span></div>
        <div style={row}><span style={label}>Efficienza deployment</span><span style={value}>{pct(ce.efficiency_ratio)} del teorico max (5 pos × 10%)</span></div>
      </div>

      {/* Regime */}
      <div style={card}>
        <h3 style={h3}>📡 Regime & Deployment Ceiling</h3>
        <div style={row}>
          <span style={label}>Regime corrente</span>
          <span style={{
            ...value,
            color: rg.label === 'bull' ? '#22c55e' : rg.label === 'bear' ? '#ef4444' : rg.label === 'high_vol' ? '#f97316' : '#f59e0b',
          }}>
            {rg.label ?? '—'} (×{num(rg.multiplier, 1)})
          </span>
        </div>
        <div style={row}><span style={label}>Confidenza</span><span style={value}>{pct(rg.confidence)}</span></div>
        <div style={row}><span style={label}>Deployment ceiling</span><span style={value}>{pct(rg.deployment_ceiling_pct)}</span></div>
        <div style={row}><span style={label}>Capitale trattenuto vs bull</span><span style={{ ...value, color: '#f59e0b' }}>{num(rg.regime_discount_pct, 0)}%</span></div>
      </div>

      {/* Feedback Loop */}
      <div style={card}>
        <h3 style={h3}>🧠 Feedback Loop (threshold adattivo)</h3>
        <div style={row}><span style={label}>Threshold baseline</span><span style={value}>{num(fb.threshold_baseline, 2)}</span></div>
        <div style={row}>
          <span style={label}>Threshold corrente</span>
          <span style={{ ...value, color: fb.is_elevated ? '#ef4444' : '#22c55e' }}>
            {num(fb.current_threshold, 2)} {fb.is_elevated ? '🔴 ELEVATO' : '✅ Normale'}
          </span>
        </div>
        <div style={row}><span style={label}>Regime scale</span><span style={value}>×{num(fb.current_scale, 2)}</span></div>
        {fb.is_elevated && (
          <div style={row}>
            <span style={label}>Recovery</span>
            <span style={value}>{fb.consecutive_wins ?? 0}/{fb.recovery_win_streak ?? 5} win consecutivi</span>
          </div>
        )}
        {fb.last_adjustment_ts && (
          <div style={row}><span style={label}>Ultimo aggiustamento</span><span style={value}>{fb.last_adjustment_ts.slice(0, 10)}</span></div>
        )}
      </div>

      {/* Infrastructure */}
      <div style={card}>
        <h3 style={h3}>🏗️ Costi Infrastruttura & Break-even</h3>
        <div style={row}><span style={label}>Costo fisso mensile</span><span style={value}>${num(inf.monthly_fixed_usd, 0)}</span></div>
        <div style={row}><span style={label}>Costo LLM (30d)</span><span style={value}>${num(inf.monthly_llm_usd, 2)}</span></div>
        <div style={row}><span style={label}>Totale mensile</span><span style={{ ...value, fontWeight: 700 }}>${num(inf.monthly_total_usd, 0)}</span></div>
        <div style={row}><span style={label}>Stima annuale</span><span style={{ ...value, color: '#f59e0b' }}>${(inf.annual_total_usd ?? 0).toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span></div>
        <div style={{ marginTop: 12, fontSize: 12, color: '#64748b' }}>Break-even portfolio (per coprire i costi annui):</div>
        {inf.breakevens && Object.entries(inf.breakevens).map(([pctStr, size]) => (
          <div key={pctStr} style={row}>
            <span style={label}>A {pctStr}% rendimento annuo</span>
            <span style={value}>${(size as number).toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span>
          </div>
        ))}
      </div>

      {/* Weights suggestion */}
      <div style={card}>
        <h3 style={h3}>⚖️ Pesi LLM — Suggerimento</h3>
        {wt.freeze_reason ? (
          <div style={{ color: '#f59e0b', fontSize: 13, marginBottom: 12 }}>
            ⚠️ Aggiornamento pesi congelato: {wt.freeze_reason}
          </div>
        ) : null}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, fontSize: 12 }}>
          <div style={{ color: '#64748b', fontWeight: 600 }}>Modello</div>
          <div style={{ color: '#64748b', fontWeight: 600 }}>Corrente</div>
          <div style={{ color: '#64748b', fontWeight: 600 }}>Suggerito</div>
          {Object.keys({ ...wt.current, ...wt.suggested }).map((model) => (
            <>
              <div key={model + '-m'} style={{ color: '#94a3b8' }}>{model}</div>
              <div key={model + '-c'} style={{ color: 'white' }}>{((wt.current[model] ?? 0) * 100).toFixed(1)}%</div>
              <div key={model + '-s'} style={{ color: '#60a5fa' }}>{((wt.suggested[model] ?? 0) * 100).toFixed(1)}%</div>
            </>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build completes without TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/performance.ts frontend/src/pages/Performance.tsx
git commit -m "feat(frontend): add Weekly Report tab to Performance page with cost/capital/regime/infra sections"
```

---

## Task 4: Frontend — Riscrittura completa `Docs.tsx`

**Files:**
- Modify: `frontend/src/pages/Docs.tsx` — sostituzione completa del contenuto

**Obiettivo:** Spiegare a un utente che si avvicina ad Alembic per la prima volta:
1. Cosa fa il sistema
2. Teoria e logica di ogni strategia (S1, S4, S2 disabled, S3 R&D)
3. Flusso completo di un segnale (da news a ordine Alpaca)
4. Come le strategie intervengono sul segnale (filtri, scaling, merge orchestratore)
5. Parametri di rischio e validazione

- [ ] **Step 1: Sostituire il contenuto di `frontend/src/pages/Docs.tsx`**

Sostituire **l'intero file** con il seguente contenuto:

```tsx
import { HelpButton } from '@/components/shared/HelpButton'

export default function Docs() {
  const h2: React.CSSProperties = {
    fontSize: 17, fontWeight: 700, margin: '0 0 14px',
    paddingBottom: 10, borderBottom: '1px solid var(--border)',
    display: 'flex', alignItems: 'center', gap: 8,
  }
  const h3: React.CSSProperties = { fontSize: 13, fontWeight: 600, margin: '16px 0 6px', color: 'var(--blue)' }
  const card: React.CSSProperties = {
    background: 'var(--card)', border: '1px solid var(--border)',
    borderRadius: 8, padding: '20px 24px', marginBottom: 20,
  }
  const inner: React.CSSProperties = {
    background: 'var(--bg)', border: '1px solid var(--border)',
    borderRadius: 6, padding: '12px 14px', marginBottom: 10,
  }
  const p: React.CSSProperties = { margin: '0 0 10px', lineHeight: 1.7, color: 'var(--text-muted)', fontSize: 13 }
  const ul: React.CSSProperties = { margin: '0 0 10px', paddingLeft: 20, lineHeight: 2, color: 'var(--text-muted)', fontSize: 13 }
  const mono: React.CSSProperties = {
    background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6,
    padding: '14px 18px', fontFamily: 'monospace', fontSize: 12,
    color: 'var(--text-muted)', lineHeight: 2, overflowX: 'auto', whiteSpace: 'pre',
    marginBottom: 10,
  }
  const badge = (color: string, bg: string): React.CSSProperties => ({
    display: 'inline-block', marginLeft: 8, padding: '1px 8px',
    borderRadius: 99, fontSize: 11, fontWeight: 600, color, background: bg, border: `1px solid ${color}`,
  })
  const row: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8 }
  const tag: React.CSSProperties = {
    background: 'var(--blue)', color: 'white', borderRadius: 6,
    padding: '3px 9px', fontWeight: 700, fontSize: 12, flexShrink: 0, marginTop: 1,
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '0 0 40px' }}>
      <HelpButton title="Guida Alembic" sections={[
        {
          heading: "Cos'è Alembic",
          content: "Alembic è un sistema di trading algoritmico guidato da LLM. L'intelligenza artificiale lavora offline come motore di ricerca: produce segnali di sentiment che vengono letti dal motore di esecuzione in modo asincrono. Nessun LLM viene chiamato in tempo reale durante un ordine.",
        },
        {
          heading: "Le strategie in breve",
          content: "**S1 (50%)**: momentum multi-lookback su ETF/azionario — usa solo prezzi storici, nessun LLM.\n\n**S4 (10%)**: news sentiment via LLM ensemble — legge segnali pre-calcolati da Redis, filtra con EMA e regime.\n\n**S2**: disabilitata (OOS Sharpe −0.55, tutti i gate falliti).\n\n**S3**: R&D sleeve, non in produzione.",
        },
        {
          heading: "Dove guardare",
          content: "• **Overview** — P&L live, segnali recenti, IC\n• **Signals** — segnali LLM per ticker\n• **Trades** → Analytics — P&L per regime/simbolo/durata\n• **Performance** → Weekly Report — costi, cash drag, infrastruttura\n• **Strategies** — gate di validazione OOS\n• **Auto-Improve** — feedback loop e counterfactual\n• **LLM** — pesi ensemble e ICIR per modello",
        },
      ]} />

      <h1 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Guida Alembic</h1>

      {/* ── 1. COS'È ALEMBIC ── */}
      <div style={card}>
        <h2 style={h2}>🧭 Cos'è Alembic e come funziona</h2>
        <p style={p}>
          Alembic è un sistema di trading algoritmico che usa LLM (Large Language Models) come motore di ricerca e generazione di segnali, mai come esecutore in tempo reale. Il principio architetturale fondamentale è: <strong>gli LLM lavorano offline, l'execution engine legge segnali pre-calcolati</strong>.
        </p>
        <div style={mono}>{`[News: GDELT / MarketAux / Alpaca]
         ↓  ogni 15 min (ore di mercato)
[LLM Ensemble Worker] ──→ Redis: signal:{symbol}:sentiment
         ↑ offline, asincrono
         
[Portfolio Scheduler] ──→ legge segnali da Redis (ogni ora)
         ↓
[Risk Constraints] ──→ [Alpaca Paper/Live API]`}</div>
        <p style={p}>
          Questo design garantisce che un eventuale timeout o rallentamento del modello LLM non blocchi mai l'esecuzione di un ordine. Il motore di esecuzione ha sempre un segnale già pronto in Redis.
        </p>
      </div>

      {/* ── 2. STRATEGIE ── */}
      <div style={card}>
        <h2 style={h2}>📊 Le Strategie</h2>
        <p style={{ ...p, marginBottom: 16 }}>
          Alembic usa un portfolio multi-strategia con allocazioni fisse configurate in <code>config/strategies.yaml</code>. Le strategie producono <em>pesi sleeve-local</em> (frazioni del proprio capitale), poi l'orchestratore li scala per l'allocazione percentuale.
        </p>

        {/* S1 */}
        <div style={inner}>
          <div style={row}>
            <div style={tag}>S1</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                Multi-Lookback Relative Momentum
                <span style={badge('#15803d', '#dcfce7')}>LIVE — 50% portafoglio</span>
              </div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Teoria</h3>
              <p style={p}>
                Il momentum è uno degli anomalie di mercato più documentate in finanza (Jegadeesh & Titman, 1993; Moskowitz et al., 2012). L'idea: le attività che hanno performato bene negli ultimi mesi tendono a continuare a farlo nel breve termine, per ragioni comportamentali (under-reaction, herding) e strutturali (trend-following istituzionale).
              </p>
              <p style={p}>
                S1 usa <strong>quattro finestre di lookback</strong> (1M=21d, 3M=63d, 6M=126d, 12M=252d) per catturare il momentum a diversi orizzonti temporali. Il ritorno grezzo viene normalizzato per la volatilità (vol-scaling) per rendere comparabili asset con volatilità diverse. Il <strong>z-score cross-sezionale</strong> classifica ogni asset rispetto ai peer alla stessa data — il segnale non è il livello assoluto ma il ranking relativo.
              </p>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come genera il segnale</h3>
              <div style={mono}>{`Dati input: prezzi OHLCV storici (ETF + azionario, ~15 simboli)

Per ogni lookback lb ∈ {21, 63, 126, 252} giorni:
    raw_lb     = price / price.shift(lb) - 1          # ritorno grezzo
    norm_lb    = raw_lb / rolling_vol(63d)             # normalizzato per vol

signal_raw = weighted_sum(norm_lb, [1×, e×, e²×, e³×] norm.)  # peso esponenziale
signal     = z_score(signal_raw, cross-sectional)              # ranking vs peer

raw_weight ∝ signal × (target_vol=15% / realised_vol)   # sizing inverso-vol
sleeve_weight = normalise(raw_weight, long-only, sum≤1)`}</div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come interviene sul portafoglio</h3>
              <p style={p}>
                L'orchestratore moltiplica i pesi sleeve S1 per 0.50 (allocazione). Un asset con peso sleeve 0.40 occupa il 20% del portafoglio totale. S1 è <strong>puro price-momentum</strong>: nessun filtro LLM, nessun regime multiplier. Il rischio è il momentum crash (sharp reversal in bear markets).
              </p>
            </div>
          </div>
        </div>

        {/* S4 */}
        <div style={inner}>
          <div style={row}>
            <div style={tag}>S4</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                News-Driven Tactical (LLM Sentiment)
                <span style={badge('#1d4ed8', '#dbeafe')}>PAPER — 10% portafoglio</span>
              </div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Teoria</h3>
              <p style={p}>
                Le notizie aziendali generano price discovery: il mercato reagisce con ritardo agli eventi positivi/negativi, specialmente per small/mid cap. Il sentiment estratto da notizie è un segnale predittivo del rendimento a breve termine (Tetlock, 2007; Loughran & McDonald, 2011). L'uso di LLM permette di estrarre sentiment più preciso rispetto a dizionari tradizionali, catturando contesto e sfumature.
              </p>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come genera il segnale</h3>
              <div style={mono}>{`Fonti news (ogni 15 min, 14:00-21:00 UTC Lun-Ven):
  ├── GDELT GKG         — eventi geopolitici globali
  ├── MarketAux         — sentiment pre-calcolato, news finanziarie
  └── Alpaca News       — news in tempo reale su ticker specifici

LLM Ensemble (4 modelli in parallelo via Ollama cloud):
  kimi-k2.6   → { polarity ∈ [-1,+1], confidence ∈ [0,1] }
  qwen3.5     → { polarity, confidence }
  deepseek    → { polarity, confidence }      score_i = polarity_i × confidence_i
  glm-5.1     → { polarity, confidence }

Aggregazione:
  if std(score_i) > 0.30 → scarta ensemble, usa FinBERT locale
  else: score = Σ(weight_i × score_i)   # pesi da LOO-ICIR settimanale

Redis: SET signal:{symbol}:sentiment = { score, ts, model_id }`}</div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come S4 interviene sul segnale</h3>
              <p style={p}>
                S4 applica <strong>tre filtri sequenziali</strong> prima di generare un ordine. Ogni filtro può bloccare il trade:
              </p>
              <div style={mono}>{`Ogni ciclo portfolio (ogni ora):
  S4.compute_target_weights(signals):
  
  [1] Filtro score: score < 0.30 → SKIP (segnale troppo neutro)
  [2] Filtro EMA20: price < EMA20 → SKIP (ticker in downtrend)
  [3] Filtro staleness: signal_age > 30 min → SKIP (notizia obsoleta)
  
  Se PASS tutti e tre:
    sleeve_weight = base_size (0.02) × regime_multiplier
  
  regime_multiplier:
    bull      → ×1.0 (full size)
    sideways  → ×0.7
    bear      → ×0.4
    high_vol  → ×0.2 (quasi flat)
    
Portfolio orchestratore:
  merged[sym] += S4_weight[sym] × 0.10`}</div>
              <p style={p}>
                Il <strong>regime multiplier</strong> è il meccanismo più importante: in un mercato bear, anche un segnale LLM fortemente positivo genera solo il 40% della posizione normale. Questo protegge dal bias di conferma dell'LLM in mercati avversi.
              </p>
            </div>
          </div>
        </div>

        {/* S2 */}
        <div style={{ ...inner, opacity: 0.65 }}>
          <div style={row}>
            <div style={{ ...tag, background: '#475569' }}>S2</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                Volatility Risk Premium (VRP)
                <span style={badge('#991b1b', '#fee2e2')}>DISABILITATA — 0% portafoglio</span>
              </div>
              <p style={p}>
                <strong>Teoria:</strong> La volatilità implicita (VIX) eccede sistematicamente la volatilità realizzata di 3–4 punti annualizzati. Vendere questa "assicurazione" (short put su SPY/QQQ) cattura un premio strutturale. L'implementazione attuale è un proxy semplificato (long SPY overnight quando VIX/realised_vol_20d {">"} 0.20) — non usa opzioni reali.
              </p>
              <p style={{ ...p, color: '#ef4444' }}>
                Stato: OOS Sharpe −0.55, tutti i gate (1–4) falliti nel backtest. Non attiva in paper o live. Per riattivarla serve superare tutti i gate — modificare <code>config/strategies.yaml</code> richiede override esplicito.
              </p>
            </div>
          </div>
        </div>

        {/* S3 */}
        <div style={{ ...inner, opacity: 0.65 }}>
          <div style={row}>
            <div style={{ ...tag, background: '#92400e' }}>S3</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                Cross-Sectional Momentum
                <span style={badge('#a16207', '#fef9c3')}>R&D — 0% portafoglio</span>
              </div>
              <p style={p}>
                <strong>Teoria:</strong> Il momentum residuale (Fama-French factor-neutral) su azionario US: comprare il quintile top per rendimento 12-1 mesi, shortare il quintile bottom. Universo: S&P 500 filtrato per liquidità. Rebalancing mensile.
              </p>
              <p style={{ ...p, color: '#f59e0b' }}>
                Stato: Gate 3 (IC OOS {"<"} 0.05) e Gate 5 (drag da costi eccessivo) falliti. Possibile lookahead nel sizing. Non attiva.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. FLUSSO COMPLETO SEGNALE ── */}
      <div style={card}>
        <h2 style={h2}>🔄 Flusso Completo di un Segnale (S4)</h2>
        <p style={p}>
          Questo è il percorso di un'articolo di notizie dall'ingestion fino all'ordine su Alpaca. Il flusso S1 è separato (usa solo prezzi, nessuna news).
        </p>
        <div style={mono}>{`STEP 1 — INGESTION (ogni 15 min, 14:00-21:00 UTC, Lun-Ven)
  news-ingestion task (Celery beat) chiama:
    GDELTConnector.fetch()      → articoli geopolitici
    MarketAuxConnector.fetch()  → news finanziarie con ticker
    AlpacaNewsConnector.fetch() → news real-time Alpaca
  
  → INSERT INTO news_log (ticker, headline, source, fetched_at)
  → PUSH news_id in Redis queue per sentiment worker

STEP 2 — LLM ENSEMBLE (worker asyncio)
  Per ogni news in coda:
    Prompt DK-CoT: "Act as buy-side analyst. Reason step-by-step
    over cash flows, competition, profitability. Output JSON:
    { polarity: float, confidence: float, reasoning: string }"
    
    4 modelli in parallelo → [score_1, score_2, score_3, score_4]
    
    if std(scores) > 0.30:
      → FinBERT locale (fallback deterministico)
      confidence = 1 - H(softmax) / log(3)   # entropic confidence
    else:
      → score = Σ(weight_i × polarity_i × confidence_i)
      
    → UPDATE sentiment_signals SET score=..., model_id=...
    → SET Redis: signal:{ticker}:sentiment = {score, ts, model_id}

STEP 3 — PORTFOLIO CYCLE (ogni ora, via Celery beat)
  PortfolioOrchestrator.run_cycle():
  
  S1.compute_target_weights(prices):   # nessun LLM, solo prezzi
    → {AAPL: 0.35, NVDA: 0.22, ...}   # pesi sleeve-local
    
  S4.compute_target_weights(signals):  # legge da Redis
    Per ogni ticker nel watchlist:
      score = Redis.GET signal:{ticker}:sentiment
      if score < 0.30 → skip
      if price < EMA20 → skip
      if now - signal_ts > 30min → skip
      sleeve_weight = 0.02 × regime_multiplier
    → {MSFT: 0.02, TSLA: 0.015, ...}  # pesi sleeve-local

STEP 4 — MERGE E RISK CONSTRAINTS
  merged = {}
  merged[sym] += S1_weight[sym] × 0.50   # S1 sleeve × allocazione
  merged[sym] += S4_weight[sym] × 0.10   # S4 sleeve × allocazione
  
  Risk constraints (iterative, max 10 pass):
    ├── Max per-asset: 10% NAV → scala BUY in eccesso
    ├── Max total exposure: 95% NAV
    ├── Max sector: 25% NAV
    └── HHI concentration check
    
  Vol overlay: qty × (target_vol=10% / estimated_portfolio_vol)
               clamped [0.5×, 2.0×]

STEP 5 — ORDINI
  delta_qty = target_qty - current_qty
  if delta_qty > 0: BUY notional=delta_qty × price (Alpaca paper)
  if delta_qty < 0: SELL (se stop-loss o riduzione posizione)
  
  → INSERT INTO trades (symbol, entry_price, qty, entry_notional, ...)
  → Alpaca API: market order (paper account)`}</div>

        <h3 style={h3}>Flusso S1 (separato)</h3>
        <div style={mono}>{`STEP 1 — Dati di prezzo (fetch daily OHLCV, storico)
STEP 2 — S1.compute_target_weights(prices):
    signal = z_score(Σ norm_momentum_lookbacks)
    weight = signal × (15% / vol), long-only, normalised
STEP 3 — Merge in orchestratore (× 0.50)
STEP 4 — Risk constraints + vol overlay
STEP 5 — Ordini Alpaca`}</div>
      </div>

      {/* ── 4. COME LE STRATEGIE INTERVENGONO ── */}
      <div style={card}>
        <h2 style={h2}>⚙️ Come le Strategie Intervengono sul Segnale</h2>

        <h3 style={h3}>Interazioni e filtri applicati</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Filtro / Intervento', 'S1', 'S4', 'Dove'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '6px 10px', color: '#64748b', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                ['Score threshold (≥0.30)', '—', '✓ blocca entry', 'S4.compute_target_weights()'],
                ['EMA20 trend filter', '—', '✓ blocca entry in downtrend', 'S4.compute_target_weights()'],
                ['Signal staleness (≤30 min)', '—', '✓ scarta segnali vecchi', 'S4.compute_target_weights()'],
                ['Regime multiplier (×0.2–1.0)', '—', '✓ scala la size', 'S4 + RegimeDetector'],
                ['Vol-normalisation', '✓ per lookback', '—', 'S1 signal compute'],
                ['Cross-sectional z-score', '✓ ranking vs peer', '—', 'S1 signal compute'],
                ['Inverse-vol sizing', '✓ target 15% vol', '—', 'S1 sizing.py'],
                ['Allocazione sleeve (50% / 10%)', '✓', '✓', 'PortfolioOrchestrator'],
                ['Max per-asset 10% NAV', '✓', '✓', 'PortfolioConstraints'],
                ['Max exposure 95% NAV', '✓', '✓', 'PortfolioConstraints'],
                ['Max sector 25% NAV', '✓', '✓', 'PortfolioConstraints'],
                ['Vol overlay (target 10% portafoglio)', '✓', '✓', 'PortfolioVolTargeter'],
                ['Kill-switch (blocca tutto)', '✓', '✓', 'ExecutionWorker pre-check'],
                ['Drawdown cap portafoglio (10%)', '✓', '✓', 'ExecutionWorker pre-check'],
                ['Feedback: threshold adattivo', '—', '✓ alza soglia score', 'LossFeedbackWorker'],
              ].map(([filtro, s1, s4, dove]) => (
                <tr key={filtro as string} style={{ borderBottom: '1px solid #1e293b' }}>
                  <td style={{ padding: '6px 10px', color: '#94a3b8' }}>{filtro}</td>
                  <td style={{ padding: '6px 10px', color: s1 === '—' ? '#334155' : '#22c55e' }}>{s1}</td>
                  <td style={{ padding: '6px 10px', color: s4 === '—' ? '#334155' : '#60a5fa' }}>{s4}</td>
                  <td style={{ padding: '6px 10px', color: '#64748b', fontSize: 11 }}>{dove}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 style={h3}>Regime multiplier: effetto pratico su S4</h3>
        <div style={mono}>{`Regime   Multiplier   Esempio: segnale MSFT score=0.45
─────────────────────────────────────────────────────
bull      ×1.0        sleeve_weight = 0.02 × 1.0 = 2.0% → ordine $200 su $10k portafoglio
sideways  ×0.7        sleeve_weight = 0.02 × 0.7 = 1.4% → ordine $140
bear      ×0.4        sleeve_weight = 0.02 × 0.4 = 0.8% → ordine $80
high_vol  ×0.2        sleeve_weight = 0.02 × 0.2 = 0.4% → ordine $40

Dopo moltiplicazione S4 allocation (10%):
  portfolio_weight = sleeve_weight × 0.10
  bull: 2.0% × 0.10 = 0.20% del portafoglio in MSFT da S4`}</div>

        <h3 style={h3}>Feedback loop (Phase B): threshold adattivo</h3>
        <p style={p}>
          Se si verificano N perdite consecutive o P&L rolling negativo, il <code>LossFeedbackWorker</code> alza automaticamente il <code>ENTRY_THRESHOLD</code> oltre 0.30 (baseline). Questo riduce il numero di segnali che passano il filtro score. Il threshold si abbassa di nuovo solo dopo un numero configurabile di win consecutive.
        </p>
      </div>

      {/* ── 5. PARAMETRI DI RISCHIO ── */}
      <div style={card}>
        <h2 style={h2}>⚠️ Parametri di Rischio</h2>
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {['Parametro', 'Default', 'Descrizione'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '6px 10px', color: '#64748b', fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              ['ENTRY_THRESHOLD (S4)', '0.30', 'Score minimo LLM per triggherare BUY. Alzato dal feedback loop in caso di perdite.'],
              ['Stop-loss S4', '5% (tier A/B: 2%)', 'Chiude posizione se prezzo scende a entry × (1 - stop_loss_pct). Tier basato su notional.'],
              ['Max posizione per asset', '10% NAV', 'Nessun singolo ticker può superare il 10% del portafoglio.'],
              ['Max esposizione totale', '95% NAV', 'Il 5% rimane sempre liquido come buffer.'],
              ['Max esposizione settoriale', '25% NAV', 'Evita concentrazione su singolo settore.'],
              ['Drawdown cap portafoglio', '10%', 'Se portafoglio scende del 10% dal picco → kill-switch automatico.'],
              ['Regime multiplier min', '×0.2 (high_vol)', 'In alta volatilità le posizioni S4 si riducono dell\'80%.'],
              ['Vol target portafoglio', '10% annualizzato', 'Il vol overlay scala tutte le qty per puntare a questo livello.'],
              ['Max signal age S4', '30 min', 'Segnali più vecchi di 30 minuti vengono ignorati (news stale).'],
              ['Allocazione S1', '50% NAV', 'Sleeve momentum. Unica strategia con gate completi superati.'],
              ['Allocazione S4', '10% NAV', 'Sleeve news sentiment. Cappato al 10% fino a gate dedicati.'],
            ].map(([param, def_, desc]) => (
              <tr key={param as string} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={{ padding: '6px 10px', color: '#94a3b8', fontFamily: 'monospace', fontSize: 11 }}>{param}</td>
                <td style={{ padding: '6px 10px', color: 'white', fontWeight: 600, whiteSpace: 'nowrap' }}>{def_}</td>
                <td style={{ padding: '6px 10px', color: '#64748b' }}>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── 6. GATE DI VALIDAZIONE ── */}
      <div style={card}>
        <h2 style={h2}>✅ Gate di Validazione Strategie</h2>
        <p style={p}>
          Ogni strategia deve superare 5 gate prima di essere promossa al portfolio live. Il fallimento di un gate demote la strategia al sleeve di R&D (non esegue ordini reali).
        </p>
        {[
          { gate: 'Gate 1', name: 'Significance', desc: 'OOS Sharpe > 0.5. La strategia batte il caso?' },
          { gate: 'Gate 2', name: 'Walk-Forward OOS', desc: 'OOS Sharpe > 0.8 × IS Sharpe. Il rendimento regge out-of-sample?' },
          { gate: 'Gate 3', name: 'Robustness', desc: 'IC OOS > 0.05 su ≥3 finestre walk-forward. Il segnale è generalizzabile?' },
          { gate: 'Gate 4', name: 'Sensitivity', desc: 'Sharpe stabile con ±20% variazione parametri (CV < 0.5). Nessun overfitting.' },
          { gate: 'Gate 5', name: 'Stress Test', desc: 'Non collassa in 2008, COVID 2020, 2022 rate shock. Il cost drag non supera il gross P&L.' },
        ].map(({ gate, name, desc }) => (
          <div key={gate} style={{ ...inner, display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 6 }}>
            <div style={{ background: '#1d4ed8', color: 'white', borderRadius: 6, padding: '2px 8px', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{gate}</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{name}</div>
              <div style={{ color: '#64748b', fontSize: 12, marginTop: 2 }}>{desc}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── 7. METRICHE CHIAVE ── */}
      <div style={card}>
        <h2 style={h2}>📈 Metriche Chiave</h2>
        {[
          { name: 'IC (Information Coefficient)', desc: 'Correlazione di Spearman tra predizione LLM e rendimento reale. > 0.05 = segnale utile, < 0 = anti-predittivo.' },
          { name: 'ICIR (IC Information Ratio)', desc: 'IC / Std(IC). > 0.3 = segnale consistente nel tempo. Il LOO-ICIR è la versione purificata che misura il contributo marginale di ogni modello.' },
          { name: 'Polarity', desc: 'Direzione del segnale LLM: +1 = fortemente bullish, −1 = fortemente bearish.' },
          { name: 'Confidence', desc: 'Certezza del modello LLM. Per FinBERT: entropic confidence = 1 − H(softmax) / log(3).' },
          { name: 'Score finale S4', desc: 'polarity × confidence. Alta polarità + bassa confidenza → score piccolo. Penalizza l\'incertezza.' },
          { name: 'OOS Sharpe', desc: 'Sharpe ratio out-of-sample. > 0.5 = Gate 1 superato. > 1.0 = eccellente.' },
          { name: 'Cost drag', desc: 'Frazione di P&L lordo consumata da spread + market impact. Annualizzato = cost_drag_pct × 252.' },
          { name: 'Cash drag', desc: 'Opportunità cost del capitale non deployato: cash_pct × 4.5% (T-bill proxy) per anno.' },
          { name: 'Regime multiplier', desc: 'Coefficiente (0.2–1.0) che scala le posizioni S4 in base al regime di mercato rilevato da RegimeDetector.' },
          { name: 'HHI', desc: 'Herfindahl-Hirschman Index: misura la concentrazione del portafoglio. Alto HHI = pochi asset dominanti.' },
        ].map(({ name, desc }) => (
          <div key={name} style={{ ...inner, marginBottom: 6 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{name}</div>
            <div style={{ color: '#64748b', fontSize: 12 }}>{desc}</div>
          </div>
        ))}
      </div>

      {/* ── 8. AUTO-IMPROVE ── */}
      <div style={card}>
        <h2 style={h2}>🔧 Auto-Improve (Phase A / B / C)</h2>
        <p style={p}>
          Il sistema include tre livelli di auto-miglioramento basati su dati reali. Si trovano nella pagina <strong>Auto-Improve</strong> e nel tab <strong>Analytics</strong> della pagina Trades.
        </p>

        <h3 style={h3}>Phase A — Trade Analytics (pagina Trades → tab Analytics)</h3>
        <ul style={ul}>
          <li><strong>P&L per simbolo</strong> — quali ticker generano alpha, quali distruggono valore</li>
          <li><strong>P&L per regime</strong> — la strategia funziona meglio in bull o sideways?</li>
          <li><strong>P&L per score bucket</strong> — segnali con score alto → P&L alto? Se no, il segnale LLM non ha edge</li>
          <li><strong>P&L per durata holding</strong> — finestra ottimale (trade troppo brevi soffrono spread, troppo lunghi rischiano staleness)</li>
        </ul>

        <h3 style={h3}>Phase B — Loss Feedback Loop (pagina Auto-Improve)</h3>
        <p style={p}>
          N perdite consecutive o P&L rolling negativo → <code>LossFeedbackWorker</code> alza <code>ENTRY_THRESHOLD</code> e riduce <code>regime_scale</code>. Visibile nel Weekly Report (tab Performance → Weekly Report → Feedback Loop).
        </p>

        <h3 style={h3}>Phase C — Counterfactual Analysis (pagina Auto-Improve)</h3>
        <p style={p}>
          Per ogni trade saltato (<code>SKIP_EMA</code>, <code>SKIP_CAP</code>, <code>SKIP_POSITION</code>), viene calcolato il rendimento che avrebbe generato se fosse stato eseguito. Permette di calibrare i filtri: se SKIP_EMA scarta sistematicamente trade profittevoli, il filtro è troppo conservativo.
        </p>
      </div>

      {/* ── 9. MODALITÀ OPERATIVE ── */}
      <div style={card}>
        <h2 style={h2}>⚙️ Modalità Operative</h2>
        {[
          { mode: 'Backtest', badge: '#475569', badgeBg: '#f1f5f9', desc: 'Simulazione su dati storici. Nessun ordine reale o simulato. Pagina Backtest.' },
          { mode: 'Paper', badge: '#1d4ed8', badgeBg: '#dbeafe', desc: 'Ordini simulati su Alpaca paper account. Denaro fittizio. Stato attuale del sistema.' },
          { mode: 'Live', badge: '#15803d', badgeBg: '#dcfce7', desc: 'Ordini reali su Alpaca live. Solo dopo completamento validazione paper (90 giorni + go-live checklist).' },
        ].map(({ mode, badge: bc, badgeBg, desc }) => (
          <div key={mode} style={{ ...inner, display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 6 }}>
            <div style={badge(bc, badgeBg)}>{mode}</div>
            <div style={{ color: '#94a3b8', fontSize: 13 }}>{desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build completes without TypeScript or JSX errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Docs.tsx
git commit -m "docs(frontend): complete rewrite of Docs page — strategy theory, signal flow, intervention table"
```

---

## Self-Review

**Spec coverage:**
- [x] Spiegazione strategie con cenni teorici (S1: Jegadeesh & Titman, S4: Tetlock — Task 4)
- [x] Flusso completo segnale S4 (news → LLM → Redis → filtri → ordine — Task 4)
- [x] Flusso S1 (prices → momentum → weights — Task 4)
- [x] Come le strategie intervengono (tabella filtri + regime multiplier — Task 4)
- [x] S2 disabilitata corretta (0%, OOS −0.55 — Task 4)
- [x] S4 allocazione corretta (10% non 30% — Task 4)
- [x] Report costi anche su web (struttura dati → Redis → API — Tasks 1, 2)
- [x] Frontend Weekly Report tab con tutte le sezioni costi (Task 3)

**Placeholder scan:** nessun TBD o placeholder trovato.

**Type consistency:** `WeeklyReport` definita in Task 3 Step 1, usata nel componente `WeeklyReportTab` in Task 3 Step 3 con `import('@/api/performance').WeeklyReport` — consistente.

**Gap trovato e risolto:** La `import json` nel backend di performance.py — già presente (`from collections import defaultdict` suggerisce file già importa json, ma aggiunto reminder di verificare nel Task 2 Step 2).
