import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Layout } from '@/components/layout/Layout'
import Overview from '@/pages/Overview'
import Signals from '@/pages/Signals'
import Trading from '@/pages/Trading'
import Performance from '@/pages/Performance'
import News from '@/pages/News'
import LLM from '@/pages/LLM'
import Config from '@/pages/Config'
import Admin from '@/pages/Admin'
import AutoImprove from '@/pages/AutoImprove'

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 3, retryDelay: (n) => Math.min(1000 * 2 ** n, 30000) } },
})

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/"             element={<Overview />} />
            <Route path="/signals"      element={<Signals />} />
            <Route path="/trading"      element={<Trading />} />
            <Route path="/performance"  element={<Performance />} />
            <Route path="/news"         element={<News />} />
            <Route path="/llm"          element={<LLM />} />
            <Route path="/config"       element={<Config />} />
            <Route path="/admin"        element={<Admin />} />
            <Route path="/auto-improve" element={<AutoImprove />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
