import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { useStore } from '@/store'

const Overview    = lazy(() => import('@/pages/Overview'))
const Signals     = lazy(() => import('@/pages/Signals'))
const Trading     = lazy(() => import('@/pages/Trading'))
const Performance = lazy(() => import('@/pages/Performance'))
const Backtest    = lazy(() => import('@/pages/Backtest'))
const News        = lazy(() => import('@/pages/News'))
const LLM         = lazy(() => import('@/pages/LLM'))
const Operations  = lazy(() => import('@/pages/Operations'))
const AutoImprove = lazy(() => import('@/pages/AutoImprove'))
const Strategies  = lazy(() => import('@/pages/Strategies'))
const Docs        = lazy(() => import('@/pages/Docs'))
const LoginPage   = lazy(() => import('@/pages/LoginPage'))
const Validation  = lazy(() => import('@/pages/Validation'))
const Labeling    = lazy(() => import('@/pages/Labeling'))
const Quality     = lazy(() => import('@/pages/Quality'))

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 3, retryDelay: (n) => Math.min(1000 * 2 ** n, 30000) } },
})

const PageFallback = () => (
  <div style={{ padding: 40, color: 'var(--text-muted)', textAlign: 'center' }}>Loading...</div>
)

function ProtectedLayout() {
  const isAuthenticated = useStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <Layout />
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ErrorBoundary>
          <Suspense fallback={<PageFallback />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route element={<ProtectedLayout />}>
                <Route path="/"             element={<Overview />} />
                <Route path="/signals"      element={<Signals />} />
                <Route path="/trading"      element={<Trading />} />
                <Route path="/performance"  element={<Performance />} />
                <Route path="/strategies"   element={<Strategies />} />
                <Route path="/backtest"     element={<Backtest />} />
                <Route path="/news"         element={<News />} />
                <Route path="/llm"          element={<LLM />} />
                <Route path="/operations"   element={<Operations />} />
                <Route path="/config"       element={<Navigate to="/operations?tab=config" replace />} />
                <Route path="/admin"        element={<Navigate to="/operations?tab=admin" replace />} />
                <Route path="/auto-improve" element={<AutoImprove />} />
                <Route path="/docs"         element={<Docs />} />
                <Route path="/dashboard"    element={<Navigate to="/" replace />} />
                <Route path="/system"       element={<Navigate to="/operations?tab=system" replace />} />
                <Route path="/validation"   element={<Validation />} />
                <Route path="/labeling"     element={<Labeling />} />
                <Route path="/quality"      element={<Quality />} />
              </Route>
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
