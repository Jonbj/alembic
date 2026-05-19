import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchConfig, updateConfig } from '@/api/config'

export default function Config() {
  const qc = useQueryClient()
  const { data: cfg, isLoading } = useQuery({ queryKey: ['config'], queryFn: fetchConfig })

  const [watchlist, setWatchlist] = useState<string[]>([])
  const [drawdown, setDrawdown] = useState(10)
  const [stopLoss, setStopLoss] = useState(0.05)
  const [newSymbol, setNewSymbol] = useState('')

  useEffect(() => {
    if (!cfg) return
    const symbols = (cfg as any)?.symbols?.watchlist ?? []
    setWatchlist(symbols)
    setDrawdown(((cfg as any)?.risk?.portfolio_drawdown ?? 0.1) * 100)
    setStopLoss((cfg as any)?.risk?.stop_loss ?? 0.05)
  }, [cfg])

  const saveMutation = useMutation({
    mutationFn: () => updateConfig({
      symbols: { watchlist },
      risk: { portfolio_drawdown: drawdown / 100, stop_loss: stopLoss },
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['config'] }),
  })

  if (isLoading) return <p style={{ color: 'var(--text-muted)' }}>Loading config...</p>

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Config</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Watchlist</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
            {watchlist.map((sym) => (
              <span key={sym} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: '#dbeafe', color: '#1d4ed8', borderRadius: 4, padding: '2px 8px', fontSize: 13, fontWeight: 600 }}>
                {sym}
                <button
                  onClick={() => setWatchlist((l) => l.filter((s) => s !== sym))}
                  style={{ background: 'none', color: '#1d4ed8', padding: '0 2px', fontSize: 14, lineHeight: 1 }}
                >×</button>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              placeholder="Add symbol..."
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newSymbol.trim()) {
                  setWatchlist((l) => [...new Set([...l, newSymbol.trim()])])
                  setNewSymbol('')
                }
              }}
              style={{ flex: 1 }}
            />
            <button className="btn-primary" onClick={() => {
              if (newSymbol.trim()) {
                setWatchlist((l) => [...new Set([...l, newSymbol.trim()])])
                setNewSymbol('')
              }
            }}>Add</button>
          </div>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Risk Parameters</h3>

          <label style={{ display: 'block', marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Max Drawdown: {drawdown.toFixed(0)}%</span>
            <input
              type="range" min={1} max={20} step={0.5}
              value={drawdown}
              onChange={(e) => setDrawdown(parseFloat(e.target.value))}
              style={{ width: '100%', marginTop: 6, border: 'none', padding: 0 }}
            />
          </label>

          <label style={{ display: 'block', marginBottom: 16 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Stop Loss</span>
            <input
              type="number" min={0.01} max={0.5} step={0.01}
              value={stopLoss}
              onChange={(e) => setStopLoss(parseFloat(e.target.value))}
              style={{ width: '100%', marginTop: 4 }}
            />
          </label>

          <button
            className="btn-primary"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving...' : '✓ Save Config'}
          </button>
          {saveMutation.isSuccess && <span style={{ color: 'var(--green)', fontSize: 12, marginLeft: 8 }}>Saved</span>}
          {saveMutation.isError && <span style={{ color: 'var(--red)', fontSize: 12, marginLeft: 8 }}>Error — check API key</span>}
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Full Config (read-only)</h3>
          <pre style={{ fontSize: 12, color: 'var(--text-muted)', overflow: 'auto', maxHeight: 300, background: '#f8fafc', padding: 12, borderRadius: 6 }}>
            {JSON.stringify(cfg, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  )
}
