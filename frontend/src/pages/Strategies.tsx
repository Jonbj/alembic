import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ComposedChart, Line, Area,
  BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { strategiesApi } from '@/api/strategies'
import type { GateResult, SensitivityResult } from '@/api/strategies'

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return (Number(v) * 100).toFixed(1) + '%'
}

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: '#1e293b', borderRadius: 8, padding: '14px 18px',
      border: '1px solid #334155', minWidth: 130, flex: '1 1 130px',
    }}>
      <div style={{ color: '#64748b', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{label}</div>
      <div style={{ color: 'white', fontSize: 22, fontWeight: 700 }}>{value}</div>
      {sub && <div style={{ color: '#94a3b8', fontSize: 11, marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const MAP: Record<string, { fg: string; bg: string; label: string }> = {
    validated: { fg: '#22c55e', bg: '#14532d', label: '🟢 Validata' },
    testing:   { fg: '#f59e0b', bg: '#78350f', label: '🟡 In Test' },
    building:  { fg: '#ef4444', bg: '#7f1d1d', label: '🔴 In Costruzione' },
  }
  const c = MAP[status] ?? MAP.building
  return (
    <span style={{
      background: c.bg, color: c.fg, border: `1px solid ${c.fg}`,
      borderRadius: 6, padding: '3px 12px', fontSize: 12, fontWeight: 600,
    }}>{c.label}</span>
  )
}

function GateCard({ gate }: { gate: GateResult }) {
  const ok = gate.passed
  return (
    <div style={{
      background: '#1e293b', borderRadius: 8, border: `1px solid ${ok ? '#166534' : '#7f1d1d'}`,
      padding: '14px 16px', flex: '1 1 180px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ color: '#94a3b8', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {gate.gate_id.replace('_', ' ').toUpperCase()}
        </span>
        <span style={{
          background: ok ? '#14532d' : '#7f1d1d', color: ok ? '#22c55e' : '#ef4444',
          borderRadius: 4, padding: '2px 8px', fontSize: 11, fontWeight: 700,
        }}>
          {ok ? '✅ PASS' : '❌ FAIL'}
        </span>
      </div>
      <div style={{ color: 'white', fontWeight: 600, fontSize: 13, marginBottom: 6 }}>{gate.gate_name}</div>
      <div style={{ color: '#94a3b8', fontSize: 11, lineHeight: 1.4, marginBottom: 8 }}>{gate.details}</div>
      {gate.metric_value != null && gate.threshold != null && (
        <div style={{ display: 'flex', gap: 16, fontSize: 11 }}>
          <span>
            <span style={{ color: '#64748b' }}>Valore: </span>
            <span style={{ color: ok ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
              {fmt(gate.metric_value, 3)}
            </span>
          </span>
          <span>
            <span style={{ color: '#64748b' }}>Soglia: </span>
            <span style={{ color: '#94a3b8' }}>{fmt(gate.threshold, 3)}</span>
          </span>
        </div>
      )}
    </div>
  )
}

function SensitivityChart({ item }: { item: SensitivityResult }) {
  const data = item.results.map(r => ({ name: String(r.value), Sharpe: r.sharpe, MaxDD: -r.max_dd }))
  return (
    <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 16 }}>
      <div style={{ color: 'white', fontWeight: 600, fontSize: 13, marginBottom: 12 }}>
        Sensibilità: <span style={{ color: '#94a3b8' }}>{item.parameter}</span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 0, right: 0, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
          <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
            formatter={(v: unknown) => [fmt(v as number, 3)]}
          />
          <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 11 }} />
          <Bar dataKey="Sharpe" fill="#3b82f6" radius={[3, 3, 0, 0]} />
          <Bar dataKey="MaxDD" fill="#ef4444" radius={[3, 3, 0, 0]} name="|Max DD|" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function SharpeGrid({ item }: { item: SensitivityResult }) {
  const rows = item.lookback_long_values ?? []
  const cols = item.vol_window_values ?? []
  const grid = item.grid ?? []

  function cellColor(v: number) {
    if (v >= 0.6) return { bg: '#14532d', fg: '#22c55e' }
    if (v >= 0.4) return { bg: '#78350f', fg: '#fcd34d' }
    return { bg: '#7f1d1d', fg: '#fca5a5' }
  }

  return (
    <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 16 }}>
      <div style={{ color: 'white', fontWeight: 600, fontSize: 13, marginBottom: 12 }}>
        Sharpe Surface — lookback_long × vol_window
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              <th style={{ padding: '6px 16px', color: '#64748b', fontWeight: 500, textAlign: 'left' }}>
                lookback \ vol_win
              </th>
              {cols.map(c => (
                <th key={c} style={{ padding: '6px 16px', color: '#94a3b8', fontWeight: 600, textAlign: 'center' }}>
                  {c}m
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={row}>
                <td style={{ padding: '6px 16px', color: '#94a3b8', fontWeight: 600 }}>{row}m</td>
                {(grid[ri] ?? []).map((v, ci) => {
                  const { bg, fg } = cellColor(v)
                  return (
                    <td key={ci} style={{
                      padding: '8px 16px', textAlign: 'center',
                      background: bg, color: fg, fontWeight: 700,
                      border: '2px solid #0f172a', borderRadius: 4,
                    }}>
                      {fmt(v, 2)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
        {[
          { bg: '#14532d', fg: '#22c55e', label: '≥ 0.60' },
          { bg: '#78350f', fg: '#fcd34d', label: '0.40 – 0.60' },
          { bg: '#7f1d1d', fg: '#fca5a5', label: '< 0.40' },
        ].map(({ bg, fg, label }) => (
          <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: '#94a3b8' }}>
            <span style={{ width: 12, height: 12, background: bg, border: `1px solid ${fg}`, borderRadius: 2, display: 'inline-block' }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function Strategies() {
  const [selectedId, setSelectedId] = useState('s1')

  const { data: strategies } = useQuery({
    queryKey: ['strategies-list'],
    queryFn: strategiesApi.list,
    staleTime: 60_000,
  })

  const { data: backtest, isLoading } = useQuery({
    queryKey: ['strategies-backtest', selectedId],
    queryFn: () => strategiesApi.backtest(selectedId),
    enabled: !!selectedId,
    staleTime: 60_000,
  })

  const { data: gates } = useQuery({
    queryKey: ['strategies-gates', selectedId],
    queryFn: () => strategiesApi.gates(selectedId),
    enabled: !!selectedId,
    staleTime: 60_000,
  })

  const { data: sensitivity } = useQuery({
    queryKey: ['strategies-sensitivity', selectedId],
    queryFn: () => strategiesApi.sensitivity(selectedId),
    enabled: !!selectedId,
    staleTime: 60_000,
  })

  const selected = strategies?.find(s => s.id === selectedId)
  const m = backtest?.metrics

  const equityCurveData = (backtest?.equity_curve ?? []).filter((_, i) => i % 3 === 0)

  const sensitivityItems = (sensitivity ?? []).filter(s => s.parameter !== 'sharpe_grid')
  const gridItem = (sensitivity ?? []).find(s => s.parameter === 'sharpe_grid')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'white' }}>Strategie</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ color: '#94a3b8', fontSize: 13 }}>Strategia:</span>
          <select
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
            style={{
              background: '#1e293b', color: 'white', border: '1px solid #334155',
              borderRadius: 6, padding: '6px 12px', fontSize: 13, cursor: 'pointer',
            }}
          >
            {(strategies ?? [{ id: 's1', name: 'S1 — Time-Series Momentum' }]).map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {selected && <StatusBadge status={selected.status} />}
        </div>
      </div>

      {selected?.description && (
        <div style={{ color: '#64748b', fontSize: 12 }}>{selected.description}</div>
      )}

      {isLoading && <div style={{ color: '#94a3b8', padding: 12 }}>Caricamento dati strategia…</div>}

      {/* KPI Cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KpiCard label="Sharpe OOS" value={fmt(m?.sharpe)} sub="Out-of-sample" />
        <KpiCard label="Rendimento Annuo" value={pct(m?.annual_return)} sub="CAGR" />
        <KpiCard label="Drawdown Massimo" value={pct(m?.max_drawdown)} sub="Peak-to-trough" />
        <KpiCard label="Sortino" value={fmt(m?.sortino)} sub="Downside risk adj." />
        <KpiCard label="Win Rate" value={pct(m?.win_rate)} sub="Mesi positivi" />
        <KpiCard label="N Asset" value={String(selected?.n_assets ?? '—')} sub="Universo ETF" />
      </div>

      {/* Equity Curve + Drawdown */}
      {equityCurveData.length > 0 && (
        <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
          <div style={{ marginBottom: 16 }}>
            <div style={{ color: 'white', fontWeight: 600, fontSize: 15 }}>Curva Equity e Drawdown</div>
            <div style={{ color: '#64748b', fontSize: 12, marginTop: 2 }}>
              {backtest?.period.start?.slice(0, 7)} → {backtest?.period.end?.slice(0, 7)} · rendimento cumulativo mensile
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={equityCurveData} margin={{ top: 0, right: 40, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                tickFormatter={d => d.slice(0, 4)}
                interval={35}
              />
              <YAxis
                yAxisId="return"
                tickFormatter={v => (Number(v) * 100).toFixed(0) + '%'}
                tick={{ fill: '#94a3b8', fontSize: 11 }}
              />
              <YAxis
                yAxisId="dd"
                orientation="right"
                tickFormatter={v => (Number(v) * 100).toFixed(0) + '%'}
                tick={{ fill: '#94a3b8', fontSize: 11 }}
                domain={[-0.3, 0]}
              />
              <Tooltip
                contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6 }}
                formatter={(v, name) => [
                  (Number(v) * 100).toFixed(1) + '%',
                  String(name ?? ''),
                ]}
                labelFormatter={l => String(l)}
              />
              <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
              <Line
                yAxisId="return"
                type="monotone"
                dataKey="cumulative_return"
                stroke="#22c55e"
                dot={false}
                strokeWidth={1.5}
                name="Rendimento Cumulativo"
              />
              <Area
                yAxisId="dd"
                type="monotone"
                dataKey="drawdown"
                fill="#ef444440"
                stroke="#ef4444"
                strokeWidth={1}
                dot={false}
                name="Drawdown"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Validation Gates */}
      {gates && gates.length > 0 && (
        <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
          <div style={{ color: 'white', fontWeight: 600, fontSize: 15, marginBottom: 4 }}>Gate di Validazione</div>
          <div style={{ color: '#64748b', fontSize: 12, marginBottom: 16 }}>
            {gates.filter(g => g.passed).length}/{gates.length} gate superati
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {gates.map(g => <GateCard key={g.gate_id} gate={g} />)}
          </div>
        </div>
      )}

      {/* Per-Asset Contribution */}
      {backtest?.per_asset && backtest.per_asset.length > 0 && (
        <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
          <div style={{ color: 'white', fontWeight: 600, fontSize: 15, marginBottom: 14 }}>Contributo per Asset</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#64748b', textAlign: 'left', borderBottom: '1px solid #334155' }}>
                  <th style={{ padding: '6px 12px', fontWeight: 500 }}>Ticker</th>
                  <th style={{ padding: '6px 12px', fontWeight: 500 }}>Peso (%)</th>
                  <th style={{ padding: '6px 12px', fontWeight: 500 }}>Contributo (%)</th>
                  <th style={{ padding: '6px 12px', fontWeight: 500 }}>Sharpe</th>
                </tr>
              </thead>
              <tbody>
                {backtest.per_asset.map(row => (
                  <tr key={row.ticker} style={{ borderBottom: '1px solid #1e293b', color: '#e2e8f0' }}>
                    <td style={{ padding: '7px 12px', fontWeight: 600 }}>{row.ticker}</td>
                    <td style={{ padding: '7px 12px' }}>{pct(row.weight)}</td>
                    <td style={{
                      padding: '7px 12px',
                      color: row.contribution > 0 ? '#22c55e' : '#ef4444',
                    }}>
                      {pct(row.contribution)}
                    </td>
                    <td style={{
                      padding: '7px 12px',
                      color: row.sharpe > 0.3 ? '#22c55e' : row.sharpe > 0 ? '#f59e0b' : '#ef4444',
                    }}>
                      {fmt(row.sharpe)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Sensitivity Analysis */}
      {(sensitivityItems.length > 0 || gridItem) && (
        <div style={{ background: '#1e293b', borderRadius: 8, border: '1px solid #334155', padding: 20 }}>
          <div style={{ color: 'white', fontWeight: 600, fontSize: 15, marginBottom: 4 }}>Analisi di Sensibilità</div>
          <div style={{ color: '#64748b', fontSize: 12, marginBottom: 16 }}>
            Impatto dei parametri sul Sharpe ratio OOS
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: gridItem ? 20 : 0 }}>
            {sensitivityItems.map(item => (
              <div key={item.parameter} style={{ flex: '1 1 280px' }}>
                <SensitivityChart item={item} />
              </div>
            ))}
          </div>
          {gridItem && <SharpeGrid item={gridItem} />}
        </div>
      )}
    </div>
  )
}
