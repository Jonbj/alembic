import { useState, useMemo, useRef, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fmtDateTime } from '@/utils/format'
import { sanitizeText } from '@/utils/sanitize'
import { useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { fetchSignals, type Signal } from '@/api/signals'
import { fetchDecisions, fetchFeedbackStatus, type Decision } from '@/api/trades'
import { DirectionBadge } from '@/components/shared/DirectionBadge'
import { HelpButton } from '@/components/shared/HelpButton'
import { DataTable } from '@/components/shared/DataTable'
import { SignalTraceLinks } from '@/components/shared/SignalTraceLinks'

const ROW_H = 40

const COLS = [
  { label: 'Ticker',     pct: 8 },
  { label: 'Direction',  pct: 9 },
  { label: 'Score',      pct: 8 },
  { label: 'Confidence', pct: 8 },
  { label: 'Model',      pct: 20 },
  { label: 'Fallback',   pct: 6 },
  { label: 'Time',       pct: 15 },
  { label: 'Usato',      pct: 14 },
  { label: 'Trace',      pct: 12 },
]

const GRID_TEMPLATE = COLS.map(c => `${c.pct}%`).join(' ')

export default function Signals() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [ticker, setTicker] = useState(searchParams.get('symbol') ?? '')
  const newsId = searchParams.get('news_id')
  const signalId = searchParams.get('signal_id')
  const decisionId = searchParams.get('decision_id')
  const [direction, setDirection] = useState('')
  const [tab, setTab] = useState<'signals' | 'decisions'>(searchParams.get('tab') === 'decisions' ? 'decisions' : 'signals')

  useEffect(() => {
    const nextTab = searchParams.get('tab') === 'decisions' ? 'decisions' : 'signals'
    setTab((current) => (current === nextTab ? current : nextTab))
    setTicker((current) => {
      const nextTicker = searchParams.get('symbol') ?? ''
      return current === nextTicker ? current : nextTicker
    })
  }, [searchParams])

  const { data: signals = [], isLoading, error } = useQuery({
    queryKey: ['signals', newsId, signalId],
    queryFn: () => fetchSignals({
      newsId: newsId ? Number(newsId) : undefined,
      signalId: signalId ? Number(signalId) : undefined,
    }),
    refetchInterval: 60000,
  })

  const { data: decisions = [], isLoading: decisionsLoading } = useQuery({
    queryKey: ['decisions', ticker, decisionId],
    queryFn: () => fetchDecisions(ticker || undefined, 100, decisionId ? Number(decisionId) : undefined),
    enabled: tab === 'decisions',
    refetchInterval: 60000,
  })

  // Live feedback gate threshold (loss-feedback). Signals with |score| >= this clear
  // the gate; below it they are dropped (see Decision Log → SKIP_THRESHOLD).
  const { data: feedback } = useQuery({
    queryKey: ['feedback-status'],
    queryFn: fetchFeedbackStatus,
    refetchInterval: 120000,
  })
  // #474: SKIP_THRESHOLD is S4's sentiment gate — read strategies.S4 explicitly.
  // Fallback = loss_feedback.threshold_baseline (config/trading.yaml), lo stesso
  // pavimento che usa _get_feedback_threshold quando la chiave Redis manca. Era 0.35,
  // un valore congiunturale di agosto: il gate vivo di S4 è 0.30.
  const gateThreshold = feedback?.strategies?.S4?.entry_threshold ?? 0.30

  const filtered = useMemo(() =>
    signals.filter((s: Signal) => {
      if (ticker && !s.symbol.toLowerCase().includes(ticker.toLowerCase())) return false
      if (direction === 'BUY' && s.score <= 0.1) return false
      if (direction === 'SELL' && s.score >= -0.1) return false
      if (direction === 'HOLD' && Math.abs(s.score) > 0.1) return false
      return true
    }),
    [signals, ticker, direction]
  )

  const scrollRef = useRef<HTMLDivElement>(null)
  // TanStack Virtual intentionally returns non-memoizable functions; React Compiler
  // skips this component while virtualization remains correct at runtime.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_H,
    overscan: 8,
  })
  const virtualItems = virtualizer.getVirtualItems()

  const DECISION_LABELS: Record<string, string> = {
    BUY: 'BUY',
    SELL: 'SELL',
    SKIP_EMA: 'Skip — below EMA',
    SKIP_CAP: 'Skip — cycle cap',
    SKIP_POSITION: 'Skip — position open',
    SKIP_THRESHOLD: 'Skip — sotto soglia',
    SKIP_STALE: 'Skip — segnale scaduto',
  }

  const updateTraceParams = (nextTab: 'signals' | 'decisions', nextTicker = ticker) => {
    const next = new URLSearchParams(searchParams)
    if (nextTab === 'decisions') next.set('tab', 'decisions')
    else next.delete('tab')
    if (nextTicker.trim()) next.set('symbol', nextTicker.trim().toUpperCase())
    else next.delete('symbol')
    setSearchParams(next, { replace: true })
  }

  const updateTicker = (value: string) => {
    setTicker(value)
    updateTraceParams(tab, value)
  }

  const updateTab = (nextTab: 'signals' | 'decisions') => {
    setTab(nextTab)
    updateTraceParams(nextTab)
  }

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Signals</h2>
      <HelpButton title="Signals — Guida completa" sections={[
        {
          heading: "Cosa sono i segnali",
          content: "I segnali sono l'output del modello LLM ensemble. Per ogni ticker nel watchlist, i modelli della coppia attiva (configurabile — oggi glm-5.2 + gpt-oss:20b) generano un sentiment score da -1 (bearish forte) a +1 (bullish forte), con confidence 0-1. Il sistema aggrega i punteggi ponderati per produrre il segnale finale.",
        },
        {
          heading: "Colonne — Signals",
          content: "**Ticker**: il simbolo azionario (es. NVDA, AAPL).\n**Direction**: basata sullo score — BUY (score > 0.1), SELL (score < -0.1), HOLD (|score| ≤ 0.1).\n**Score**: valore da -1 a +1. |score| > 0.3 è significativo, > 0.6 è forte.\n**Confidence**: da 0 a 1. Indica quanto è certo il modello. Alta confidence = segnale affidabile.\n**Model**: identificatore del modello LLM che ha generato il segnale (es. ensemble:glm-5.2:cloud+gpt-oss:20b-cloud, oppure finbert per i fallback).\n**FB**: badge giallo = il modello fallback (FinBERT) è stato usato perché il modello primario ha fallito o divergeva troppo.\n\n_Selezione per ticker_: nella finestra di freschezza (4h) il ciclo usa il segnale **ensemble più recente**; un FB debole generato dopo un ensemble forte non lo sovrascrive (il fallback si usa solo se non c'è ensemble fresco). Fra due segnali ensemble vince comunque **il più recente, non il più forte** — è il comportamento discusso in #169.\n\n_Attenzione allo score mostrato qui_: è lo score **grezzo** salvato in sentiment_signals. Il gate d'ordine confronta lo score **dopo** il moltiplicatore di signal velocity (×1.20 o ×0.80 quando la variazione sulle ultime 3 voci di history supera 0.30, #401): un segnale può quindi passare o essere scartato a un valore diverso da quello in tabella.",
        },
        {
          heading: "Decision Log — cosa è",
          content: "Il Decision Log registra le decisioni prese dal portfolio scheduler ad ogni ciclo (ogni 15 min). Non ogni segnale genera un ordine: il sistema applica filtri aggiuntivi prima di inviare ordini ad Alpaca.",
        },
        {
          heading: "Trace",
          content: "La colonna Trace mostra solo collegamenti con dati realmente presenti: Signal porta al segnale storico esatto, Decision alla decisione esatta e Orders all'ordine broker esatto. \"—\" significa che quella conseguenza non esiste o non è tracciata, non un errore di caricamento.",
        },
        {
          heading: "Colonne — Decision Log",
          content: "**Tick Time**: timestamp del ciclo in cui è stata presa la decisione.\n**Symbol**: ticker azionario.\n**Weight**: peso percentuale assegnato nel portafoglio (es. 2.0% = 2% del NAV).\n**Decision**: esito. Sotto `engine=portfolio` esistono **sei** codici, questi e nessun altro:\n• **BUY** — ordine inviato ad Alpaca\n• **SELL** — uscita: ribilanciamento, contro-segnale (`sentiment_reversal`) o peso a zero. Il perché sta in `exit_mechanism`\n• **SKIP_THRESHOLD** — sotto la soglia del feedback gate `feedback:entry_threshold:S4` (vedi Reason per score e soglia: così i giorni senza trade non sono un log vuoto)\n• **SKIP_STALE** — segnale più vecchio di `max_signal_age_hours` (4h)\n• **SKIP_FALLBACK** — segnale prodotto da FinBERT in fallback, escluso dal ranking BUY (#108)\n• **SKIP_PYRAMIDING** — simbolo già a libro: il guard P0-05 blocca il secondo BUY, anche quando servirebbe solo a riportare la posizione a peso (#230/#491)\n\n`SKIP_EMA`, `SKIP_CAP` e `SKIP_POSITION` appartengono al path `legacy_sentiment` e **non sono mai stati emessi** dal path vivo: se li vedi citati altrove, è documentazione vecchia.\n\nIl ledger completo per intento (`s4_intent_events.reason_code`) ha più granularità — `CANDIDATE_OBSERVED`, `SKIP_ENTRY_FRESHNESS`, `SKIP_ENTRY_GATE`, `SKIP_IDEMPOTENCY`, `RANK_*`, `SUBMITTED` — e non è questa tabella.\n**Order ID**: ID dell'ordine Alpaca se la decisione era BUY; vuoto altrimenti.\n**Reason**: testo esplicativo con score, modello usato, e reasoning LLM abbreviato.",
        },
        {
          heading: "Filtri",
          content: "Usa il campo di testo per filtrare per ticker e il dropdown per direzione (BUY/SELL/HOLD). La lista segnali è virtualizzata per gestire migliaia di segnali senza rallentare.",
        },
      ]} />

      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid #334155' }}>
        {(['signals', 'decisions'] as const).map(t => (
          <button
            key={t}
            onClick={() => updateTab(t)}
            style={{
              padding: '8px 20px', border: 'none', cursor: 'pointer',
              background: 'transparent',
              color: tab === t ? '#3b82f6' : '#64748b',
              borderBottom: tab === t ? '2px solid #3b82f6' : '2px solid transparent',
              fontWeight: tab === t ? 600 : 400, fontSize: 14,
              textTransform: 'capitalize',
            }}
          >{t === 'signals' ? 'Signals' : 'Decision Log'}</button>
        ))}
      </div>

      {tab === 'decisions' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              value={ticker}
              onChange={e => updateTicker(e.target.value)}
              placeholder="Filter symbol…"
              style={{ padding: '6px 10px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: 'white', fontSize: 13, width: 140 }}
            />
          </div>
          <DataTable
            loading={decisionsLoading}
            columns={[
              { label: 'Tick Time',    width: '13%' },
              { label: 'Symbol',       width: '7%' },
              { label: 'Weight',       width: '7%' },
              { label: 'Decision',     width: '8%' },
              { label: 'Segnale →Δ',  width: '10%' },
              { label: 'Order ID',     width: '10%' },
              { label: 'Trace',        width: '9%' },
              { label: 'Reason',       width: 'auto' },
            ]}
            rows={(decisions as Decision[]).map(d => {
              let signalLag: string = '—'
              if (d.signal_generated_at && d.tick_time) {
                const lagMs = new Date(d.tick_time).getTime() - new Date(d.signal_generated_at).getTime()
                const lagMin = Math.round(lagMs / 60000)
                const lagH = Math.floor(Math.abs(lagMin) / 60)
                const lagM = Math.abs(lagMin) % 60
                signalLag = lagH > 0 ? `+${lagH}h${lagM}m` : `+${lagMin}m`
              }
              return {
                cells: [
                  <span style={{ color: 'var(--text-muted)' }}>{d.tick_time.slice(0, 16).replace('T', ' ')}</span>,
                  <strong>{d.symbol}</strong>,
                  `${(d.score * 100).toFixed(1)}%`,
                  <span style={{
                    color: d.decision === 'BUY' ? 'var(--green)' : d.decision === 'SELL' ? 'var(--red)' : 'var(--text-muted)',
                    fontWeight: ['BUY', 'SELL'].includes(d.decision) ? 600 : 400,
                  }}>{DECISION_LABELS[d.decision] ?? d.decision}</span>,
                  <span title={d.signal_generated_at ? `Segnale generato: ${fmtDateTime(d.signal_generated_at)}` : undefined}
                    style={{ color: 'var(--text-muted)', fontSize: 11, fontVariantNumeric: 'tabular-nums' }}>
                    {signalLag}
                  </span>,
                  <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{d.order_id ?? '—'}</span>,
                  <SignalTraceLinks
                    symbol={d.symbol}
                    compact
                    includeNews={false}
                    includeDecision={false}
                    includePerformance={false}
                    availability={{
                      newsId: d.news_log_id ?? undefined,
                      signalId: d.signal_id ?? undefined,
                      orderId: d.order_id ?? undefined,
                      signalCount: d.signal_id ? 1 : 0,
                      orderCount: d.order_id ? 1 : 0,
                    }}
                    emptyMessage="—"
                  />,
                  <span style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.4 }}>{sanitizeText(d.reason ?? '')}</span>,
                ],
              }
            })}
            emptyMessage="No decisions logged yet."
          />
          {decisionId && (
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              marginTop: 12,
              padding: '8px 10px',
              border: '1px solid var(--border)',
              borderRadius: 6,
              background: '#f8fafc',
              color: 'var(--text-muted)',
              fontSize: 12,
            }}>
              <span>Showing decision #{decisionId}.</span>
              <button
                className="btn-ghost"
                onClick={() => {
                  const next = new URLSearchParams(searchParams)
                  next.delete('decision_id')
                  setSearchParams(next, { replace: true })
                }}
                style={{ fontSize: 12, padding: '4px 8px' }}
              >
                Show latest decisions
              </button>
            </div>
          )}
        </div>
      )}

      {tab === 'signals' && (
      <>

      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input placeholder="Filter ticker..." value={ticker} onChange={(e) => updateTicker(e.target.value)} style={{ width: 160 }} />
        <select value={direction} onChange={(e) => setDirection(e.target.value)}>
          <option value="">All directions</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
          <option value="HOLD">HOLD</option>
        </select>
        <span style={{ color: 'var(--text-muted)', alignSelf: 'center', fontSize: 12 }}>{filtered.length} signals</span>
        <span style={{ alignSelf: 'center', fontSize: 12, marginLeft: 'auto', color: 'var(--text-muted)' }}>
          Feedback gate: <strong style={{ color: 'var(--text)' }}>{gateThreshold.toFixed(2)}</strong>
          {' · '}<span style={{ color: '#059669', fontWeight: 700 }}>verde ✓</span> = |score| ≥ soglia (supera il gate)
        </span>
      </div>
      {(newsId || signalId) && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          marginBottom: 12,
          padding: '8px 10px',
          border: '1px solid var(--border)',
          borderRadius: 6,
          background: '#f8fafc',
          color: 'var(--text-muted)',
          fontSize: 12,
        }}>
          <span>
            {signalId
              ? `Showing historical signal #${signalId}.`
              : `Showing historical signals generated by news #${newsId}.`}
          </span>
          <button
            className="btn-ghost"
            onClick={() => {
              const next = new URLSearchParams(searchParams)
              next.delete('news_id')
              next.delete('signal_id')
              next.delete('decision_id')
              setSearchParams(next, { replace: true })
            }}
            style={{ fontSize: 12, padding: '4px 8px' }}
          >
            Show latest signals
          </button>
        </div>
      )}

      <div className="card" style={{ padding: 0 }}>
        {isLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
        {error && <p style={{ padding: 16, color: 'var(--red)' }}>Error loading signals</p>}

        {/* Single scroll container — header is sticky inside it */}
        <div
          ref={scrollRef}
          style={{ maxHeight: 520, overflowY: 'auto' }}
        >
          {/* Sticky header */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: GRID_TEMPLATE,
              padding: '0 12px',
              fontWeight: 600,
              fontSize: 11,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
              color: 'var(--text-muted)',
              borderBottom: '1px solid var(--border)',
              position: 'sticky',
              top: 0,
              background: 'var(--bg-primary, #0f172a)',
              zIndex: 2,
            }}
          >
            {COLS.map(c => <div key={c.label}>{c.label}</div>)}
          </div>

          {/* Virtualized rows — width: 100% is CRITICAL for absolute-positioned grid children */}
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
            {virtualItems.map((vr) => {
              const s = filtered[vr.index]
              return (
                <div
                  key={vr.key}
                  data-index={vr.index}
                  ref={virtualizer.measureElement}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: GRID_TEMPLATE,
                    padding: '0 12px',
                    alignItems: 'center',
                    height: ROW_H,
                    borderBottom: '1px solid var(--border)',
                    position: 'absolute',
                    top: 0,
                    width: '100%',
                    transform: `translateY(${vr.start}px)`,
                  }}
                >
                  <div><strong>{s.symbol}</strong></div>
                  <div><DirectionBadge score={s.score} /></div>
                  <div style={{
                    fontVariantNumeric: 'tabular-nums',
                    ...(Math.abs(s.score) >= gateThreshold
                      ? { color: '#059669', fontWeight: 700 }
                      : { color: 'var(--text-muted)' }),
                  }}>
                    {s.score.toFixed(4)}{Math.abs(s.score) >= gateThreshold ? ' ✓' : ''}
                  </div>
                  <div>{(s.confidence * 100).toFixed(1)}%</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{s.model_id}</div>
                  <div>{s.fallback_used ? <span className="badge badge-yellow">FB</span> : '—'}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{fmtDateTime(s.generated_at)}</div>
                  <div>
                    {s.used_in_decision === true ? (
                      <span title={`Decisione: ${s.decision_type} alle ${s.decision_at ? fmtDateTime(s.decision_at) : '?'}`} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 4,
                        color: s.decision_type === 'BUY' ? 'var(--green)' : s.decision_type === 'SELL' ? 'var(--red)' : 'var(--text-muted)',
                        fontSize: 11, fontWeight: 600,
                      }}>
                        ✓ {s.decision_type}
                        {s.decision_at && (
                          <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>
                            {new Date(s.decision_at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </span>
                    ) : s.used_in_decision === false ? (
                      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
                    )}
                  </div>
                  <div>
                    <SignalTraceLinks
                      symbol={s.symbol}
                      compact
                      includeNews={false}
                      includeSignal={false}
                      includePerformance={false}
                      availability={{
                        decisionId: s.decision_id ?? undefined,
                        decisionCount: s.used_in_decision ? 1 : 0,
                        orderCount: ['BUY', 'SELL'].includes(s.decision_type ?? '') ? 1 : 0,
                      }}
                      emptyMessage="—"
                    />
                  </div>
                </div>
              )
            })}
          </div>
          {filtered.length === 0 && !isLoading && (
            <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)' }}>No signals</div>
          )}
        </div>
      </div>
      </>
      )}
    </div>
  )
}
