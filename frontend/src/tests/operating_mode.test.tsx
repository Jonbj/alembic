import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { OPERATING_MODES, type Mode } from '@/types/system'

vi.mock('@/api/admin', () => ({
  fetchKillswitchStatus: vi.fn().mockResolvedValue({ active: false, activated_at: null, reason: null }),
  activateKillswitch: vi.fn().mockResolvedValue({}),
  requestKillswitchRecoveryToken: vi.fn().mockResolvedValue({ recovery_token: 'token', expires_in_seconds: 60 }),
  deactivateKillswitch: vi.fn().mockResolvedValue({}),
  fetchMode: vi.fn().mockResolvedValue({ mode: 'dry_run' }),
  setMode: vi.fn().mockResolvedValue({}),
}))

describe('operating mode condiviso', () => {
  test('espone tutti e soli i mode accettati dal backend', () => {
    const backendModes: Mode[] = ['backtest', 'paper', 'semi_auto', 'full_auto', 'halted', 'dry_run']
    expect(OPERATING_MODES).toEqual(backendModes)
  })

  test('Admin riconosce e mostra dry_run restituito dal backend', async () => {
    const { default: Admin } = await import('@/pages/Admin')
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    render(
      <QueryClientProvider client={queryClient}>
        <Admin />
      </QueryClientProvider>,
    )

    const dryRun = await screen.findByRole('radio', { name: /dry run/i })
    await waitFor(() => expect(dryRun).toBeChecked())
  })
})
