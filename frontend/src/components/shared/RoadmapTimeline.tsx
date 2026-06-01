/**
 * RoadmapTimeline — Visualizza lo stato delle fasi del progetto Alembic v2.
 * Ogni fase mostra: nome, stato, metriche chiave, task completati.
 */

export type PhaseStatus = 'done' | 'pass' | 'in_progress' | 'r_and_d' | 'paused' | 'pending'

export interface Phase {
  id: string
  label: string
  title: string
  status: PhaseStatus
  strategy?: string
  sharpe?: number
  gates?: { pass: number; total: number }
  tasks?: { done: number; total: number }
  highlights?: string[]
}

const STATUS_CONFIG: Record<PhaseStatus, { icon: string; bg: string; border: string; label: string }> = {
  done:        { icon: '✅', bg: 'rgba(22,163,74,0.08)', border: '#16a34a', label: 'Completata' },
  pass:        { icon: '✅', bg: 'rgba(22,163,74,0.12)', border: '#16a34a', label: 'Gate PASS' },
  in_progress: { icon: '🔄', bg: 'rgba(59,130,246,0.08)', border: '#3b82f6', label: 'In corso' },
  r_and_d:     { icon: '🔬', bg: 'rgba(234,179,8,0.08)',  border: '#eab308', label: 'R&D Sleeve' },
  paused:      { icon: '⏸',  bg: 'rgba(100,116,139,0.08)', border: '#64748b', label: 'In pausa' },
  pending:     { icon: '⏳', bg: 'rgba(100,116,139,0.05)', border: '#334155', label: 'Prossima' },
}

export const PHASES: Phase[] = [
  {
    id: 'A',
    label: 'Fase A',
    title: 'Foundation',
    status: 'done',
    tasks: { done: 7, total: 7 },
    highlights: [
      'ParquetCache + DataLoader',
      'Backtest Engine + Cost Model',
      'Anti-look-ahead suite',
      'Walk-forward + Analytics',
      '5 validation gates',
    ],
  },
  {
    id: 'B',
    label: 'Fase B',
    title: 'S1 TimeSeries Momentum',
    status: 'pass',
    strategy: 'S1',
    sharpe: 0.51,
    gates: { pass: 5, total: 5 },
    tasks: { done: 5, total: 5 },
    highlights: [
      'Signal computation + vol sizing',
      'Walk-forward + perturbation',
      'Sensitivity analysis',
      'OOS Sharpe 0.51',
    ],
  },
  {
    id: 'C',
    label: 'Fase C',
    title: 'S3 Cross-Sectional Momentum',
    status: 'r_and_d',
    strategy: 'S3',
    sharpe: 0.15,
    gates: { pass: 3, total: 5 },
    tasks: { done: 3, total: 3 },
    highlights: [
      'Gate 3 (CV) e Gate 5 (stress) falliti',
      'Sharpe 0.15 — troppo basso per il live',
      'Tuning parametri rinviato a post-Fase-F',
    ],
  },
  {
    id: 'D',
    label: 'Fase D',
    title: 'S2 Volatility Risk Premium',
    status: 'in_progress',
    strategy: 'S2',
    highlights: [
      'VRP via VIX derivatives',
      'Broker: Alpaca (paper)',
      'IBKR fallback (in approvazione)',
    ],
  },
  {
    id: 'E',
    label: 'Fase E',
    title: 'S4 News-Driven Tactical',
    status: 'paused',
    strategy: 'S4',
    highlights: ['Aspetta completamento Fase D'],
  },
  {
    id: 'F',
    label: 'Fase F',
    title: 'Portfolio Combiner',
    status: 'pending',
    highlights: ['Integrazione S1+S2+S4', 'Gestione rischio aggregata'],
  },
]

export function RoadmapTimeline({ phases }: { phases?: Phase[] }) {
  const data = phases ?? PHASES
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {data.map((phase, i) => {
        const cfg = STATUS_CONFIG[phase.status]
        const isLast = i === data.length - 1
        const isActive = phase.status === 'pass' || phase.status === 'done' || phase.status === 'in_progress' || phase.status === 'r_and_d'

        return (
          <div key={phase.id} style={{ display: 'flex', gap: 16 }}>
            {/* Timeline rail */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 36, flexShrink: 0 }}>
              {/* Dot */}
              <div style={{
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: cfg.bg,
                border: `2px solid ${cfg.border}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 13,
                flexShrink: 0,
              }}>
                {cfg.icon}
              </div>
              {/* Connector line */}
              {!isLast && (
                <div style={{
                  width: 2,
                  flex: 1,
                  minHeight: 24,
                  background: isActive ? '#334155' : '#1e293b',
                  marginTop: 2,
                }} />
              )}
            </div>

            {/* Card content */}
            <div style={{
              paddingBottom: isLast ? 0 : 16,
              flex: 1,
              minWidth: 0,
            }}>
              <div style={{
                background: cfg.bg,
                border: `1px solid ${isActive ? cfg.border : '#1e293b'}`,
                borderRadius: 8,
                padding: '10px 14px',
                opacity: phase.status === 'pending' ? 0.5 : 1,
              }}>
                {/* Header row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, fontSize: 14, color: '#e2e8f0' }}>
                    {phase.label}
                  </span>
                  <span style={{ fontSize: 13, color: '#94a3b8' }}>
                    {phase.title}
                  </span>
                  <span style={{
                    fontSize: 10,
                    fontWeight: 600,
                    padding: '2px 7px',
                    borderRadius: 4,
                    background: cfg.border,
                    color: phase.status === 'r_and_d' ? '#1e293b' : '#fff',
                    whiteSpace: 'nowrap',
                  }}>
                    {cfg.label}
                  </span>
                </div>

                {/* Metrics row */}
                {(phase.sharpe !== undefined || phase.gates || phase.tasks) && (
                  <div style={{ display: 'flex', gap: 14, marginBottom: 6, flexWrap: 'wrap' }}>
                    {phase.sharpe !== undefined && (
                      <span style={{ fontSize: 12, color: '#94a3b8' }}>
                        Sharpe <strong style={{ color: phase.sharpe > 0.3 ? '#16a34a' : phase.sharpe > 0.1 ? '#eab308' : '#dc2626' }}>
                          {phase.sharpe.toFixed(2)}
                        </strong>
                      </span>
                    )}
                    {phase.gates && (
                      <span style={{ fontSize: 12, color: '#94a3b8' }}>
                        Gates <strong style={{ color: phase.gates.pass === phase.gates.total ? '#16a34a' : '#eab308' }}>
                          {phase.gates.pass}/{phase.gates.total}
                        </strong>
                      </span>
                    )}
                    {phase.tasks && (
                      <span style={{ fontSize: 12, color: '#94a3b8' }}>
                        Task <strong style={{ color: phase.tasks.done === phase.tasks.total ? '#16a34a' : '#94a3b8' }}>
                          {phase.tasks.done}/{phase.tasks.total}
                        </strong>
                      </span>
                    )}
                  </div>
                )}

                {/* Highlights */}
                {phase.highlights && phase.highlights.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {phase.highlights.map((h, hi) => (
                      <span key={hi} style={{ fontSize: 11, color: '#64748b', lineHeight: 1.5 }}>
                        · {h}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}