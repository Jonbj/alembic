import { useSearchParams } from 'react-router-dom'
import Config from '@/pages/Config'
import Admin from '@/pages/Admin'
import SystemLog from '@/pages/SystemLog'
import { HelpButton } from '@/components/shared/HelpButton'

type OperationsTab = 'system' | 'config' | 'admin'

const TABS: Array<{ id: OperationsTab; label: string; description: string }> = [
  { id: 'system', label: 'System', description: 'Scheduler, activity log, PEAD signals' },
  { id: 'config', label: 'Config', description: 'Watchlist, risk parameters, read-only config' },
  { id: 'admin', label: 'Admin', description: 'Kill switch and operating mode' },
]

function isOperationsTab(value: string | null): value is OperationsTab {
  return value === 'system' || value === 'config' || value === 'admin'
}

export default function Operations() {
  const [params, setParams] = useSearchParams()
  const requestedTab = params.get('tab')
  const activeTab: OperationsTab = isOperationsTab(requestedTab) ? requestedTab : 'system'

  const setTab = (tab: OperationsTab) => {
    setParams({ tab }, { replace: true })
  }

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 20, fontWeight: 700 }}>Operations</h2>
      <p style={{ margin: '0 0 20px', color: 'var(--text-muted)', fontSize: 14 }}>
        Operational status, configuration, and emergency controls.
      </p>

      <HelpButton title="Operations — Guida" sections={[
        {
          heading: 'System',
          content: 'Vista read-only per verificare scheduler, activity log e segnali PEAD. È il punto di partenza consigliato prima di intervenire.',
        },
        {
          heading: 'Config',
          content: 'Configurazione operativa: watchlist, risk parameters e full config read-only. Le modifiche sono permanenti e richiedono conferma per valori ad alto rischio.',
        },
        {
          heading: 'Admin',
          content: 'Controlli ad alto impatto: kill switch e operating mode. Usali solo con runbook/preflight coerente. La pagina mantiene conferme e recovery token esistenti.',
        },
      ]} />

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: 10,
        marginBottom: 24,
      }}>
        {TABS.map((tab) => {
          const active = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => setTab(tab.id)}
              style={{
                textAlign: 'left',
                padding: '12px 14px',
                borderRadius: 8,
                border: `1px solid ${active ? 'var(--blue)' : 'var(--border)'}`,
                background: active ? '#dbeafe' : '#fff',
                color: active ? '#1d4ed8' : 'inherit',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: 14 }}>{tab.label}</div>
              <div style={{ color: active ? '#1d4ed8' : 'var(--text-muted)', fontSize: 12, marginTop: 2 }}>
                {tab.description}
              </div>
            </button>
          )
        })}
      </div>

      {activeTab === 'system' && <SystemLog />}
      {activeTab === 'config' && <Config />}
      {activeTab === 'admin' && <Admin />}
    </div>
  )
}
