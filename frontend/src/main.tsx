import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// B5 — applica il tema persistito (mode+theme) al <html> PRIMA del primo
// render. Lo script inline che faceva questo in index.html è stato rimosso
// per rispettare la CSP strict (no inline script). Effetto: FOUC di pochi ms
// sul primo paint — accettabile, il default è dark.
const persisted = JSON.parse(sessionStorage.getItem('alembic-store') || '{}')
const theme = persisted.state?.theme === 'light' ? 'light' : 'dark'
document.documentElement.setAttribute('data-theme', theme)
document.documentElement.style.background = theme === 'light'
  ? 'oklch(0.985 0.003 250)'
  : 'oklch(0.165 0.005 250)'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
