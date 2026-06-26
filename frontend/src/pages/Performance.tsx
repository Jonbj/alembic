import { useState, useMemo } from 'react'
import { fmtDateTime, fmtDate } from '@/utils/format'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Cell,
} from 'recharts'
import { fetchPnL, fetchWeeklyReport, fetchDailyPnL } from '@/api/performance'
import type { WeeklyReport, DailyPnLDay } from '@/api/performance'
import { fetchTradesSummary } from '@/api/trades'
import { HelpButton } from '@/components/shared/HelpButton'
import { DataTable } from '@/components/shared/DataTable'

const PERIODS = ['1M', '3M', '6M', '1Y'] as const
type Period = typeof PERIODS[number]

function WeeklyReportTab({
  weekly,
  isLoading,
}: {
  weekly: WeeklyReport | undefined
  isLoading: boolean
}) {
  const card: React.CSSProperties = {
    background: '#1e293b', border: '1px solid #334155',
    borderRadius: 8, padding: '16px 20px', marginBottom: 16,
  }
  const h3: React.CSSProperties = { margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: 'white' }
  const row: React.CSSProperties = {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '5px 0', borderBottom: '1px solid #0f172a', fontSize: 13,
  }
  const labelSt: React.CSSProperties = { color: '#94a3b8' }
  const valueSt: React.CSSProperties = { color: 'white', fontWeight: 500 }
  const pct = (v: number | undefined) => v != null ? `${(v * 100).toFixed(2)}%` : '—'
  const usd = (v: number | undefined) => v != null ? `$${v.toFixed(2)}` : '—'
  const bps = (v: number | undefined) => v != null ? `${v.toFixed(1)} bps` : '—'
  const num = (v: number | undefined, d = 1) => v != null ? v.toFixed(d) : '—'

  if (isLoading) return <div style={{ color: '#94a3b8', padding: 24 }}>Caricamento report settimanale…</div>
  if (!weekly) return (
    <div style={{ color: '#94a3b8', padding: 24, textAlign: 'center' }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>📭</div>
      <div>Nessun report settimanale disponibile.</div>
      <div style={{ fontSize: 12, marginTop: 8 }}>
        Il report viene calcolato ogni lunedì alle 04:00 UTC da <code>run_weekly_weights</code>.
      </div>
    </div>
  )

  const tp = weekly.trade_pnl
  const ce = weekly.capital_efficiency
  const rg = weekly.regime
  const fb = weekly.feedback
  const inf = weekly.infrastructure
  const wt = weekly.weights

  const computedDate = weekly.computed_at
    ? fmtDateTime(weekly.computed_at)
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
            <div style={row}><span style={labelSt}>Trade totali</span><span style={valueSt}>{tp.total_trades}</span></div>
            <div style={row}><span style={labelSt}>Win rate</span><span style={valueSt}>{pct(tp.win_rate)}</span></div>
            <div style={row}><span style={labelSt}>P&L netto medio</span><span style={{ ...valueSt, color: (tp.avg_net_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>{usd(tp.avg_net_pnl)}</span></div>
            <div style={row}><span style={labelSt}>P&L lordo medio</span><span style={valueSt}>{usd(tp.avg_gross_pnl)}</span></div>
            <div style={row}><span style={labelSt}>Slippage medio</span><span style={valueSt}>{usd(tp.avg_slippage_est)}</span></div>
            <div style={row}><span style={labelSt}>P&L netto totale</span><span style={{ ...valueSt, color: (tp.total_net_pnl ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}>{usd(tp.total_net_pnl)}</span></div>
            <div style={row}><span style={labelSt}>Notional totale</span><span style={valueSt}>${(tp.total_notional ?? 0).toFixed(0)}</span></div>
            <div style={row}><span style={labelSt}>Trade/settimana</span><span style={valueSt}>{num(tp.trades_per_week)}</span></div>
            <div style={row}><span style={labelSt}>Hold medio</span><span style={valueSt}>{num(tp.avg_hold_minutes, 0)} min</span></div>
            <div style={row}><span style={labelSt}>Return on notional</span><span style={valueSt}>{pct(tp.return_on_notional)}</span></div>
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
            <div style={row}><span style={labelSt}>Costo medio/trade</span><span style={valueSt}>{bps(tp.avg_cost_bps)}</span></div>
            <div style={row}><span style={{ ...labelSt, paddingLeft: 12 }}>di cui spread</span><span style={labelSt}>{bps(tp.avg_spread_cost_bps)}</span></div>
            <div style={row}><span style={{ ...labelSt, paddingLeft: 12 }}>di cui market impact</span><span style={labelSt}>{bps(tp.avg_impact_cost_bps)}</span></div>
            <div style={row}><span style={labelSt}>Costo totale (7d)</span><span style={valueSt}>{usd(tp.total_cost_usd)}</span></div>
            <div style={row}><span style={labelSt}>Cost drag (giornaliero)</span><span style={valueSt}>{pct(tp.cost_drag_pct)}</span></div>
            <div style={row}>
              <span style={labelSt}>Cost drag annualizzato</span>
              <span style={{ ...valueSt, color: '#f59e0b' }}>~{((tp.cost_drag_pct ?? 0) * 252 * 10_000).toFixed(0)} bps/anno</span>
            </div>
          </>
        )}
      </div>

      {/* Capital Efficiency */}
      <div style={card}>
        <h3 style={h3}>💰 Efficienza Capitale</h3>
        {!ce || ce.portfolio_value_usd == null ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>Dati non disponibili questa settimana.</div>
        ) : (
          <>
            <div style={row}><span style={labelSt}>Valore portafoglio</span><span style={valueSt}>${(ce.portfolio_value_usd ?? 0).toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span></div>
            <div style={row}><span style={labelSt}>Capitale deployato</span><span style={valueSt}>{pct(ce.deployment_pct)} ({ce.n_open_positions ?? 0} posizioni)</span></div>
            <div style={row}><span style={labelSt}>Capitale idle (cash)</span><span style={valueSt}>{pct(ce.cash_pct)}</span></div>
            <div style={row}><span style={labelSt}>Cash drag annuo stimato</span><span style={{ ...valueSt, color: '#f59e0b' }}>{num(ce.annual_cash_drag_pct, 1)}% (costo opportunità vs T-bill 4.5%)</span></div>
            <div style={row}><span style={labelSt}>Efficienza deployment</span><span style={valueSt}>{pct(ce.efficiency_ratio)} del teorico max (5 pos × 10%)</span></div>
          </>
        )}
      </div>

      {/* Regime */}
      <div style={card}>
        <h3 style={h3}>📡 Regime & Deployment Ceiling</h3>
        {!rg || rg.label == null ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>Dati non disponibili questa settimana.</div>
        ) : (
          <>
            <div style={row}>
              <span style={labelSt}>Regime corrente</span>
              <span style={{
                ...valueSt,
                color: rg.label === 'bull' ? '#22c55e' : rg.label === 'bear' ? '#ef4444' : rg.label === 'high_vol' ? '#f97316' : '#f59e0b',
              }}>
                {rg.label ?? '—'} (×{num(rg.multiplier, 1)})
              </span>
            </div>
            <div style={row}><span style={labelSt}>Confidenza</span><span style={valueSt}>{pct(rg.confidence)}</span></div>
            <div style={row}><span style={labelSt}>Deployment ceiling</span><span style={valueSt}>{pct(rg.deployment_ceiling_pct)}</span></div>
            <div style={row}><span style={labelSt}>Capitale trattenuto vs bull</span><span style={{ ...valueSt, color: '#f59e0b' }}>{num(rg.regime_discount_pct, 0)}%</span></div>
          </>
        )}
      </div>

      {/* Feedback Loop */}
      <div style={card}>
        <h3 style={h3}>🧠 Feedback Loop (threshold adattivo)</h3>
        {!fb || fb.current_threshold == null ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>Dati non disponibili questa settimana.</div>
        ) : (
          <>
            <div style={row}><span style={labelSt}>Threshold baseline</span><span style={valueSt}>{num(fb.threshold_baseline, 2)}</span></div>
            <div style={row}>
              <span style={labelSt}>Threshold corrente</span>
              <span style={{ ...valueSt, color: fb.is_elevated ? '#ef4444' : '#22c55e' }}>
                {num(fb.current_threshold, 2)} {fb.is_elevated ? '🔴 ELEVATO' : '✅ Normale'}
              </span>
            </div>
            <div style={row}><span style={labelSt}>Regime scale</span><span style={valueSt}>×{num(fb.current_scale, 2)}</span></div>
            {fb.is_elevated && (
              <div style={row}>
                <span style={labelSt}>Recovery</span>
                <span style={valueSt}>{fb.consecutive_wins ?? 0}/{fb.recovery_win_streak ?? 5} win consecutivi</span>
              </div>
            )}
            {fb.last_adjustment_ts && (
              <div style={row}><span style={labelSt}>Ultimo aggiustamento</span><span style={valueSt}>{fb.last_adjustment_ts.slice(0, 10)}</span></div>
            )}
          </>
        )}
      </div>

      {/* Infrastructure */}
      <div style={card}>
        <h3 style={h3}>🏗️ Costi Infrastruttura & Break-even</h3>
        {!inf || inf.monthly_total_usd == null ? (
          <div style={{ color: '#64748b', fontSize: 13 }}>Dati non disponibili questa settimana.</div>
        ) : (
          <>
            <div style={row}><span style={labelSt}>Costo fisso mensile</span><span style={valueSt}>${num(inf.monthly_fixed_usd, 0)}</span></div>
            <div style={row}><span style={labelSt}>Costo LLM (30d)</span><span style={valueSt}>${num(inf.monthly_llm_usd, 2)}</span></div>
            <div style={row}><span style={labelSt}>Totale mensile</span><span style={{ ...valueSt, fontWeight: 700 }}>${num(inf.monthly_total_usd, 0)}</span></div>
            <div style={row}><span style={labelSt}>Stima annuale</span><span style={{ ...valueSt, color: '#f59e0b' }}>${(inf.annual_total_usd ?? 0).toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span></div>
            <div style={{ marginTop: 12, fontSize: 12, color: '#64748b' }}>Break-even portfolio (per coprire i costi annui):</div>
            {inf.breakevens && Object.entries(inf.breakevens).map(([pctStr, size]) => (
              <div key={pctStr} style={row}>
                <span style={labelSt}>A {pctStr}% rendimento annuo</span>
                <span style={valueSt}>${(size as number).toLocaleString('it-IT', { maximumFractionDigits: 0 })}</span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Weights */}
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
            <div key={model} style={{ display: 'contents' }}>
              <div style={{ color: '#94a3b8' }}>{model}</div>
              <div style={{ color: 'white' }}>{((wt.current[model] ?? 0) * 100).toFixed(1)}%</div>
              <div style={{ color: '#60a5fa' }}>{((wt.suggested[model] ?? 0) * 100).toFixed(1)}%</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── helpers ────────────────────────────────────────────────────────────────

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function nDaysAgoStr(n: number) {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function fmtPnL(v: number) {
  const sign = v >= 0 ? '+' : ''
  return `${sign}$${v.toFixed(2)}`
}

// DD/MM from YYYY-MM-DD (for chart axis — no year to save space)
function fmtDateShort(iso: string) {
  if (!iso || iso.length < 10) return iso
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}`
}

// ─── ItDatePicker — shows Italian format, delegates to native input ──────────

function ItDatePicker({ value, onChange, min, max, label }: {
  value: string
  onChange: (v: string) => void
  label: string
  min?: string
  max?: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{label}</span>
      <div style={{ position: 'relative', display: 'inline-block' }}>
        <span style={{
          display: 'block',
          padding: '4px 10px',
          background: 'var(--card)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          color: 'var(--text)',
          fontSize: 13,
          minWidth: 90,
          pointerEvents: 'none',
          userSelect: 'none',
        }}>
          {fmtDate(value)}
        </span>
        <input
          type="date"
          value={value}
          min={min}
          max={max}
          onChange={(e) => onChange(e.target.value)}
          style={{
            position: 'absolute', top: 0, left: 0,
            width: '100%', height: '100%',
            opacity: 0, cursor: 'pointer',
          }}
        />
      </div>
    </div>
  )
}

// ─── DailyPnLTab ────────────────────────────────────────────────────────────

function DailyPnLTab() {
  const [fromDate, setFromDate] = useState(nDaysAgoStr(6))
  const [toDate, setToDate] = useState(todayStr())

  const { data, isLoading, isError } = useQuery({
    queryKey: ['daily-pnl', fromDate, toDate],
    queryFn: () => fetchDailyPnL(fromDate, toDate),
    enabled: !!fromDate && !!toDate && fromDate <= toDate,
    staleTime: 60_000,
  })

  const summary = data?.summary
  const days = data?.days ?? []

  const chartData = days.map((d) => ({
    date: fmtDateShort(d.date),
    pnl: d.total_net_pnl,
  }))

  const tableRows = days.map((day) => {
    const pos = day.total_net_pnl >= 0
    return {
      cells: [
        <span style={{ fontWeight: 500 }}>{fmtDate(day.date)}</span>,
        day.trades_closed,
        <span style={{ color: pos ? 'var(--green)' : 'var(--red)', fontWeight: 700 }}>
          {fmtPnL(day.total_net_pnl)}
        </span>,
        <span style={{ color: 'var(--green)' }}>
          {day.gross_profit > 0 ? `+$${day.gross_profit.toFixed(2)}` : '—'}
        </span>,
        <span style={{ color: 'var(--red)' }}>
          {day.gross_loss < 0 ? `-$${Math.abs(day.gross_loss).toFixed(2)}` : '—'}
        </span>,
        <span className={`badge ${pos ? 'badge-green' : 'badge-red'}`}>
          {day.winners}W / {day.losers}L
        </span>,
      ],
      expanded: day.trades.length > 0 ? (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr>
              {['Symbol', 'Motivo uscita', 'Entry', 'Exit', 'Qty', 'Gross P&L', 'Net P&L'].map((h) => (
                <th key={h} style={{ textAlign: 'left', padding: '4px 8px', color: 'var(--text-muted)', fontWeight: 600, fontSize: 11 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {day.trades.map((t, i) => (
              <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '4px 8px', fontWeight: 600 }}>{t.symbol}</td>
                <td style={{ padding: '4px 8px', color: 'var(--text-muted)', maxWidth: 300, wordBreak: 'break-word' }}>
                  {t.exit_reason ?? '—'}
                </td>
                <td style={{ padding: '4px 8px' }}>{t.entry_price != null ? `$${t.entry_price.toFixed(2)}` : '—'}</td>
                <td style={{ padding: '4px 8px' }}>{t.exit_price != null ? `$${t.exit_price.toFixed(2)}` : '—'}</td>
                <td style={{ padding: '4px 8px' }}>{t.qty != null ? t.qty.toFixed(4) : '—'}</td>
                <td style={{ padding: '4px 8px', color: (t.gross_pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {t.gross_pnl != null ? fmtPnL(t.gross_pnl) : '—'}
                </td>
                <td style={{ padding: '4px 8px', fontWeight: 700, color: t.net_pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {fmtPnL(t.net_pnl)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : undefined,
    }
  })

  return (
    <div>
      {/* Date range bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <ItDatePicker label="Dal" value={fromDate} max={toDate} onChange={setFromDate} />
        <ItDatePicker label="al" value={toDate} min={fromDate} max={todayStr()} onChange={setToDate} />
        {[
          { label: '7d', from: nDaysAgoStr(6) },
          { label: '14d', from: nDaysAgoStr(13) },
          { label: '30d', from: nDaysAgoStr(29) },
        ].map(({ label, from }) => {
          const active = fromDate === from && toDate === todayStr()
          return (
            <button
              key={label}
              onClick={() => { setFromDate(from); setToDate(todayStr()) }}
              style={{
                padding: '4px 10px', fontSize: 12, cursor: 'pointer',
                background: active ? 'var(--blue)' : 'transparent',
                color: active ? 'white' : 'var(--text-muted)',
                border: '1px solid var(--border)', borderRadius: 6,
              }}
            >{label}</button>
          )
        })}
      </div>

      {isLoading && <div style={{ color: 'var(--text-muted)', padding: 24 }}>Caricamento…</div>}
      {isError && <div style={{ color: 'var(--red)', padding: 24 }}>Errore nel caricamento dei dati.</div>}
      {!isLoading && !isError && days.length === 0 && (
        <div style={{ color: 'var(--text-muted)', padding: 24, textAlign: 'center' }}>
          Nessun trade chiuso nel periodo selezionato.
        </div>
      )}

      {summary && days.length > 0 && (
        <>
          {/* KPI strip */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
            {[
              {
                label: 'P&L Netto Totale',
                value: fmtPnL(summary.total_net_pnl),
                color: summary.total_net_pnl >= 0 ? 'var(--green)' : 'var(--red)',
              },
              {
                label: 'Trade Chiusi',
                value: `${summary.total_trades} (${summary.winners}W / ${summary.losers}L)`,
                color: 'var(--text)',
              },
              {
                label: 'Win Rate',
                value: `${(summary.win_rate * 100).toFixed(1)}%`,
                color: summary.win_rate >= 0.5 ? 'var(--green)' : '#f59e0b',
              },
              {
                label: 'Giorni +/−',
                value: `${summary.positive_days} ▲ / ${summary.negative_days} ▼`,
                color: 'var(--text)',
              },
            ].map(({ label, value, color }) => (
              <div key={label} className="card" style={{ textAlign: 'center', padding: '12px 16px' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color }}>{value}</div>
              </div>
            ))}
          </div>

          {/* Bar chart */}
          <div className="card" style={{ marginBottom: 20 }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>P&L per Giornata</h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  formatter={(v) => [fmtPnL(Number(v)), 'Net P&L']}
                  contentStyle={{ borderRadius: 6 }}
                />
                <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, idx) => (
                    <Cell key={idx} fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Per-day table */}
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Dettaglio per Giornata</h3>
          <DataTable
            loading={isLoading}
            columns={[
              { label: 'Data',     width: '16%' },
              { label: 'Trade',    width: '8%'  },
              { label: 'Net P&L',  width: '14%' },
              { label: 'Profitti', width: '14%' },
              { label: 'Perdite',  width: '14%' },
              { label: 'W / L',    width: '14%' },
            ]}
            rows={tableRows}
            emptyMessage="Nessun trade chiuso nel periodo selezionato."
          />
        </>
      )}
    </div>
  )
}

export default function Performance() {
  const [period, setPeriod] = useState<Period>('6M')
  const [activeTab, setActiveTab] = useState<'pnl' | 'weekly' | 'daily'>('pnl')

  const { data: pnl, isLoading } = useQuery({
    queryKey: ['pnl', period],
    queryFn: () => fetchPnL(period),
  })

  const { data: tradeSummary } = useQuery({
    queryKey: ['trades-summary-perf', 30],
    queryFn: () => fetchTradesSummary(30),
    refetchInterval: 300000,
  })

  const { data: weekly, isLoading: weeklyLoading } = useQuery({
    queryKey: ['weekly-report'],
    queryFn: fetchWeeklyReport,
    retry: false,
    staleTime: 1000 * 60 * 60, // 1 hour — weekly report is static for 9 days
  })

  const daily = pnl?.daily ?? []
  const monthly = pnl?.monthly ?? []

  const cumulativeData = useMemo(() => {
    let cumPnL = 0
    return daily.map((d) => {
      cumPnL += d.profit_loss ?? 0
      return { date: d.date, cumulative: parseFloat(cumPnL.toFixed(2)), equity: d.equity }
    })
  }, [daily])

  return (
    <div style={{ position: 'relative' }}>
      <HelpButton title="Performance — Rendimento" sections={[
        {
          heading: "Come leggere i grafici",
          content: "**Cumulative P&L**: il profitto/perdita cumulativo nel periodo selezionato. Linea blu che sale = profitto, che scende = perdita.\n\n**Portfolio Equity**: il valore totale del portafoglio nel tempo. Linea verde.",
        },
        {
          heading: "Periodi disponibili",
          content: "1M, 3M, 6M, 1Y. I dati vengono dal worker di performance che gira ogni giorno alle 22:00 UTC. Se non vedi dati, potrebbe non esserci ancora un ciclo completo.",
        },
        {
          heading: "Monthly P&L Summary",
          content: "La tabella in basso mostra P&L mensile aggregato. ▲ Gain = mese positivo, ▼ Loss = mese negativo. Utile per verificare la consistenza del rendimento.",
        },
        {
          heading: "Trade Activity — metriche",
          content: "**Trades**: numero di trade chiusi nel periodo (30 giorni).\n**Trades/week**: frequenza annualizzata — es. 2.0 = 2 trade a settimana in media.\n**Win rate**: % di trade chiusi in profitto netto. >50% = sistema in vantaggio.\n**Avg net P&L**: P&L medio per trade al netto dei costi di transazione.\n**Total net P&L**: P&L cumulativo totale del periodo.\n**Avg hold**: durata media di una posizione in minuti.\n**Slippage % gross**: costi di esecuzione (spread + market impact) come % del P&L lordo — idealmente <20%.",
        },
        {
          heading: "Giornaliero — Metriche",
          content: "**W (Winners)**: trade chiusi con profitto netto positivo (net_pnl > 0).\n**L (Losers)**: trade chiusi in perdita (net_pnl < 0).\n**Net P&L**: somma dei net_pnl di tutti i trade chiusi in quella giornata. È il risultato reale dopo slippage e costi stimati — non l'equity Alpaca.\n**Profitti**: somma dei soli trade positivi (gross profit della giornata).\n**Perdite**: somma dei soli trade negativi (gross loss della giornata).\n**Win rate (KPI)**: Winners / totale trade nel periodo selezionato. >50% = più trade in guadagno che in perdita.\n**Giorni +/−**: numero di giornate con P&L netto positivo vs negativo nel range.\n\n**Nota**: i dati vengono dalla tabella `trades` locale, non da Alpaca. Piccole differenze vs P&L Storico (tab 1) sono normali perché Alpaca conta le variazioni di equity intraday incluse le posizioni aperte.",
        },
        {
          heading: "Report Settimanale — Trade P&L",
          content: "**Win rate**: percentuale di trade chiusi in profitto. Baseline attesa >50%.\n**P&L netto medio**: guadagno/perdita medio per trade dopo aver sottratto i costi di transazione.\n**Return on Notional (RON)**: P&L netto totale / capitale totale impiegato. Misura l'efficienza del capitale: 0.5% = hai guadagnato 50¢ ogni 100$ deployati.\n**Slippage medio**: stima del costo di esecuzione per trade (spread bid-ask + market impact).\n**Trade/settimana**: frequenza di trading annualizzata.",
        },
        {
          heading: "Report Settimanale — Costi & Capital Efficiency",
          content: "**avg_cost_bps**: costo medio di transazione in basis point (1 bps = 0.01%). Es. 5 bps = 0.05% del notional per trade.\n**Spread cost**: componente bid-ask del costo (sempre presente).\n**Market impact**: effetto che il tuo ordine ha sul prezzo — cresce con la dimensione dell'ordine.\n**Cost drag %**: costi totali / notional impiegato. Annualizzato dà la soglia minima di rendimento necessaria per coprire le spese.\n\n**Deployment %**: capitale investito in posizioni / valore totale del portafoglio. Basso = troppa liquidità inutilizzata.\n**Cash drag annual**: costo opportunità della liquidità non investita, stimato al 4.5% APY (T-bill). Es. 90% cash = perdi 4% l'anno di rendimento risk-free.\n**Efficiency ratio**: deployment reale / deployment teorico ottimale (50%).",
        },
        {
          heading: "Report Settimanale — Regime & Feedback",
          content: "**Regime**: stato del mercato rilevato dal modello — bear / caution / neutral / bull / strong_bull.\n**Multiplier (×N)**: fattore applicato all'entry threshold. ×0.7 in bear = threshold più alta, meno trade. ×1.3 in bull = threshold più bassa, più trade.\n**Deployment ceiling**: massima % di portafoglio allocabile in questo regime (es. 30% in bear, 90% in bull).\n**Capitale trattenuto vs bull**: quanta liquidità stiamo tenendo rispetto a un regime bull — il costo del regime di cautela.\n\n**Threshold corrente**: soglia minima di score per aprire un trade (baseline 0.30). Si alza automaticamente dopo serie di perdite.\n**Regime scale ×N**: ulteriore moltiplicatore sul capitale allocato per trade. ×0.8 = posizioni più piccole del normale.",
        },
      ]} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Performance</h2>
        <div style={{ display: 'flex', gap: 4 }}>
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              style={{
                padding: '4px 10px',
                fontSize: 12,
                background: period === p ? 'var(--blue)' : 'transparent',
                color: period === p ? 'white' : 'var(--text-muted)',
                border: '1px solid var(--border)',
              }}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, marginTop: 8 }}>
        {(['pnl', 'daily', 'weekly'] as const).map((t) => (
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
            {t === 'pnl' ? 'P&L Storico' : t === 'daily' ? 'Giornaliero' : 'Report Settimanale'}
          </button>
        ))}
      </div>

      {activeTab === 'pnl' && (
        <>
          {isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading...</p>}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>
            <div className="card">
              <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Cumulative P&L</h3>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={cumulativeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v}`} />
                  <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, 'Cumulative P&L']} />
                  <Line type="monotone" dataKey="cumulative" stroke="#3b82f6" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="card">
              <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Portfolio Equity</h3>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={cumulativeData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
                  <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, 'Equity']} />
                  <Line type="monotone" dataKey="equity" stroke="#16a34a" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Monthly P&L Summary</h3>
            <DataTable
              loading={isLoading}
              columns={[
                { label: 'Month',     width: '40%' },
                { label: 'P&L',       width: '30%' },
                { label: 'Direction', width: '30%' },
              ]}
              rows={monthly.map((m) => ({
                cells: [
                  m.month,
                  <span style={{ color: m.pnl >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                    {m.pnl >= 0 ? '+' : ''}${m.pnl.toFixed(2)}
                  </span>,
                  <span className={`badge ${m.pnl >= 0 ? 'badge-green' : 'badge-red'}`}>
                    {m.pnl >= 0 ? '▲ Gain' : '▼ Loss'}
                  </span>,
                ],
              }))}
              emptyMessage="No monthly data available."
            />
          </div>

          {tradeSummary && tradeSummary.total_trades > 0 && (
            <div style={{ marginTop: 32 }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 600 }}>Trade Activity (last 30d)</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
                  <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 12 }}>Summary</div>
                  {[
                    ['Trades', String(tradeSummary.total_trades)],
                    ['Trades/week', tradeSummary.trades_per_week.toFixed(1)],
                    ['Win rate', `${(tradeSummary.win_rate * 100).toFixed(1)}%`],
                    ['Avg net P&L', `$${tradeSummary.avg_net_pnl.toFixed(2)}`],
                    ['Total net P&L', `$${tradeSummary.total_net_pnl.toFixed(2)}`],
                    ['Avg hold', `${tradeSummary.avg_hold_minutes.toFixed(0)}min`],
                    ['Slippage % gross', `${(tradeSummary.slippage_pct_of_gross * 100).toFixed(1)}%`],
                  ].map(([label, value]) => (
                    <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #0f172a', fontSize: 13 }}>
                      <span style={{ color: '#64748b' }}>{label}</span>
                      <span style={{ fontWeight: 600 }}>{value}</span>
                    </div>
                  ))}
                </div>
                <div style={{ background: '#1e293b', borderRadius: 8, padding: 16 }}>
                  <div style={{ fontSize: 13, color: '#94a3b8', marginBottom: 12 }}>Notional & P&L</div>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart data={[
                      { label: 'Total Notional', value: tradeSummary.total_notional },
                      { label: 'Gross P&L', value: tradeSummary.total_gross_pnl },
                      { label: 'Net P&L', value: tradeSummary.total_net_pnl },
                    ]}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                      <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => `$${v}`} />
                      <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`]} />
                      <Bar dataKey="value" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}
        </>
      )}
      {activeTab === 'daily' && <DailyPnLTab />}
      {activeTab === 'weekly' && (
        <WeeklyReportTab weekly={weekly} isLoading={weeklyLoading} />
      )}
    </div>
  )
}
