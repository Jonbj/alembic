import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
  Cell,
} from 'recharts'
import { strategiesApi } from '@/api/strategies'
import type { Strategy, GateResult, SensitivityPoint } from '@/api/strategies'

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

function GateBadge({ passed }: { passed: boolean }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 11,
      fontWeight: 600,
      background: passed ? '#059669' : '#ef4444',
      color: 'white',
    }}>
      {passed ? 'PASS' : 'FAIL'}
    </span>
  )
}

export default function Strategies() {
  const { data: strategies, isLoading: strategiesLoading, error: strategiesError } = useQuery({
    queryKey: ['strategies'],
    queryFn: strategiesApi.list,
    staleTime: 60_000,
  })

  const [selectedId, setSelectedId] = useState<string>('s1')

  // Select first strategy once loaded
  const id = selectedId || (strategies && strategies.length > 0 ? strategies[0].id : '')

  const { data: detail } = useQuery({
    queryKey: ['strategy-detail', id],
    queryFn: () => strategiesApi.detail(id),
    enabled: !!id,
    staleTime: 60_000,
  })

  const { data: backtestData } = useQuery({
    queryKey: ['strategy-backtest', id],
    queryFn: () => strategiesApi.backtest(id),
    enabled: !!id,
    staleTime: 60_000,
  })

  const { data: gates } = useQuery({
    queryKey: ['strategy-gates', id],
    queryFn: () => strategiesApi.gates(id),
    enabled: !!id,
    staleTime: 60_000,
  })

  const { data: sensitivity } = useQuery({
    queryKey: ['strategy-sensitivity', id],
    queryFn: () => strategiesApi.sensitivity(id),
    enabled: !!id,
    staleTime: 60_000,
  })

  if (strategiesLoading) return <div style={{ color: '#94a3b8', padding: 24 }}>Loading strategies…</div>
  if (strategiesError) return <div style={{ color: '#ef4444', padding: 24 }}>Failed to load strategies: {String(strategiesError)}</div>
  if (!strategies || strategies.length === 0) return <div style={{ color: '#94a3b8', padding: 24 }}>No strategies found.</div>

  const currentStrategy = strategies.find(s => s.id === id)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'white' }}>Strategies</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ color: '#94a3b8', fontSize: 13 }}>Strategy:</span>
          <select
            value={id}
            onChange={e => setSelectedId(e.target.value)}
            style={{
              background: '#1e293b', color: 'white', border: '1px solid #334155',
              borderRadius: 6, padding: '6px 12px', fontSize: 13, cursor: 'pointer',
            }}
          >
            {strategies.map(s => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {currentStrategy && (
        <div style={{ color: '#64748b', fontSize: 12 }}>
          {currentStrategy.n_assets} assets · {currentStrategy.status.toUpperCase()} · {currentStrategy.oos_sharpe} OOS Sharpe
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard
          label="OOS Sharpe"
          value={fmt(detail?.oos_sharpe)}
          sub="Out-of-Sample Performance"
        />
        <KpiCard
          label="Max Drawdown"
          value={pct(detail?.max_drawdown)}
          sub="Worst drawdown"
        />
        <KpiCard
          label="Annual Return"
          value={pct(detail?.annual_return)}
          sub="Historical annualized"
        />
        <KpiCard
          label="Total Trades"
          value={detail?.total_trades?.toLocaleString() ?? '—'}
          sub="Lifetime activity"
        />
      </div>

      {/* Equity Curve */}
      <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, border: '1px solid #334155' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: 'white' }}>Equity Curve</h3>
        <div style={{ height: 300, width: '100%' }}>
          <ResponsiveContainer>
            <LineChart data={backtestData}>
              <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', color: 'white', borderRadius: 6 }}
                itemStyle={{ color: '#60a5fa' }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="cumulative_return"
                name="Cumulative Return"
                stroke="#60a5fa"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="drawdown"
                name="Drawdown"
                stroke="#f43f5e"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Gates */}
      <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, border: '1px solid #334155' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: 'white' }}>Validation Gates</h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid #334155', color: '#94a3b8', fontSize: 11 }}>
                  Gate
                </th>
                <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid #334155', color: '#94a3b8', fontSize: 11 }}>
                  Result
                </th>
                <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid #334155', color: '#94a3b8', fontSize: 11 }}>
                  Metric
                </th>
                <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid #334155', color: '#94a3b8', fontSize: 11 }}>
                  Threshold
                </th>
                <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid #334155', color: '#94a3b8', fontSize: 11 }}>
                  Details
                </th>
              </tr>
            </thead>
            <tbody>
              {gates?.map((gate: GateResult) => (
                <tr key={gate.gate_id}>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #334155', color: 'white', fontSize: 13 }}>
                    {gate.gate_name}
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #334155' }}>
                    <GateBadge passed={gate.passed} />
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #334155', color: 'white', fontSize: 13 }}>
                    {fmt(gate.metric_value)}
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #334155', color: 'white', fontSize: 13 }}>
                    {fmt(gate.threshold)}
                  </td>
                  <td style={{ padding: '8px 12px', borderBottom: '1px solid #334155', color: '#94a3b8', fontSize: 12 }}>
                    {gate.details}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Sensitivity Heatmap */}
      <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, border: '1px solid #334155' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: 'white' }}>Parameter Sensitivity (Sharpe)</h3>
        <div style={{ height: 300, width: '100%' }}>
          <ResponsiveContainer>
            <BarChart
              data={sensitivity}
              margin={{ top: 20, right: 30, left: 20, bottom: 50 }}
            >
              <CartesianGrid stroke="#334155" strokeDasharray="3 3" />
              <XAxis dataKey="lookback" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis dataKey="vol_window" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #334155', color: 'white', borderRadius: 6 }}
              />
              <Legend />
              <Bar dataKey="sharpe" name="Sharpe Ratio">
                {sensitivity?.map((entry: SensitivityPoint, index: number) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.sharpe > 0.6 ? '#10b981' : entry.sharpe > 0.4 ? '#f59e0b' : '#ef4444'}
                    opacity={0.8}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: '#64748b' }}>
          Peak Sharpe near (lookback=60, vol_window=30)
        </div>
      </div>

      {/* Strategy Details */}
      <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, border: '1px solid #334155' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: 'white' }}>Strategy Parameters</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
          <div style={{ background: '#0f172a', padding: 12, borderRadius: 6 }}>
            <div style={{ color: '#64748b', fontSize: 11 }}>Lookback Long</div>
            <div style={{ color: 'white', fontSize: 14, fontWeight: 600 }}>{detail?.parameters.lookback_long}</div>
          </div>
          <div style={{ background: '#0f172a', padding: 12, borderRadius: 6 }}>
            <div style={{ color: '#64748b', fontSize: 11 }}>Lookback Short</div>
            <div style={{ color: 'white', fontSize: 14, fontWeight: 600 }}>{detail?.parameters.lookback_short}</div>
          </div>
          <div style={{ background: '#0f172a', padding: 12, borderRadius: 6 }}>
            <div style={{ color: '#64748b', fontSize: 11 }}>Vol Window</div>
            <div style={{ color: 'white', fontSize: 14, fontWeight: 600 }}>{detail?.parameters.vol_window}</div>
          </div>
          <div style={{ background: '#0f172a', padding: 12, borderRadius: 6 }}>
            <div style={{ color: '#64748b', fontSize: 11 }}>Vol Target</div>
            <div style={{ color: 'white', fontSize: 14, fontWeight: 600 }}>{(detail?.parameters.vol_target ?? 0) * 100}%</div>
          </div>
          <div style={{ background: '#0f172a', padding: 12, borderRadius: 6 }}>
            <div style={{ color: '#64748b', fontSize: 11 }}>Max Leverage</div>
            <div style={{ color: 'white', fontSize: 14, fontWeight: 600 }}>{detail?.parameters.max_leverage}</div>
          </div>
        </div>
      </div>

      {/* Universe */}
      <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, border: '1px solid #334155' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: 'white' }}>Universe ({detail?.universe.length} ETFs)</h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {detail?.universe.map(ticker => (
            <span
              key={ticker}
              style={{
                background: '#334155',
                color: 'white',
                padding: '4px 10px',
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 500,
              }}
            >
              {ticker}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}