import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchValidationMetrics } from '@/api/validation'
import { KPICard } from '@/components/shared/KPICard'
import { HelpButton } from '@/components/shared/HelpButton'

function pct(v: number | null | undefined): string {
  return v == null ? '—' : (v * 100).toFixed(1) + '%'
}
function usd(v: number | null | undefined): string {
  return v == null ? '—' : (v < 0 ? '-$' : '$') + Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })
}

function regimeLabel(m: number | null): string {
  if (m == null) return 'unknown'
  if (m >= 0.95) return 'bull (×1.0)'
  if (m >= 0.65) return `sideways (×${m})`
  if (m >= 0.35) return `bear (×${m})`
  return `high-vol (×${m})`
}

export default function Validation() {
  const [days, setDays] = useState(7)
  const { data, isLoading, error } = useQuery({
    queryKey: ['validation-metrics', days],
    queryFn: () => fetchValidationMetrics(days),
    refetchInterval: 60_000,
  })

  return (
    <div style={{ position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Paper Validation</h2>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={1}>Last 1d</option>
          <option value={7}>Last 7d</option>
          <option value={30}>Last 30d</option>
          <option value={90}>Last 90d</option>
        </select>
      </div>
      <HelpButton title="Paper Validation — monitoraggio controlled paper" sections={[
        { heading: 'A cosa serve', content: 'Vista di salute del paper run: quanto capitale è schierato (deployment), quanto si fa turnover/churn, PnL realizzato netto costi, e il moltiplicatore di regime in vigore. Sostituisce le query SQL manuali durante i 90 giorni.' },
        { heading: 'Deployment & Regime', content: 'Deployment % = notional aperto / NAV. È limitato dal regime_mult: ×0.2 high-vol → ×1.0 bull. Se è basso e regime_mult=×0.2, controlla che regime:current sia popolato.' },
        { heading: 'Churn', content: 'Roundtrip = simboli aperti più volte nella finestra. Tanti roundtrip + hold medio basso = over-trading. L\'isteresi di uscita (2 cicli) dovrebbe tenerlo basso.' },
      ]} />

      {isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading...</p>}
      {error && <p style={{ color: 'var(--red)' }}>Error loading validation metrics</p>}

      {data && (
        <>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            <KPICard label="Deployment" value={pct(data.deployment_pct)} sub={`NAV ${usd(data.nav)}`} tooltip="Notional aperto / NAV. Limitato dal regime multiplier." />
            <KPICard label="Regime mult" value={data.regime_mult != null ? `×${data.regime_mult}` : '—'} sub={regimeLabel(data.regime_mult)} tooltip="Moltiplicatore di sizing in vigore (regime:current)." />
            <KPICard label="Net PnL (realized)" value={usd(data.pnl.realized_net_pnl)} sub={`cost drag ${usd(data.pnl.cost_drag)}`} tooltip="PnL realizzato netto costi sui trade chiusi." />
            <KPICard label="Win rate" value={data.pnl.win_rate != null ? pct(data.pnl.win_rate) : '—'} sub={`${data.pnl.closed_trades} closed · ${data.pnl.open_trades} open`} tooltip="Frazione di trade chiusi con net PnL > 0." />
            <KPICard label="Turnover" value={data.turnover.turnover_ratio != null ? data.turnover.turnover_ratio.toFixed(2) + '×' : '—'} sub={`traded ${usd(data.turnover.traded_notional)}`} tooltip="Notional totale scambiato / NAV nella finestra." />
            <KPICard label="Churn" value={`${data.churn.roundtrip_count} roundtrip`} sub={`avg hold ${data.churn.avg_hold_minutes != null ? Math.round(data.churn.avg_hold_minutes) + 'm' : '—'}`} tooltip="Simboli aperti più volte. Hold medio basso = over-trading." />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
            <div className="card">
              <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Round-trip symbols (churn)</h3>
              {Object.keys(data.churn.roundtrip_symbols).length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Nessun roundtrip nella finestra ✓</p>
              ) : (
                <table><tbody>
                  {Object.entries(data.churn.roundtrip_symbols).map(([sym, n]) => (
                    <tr key={sym}><td><strong>{sym}</strong></td><td style={{ textAlign: 'right' }}>{n}× aperto</td></tr>
                  ))}
                </tbody></table>
              )}
            </div>
            <div className="card">
              <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Exit reasons</h3>
              {Object.keys(data.exits).length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Nessun trade chiuso nella finestra</p>
              ) : (
                <table><tbody>
                  {Object.entries(data.exits).map(([reason, n]) => (
                    <tr key={reason}>
                      <td><span className={`badge ${reason === 'stop_loss' ? 'badge-red' : 'badge-grey'}`}>{reason}</span></td>
                      <td style={{ textAlign: 'right' }}>{n}</td>
                    </tr>
                  ))}
                </tbody></table>
              )}
            </div>
          </div>

          <p style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 16 }}>
            Aggiornato: {new Date(data.generated_at).toLocaleString()} · finestra {data.window_days}g · auto-refresh 60s
          </p>
        </>
      )}
    </div>
  )
}
