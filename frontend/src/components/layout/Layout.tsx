import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useStore } from '@/store'

export function Layout() {
  const { setKillswitch, setMode, setLlmModels } = useStore()

  useEffect(() => {
    const sync = async () => {
      try {
        const res = await fetch('/api/admin/status')
        if (!res.ok) return
        const data = await res.json()
        setKillswitch(data.killswitch)
        if (data.mode && data.mode !== 'unknown') setMode(data.mode)
        if (data.llm_models) setLlmModels(data.llm_models)
      } catch { /* backend unreachable */ }
    }
    sync()
    const id = setInterval(sync, 15_000)
    return () => clearInterval(id)
  }, [])

  return (
    <>
      <Sidebar />
      <main style={{ flex: 1, padding: '24px', overflowY: 'auto', maxWidth: '100%' }}>
        <Outlet />
      </main>
    </>
  )
}
