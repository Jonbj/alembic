import { useEffect, useMemo, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ModeBadge } from './ModeBadge'
import { useStore } from '@/store'
import type { LLMModelInfo } from '@/store'
import { activeModelLabel } from '@/utils/llm'
import alembicLogo from '@/assets/alembic.png'

const NAV = [
  { to: '/',            label: 'Overview',    icon: '⊞' },
  { to: '/news',        label: 'News',        icon: '📰' },
  { to: '/llm',         label: 'LLM',         icon: '🤖' },
  { to: '/signals',     label: 'Signals',     icon: '⚡' },
  { to: '/quality',     label: 'Quality',     icon: '🔬' },
  { to: '/trading',     label: 'Trading',     icon: '📈' },
  { to: '/performance',   label: 'Performance',  icon: '📊' },
  { to: '/strategies',  label: 'Strategies',  icon: '🎯' },
  { to: '/auto-improve',  label: 'Auto-Improve', icon: '🔧' },
  { to: '/validation',  label: 'Validation',  icon: '🧪' },
  { to: '/labeling',    label: 'Labeling',    icon: '🏷️' },
  { to: '/backtest',    label: 'Backtest',    icon: '🔬' },
  { to: '/operations',  label: 'Admin',       icon: '🔒' },
  { to: '/docs',        label: 'Docs',        icon: '📖' },
]

export function Sidebar() {
  const { token, logout, llmModels, setLlmModels, llmModelRegistry, setLlmModelRegistry } = useStore()

  // Load registry on first render if Layout hasn't already.
  useEffect(() => {
    if (llmModelRegistry) return
    fetch('/api/admin/status', { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (data?.llm_model_registry) setLlmModelRegistry(data.llm_model_registry)
      })
      .catch(() => { /* backend unreachable */ })
  }, [llmModelRegistry, setLlmModelRegistry, token])

  const [pendingSelection, setPendingSelection] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const pendingKeys = useMemo(
    () => new Set((pendingSelection ?? llmModels).split(',').filter(Boolean)),
    [llmModels, pendingSelection],
  )

  const applySelection = async (keys: Set<string>) => {
    const canonical = Array.from(keys).join(',') || 'all'
    setSaving(true)
    try {
      const res = await fetch('/api/admin/llm-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ models: canonical }),
      })
      if (res.ok) {
        const data = await res.json()
        setLlmModels(data.llm_models)
        if (data.model_registry) setLlmModelRegistry(data.model_registry)
        setPendingSelection(null)
      } else {
        console.warn(`LLM model update failed: ${res.status}`)
      }
    } catch { /* network error — no state change */ }
    setSaving(false)
  }

  const toggleKey = (key: string) => {
    const next = new Set(pendingKeys)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setPendingSelection(Array.from(next).join(','))
  }

  const applyEconomy = () => {
    const economy = llmModelRegistry?.models.find((m: LLMModelInfo) => m.economy_default)
    applySelection(new Set(economy ? [economy.key] : ['glm52']))
  }

  const handleLogout = () => {
    logout()
    window.location.href = '/login'
  }

  const registry = llmModelRegistry
  const selectionLabel = registry ? activeModelLabel(registry.models) : (llmModels === 'all' ? 'Inferred ensemble' : llmModels)
  const registryModels: LLMModelInfo[] = registry?.models ?? []

  return (
    <nav className="app-sidebar" style={{
      width: 'var(--sidebar-w)',
      minWidth: 'var(--sidebar-w)',
      background: '#1e293b',
      display: 'flex',
      flexDirection: 'column',
      minHeight: '100vh',
      position: 'sticky',
      top: 0,
    }}>
      <div style={{ padding: '16px 12px 12px', display: 'flex', alignItems: 'center', gap: 8, borderBottom: '1px solid #334155', marginBottom: 4 }}>
        <img src={alembicLogo} alt="Alembic" style={{ width: 32, height: 32, borderRadius: 6, objectFit: 'cover' }} />
        <div>
          <div style={{ color: 'white', fontWeight: 700, fontSize: 14, letterSpacing: '-0.3px', lineHeight: 1.1 }}>Alembic</div>
          <div style={{ color: '#64748b', fontSize: 10, fontWeight: 500, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Open Source Finance</div>
        </div>
      </div>

      <div style={{ flex: 1, padding: '4px 0' }}>
        {NAV.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '9px 14px',
              color: isActive ? 'white' : '#94a3b8',
              background: isActive ? 'var(--blue)' : 'transparent',
              borderRadius: 6,
              margin: '1px 6px',
              textDecoration: 'none',
              fontSize: 13,
              fontWeight: isActive ? 600 : 400,
              transition: 'background 0.15s',
            })}
          >
            <span>{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </div>

      <div style={{ padding: '12px 14px', borderTop: '1px solid #334155' }}>
        <ModeBadge />

        {/* Registry-backed model-pair selector (WS-1, 2026-07-14). */}
        <div style={{
          marginTop: 8,
          padding: '8px 10px',
          border: '1px solid #334155',
          borderRadius: 6,
          background: '#0f172a',
          fontSize: 11,
          color: '#94a3b8',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontWeight: 600, color: '#e2e8f0' }}>LLM ensemble</span>
            <span style={{ color: '#fcd34d' }}>{selectionLabel}</span>
          </div>
          {registry ? (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 8 }}>
                {registryModels.map((model: LLMModelInfo) => (
                  <label key={model.key} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={pendingKeys.has(model.key)}
                      onChange={() => toggleKey(model.key)}
                      disabled={saving}
                    />
                    <span style={{ color: pendingKeys.has(model.key) ? '#e2e8f0' : '#94a3b8' }}>{model.label}</span>
                  </label>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  onClick={() => applySelection(pendingKeys)}
                  disabled={saving || pendingKeys.size === 0}
                  style={{
                    flex: 1,
                    padding: '4px 8px',
                    fontSize: 11,
                    background: pendingKeys.size > 0 ? '#0ea5e9' : '#475569',
                    color: 'white',
                    border: 'none',
                    borderRadius: 4,
                    cursor: pendingKeys.size > 0 ? 'pointer' : 'not-allowed',
                  }}
                >
                  {saving ? 'Saving…' : 'Apply'}
                </button>
                <button
                  onClick={applyEconomy}
                  disabled={saving}
                  title="Single economy model (lowest token cost)"
                  style={{
                    padding: '4px 8px',
                    fontSize: 11,
                    background: 'transparent',
                    color: '#94a3b8',
                    border: '1px solid #334155',
                    borderRadius: 4,
                    cursor: 'pointer',
                  }}
                >
                  Economy
                </button>
              </div>
            </>
          ) : (
            <div style={{ fontStyle: 'italic', color: '#64748b' }}>Loading registry…</div>
          )}
        </div>

        <button
          onClick={handleLogout}
          style={{ marginTop: 6, width: '100%', background: 'transparent', color: '#94a3b8', border: '1px solid #334155', fontSize: 12 }}
        >
          ⏻ Logout
        </button>
      </div>
    </nav>
  )
}
