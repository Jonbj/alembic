import { apiFetch } from './client'

export const fetchConfig = () => apiFetch<Record<string, unknown>>('/api/config')
export const updateConfig = (updates: Record<string, unknown>) =>
  apiFetch<Record<string, unknown>>('/api/config', { method: 'POST', body: JSON.stringify(updates) })
