import { useQuery } from '@tanstack/react-query'
import { fmtDateTime } from '@/utils/format'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { fetchSignals } from '@/api/signals'
import { fetchPositions } from '@/api/positions'
import { fetchPnL } from '@/api/performance'
import { fetchReadiness } from '@/api/system'
import { fetchDecisions, fetchFeedbackStatus } from '@/api/trades'
import { fetchQualityMetrics } from '@/api/quality'
import { fetchPortfolioStatus } from '@/api/portfolio'
import { StrategyAuthStatus } from '@/components/shared/StrategyAuthStatus'
import { KPICard } from '@/components/shared/KPICard'
import { DirectionBadge } from '@/components/shared/DirectionBadge'
import { HelpButton } from '@/components/shared/HelpButton'

const SIGNAL_FRESH_HOURS = 4

function pct(v: number | null | undefined, digits = 1): string {
  return v == null ? '—' : `${(Number(v) * 100).toFixed(digits)}%`
}

function n(v: number | null | undefined, digits = 2): string {
  return v == null ? '—' : Number(v).toFixed(digits)
}

function ageText(minutes: number | null | undefined): string {
  if (minutes == null) return '—'
  if (minutes < 60) return `${Math.round(minutes)}m`
  return `${(minutes / 60).toFixed(1)}h`
}

function signalAgeMinutes(iso: string): number {
  return (Date.now() - new Date(iso).getTime()) / 60000
}

function StatusPill({ label, tone = 'neutral' }: { label: string; tone?: 'good' | 'warn' | 'bad' | 'neutral' }) {
  const palette = {
    good: { bg: '#dcfce7', fg: '#15803d' },
    warn: { bg: '#fef9c3', fg: '#a16207' },
    bad: { bg: '#fee2e2', fg: '#b91c1c' },
    neutral: { bg: '#f1f5f9', fg: '#475569' },
  }[tone]
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      padding: '2px 8px',
      borderRadius: 999,
      fontSize: 11,
      fontWeight: 700,
      background: palette.bg,
      color: palette.fg,
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  )
}

function MiniMetric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ minWidth: 130 }}>
      <div style={{ color: 'var(--text-muted)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, marginTop: 3 }}>{value}</div>
      {sub && <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 1 }}>{sub}</div>}
    </div>
  )
}

export default function Overview() {
  const { data: signals = [], dataUpdatedAt: signalsUpdatedAt } = useQuery({ queryKey: ['signals'], queryFn: () => fetchSignals(), refetchInterval: 60000 })
  const { data: positions = [] } = useQuery({ queryKey: ['positions'], queryFn: fetchPositions, refetchInterval: 60000 })
  const { data: pnl } = useQuery({ queryKey: ['pnl'], queryFn: () => fetchPnL('6M'), refetchInterval: 300000 })
  const { data: readiness } = useQuery({ queryKey: ['readiness'], queryFn: fetchReadiness, refetchInterval: 30000 })
  const { data: decisions = [] } = useQuery({ queryKey: ['overview-decisions'], queryFn: () => fetchDecisions(undefined, 40), refetchInterval: 60000 })
  const { data: feedback } = useQuery({ queryKey: ['feedback-status'], queryFn: fetchFeedbackStatus, refetchInterval: 120000 })
  const { data: quality } = useQuery({ queryKey: ['overview-quality', 14], queryFn: () => fetchQualityMetrics(14), refetchInterval: 120000 })
  const { data: portfolio } = useQuery({ queryKey: ['overview-portfolio-status'], queryFn: fetchPortfolioStatus, staleTime: 60000 })

  // #474: gateThreshold counts sentiment signals against the entry gate, which is
  // S4's — read strategies.S4 explicitly rather than a blended/global value.
  const gateThreshold = feedback?.strategies?.S4?.entry_threshold ?? 0.30
  const gateElevated = feedback?.strategies?.S4?.is_elevated ?? false
  const now = signalsUpdatedAt
  const freshSignals = signals.filter((s) => now - new Date(s.generated_at).getTime() <= SIGNAL_FRESH_HOURS * 3600_000)
  const staleSignals = signals.length - freshSignals.length
  const buys = signals.filter((s) => s.score > 0.1).length
  const sells = signals.filter((s) => s.score < -0.1).length
  const holds = signals.length - buys - sells
  const gatePass = freshSignals.filter((s) => s.score >= gateThreshold && !s.fallback_used).length

  const totalUnrealized = positions.reduce((acc, p) => acc + (p.unrealized_pl || 0), 0)
  const deployedNotional = positions.reduce((acc, p) => acc + Math.abs(p.market_value || 0), 0)
  const monthlyPnL = pnl?.monthly ?? []
  const currentMonthPnL = monthlyPnL[monthlyPnL.length - 1]?.pnl ?? 0
  const strategies = portfolio?.strategies ?? []
  const s4 = strategies.find((s) => s.strategy_id.toUpperCase() === 'S4')
  const s1 = strategies.find((s) => s.strategy_id.toUpperCase() === 'S1')
  const pctOrDash = (v: number | undefined) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`)

  const decisionCounts = decisions.reduce<Record<string, number>>((acc, d) => {
    acc[d.decision] = (acc[d.decision] ?? 0) + 1
    return acc
  }, {})
  const recentBuys = decisions.filter((d) => d.decision === 'BUY').length
  const skipThreshold = decisionCounts.SKIP_THRESHOLD ?? 0
  const skipStale = decisionCounts.SKIP_STALE ?? 0
  const skipFallback = decisionCounts.SKIP_FALLBACK ?? 0
  const topSkips = Object.entries(decisionCounts)
    .filter(([key]) => key.startsWith('SKIP'))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)

  const readinessTone =
    readiness == null ? 'neutral'
      : readiness.killswitch_active || !readiness.db_healthy || !readiness.redis_healthy ? 'bad'
        : !readiness.redis_writeable || readiness.stale_signals || readiness.worker_beat_lag ? 'warn'
          : 'good'
  const readinessLabel =
    readinessTone === 'bad' ? 'Blocked'
      : readinessTone === 'warn' ? 'Degraded'
        : readinessTone === 'good' ? 'Ready'
          : 'Unknown'

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Overview</h2>
      <HelpButton title="Overview — Dashboard" sections={[
        {
          heading: "Cos'è questa pagina",
          content: "La dashboard riassume lo stato operativo del sistema: readiness, autorizzazione strategie, P&L, posizioni, soglia segnale, qualità del sentiment e ultime decisioni. I dati principali si aggiornano automaticamente.",
        },
        {
          heading: "Come leggere le KPI cards",
          content: "**Net P&L (month)**: profitto/perdita netto del mese corrente, basato sul P&L giornaliero Alpaca.\n\n**Open positions**: numero di posizioni aperte su Alpaca e ticker coinvolti.\n\n**Unrealized P&L**: P&L fluttuante delle posizioni ancora aperte.\n\n**Active signals**: formato \"XB / YS / ZH\" — X segnali BUY (score > 0.1), Y SELL (score < -0.1), Z HOLD (|score| ≤ 0.1). Non significa necessariamente \"generati oggi\": sono i segnali restituiti dall'endpoint latest.",
        },
        {
          heading: "Operational State",
          content: "Mostra se il sistema è READY/DEGRADED/BLOCKED, l'età dell'ultimo signal e dell'ultimo portfolio cycle, la soglia attiva del feedback gate, e lo stato di autorizzazione di S1/S4. La home non autorizza trading: guarda sempre i badge lifecycle.",
        },
        {
          heading: "Signal Quality e Decisioni",
          content: "Le card Quality riportano near-zero rate, fallback rate e precision ticker dal golden label set. Il Decision Summary mostra cosa è successo negli ultimi cicli: BUY, SKIP_THRESHOLD, SKIP_STALE, SKIP_FALLBACK e altri skip.",
        },
        {
          heading: "Flusso consigliato",
          content: "1. Controlla readiness e lifecycle in Overview\n2. Vai su Signals per signal dettagliati e Decision Log\n3. Verifica Trading per posizioni e ordini\n4. Usa Quality per capire se il problema è ticker/sentiment\n5. Usa Performance e Auto-Improve per P&L, costi e soglie dinamiche",
        },
      ]} />

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <KPICard label="Net P&L (month)" value={`$${currentMonthPnL.toFixed(2)}`} sub="current month" tooltip="Profitto/perdita netto del mese corrente." />
        <KPICard label="Open positions" value={String(positions.length)} sub={positions.map((p) => p.symbol).join(', ') || '—'} tooltip="Numero di posizioni attualmente aperte e relativi ticker." />
        <KPICard label="Unrealized P&L" value={`$${totalUnrealized.toFixed(2)}`} tooltip="Profitto/perdita fluttuante delle posizioni ancora aperte." />
        <KPICard label="Active signals" value={`${buys}B / ${sells}S / ${holds}H`} sub={`${signals.length} latest · ${freshSignals.length} fresh`} tooltip="Latest signals: B (score > 0.1), S (score < -0.1), H (|score| ≤ 0.1). Fresh = entro 4 ore." />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16, marginBottom: 24 }}>
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>Operational State</h3>
            <StatusPill label={readinessLabel} tone={readinessTone} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <MiniMetric label="Last signal" value={ageText(readiness?.last_signal_age_minutes)} sub={readiness?.stale_signals ? 'stale flag' : 'freshness'} />
            <MiniMetric label="Last cycle" value={ageText(readiness?.last_cycle_age_minutes)} sub={readiness?.worker_beat_lag ? 'beat lag' : 'portfolio'} />
            <MiniMetric label="Redis" value={readiness?.redis_healthy ? 'OK' : readiness ? 'Down' : '—'} sub={readiness?.redis_writeable === false ? 'not writeable' : 'writeable'} />
            <MiniMetric label="Database" value={readiness?.db_healthy ? 'OK' : readiness ? 'Down' : '—'} sub={readiness?.killswitch_active ? 'kill-switch active' : 'kill-switch off'} />
          </div>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>Authorization</h3>
          {/* Fed by GET /portfolio/status since 2026-09-02: mode/approved from
              strategy_lifecycle, allocation and promotion_blocked from
              config/strategies.yaml. No snapshot values on this card. */}
          <div style={{ display: 'grid', gap: 10, marginBottom: 12 }}>
            {strategies.length === 0 ? (
              <StrategyAuthStatus />
            ) : (
              strategies.map((s) => (
                <div key={s.strategy_id}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 700 }}>
                    {s.strategy_id} · {pctOrDash(s.allocation_pct)} sleeve
                    {s.approved === false ? ' · not approved' : ''}
                  </div>
                  <StrategyAuthStatus
                    mode={s.mode ?? undefined}
                    promotion_blocked={s.promotion_blocked}
                    live_authorized={s.live_authorized}
                  />
                </div>
              ))
            )}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <MiniMetric label="S4 Allocation" value={pctOrDash(s4?.allocation_pct)} sub="config/strategies.yaml" />
            <MiniMetric label="Live authorized" value={strategies.some((s) => s.live_authorized) ? 'Some' : 'No'} sub="fail-closed display" />
            <MiniMetric label="S1 mode" value={s1?.mode ?? 'unknown'} sub="strategy_lifecycle" />
            <MiniMetric label="Engine" value="Portfolio" sub="authoritative path" />
          </div>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>Signal Gate</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <MiniMetric label="Threshold" value={gateThreshold.toFixed(2)} sub={gateElevated ? 'feedback active (S4)' : 'baseline / current'} />
            <MiniMetric label="Gate pass" value={String(gatePass)} sub="fresh non-FB score ≥ threshold" />
            <MiniMetric label="Stale latest" value={String(staleSignals)} sub={`>${SIGNAL_FRESH_HOURS}h old`} />
            <MiniMetric label="Deployed" value={`$${deployedNotional.toFixed(0)}`} sub="open market value" />
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16, marginBottom: 24 }}>
        <div className="card">
          <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>Signal Quality</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <MiniMetric label="Near-zero" value={pct(quality?.signals.near_zero_rate)} sub={`${quality?.signals.n ?? 0} signals / 14d`} />
            <MiniMetric label="Fallback" value={pct(quality?.signals.fallback_rate)} sub="FinBERT share" />
            <MiniMetric label="Ensemble std" value={n(quality?.signals.mean_ensemble_std, 3)} sub="model divergence" />
            <MiniMetric label="Ticker precision" value={n(quality?.extraction.precision, 2)} sub={`${quality?.extraction.n_labeled ?? 0} labels`} />
          </div>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 14px', fontSize: 14, fontWeight: 700 }}>Decision Summary</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 12 }}>
            <MiniMetric label="BUY" value={String(recentBuys)} sub="last 40 decisions" />
            <MiniMetric label="Skip threshold" value={String(skipThreshold)} sub="score below gate" />
            <MiniMetric label="Skip stale" value={String(skipStale)} sub="signal expired" />
            <MiniMetric label="Skip fallback" value={String(skipFallback)} sub="FinBERT only" />
          </div>
          {topSkips.length > 0 ? (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {topSkips.map(([key, value]) => <StatusPill key={key} label={`${key}: ${value}`} tone="neutral" />)}
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No recent skip decisions.</div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Monthly P&L</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={monthlyPnL}>
              <XAxis dataKey="month" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, 'P&L']} />
              <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
                {monthlyPnL.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Open Positions</h3>
          {positions.length === 0 ? (
            <p style={{ color: 'var(--text-muted)' }}>No open positions</p>
          ) : (
            <table>
              <thead><tr><th>Ticker</th><th>Qty</th><th>P&L</th><th>P&L%</th></tr></thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.symbol}>
                    <td><strong>{p.symbol}</strong></td>
                    <td>{p.qty}</td>
                    <td style={{ color: p.unrealized_pl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                      ${p.unrealized_pl.toFixed(2)}
                    </td>
                    <td>{(p.unrealized_plpc * 100).toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="card">
        <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Latest Signals</h3>
        <table>
          <thead><tr><th>Ticker</th><th>Direction</th><th>Score</th><th>Confidence</th><th>Fallback</th><th>Used</th><th>Model</th><th>Age</th><th>Time</th></tr></thead>
          <tbody>
            {signals.slice(0, 10).map((s, i) => (
              <tr key={i}>
                <td><strong>{s.symbol}</strong></td>
                <td><DirectionBadge score={s.score} /></td>
                <td style={{ color: s.score >= gateThreshold ? 'var(--green)' : 'inherit', fontWeight: s.score >= gateThreshold ? 700 : 400 }}>
                  {s.score.toFixed(3)}{s.score >= gateThreshold ? ' ✓' : ''}
                </td>
                <td>{(s.confidence * 100).toFixed(0)}%</td>
                <td>{s.fallback_used ? <span className="badge badge-yellow">FB</span> : '—'}</td>
                <td>{s.used_in_decision ? <StatusPill label={s.decision_type ?? 'used'} tone={s.decision_type === 'BUY' ? 'good' : 'neutral'} /> : '—'}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{s.model_id}</td>
                <td style={{ color: signalAgeMinutes(s.generated_at) > SIGNAL_FRESH_HOURS * 60 ? 'var(--red)' : 'var(--text-muted)', fontSize: 12 }}>
                  {ageText(signalAgeMinutes(s.generated_at))}
                </td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{fmtDateTime(s.generated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
