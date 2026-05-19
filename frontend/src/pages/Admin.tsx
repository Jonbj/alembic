import { useState, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchKillswitchStatus, activateKillswitch, deactivateKillswitch, fetchMode, setMode } from '@/api/admin'
import { useStore } from '@/store'

const MODES = ['backtest', 'paper', 'semi_auto', 'full_auto', 'halted'] as const
const MODE_DESC: Record<string, string> = {
  backtest: 'Running historical simulation — no live orders',
  paper: 'Paper trading — simulated orders, no real capital',
  semi_auto: 'Each order requires Telegram approval before execution',
  full_auto: 'Fully automated — orders execute without confirmation',
  halted: 'All order execution stopped',
}

export default function Admin() {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [reason, setReason] = useState('')
  const qc = useQueryClient()
  const setStoreMode = useStore((s) => s.setMode)

  const { data: ks } = useQuery({ queryKey: ['killswitch'], queryFn: fetchKillswitchStatus, refetchInterval: 15000 })
  const { data: modeData } = useQuery({ queryKey: ['mode'], queryFn: fetchMode, refetchInterval: 15000 })

  const activateMutation = useMutation({
    mutationFn: () => activateKillswitch(reason || 'Manual activation from dashboard'),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['killswitch'] }); setConfirmOpen(false); setReason('') },
  })

  const deactivateMutation = useMutation({
    mutationFn: deactivateKillswitch,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['killswitch'] }),
  })

  type Mode = Parameters<typeof setStoreMode>[0]

  const modeMutation = useMutation({
    mutationFn: (m: Mode) => setMode(m),
    onSuccess: (_, m) => { qc.invalidateQueries({ queryKey: ['mode'] }); setStoreMode(m) },
  })

  const handleModeChange = useCallback((m: Mode) => modeMutation.mutate(m), [modeMutation])

  const ksActive = ks?.active ?? false

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Admin</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div className="card" style={{ textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 20px', fontSize: 14, fontWeight: 600 }}>Kill Switch</h3>

          <div style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            width: 80, height: 80, borderRadius: '50%',
            background: ksActive ? '#fee2e2' : '#dcfce7',
            marginBottom: 16, fontSize: 32,
          }}>
            {ksActive ? '🔴' : '🟢'}
          </div>

          <p style={{ color: 'var(--text-muted)', margin: '0 0 16px' }}>
            {ksActive
              ? `ACTIVE — activated at ${ks?.activated_at ? new Date(ks.activated_at).toLocaleString() : '—'}`
              : 'Not active — system is running normally'}
          </p>

          {!ksActive ? (
            <button className="btn-danger" style={{ fontSize: 15, padding: '10px 24px' }} onClick={() => setConfirmOpen(true)}>
              ⚠ Activate Kill Switch
            </button>
          ) : (
            <button className="btn-primary" onClick={() => deactivateMutation.mutate()} disabled={deactivateMutation.isPending}>
              ✓ Deactivate Kill Switch
            </button>
          )}
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Operating Mode</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {MODES.map((m) => (
              <label key={m} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', padding: 8, borderRadius: 6, background: modeData?.mode === m ? '#dbeafe' : 'transparent' }}>
                <input
                  type="radio"
                  name="mode"
                  value={m}
                  checked={modeData?.mode === m}
                  onChange={() => handleModeChange(m)}
                  style={{ marginTop: 2 }}
                />
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{m.replace('_', ' ')}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{MODE_DESC[m]}</div>
                </div>
              </label>
            ))}
          </div>
          {modeMutation.isError && <p style={{ color: 'var(--red)', fontSize: 12, marginTop: 8 }}>Error — check API key</p>}
        </div>
      </div>

      {/* Confirm dialog */}
      {confirmOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="card" style={{ width: 420 }}>
            <h3 style={{ margin: '0 0 12px', color: 'var(--red)' }}>⚠ Activate Kill Switch</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>
              This will halt all order execution immediately. Are you sure?
            </p>
            <input
              placeholder="Reason (optional)..."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{ width: '100%', marginBottom: 12 }}
            />
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-ghost" onClick={() => setConfirmOpen(false)}>Cancel</button>
              <button className="btn-danger" onClick={() => activateMutation.mutate()} disabled={activateMutation.isPending}>
                {activateMutation.isPending ? 'Activating...' : 'Confirm Activate'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
