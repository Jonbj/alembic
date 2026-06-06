import { useState } from 'react'
import { HelpButton } from '@/components/shared/HelpButton'

const TABS = [
  { id: 'alembic-overview', label: 'Overview' },
  { id: 'alembic-risk',     label: 'Risk Monitor' },
  { id: 'alembic-decay',    label: 'Decay Monitor' },
] as const

type TabId = typeof TABS[number]['id']

export default function DashboardPage() {
  const [active, setActive] = useState<TabId>('alembic-overview')
  const hostname = window.location.hostname
  const grafanaBase = `http://${hostname}:3001`
  const src = `${grafanaBase}/d/${active}?kiosk=1&theme=dark&refresh=5m`

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '0 0 0 0', position: 'relative' }}>
      <HelpButton title="Monitoring — Grafana Dashboards" sections={[
        {
          heading: 'Cosa mostra questa pagina',
          content: 'Embed live dei dashboard Grafana (porta 3001). I dati si aggiornano ogni 5 minuti automaticamente. Il link "Open in Grafana ↗" apre il dashboard completo in una nuova scheda con tutti i pannelli accessibili.',
        },
        {
          heading: 'Tab Overview',
          content: 'Panoramica operativa del sistema in tempo reale:\n\n**P&L cumulativo** — rendimento totale dall\'inizio del paper trading\n**Posizioni aperte** — numero di posizioni attive e notional investito\n**IC recente** — Information Coefficient degli ultimi 30 giorni per modello\n**Segnali attivi** — quanti ticker hanno un segnale fresco (<30 min)\n**Spesa LLM** — token consumati oggi e costo stimato\n**Volume news** — articoli ingestiti nelle ultime 24h per sorgente',
        },
        {
          heading: 'Tab Risk Monitor',
          content: 'Monitoraggio dell\'esposizione di portfolio:\n\n**Esposizione totale** — somma dei pesi assoluti (limite: 50%). Sopra il 40% il sistema entra in modalità cautela.\n**HHI (Herfindahl-Hirschman Index)** — concentrazione: 0=perfettamente diversificato, 1=tutto su un asset. Soglia di alert: >0.25.\n**Peso per asset** — nessun singolo ticker può superare 10% del NAV.\n**Pesi per strategia** — distribuzione effettiva S1/S2/S4 vs allocazione target.\n**Pesi modelli LLM** — distribuzione LOO ICIR tra Kimi/Qwen/DeepSeek/GLM.',
        },
        {
          heading: 'Tab Decay Monitor',
          content: 'Confronto mensile tra performance recente (ultimi 90 gg) e baseline OOS per strategia:\n\n**IC decay** — se l\'IC recente scende >30% sotto il baseline OOS, alert giallo.\n**Sharpe decay** — confronto Sharpe rolling 90gg vs OOS storico.\n**Hit rate decay** — percentuale di predizioni corrette in trend discendente?\n**Drawdown** — massima perdita dal picco: >20% è soglia di revisione.\n\nAlert rosso (score ≥0.5) = valutare sospensione della strategia e revisione dei parametri.',
        },
        {
          heading: 'Come accedere a Grafana direttamente',
          content: 'Grafana è disponibile su **porta 3001** dello stesso host. Credenziali: admin/admin (primo accesso) — cambiare la password dopo il deploy.\n\nDashboard IDs:\n• alembic-overview — Overview\n• alembic-risk — Risk Monitor\n• alembic-decay — Decay Monitor\n\nPer creare alert Grafana (email/Slack), configurare un Contact Point in Grafana → Alerting → Contact Points.',
        },
      ]} />
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '12px 20px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
      }}>
        <span style={{ color: 'var(--text)', fontWeight: 600, fontSize: 15, marginRight: 8 }}>
          Monitoring
        </span>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActive(tab.id)}
            style={{
              padding: '5px 14px',
              fontSize: 13,
              fontWeight: active === tab.id ? 600 : 400,
              color: active === tab.id ? 'white' : 'var(--text-muted)',
              background: active === tab.id ? 'var(--blue)' : 'transparent',
              border: `1px solid ${active === tab.id ? 'var(--blue)' : 'var(--border)'}`,
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            {tab.label}
          </button>
        ))}
        <a
          href={`${grafanaBase}/d/${active}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)', textDecoration: 'none' }}
        >
          Open in Grafana ↗
        </a>
      </div>
      <iframe
        key={src}
        src={src}
        title={`Grafana ${active}`}
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
        style={{
          flex: 1,
          width: '100%',
          border: 'none',
          minHeight: 0,
        }}
      />
    </div>
  )
}
