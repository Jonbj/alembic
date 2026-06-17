import { useQuery } from '@tanstack/react-query'
import { fmtDateTime } from '@/utils/format'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { fetchSignals } from '@/api/signals'
import { fetchPositions } from '@/api/positions'
import { fetchPnL } from '@/api/performance'
import { KPICard } from '@/components/shared/KPICard'
import { DirectionBadge } from '@/components/shared/DirectionBadge'
import { HelpButton } from '@/components/shared/HelpButton'

export default function Overview() {
  const { data: signals = [] } = useQuery({ queryKey: ['signals'], queryFn: () => fetchSignals(), refetchInterval: 60000 })
  const { data: positions = [] } = useQuery({ queryKey: ['positions'], queryFn: fetchPositions, refetchInterval: 60000 })
  const { data: pnl } = useQuery({ queryKey: ['pnl'], queryFn: () => fetchPnL('6M'), refetchInterval: 300000 })

  const buys = signals.filter((s) => s.score > 0.1).length
  const sells = signals.filter((s) => s.score < -0.1).length
  const holds = signals.length - buys - sells

  const totalUnrealized = positions.reduce((acc, p) => acc + (p.unrealized_pl || 0), 0)
  const monthlyPnL = pnl?.monthly ?? []
  const currentMonthPnL = monthlyPnL[monthlyPnL.length - 1]?.pnl ?? 0

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Overview</h2>
      <HelpButton title="Overview — Dashboard" sections={[
        {
          heading: "Cos'è questa pagina",
          content: "La dashboard riassume lo stato attuale del sistema: P&L mensile, posizioni aperte, P&L non realizzato e segnali recenti. I dati si aggiornano automaticamente ogni 60 secondi.",
        },
        {
          heading: "Come leggere le KPI cards",
          content: "**Net P&L (month)**: il profitto/perdita netto del mese corrente, basato sul P&L giornaliero Alpaca. Aggiornato ogni 5 minuti.\n\n**Open positions**: numero di posizioni attualmente aperte su Alpaca. Il sottotitolo elenca i ticker (es. AVGO, MU, NVDA).\n\n**Unrealized P&L**: profitto/perdita fluttuante totale delle posizioni ancora aperte. Non è un guadagno realizzato finché le posizioni non vengono chiuse.\n\n**Signals today**: formato \"XB / YS / ZH\" — X segnali BUY (score > 0.1), Y SELL (score < -0.1), Z HOLD (|score| ≤ 0.1). Il numero totale include tutti i ticker nel watchlist che hanno un segnale attivo.",
        },
        {
          heading: "Grafico Monthly P&L",
          content: "Barre mensili del P&L di portafoglio. Verde = mese in profitto, rosso = mese in perdita.\n\nUtile per identificare stagionalità, periodi di drawdown, e la consistenza del rendimento nel tempo. I dati provengono da Alpaca e coprono gli ultimi 6 mesi.",
        },
        {
          heading: "Tabelle Open Positions e Latest Signals",
          content: "**Open Positions**: lista compatta delle posizioni aperte con qty, P&L assoluto e P&L percentuale.\n\n**Latest Signals**: ultimi 10 segnali LLM generati, con direzione (BUY/SELL/HOLD), score (-1 a +1), confidence (0-100%), modello usato e orario di generazione. Questi segnali guidano le decisioni del portfolio scheduler al ciclo successivo.",
        },
        {
          heading: "Flusso consigliato",
          content: "1. Controlla Overview per il quadro generale\n2. Vai su Signals per i dettagli dei segnali e il Decision Log\n3. Verifica su Trading le posizioni e gli ordini\n4. Su Strategies controlla lo stato delle strategie validate\n5. Su Performance analizza il P&L storico e i costi",
        },
      ]} />

      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        <KPICard label="Net P&L (month)" value={`$${currentMonthPnL.toFixed(2)}`} sub="current month" tooltip="Profitto/perdita netto del mese corrente." />
        <KPICard label="Open positions" value={String(positions.length)} sub={positions.map((p) => p.symbol).join(', ') || '—'} tooltip="Numero di posizioni attualmente aperte e relativi ticker." />
        <KPICard label="Unrealized P&L" value={`$${totalUnrealized.toFixed(2)}`} tooltip="Profitto/perdita fluttuante delle posizioni ancora aperte." />
        <KPICard label="Signals today" value={`${buys}B / ${sells}S / ${holds}H`} sub={`${signals.length} total`} tooltip="Segnali odierni: B (buy, score > 0.1), S (sell, score < -0.1), H (hold)." />
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
          <thead><tr><th>Ticker</th><th>Direction</th><th>Score</th><th>Confidence</th><th>Model</th><th>Time</th></tr></thead>
          <tbody>
            {signals.slice(0, 10).map((s, i) => (
              <tr key={i}>
                <td><strong>{s.symbol}</strong></td>
                <td><DirectionBadge score={s.score} /></td>
                <td>{s.score.toFixed(3)}</td>
                <td>{(s.confidence * 100).toFixed(0)}%</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{s.model_id}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{fmtDateTime(s.generated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}