export function KPICard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-lbl">{label}</div>
      <div className="kpi-val">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}
