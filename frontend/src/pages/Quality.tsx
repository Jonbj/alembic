import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchQualityMetrics } from '@/api/quality'
import { KPICard } from '@/components/shared/KPICard'
import { HelpButton } from '@/components/shared/HelpButton'

function n3(v: number | null | undefined): string {
  return v == null ? '—' : Number(v).toFixed(3)
}
function pct(v: number | null | undefined): string {
  return v == null ? '—' : (Number(v) * 100).toFixed(1) + '%'
}

export default function Quality() {
  const [days, setDays] = useState(14)
  const { data, isLoading, error } = useQuery({
    queryKey: ['quality-metrics', days],
    queryFn: () => fetchQualityMetrics(days),
    refetchInterval: 120000,
  })

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Quality — Sentiment & Extraction</h2>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>7d</option>
          <option value={14}>14d</option>
          <option value={30}>30d</option>
        </select>
      </div>
      <HelpButton title="Quality — qualità del segnale" sections={[
        { heading: 'A cosa serve', content: 'Mostra empiricamente i problemi di qualità del sentiment (polarity/confidence per modello, near-zero rate, fallback/divergence) e l\'estrazione ticker (precision/recall dal golden label set).' },
        { heading: 'Cosa guardare', content: 'Polarity media lontana da 0 = bias del modello. Confidence compressa ~0.65 = poco discriminante. Near-zero rate alto = molti segnali rumore. Precision estrazione bassa = troppi ticker falsi.' },
      ]} />

      {isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading…</p>}
      {error && <p style={{ color: 'var(--red)' }}>Error loading quality metrics</p>}

      {data && (
        <>
          <h3 style={{ fontSize: 14, fontWeight: 600, margin: '8px 0' }}>Sentiment per modello</h3>
          <div className="card" style={{ padding: 0 }}>
            <table>
              <thead><tr><th>Modello</th><th>N</th><th>Polarity media</th><th>Confidence media</th><th>Near-zero</th><th>Eligible</th></tr></thead>
              <tbody>
                {data.per_model.map((m) => (
                  <tr key={m.model_id}>
                    <td><strong>{m.model_id}</strong></td>
                    <td>{m.n}</td>
                    <td style={{ color: Math.abs(m.mean_polarity ?? 0) > 0.1 ? 'var(--amber, #d97706)' : undefined }}>
                      {n3(m.mean_polarity)} {Math.abs(m.mean_polarity ?? 0) > 0.1 ? '⚠ bias' : ''}
                    </td>
                    <td>{n3(m.mean_confidence)}</td>
                    <td>{pct(m.near_zero_rate)}</td>
                    <td>{pct(m.eligible_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h3 style={{ fontSize: 14, fontWeight: 600, margin: '16px 0 8px' }}>Segnali ensemble</h3>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <KPICard label="Near-zero rate" value={pct(data.signals.near_zero_rate)} sub={`${data.signals.n ?? 0} segnali`} tooltip="Frazione di segnali con |score|<0.05 — rumore che non clearera la soglia." />
            <KPICard label="Fallback rate" value={pct(data.signals.fallback_rate)} sub="FinBERT fallback" tooltip="Frazione di segnali da FinBERT (timeout/divergenza/budget)." />
            <KPICard label="Ensemble std medio" value={n3(data.signals.mean_ensemble_std)} sub="divergenza modelli" tooltip="Std medio delle polarità tra modelli (soglia discard 0.30)." />
            <KPICard label="Score medio" value={n3(data.signals.mean_score)} sub={`std ${n3(data.signals.std_score)}`} tooltip="polarity × confidence medio." />
          </div>

          <h3 style={{ fontSize: 14, fontWeight: 600, margin: '16px 0 8px' }}>Estrazione ticker (golden label set QX-01)</h3>
          {data.extraction.n_labeled === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Nessuna news annotata ancora — vai su Labeling.</p>
          ) : (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <KPICard label="Precision" value={n3(data.extraction.precision)} sub={`${data.extraction.n_labeled} annotate`} tooltip="ticker corretti / ticker estratti. Basso = molti falsi positivi." />
              <KPICard label="Recall" value={n3(data.extraction.recall)} sub={`in-WL ${n3(data.extraction.recall_in_watchlist)}`} tooltip="ticker veri trovati / ticker veri (in-WL = solo quelli in watchlist)." />
              <KPICard label="FP / articolo" value={n3(data.extraction.fp_per_article)} sub="falsi positivi" tooltip="Ticker falsi medi per articolo." />
              <KPICard label="Macro-FP / art" value={n3(data.extraction.macro_fp_per_article)} sub="dovrebbe ≈0" tooltip="Ticker estratti su news macro/irrilevanti — il problema del fallback watchlist (QT-01)." />
            </div>
          )}
          <p style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 16 }}>Finestra {data.window_days}g · auto-refresh 2 min</p>
        </>
      )}
    </div>
  )
}
