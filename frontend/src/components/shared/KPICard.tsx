export function KPICard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 160 }}>
      <div style={{ color: 'var(--text-muted)', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, margin: '6px 0 2px' }}>{value}</div>
      {sub && <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>{sub}</div>}
    </div>
  )
}
