import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchNextLabel, fetchLabelProgress, submitLabel } from '@/api/labeling'
import { fmtDateTime } from '@/utils/format'
import { sanitizeText } from '@/utils/sanitize'
import { HelpButton } from '@/components/shared/HelpButton'

const RELEVANCE = ['company_specific', 'sector', 'macro', 'irrelevant'] as const
const TICKER_RE = /^[A-Z][A-Z0-9.-]{0,9}$/

function Btn({ active, onClick, children, color }: { active: boolean; onClick: () => void; children: React.ReactNode; color?: string }) {
  return (
    <button onClick={onClick} style={{
      padding: '6px 12px', borderRadius: 6, fontSize: 13, cursor: 'pointer',
      border: `1px solid ${active ? (color || 'var(--blue)') : '#334155'}`,
      background: active ? (color || 'var(--blue)') : 'transparent',
      color: active ? 'white' : 'var(--text-muted)', fontWeight: active ? 600 : 400,
    }}>{children}</button>
  )
}

export default function Labeling() {
  const [tickers, setTickers] = useState('')
  const [relevance, setRelevance] = useState<string>('')
  const [direction, setDirection] = useState<string>('')
  const [strength, setStrength] = useState(0)
  const [rationale, setRationale] = useState('')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const { data: progress, refetch: refetchProgress } = useQuery({ queryKey: ['label-progress'], queryFn: fetchLabelProgress })
  const { data: item, refetch: refetchItem, isFetching } = useQuery({ queryKey: ['label-next'], queryFn: fetchNextLabel })

  const reset = useCallback(() => {
    setTickers(''); setRelevance(''); setDirection(''); setStrength(0); setRationale(''); setErr('')
  }, [])

  const selectRelevance = (next: string) => {
    setRelevance(next)
    if (next === 'irrelevant' || next === 'macro') {
      setTickers('')
      if (!direction) {
        setDirection('neutral')
        setStrength(0)
      }
    }
  }

  const selectDirection = (next: string) => {
    setDirection(next)
    setStrength((current) => {
      if (next === 'neutral') return 0
      if (next === 'positive' && current <= 0) return 0.1
      if (next === 'negative' && current >= 0) return -0.1
      return current
    })
  }

  const parsedTickers = tickers.split(',').map((t) => t.trim().toUpperCase()).filter(Boolean)
  const validationErrors = [
    !relevance ? 'Seleziona la rilevanza.' : '',
    !direction ? 'Seleziona la direzione del sentiment.' : '',
    relevance === 'company_specific' && parsedTickers.length === 0
      ? 'Le news company-specific richiedono almeno un ticker.'
      : '',
    parsedTickers.some((ticker) => !TICKER_RE.test(ticker))
      ? 'Usa ticker validi separati da virgola, ad esempio AAPL, BRK.B.'
      : '',
    (relevance === 'macro' || relevance === 'irrelevant') && parsedTickers.length > 0
      ? 'Macro e irrilevante devono avere ticker vuoto.'
      : '',
    direction === 'positive' && strength <= 0 ? 'Il sentiment positive richiede forza > 0.' : '',
    direction === 'negative' && strength >= 0 ? 'Il sentiment negative richiede forza < 0.' : '',
    direction === 'neutral' && strength !== 0 ? 'Il sentiment neutral richiede forza 0.' : '',
  ].filter(Boolean)
  const canSave = validationErrors.length === 0 && !saving
  const showValidation = Boolean(relevance || direction || tickers || strength !== 0)

  const save = async () => {
    if (!item?.label_id || !canSave) return
    setSaving(true); setErr('')
    try {
      await submitLabel(item.label_id, {
        gt_tickers: parsedTickers, gt_relevance: relevance, gt_sentiment_dir: direction,
        gt_sentiment_strength: strength, gt_rationale: rationale, annotator_id: 'operator',
      })
      reset()
      await Promise.all([refetchItem(), refetchProgress()])
    } catch (e) {
      setErr(String(e))
    } finally {
      setSaving(false)
    }
  }

  const pct = progress ? Math.round((progress.labeled / Math.max(1, progress.total)) * 100) : 0

  return (
    <div style={{ maxWidth: 860 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Labeling — Golden Set (QX-01)</h2>
        {progress && <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>{progress.labeled}/{progress.total} ({pct}%) · {progress.pending} rimanenti</span>}
      </div>
      <HelpButton title="Labeling — annotazione blind" sections={[
        { heading: 'Cosa fare', content: 'Leggi titolo + testo (NON vedi il ticker estratto dal sistema — annotazione blind). Indica: i ticker che la news riguarda davvero (vuoto se macro/irrilevante), la rilevanza, la direzione e la forza del sentiment. ~30-60s a news.' },
        { heading: 'Forza', content: '0 = neutro/debole · ±0.2-0.6 = moderato · ±0.6-1 = forte. Per direzione "neutral" lascia 0.' },
        { heading: 'Forward return', content: 'Calcolati automaticamente da Alpaca dopo l\'annotazione — non li devi inserire tu.' },
      ]} />

      {item?.done ? (
        <div className="card" style={{ marginTop: 16, textAlign: 'center', padding: 32 }}>
          <p style={{ fontSize: 16, fontWeight: 600 }}>🎉 Tutte le news annotate!</p>
          <p style={{ color: 'var(--text-muted)' }}>Il golden set è completo. Calcolo forward return + metriche.</p>
        </div>
      ) : item && (
        <>
          <div className="card" style={{ marginTop: 16 }}>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>
              <span className="badge badge-grey">{item.source}</span>{' '}
              {item.published_at ? fmtDateTime(item.published_at) : '—'}
              {item.text_adequacy === 'headline_only' && <span style={{ marginLeft: 8, color: 'var(--amber, #d97706)' }}>solo titolo</span>}
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>{sanitizeText(item.title)}</div>
            {item.body_snippet && <p style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--text)' }}>{sanitizeText(item.body_snippet)}</p>}
          </div>

          <div className="card" style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Ticker (separati da virgola, vuoto se nessuno)</label>
              <input value={tickers} onChange={(e) => setTickers(e.target.value)} placeholder="es. AAPL, MSFT"
                style={{ width: '100%', marginTop: 4 }} disabled={relevance === 'irrelevant' || relevance === 'macro'} />
            </div>
            <div>
              <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Rilevanza</label>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {RELEVANCE.map((r) => <Btn key={r} active={relevance === r} onClick={() => selectRelevance(r)}>{r}</Btn>)}
              </div>
            </div>
            <div>
              <label style={{ fontSize: 13, fontWeight: 600, display: 'block', marginBottom: 4 }}>Direzione sentiment</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <Btn active={direction === 'positive'} onClick={() => selectDirection('positive')} color="#059669">positive</Btn>
                <Btn active={direction === 'neutral'} onClick={() => selectDirection('neutral')}>neutral</Btn>
                <Btn active={direction === 'negative'} onClick={() => selectDirection('negative')} color="#dc2626">negative</Btn>
              </div>
            </div>
            <div>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Forza: {strength.toFixed(1)}</label>
              <input type="range" min={-1} max={1} step={0.1} value={strength}
                onChange={(e) => setStrength(Number(e.target.value))}
                disabled={direction === 'neutral'}
                style={{ width: '100%' }} />
            </div>
            <div>
              <label style={{ fontSize: 13, fontWeight: 600 }}>Motivazione (opzionale)</label>
              <input value={rationale} onChange={(e) => setRationale(e.target.value)} style={{ width: '100%', marginTop: 4 }} />
            </div>
            {showValidation && validationErrors.length > 0 && (
              <div style={{ color: 'var(--red)', fontSize: 12, lineHeight: 1.6 }}>
                {validationErrors.map((message) => <div key={message}>{message}</div>)}
              </div>
            )}
            {err && <p style={{ color: 'var(--red)', fontSize: 12 }}>{err}</p>}
            <button onClick={save} disabled={!canSave}
              style={{ background: canSave ? 'var(--blue)' : '#334155', color: 'white', padding: '10px', fontWeight: 600, fontSize: 14 }}>
              {saving ? 'Salvataggio…' : 'Salva e continua →'}
            </button>
          </div>
        </>
      )}
      {isFetching && !item && <p style={{ color: 'var(--text-muted)', marginTop: 16 }}>Loading…</p>}
    </div>
  )
}
