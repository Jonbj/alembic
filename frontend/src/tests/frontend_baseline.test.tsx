import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchReadiness: vi.fn(),
  isTradingWindow: vi.fn(),
  logout: vi.fn(),
  portfolioStatus: vi.fn(),
  storeState: {
    token: 'jwt-test',
    logout: vi.fn(),
  },
}))

vi.mock('@/store', () => ({
  useStore: { getState: () => mocks.storeState },
}))

vi.mock('@/api/system', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/system')>()
  return { ...actual, fetchReadiness: mocks.fetchReadiness }
})

vi.mock('@/utils/market', () => ({
  isTradingWindow: mocks.isTradingWindow,
}))

// Strategies page and @/api/strategies removed 2026-09-02; Overview now reads
// the authorization surface from GET /portfolio/status.
vi.mock('@/api/portfolio', () => ({
  fetchPortfolioStatus: mocks.portfolioStatus,
}))

function response(status: number, body: unknown = {}, statusText = ''): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response
}

function queryWrapper(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

const READY = {
  redis_healthy: true,
  redis_writeable: true,
  db_healthy: true,
  killswitch_active: false,
  stale_signals: false,
  worker_beat_lag: false,
  last_signal_age_minutes: 2,
  last_cycle_age_minutes: 3,
}

describe('apiFetch', () => {
  beforeEach(() => {
    mocks.storeState.logout = mocks.logout
    vi.stubGlobal('fetch', vi.fn())
    const testWindow = Object.create(window) as Window
    Object.defineProperty(testWindow, 'location', { value: { href: 'http://localhost/' } })
    vi.stubGlobal('window', testWindow)
    vi.clearAllMocks()
  })

  afterEach(() => vi.unstubAllGlobals())

  test('aggiunge il bearer token e restituisce il JSON', async () => {
    vi.mocked(fetch).mockResolvedValue(response(200, { ok: true }))
    const { apiFetch } = await import('@/api/client')

    await expect(apiFetch('/api/example')).resolves.toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledWith('/api/example', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer jwt-test' }),
    }))
  })

  test.each([401, 403])('fa logout e segnala sessione scaduta su HTTP %i', async (status) => {
    vi.mocked(fetch).mockResolvedValue(response(status))
    const { apiFetch } = await import('@/api/client')

    await expect(apiFetch('/api/private')).rejects.toEqual(
      expect.objectContaining({ status, message: 'Session expired — please log in again' }),
    )
    expect(mocks.logout).toHaveBeenCalledOnce()
    expect(window.location.href).toBe('/login')
  })

  test('rende esplicito il rate limit HTTP 429', async () => {
    vi.mocked(fetch).mockResolvedValue(response(429))
    const { apiFetch } = await import('@/api/client')

    await expect(apiFetch('/api/busy')).rejects.toMatchObject({
      status: 429,
      message: 'Rate limited — try again later',
    })
  })

  test('rende espliciti gli errori server', async () => {
    vi.mocked(fetch).mockResolvedValue(response(503))
    const { apiFetch } = await import('@/api/client')

    await expect(apiFetch('/api/down')).rejects.toMatchObject({
      status: 503,
      message: 'Server error (503) — check backend logs',
    })
  })
})

describe('ReadinessBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.isTradingWindow.mockReturnValue(true)
  })

  test('mostra BLOCKED per un guasto infrastrutturale', async () => {
    mocks.fetchReadiness.mockResolvedValue({ ...READY, db_healthy: false })
    const { ReadinessBanner } = await import('@/components/layout/ReadinessBanner')

    render(queryWrapper(<ReadinessBanner />))
    expect(await screen.findByText(/BLOCKED/)).toBeInTheDocument()
  })

  test('mostra DEGRADED per segnali stale durante il mercato', async () => {
    mocks.fetchReadiness.mockResolvedValue({ ...READY, stale_signals: true })
    const { ReadinessBanner } = await import('@/components/layout/ReadinessBanner')

    render(queryWrapper(<ReadinessBanner />))
    expect(await screen.findByText(/DEGRADED/)).toBeInTheDocument()
  })

  test('fuori orario tratta segnali stale come attesi e mostra MARKET CLOSED', async () => {
    mocks.isTradingWindow.mockReturnValue(false)
    mocks.fetchReadiness.mockResolvedValue({ ...READY, stale_signals: true, worker_beat_lag: true })
    const { ReadinessBanner } = await import('@/components/layout/ReadinessBanner')

    render(queryWrapper(<ReadinessBanner />))
    expect(await screen.findByText(/MARKET CLOSED/)).toBeInTheDocument()
  })

  test('non spaccia per healthy un endpoint irraggiungibile', async () => {
    mocks.fetchReadiness.mockRejectedValue(new Error('offline'))
    const { ReadinessBanner } = await import('@/components/layout/ReadinessBanner')

    render(queryWrapper(<ReadinessBanner />))
    expect(await screen.findByText(/system state unknown/i)).toBeInTheDocument()
  })
})

describe('ErrorBoundary', () => {
  afterEach(() => vi.restoreAllMocks())

  test('isola un errore di rendering e mostra un fallback utile', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { ErrorBoundary } = await import('@/components/ErrorBoundary')
    const Broken = () => {
      throw new Error('render fallito')
    }

    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('render fallito')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })
})

// La pagina Strategies e' stata eliminata il 2026-09-02 (metriche hardcoded, non live).
// Il test che qui verificava il suo stato vuoto e' stato riscritto sulla superficie che
// l'ha sostituita: la card Authorization di Overview, alimentata da GET /portfolio/status.
// La garanzia da preservare e' la stessa e vale piu' di prima, perche' ora e' l'unico
// posto che dice se una strategia e' autorizzata: quando l'elenco arriva vuoto la UI
// deve dirlo esplicitamente, mai lasciare il vuoto a suggerire "nessun problema".
describe('Overview — superficie di autorizzazione', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline in test')))
  })
  afterEach(() => vi.unstubAllGlobals())

  test('senza strategie mostra l\'avviso esplicito, non un vuoto silenzioso', async () => {
    mocks.portfolioStatus.mockResolvedValue({ active_strategies: 0, strategies: [], last_cycle: null })
    const { default: Overview } = await import('@/pages/Overview')

    render(queryWrapper(<Overview />))

    expect(await screen.findByTestId('auth-unavailable')).toBeInTheDocument()
  })

  test('con una strategia non live mostra mode e live_authorized: false', async () => {
    mocks.portfolioStatus.mockResolvedValue({
      active_strategies: 1,
      strategies: [{
        strategy_id: 'S1', allocation_pct: 0.5, schedule: '', enabled: true,
        mode: 'supervised_paper', approved: true,
        promotion_blocked: true, live_authorized: false,
      }],
      last_cycle: null,
    })
    const { default: Overview } = await import('@/pages/Overview')

    render(queryWrapper(<Overview />))

    expect(await screen.findByTestId('mode-badge')).toHaveTextContent('supervised_paper')
    expect(screen.getByTestId('not-live-authorized')).toBeInTheDocument()
    expect(screen.getByTestId('promotion-blocked-badge')).toBeInTheDocument()
  })
})
