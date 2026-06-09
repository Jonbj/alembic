import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
  Cell,
} from 'recharts'
import { strategiesApi } from '@/api/strategies'
import { HelpButton } from '@/components/shared/HelpButton'
import { DataTable } from '@/components/shared/DataTable'
import { KPICard } from '@/components/shared/KPICard'
import type { Strategy, GateResult, SensitivityPoint } from '@/api/strategies'

function fmt(v: number | null | undefined, decimals = 4): string {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return (Number(v) * 100).toFixed(2) + '%'
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

/**
 * Badge indicating whether the displayed metrics come from live portfolio
 * execution or from static backtest results.
 *
 * - LIVE   (green)  — the strategy has run in at least one portfolio cycle
 * - BACKTEST (amber) — only static backtest data is available
 */
function DataSourceBadge({ source }: { source: 'LIVE' | 'BACKTEST' | undefined }) {
  if (!source) return null
  const isLive = source === 'LIVE'
  return (
    <span
      title={
        isLive
          ? 'Metrics reflect live portfolio execution data'
          : 'Metrics are from static backtest results only — no live runs recorded'
      }
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.04em',
        background: isLive ? '#065f46' : '#78350f',
        color: isLive ? '#6ee7b7' : '#fcd34d',
        border: `1px solid ${isLive ? '#059669' : '#d97706'}`,
        userSelect: 'none',
      }}
    >
      <span style={{
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: isLive ? '#34d399' : '#fbbf24',
        flexShrink: 0,
      }} />
      {isLive ? 'LIVE' : 'BACKTEST'}
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, position: 'relative' }}>
      <HelpButton title="Strategies — Validazione Strategie" sections={[
        {
          heading: "Le strategie",
          content: "Alembic usa un portfolio multi-strategia. Ogni strategia è validata independently con 5 validation gates.\n\n**S1 — Time-Series Momentum**: strategia cross-asset trend-following con volatility targeting. VALIDATA (OOS Sharpe 0.51, 5/5 gate passati).\n\n**S3 — Cross-Sectional Momentum**: strategia equity residual momentum. R&D SLEEVE — gate 3 (robustness) e 5 (stress) FALLITI. OOS Sharpe 0.15. NON nel portfolio live.\n\nS2 (VRP) e S4 (News) sono in sviluppo.",
        },
        {
          heading: "I 5 validation gates",
          content: "1. **Significance**: OOS Sharpe > 0.5 — la strategia batte il caso?\n2. **Walk-Forward**: OOS Sharpe > 0.8 × IS Sharpe — il rendimento regge out-of-sample?\n3. **Robustness**: Sharpe stabile attraverso perturbazioni parametriche (CV < 0.5)\n4. **Regime Stability**: performa in diversi regimi di mercato (bull, bear, stress, goldilocks)\n5. **Stress Test**: non collassa in scenari estremi (2008, COVID 2020)",
        },
        {
          heading: "Sensitivity",
          content: "La griglia di sensitivity mostra lo Sharpe ratio per combinazioni di parametri (lookback × vol_window). Colori: verde (Sharpe > 0.6), giallo (0.4-0.6), rosso (< 0.4). Una strategia robusta ha un picco largo, non un singolo punto verde. Peak Sharpe near (lookback=126, vol_window=60).",
        },
      ]} />
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ color: '#64748b', fontSize: 12 }}>
            {currentStrategy.n_assets} assets · {currentStrategy.status.toUpperCase()} · {currentStrategy.oos_sharpe} OOS Sharpe
          </span>
          <DataSourceBadge source={currentStrategy.data_source} />
        </div>
      )}

      {/* KPI Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#94a3b8', fontSize: 12, fontWeight: 500 }}>Performance Metrics</span>
          <DataSourceBadge source={detail?.data_source ?? currentStrategy?.data_source} />
        </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KPICard
          label="OOS Sharpe"
          value={fmt(detail?.oos_sharpe)}
          sub="Out-of-Sample Performance"
          tooltip="Sharpe ratio calcolato su dati out-of-sample. > 0.5 = buona, > 1.0 = eccellente."
        />
        <KPICard
          label="Max Drawdown"
          value={pct(detail?.max_drawdown)}
          sub="Worst drawdown"
          tooltip="Massima perdita dal picco storico. < 20% = accettabile."
        />
        <KPICard
          label="Annual Return"
          value={pct(detail?.annual_return)}
          sub="Historical annualized"
          tooltip="Rendimento annualizzato storico della strategia."
        />
        <KPICard
          label="Total Trades"
          value={detail?.total_trades?.toLocaleString() ?? '—'}
          sub="Lifetime activity"
          tooltip="Numero totale di trade eseguiti dalla strategia nel periodo di backtest."
        />
      </div>
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
      <div>
        <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Validation Gates</h3>
        <DataTable
          columns={[
            { label: 'Gate',      width: '25%' },
            { label: 'Result',    width: '10%' },
            { label: 'Metric',    width: '12%' },
            { label: 'Threshold', width: '12%' },
            { label: 'Details',   width: 'auto' },
          ]}
          rows={(gates ?? []).map((gate: GateResult) => ({
            cells: [
              <strong>{gate.gate_name}</strong>,
              <GateBadge passed={gate.passed} />,
              fmt(gate.metric_value),
              fmt(gate.threshold),
              <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{gate.details}</span>,
            ],
          }))}
          emptyMessage="No validation gates available."
        />
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
          {detail && Object.entries(detail.parameters).map(([key, val]) => (
            <div key={key} style={{ background: '#0f172a', padding: 12, borderRadius: 6 }}>
              <div style={{ color: '#64748b', fontSize: 11 }}>{key.replace(/_/g, ' ')}</div>
              <div style={{ color: 'white', fontSize: 14, fontWeight: 600 }}>
                {Array.isArray(val) ? val.join(', ') : (val ?? '—')}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Universe */}
      <div style={{ background: '#1e293b', borderRadius: 8, padding: 16, border: '1px solid #334155' }}>
        <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600, color: 'white' }}>
          Universe ({Array.isArray(detail?.universe) ? `${detail.universe.length} ETFs` : 'Dynamic'})
        </h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {Array.isArray(detail?.universe) ? (
            detail.universe.map((ticker: string) => (
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
            ))
          ) : (
            <span style={{ color: '#94a3b8', fontSize: 13 }}>{detail?.universe ?? '—'}</span>
          )}
        </div>
      </div>
    </div>
  )
}