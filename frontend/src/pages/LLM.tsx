import { useState } from 'react'
import { fmtDateTime } from '@/utils/format'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchLLMFeedback, fetchWeights, approveWeights } from '@/api/llm'
import { HelpButton } from '@/components/shared/HelpButton'

type Tab = 'feedback' | 'weights'

export default function LLM() {
  const [tab, setTab] = useState<Tab>('feedback')
  const [note, setNote] = useState('')
  const qc = useQueryClient()

  const { data: feedback = [], isLoading: fbLoading } = useQuery({
    queryKey: ['llm-feedback'],
    queryFn: () => fetchLLMFeedback({ limit: 100 }),
    refetchInterval: 300000,
  })

  const { data: weights, isLoading: wLoading } = useQuery({
    queryKey: ['weights'],
    queryFn: fetchWeights,
    refetchInterval: 300000,
  })

  const approveMutation = useMutation({
    mutationFn: () => approveWeights(note),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['weights'] }); setNote('') },
  })

  const tabStyle = (t: Tab) => ({
    padding: '8px 20px', cursor: 'pointer',
    borderBottom: tab === t ? '2px solid var(--blue)' : '2px solid transparent',
    color: tab === t ? 'var(--blue)' : 'var(--text-muted)',
    fontWeight: tab === t ? 600 : 400,
    background: 'none', borderRadius: 0,
  })

  function polarityBadge(p: number) {
    if (p > 0.1) return <span className="badge badge-green">▲ {p.toFixed(2)}</span>
    if (p < -0.1) return <span className="badge badge-red">▼ {p.toFixed(2)}</span>
    return <span className="badge badge-grey">— {p.toFixed(2)}</span>
  }

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>LLM</h2>
      <HelpButton title="LLM — Modelli e Pesi" sections={[
        {
          heading: "Feedback modelli — cosa è",
          content: "Mostra l'output grezzo di ogni modello LLM per ogni segnale generato. Ogni riga corrisponde alla risposta di un singolo modello per un ticker specifico, prima dell'aggregazione dell'ensemble.",
        },
        {
          heading: "Colonne — Feedback modelli",
          content: "**Ticker**: simbolo azionario analizzato.\n**Model**: identificatore del modello LLM (es. kimi-k2.6:cloud, glm-5.2:cloud).\n**Polarity**: direzione del sentiment da –1 (fortemente bearish) a +1 (fortemente bullish). Il badge mostra ▲ se >0.1, ▼ se <-0.1, — se neutro.\n**Confidence**: certezza del modello nella sua predizione (0–1). Un modello con polarity=+0.8 e confidence=0.9 è molto bullish e molto sicuro.\n**Divergenza σ**: deviazione standard tra le risposte dei diversi modelli nell'ensemble. Alta σ (>0.3) = i modelli sono in disaccordo → il segnale finale è meno affidabile e potrebbe usare il fallback FinBERT.\n**Fallback (FB)**: badge giallo = il modello primario ha fallito (timeout, errore di rete) o la divergenza era troppo alta → si è usato FinBERT come modello di backup.\n**Reasoning**: estratto del ragionamento del modello (troncato a 240 caratteri). Il testo completo è disponibile nel database.",
        },
        {
          heading: "Pesi ensemble — Active Weights",
          content: "I pesi attivi determinano quanto contribuisce ogni modello al segnale finale aggregato. Un modello con peso 0.40 (40%) ha il doppio dell'influenza di uno con peso 0.20 (20%).\n\nI pesi di default sono uniformi. Vengono aggiornati dal worker settimanale in base alla performance storica (pIC purificato per modello).",
        },
        {
          heading: "Pesi ensemble — Proposed Weights e approvazione",
          content: "Ogni lunedì alle 04:00 UTC il worker calcola i pesi ottimali basandosi sull'IC per modello delle ultime settimane. I pesi proposti rimangono in stato 'PENDING APPROVAL' finché non vengono approvati manualmente.\n\n**vs Active (Δ)**: differenza tra il peso proposto e quello corrente — verde se il peso sale, rosso se scende.\n\nClicca 'Approve — apply these weights' per attivare i nuovi pesi. L'approvazione è irreversibile (serve un nuovo ciclo del worker per generare una nuova proposta). Richiede API key valida.",
        },
      ]} />

      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        <button style={tabStyle('feedback')} onClick={() => setTab('feedback')}>Feedback modelli</button>
        <button style={tabStyle('weights')} onClick={() => setTab('weights')}>Pesi ensemble</button>
      </div>

      {tab === 'feedback' && (
        <div className="card" style={{ padding: 0 }}>
          {fbLoading && <p style={{ padding: 16, color: 'var(--text-muted)' }}>Loading...</p>}
          <table>
            <thead>
              <tr><th>Ticker</th><th>Model</th><th>Polarity</th><th>Confidence</th><th>Divergence σ</th><th>Fallback</th><th>Reasoning</th><th>Time</th></tr>
            </thead>
            <tbody>
              {feedback.map((f) => (
                <tr key={f.id}>
                  <td><strong>{f.symbol}</strong></td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{f.model_id}</td>
                  <td>{polarityBadge(f.polarity)}</td>
                  <td>{(f.confidence * 100).toFixed(0)}%</td>
                  <td>{f.ensemble_std?.toFixed(3) ?? '—'}</td>
                  <td>{f.fallback_used ? <span className="badge badge-yellow">FB</span> : '—'}</td>
                  <td style={{ maxWidth: 240, fontSize: 12, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.reasoning}
                  </td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{fmtDateTime(f.generated_at)}</td>
                </tr>
              ))}
              {feedback.length === 0 && !fbLoading && (
                <tr><td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No feedback data</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'weights' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div className="card">
            <h3 style={{ margin: '0 0 4px', fontSize: 14, fontWeight: 600 }}>Active Weights</h3>
            <p style={{ margin: '0 0 16px', fontSize: 12, color: 'var(--text-muted)' }}>
              These weights are currently live and applied to every ensemble signal.
            </p>
            {wLoading && <p style={{ color: 'var(--text-muted)' }}>Loading...</p>}
            {weights?.current && (
              <table>
                <thead><tr><th>Model</th><th>Weight</th></tr></thead>
                <tbody>
                  {Object.entries(weights.current).map(([model, w]) => (
                    <tr key={model}>
                      <td>{model}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: `${(w as number) * 100}%`, maxWidth: 80, height: 6, background: 'var(--blue)', borderRadius: 3 }} />
                          {((w as number) * 100).toFixed(1)}%
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card" style={{ border: weights?.suggested ? '1px solid var(--yellow, #f59e0b)' : undefined, background: weights?.suggested ? 'rgba(245,158,11,0.04)' : undefined }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Proposed Weights</h3>
              {weights?.suggested && (
                <span className="badge badge-yellow" style={{ fontSize: 11, padding: '2px 7px' }}>PENDING APPROVAL</span>
              )}
            </div>
            <p style={{ margin: '0 0 16px', fontSize: 12, color: 'var(--text-muted)' }}>
              Auto-computed by the system based on historical performance. Not yet active — click "Approve" to apply.
            </p>
            {weights?.suggested ? (
              <>
                <table>
                  <thead><tr><th>Model</th><th>Proposed</th><th>vs Active</th></tr></thead>
                  <tbody>
                    {Object.entries(weights.suggested).map(([model, w]) => {
                      const curr = (weights.current?.[model] ?? 0) as number
                      const delta = (w as number) - curr
                      return (
                        <tr key={model}>
                          <td>{model}</td>
                          <td>{((w as number) * 100).toFixed(1)}%</td>
                          <td style={{ color: delta > 0 ? 'var(--green)' : delta < 0 ? 'var(--red)' : 'var(--text-muted)' }}>
                            {delta > 0 ? '+' : ''}{(delta * 100).toFixed(1)}%
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {weights.note && <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>{weights.note}</p>}
                <div style={{ marginTop: 16 }}>
                  <input
                    placeholder="Approval note (optional)..."
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    style={{ width: '100%', marginBottom: 8 }}
                  />
                  <button
                    className="btn-primary"
                    onClick={() => approveMutation.mutate()}
                    disabled={approveMutation.isPending}
                  >
                    {approveMutation.isPending ? 'Approving...' : 'Approve — apply these weights'}
                  </button>
                  {approveMutation.isError && <p style={{ color: 'var(--red)', fontSize: 12 }}>Error — check API key</p>}
                </div>
              </>
            ) : (
              <p style={{ color: 'var(--text-muted)' }}>No pending proposal — weights are up to date.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
