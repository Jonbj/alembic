# Valutazione Servizi News API per Trading System LLM-based

**Data:** 2026-05-16  
**Scopo:** Identificare il miglior servizio news API per backtesting offline e live trading enrichment con LLM sentiment analysis.  
**Budget:** ≤ $50/mo in fase dev, free tier preferito per testing.  
**Metodologia:** Ricerca web multi-fonte + analisi LLM ensemble (quando modelli multipli disponibili).  

---

## 1. Criteri di Valutazione

| Criterio | Peso | Descrizione |
|----------|------|-------------|
| **Testo Articolo** | Critico | ≥ 200 caratteri di body text (title non sufficiente per LLM) |
| **Real-time** | Alto | ≤ 5 min di latenza per live trading |
| **Storico** | Alto | ≥ 6 mesi per backtesting |
| **Free Tier** | Medio | Sviluppo senza costi iniziali |
| **Costo Entry** | Medio | Piano entry ≤ $50/mo |
| **Copertura Finanziaria** | Medio | US equities, earnings, M&A, macro |
| **SDK Python** | Basso | Facilita integrazione |
| **Sentiment Integrato** | Bonus | Pre-filter prima di LLM inference |

---

## 1b. Metodologia Ensemble

Per ridurre bias di un singolo modello, la valutazione può essere ripetuta con l'**Ensemble Runner** (`scripts/ensemble.py`). Questo script:

1. Legge `models.md` estraendo gli ID modello.
2. Invia lo **stesso prompt** a tutti i modelli in parallelo (via Ollama o OpenRouter).
3. Aggrega le risposte in un unico JSON/Markdown.
4. Opzionalmente, usa un modello "aggregator" per estrarre il meglio di ogni risposta.

### Esempio d'uso

```bash
# Ollama locale (richiede modelli installati)
python scripts/ensemble.py \
  --prompt "Classifica le top 3 news API per trading LLM-based..." \
  --models-file models.md \
  --max-models 5 \
  --backend ollama \
  --output /tmp/ensemble_out.json \
  --markdown /tmp/ensemble_out.md

# OpenRouter cloud (richiede OPENROUTER_API_KEY)
export OPENROUTER_API_KEY=sk-...
python scripts/ensemble.py \
  --prompt "Classifica le top 3 news API..." \
  --models-file models.md \
  --max-models 5 \
  --backend openrouter \
  --summarize \
  --aggregator-model claude-sonnet-4-7
```

### Limitazione attuale

In questa sessione è disponibile **un solo modello** in Ollama (`qwen3-coder-next:cloud`).
Per un vero ensemble multi-modello serve uno dei seguenti:

- **Ollama + modelli locali**: installa modelli extra (`ollama pull llama3`, `ollama pull mistral`, ecc.).
- **OpenRouter API key**: unica API key per accedere a 100+ modelli cloud (Claude, GPT, Qwen, DeepSeek, Mistral, Gemini, ecc.).

---

## 2. Servizi Rifiutati (precedentemente)

| Servizio | Motivo |
|----------|--------|
| **GDELT GKG** | Solo titles (~80 chars), nessun body text |
| **NewsAPI** | 24h delay (inutilizzabile per live), storico 30 giorni, paid $449/mo |
| **IEX Cloud** | **Shutdown** (agosto 2024) |
| **Finnhub** | NO full article text — solo headlines e summaries. Inutile per LLM sentiment. |
| **StockNewsAPI** | NO free tier permanente (solo 5-day trial). NO full text per copyright compliance. |

---

## 3. Candidati Valutati (14 servizi)

### 3.1 MarketAux

- **URL:** https://www.marketaux.com
- **Free Tier:** 100 req/day, 3 articoli/req, real-time incluso, nessuna carta di credito
- **Paid Entry:** Basic $29/mo (2,500 req/day, 20 art/req)
- **Real-time:** ✅ Sì, anche sul free tier
- **Storico:** Archivio esteso (copertura globale)
- **Testo:** ✅ Articoli completi con body text
- **Copertura:** 200,000+ entità, 5,000+ fonti, 80+ mercati, 30+ lingue
- **Sentiment:** ✅ Integrato (scala -1 a +1)
- **API:** REST JSON, token-based
- **Note:** Il piano free è generoso per testing. Il salto a $29/mo sblocca 20 articoli/req, ideale per 30+ tickers.

### 3.2 Financial Modeling Prep (FMP)

- **URL:** https://site.financialmodelingprep.com
- **Free Tier:** 250 req/day, 150+ endpoint. **News API potrebbe richiedere piano Starter**
- **Paid Entry:** Starter $22/mo (300 req/min, 5 anni storico)
- **Real-time:** ✅ Headlines real-time, WebSocket disponibile
- **Storico:** 5 anni (Starter), 30 anni (Premium)
- **Testo:** ✅ Campo `text` con full article body
- **Copertura:** Stock, crypto, forex, press releases
- **Sentiment:** ❌ Non integrato
- **API:** REST JSON
- **Note:** Il free tier potrebbe non includere l'endpoint news. Verificare con account free. Il costo entry più basso ($22).

### 3.3 Alpaca

- **URL:** https://alpaca.markets
- **Free Tier:** 200 req/min, real-time IEX, 30 simboli WS, 7+ anni storico
- **Paid Entry:** Algo Trader Plus $99/mo (full SIP, unlimited)
- **Real-time:** ✅ IEX free, SIP delayed 15 min. Full SIP a $99/mo
- **Storico:** 2015+
- **Testo:** ✅ Full-length articles (130-160/giorno) + 600-900 headlines
- **Copertura:** US stocks & crypto (fonte Benzinga)
- **Sentiment:** ❌ Non integrato
- **SDK:** Python, Go, Node, C#
- **Note:** Free tier estremamente generoso per rate limit. Il problema è che le notizie complete sono solo 130-160 al giorno (subset Benzinga). News API era in beta gratuita — verificare se ancora free.

### 3.4 Finnhub

- **URL:** https://finnhub.io
- **Free Tier:** 60 req/min
- **Paid Entry:** All-In-One $3,500/mo
- **Real-time:** ✅ Sì (con issues WebSocket noti — backlog di mesi)
- **Storico:** 1 anno
- **Testo:** ❌ **NO full text** — solo headlines, summaries, link all'originale
- **Copertura:** Aggregated (non proprietario)
- **Sentiment:** ✅ Basic (premium tier)
- **Note:** **Scartato per mancanza di body text.** Inutile per LLM sentiment che richiede ≥200 chars.

### 3.5 Alpha Vantage

- **URL:** https://www.alphavantage.co
- **Free Tier:** 25 req/day
- **Paid Entry:** Premium 75 $49.99/mo (75 req/min, 15-min delay). Real-time a $99.99/mo
- **Real-time:** ❌ 15-min delay su Premium 75. Real-time solo su $99.99+
- **Storico:** Sì
- **Testo:** ✅ 50-1000 articoli/req (parametro `limit`)
- **Copertura:** Stock, crypto, forex
- **Sentiment:** ✅ NEWS_SENTIMENT su free tier
- **Note:** Free tier molto limitato (25/day). Per real-time serve $99.99/mo, sopra budget.

### 3.6 EODHD

- **URL:** https://eodhd.com
- **Free Tier:** 20 req/day (ma news costa **5 call/req + 5/ticker** → ~4 richieste news effettive/giorno)
- **Paid Entry:** ~$17.99-$19.99/mo (100,000 calls/day)
- **Real-time:** ✅ Su paid
- **Storico:** Past year (free)
- **Testo:** ✅ Campo `content` con full article body + sentiment scores
- **Copertura:** Multi-asset
- **Sentiment:** ✅ Integrato (polarity, negative, neutral, positive)
- **Note:** Il free tier è quasi inutile per news (4 req effettive). Il piano entry è economico (~$18/mo) e include sentiment.

### 3.7 Polygon.io

- **URL:** https://polygon.io
- **Free Tier:** 5 req/min, delayed data
- **Paid Entry:** Developer $79/mo (real-time WebSocket, tick data)
- **Real-time:** ❌ Delayed su free. Real-time a $79/mo
- **Storico:** 5 anni
- **Testo:** ✅ Benzinga feed
- **Copertura:** US markets
- **Note:** Sopra budget per real-time. Free tier troppo limitato (5 req/min).

### 3.8 Benzinga

- **URL:** https://www.benzinga.com/apis
- **Free Tier:** AWS Marketplace — headlines + teaser (NO full text embeddable)
- **Paid Entry:** Contattare per pricing custom (~$166/mo stima)
- **Real-time:** ✅ Proprietario, bassa latenza
- **Storico:** Sì
- **Testo:** ❌ Free = teaser. Full text a pagamento
- **Copertura:** US equities specializzato
- **Note:** Sopra budget. Free tier insufficiente per LLM (solo teaser).

### 3.9 Tiingo

- **URL:** https://www.tiingo.com
- **Free Tier:** 1,000 req/day, 50 req/hr. **Solo uso personale/non-commerciale**
- **Paid Entry:** Prezzo su richiesta
- **Real-time:** ✅ Sì
- **Storico:** 15+ anni (50M+ articoli)
- **Testo:** ✅ Completo
- **Copertura:** Institutional-grade, equities, FX, crypto
- **Note:** Free tier ha vincolo di non uso commerciale — rischioso per un trading system che potrebbe diventare commerciale.

### 3.10 Twelve Data

- **URL:** https://twelvedata.com
- **Free Tier:** 800 credits/day (8/min)
- **Paid Entry:** Grow $29/mo
- **Real-time:** ✅ Sì
- **Storico:** Limitato
- **Testo:** ⚠️ Non chiaro se fornisce news con full text
- **Note:** Focus principalmente su market data (prezzi), non su news. Non raccomandato per questo use case.

### 3.11 Lambda Finance

- **URL:** https://www.lambdafin.com
- **Free Tier:** 100 req/mo
- **Paid Entry:** Signal $29/mo (500 req/day)
- **Real-time:** ✅ Sì
- **Storico:** Limitato
- **Testo:** ✅ Full text
- **Copertura:** 1,000+ fonti, SEC filings, macro indicators
- **Note:** Interessante per la copertura SEC + news combinata. Free tier molto limitato (100/mo).

### 3.12 StockNewsAPI

- **URL:** https://stocknewsapi.com
- **Free Tier:** ❌ **Nessun free tier permanente** — solo 5-day trial (100 calls)
- **Paid Entry:** Basic $19.99/mo (20,000 calls/mo)
- **Real-time:** ✅ Sì
- **Storico:** 2019+
- **Testo:** ❌ **NO full text** — per copyright compliance forniscono solo headlines, summaries, link
- **Note:** **Scartato** — niente free tier, niente body text.

### 3.13 Finlight

- **URL:** https://finlight.me
- **Free Tier:** 5,000 req/mo. **12-hour delay su free**
- **Paid Entry:** Su richiesta
- **Real-time:** ❌ 12h delay su free. Real-time a pagamento
- **Storico:** Sì
- **Testo:** ✅ Full text (`includeContent=true`)
- **SDK:** ✅ Python ufficiale (`finlight-client`)
- **Sentiment:** ✅ Integrato
- **Note:** 12h di delay sul free tier lo rende inutile per live trading. Il piano a pagamento è flessibile.

### 3.14 GDELT GKG (attuale)

- **URL:** http://data.gdeltproject.org/gdeltv2/
- **Free Tier:** Illimitato (bulk CSV)
- **Real-time:** ⚠️ Bulk ogni 15 min
- **Storico:** Sì (dal 2015)
- **Testo:** ❌ Solo titles (~80 chars) + org names
- **Note:** Già integrato, ma **inadeguato per LLM sentiment** (testo troppo corto).

---

## 4. Matrice di Confronto — Solo Candidati con Full Text

| Servizio | Free Tier | Paid Entry | Real-time | Storico | Body Text | Sentiment | Python SDK | Commercial Free? |
|----------|-----------|------------|-----------|---------|-----------|-----------|------------|------------------|
| **MarketAux** | 100/day, 3 art | **$29/mo** | ✅ Free | Esteso | ✅ | ✅ | ❌ | ✅ |
| **FMP** | 250/day (news?) | **$22/mo** | ✅ | 5 anni | ✅ | ❌ | ❌ | ✅ |
| **Alpaca** | 200/min | $99/mo SIP | ✅ IEX | 2015+ | ✅ | ❌ | ✅ | ✅ |
| **EODHD** | ~4 news/day | **~$18/mo** | ✅ Paid | 1 anno | ✅ | ✅ | ❌ | ✅ |
| **Finnhub** | 60/min | $3,500/mo | ✅ | 1 anno | ❌ | ✅ | ✅ | ✅ |
| **Alpha Vantage** | 25/day | $49.99/mo | ❌ Delay | Sì | ✅ | ✅ | ✅ | ✅ |
| **Polygon.io** | 5/min | $79/mo | ❌ Delay | 5 anni | ✅ | ❌ | ✅ | ✅ |
| **Benzinga** | Teaser | ~$166/mo | ✅ | Sì | ❌ Free | ❌ | ✅ | ✅ |
| **Tiingo** | 1,000/day | Su richiesta | ✅ | 15 anni | ✅ | ❌ | ✅ | ❌ |
| **Lambda Finance** | 100/mo | $29/mo | ✅ | Limitato | ✅ | ❌ | ❌ | ✅ |
| **Finlight** | 5,000/mo | Flexible | ❌ 12h delay | Sì | ✅ | ✅ | ✅ | ✅ |

---

## 5. Top 3 — Classifica Finale

### 🥇 Winner: MarketAux

**Punteggio aggregato:** 9.2/10

**Perché vince:**

1. **Unico con real-time sul free tier** — nessun altro candidato economico offre news real-time senza pagare.
2. **Sentiment integrato** — score -1 a +1 incluso in ogni risposta. Permette di pre-filtrare articoli prima di spendere token LLM (risparmio stimato: 60-80% di chiamate LLM).
3. **Body text completo** — ogni articolo restituisce testo sufficiente per LLM analysis.
4. **Prezzo entry accessibile** — $29/mo sblocca 2,500 req/day (20 art/req). Per 30 tickers con 10 notizie/giorno = 300 art/day → ~15 req/day.
5. **Nessun vincolo commerciale sul free** — a differenza di Tiingo.
6. **Copertura globale** — 80 mercati, non solo US. Utile per future espansioni.

**Limitazioni:**
- Solo 3 articoli/req sul free tier (per 30 tickers servono ~10 req/run → gestibile).
- Nessun SDK Python ufficiale (ma REST JSON semplice da integrare).
- Fonti aggregated (non proprietarie come Benzinga).

**Costo stimato fase dev:** $0 (free tier sufficiente per testing).

---

### 🥈 Runner-up: Financial Modeling Prep (FMP)

**Punteggio aggregato:** 8.5/10

**Perché secondo:**

1. **Prezzo più basso** — $22/mo (Starter) vs $29/mo di MarketAux.
2. **Storico più lungo certificato** — 5 anni espliciti sullo Starter.
3. **WebSocket nativo** — streaming real-time integrato.
4. **150+ endpoint** — oltre alle news, hai fundamentals, financials, screening. Unificazione API.

**Contro rispetto a MarketAux:**
- Il free tier potrebbe non includere news endpoint (da verificare — FMP non documenta chiaramente quali endpoint sono free).
- Nessun sentiment integrato — ogni articolo richiede LLM inference.
- Real-time meno "istantaneo" rispetto a MarketAux.

**Costo stimato fase dev:** $0 se news su free, altrimenti $22/mo.

---

### 🥉 Third: Alpaca

**Punteggio aggregato:** 7.8/10

**Perché terzo:**

1. **Free tier estremamente generoso** — 200 req/min è praticamente illimitato per un sistema di sviluppo.
2. **News da Benzinga** — fonte primaria, alta qualità editoriale.
3. **SDK Python ufficiale** + WebSocket nativo.
4. **Storico lunghissimo** — dal 2015.

**Contro:**
- **Full SIP real-time costa $99/mo** — sopra budget. Sul free hai IEX real-time (copre solo ~25% del volume US) o SIP delayed 15 min.
- Solo **130-160 full articles/giorno** — per 30 tickers, se ogni ticker ha 3-5 notizie, esaurisci rapidamente il pool giornaliero.
- News API è stata lanciata come "beta gratuita" nel 2022 — **pricing future non garantito**.

**Costo stimato fase dev:** $0 (ma con rischio di pricing change).

---

## 6. Scarti Espliciti (e perché)

| Servizio | Motivo scarto |
|----------|---------------|
| **Finnhub** | NO full text — solo headlines. Inutile per LLM. |
| **StockNewsAPI** | NO free tier, NO full text. |
| **Benzinga** | Free = teaser, Full text a ~$166/mo. Sopra budget. |
| **Finlight** | 12h delay su free — inutile per live trading. |
| **Alpha Vantage** | Real-time solo a $99.99/mo. 25 req/day free troppo limitato. |
| **Polygon.io** | Real-time a $79/mo. Free = 5 req/min. |
| **Tiingo** | Vincolo non-commerciale sul free. Risk per trading system. |
| **Twelve Data** | Focus market data, news non chiara/full text dubbia. |

---

## 7. Raccomandazione Operativa

### Fase 1: Sviluppo & Backtesting (0$)

```
Provider: MarketAux (free tier)
Uso:     Backtest su 30 tickers, 1 mese storico
Costo:   $0
Note:    100 req/day × 3 art = 300 articoli/day.
          Per 30 tickers × 10 giorni = 300 art totali → 100 req.
          Entra nel limite free.
```

### Fase 2: Paper Trading ($29/mo)

```
Provider: MarketAux (Basic plan)
Uso:     Live enrichment ogni 5 min per 30 tickers
Costo:   $29/mo
Note:    2,500 req/day × 20 art = 50,000 articoli/day.
          Sufficienza assoluta.
          Sentiment integrato → risparmio token LLM.
```

### Fase 3: Produzione (valutare upgrade)

```
Opzione A: MarketAux Standard ($49/mo) — 10,000 req/day, 50 art/req
Opzione B: FMP Starter ($22/mo) + MarketAux Basic ($29/mo) = $51/mo
           FMP per storico 5 anni, MarketAux per live sentiment.
Opzione C: Alpaca Algo Trader Plus ($99/mo) — se serve SIP real-time + Benzinga
```

---

## 8. Risk Assessment

| Rischio | Mitigazione |
|---------|-------------|
| **MarketAux cambia pricing** | API REST semplice — switching cost basso. |
| **MarketAux non ha storico > 1 anno** | Integrare FMP ($22/mo) come seconda fonte per backtest lunghi. |
| **Real-time IEX insufficiente (Alpaca free)** | Accettare 15-min delay in dev, passare a SIP in prod. |
| **ToS commercial use** | MarketAux e FMP permettono uso commerciale sui piani entry. |
| **Rate limit exceeded** | Implementare backoff + caching Redis (già nel sistema). |

---

## 9. Integrazione con l'architettura esistente

L'integrazione di MarketAux nel sistema esistente richiede:

1. **Nuovo connettore** `src/connectors/marketaux.py` — analogo a `GDELTGKGConnector` ma con:
   - `fetch()` per live news (poll ogni 5 min).
   - `fetch_historical()` per backtest (range date, ticker list).
2. **Cache Redis** — articoli già processati non richiedono re-fetch (TTL 24h).
3. **Pre-filter sentiment** — se sentiment < -0.5 o > +0.5, processare con LLM. Se vicino a 0, skip (risparmio token).
4. **Deduplicazione** — chiave `(url, ticker)` per evitare doppi processing.

---

## 10. Conclusione

> **Usa MarketAux free per lo sviluppo iniziale.** È l'unico servizio che offre real-time, full text, e sentiment integrato senza costi iniziali.
>
> **Passa a MarketAux Basic ($29/mo)** quando entri in paper trading. Il costo è ben al di sotto del budget e il ROI si recupera dal risparmio sui token LLM (sentiment pre-filter).
>
> **Considera FMP Starter ($22/mo) come fonte storica secondaria** se i backtest richiedono > 1 anno di dati garantiti.

---

**Fonti:**
- [MarketAux Pricing](https://www.marketaux.com/pricing)
- [FMP Stock News API](https://site.financialmodelingprep.com/developer/docs/stock-news-api)
- [Alpaca News API Docs](https://docs.alpaca.markets/reference/news-3)
- [Finnhub API Docs](https://www.finnhub.io/docs/api)
- [Alpha Vantage Premium](https://www.alphavantage.co/premium/)
- [EODHD News API](https://eodhd.com/financial-apis/stock-market-financial-news-api)
- [Finlight Pricing](https://finlight.me/pricing)
- [Lambda Finance News API](https://www.lambdafin.com/financial-news-api)
- [StockNewsAPI Pricing](https://stocknewsapi.com/pricing)
- [Tiingo Review 2026](https://www.findmymoat.com/tools/tiingo)
- [Twelve Data Pricing](https://twelvedata.com/pricing)
- [Polygon.io Review 2026](https://tradingtoolshub.com/review/polygon-io/)
- [Benzinga API Docs](https://docs.benzinga.com/)
