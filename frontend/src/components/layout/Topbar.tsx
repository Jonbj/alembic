import { useLocation } from 'react-router-dom'
import { useStore } from '@/store'

const PAGE_META: Record<string, { name: string; group: string }> = {
  '/':             { name: 'Overview',     group: 'trade' },
  '/signals':      { name: 'Signals',      group: 'trade' },
  '/trading':      { name: 'Trading',      group: 'trade' },
  '/performance':  { name: 'Performance',  group: 'trade' },
  '/backtest':     { name: 'Backtest',     group: 'research' },
  '/news':         { name: 'News',         group: 'research' },
  '/llm':          { name: 'LLM',          group: 'research' },
  '/config':       { name: 'Config',       group: 'system' },
  '/admin':        { name: 'Admin',        group: 'system' },
  '/auto-improve': { name: 'Auto-Improve', group: 'system' },
}

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="3"/>
      <path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/>
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 9.5A6 6 0 1 1 6.5 3 5 5 0 0 0 13 9.5z"/>
    </svg>
  )
}

export function Topbar() {
  const location = useLocation()
  const { mode, theme, killswitchActive, setTheme } = useStore()
  const meta = PAGE_META[location.pathname] ?? { name: location.pathname, group: 'trade' }

  const isLive = mode === 'full_auto'

  return (
    <header className="topbar">
      <div className="crumbs">
        <span className="here">{meta.name}</span>
        <span className="sub">/ {meta.group}</span>
      </div>
      <div className="divider" />
      <div className="spacer" />
      <span className={`pill mode-pill${isLive ? ' mode-live' : ''}`}>
        <span className="dot" style={{ background: 'currentColor', width: 6, height: 6, borderRadius: '50%', display: 'inline-block' }} />
        {mode.replace('_', ' ')}
      </span>
      <span
        className="pill kill-pill"
        data-state={killswitchActive ? 'tripped' : 'armed'}
      >
        <span
          className={`dot${killswitchActive ? ' red pulse' : ' green'}`}
          style={{ position: 'relative' }}
        />
        {killswitchActive ? 'KILL TRIPPED' : 'killswitch armed'}
      </span>
      <button
        className="icon-btn"
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        title="Toggle theme"
      >
        {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
      </button>
    </header>
  )
}
