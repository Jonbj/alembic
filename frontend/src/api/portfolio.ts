import { apiFetch } from './client'

/**
 * Portfolio status — the authorization surface.
 *
 * Replaces `strategiesApi` (removed 2026-09-02 with the Strategies page), whose
 * payload came from hardcoded snapshots. Everything here is read at request time:
 * `mode`/`approved` from the `strategy_lifecycle` table, `allocation_pct`,
 * `enabled` and `promotion_blocked` from `config/strategies.yaml`.
 *
 * Note the route has NO `/api` prefix — the router is mounted on `/portfolio`.
 */
export interface PortfolioStrategy {
  strategy_id: string
  allocation_pct: number
  schedule: string
  enabled: boolean
  /** From strategy_lifecycle; null when the DB is unreachable (endpoint is fail-open). */
  mode: string | null
  approved: boolean | null
  promotion_blocked: boolean
  /** True only for mode === 'live' with the global promotion flag on. Fail-closed. */
  live_authorized: boolean
}

export interface PortfolioLastCycle {
  timestamp: string
  strategies_run: string[]
  orders_count: number
  constraints_fired: unknown[]
}

export interface PortfolioStatus {
  active_strategies: number
  strategies: PortfolioStrategy[]
  last_cycle: PortfolioLastCycle | null
}

export const fetchPortfolioStatus = () => apiFetch<PortfolioStatus>('/portfolio/status')
