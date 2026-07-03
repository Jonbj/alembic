// ROADMAP_DATA_ALPHA §7.4 removal thresholds:
// remove if (hit-rate <40% AND P&L 30d <0) OR latency p50 >24h OR near-zero >50%.
import { describe, expect, it } from 'vitest'
import { sourceVerdict } from '@/pages/qualitySourceVerdict'

describe('sourceVerdict', () => {
  it('flags a source losing money with low hit rate', () => {
    expect(sourceVerdict({ hitRate: 0.29, totalPnl: -282, latencyP50Min: 60, nearZeroRate: 0.2 }).tone).toBe('bad')
  })
  it('flags a stale source even if P&L is flat', () => {
    expect(sourceVerdict({ hitRate: 0.5, totalPnl: 0, latencyP50Min: 25 * 60, nearZeroRate: 0.2 }).tone).toBe('bad')
  })
  it('flags high near-zero rate', () => {
    expect(sourceVerdict({ hitRate: 0.5, totalPnl: 10, latencyP50Min: 60, nearZeroRate: 0.55 }).tone).toBe('bad')
  })
  it('passes a healthy source', () => {
    expect(sourceVerdict({ hitRate: 0.55, totalPnl: 120, latencyP50Min: 45, nearZeroRate: 0.2 }).tone).toBe('good')
  })
  it('is neutral without enough data', () => {
    expect(sourceVerdict({ hitRate: null, totalPnl: null, latencyP50Min: null, nearZeroRate: null }).tone).toBe('neutral')
  })
  it('warns on borderline hit rate', () => {
    expect(sourceVerdict({ hitRate: 0.42, totalPnl: 5, latencyP50Min: 60, nearZeroRate: 0.2 }).tone).toBe('warn')
  })
})
