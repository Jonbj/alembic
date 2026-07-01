import { useQuery } from '@tanstack/react-query'
import { fmtDateTime } from '@/utils/format'
import { fetchFeedbackStatus, fetchCounterfactualSummary, fetchCounterfactualStatus } from '@/api/trades'
import { HelpButton } from '@/components/shared/HelpButton'

const fmt = (v: number | null | undefined, digits = 2) =>
  v == null ? '—' : v.toFixed(digits)

const fmtPct = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`

const fmtSign = (v: number | null | undefined) => {
  if (v == null) return '—'
  const s = v >= 0 ? '+' : ''
  return `${s}${(v * 100).toFixed(2)}%`
}

const DECISION_STYLE: Record<string, { label: string; bg: string; fg: string; note: string }> = {
  SKIP_THRESHOLD: {
    label: 'Gate threshold',
    bg: 'rgba(245,158,11,0.15)',
    fg: '#d97706',
    note: 'Feedback gate blocked the signal because score was below the active entry threshold.',
  },
  SKIP_EMA: {
    label: 'EMA trend',
    bg: 'rgba(99,102,241,0.15)',
    fg: '#6366f1',
    note: 'Legacy trend filter blocked a candidate below EMA20.',
  },
  SKIP_CAP: {
    label: 'Cycle cap',
    bg: 'rgba(249,115,22,0.15)',
    fg: '#ea580c',
    note: 'Legacy cycle allocation cap blocked an otherwise valid candidate.',
  },
}

function decisionMeta(decision: string) {
  return DECISION_STYLE[decision] ?? {
    label: decision,
    bg: 'rgba(100,116,139,0.15)',
    fg: '#64748b',
    note: 'Skipped trade candidate.',
  }
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 600, color: 'var(--text-muted)' }}>
        {title}
      </h3>
      {children}
    </div>
  )
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: active ? '#f59e0b' : '#22c55e',
      marginRight: 6,
    }} />
  )
}

function PhaseCState({ status }: { status: ReturnType<typeof describePhaseCState> }) {
  return (
    <div style={{
      background: status.bg,
      border: `1px solid ${status.border}`,
      borderRadius: 8,
      padding: '10px 14px',
      marginBottom: 14,
      fontSize: 13,
    }}>
      <strong style={{ color: status.fg }}>{status.label}</strong>
      <span style={{ color: 'var(--text-muted)' }}> — {status.detail}</span>
    </div>
  )
}

function Stat({
  label, value, sub, highlight = false,
}: {
  label: string
  value: React.ReactNode
  sub?: string
  highlight?: boolean
}) {
  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: highlight ? '#f59e0b' : 'inherit' }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

const th: React.CSSProperties = { padding: '4px 12px 8px 0', fontWeight: 500 }
const td: React.CSSProperties = { padding: '8px 12px 8px 0' }

function describePhaseCState(status: Awaited<ReturnType<typeof fetchCounterfactualStatus>> | undefined) {
  if (!status) {
    return {
      label: 'Status unavailable',
      detail: 'Phase C metadata could not be loaded.',
      bg: 'rgba(100,116,139,0.10)',
      border: 'rgba(100,116,139,0.30)',
      fg: '#64748b',
    }
  }
  if (!status.worker) {
    return {
      label: 'Worker not observed',
      detail: 'No counterfactual-worker run metadata is present in Redis. The table may be empty because the worker has not run since this metadata was introduced.',
      bg: 'rgba(245,158,11,0.10)',
      border: 'rgba(245,158,11,0.35)',
      fg: '#d97706',
    }
  }
  if (status.worker.status === 'error') {
    return {
      label: 'Last worker run failed',
      detail: status.worker.reason || 'Check worker logs before trusting Phase C freshness.',
      bg: 'rgba(239,68,68,0.10)',
      border: 'rgba(239,68,68,0.35)',
      fg: '#dc2626',
    }
  }
  if (status.worker.status === 'skipped') {
    return {
      label: 'Last worker run skipped',
      detail: status.worker.reason || 'The worker did not process Phase C rows.',
      bg: 'rgba(245,158,11,0.10)',
      border: 'rgba(245,158,11,0.35)',
      fg: '#d97706',
    }
  }
  if (status.phase_c.total_skips === 0) {
    return {
      label: 'No Phase C skips in window',
      detail: 'The worker has run, but no SKIP_THRESHOLD, SKIP_EMA or SKIP_CAP decisions exist in the selected window.',
      bg: 'rgba(34,197,94,0.10)',
      border: 'rgba(34,197,94,0.30)',
      fg: '#16a34a',
    }
  }
  if (status.phase_c.pending > 0) {
    return {
      label: 'Skips pending nightly processing',
      detail: `${status.phase_c.pending} Phase C skip(s) still need 1h return computation. Next scheduled run: ${status.next_run_hint}.`,
      bg: 'rgba(59,130,246,0.08)',
      border: 'rgba(59,130,246,0.30)',
      fg: '#2563eb',
    }
  }
  return {
    label: 'Phase C processed',
    detail: `${status.phase_c.processed} skip(s) processed; ${status.phase_c.with_return} have available 1h return data.`,
    bg: 'rgba(34,197,94,0.10)',
    border: 'rgba(34,197,94,0.30)',
    fg: '#16a34a',
  }
}

export default function AutoImprove() {
  const { data: feedback, isLoading: fbLoading } = useQuery({
    queryKey: ['feedback-status'],
    queryFn: fetchFeedbackStatus,
    refetchInterval: 60_000,
  })

  const { data: counterfactual, isLoading: cfLoading } = useQuery({
    queryKey: ['counterfactual-7d'],
    queryFn: () => fetchCounterfactualSummary(7),
    refetchInterval: 300_000,
  })

  const { data: cfStatus, isLoading: cfStatusLoading } = useQuery({
    queryKey: ['counterfactual-status-7d'],
    queryFn: () => fetchCounterfactualStatus(7),
    refetchInterval: 300_000,
  })

  const phaseCState = describePhaseCState(cfStatus)

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 700 }}>Auto-Improve</h2>
      <p style={{ margin: '0 0 24px', color: 'var(--text-muted)', fontSize: 14 }}>
        Feedback gate status and counterfactual checks on skipped trade candidates.
      </p>
      <HelpButton title="Auto-Improve — Guida alla Lettura" sections={[
        {
          heading: "Cos'è Auto-Improve",
          content: 'Il sistema si auto-corregge in tre fasi:\n\n**Phase A** (Performance → Analytics): analizza il passato — dove guadagna e perde il sistema per simbolo, regime, ora, score e durata.\n**Phase B** (questa pagina, card sopra): reagisce alle perdite alzando la soglia di ingresso usata dal portfolio scheduler.\n**Phase C** (questa pagina, tabella sotto): misura retrospettivamente i candidati scartati da gate/filtri per capire se il sistema è troppo restrittivo.\n\nNessun intervento manuale richiesto: Phase B e C operano automaticamente.',
        },
        {
          heading: 'Phase B — Valori da Monitorare',
          content: '**Entry Threshold** (baseline 0.30): il portfolio scheduler entra in posizione solo se lo score supera questa soglia. Quando il feedback è attivo, può salire fino a 0.60 — il sistema diventa più selettivo.\n\n**Regime Scale** (normale 1.0×): è ancora esposto come stato Redis e resta consumato dal path legacy `execution.py`. Nel path portfolio corrente non deve essere interpretato come riduzione certa del sizing finché non viene cablato esplicitamente nel portfolio scheduler.',
        },
        {
          heading: 'Phase B — Trigger e Recovery',
          content: '**Trigger automatico** (OR logic):\n• 3 perdite consecutive, OPPURE\n• P&L rolling negativo sugli ultimi 10 trade\n\n**Cooldown**: 4 ore tra un aggiustamento e il successivo — evita che il sistema stringa troppo in una singola sessione.\n\n**Recovery**: 5 vincite consecutive riportano threshold e scale ai valori baseline.\n\n**Scadenza automatica**: ogni aggiustamento ha un TTL di 48 ore. Se il sistema non esegue abbastanza trade per la recovery, l\'aggiustamento scade da solo.',
        },
        {
          heading: 'Phase B — Cosa Fare Quando è Attivo',
          content: 'Se l\'aggiustamento è attivo **da più di 24 ore senza recovery**, valuta:\n\n1. **Pagina Signals** — confidence bassa sui segnali? I modelli LLM concordano poco?\n2. **Pagina Overview** — regime di mercato ribassista? HHI elevato (portfolio concentrato)?\n3. **Pagina News** — notizie macro avverse nel watchlist (es. earnings season, eventi Fed)?\n4. **Performance → Analytics** — quale ora, simbolo, score bucket o durata sta generando le perdite?\n\nSe il contesto è chiaramente avverso (mercato in sell-off, VIX elevato), considera di attivare manualmente la modalità Halted dalla pagina Admin.',
        },
        {
          heading: 'Phase C — Come Leggere la Tabella',
          content: '**SKIP_THRESHOLD**: segnale scartato dal feedback gate perché sotto la soglia attiva. È il caso più importante nel path portfolio.\n**SKIP_EMA** e **SKIP_CAP**: filtri legacy ancora supportati dai counterfactual.\n\n**SKIP_STALE** e **SKIP_FALLBACK** non sono inclusi: sono problemi di freshness/affidabilità del segnale, non opportunità da sbloccare abbassando un filtro.\n\n**Colonne chiave**:\n• **Skips**: quante volte il filtro ha bloccato un trade nel periodo\n• **Computed**: quanti skip hanno un ritorno a 1h calcolato\n• **Avg 1h return**: ritorno medio se avessimo aperto la posizione\n• **% Profitable**: percentuale di skip che sarebbero stati profittevoli\n• **Upside missed**: somma dei ritorni positivi',
        },
        {
          heading: 'Phase C — Interpretazione e Azioni',
          content: '**Avg 1h return verde + % profitable >50%** → il gate potrebbe essere troppo restrittivo. Per SKIP_THRESHOLD valuta la soglia solo insieme a IC/label evidence, non solo sul ritorno 1h.\n\n**Avg 1h return rosso** → il filtro sta evitando perdite. Non intervenire.\n\n**Upside missed alto con pochi skip** → possibilmente rumore statistico. Aspetta almeno 2 settimane di dati e almeno 30 osservazioni computate prima di modificare parametri.',
        },
        {
          heading: 'Phase C — Tempistica e Aggiornamento Dati',
          content: 'I ritorni a 1h vengono calcolati **nightly alle 22:45 UTC** dal task `counterfactual-worker`.\n\nI dati del giorno corrente appariranno il giorno successivo. Se la tabella è vuota, è normale nei primi giorni di paper trading.\n\n**Finestra temporale consigliata**:\n• 7 giorni: valutazione recente, ma statisticamente limitata\n• 30 giorni: trend affidabili per decisioni strutturali\n\nLa tabella si aggiorna ogni 5 minuti nell\'interfaccia.',
        },
      ]} />

      {/* Phase B: Loss Feedback */}
      <Card title="Phase B — Feedback Gate">
        {fbLoading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : !feedback ? (
          <p style={{ color: 'var(--text-muted)' }}>Unavailable</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', marginBottom: 16 }}>
              <Stat
                label="Entry Threshold"
                value={fmt(feedback.entry_threshold, 2)}
                sub={`baseline ${fmt(feedback.entry_threshold_baseline, 2)}`}
                highlight={feedback.adjustment_active && feedback.entry_threshold > feedback.entry_threshold_baseline}
              />
              <Stat
                label="Regime Scale"
                value={`${fmt(feedback.regime_scale, 2)}×`}
                sub={feedback.regime_scale < 1 ? 'legacy scale state' : 'normal'}
                highlight={feedback.regime_scale < 1}
              />
              <Stat
                label="Status"
                value={
                  <span style={{ fontSize: 16 }}>
                    <StatusDot active={feedback.adjustment_active} />
                    {feedback.adjustment_active ? 'Adjustment active' : 'At baseline'}
                  </span>
                }
                sub={feedback.last_reason ?? ''}
              />
            </div>

            {feedback.adjustment_active && (
              <div style={{
                background: 'rgba(245,158,11,0.10)',
                border: '1px solid rgba(245,158,11,0.3)',
                borderRadius: 8, padding: '10px 14px', fontSize: 13,
              }}>
                <strong>Last trigger:</strong>{' '}
                {feedback.consecutive_losses != null && `${feedback.consecutive_losses} consecutive losses`}
                {feedback.rolling_net_pnl != null && ` · rolling P&L $${feedback.rolling_net_pnl.toFixed(2)}`}
                {feedback.last_adjustment_ts && (
                  <span style={{ color: 'var(--text-muted)', marginLeft: 8 }}>
                    ({fmtDateTime(feedback.last_adjustment_ts)})
                  </span>
                )}
              </div>
            )}

            {feedback.regime_scale < 1 && (
              <div style={{
                background: 'rgba(59,130,246,0.08)',
                border: '1px solid rgba(59,130,246,0.25)',
                borderRadius: 8, padding: '10px 14px', fontSize: 13, marginTop: 10,
                color: 'var(--text-muted)',
              }}>
                Portfolio path note: the entry threshold is enforced by the scheduler.
                Regime scale is currently an audit/legacy execution state unless portfolio sizing is explicitly wired to it.
              </div>
            )}

            <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              Checked every 30 min during market hours. Raises the entry threshold after
              3 consecutive losses or negative rolling P&L (last 10 trades). Recovers after
              5 consecutive wins. Adjustments expire after 48 h.
            </p>
          </>
        )}
      </Card>

      {/* Phase C: Counterfactual / Opportunity Cost */}
      <Card title="Phase C — Gate Opportunity Cost (last 7 days)">
        {cfLoading || cfStatusLoading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : (
          <>
            <PhaseCState status={phaseCState} />

            <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', marginBottom: 16 }}>
              <Stat
                label="Last worker run"
                value={<span style={{ fontSize: 16 }}>{cfStatus?.worker?.last_run_at ? fmtDateTime(cfStatus.worker.last_run_at) : '—'}</span>}
                sub={cfStatus?.worker?.reason || cfStatus?.worker?.status || 'no metadata'}
              />
              <Stat
                label="Last processed row"
                value={<span style={{ fontSize: 16 }}>{cfStatus?.last_processed_at ? fmtDateTime(cfStatus.last_processed_at) : '—'}</span>}
                sub="MAX counterfactual_computed_at"
              />
              <Stat
                label="Raw Phase C skips"
                value={cfStatus?.phase_c.total_skips ?? 0}
                sub={`${cfStatus?.phase_c.pending ?? 0} pending · ${cfStatus?.phase_c.with_return ?? 0} with 1h return`}
                highlight={(cfStatus?.phase_c.pending ?? 0) > 0}
              />
            </div>

            {!counterfactual || counterfactual.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>
                No opportunity-cost rows are available yet. Use the status above and raw skip counts below
                to tell whether this is a true zero-skip window, pending nightly processing, or missing worker metadata.
              </p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                    <th style={th}>Decision</th>
                    <th style={th}>Skips</th>
                    <th style={th}>Computed</th>
                    <th style={th}>Avg 1h return</th>
                    <th style={th}>% Profitable</th>
                    <th style={th}>Upside missed</th>
                  </tr>
                </thead>
                <tbody>
                  {counterfactual.map(row => {
                    const meta = decisionMeta(row.decision)
                    return (
                      <tr key={row.decision} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={td}>
                          <div>
                            <span style={{
                              background: meta.bg,
                              color: meta.fg,
                              borderRadius: 4, padding: '2px 6px', fontSize: 11, fontWeight: 600,
                            }}>
                              {row.decision}
                            </span>
                            <div style={{ color: 'var(--text-muted)', fontSize: 11, marginTop: 3 }}>
                              {meta.label}
                            </div>
                          </div>
                        </td>
                        <td style={td}>{row.total_skips}</td>
                        <td style={td}>{row.computed}</td>
                        <td style={{ ...td, color: row.avg_return >= 0 ? '#4ade80' : '#f87171' }}>
                          {fmtSign(row.avg_return)}
                        </td>
                        <td style={td}>{fmtPct(row.pct_profitable)}</td>
                        <td style={{ ...td, color: row.sum_positive_returns > 0 ? '#f59e0b' : 'inherit' }}>
                          {fmtSign(row.sum_positive_returns)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}

            {(cfStatus?.raw_skip_counts.length ?? 0) > 0 && (
              <div style={{ marginTop: 18 }}>
                <h4 style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--text-muted)' }}>Raw skip counts</h4>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ color: 'var(--text-muted)', textAlign: 'left' }}>
                      <th style={th}>Decision</th>
                      <th style={th}>Raw</th>
                      <th style={th}>Processed</th>
                      <th style={th}>With return</th>
                      <th style={th}>Pending</th>
                      <th style={th}>Phase C</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cfStatus?.raw_skip_counts.map(row => (
                      <tr key={row.decision} style={{ borderTop: '1px solid var(--border)' }}>
                        <td style={td}>{row.decision}</td>
                        <td style={td}>{row.total}</td>
                        <td style={td}>{row.processed}</td>
                        <td style={td}>{row.with_return}</td>
                        <td style={{ ...td, color: row.pending > 0 ? '#f59e0b' : 'inherit' }}>{row.pending}</td>
                        <td style={td}>{row.included_in_phase_c ? 'included' : 'excluded'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              <strong>SKIP_THRESHOLD</strong> measures whether the active feedback gate is rejecting
              profitable candidates. <strong>SKIP_EMA</strong> and <strong>SKIP_CAP</strong> remain
              supported for legacy filter analysis. SKIP_STALE, SKIP_FALLBACK and SKIP_POSITION are
              excluded intentionally.
            </p>
          </>
        )}
      </Card>
    </div>
  )
}
