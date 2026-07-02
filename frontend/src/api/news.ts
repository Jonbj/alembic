import { apiFetch } from './client'

export interface NewsItem {
  id: number
  title: string
  url: string
  source: string
  ticker: string
  raw_sentiment: number | null
  body_snippet: string | null
  fetched_at: string
  published_at: string | null
  signal_count: number
  decision_count: number
  order_count: number
}

export interface NewsSourceQualityRow {
  source: string
  news_count: number
  with_ticker_count: number
  with_sentiment_count: number
  avg_abs_raw_sentiment: number | null
  avg_publish_to_fetch_minutes: number | null
  signals_count: number
  decisions_count: number
  orders_count: number
  trades_count: number
  closed_trades_count: number
  avg_score: number | null
  avg_confidence: number | null
  avg_net_pnl: number | null
  total_net_pnl: number | null
  win_rate: number | null
  signal_rate: number | null
  decision_rate: number | null
  order_rate: number | null
}

export const fetchNews = (params?: { limit?: number; ticker?: string; source?: string }) => {
  const q = new URLSearchParams()
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.ticker) q.set('ticker', params.ticker)
  if (params?.source) q.set('source', params.source)
  return apiFetch<NewsItem[]>(`/api/news/recent?${q}`)
}

export const fetchNewsSourceQuality = (params?: { days?: number }) => {
  const q = new URLSearchParams()
  if (params?.days) q.set('days', String(params.days))
  return apiFetch<NewsSourceQualityRow[]>(`/api/news/source-quality?${q}`)
}
