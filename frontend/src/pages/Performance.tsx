import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer,
} from 'recharts'
import { fetchPnL, fetchWeeklyReport } from '@/api/performance'
import type { WeeklyReport } from '@/api/performance'
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

export default function Performance() {
  const [period, setPeriod] = useState<Period>('6M')
  const [activeTab, setActiveTab] = useState<'pnl' | 'weekly'>('pnl')

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
      {activeTab === 'weekly' && (
        <WeeklyReportTab weekly={weekly} isLoading={weeklyLoading} />
      )}
    </div>
  )
}
