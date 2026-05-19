import { apiFetch } from './client'

export interface NewsItem {
  id: number
  title: string
  url: string
  source: string
  ticker: string
  raw_sentiment: number | null
  fetched_at: string
}

export const fetchNews = (params?: { limit?: number; ticker?: string; source?: string }) => {
  const q = new URLSearchParams()
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.ticker) q.set('ticker', params.ticker)
  if (params?.source) q.set('source', params.source)
  return apiFetch<NewsItem[]>(`/api/news/recent?${q}`)
}
