export function DirectionBadge({ score }: { score: number }) {
  if (score > 0.1)  return <span className="badge buy">BUY ▲</span>
  if (score < -0.1) return <span className="badge sell">SELL ▼</span>
  return <span className="badge hold">HOLD —</span>
}
