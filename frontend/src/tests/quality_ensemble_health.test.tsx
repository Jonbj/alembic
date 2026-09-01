import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchQualityMetrics: vi.fn(),
  fetchQualitySources: vi.fn(),
  fetchQualityEnsembleHealth: vi.fn(),
}))

vi.mock('@/api/quality', () => ({
  fetchQualityMetrics: mocks.fetchQualityMetrics,
  fetchQualitySources: mocks.fetchQualitySources,
  fetchQualityEnsembleHealth: mocks.fetchQualityEnsembleHealth,
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Quality />
    </QueryClientProvider>,
  )
}

import Quality from '@/pages/Quality'

describe('Quality ensemble health', () => {
  test('mostra la quota full-ensemble per ciclo nel tempo', async () => {
    mocks.fetchQualityMetrics.mockResolvedValue({
      window_days: 14,
      per_model: [],
      signals: {},
      extraction: { n_labeled: 0 },
    })
    mocks.fetchQualitySources.mockResolvedValue({
      window_days: 14,
      funnel: [],
      signals: [],
      trades: [],
      trace_coverage: {},
    })
    mocks.fetchQualityEnsembleHealth.mockResolvedValue({
      window_days: 14,
      cycles: [
        {
          cycle_started_at: '2026-08-27T18:00:00Z',
          cycle_ended_at: '2026-08-27T18:01:00Z',
          n_ensemble: 3,
          n_single: 0,
          n_finbert: 1,
          aggregate: 4,
          rth: true,
        },
      ],
      summary: {
        n_cycles: 1,
        total_ensemble: 3,
        total_single: 0,
        total_finbert: 1,
        total_aggregate: 4,
        rth_cycles: 1,
        rth_share: 1,
        full_ensemble_share: 0.75,
      },
    })

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Ensemble health' })).toBeInTheDocument()
    expect(await screen.findAllByText('Full-ensemble share')).toHaveLength(2)
    expect(await screen.findAllByText('75.0%')).toHaveLength(2)
    expect(screen.getByText('2026-08-27 18:00 UTC')).toBeInTheDocument()
    expect(mocks.fetchQualityEnsembleHealth).toHaveBeenCalledWith(14)
  })
})
