// Source removal thresholds from ROADMAP_DATA_ALPHA_2026-07-02 §7.4.
// Kept as a pure function so the policy is testable without rendering.
export interface SourceHealthInput {
  hitRate: number | null
  totalPnl: number | null
  latencyP50Min: number | null
  nearZeroRate: number | null
}

export interface SourceVerdictResult {
  tone: 'good' | 'warn' | 'bad' | 'neutral'
  reasons: string[]
}

export function sourceVerdict(s: SourceHealthInput): SourceVerdictResult {
  const reasons: string[] = []
  if (s.hitRate == null && s.totalPnl == null && s.latencyP50Min == null && s.nearZeroRate == null) {
    return { tone: 'neutral', reasons: ['no data yet'] }
  }
  if (s.hitRate != null && s.totalPnl != null && s.hitRate < 0.4 && s.totalPnl < 0) {
    reasons.push('hit-rate <40% with negative P&L — removal candidate')
  }
  if (s.latencyP50Min != null && s.latencyP50Min > 24 * 60) {
    reasons.push('latency p50 >24h — stale by design')
  }
  if (s.nearZeroRate != null && s.nearZeroRate > 0.5) {
    reasons.push('near-zero >50% — mostly wasted tokens')
  }
  if (reasons.length > 0) return { tone: 'bad', reasons }
  if ((s.hitRate != null && s.hitRate < 0.45) || (s.nearZeroRate != null && s.nearZeroRate > 0.4)) {
    return { tone: 'warn', reasons: ['borderline — keep under observation'] }
  }
  return { tone: 'good', reasons: ['healthy'] }
}
