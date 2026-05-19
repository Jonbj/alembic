import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchNews, type NewsItem } from '@/api/news'

function safeUrl(url: string): string | undefined {
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') return url
  } catch {}
  return undefined
}

export default function News() {
  const [ticker, setTicker] = useState('')
  const [source, setSource] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  const { data: news = [], isLoading, error } = useQuery({
    queryKey: ['news', ticker, source],
    queryFn: () => fetchNews({ limit: 200, ticker: ticker || undefined, source: source || undefined }),
    refetchInterval: 300000,
  })

  function sentimentBadge(raw: number | null) {
    if (raw === null) return <span className="badge badge-grey">—</span>
    if (raw > 0.1) return <span className="badge badge-green">Positive</span>
    if (raw < -0.1) return <span className="badge badge-red">Negative</span>
    return <span className="badge badge-grey">Neutral</span>
  }

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>News</h2>

      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input placeholder="Filter ticker..." value={ticker} onChange={(e) => setTicker(e.target.value)} style={{ width: 160 }} />
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">All sources</option>
          <option value="gdelt_gkg">GDELT GKG</option>
          <option value="marketaux">MarketAux</option>
          <option value="alpaca">Alpaca</option>
        </select>
        <span style={{ color: 'var(--text-muted)', alignSelf: 'center', fontSize: 12 }}>{news.length} articles</span>
      </div>

      {isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading...</p>}
      {error && <p style={{ color: 'var(--red)' }}>Error loading news</p>}

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr><th>Title</th><th>Source</th><th>Ticker</th><th>Sentiment</th><th>Time</th></tr>
          </thead>
          <tbody>
            {news.map((item: NewsItem) => (
              <Fragment key={item.id}>
                <tr
                  onClick={() => setExpanded(expanded === item.id ? null : item.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <span style={{ color: 'var(--blue)' }}>
                      {expanded === item.id ? '▼ ' : '▶ '}
                    </span>
                    {item.title}
                  </td>
                  <td><span className="badge badge-grey">{item.source}</span></td>
                  <td><strong>{item.ticker}</strong></td>
                  <td>{sentimentBadge(item.raw_sentiment)}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                    {new Date(item.fetched_at).toLocaleString()}
                  </td>
                </tr>
                {expanded === item.id && (
                  <tr>
                    <td colSpan={5} style={{ background: '#f8fafc', padding: '12px 16px' }}>
                      {(() => {
                        const href = safeUrl(item.url)
                        return href
                          ? <a href={href} target="_blank" rel="noreferrer" style={{ color: 'var(--blue)', fontSize: 12 }}>{item.url}</a>
                          : <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.url}</span>
                      })()}
                      {item.raw_sentiment !== null && (
                        <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                          Raw sentiment score: {item.raw_sentiment?.toFixed(4)}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {news.length === 0 && !isLoading && (
              <tr><td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No news</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
