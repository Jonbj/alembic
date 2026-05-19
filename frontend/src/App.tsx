import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { fetchMode } from '@/api/admin'
import { useStore } from '@/store'

const Overview    = lazy(() => import('@/pages/Overview'))
const Signals     = lazy(() => import('@/pages/Signals'))
const Trading     = lazy(() => import('@/pages/Trading'))
const Performance = lazy(() => import('@/pages/Performance'))
const Backtest    = lazy(() => import('@/pages/Backtest'))
const News        = lazy(() => import('@/pages/News'))
const LLM         = lazy(() => import('@/pages/LLM'))
const Config      = lazy(() => import('@/pages/Config'))
const Admin       = lazy(() => import('@/pages/Admin'))
const AutoImprove = lazy(() => import('@/pages/AutoImprove'))

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 3, retryDelay: (n) => Math.min(1000 * 2 ** n, 30000) } },
})

const PageFallback = () => (
  <div style={{ padding: 40, color: 'var(--text-muted)', textAlign: 'center' }}>Loading...</div>
)

// Syncs the persisted mode from sessionStorage with the backend's current mode.
// Prevents frontend showing 'paper' after a backend emergency halt.
function ModeSync() {
  const setMode = useStore((s) => s.setMode)
  useEffect(() => {
    fetchMode()
      .then(({ mode }) => setMode(mode as Parameters<typeof setMode>[0]))
      .catch(() => { /* backend unreachable — keep persisted mode */ })
  }, [setMode])
  return null
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ModeSync />
        <ErrorBoundary>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route element={<Layout />}>
                <Route path="/"             element={<Overview />} />
                <Route path="/signals"      element={<Signals />} />
                <Route path="/trading"      element={<Trading />} />
                <Route path="/performance"  element={<Performance />} />
                <Route path="/backtest"     element={<Backtest />} />
                <Route path="/news"         element={<News />} />
                <Route path="/llm"          element={<LLM />} />
                <Route path="/config"       element={<Config />} />
                <Route path="/admin"        element={<Admin />} />
                <Route path="/auto-improve" element={<AutoImprove />} />
              </Route>
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
