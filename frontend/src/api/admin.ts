import { apiFetch } from './client'

export interface KillswitchStatus {
  active: boolean
  activated_at: string | null
  reason: string | null
}

export const fetchKillswitchStatus = () => apiFetch<KillswitchStatus>('/api/admin/killswitch')
export const activateKillswitch = (reason: string) =>
  apiFetch('/api/admin/killswitch', { method: 'POST', body: JSON.stringify({ reason }) })
export const deactivateKillswitch = () =>
  apiFetch('/api/admin/killswitch', { method: 'DELETE' })

export const fetchMode = () => apiFetch<{ mode: string }>('/api/admin/mode')
export const setMode = (mode: string) =>
  apiFetch('/api/admin/mode', { method: 'POST', body: JSON.stringify({ mode }) })
