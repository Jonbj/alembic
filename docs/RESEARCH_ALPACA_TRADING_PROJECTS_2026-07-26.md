# Ricerca: progetti e documentazione su sistemi di trading basati su Alpaca

**Data:** 2026-07-26
**Scopo:** confrontare strategie e connettori usati da altri sistemi di trading su Alpaca con il progetto Alembic, per identificare gap e spunti riutilizzabili (in particolare per il pivot event-driven e l'uso off-hours).

---

## 1. Progetti open-source su Alpaca

### 1.1 davidalv2/algo-trading-bot
- **Stack:** Python, framework Lumibot, Alpaca API
- **Strategie:**
  - Buy & Hold (baseline)
  - Momentum — ranking per rendimento 20gg su universo (AAPL, GOOGL, MSFT, AMZN, TSLA), alloca ai top performer
  - Trend Following — crossover SMA 9 vs 21gg su GLD
  - Statistical Arbitrage / Pairs Trading — mean reversion su z-score di coppie correlate
- **Modi:** backtest (dati Yahoo Finance) o paper live via Alpaca
- **Profilo:** didattico, codice pulito per strategie quant classiche

### 1.2 rgomezjnr/pacabot
- **Tipo:** CLI fire-and-forget (MIT)
- **Strategie:**
  - Cross-Sectional Momentum — ranking trailing-return con lookback configurabile (21–252gg), long-only o long/short
  - Mean Reversion — RSI / Bollinger / Z-score
  - Pairs Trading — hedge ratio OLS, z-score entry/exit, stop-loss sul breakdown dello spread
- **Feature:** config TOML, risk management integrato (margin cap, stop loss, daily loss limit), backtest con equity curve, universi multipli (S&P 500, Nasdaq 100, Russell 1000)
- **Profilo:** CLI production-style con risk management solido

### 1.3 gr8monk3ys/trading-bot
- **Stack:** Python async, Alpaca, Docker
- **Strategie:**
  - Momentum — RSI/MACD/ADX con trailing stop
  - Mean Reversion
  - Adaptive Coordinator — switch strategia in base al regime di mercato
- **Feature:** backtest con slippage/spread realistici, risk manager (VaR, correlazione, position sizing), circuit breaker
- **Autovalutazione onesta:** underperform vs SPY buy&hold ma migliore drawdown control (−7% maxDD vs −33% passivo)
- **Profilo:** regime-adaptive

### 1.4 costajohnt/alpaca-trader  ⭐ gemello di Alembic
- **Strategie:** mean reversion, **AI sentiment** (OpenRouter/Claude su Alpaca News API), **segnali insider trading (Finnhub)**, momentum, fundamental analysis (DCF)
- **Feature:** conviction-based position sizing, **sector exposure guards**, **market regime detection**, **walk-forward validation**, **shadow experiments**, Flask dashboard, **strategy-improvement agent loop** (Claude)
- **Test:** 1.163 su 56 file; Python 3.14+
- **Safety rails hardcoded:** min 50 trade per cambio parametro (30 per filtri), max 2 deploy/settimana, 14gg cooling per file, 5% max position size, max-loss stop non disattivabile
- **Stato (mag 2026):** review manuale; cron autonomo settimanale disattivato. L'operatore genera un brief via `scripts/agent_brief.py` e lo incolla in una sessione Claude Code locale.
- **Blog architetturale:** [jcosta.tech — Building a Self-Improving Trading System With AI](https://jcosta.tech/writing/building-a-self-improving-trading-system-with-ai/)
  - **Lezione chiave:** 86 decisioni agent loggate in 3 mesi → **0 deploy reali**. Motivo del passaggio ad auto→manuale. Conferma la disciplina shadow-first.

### 1.5 stuagano/Alpaca-StochRSI-EMA-Trading-Bot
- **Indicatori:** StochRSI, Stochastic, EMA
- **Feature:** stop loss, trailing stop, position sizing, backtest, Flask dashboard, Docker
- **Profilo:** technical-indicator focused con dashboard

### 1.6 Cikle/Alpatrader
- **Logica:** opzioni trading **inverso** basato su news sentiment + insider trades + congressional trading
- **Fonti dati:**
  - OpenInsider (insider, focus CEO/CFO)
  - Senate Stock Watcher (Congress)
  - NewsAPI / GNews (headline)
  - Finnhub (sentiment scoring)
  - SQLite cache
- **Gerarchia segnale:** Strong News + Insider/Congress = 2x posizione, Congress-only = 1x, Insider-only = 0.5x
- **Backtest:** eventi storici (collasso SVB, insider sale Meta)

### 1.7 enving/TradeAgent
- **Stack:** AI-powered, Alpaca paper, Supabase persistence
- **Fonti news:** Yahoo Finance, Finnhub, Alpha Vantage, NewsAPI
- **Sentiment:** Claude 3.5 Sonnet analizza 90+ articoli per ticker
- **Feature:** ottimizzazione adattiva (grid search su performance 30gg), risk management (Kelly Criterion, circuit breaker, correlazione)

### 1.8 RajendharAre/SentXStock
- **Pipeline AI a 3 tier:** FinBERT → Gemini → VADER
- **Fonti:** Finnhub + NewsAPI (80.000+ fonti), Reddit (r/wallstreetbets, r/stocks, r/investing)
- **Feature:** risk engine dinamico su sentiment, dashboard React

### 1.9 quangkhaidataka/LLM_Alpha  🔥 più rilevante per Alembic
- **Strategia:** market-neutral long/short su S&P 100, combina **SEC EDGAR 8-K** + **GDELT 2.0**
- **LLM:** Claude Haiku 4.5 estrae feature strutturate: polarity, magnitude, event type, tense, specificity, novelty
- **Segnale:** *sentiment acceleration* = short MA − long MA del polarity LLM-scored, rank-weighted, **GICS settore-neutralizzato**
- **Walk-forward:** purged 5gg + embargo 5gg (stile López de Prado)
- **Risultati:** OOS Sharpe +0.78, maxDD 3.3%, 12 trimestri (Q1 2022–Q4 2024); netto di 5 bps round-trip; α t-stat +1.35 (sotto soglia 1.96)
- **Pipeline:** `src/alpha/`, `src/signal/`, `src/backtest/`, pytest 66/66 pass
- **Rilevanza:** blueprint quasi esatto del pivot event-driven di Alembic (filings + GDELT + LLM feature extraction)

### 1.10 E9Technologies/ED-ALPHA
- **Tipo:** benchmark aperto per predizione eventi aziendali futuri, linkando EDGAR 8-K + GDELT
- **LLM:** OpenRouter per rankare aziende per probabilità di filing item rilevanti (M&A, spinoff, bancarotta)
- **Stack:** Docker Compose (Postgres + FastAPI + Next.js + batch runner)
- **Metriche:** recall@k / precision@k

### 1.11 zrxbeijing/NewsTrader
- **Fonti:** GDELT (events, GKG, mentions), CommonCrawl news, scraping web
- **Estrazione simboli:** BERT NER + word embeddings dai titoli → link a ticker
- **Feature:** feature extraction + portfolio backtest (MIT)

### 1.12 ashotm1/small-cap-signal
- **Tipo:** event-driven price prediction su small-cap
- **Fonti:** press release da newswire (GlobeNewswire, PRNewswire, Business Wire, ACCESS Newswire), SEC EDGAR 8-K/EX-99 come secondaria
- **LLM:** Anthropic Batch API per feature strutturate
- **Modello:** XGBoost quantile regression su log-return, walk-forward

### 1.13 renee-jia/trading-bot (103⭐)
- multi-agent macro trading bot con sentiment + regime detection + esecuzione Alpaca

### 1.14 rmbell09-lang/tradesight (152⭐)
- self-hosted AI trading strategy lab con walk-forward validation + regime detection

---

## 2. Articoli / tutorial / documentazione

### 2.1 Predict & Profit — Finnhub Sentiment Integration
[Link](https://predictandprofit.io/blog/finnhub-sentiment-age-weighted-scoring-alpaca-python)
- Integrazione endpoint `/news-sentiment` di Finnhub con bot Alpaca
- **Re-centering** score Finnhub 0–1 → scala −1/+1
- **Age-weighting** con decadimento esponenziale (riduce peso news stale)
- **Volatility gate** su barre storiche Alpaca (evita periodi illiquidi)
- TTL cache 3 min per rispettare rate limit 60/min
- Pipeline < 200ms per ticker
- 🔗 Alembic ha già age-weighting/decay; il volatility gate è un pattern utile

### 2.2 Alpaca Learn — Sentiment Analysis con News API + Transformers
[Link](https://alpaca.markets/learn/sentiment-analysis-with-news-api-and-transformers)
- **Alpaca News API**: 6+ anni storico + streaming websocket live
- Sentiment via HuggingFace Transformers (FinBERT)
- Trading: positive → long, negative → short con confidence threshold
- 🔗 conferma che Alpaca News API è lo standard nativo (Alembic già lo usa)

### 2.3 mimic-signal (PyPI v0.1.0)
[Link](https://pypi.org/project/mimic-signal/)
- Libreria event-detection real-time che osserva GDELT, SEC EDGAR 8-K, FRED, NewsAPI, AIS, options flow, Twitter
- Emette `Signal` strutturati con severity/confidence
- **Weak Signal System** con 10 pattern precursori pre-costruiti (es. "GDELT tone decline → crisi geopolitica", "options put spike → evento aziendale")
- Python ≥3.10, Apache-2.0
- 🔗 riusabile come layer ingestion/event-detection; i "precursori deboli" sono un'idea di feature aggiuntiva

---

## 3. Pattern architetturale comune

```
fetch news → score sentiment (FinBERT/VADER/LLM)
          → age-weight & normalize
          → combina con filtri tecnici/volatilità
          → esecuzione via Alpaca paper trading API
```
- **Caching** (SQLite o TTL dict) per gestire rate limit free-tier
- **GDELT** non è diffusissimo; la maggioranza usa Finnhub + NewsAPI + Alpaca News API nativa
- **Risk management** (stop loss, position sizing, daily loss limit) presente ovunque
- **Python** dominante; **paper trading** come default di test

---

## 4. Confronto con Alembic

### 4.1 Connettori

| Fonte dati | Alembic oggi | Altri progetti | Gap / nota |
|---|---|---|---|
| News free-text | GDELT GKG/DOC, Alpaca News, MarketAux, RSS, Finnhub (shelved) | Finnhub standard de-facto ovunque | Finnhub già implementato, da riattivare (`FINNHUB_INGESTION_ENABLED`) |
| Insider / Congresso | ❌ | OpenInsider + Senate Stock Watcher (Alpatrader) | segnale ortogonale, sleeve diversificante |
| Social | ❌ | Reddit (SentXStock) | |
| Fundamentals / filings | SEC EDGAR (shelved) | EDGAR 8-K centrale in LLM_Alpha, ED-ALPHA, small-cap-signal | centrale per pivot event-driven |
| Macro | FRED (verifica) | FRED in mimic-signal | |
| Prezzo/storico | Alpaca historical | Alpaca ovunque; Yahoo per backtest | OK |

**Takeaway:** lo stack news + resolver deterministico di Alembic è già sopra la media (poco comune e robusto). Gap: Finnhub (già in codice) e insider/congressional trades (nuovo).

### 4.2 Strategie

| Strategia | Presente in | Alembic |
|---|---|---|
| Momentum cross-sectional | davidalv2, pacabot | ≈ S1 |
| Mean reversion (RSI/Bollinger/Z-score) | pacabot, gr8monk3ys, stuagano | solo come fallback deterministico |
| Pairs trading (OLS hedge, z-score spread) | davidalv2, pacabot | ❌ assente — sleeve diversificante a basso costo |
| Regime-adaptive (selector) | gr8monk3ys Adaptive Coordinator | regime_mult come scalare, non selector |
| Sentiment acceleration + settore-neutral + walk-forward purged | LLM_Alpha | 🔥 blueprint per pivot event-driven |
| Event-driven 8-K + news, market-neutral | LLM_Alpha, ED-ALPHA, small-cap-signal | coincide con roadmap dati/alpha |

### 4.3 Governance / loop agente
- costajohnt/alpaca-trader: shadow-first + walk-forward + safety rails + cooldown → **conferma la direzione di Alembic** (F8, regime_scale). Il suo fallimento del cron autonomo (0 deploy in 3 mesi) argomenta per tenere l'operatore in-loop.

---

## 5. Priorità di studio per Alembic

1. **LLM_Alpha** — blueprint del pivot event-driven: feature strutturate LLM (polarity/magnitude/event-type/tense/specificity/novelty) + sentiment acceleration + settore-neutral + walk-forward purged/embargo. Confrontare con il sentiment schema attuale di Alembic.
2. **costajohnt/alpaca-trader** + blog — governance del loop agent→shadow→walk-forward→deploy e safety rails.
3. **mimic-signal** — layer ingestion/event-detection riusabile + weak-signal precursors come feature aggiuntive.

---

## Fonti

- https://github.com/davidalv2/algo-trading-bot
- https://github.com/rgomezjnr/pacabot
- https://github.com/gr8monk3ys/trading-bot
- https://github.com/costajohnt/alpaca-trader
- https://jcosta.tech/writing/building-a-self-improving-trading-system-with-ai/
- https://github.com/stuagano/Alpaca-StochRSI-EMA-Trading-Bot
- https://github.com/Cikle/Alpatrader
- https://github.com/enving/TradeAgent
- https://github.com/RajendharAre/SentXStock
- https://predictandprofit.io/blog/finnhub-sentiment-age-weighted-scoring-alpaca-python
- https://alpaca.markets/learn/sentiment-analysis-with-news-api-and-transformers
- https://github.com/quangkhaidataka/LLM_Alpha
- https://pypi.org/project/mimic-signal/
- https://github.com/E9Technologies/ED-ALPHA
- https://github.com/zrxbeijing/NewsTrader
- https://github.com/ashotm1/ai-market-signal
- https://github.com/renee-jia/trading-bot
- https://github.com/rmbell09-lang/tradesight