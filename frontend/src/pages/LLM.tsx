import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchLLMFeedback, fetchWeights, approveWeights } from '@/api/llm'

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
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>LLM</h2>

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
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{new Date(f.generated_at).toLocaleString()}</td>
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
            <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Current Weights</h3>
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

          <div className="card">
            <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Suggested Weights</h3>
            {weights?.suggested ? (
              <>
                <table>
                  <thead><tr><th>Model</th><th>Suggested</th><th>Δ vs Current</th></tr></thead>
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
                    {approveMutation.isPending ? 'Approving...' : '✓ Approve Weights'}
                  </button>
                  {approveMutation.isError && <p style={{ color: 'var(--red)', fontSize: 12 }}>Error — check API key</p>}
                </div>
              </>
            ) : (
              <p style={{ color: 'var(--text-muted)' }}>No pending suggestion</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
