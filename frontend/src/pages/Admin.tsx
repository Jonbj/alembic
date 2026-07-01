import { useState, useCallback } from 'react'
import { fmtDateTime } from '@/utils/format'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchKillswitchStatus,
  activateKillswitch,
  requestKillswitchRecoveryToken,
  deactivateKillswitch,
  fetchMode,
  setMode,
} from '@/api/admin'
import { HelpButton } from '@/components/shared/HelpButton'
import { useStore } from '@/store'

const MODES = ['backtest', 'paper', 'semi_auto', 'full_auto', 'halted'] as const
type Mode = typeof MODES[number]
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
  // F0-3: kill-switch deactivation requires explicit confirmation (separate from activation)
  const [deactivateConfirmOpen, setDeactivateConfirmOpen] = useState(false)
  const [deactivateError, setDeactivateError] = useState<string | null>(null)
  const [isDeactivating, setIsDeactivating] = useState(false)
  const [pendingMode, setPendingMode] = useState<Mode | null>(null)

  const qc = useQueryClient()
  const setStoreMode = useStore((s) => s.setMode)

  const { data: ks } = useQuery({ queryKey: ['killswitch'], queryFn: fetchKillswitchStatus, refetchInterval: 15000 })
  const { data: modeData } = useQuery({ queryKey: ['mode'], queryFn: fetchMode, refetchInterval: 15000 })

  const activateMutation = useMutation({
    mutationFn: () => activateKillswitch(reason || 'Manual activation from dashboard'),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['killswitch'] }); setConfirmOpen(false); setReason('') },
  })

  // F0-3: two-step recovery flow — request OTP token, then deactivate with it
  const handleDeactivateConfirm = useCallback(async () => {
    setIsDeactivating(true)
    setDeactivateError(null)
    try {
      const { recovery_token } = await requestKillswitchRecoveryToken()
      await deactivateKillswitch(recovery_token)
      qc.invalidateQueries({ queryKey: ['killswitch'] })
      setDeactivateConfirmOpen(false)
    } catch (err) {
      setDeactivateError(
        err instanceof Error ? err.message : 'Failed to deactivate — check API key and try again.'
      )
    } finally {
      setIsDeactivating(false)
    }
  }, [qc])

  const modeMutation = useMutation({
    mutationFn: (m: Mode) => setMode(m),
    onSuccess: (_, m) => { qc.invalidateQueries({ queryKey: ['mode'] }); setStoreMode(m); setPendingMode(null) },
  })

  const handleModeChange = useCallback((m: Mode) => {
    if (m === modeData?.mode) return
    setPendingMode(m)
  }, [modeData?.mode])

  const ksActive = ks?.active ?? false

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Admin</h2>
      <HelpButton title="Admin — Amministrazione" sections={[
        {
          heading: "Kill Switch",
          content: "Il kill switch ferma TUTTA l'esecuzione di ordini immediatamente. Usalo solo in emergenza. Quando è attivo (rosso), nessun ordine viene eseguito.\n\nPer disattivarlo, clicca 'Deactivate Kill Switch' e conferma nella dialog. Il sistema richiede un recovery token one-time al backend prima di procedere.",
        },
        {
          heading: "Operating Mode",
          content: "- **Backtest**: simulazione storica, nessun ordine reale\n- **Paper**: trading simulato con Alpaca paper, nessun capitale reale\n- **Semi-auto**: ogni ordine richiede conferma via Telegram\n- **Full-auto**: ⚠ NON AUTORIZZATO — live trading e strategy promotions restano disabilitati\n- **Halted**: tutto fermo\n\nIl mode corrente è mostrato nel sidebar.",
        },
        {
          heading: "⚠ Attenzione",
          content: "**full_auto è disabilitato** in questa fase. Live trading e strategy promotions non sono autorizzati.\n\nLa pagina Admin richiede API key per le operazioni di scrittura. La deattivazione del kill-switch avviene solo tramite confirmation dialog + recovery token.",
        },
      ]} />

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
              ? `ACTIVE — activated at ${ks?.activated_at ? fmtDateTime(ks.activated_at) : '—'}`
              : 'Not active — system is running normally'}
          </p>

          {!ksActive ? (
            <button className="btn-danger" style={{ fontSize: 15, padding: '10px 24px' }} onClick={() => setConfirmOpen(true)}>
              ⚠ Activate Kill Switch
            </button>
          ) : (
            /* F0-3: deactivation opens confirmation dialog — never direct API call */
            <button
              className="btn-primary"
              onClick={() => { setDeactivateError(null); setDeactivateConfirmOpen(true) }}
            >
              ✓ Deactivate Kill Switch
            </button>
          )}
        </div>

        <div className="card">
          <h3 style={{ margin: '0 0 16px', fontSize: 14, fontWeight: 600 }}>Operating Mode</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {MODES.map((m) => {
              // F0-3: full_auto is disabled — not authorized; no casual selection
              const isFullAuto = m === 'full_auto'
              return (
                <label
                  key={m}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    cursor: isFullAuto ? 'not-allowed' : 'pointer',
                    padding: 8, borderRadius: 6,
                    background: modeData?.mode === m ? '#dbeafe' : 'transparent',
                    opacity: isFullAuto ? 0.5 : 1,
                  }}
                >
                  <input
                    type="radio"
                    name="mode"
                    value={m}
                    checked={modeData?.mode === m}
                    onChange={() => handleModeChange(m)}
                    disabled={isFullAuto}
                    style={{ marginTop: 2 }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>
                      {m.replace('_', ' ')}
                      {isFullAuto && (
                        <span style={{ marginLeft: 6, fontSize: 11, color: '#ef4444', fontWeight: 700 }}>
                          [NOT AUTHORIZED]
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {isFullAuto
                        ? 'Full auto is not authorized. Live trading and strategy promotions remain disabled.'
                        : MODE_DESC[m]}
                    </div>
                  </div>
                </label>
              )
            })}
          </div>
          {modeMutation.isError && <p style={{ color: 'var(--red)', fontSize: 12, marginTop: 8 }}>Error — check API key</p>}
        </div>
      </div>

      {/* Activate confirmation dialog */}
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

      {/* F0-3: Deactivate confirmation dialog — required copy per spec */}
      {deactivateConfirmOpen && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="card" style={{ width: 480 }}>
            <h3 style={{ margin: '0 0 12px', color: '#f59e0b' }}>⚠ Deactivate Kill Switch</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.6 }}>
              Deactivating kill-switch may allow the next paper cycle to proceed.
              Confirm only if the preflight/runbook allows it.
              This does not authorize live trading.
            </p>
            <p style={{ color: '#94a3b8', fontSize: 12, marginBottom: 16 }}>
              A one-time recovery token will be requested from the backend. The kill-switch will
              deactivate only if the token is valid. Refer to the operator runbook before proceeding.
            </p>
            {deactivateError && (
              <p style={{ color: 'var(--red)', fontSize: 12, marginBottom: 12 }}>{deactivateError}</p>
            )}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn-ghost"
                onClick={() => { setDeactivateConfirmOpen(false); setDeactivateError(null) }}
                disabled={isDeactivating}
              >
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleDeactivateConfirm}
                disabled={isDeactivating}
              >
                {isDeactivating ? 'Deactivating…' : 'Confirm Deactivate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Operating mode confirmation dialog */}
      {pendingMode && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="card" style={{ width: 460 }}>
            <h3 style={{ margin: '0 0 12px', color: '#f59e0b' }}>Confirm Operating Mode Change</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.6 }}>
              Change operating mode from <strong>{modeData?.mode ?? 'unknown'}</strong> to <strong>{pendingMode}</strong>?
            </p>
            <p style={{ color: '#94a3b8', fontSize: 12, marginBottom: 16 }}>
              This affects the next execution cycles. It does not authorize live trading or strategy promotion.
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                className="btn-ghost"
                onClick={() => setPendingMode(null)}
                disabled={modeMutation.isPending}
              >
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={() => modeMutation.mutate(pendingMode)}
                disabled={modeMutation.isPending}
              >
                {modeMutation.isPending ? 'Changing...' : 'Confirm Change'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
