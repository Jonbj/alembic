import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { backtestApi } from '@/api/backtest'
import type { BacktestRun } from '@/api/backtest'

function fmt(v: number | null | undefined, decimals = 4): string {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return (Number(v) * 100).toFixed(2) + '%'
}

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: '#1e293b', borderRadius: 8, padding: '14px 18px',
      border: '1px solid #334155', minWidth: 120,
    }}>
      <div style={{ color: '#64748b', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
      <div style={{ color: 'white', fontSize: 22, fontWeight: 700 }}>{value}</div>
      {sub && <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function RunSelector({ runs, selected, onChange }: {
  runs: BacktestRun[]
  selected: string
  onChange: (id: string) => void
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      <span style={{ color: '#94a3b8', fontSize: 13 }}>Run:</span>
      <select
        value={selected}
        onChange={e => onChange(e.target.value)}
        style={{
          background: '#1e293b', color: 'white', border: '1px solid #334155',
          borderRadius: 6, padding: '6px 12px', fontSize: 13, cursor: 'pointer',
        }}
      >
        {runs.map(r => (
          <option key={r.run_id} value={r.run_id}>
            {r.run_id} — {r.scored.toLocaleString()} scored / {r.total.toLocaleString()} total
          </option>
        ))}
      </select>
    </div>
  )
}

export default function Backtest() {
  const { data: runs, isLoading: runsLoading, error: runsError } = useQuery({
    queryKey: ['backtest-runs'],
    queryFn: backtestApi.runs,
    staleTime: 60_000,
  })

  const [selectedRun, setSelectedRun] = useState<string>('')
  const [buckets, setBuckets] = useState(10)
  const [threshold, setThreshold] = useState(0.05)

  // Select first run once loaded
  const runId = selectedRun || (runs && runs.length > 0 ? runs[runs.length - 1].run_id : '')

  const { data: summary } = useQuery({
    queryKey: ['backtest-summary', runId],
    queryFn: () => backtestApi.summary(runId),
    enabled: !!runId,
    staleTime: 60_000,
  })

  const { data: bucketData } = useQuery({
    queryKey: ['backtest-buckets', runId, buckets],
    queryFn: () => backtestApi.bucketAnalysis(runId, buckets),
    enabled: !!runId,
    staleTime: 60_000,
  })

  const { data: modelIc } = useQuery({
    queryKey: ['backtest-model-ic', runId],
    queryFn: () => backtestApi.modelIc(runId),
    enabled: !!runId,
    staleTime: 60_000,
  })

  const { data: symbolIc } = useQuery({
    queryKey: ['backtest-symbol-ic', runId],
    queryFn: () => backtestApi.symbolIc(runId),
    enabled: !!runId,
    staleTime: 60_000,
  })

  const { data: pnl } = useQuery({
    queryKey: ['backtest-pnl', runId, threshold],
    queryFn: () => backtestApi.pnlCurve(runId, threshold),
    enabled: !!runId,
    staleTime: 60_000,
  })

  if (runsLoading) return <div style={{ color: '#94a3b8', padding: 24 }}>Loading backtest runs…</div>
  if (runsError) return <div style={{ color: '#ef4444', padding: 24 }}>Failed to load runs: {String(runsError)}</div>
  if (!runs || runs.length === 0) return <div style={{ color: '#94a3b8', padding: 24 }}>No backtest runs found.</div>

  const currentRun = runs.find(r => r.run_id === runId)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'white' }}>Backtest Analysis</h1>
        <RunSelector
          runs={runs}
          selected={runId}
          onChange={id => setSelectedRun(id)}
        />
      </div>

      {currentRun && (
        <div style={{ color: '#64748b', fontSize: 12 }}>
          {currentRun.symbols} symbols · {currentRun.models} models · {currentRun.started_at?.slice(0, 10)} → {currentRun.ended_at?.slice(0, 10)}
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard
          label="IC (Spearman)"
          value={fmt(summary?.ic)}
          sub="Information Coefficient"
        />
        <KpiCard
          label="ICIR"
          value={fmt(summary?.icir)}
          sub={`${summary?.n_weeks ?? 0} weeks`}
        />
        <KpiCard
          label="Hit Rate"
          value={pct(summary?.hit_rate)}
          sub="Directional accuracy"
        />
        <KpiCard
          label="Avg Long Return"
          value={pct(summary?.avg_long_return)}
          sub="score > 0.05"
        />
        <KpiCard
          label="Avg Short Return"
          value={pct(summary?.avg_short_return)}
          sub="score < -0.05 (as short)"
        />
        <KpiCard
          label="N Scored"
          value={(summary?.n_scored ?? 0).toLocaleString()}
          sub="Signals with forward return"
        />
      </div>

      {/* Bucket Analysis */}
      <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div style={{ color: 'white', fontWeight: 600, fontSize: 15 }}>Score Bucket Analysis</div>
            <div style={{ color: '#64748b', fontSize: 12, marginTop: 2 }}>
              Avg 24h return by score bucket — monotonically increasing = good model
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: '#94a3b8', fontSize: 12 }}>Buckets:</span>
            {[5, 10, 20].map(b => (
              <button
                key={b}
                onClick={() => setBuckets(b)}
                style={{
                  background: buckets === b ? 'var(--blue)' : '#0f172a',
                  color: 'white', border: '1px solid #334155',
                  borderRadius: 4, padding: '3px 10px', fontSize: 12, cursor: 'pointer',
                }}
              >{b}</button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={bucketData ?? []} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="bucket" tick={{ fill: '#94a3b8', fontSize: 11 }} label={{ value: 'Score Bucket', position: 'insideBottom', offset: -2, fill: '#64748b', fontSize: 11 }} />
            <YAxis tickFormatter={v => (Number(v) * 100).toFixed(1) + '%'} tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
              formatter={(v) => [(Number(v) * 100).toFixed(3) + '%']}
            />
            <ReferenceLine y={0} stroke="#475569" />
            <Bar dataKey="avg_return" fill="#3b82f6" name="Avg 24h Return" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* P&L Curve */}
      <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div style={{ color: 'white', fontWeight: 600, fontSize: 15 }}>Cumulative P&L Curve</div>
            <div style={{ color: '#64748b', fontSize: 12, marginTop: 2 }}>Equal-weight, no compounding. Long-Short = combined strategy.</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: '#94a3b8', fontSize: 12 }}>Threshold:</span>
            {[0.02, 0.05, 0.10].map(t => (
              <button
                key={t}
                onClick={() => setThreshold(t)}
                style={{
                  background: threshold === t ? 'var(--blue)' : '#0f172a',
                  color: 'white', border: '1px solid #334155',
                  borderRadius: 4, padding: '3px 10px', fontSize: 12, cursor: 'pointer',
                }}
              >{t}</button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={pnl ?? []} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="day" tick={{ fill: '#94a3b8', fontSize: 10 }} />
            <YAxis tickFormatter={v => (Number(v) * 100).toFixed(1) + '%'} tick={{ fill: '#94a3b8', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
              formatter={(v) => [(Number(v) * 100).toFixed(3) + '%']}
            />
            <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
            <ReferenceLine y={0} stroke="#475569" />
            <Line type="monotone" dataKey="cum_long" stroke="#22c55e" dot={false} name="Long" strokeWidth={1.5} />
            <Line type="monotone" dataKey="cum_short" stroke="#f59e0b" dot={false} name="Short" strokeWidth={1.5} />
            <Line type="monotone" dataKey="cum_long_short" stroke="#3b82f6" dot={false} name="Long-Short" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Model IC Table */}
      <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
        <div style={{ color: 'white', fontWeight: 600, fontSize: 15, marginBottom: 14 }}>IC by Model</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#64748b', textAlign: 'left', borderBottom: '1px solid #334155' }}>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>Model</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>N</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>IC</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>Hit Rate</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>Avg Return</th>
              </tr>
            </thead>
            <tbody>
              {(modelIc ?? []).map(row => (
                <tr key={row.model_id} style={{ borderBottom: '1px solid #1e293b', color: '#e2e8f0' }}>
                  <td style={{ padding: '7px 12px', fontFamily: 'monospace', fontSize: 12 }}>{row.model_id}</td>
                  <td style={{ padding: '7px 12px' }}>{row.n.toLocaleString()}</td>
                  <td style={{ padding: '7px 12px', color: row.ic == null ? '#64748b' : row.ic > 0 ? '#22c55e' : '#ef4444' }}>
                    {fmt(row.ic)}
                  </td>
                  <td style={{ padding: '7px 12px' }}>{pct(row.hit_rate)}</td>
                  <td style={{ padding: '7px 12px', color: row.avg_return == null ? '#64748b' : row.avg_return > 0 ? '#22c55e' : '#ef4444' }}>
                    {pct(row.avg_return)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!modelIc || modelIc.length === 0) && (
            <div style={{ color: '#64748b', padding: 16, textAlign: 'center' }}>No data</div>
          )}
        </div>
      </div>

      {/* Symbol IC Table */}
      <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
        <div style={{ color: 'white', fontWeight: 600, fontSize: 15, marginBottom: 14 }}>IC by Symbol</div>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#64748b', textAlign: 'left', borderBottom: '1px solid #334155' }}>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>Symbol</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>N</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>IC</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>Hit Rate</th>
                <th style={{ padding: '6px 12px', fontWeight: 500 }}>Avg Return</th>
              </tr>
            </thead>
            <tbody>
              {(symbolIc ?? []).map(row => (
                <tr key={row.symbol} style={{ borderBottom: '1px solid #1e293b', color: '#e2e8f0' }}>
                  <td style={{ padding: '7px 12px', fontWeight: 600 }}>{row.symbol}</td>
                  <td style={{ padding: '7px 12px' }}>{row.n.toLocaleString()}</td>
                  <td style={{ padding: '7px 12px', color: row.ic == null ? '#64748b' : row.ic > 0 ? '#22c55e' : '#ef4444' }}>
                    {fmt(row.ic)}
                  </td>
                  <td style={{ padding: '7px 12px' }}>{pct(row.hit_rate)}</td>
                  <td style={{ padding: '7px 12px', color: row.avg_return == null ? '#64748b' : row.avg_return > 0 ? '#22c55e' : '#ef4444' }}>
                    {pct(row.avg_return)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!symbolIc || symbolIc.length === 0) && (
            <div style={{ color: '#64748b', padding: 16, textAlign: 'center' }}>No data</div>
          )}
        </div>
      </div>
    </div>
  )
}
