import { apiFetch } from './client'

export interface SchedulerTask {
  task: string
  description: string
  schedule: string
  last_run: string | null
}

export interface ActivityEvent {
  type: string
  time: string
  summary: string
  detail: string | null
  status: 'ok' | 'warn' | 'error'
}

export interface PeadSignal {
  symbol: string
  direction: 'beat' | 'miss' | 'inline'
  surprise_pct: number
  confidence: number
  filing_id: string
  detected_at: string
  hold_until: string
  days_remaining: number
  is_active: boolean
}

export const fetchScheduler = () => apiFetch<SchedulerTask[]>('/api/system/scheduler')
export const fetchActivity = (limit = 60) => apiFetch<ActivityEvent[]>(`/api/system/activity?limit=${limit}`)
export const fetchPeadSignals = () => apiFetch<PeadSignal[]>('/api/pead/signals')
