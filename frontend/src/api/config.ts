import { apiFetch } from './client'

export interface ConfigResponse {
  symbols?: { watchlist: string[] }
  risk?: { portfolio_drawdown: number; stop_loss: number }
}

export const fetchConfig = () => apiFetch<ConfigResponse>('/api/config')
export const updateConfig = (updates: ConfigResponse) =>
  apiFetch<ConfigResponse>('/api/config', { method: 'POST', body: JSON.stringify(updates) })
