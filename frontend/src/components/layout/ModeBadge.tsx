import { useStore } from '@/store'

const MODE_STYLE: Record<string, string> = {
  backtest: 'badge-grey',
  paper: 'badge-blue',
  semi_auto: 'badge-yellow',
  full_auto: 'badge-green',
  halted: 'badge-red',
}

export function ModeBadge() {
  const mode = useStore((s) => s.mode)
  return <span className={`badge ${MODE_STYLE[mode] ?? 'badge-grey'}`}>{mode.replace('_', ' ')}</span>
}
