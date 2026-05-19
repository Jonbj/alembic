import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <>
      <Sidebar />
      <main style={{ flex: 1, padding: '24px', overflowY: 'auto', maxWidth: '100%' }}>
        <Outlet />
      </main>
    </>
  )
}
