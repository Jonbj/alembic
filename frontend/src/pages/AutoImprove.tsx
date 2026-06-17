import { useQuery } from '@tanstack/react-query'
import { fmtDateTime } from '@/utils/format'
import { fetchFeedbackStatus, fetchCounterfactualSummary } from '@/api/trades'
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

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 700 }}>Auto-Improve</h2>
      <p style={{ margin: '0 0 24px', color: 'var(--text-muted)', fontSize: 14 }}>
        Automatic strategy adjustments triggered by live performance.
      </p>
      <HelpButton title="Auto-Improve — Guida alla Lettura" sections={[
        {
          heading: "Cos'è Auto-Improve",
          content: 'Il sistema si auto-corregge in tre fasi:\n\n**Phase A** (tab Analytics in Trades): analizza il passato — dove guadagna e perde il sistema per dimensione.\n**Phase B** (questa pagina, card sopra): reagisce alle perdite in tempo reale — alza le soglie di ingresso e riduce l\'esposizione quando il sistema sta perdendo.\n**Phase C** (questa pagina, tabella sotto): valuta le opportunità mancate — analizza retrospettivamente i trade filtrati per capire se i filtri sono troppo restrittivi.\n\nNessun intervento manuale richiesto: Phase B e C operano automaticamente.',
        },
        {
          heading: 'Phase B — Valori da Monitorare',
          content: '**Entry Threshold** (baseline 0.30): il sistema entra in posizione solo se lo score LLM supera questa soglia. Quando il feedback è attivo, può salire fino a 0.60 — il sistema diventa più selettivo (meno trade, ma filtrati meglio).\n\n**Regime Scale** (normale 1.0×): moltiplica il regime_mult di ogni ciclo. Con scale=0.80, un regime_mult di 1.20 diventa effettivamente 0.96 — position sizing ridotto del 20%.\n\nEsempio pratico: se threshold=0.45 e scale=0.80, solo segnali forti entrano in posizione e con sizing ridotto.',
        },
        {
          heading: 'Phase B — Trigger e Recovery',
          content: '**Trigger automatico** (OR logic):\n• 3 perdite consecutive, OPPURE\n• P&L rolling negativo sugli ultimi 10 trade\n\n**Cooldown**: 4 ore tra un aggiustamento e il successivo — evita che il sistema stringa troppo in una singola sessione.\n\n**Recovery**: 5 vincite consecutive riportano threshold e scale ai valori baseline.\n\n**Scadenza automatica**: ogni aggiustamento ha un TTL di 48 ore. Se il sistema non esegue abbastanza trade per la recovery, l\'aggiustamento scade da solo.',
        },
        {
          heading: 'Phase B — Cosa Fare Quando è Attivo',
          content: 'Se l\'aggiustamento è attivo **da più di 24 ore senza recovery**, valuta:\n\n1. **Pagina Signals** — confidence bassa sui segnali? I modelli LLM concordano poco?\n2. **Pagina Overview** — regime di mercato ribassista? HHI elevato (portfolio concentrato)?\n3. **Pagina News** — notizie macro avverse nel watchlist (es. earnings season, eventi Fed)?\n4. **Analytics tab in Trades** — quale ora o simbolo sta generando le perdite?\n\nSe il contesto è chiaramente avverso (mercato in sell-off, VIX elevato), considera di attivare manualmente la modalità Halted dalla pagina Admin.',
        },
        {
          heading: 'Phase C — Come Leggere la Tabella',
          content: '**SKIP_EMA**: trade saltati perché il prezzo era sotto la EMA20 (filtro trend-following). La EMA evita di comprare in downtrend.\n**SKIP_CAP**: trade saltati perché il limite di allocazione del ciclo era stato raggiunto (troppi trade in un singolo ciclo orario).\n\n**Colonne chiave**:\n• **Skips**: quante volte il filtro ha bloccato un trade nel periodo\n• **Computed**: quanti skip hanno un ritorno a 1h calcolato (dipende dalla disponibilità di dati Alpaca)\n• **Avg 1h return**: ritorno medio se avessimo aperto la posizione\n• **% Profitable**: percentuale di skip che sarebbero stati profittevoli\n• **Upside missed**: somma dei ritorni positivi — opportunità economica persa',
        },
        {
          heading: 'Phase C — Interpretazione e Azioni',
          content: '**Avg 1h return verde + % profitable >50%** → il filtro sta bloccando trade profittevoli. Considera:\n• Per SKIP_EMA: abbassare o disabilitare il filtro EMA (parametro in Config).\n• Per SKIP_CAP: aumentare il cap di allocazione per ciclo.\n\n**Avg 1h return rosso** → il filtro funziona correttamente, stai evitando perdite. Non intervenire.\n\n**Upside missed alto con pochi skip** → possibilmente rumore statistico. Aspetta almeno 2 settimane di dati (>50 skip per tipo) prima di modificare i parametri.\n\n**Regola pratica**: agisci solo se avg_return >+0.5% e % profitable >55% su almeno 30 osservazioni.',
        },
        {
          heading: 'Phase C — Tempistica e Aggiornamento Dati',
          content: 'I ritorni a 1h vengono calcolati **nightly alle 22:45 UTC** dal task `counterfactual-worker`.\n\nI dati del giorno corrente appariranno il giorno successivo. Se la tabella è vuota, è normale nei primi giorni di paper trading.\n\n**Finestra temporale consigliata**:\n• 7 giorni: valutazione recente, ma statisticamente limitata\n• 30 giorni: trend affidabili per decisioni strutturali\n\nLa tabella si aggiorna ogni 5 minuti nell\'interfaccia.',
        },
      ]} />

      {/* Phase B: Loss Feedback */}
      <Card title="Phase B — Loss Feedback Loop">
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
                sub={feedback.regime_scale < 1 ? 'reduced by feedback' : 'normal'}
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

            <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              Checked every 30 min during market hours. Raises threshold after 3 consecutive losses
              or negative rolling P&L (last 10 trades). Recovers after 5 consecutive wins.
              Adjustments expire after 48 h.
            </p>
          </>
        )}
      </Card>

      {/* Phase C: Counterfactual / Opportunity Cost */}
      <Card title="Phase C — Opportunity Cost (last 7 days)">
        {cfLoading ? (
          <p style={{ color: 'var(--text-muted)' }}>Loading…</p>
        ) : !counterfactual || counterfactual.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>
            No data yet — counterfactual returns are computed nightly at 22:45 UTC.
            Data will appear after the first day of paper trading.
          </p>
        ) : (
          <>
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
                {counterfactual.map(row => (
                  <tr key={row.decision} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={td}>
                      <span style={{
                        background: row.decision === 'SKIP_EMA'
                          ? 'rgba(99,102,241,0.15)' : 'rgba(249,115,22,0.15)',
                        color: row.decision === 'SKIP_EMA' ? '#818cf8' : '#fb923c',
                        borderRadius: 4, padding: '2px 6px', fontSize: 11, fontWeight: 600,
                      }}>
                        {row.decision}
                      </span>
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
                ))}
              </tbody>
            </table>

            <p style={{ margin: '12px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
              <strong>SKIP_EMA</strong>: price was below EMA20 — would the trade have been profitable
              anyway? <strong>SKIP_CAP</strong>: cycle allocation cap was hit — what did we leave on
              the table? <em>Upside missed</em> = sum of positive 1-hour returns across all skipped
              signals. SKIP_POSITION (already open) is excluded.
            </p>
          </>
        )}
      </Card>
    </div>
  )
}
