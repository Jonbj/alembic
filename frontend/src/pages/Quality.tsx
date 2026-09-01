import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchQualityEnsembleHealth,
  fetchQualityMetrics,
  fetchQualitySources,
} from '@/api/quality'
import { KPICard } from '@/components/shared/KPICard'
import { HelpButton } from '@/components/shared/HelpButton'
import { sourceVerdict } from './qualitySourceVerdict'

function n3(v: number | null | undefined): string {
  return v == null ? '—' : Number(v).toFixed(3)
}
function pct(v: number | null | undefined): string {
  return v == null ? '—' : (Number(v) * 100).toFixed(1) + '%'
}
function utcMinute(v: string): string {
  const date = new Date(v)
  return Number.isNaN(date.getTime())
    ? v
    : `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`
}

type VerdictTone = 'good' | 'warn' | 'bad' | 'neutral'

function VerdictBox({ tone, title, details }: { tone: VerdictTone; title: string; details: string[] }) {
  const palette = {
    good: { bg: '#dcfce7', border: '#86efac', fg: '#166534' },
    warn: { bg: '#fef9c3', border: '#fde68a', fg: '#854d0e' },
    bad: { bg: '#fee2e2', border: '#fca5a5', fg: '#991b1b' },
    neutral: { bg: '#f1f5f9', border: '#cbd5e1', fg: '#475569' },
  }[tone]

  return (
    <div style={{ background: palette.bg, border: `1px solid ${palette.border}`, color: palette.fg, borderRadius: 8, padding: 14, marginBottom: 16 }}>
      <div style={{ fontWeight: 800, marginBottom: 6 }}>{title}</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {details.map((detail) => (
          <span key={detail} style={{ fontSize: 12, fontWeight: 600 }}>{detail}</span>
        ))}
      </div>
    </div>
  )
}

function buildQualityVerdict(data: Awaited<ReturnType<typeof fetchQualityMetrics>>) {
  const details: string[] = []
  let risk = 0

  if ((data.signals.n ?? 0) < 50) {
    risk += 1
    details.push('sample too small for stable quality read')
  }
  if ((data.signals.near_zero_rate ?? 0) > 0.55) {
    risk += 1
    details.push('near-zero rate high: signal is mostly noise')
  }
  if ((data.signals.fallback_rate ?? 0) > 0.20) {
    risk += 1
    details.push('fallback rate high: primary model path degraded')
  }
  if ((data.signals.mean_ensemble_std ?? 0) > 0.40) {
    risk += 1
    details.push('ensemble divergence above discard threshold')
  }
  if (data.extraction.n_labeled < 30) {
    risk += 1
    details.push('needs more labels before trusting extraction metrics')
  } else {
    if ((data.extraction.precision ?? 1) < 0.80) {
      risk += 2
      details.push('ticker precision below 0.80: false positives likely')
    }
    if ((data.extraction.recall ?? 1) < 0.70) {
      risk += 1
      details.push('ticker recall below 0.70: missed tickers likely')
    }
    if ((data.extraction.macro_fp_per_article ?? 0) > 0.10) {
      risk += 1
      details.push('macro false positives are leaking into ticker labels')
    }
  }

  if (details.length === 0) details.push('no quality blocker detected in current window')
  if (risk >= 3) return { tone: 'bad' as const, title: 'Verdict: blocked for promotion', details }
  if (risk >= 1) return { tone: 'warn' as const, title: 'Verdict: usable with review', details }
  return { tone: 'good' as const, title: 'Verdict: quality acceptable', details }
}

export default function Quality() {
  const [days, setDays] = useState(14)
  const { data, isLoading, error } = useQuery({
    queryKey: ['quality-metrics', days],
    queryFn: () => fetchQualityMetrics(days),
    refetchInterval: 120000,
  })
  const sourcesQ = useQuery({
    queryKey: ['quality-sources', days],
    queryFn: () => fetchQualitySources(days),
    refetchInterval: 120000,
  })
  const ensembleHealthQ = useQuery({
    queryKey: ['quality-ensemble-health', days],
    queryFn: () => fetchQualityEnsembleHealth(days),
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
          <VerdictBox {...buildQualityVerdict(data)} />

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
            <KPICard label="Ensemble std medio" value={n3(data.signals.mean_ensemble_std)} sub="divergenza modelli" tooltip="Std medio delle polarità tra modelli (soglia discard 0.40; sulle righe fallback la std salvata è 0)." />
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

      <h3 style={{ fontSize: 14, fontWeight: 600, margin: '24px 0 8px' }}>Ensemble health</h3>
      {ensembleHealthQ.isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading…</p>}
      {ensembleHealthQ.error != null && <p style={{ color: 'var(--red)' }}>Error loading ensemble health</p>}
      {ensembleHealthQ.data && (() => {
        const health = ensembleHealthQ.data
        return (
          <>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
              <KPICard
                label="Full-ensemble share"
                value={pct(health.summary.full_ensemble_share)}
                sub={`${health.summary.total_ensemble ?? 0}/${health.summary.total_aggregate ?? 0} segnali`}
                tooltip="Quota dei segnali prodotti dall'ensemble completo nella finestra selezionata."
              />
              <KPICard
                label="Single-model rows"
                value={String(health.summary.total_single ?? 0)}
                sub="degradazione parziale"
                tooltip="Righe prodotte da un solo modello LLM disponibile."
              />
              <KPICard
                label="FinBERT rows"
                value={String(health.summary.total_finbert ?? 0)}
                sub="full fallback"
                tooltip="Righe prodotte dal fallback FinBERT durante un outage completo dell'ensemble."
              />
            </div>
            {health.cycles.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                Nessun ciclo misurato nella finestra selezionata.
              </p>
            ) : (
              <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
                <table aria-label="Full-ensemble share over time">
                  <thead>
                    <tr><th>Ciclo</th><th>Full-ensemble share</th><th>Ensemble</th><th>Single</th><th>FinBERT</th><th>RTH</th></tr>
                  </thead>
                  <tbody>
                    {health.cycles.slice(0, 48).map((cycle) => (
                      <tr key={cycle.cycle_started_at}>
                        <td>{utcMinute(cycle.cycle_started_at)}</td>
                        <td>{pct(cycle.aggregate > 0 ? cycle.n_ensemble / cycle.aggregate : null)}</td>
                        <td>{cycle.n_ensemble}</td>
                        <td>{cycle.n_single}</td>
                        <td>{cycle.n_finbert}</td>
                        <td>{cycle.rth ? 'sì' : 'no'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )
      })()}

      <h3 style={{ fontSize: 14, fontWeight: 600, margin: '24px 0 8px' }}>Source Funnel &amp; P&amp;L</h3>
      {sourcesQ.isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading…</p>}
      {sourcesQ.error != null && <p style={{ color: 'var(--red)' }}>Error loading source metrics</p>}
      {sourcesQ.data && (() => {
        const s = sourcesQ.data
        const names = Array.from(new Set([
          ...s.funnel.map((f) => f.source),
          ...s.signals.map((x) => x.source),
          ...s.trades.map((t) => t.source),
        ]))
        const toneColor: Record<string, string> = {
          good: 'var(--green, #166534)',
          warn: 'var(--amber, #d97706)',
          bad: 'var(--red, #991b1b)',
          neutral: 'var(--text-muted)',
        }
        return (
          <>
            <p style={{ color: 'var(--text-muted)', fontSize: 12, margin: '0 0 8px' }}>
              Trace coverage: {s.trace_coverage.linked ?? '—'}/{s.trace_coverage.total ?? '—'} segnali con fonte nota ·
              soglie rimozione (roadmap §7.4): hit&lt;40% ∧ P&amp;L&lt;0 · latenza p50&gt;24h · near-zero&gt;50%
            </p>
            {names.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>Nessun dato ancora — il funnel si popola coi run di ingestione.</p>
            ) : (
              <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Fonte</th><th>Fetched</th><th>Queued</th><th>Dup</th><th>No ticker</th><th>Stale</th><th>Parse fail</th>
                      <th>Segnali</th><th>Near-zero</th><th>Lat p50</th><th>Trade</th><th>Hit</th><th>P&amp;L</th><th>Verdetto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {names.map((name) => {
                      const f = s.funnel.find((x) => x.source === name)
                      const sig = s.signals.find((x) => x.source === name)
                      const trd = s.trades.find((x) => x.source === name)
                      const v = sourceVerdict({
                        hitRate: trd?.hit_rate ?? null,
                        totalPnl: trd?.total_net_pnl ?? null,
                        latencyP50Min: sig?.latency_p50_min ?? null,
                        nearZeroRate: sig?.near_zero_rate ?? null,
                      })
                      return (
                        <tr key={name}>
                          <td><strong>{name}</strong></td>
                          <td>{f?.fetched ?? '—'}</td>
                          <td>{f?.queued ?? '—'}</td>
                          <td>{f?.duplicates ?? '—'}</td>
                          <td>{f?.discarded_no_ticker ?? '—'}</td>
                          <td>{f?.discarded_stale ?? '—'}</td>
                          <td>{f?.parse_fail ?? '—'}</td>
                          <td>{sig?.n_signals ?? '—'}</td>
                          <td>{pct(sig?.near_zero_rate)}</td>
                          <td>{sig?.latency_p50_min != null ? `${Math.round(sig.latency_p50_min)}m` : '—'}</td>
                          <td>{trd?.n_trades ?? '—'}</td>
                          <td>{pct(trd?.hit_rate)}</td>
                          <td style={{ color: (trd?.total_net_pnl ?? 0) < 0 ? 'var(--red)' : undefined }}>
                            {trd?.total_net_pnl != null ? `$${Number(trd.total_net_pnl).toFixed(2)}` : '—'}
                          </td>
                          <td style={{ color: toneColor[v.tone], fontWeight: 700 }} title={v.reasons.join('; ')}>{v.tone}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )
      })()}
    </div>
  )
}
