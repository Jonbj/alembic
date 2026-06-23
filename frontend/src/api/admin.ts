import { apiFetch } from './client'

export interface KillswitchStatus {
  active: boolean
  activated_at: string | null
  reason: string | null
}

export interface RecoveryTokenResponse {
  recovery_token: string
  expires_in_seconds: number
}

export const fetchKillswitchStatus = () => apiFetch<KillswitchStatus>('/api/admin/killswitch')
export const activateKillswitch = (reason: string) =>
  apiFetch('/api/admin/killswitch', { method: 'POST', body: JSON.stringify({ reason }) })

/** Step 1 of the two-step kill-switch recovery flow: request a one-time token. */
export const requestKillswitchRecoveryToken = () =>
  apiFetch<RecoveryTokenResponse>('/api/admin/killswitch/recovery-token', { method: 'POST' })

/** Step 2 of the recovery flow: deactivate using the token from step 1. */
export const deactivateKillswitch = (confirmToken: string) =>
  apiFetch(`/api/admin/killswitch?confirm_token=${encodeURIComponent(confirmToken)}`, { method: 'DELETE' })

export const fetchMode = () => apiFetch<{ mode: string }>('/api/admin/mode')
export const setMode = (mode: string) =>
  apiFetch('/api/admin/mode', { method: 'POST', body: JSON.stringify({ mode }) })
