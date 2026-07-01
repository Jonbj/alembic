import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { backtestApi } from '@/api/backtest'
import { HelpButton } from '@/components/shared/HelpButton'
import { KPICard } from '@/components/shared/KPICard'
import type { BacktestRun } from '@/api/backtest'

function fmt(v: number | null | undefined, decimals = 4): string {
  if (v == null) return '—'
  return Number(v).toFixed(decimals)
}

function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return (Number(v) * 100).toFixed(2) + '%'
}

type VerdictTone = 'good' | 'warn' | 'bad' | 'neutral'

function VerdictBox({ tone, title, details }: { tone: VerdictTone; title: string; details: string[] }) {
  const palette = {
    good: { bg: '#064e3b', border: '#059669', fg: '#bbf7d0' },
    warn: { bg: '#78350f', border: '#d97706', fg: '#fef3c7' },
    bad: { bg: '#7f1d1d', border: '#dc2626', fg: '#fecaca' },
    neutral: { bg: '#1e293b', border: '#334155', fg: '#cbd5e1' },
  }[tone]

  return (
    <div style={{ background: palette.bg, border: `1px solid ${palette.border}`, color: palette.fg, borderRadius: 8, padding: 16 }}>
      <div style={{ fontWeight: 800, marginBottom: 8 }}>{title}</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {details.map((detail) => (
          <span key={detail} style={{ fontSize: 12, fontWeight: 600 }}>{detail}</span>
        ))}
      </div>
    </div>
  )
}

function monotonicityScore(rows: { avg_return: number }[] | undefined): number | null {
  if (!rows || rows.length < 3) return null
  let increasingPairs = 0
  for (let i = 1; i < rows.length; i += 1) {
    if (Number(rows[i].avg_return) >= Number(rows[i - 1].avg_return)) increasingPairs += 1
  }
  return increasingPairs / (rows.length - 1)
}

function buildBacktestVerdict(summary: Awaited<ReturnType<typeof backtestApi.summary>> | undefined, buckets: { avg_return: number }[] | undefined) {
  if (!summary) {
    return { tone: 'neutral' as const, title: 'Verdict: waiting for evidence', details: ['summary not loaded yet'] }
  }

  const details: string[] = []
  let blockers = 0
  let warnings = 0
  const mono = monotonicityScore(buckets)

  if ((summary.n_scored ?? 0) < 1000) {
    warnings += 1
    details.push('sample below 1,000 scored signals')
  }
  if ((summary.ic ?? 0) < 0.05) {
    blockers += 1
    details.push('IC below 0.05 promotion threshold')
  }
  if ((summary.icir ?? 0) < 0.30) {
    warnings += 1
    details.push('ICIR below 0.30 stability threshold')
  }
  if ((summary.hit_rate ?? 0) < 0.50) {
    blockers += 1
    details.push('hit rate below 50% directional edge')
  }
  if ((summary.avg_long_return ?? 0) <= 0) {
    warnings += 1
    details.push('long bucket return not positive')
  }
  if ((summary.avg_short_return ?? 0) <= 0) {
    warnings += 1
    details.push('short bucket return not positive')
  }
  if (mono != null && mono < 0.60) {
    warnings += 1
    details.push('score buckets are not monotonic enough')
  }

  if (details.length === 0) details.push('meets current promotion evidence thresholds')
  if (blockers > 0) return { tone: 'bad' as const, title: 'Verdict: not enough evidence for promotion', details }
  if (warnings > 0) return { tone: 'warn' as const, title: 'Verdict: review before promotion', details }
  return { tone: 'good' as const, title: 'Verdict: promotion evidence acceptable', details }
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
  const verdict = buildBacktestVerdict(summary, bucketData)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, position: 'relative' }}>
      <HelpButton title="Backtest — Test Storici" sections={[
        {
          heading: "Cosa sono i backtest",
          content: "I backtest eseguono le strategie su dati storici per verificarne la validità predittiva. Ogni run processa un dataset di notizie, genera i segnali LLM, e misura quanto bene questi segnali predicono i rendimenti reali del giorno successivo (24h forward return).",
        },
        {
          heading: "KPI Cards — definizioni",
          content: "**IC (Information Coefficient)**: correlazione di Spearman tra il rank dello score LLM e il rank del rendimento reale a 24h. Valori: >0.05 = statisticamente significativo, >0.10 = ottimo, >0.15 = eccellente. Un IC di 0 significa predizione casuale.\n\n**ICIR (IC Information Ratio)**: IC medio / deviazione standard IC settimana per settimana. Misura la consistenza nel tempo. >0.3 = segnale stabile, >0.5 = molto consistente.\n\n**Hit Rate**: % di segnali con il segno corretto (score >0 e rendimento >0, oppure entrambi negativi). >50% = edge direzionale, >55% = buono.\n\n**Avg Long Return**: rendimento medio a 24h per i segnali con score >0.05. Dovrebbe essere positivo.\n\n**Avg Short Return**: rendimento medio per i segnali con score <-0.05, espresso come short. Dovrebbe essere positivo (rendimento negativo = short guadagna).\n\n**N Scored**: numero di segnali con rendimento forward disponibile — la dimensione effettiva del campione.",
        },
        {
          heading: "Score Bucket Analysis",
          content: "I segnali vengono ordinati per score e divisi in N bucket (5, 10, o 20) dal più basso al più alto. Ogni barra mostra il rendimento medio a 24h per quel bucket.\n\nUn modello valido mostra **rendimenti monotonicamente crescenti** da sinistra (score basso/bearish) a destra (score alto/bullish). Se i bucket centrali hanno rendimenti simili agli estremi, il modello non discrimina bene.\n\nPuoi scegliere il numero di bucket con i bottoni 5/10/20.",
        },
        {
          heading: "IC by Model / IC by Symbol",
          content: "Queste tabelle scompongono le performance per modello LLM e per ticker.\n\n**N**: numero di segnali disponibili per quel modello/ticker.\n**IC**: correlazione Spearman per quel sottoinsieme — modelli/ticker con IC >0 contribuiscono positivamente all'ensemble.\n**Hit Rate**: accuratezza direzionale per quel modello/ticker.\n**Avg Return**: rendimento medio a 24h per i segnali di quel modello/ticker. Utile per identificare quali ticker il modello capisce meglio.",
        },
        {
          heading: "Curva P&L simulata",
          content: "Simula una strategia long-short equal-weight applicando una soglia (threshold) allo score:\n\n**Long**: entra se score > threshold; **Short**: entra se score < -threshold.\n\n**Threshold**: puoi scegliere 0.02, 0.05 o 0.10. Threshold più alta = meno trade ma più selettivi.\n\n**Cum Long** (verde): P&L cumulativa della strategia solo-long.\n**Cum Short** (giallo): P&L della strategia solo-short.\n**Long-Short** (blu): P&L combinata — la vera misura del valore predittivo del modello.",
        },
        {
          heading: "Selezionare un run",
          content: "Usa il dropdown per scegliere tra i run disponibili. Il formato è: run_id — N scored / N total (es. 1250 scored = 1250 segnali con rendimento forward calcolato).",
        },
      ]} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>Backtest Analysis</h1>
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

      <VerdictBox {...verdict} />

      {/* KPI Cards */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <KPICard
          label="IC (Spearman)"
          value={fmt(summary?.ic)}
          sub="Information Coefficient"
          tooltip="Correlazione tra predizione del modello e rendimento reale. IC > 0.05 = utile, > 0.1 = ottimo."
        />
        <KPICard
          label="ICIR"
          value={fmt(summary?.icir)}
          sub={`${summary?.n_weeks ?? 0} weeks`}
          tooltip="IC diviso per la deviazione standard. ICIR > 0.3 = segnale consistente nel tempo."
        />
        <KPICard
          label="Hit Rate"
          value={pct(summary?.hit_rate)}
          sub="Directional accuracy"
          tooltip="Percentuale di volte che la direzione del segnale era corretta."
        />
        <KPICard
          label="Avg Long Return"
          value={pct(summary?.avg_long_return)}
          sub="score > 0.05"
          tooltip="Rendimento medio delle posizioni long (segnali con score > 0.05)."
        />
        <KPICard
          label="Avg Short Return"
          value={pct(summary?.avg_short_return)}
          sub="score < -0.05 (as short)"
          tooltip="Rendimento medio delle posizioni short (segnali con score < -0.05)."
        />
        <KPICard
          label="N Scored"
          value={(summary?.n_scored ?? 0).toLocaleString()}
          sub="Signals with forward return"
          tooltip="Numero di segnali con rendimento forward disponibile nel periodo di backtest."
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
