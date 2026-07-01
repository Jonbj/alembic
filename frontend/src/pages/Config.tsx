import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchConfig, updateConfig, type ConfigResponse } from '@/api/config'
import { HelpButton } from '@/components/shared/HelpButton'
import { RiskParamWarning } from '@/components/shared/RiskParamWarning'
import { AccessibleModal } from '@/components/shared/AccessibleModal'

export default function Config() {
  const qc = useQueryClient()
  const { data: cfg, isLoading } = useQuery<ConfigResponse>({ queryKey: ['config'], queryFn: fetchConfig })

  const [watchlist, setWatchlist] = useState<string[]>([])
  const [drawdown, setDrawdown] = useState(10)
  const [stopLoss, setStopLoss] = useState(0.05)
  const [newSymbol, setNewSymbol] = useState('')
  // F0-3: confirmation dialog before saving high-risk values
  const [saveConfirmOpen, setSaveConfirmOpen] = useState(false)

  useEffect(() => {
    if (!cfg) return
    // Pre-existing pattern: sync server config into local editing state on load.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setWatchlist(cfg.symbols?.watchlist ?? [])
    setDrawdown((cfg.risk?.portfolio_drawdown ?? 0.1) * 100)
    setStopLoss(cfg.risk?.stop_loss ?? 0.05)
  }, [cfg])

  const saveMutation = useMutation({
    mutationFn: () => updateConfig({
      symbols: { watchlist },
      risk: { portfolio_drawdown: drawdown / 100, stop_loss: stopLoss },
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['config'] }),
  })

  // F0-3: gate save behind confirmation when values exceed safety thresholds
  const isHighRisk = stopLoss > 0.10 || drawdown > 10

  const handleSaveClick = () => {
    if (isHighRisk) {
      setSaveConfirmOpen(true)
      return
    }
    saveMutation.mutate()
  }

  if (isLoading) return <p style={{ color: 'var(--text-muted)' }}>Loading config...</p>

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Config</h2>
      <HelpButton title="Config — Configurazione" sections={[
        {
          heading: "Watchlist",
          content: "I ticker nel watchlist sono quelli monitorati dal sistema per generare segnali. Aggiungi con il campo di testo (premi Enter o clicca Add), rimuovi cliccando la × sul badge.",
        },
        {
          heading: "Risk Parameters",
          content: "**Max Drawdown**: soglia percentuale di drawdown del portafoglio. Se superata, il killswitch si attiva automaticamente. Valore tipico: 5-10%. Valori >10% sono ad alto rischio.\n\n**Stop Loss**: la perdita massima per singola posizione. Quando il P&L scende sotto questa soglia, la posizione viene chiusa automaticamente. Valore tipico: 2-5%. Valori >10% sono ad alto rischio e richiedono conferma.\n\n⚠ Questi parametri sono per paper trading e preflight. Non autorizzano il live trading.",
        },
        {
          heading: "Salvataggio",
          content: "Le modifiche sono permanenti. Clicca 'Save Config' per applicare (serve API key). Valori di rischio superiori al 10% richiedono conferma esplicita prima del salvataggio. Le modifiche alla watchlist influenzano il prossimo ciclo di generazione segnali (ogni 15 minuti).",
        },
      ]} />

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
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Max Drawdown: {drawdown.toFixed(0)}%
              {drawdown > 10 && (
                <span style={{ marginLeft: 6, color: '#ef4444', fontWeight: 700, fontSize: 11 }}>
                  HIGH RISK
                </span>
              )}
            </span>
            <input
              type="range" min={1} max={20} step={0.5}
              value={drawdown}
              onChange={(e) => setDrawdown(parseFloat(e.target.value))}
              style={{ width: '100%', marginTop: 6, border: 'none', padding: 0 }}
            />
          </label>

          <label style={{ display: 'block', marginBottom: 12 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              Stop Loss
              {stopLoss > 0.10 && (
                <span style={{ marginLeft: 6, color: '#ef4444', fontWeight: 700, fontSize: 11 }}>
                  HIGH RISK
                </span>
              )}
            </span>
            <input
              type="number" min={0.01} max={0.5} step={0.01}
              value={stopLoss}
              onChange={(e) => setStopLoss(parseFloat(e.target.value))}
              style={{ width: '100%', marginTop: 4 }}
            />
          </label>

          {/* F0-3: inline risk warnings for values exceeding safety thresholds */}
          <RiskParamWarning stopLoss={stopLoss} drawdown={drawdown} />

          <div style={{ marginTop: 12 }}>
            <button
              className="btn-primary"
              onClick={handleSaveClick}
              disabled={saveMutation.isPending}
            >
              {saveMutation.isPending ? 'Saving...' : '✓ Save Config'}
            </button>
            {saveMutation.isSuccess && <span style={{ color: 'var(--green)', fontSize: 12, marginLeft: 8 }}>Saved</span>}
            {saveMutation.isError && <span style={{ color: 'var(--red)', fontSize: 12, marginLeft: 8 }}>Error — check API key</span>}
          </div>
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Full Config (read-only)</h3>
          <pre style={{ fontSize: 12, color: 'var(--text-muted)', overflow: 'auto', maxHeight: 300, background: '#f8fafc', padding: 12, borderRadius: 6 }}>
            {JSON.stringify(cfg, null, 2)}
          </pre>
        </div>
      </div>

      {/* F0-3: confirmation dialog for high-risk save */}
      {saveConfirmOpen && (
        <AccessibleModal title="High-Risk Configuration" tone="danger" width={460} onClose={() => setSaveConfirmOpen(false)}>
            <p style={{ color: 'var(--text-muted)', marginBottom: 8, lineHeight: 1.6 }}>
              You are saving risk parameters that exceed the 10% safety threshold:
            </p>
            <ul style={{ color: '#fca5a5', fontSize: 13, marginBottom: 12, paddingLeft: 20 }}>
              {stopLoss > 0.10 && <li>Stop-loss: {(stopLoss * 100).toFixed(0)}% (threshold: 10%)</li>}
              {drawdown > 10 && <li>Max drawdown: {drawdown.toFixed(0)}% (threshold: 10%)</li>}
            </ul>
            <p style={{ color: '#94a3b8', fontSize: 12, marginBottom: 16 }}>
              These values are for paper trading and preflight only. They do not authorize live trading.
              Confirm only if you have verified these values against the operator runbook.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-ghost" onClick={() => setSaveConfirmOpen(false)}>Cancel</button>
              <button
                className="btn-danger"
                onClick={() => { setSaveConfirmOpen(false); saveMutation.mutate() }}
                disabled={saveMutation.isPending}
              >
                Confirm Save High-Risk Values
              </button>
            </div>
        </AccessibleModal>
      )}
    </div>
  )
}
