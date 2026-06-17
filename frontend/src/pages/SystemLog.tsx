import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime } from '@/utils/format'
import { fetchScheduler, fetchActivity, fetchPeadSignals } from '@/api/system'
import { HelpButton } from '@/components/shared/HelpButton'

type Tab = 'scheduler' | 'activity' | 'pead'

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  portfolio_cycle: { label: 'Cycle',     color: 'var(--blue)' },
  sentiment_run:   { label: 'Sentiment', color: '#8b5cf6' },
  ingestion:       { label: 'Ingestion', color: '#059669' },
  trade_decision:  { label: 'Trade',     color: '#f59e0b' },
}

export default function SystemLog() {
  const [tab, setTab] = useState<Tab>('scheduler')

  const { data: scheduler = [], isLoading: schLoading } = useQuery({
    queryKey: ['scheduler'],
    queryFn: fetchScheduler,
    refetchInterval: 60_000,
  })

  const { data: activity = [], isLoading: actLoading } = useQuery({
    queryKey: ['activity'],
    queryFn: () => fetchActivity(80),
    refetchInterval: 30_000,
    enabled: tab === 'activity',
  })

  const { data: pead = [], isLoading: peadLoading } = useQuery({
    queryKey: ['pead-signals'],
    queryFn: fetchPeadSignals,
    refetchInterval: 300_000,
    enabled: tab === 'pead',
  })

  const tabStyle = (t: Tab) => ({
    padding: '8px 20px', cursor: 'pointer',
    borderBottom: tab === t ? '2px solid var(--blue)' : '2px solid transparent',
    color: tab === t ? 'var(--blue)' : 'var(--text-muted)',
    fontWeight: tab === t ? 600 : 400,
    background: 'none', borderRadius: 0,
  })

  const now = new Date()
  const minutesAgo = (iso: string | null) => {
    if (!iso) return null
    const diff = Math.round((now.getTime() - new Date(iso).getTime()) / 60000)
    if (diff < 60) return `${diff} min fa`
    if (diff < 1440) return `${Math.round(diff / 60)}h fa`
    return `${Math.round(diff / 1440)}g fa`
  }

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 700 }}>System</h2>
      <p style={{ margin: '0 0 20px', color: 'var(--text-muted)', fontSize: 14 }}>
        Scheduler status, activity log and PEAD signals.
      </p>

      <HelpButton title="System — Guida" sections={[
        {
          heading: "Scheduler",
          content: "Mostra tutti i worker Celery schedulati con:\n- **Schedule**: quando gira (cron human-readable)\n- **Last Run**: ultima volta che il worker ha prodotto dati (da DB)\n\nSe 'Last Run' è molto vecchio o assente, il worker non sta girando correttamente.",
        },
        {
          heading: "Activity Log",
          content: "Cronologia degli eventi di sistema delle ultime 24 ore:\n- **Cycle**: cicli portfolio eseguiti con numero di ordini\n- **Sentiment**: run del worker LLM con numero di segnali generati\n- **Ingestion**: batch di articoli ingestiti per fonte\n- **Trade**: decisioni di trading prese dall'orchestratore\n\nGli eventi sono ordinati dal più recente.",
        },
        {
          heading: "PEAD Signals",
          content: "Segnali attivi della strategia S7 (Post-Earnings Announcement Drift):\n- Il worker analizza i filing 8-K di SEC EDGAR\n- L'LLM classifica se c'è un earnings beat (sorpresa positiva)\n- Per ogni beat con confidence ≥ 70%, viene creato un segnale con hold di 20 giorni\n\nQuesta tabella è vuota fino al primo ciclo di mercato con earnings beat classificati.",
        },
      ]} />

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        <button style={tabStyle('scheduler')} onClick={() => setTab('scheduler')}>Scheduler</button>
        <button style={tabStyle('activity')} onClick={() => setTab('activity')}>Activity Log</button>
        <button style={tabStyle('pead')} onClick={() => setTab('pead')}>PEAD Signals</button>
      </div>

      {/* ── SCHEDULER ───────────────────────────────────────────── */}
      {tab === 'scheduler' && (
        <div className="card" style={{ padding: 0 }}>
          {schLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
          <table>
            <thead>
              <tr>
                <th>Worker</th>
                <th>Descrizione</th>
                <th>Schedule</th>
                <th>Last Run</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {scheduler.map((t) => {
                const ago = minutesAgo(t.last_run)
                const isStale = !t.last_run || (now.getTime() - new Date(t.last_run).getTime()) > 3 * 3600 * 1000
                return (
                  <tr key={t.task}>
                    <td><code style={{ fontSize: 12 }}>{t.task}</code></td>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{t.description}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{t.schedule}</td>
                    <td style={{ fontSize: 12 }}>
                      {t.last_run ? (
                        <span title={fmtDateTime(t.last_run)}>{ago}</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                    <td>
                      {t.last_run
                        ? <span className={`badge ${isStale ? 'badge-yellow' : 'badge-green'}`}>{isStale ? 'Stale' : 'OK'}</span>
                        : <span className="badge badge-grey">No data</span>
                      }
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── ACTIVITY LOG ────────────────────────────────────────── */}
      {tab === 'activity' && (
        <div className="card" style={{ padding: 0 }}>
          {actLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
          <table>
            <thead>
              <tr><th>Time</th><th>Type</th><th>Event</th><th>Detail</th></tr>
            </thead>
            <tbody>
              {activity.map((e, i) => {
                const meta = TYPE_LABELS[e.type] ?? { label: e.type, color: 'var(--text-muted)' }
                return (
                  <tr key={i}>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{fmtDateTime(e.time)}</td>
                    <td>
                      <span style={{
                        fontSize: 11, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
                        background: meta.color + '22', color: meta.color,
                      }}>{meta.label}</span>
                    </td>
                    <td style={{ fontSize: 13 }}>{e.summary}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {e.detail ?? '—'}
                    </td>
                  </tr>
                )
              })}
              {activity.length === 0 && !actLoading && (
                <tr><td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24 }}>
                  No activity in the last 24 hours
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ── PEAD SIGNALS ────────────────────────────────────────── */}
      {tab === 'pead' && (
        <div>
          <div style={{ marginBottom: 16, padding: '10px 14px', background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8, fontSize: 13 }}>
            <strong>S7 PEAD</strong> — Post-Earnings Announcement Drift. Il worker classifica i filing 8-K di SEC EDGAR ogni 30 minuti durante il mercato. I segnali rimangono attivi per 20 giorni dall'earnings beat.
          </div>

          <div className="card" style={{ padding: 0 }}>
            {peadLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
            <table>
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Direction</th>
                  <th>Surprise %</th>
                  <th>Confidence</th>
                  <th>Detected</th>
                  <th>Hold Until</th>
                  <th>Days Left</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {pead.map((s) => (
                  <tr key={s.filing_id}>
                    <td><strong>{s.symbol}</strong></td>
                    <td>
                      <span className={`badge ${s.direction === 'beat' ? 'badge-green' : 'badge-red'}`}>
                        {s.direction === 'beat' ? '▲ beat' : '▼ miss'}
                      </span>
                    </td>
                    <td>{s.surprise_pct > 0 ? '+' : ''}{(s.surprise_pct * 100).toFixed(1)}%</td>
                    <td>{(s.confidence * 100).toFixed(0)}%</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{fmtDateTime(s.detected_at)}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{fmtDateTime(s.hold_until)}</td>
                    <td>
                      <span style={{ fontWeight: 600, color: s.days_remaining > 10 ? 'var(--green)' : 'var(--yellow, #f59e0b)' }}>
                        {s.days_remaining}d
                      </span>
                    </td>
                    <td>
                      {s.is_active
                        ? <span className="badge badge-green">Active</span>
                        : <span className="badge badge-grey">Expired</span>
                      }
                    </td>
                  </tr>
                ))}
                {pead.length === 0 && !peadLoading && (
                  <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24 }}>
                    No PEAD signals yet — worker will populate this once 8-K filings with earnings beats are processed.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
