import { useState } from 'react'
import { useStore } from '@/store'

interface Props { open: boolean; onClose: () => void }

export function ApiKeyModal({ open, onClose }: Props) {
  const { apiKey, setApiKey } = useStore()
  const [val, setVal] = useState(apiKey)

  if (!open) return null

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="card" style={{ width: 380 }}>
        <h3 style={{ margin: '0 0 12px', fontWeight: 600 }}>API Key</h3>
        <p style={{ color: 'var(--text-muted)', marginBottom: 12 }}>
          Required for admin actions (kill-switch, config write, weight approval).
        </p>
        <input
          type="password"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          placeholder="Enter API key..."
          style={{ width: '100%', marginBottom: 12 }}
        />
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={() => { setApiKey(val); onClose() }}>Save</button>
        </div>
      </div>
    </div>
  )
}
