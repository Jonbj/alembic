export function DirectionBadge({ score }: { score: number }) {
  if (score > 0.1) return <span className="badge badge-green">BUY ▲</span>
  if (score < -0.1) return <span className="badge badge-red">SELL ▼</span>
  return <span className="badge badge-grey">HOLD —</span>
}
