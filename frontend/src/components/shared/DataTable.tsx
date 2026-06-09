import { type ReactNode, useState } from 'react'

export interface Column {
  label: string
  width: string
}

interface RowProps {
  cells: ReactNode[]
  expanded?: ReactNode
}

interface Props {
  columns: Column[]
  rows: RowProps[]
  emptyMessage?: string
  loading?: boolean
}

export function DataTable({ columns, rows, emptyMessage = 'No data.', loading = false }: Props) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const templateColumns = columns.map(c => c.width).join(' ')

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: templateColumns,
        padding: '8px 12px',
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.05em',
        color: 'var(--text-muted)',
        borderBottom: '1px solid var(--border)',
        background: '#f8fafc',
      }}>
        {columns.map(c => <span key={c.label}>{c.label}</span>)}
      </div>

      {loading && (
        <div style={{ padding: 20, color: 'var(--text-muted)', textAlign: 'center' }}>Loading…</div>
      )}

      {!loading && rows.map((row, i) => (
        <div key={i}>
          <div
            onClick={() => row.expanded ? setExpandedIdx(expandedIdx === i ? null : i) : undefined}
            style={{
              display: 'grid',
              gridTemplateColumns: templateColumns,
              padding: '9px 12px',
              fontSize: 13,
              color: 'var(--text)',
              borderBottom: '1px solid var(--border)',
              background: expandedIdx === i ? '#f1f5f9' : 'white',
              cursor: row.expanded ? 'pointer' : 'default',
              alignItems: 'center',
            }}
            onMouseEnter={e => { if (expandedIdx !== i) (e.currentTarget as HTMLElement).style.background = '#f8fafc' }}
            onMouseLeave={e => { if (expandedIdx !== i) (e.currentTarget as HTMLElement).style.background = 'white' }}
          >
            {row.cells.map((cell, j) => <span key={j}>{cell}</span>)}
          </div>
          {expandedIdx === i && row.expanded && (
            <div style={{
              padding: '6px 12px 10px',
              background: '#f1f5f9',
              fontSize: 12,
              color: 'var(--text-muted)',
              borderBottom: '1px solid var(--border)',
            }}>
              {row.expanded}
            </div>
          )}
        </div>
      ))}

      {!loading && rows.length === 0 && (
        <div style={{ padding: 20, color: 'var(--text-muted)', textAlign: 'center' }}>{emptyMessage}</div>
      )}
    </div>
  )
}
