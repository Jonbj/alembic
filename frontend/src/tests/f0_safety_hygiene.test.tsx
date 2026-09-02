/**
 * F0-1 + F0-3 Frontend Safety Hygiene tests.
 *
 * TDD RED phase — all tests fail before production code is written.
 * These tests verify:
 *   F0-1: Strategy authorization truth is surfaced; misleading copy is absent.
 *   F0-3: Mutating safety surfaces (full_auto, risk sliders, kill-switch) have guardrails.
 */
import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { readFileSync, readdirSync, existsSync } from 'fs'
import { resolve } from 'path'

// ── Mocks (hoisted by Vitest) ────────────────────────────────────────────────

vi.mock('@/api/admin', () => ({
  fetchKillswitchStatus: vi.fn().mockResolvedValue({ active: true, activated_at: null, reason: null }),
  activateKillswitch: vi.fn().mockResolvedValue({}),
  requestKillswitchRecoveryToken: vi.fn().mockResolvedValue({ recovery_token: 'tok-xyz', expires_in_seconds: 60 }),
  deactivateKillswitch: vi.fn().mockResolvedValue({}),
  fetchMode: vi.fn().mockResolvedValue({ mode: 'paper' }),
  setMode: vi.fn().mockResolvedValue({}),
}))

// Minimal store mock — covers both hook selector and getState() (used by apiFetch)
vi.mock('@/store', () => {
  const state = {
    mode: 'paper' as const,
    theme: 'dark' as const,
    killswitchActive: false,
    token: 'test-token',
    isAuthenticated: true,
    llmModels: 'all',
    setMode: vi.fn(),
    setTheme: vi.fn(),
    setKillswitch: vi.fn(),
    setToken: vi.fn(),
    logout: vi.fn(),
    setLlmModels: vi.fn(),
  }
  const useStore = (selector?: (s: typeof state) => unknown) =>
    selector ? selector(state) : state
  useStore.getState = () => state
  return { useStore }
})

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
}

function renderWithQuery(ui: React.ReactElement) {
  return render(<QueryClientProvider client={makeQC()}>{ui}</QueryClientProvider>)
}

// ── F0-1: Strategy Authorization Truth ──────────────────────────────────────

describe('F0-1 Strategy Authorization Truth', () => {
  test('renders promotion_blocked warning when promotion_blocked=true', async () => {
    const { StrategyAuthStatus } = await import('@/components/shared/StrategyAuthStatus')
    render(<StrategyAuthStatus promotion_blocked={true} mode="supervised_paper" />)
    expect(screen.getByTestId('promotion-blocked-warning')).toBeInTheDocument()
    expect(screen.getByText(/promotion blocked/i)).toBeInTheDocument()
    expect(screen.getByText(/not authorized for live promotion/i)).toBeInTheDocument()
  })

  test('renders data_quality_warning when present', async () => {
    const { StrategyAuthStatus } = await import('@/components/shared/StrategyAuthStatus')
    const warning = 'Backtest metrics are a stale historical snapshot and do not authorize paper, promotion, or live trading.'
    render(<StrategyAuthStatus mode="paper" data_quality_warning={warning} />)
    expect(screen.getByTestId('data-quality-warning')).toBeInTheDocument()
    expect(screen.getByText(/stale historical snapshot/i)).toBeInTheDocument()
  })

  test('does not render "validated" or "VALIDATA" for supervised_paper strategy', async () => {
    const { StrategyAuthStatus } = await import('@/components/shared/StrategyAuthStatus')
    render(<StrategyAuthStatus mode="supervised_paper" promotion_blocked={true} live_authorized={false} />)
    expect(screen.queryByText(/validata/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/\bvalidated\b/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/live.ready/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('mode-badge')).toHaveTextContent('supervised_paper')
  })

  test('does not imply live authorization for paper/promotion-blocked strategy', async () => {
    const { StrategyAuthStatus } = await import('@/components/shared/StrategyAuthStatus')
    render(<StrategyAuthStatus mode="paper" live_authorized={false} promotion_blocked={true} />)
    expect(screen.queryByText(/in esecuzione live/i)).not.toBeInTheDocument()
    // Should NOT show the fail-safe (we do have auth fields)
    expect(screen.queryByTestId('auth-unavailable')).not.toBeInTheDocument()
    // Should show mode badge
    expect(screen.getByTestId('mode-badge')).toHaveTextContent('paper')
  })

  test('shows fail-safe message when no authorization fields are provided', async () => {
    const { StrategyAuthStatus } = await import('@/components/shared/StrategyAuthStatus')
    render(<StrategyAuthStatus />)
    expect(screen.getByTestId('auth-unavailable')).toBeInTheDocument()
    expect(screen.getByText(/authorization status unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/do not treat as approved/i)).toBeInTheDocument()
  })
})

// ── F0-3: Admin / Config Safety Guardrails ───────────────────────────────────

describe('F0-3 Admin and Config Safety Guardrails', () => {
  beforeEach(() => { vi.clearAllMocks() })

  test('full_auto radio input is disabled in Admin page', async () => {
    const { default: Admin } = await import('@/pages/Admin')
    renderWithQuery(<Admin />)
    // Wait for the mode query to resolve and radios to render
    await waitFor(() => {
      const radios = screen.getAllByRole('radio')
      expect(radios.length).toBeGreaterThan(0)
    })
    const radios = screen.getAllByRole('radio') as HTMLInputElement[]
    const fullAutoRadio = radios.find(r => r.value === 'full_auto')
    expect(fullAutoRadio).toBeTruthy()
    expect(fullAutoRadio).toBeDisabled()
  })

  test('RiskParamWarning shows high-risk warning when stop-loss exceeds 10%', async () => {
    const { RiskParamWarning } = await import('@/components/shared/RiskParamWarning')
    render(<RiskParamWarning stopLoss={0.15} drawdown={5} />)
    expect(screen.getByTestId('stop-loss-warning')).toBeInTheDocument()
    expect(screen.getByText(/stop.?loss.*10%/i)).toBeInTheDocument()
  })

  test('RiskParamWarning shows high-risk warning when max drawdown exceeds 10%', async () => {
    const { RiskParamWarning } = await import('@/components/shared/RiskParamWarning')
    render(<RiskParamWarning stopLoss={0.05} drawdown={15} />)
    expect(screen.getByTestId('drawdown-warning')).toBeInTheDocument()
    expect(screen.getByText(/drawdown.*10%/i)).toBeInTheDocument()
  })

  test('kill-switch deactivation requires confirmation dialog with mandatory safety copy', async () => {
    const { default: Admin } = await import('@/pages/Admin')
    const user = userEvent.setup()
    renderWithQuery(<Admin />)
    // Wait for kill-switch query to resolve and the Deactivate button to appear
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /deactivate kill.?switch/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /deactivate kill.?switch/i }))
    // Must show confirmation dialog with the required safety copy
    expect(screen.getByText(/deactivating kill.?switch may allow the next paper cycle/i)).toBeInTheDocument()
    expect(screen.getByText(/does not authorize live trading/i)).toBeInTheDocument()
  })

  // The Strategies page was deleted on 2026-09-02 (its metrics were hardcoded
  // snapshots, not live data). The original guard read Strategies.tsx and asserted
  // it wired no promotion controls; with the file gone that assertion would pass by
  // ENOENT, which is a guard dying rather than a guard holding. It is replaced by two
  // checks that keep the same guarantee against the pages that still exist.

  test('no page wires strategy promote/approve/demote controls', () => {
    const pagesDir = resolve(__dirname, '../pages')
    const offenders: string[] = []
    for (const file of readdirSync(pagesDir).filter((f) => f.endsWith('.tsx'))) {
      const src = readFileSync(resolve(pagesDir, file), 'utf-8')
      if (
        src.includes('/promote') ||
        src.includes('/demote') ||
        /Promote Strategy|Demote Strategy|Approve Strategy/.test(src)
      ) {
        offenders.push(file)
      }
    }
    expect(offenders).toEqual([])
  })

  test('the removed Strategies page and its snapshot API client stay removed', () => {
    expect(existsSync(resolve(__dirname, '../pages/Strategies.tsx'))).toBe(false)
    expect(existsSync(resolve(__dirname, '../api/strategies.ts'))).toBe(false)
  })
})
