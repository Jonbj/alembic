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

export interface Readiness {
  redis_healthy: boolean
  redis_writeable: boolean
  db_healthy: boolean
  killswitch_active: boolean
  stale_signals: boolean
  worker_beat_lag: boolean
  last_signal_age_minutes: number | null
  last_cycle_age_minutes: number | null
}

export type ReadinessState = 'ready' | 'degraded' | 'blocked'

/** Derive a single state from the flags. HTTP 200 does NOT imply healthy. */
export function readinessState(r: Readiness): ReadinessState {
  if (r.killswitch_active || !r.db_healthy || !r.redis_healthy) return 'blocked'
  if (!r.redis_writeable || r.stale_signals || r.worker_beat_lag) return 'degraded'
  return 'ready'
}

export const fetchScheduler = () => apiFetch<SchedulerTask[]>('/api/system/scheduler')
export const fetchActivity = (limit = 60) => apiFetch<ActivityEvent[]>(`/api/system/activity?limit=${limit}`)
export const fetchReadiness = () => apiFetch<Readiness>('/api/system/readiness')
