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

const HEADER: React.CSSProperties = {
  background: '#0f172a',
  fontSize: 11,
  color: '#64748b',
  fontWeight: 600,
  textTransform: 'uppercase',
  padding: '8px 12px',
  letterSpacing: '0.05em',
}

const ROW: React.CSSProperties = {
  fontSize: 13,
  color: '#e2e8f0',
  padding: '8px 12px',
  borderTop: '1px solid #0f172a',
  cursor: 'pointer',
}

const ROW_EXPANDED: React.CSSProperties = {
  ...ROW,
  background: '#0f172a',
}

const EXPANDED_DETAIL: React.CSSProperties = {
  padding: '6px 12px 10px',
  background: '#0f172a',
  fontSize: 12,
  color: '#94a3b8',
  borderTop: '1px solid #1e293b',
}

export function DataTable({ columns, rows, emptyMessage = 'No data.', loading = false }: Props) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const templateColumns = columns.map(c => c.width).join(' ')

  return (
    <div style={{ background: '#1e293b', borderRadius: 8, overflow: 'hidden' }}>
      <div style={{ display: 'grid', gridTemplateColumns: templateColumns, ...HEADER }}>
        {columns.map(c => <span key={c.label}>{c.label}</span>)}
      </div>

      {loading && (
        <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>Loading…</div>
      )}

      {!loading && rows.map((row, i) => (
        <div key={i}>
          <div
            onClick={() => row.expanded ? setExpandedIdx(expandedIdx === i ? null : i) : undefined}
            style={{
              display: 'grid',
              gridTemplateColumns: templateColumns,
              ...(expandedIdx === i ? ROW_EXPANDED : ROW),
              cursor: row.expanded ? 'pointer' : 'default',
            }}
          >
            {row.cells.map((cell, j) => <span key={j}>{cell}</span>)}
          </div>
          {expandedIdx === i && row.expanded && (
            <div style={EXPANDED_DETAIL}>{row.expanded}</div>
          )}
        </div>
      ))}

      {!loading && rows.length === 0 && (
        <div style={{ padding: 20, color: '#64748b', textAlign: 'center' }}>{emptyMessage}</div>
      )}
    </div>
  )
}
