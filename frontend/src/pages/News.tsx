import { Fragment, useState, useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fmtDateTime } from '@/utils/format'
import { useQuery } from '@tanstack/react-query'
import { fetchNews, type NewsItem } from '@/api/news'
import { HelpButton } from '@/components/shared/HelpButton'
import { SignalTraceLinks } from '@/components/shared/SignalTraceLinks'

function safeUrl(url: string): string | undefined {
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') return url
  } catch {}
  return undefined
}

export default function News() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [ticker, setTicker] = useState(searchParams.get('ticker') ?? '')
  const [source, setSource] = useState(searchParams.get('source') ?? '')
  const [limit, setLimit] = useState(Number(searchParams.get('limit') ?? 50))
  const [actionableOnly, setActionableOnly] = useState(searchParams.get('actionable') === '1')
  const [expanded, setExpanded] = useState<number | null>(null)

  const { data: news = [], isLoading, error } = useQuery({
    queryKey: ['news', ticker, source, limit],
    queryFn: () => fetchNews({ limit, ticker: ticker || undefined, source: source || undefined }),
    refetchInterval: 300000,
  })

  const visibleNews = useMemo(() =>
    actionableOnly
      ? news.filter((item) => item.ticker && item.raw_sentiment != null && Math.abs(item.raw_sentiment) >= 0.1)
      : news
  , [news, actionableOnly])

  const toggleExpanded = useCallback((id: number) => {
    setExpanded((prev) => (prev === id ? null : id))
  }, [])

  const updateTicker = (value: string) => {
    setTicker(value)
    const next = new URLSearchParams(searchParams)
    if (value.trim()) next.set('ticker', value.trim().toUpperCase())
    else next.delete('ticker')
    setSearchParams(next, { replace: true })
  }

  const updateSource = (value: string) => {
    setSource(value)
    const next = new URLSearchParams(searchParams)
    if (value) next.set('source', value)
    else next.delete('source')
    setSearchParams(next, { replace: true })
  }

  const updateLimit = (value: number) => {
    setLimit(value)
    const next = new URLSearchParams(searchParams)
    next.set('limit', String(value))
    setSearchParams(next, { replace: true })
  }

  const updateActionable = (checked: boolean) => {
    setActionableOnly(checked)
    const next = new URLSearchParams(searchParams)
    if (checked) next.set('actionable', '1')
    else next.delete('actionable')
    setSearchParams(next, { replace: true })
  }

  const clearFilters = () => {
    setTicker('')
    setSource('')
    setActionableOnly(false)
    setSearchParams(new URLSearchParams(), { replace: true })
  }

  function sentimentBadge(raw: number | null) {
    if (raw === null) return <span className="badge badge-grey">—</span>
    if (raw > 0.1) return <span className="badge badge-green">Positive</span>
    if (raw < -0.1) return <span className="badge badge-red">Negative</span>
    return <span className="badge badge-grey">Neutral</span>
  }

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>News</h2>
      <HelpButton title="News — Notizie" sections={[
        {
          heading: "Fonti dati",
          content: "Le notizie provengono da sei fonti:\n\n- **Reuters RSS**: feed live di Reuters Business News (ogni 30 min)\n- **CNBC RSS**: feed live CNBC Markets (ogni 30 min)\n- **SEC EDGAR**: filing 8-K da SEC (ogni ora, mercato aperto)\n- **GDELT GKG**: global knowledge graph con entities e sentiment automatizzato\n- **MarketAux**: notizie finanziarie con metadata aziendale\n- **Alpaca / Benzinga**: notizie dal broker direttamente",
        },
        {
          heading: "Sentiment",
          content: "Ogni articolo ha un sentiment grezzo (raw_sentiment): positivo > 0.1, negativo < -0.1, neutro altrimenti. Il sentiment viene calcolato dal modello LLM e alimentato nel sistema di segnali.",
        },
        {
          heading: "Filtraggio",
          content: "Filtra per ticker (es. SPY) o per fonte. Clicca su una riga per espandere e vedere l'URL dell'articolo e il sentiment score dettagliato.",
        },
        {
          heading: "Estrazione ticker (sicurezza)",
          content: "Un ticker sbagliato è peggio di una news persa: genererebbe un ordine su un titolo non correlato. Per questo i ticker ambigui — sigle corte (es. F, T, C, GS) o parole comuni (CAT, ON, META) — vengono associati a un articolo RSS **solo** se citati con cashtag esplicito (es. $F), non come parola sciolta (\"F-150\", \"Vitamin C\"). Le fonti con metadata ticker affidabili (GDELT, MarketAux, Alpaca) non sono toccate. Per questo alcune news di testo potrebbero non comparire associate a un ticker.\n\nÈ in arrivo un **resolver deterministico** che valida ogni ticker contro fonti ufficiali (SEC, OpenFIGI) e l'universo tradabile: quando l'evidenza è debole o ambigua (es. Apple Hospitality APLE vs Apple AAPL) il segnale viene marcato NO_TRADE invece di rischiare il ticker sbagliato.",
        },
      ]} />

      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <input placeholder="Filter ticker..." value={ticker} onChange={(e) => updateTicker(e.target.value)} style={{ width: 160 }} />
        <select value={source} onChange={(e) => updateSource(e.target.value)}>
          <option value="">All sources</option>
          <optgroup label="Live feeds">
            <option value="reuters">Reuters RSS</option>
            <option value="cnbc">CNBC RSS</option>
            <option value="sec_edgar">SEC EDGAR</option>
          </optgroup>
          <optgroup label="Data providers">
            <option value="gdelt_gkg">GDELT GKG</option>
            <option value="marketaux">MarketAux</option>
            <option value="alpaca_benzinga">Alpaca / Benzinga</option>
          </optgroup>
        </select>
        <select value={limit} onChange={(e) => updateLimit(Number(e.target.value))}>
          <option value={50}>50 latest</option>
          <option value={100}>100 latest</option>
          <option value={200}>200 latest</option>
        </select>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--text-muted)', fontSize: 12 }}>
          <input
            type="checkbox"
            checked={actionableOnly}
            onChange={(e) => updateActionable(e.target.checked)}
            style={{ width: 14, height: 14, padding: 0 }}
          />
          actionable only
        </label>
        {(ticker || source || actionableOnly) && (
          <button className="btn-ghost" onClick={clearFilters} style={{ fontSize: 12, padding: '5px 10px' }}>Clear</button>
        )}
        <span style={{ color: 'var(--text-muted)', alignSelf: 'center', fontSize: 12 }}>
          {visibleNews.length} shown · {news.length} fetched
        </span>
      </div>

      {isLoading && <p style={{ color: 'var(--text-muted)' }}>Loading...</p>}
      {error && <p style={{ color: 'var(--red)' }}>Error loading news</p>}

      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr><th>Title</th><th>Source</th><th>Ticker</th><th>Sentiment</th><th>Time</th></tr>
          </thead>
          <tbody>
            {visibleNews.map((item: NewsItem) => (
              <Fragment key={item.id}>
                <tr
                  onClick={() => toggleExpanded(item.id)}
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
                    <span title={`Pubblicato: ${item.published_at ? fmtDateTime(item.published_at) : '—'}`}>
                      {fmtDateTime(item.fetched_at)}
                    </span>
                    {item.published_at && item.published_at !== item.fetched_at && (
                      <span style={{ display: 'block', fontSize: 10, color: 'var(--text-muted)', opacity: 0.7 }}>
                        pub. {fmtDateTime(item.published_at)}
                      </span>
                    )}
                  </td>
                </tr>
                {expanded === item.id && (
                  <tr>
                    <td colSpan={5} style={{ background: '#f8fafc', padding: '12px 16px' }}>
                      {item.body_snippet && (
                        <p style={{ fontSize: 12, color: 'var(--text)', marginBottom: 8, lineHeight: 1.5 }}>
                          {item.body_snippet}
                        </p>
                      )}
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
                      <div style={{ marginTop: 10 }}>
                        <SignalTraceLinks symbol={item.ticker} />
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {visibleNews.length === 0 && !isLoading && (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24 }}>
                  {news.length === 0
                    ? 'No news returned for the selected filters.'
                    : 'No actionable news in the fetched set. Clear filters or increase the limit.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
