# Alembic — Forensic Report Operativo 2026-06-17

**Ruolo**: Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer
**Analisi**: read-only — nessun file modificato, nessun commit, nessun ordine eseguito.
**Timezone operativo**: UTC (Celery beat UTC, DB timezone `timestamp with time zone`)
**NYSE market hours 2026-06-17**: 13:30–20:00 UTC (9:30am–4:00pm EDT, martedì, non festivo)

---

## 1. EXECUTIVE SUMMARY

Il sistema ha operato il 2026-06-17 dalle 14:07 UTC alle 19:52 UTC (market hours), eseguendo 24 cicli di portfolio ogni 15 minuti con 59 BUY e 16 SELL su 12 simboli. **Tutti i trade sono paper** (S4 capped 10%). La pipeline tecnica ha girato: news ingest → sentiment → portfolio cycle → ordini → fill.

**Tre anomalie gravi si sono materializzate**:

1. **DATI STALE (CRITICO)**: Tutta la news ingested il 2026-06-17 ha `fetched_at = 2026-06-15` (2 giorni vecchia). Il sistema ha tradato interamente su notizie del 15 giugno in un giorno di mercato del 17 giugno.
2. **PYRAMIDING INCONTROLLATO (CRITICO)**: 15 segnali hanno generato BUY multipli (40/59 BUY = 68% ridondanti). INFY ha ricevuto 7 BUY sullo stesso segnale stale, accumulando una perdita paper di –$172.
3. **REGIME MULTIPLIER INATTIVO (HIGH)**: `regime_mult=1.0` per tutti i 59 trade — il regime detector è girato (07:00 UTC) ma il multiplier non è stato applicato all'esecuzione.

**PnL paper realizzato**: –$103.57 netti su $32.510 notionale totale deployato.
**Funzionalità core**: rispettata (LLM mai nel hot path, score formula corretta, audit trail completo). Il sistema è **funzionalmente corretto nella struttura** ma con difetti operativi gravi nell'idempotenza e nella freschezza dei dati.

---

## 2. VERDICT

> **ANOMALIE SIGNIFICATIVE — non affidabile per capitale reale**

| Asse | Stato |
|------|-------|
| Pipeline end-to-end | ✅ Funziona (news→LLM→signal→order→fill) |
| Freschezza dati | ❌ Stale di 2 giorni (GDELT+Alpaca da 15-giu) |
| Idempotenza segnali | ❌ 68% BUY ridondanti (stesso segnale, cicli diversi) |
| Regime de-risking | ❌ Inattivo (regime_mult hardcodato 1.0) |
| Ticker extraction | 🟡 1 misattribuzione GS/MDT (non eseguita) |
| Risk reports | 🟡 Nessun risk report il 2026-06-17 |
| Performance metrics | 🟡 Nessun IC/ICIR calcolato il 2026-06-17 |
| Paper vs live | ✅ Confermato paper (S4 10%) |
| Stop-loss | ❌ Nessuno attivo (confermato da revisione precedente) |

---

## 3. TIMELINE 2026-06-17

| Timestamp UTC | Componente | Evento | Stato | Fonte |
|---|---|---|---|---|
| 07:00 | `regime.detect_regime` | Regime detector schedulato | Esito non verificabile (nessuna `regime_history` table) | `celery_app.py:103` |
| 14:00 | `run_news_ingestion_worker` | Ingest GDELT/Alpaca/MarketAux: 51 articoli totali | ⚠️ Tutti `fetched_at = 2026-06-15` | `news_log` DB |
| 14:00 | `run_sentiment_worker` | Sentiment worker avviato | OK | `celery_app.py:63` |
| 14:02–14:46 | `sentiment_signals` | 17 segnali generati per 17 ticker (prima ora) | OK — 103 risposte kimi, 86 qwen, 22 FinBERT fallback | `sentiment_signals` DB |
| 14:07 | `portfolio_cycle #42` | 8 ordini (4 BUY: GOOGL/LLY/ORCL/INFY, 4 SELL: INTC/IWM/META/XLK) | ⚠️ BUY su news 2gg stale | `portfolio_cycles` DB |
| 14:22 | `portfolio_cycle #43` | 4 BUY (GOOGL/LLY/ORCL/MU) | ⚠️ Stessi segnali, nuovi BUY su posizioni già aperte | `portfolio_cycles` DB |
| 14:37 | `portfolio_cycle #44` | 4 BUY + 1 SELL INFY (rebalance a 0%) | ⚠️ INFY venduta, poi ri-comprata al ciclo successivo | `portfolio_cycles` DB |
| 14:52 | `portfolio_cycle #45` | 4 BUY (INFY ri-comprata con stesso segnale stale) | ❌ Idempotenza violata | `portfolio_cycles` DB |
| 15:07–19:52 | `portfolio_cycle #46–#68` | Cicli ogni 15 min, continua accumulazione MU/TSM/AZN/AMZN | ⚠️ Pyramiding su segnali stale | `portfolio_cycles` DB |
| 15:30–21:00 | `sentiment_signals` | Altri 109 segnali generati (totale 126/giorno) | OK — nessun timeout/refusal LLM | `sentiment_signals` DB |
| 19:52 | Ultimo ciclo | BUY AMZN/MU/TSM | OK — entro market hours (19:52 < 20:00) | `portfolio_cycles` DB |
| 21:30 | `run_daily_report` | Schedulato ma esito non verificabile (log non disponibili) | Non verificabile | `celery_app.py:77` |
| 22:30 | `risk-monitor` | Risk report schedulato — ZERO record per 2026-06-17 in `risk_reports` | ⚠️ Non eseguito o fallito silenziosamente | `risk_reports` DB |

---

## 4. TABELLA NEWS INGEST

| Fonte | Articoli (created 17-giu) | Ticker distinti | fetched_at range | Giorni di staleness | Note |
|---|---|---|---|---|---|
| `gdelt_gkg` | 36 | 13 | 2026-06-15 18:45–19:30 UTC | **2 giorni** | File GDELT da domenica sera |
| `alpaca_benzinga` | 14 | 14 | 2026-06-15 16:34–19:16 UTC | **2 giorni** | Articoli lunedì 15-giu su Oracle, Alphabet, Boeing |
| `marketaux` | 1 | 1 (NVDA) | 2026-06-15 18:35 UTC | **2 giorni** | HBM Micron article |
| **TOTALE** | **51** | **~20** | **tutto 15-giu** | **2 giorni** | |

**Anomalia critica**: Il sistema ha ingerito e tradato su news del 15 giugno (domenica). Le price action citate (Oracle surge, US-Iran deal, Boeing) erano già pienamente scontate dal mercato prima dell'apertura del 17 giugno.

Contesto generale DB: tutti i 311 record in `news_log` hanno `fetched_at` nel range `2026-06-15 13:24–21:15 UTC`, confermando che nessuna news successiva al 15-giu è mai entrata nel sistema.

---

## 5. TABELLA PERFORMANCE MODELLI LLM

| Modello | Segnali | Fallback | Avg Score | Avg Confidence | Avg Ensemble Std | Min/Max Score |
|---|---|---|---|---|---|---|
| `ensemble:kimi-k2.6+qwen3.5` | 77 | 0 | +0.1736 | 0.7319 | 0.1410 | –0.683 / +0.727 |
| `ensemble:kimi-k2.6:cloud` | 24 | 0 | +0.1251 | 0.6546 | 0.000 | –0.300 / +0.765 |
| `finbert` (fallback) | 22 | 22 (100%) | +0.037 | 0.341 | 0.000 | –0.007 / +0.191 |
| `ensemble:qwen3.5:cloud` | 3 | 0 | +0.288 | 0.700 | 0.000 | 0.000 / +0.525 |
| **Raw responses kimi** | 103 | — | +0.137 | 0.673 | — | — |
| **Raw responses qwen** | 86 | — | +0.269 | 0.739 | — | — |

- FinBERT ha fatto **fallback 22/22 volte** — sempre quando ensemble Std era alta o Ollama restituiva un solo modello.
- Ensemble Std medio 0.141 — inferiore alla soglia 0.30; guardrail correttamente attivato solo dove necessario.
- **Nessun errore/timeout LLM nel giorno**: 0 ineligible responses.

---

## 6. TABELLA SEGNALI FINALI PER TICKER

| Ticker | Segnali | Avg Score | Fallback | Score > 0.3 | Score < −0.3 | Eseguito |
|---|---|---|---|---|---|---|
| MU | 6 | +0.287 | 1 | 4 | 0 | ✅ 9 BUY |
| INFY | 3* | +0.325 | 3 | 1 | 0 | ✅ 7 BUY (segnali da 16-giu!) |
| TSM | 2 | +0.162 | 1 | 1 | 0 | ✅ 6 BUY |
| GOOGL | 4 | +0.124 | 2 | 1 | 0 | ✅ 5 BUY |
| GS | 4 | +0.147 | 0 | 1 | 1 | ✅ 5 BUY (segnale −0.549 non usato) |
| ORCL | 3 | +0.272 | 0 | 2 | 0 | ✅ 5 BUY |
| AMZN | 5 | +0.137 | 0 | 1 | 0 | ✅ 5 BUY |
| LLY | 3 | +0.122 | 1 | 1 | 0 | ✅ 5 BUY |
| META | 4 | +0.233 | 0 | 2 | 0 | ✅ 5 BUY |
| AZN | 1 | +0.676 | 0 | 1 | 0 | ✅ 3 BUY |
| AMD | 4 | +0.241 | 0 | 2 | 0 | ✅ 2 BUY |
| AVGO | 1 | +0.186 | 0 | 0 | 0 | ✅ 2 BUY |
| CVX | 2 | −0.458 | 0 | 0 | 2 | ❌ Non eseguito |
| XOM | 1 | −0.596 | 0 | 0 | 1 | ❌ Non eseguito |
| XLE | 1 | −0.683 | 0 | 0 | 1 | ❌ Non eseguito |

\* INFY: i 3 segnali dalla tabella sono da 2026-06-16; il segnale `id=180` (qwen3.5, +0.423) era già stale quando è stato usato il 17 giugno.

---

## 7. TABELLA ORDINI GENERATI/ESEGUITI

| Ciclo | Timestamp UTC | BUY | SELL | Ticker principali | Note |
|---|---|---|---|---|---|
| #42 | 14:07 | 4 | 4 | BUY: GOOGL/LLY/ORCL/INFY; SELL: INTC/IWM/META/XLK | Prima apertura sessione |
| #43 | 14:22 | 4 | 0 | BUY: GOOGL/LLY/ORCL/MU | Accumulo su posizioni già aperte |
| #44 | 14:37 | 4 | 1 | BUY: GOOGL/LLY/ORCL/MU; SELL INFY (rebalance) | INFY rebalanced out |
| #45 | 14:52 | 4 | 0 | BUY: GOOGL/ORCL/MU/**INFY** | ❌ INFY ri-comprata, stesso segnale stale |
| #46 | 15:07 | 5 | 1 | BUY: GOOGL/ORCL/MU/INFY/LLY; SELL NVDA | ❌ INFY 3ª volta |
| #47–#53 | 15:22–17:22 | vari | vari | AMD/TSM/GS/AMZN/META entrano | INFY accumulata x4 nel range |
| #54–#60 | 17:37–19:07 | vari | vari | MU/AVGO/GS sell; META sell; AMZN/GS re-buy | Turnover elevato |
| #61–#68 | 19:22–19:52 | vari | vari | AMZN/MU/TSM/AZN | Ultimi cicli pre-close |

**Totale**: 59 BUY + 16 SELL = 75 ordini paper su 12 ticker.
Tutti con `order_type='MARKET'` e `strategy_id='merged'`. Nessun limit order.
Strategies_run = `["S1", "S4"]` per ogni ciclo.

---

## 8. TABELLA PNL/RENDIMENTO (PAPER)

| Ticker | Trade | Gross PnL | Net PnL | Notionale | Note |
|---|---|---|---|---|---|
| INFY | 7 | –$164.58 | **–$171.88** | $3.549 | ❌ Caduta $12→$11.03 (−8.1%); cost_bps ~20 (penny stock) |
| AZN | 3 | –$39.07 | **–$43.27** | $2.057 | ❌ Aperta 17-giu, chiusa 18-giu |
| AVGO | 2 | –$27.12 | **–$28.14** | $1.860 | ❌ |
| META | 5 | –$26.99 | **–$27.43** | $2.204 | ❌ Rapida inversione intraday |
| GS | 5 | –$25.09 | **–$27.23** | $3.928 | ❌ Buy-sell-buy in stesso giorno |
| GOOGL | 5 | –$3.73 | **–$4.16** | $2.200 | |
| LLY | 5 | –$2.69 | **–$3.88** | $2.185 | |
| ORCL | 5 | +$2.37 | **+$1.18** | $2.190 | ✅ News Oracle genuinamente positiva |
| AMD | 2 | +$4.29 | **+$3.28** | $1.855 | ✅ |
| AMZN | 5 | +$8.26 | **+$7.49** | $3.916 | ✅ |
| TSM | 6 | +$63.07 | **+$61.86** | $2.215 | ✅ Maggiore vincitore |
| MU | 9 | +$130.97 | **+$128.60** | $4.346 | ✅ Maggiore vincitore (AI/HBM) |
| **TOTALE** | **59** | **–$80.32** | **–$103.57** | **$32.510** | |

**Rendimento giornaliero**: –$103.57 / $32.510 ≈ **–0.32% sul notionale** (paper).
**Slippage**: stimato per singolo trade in `slippage_est` (non aggregato qui).
**Commissioni**: $0 Alpaca paper; solo SEC/FINRA fee modellate nei `cost_bps`.

---

## 9. ANALISI CORRETTEZZA FUNZIONALE BUY/SELL

| Check | Stato | Evidenza |
|---|---|---|
| BUY solo su segnale positivo | ✅ | Tutti BUY con score > 0; CVX/XOM/XLE negativi non eseguiti |
| SELL su rebalance / signal flip | ✅ | `reason="Portfolio rebalance: weight 0.0%"` corretto |
| Stop-loss rispettato | ❌ N/A | Stop-loss inattivo (bracket off, `execution.py` morto) |
| Signal flip rispettato | ⚠️ Parziale | INFY: SELL poi re-BUY con stesso segnale (nessun flip reale) |
| Max holding days | ✅ | Sistema portfolio-based, la maggior parte dei trade dura ore |
| Rebalance band | ✅ | Portfolio combiner rialloca ogni 15 min |
| Ordini duplicati | ❌ **CRITICO** | 15 segnali → BUY multipli (68% ridondanti) |
| Ordini contrari stesso intervallo | ⚠️ | INFY: SELL @ 14:37, BUY @ 14:52 (stesso segnale) |
| Ticker non consentiti | ✅ | Tutti nel watchlist |
| Ordini fuori orario | ✅ | Primo 14:07, ultimo 19:52 (entro 14:00–20:00 UTC) |
| Trade su dati stale | ❌ **CRITICO** | News da 2026-06-15 usata il 17 giugno |
| Trade su LLM output non valido | ✅ | 0 ineligible responses |
| Circuit breaker attivo | ✅ | Nessun halt attivato |
| Paper/live mode coerente | ✅ | Confermato paper S4 |
| Idempotenza retry Celery | ❌ **CRITICO** | Stesso segnale → BUY multipli |
| Reconciliation ordini/fill/posizioni | ✅ | `ON CONFLICT DO NOTHING`; `reconcile_trade_fills` attivo |

---

## 10. ANOMALIE TROVATE

---

### [DAY-001] Tutti i dati news da 2026-06-15 (2 giorni stale)

- **Tipo**: Anomalia critica dei dati
- **Area**: News / Data
- **Evidenza**:
  - `SELECT min(fetched_at), max(fetched_at) FROM news_log` → `2026-06-15 13:24` / `2026-06-15 21:15` (tutti 311 record)
  - 2026-06-17: 51 articoli, `fetched_at` range `18:45–19:30 UTC del 15-giu`
  - Pattern: progressione sequenziale 15-min di finestre GDELT GKG del 15-giu su giorni consecutivi
- **Descrizione**: Il GDELT GKG connector (`fetch()`) scarica il file puntato da `lastupdate.txt`. Il campo `fetched_at` in DB è l'article timestamp del file GDELT (`_COL_DATE`), non il tempo di fetch nostro. Tutti i file scaricati hanno timestamp dal 15 giugno, con progressione sequenziale su giorni successivi. Causa probabile: outage GDELT (lastupdate.txt bloccato su file del 15-giu) oppure backfill sistematico. Il `gkg_url` non è loggato → causa non determinabile a posteriori.
- **Impatto**: Tutti i segnali LLM del 17-giu costruiti su news del 15-giu. Le price action citate (Oracle surge, US-Iran deal) erano già scontate 2 giorni prima. IC atteso ≈ 0 sul giorno.
- **Severità**: Critical
- **Confidenza**: High
- **Azione consigliata**: (1) Verificare `lastupdate.txt` URL nei giorni successivi. (2) Aggiungere freshness gate pre-trade: se `max(fetched_at) < now() – 6h → halt S4 + alert`. (3) Loggare `gkg_url` e date range in ogni invocazione.
- **Test/monitor**: Alert Telegram/Grafana se `max(fetched_at) < now() – 4h` durante market hours.

---

### [DAY-002] Pyramiding: 68% dei BUY ridondanti (stesso segnale, cicli multipli)

- **Tipo**: Bug critico — Idempotenza
- **Area**: Orders / Execution / Signal
- **Evidenza**:
  - `execution_decisions`: 15 `signal_id` con BUY count > 1 (range 2–7)
  - INFY signal_id=180: 7 BUY distinti, periodi 14:07–18:07 UTC
  - TSM signal_id=210: 6 BUY; MU signal_id=243: 5 BUY
  - `portfolio_scheduler.py:401` fetch solo `get_all_positions()`, no `get_orders(OPEN)`
- **Descrizione**: Il portfolio scheduler valuta il delta tra pesi target e posizioni Alpaca. Se un ordine è pending (non ancora settled), non appare nelle posizioni → il ciclo successivo ri-calcola un BUY. Stesso problema con segnali Redis non consumati dopo prima esecuzione.
- **Impatto**: INFY accumulata 7×, perdita –$172 paper. Esposizione reale >> allocazione intesa (2% per segnale).
- **Severità**: Critical
- **Confidenza**: High
- **Azione consigliata**: Ticket T-IDEMPOTENT-BUY: `get_orders(status=OPEN)` prima del sizing delta; idempotency token Redis per segnale (TTL EOD).
- **Test/monitor**: Assert `signal_id → max 1 BUY per ticker per sessione`.

---

### [DAY-003] INFY: segnale da 2026-06-16 usato il 17-giu per 7 BUY

- **Tipo**: Anomalia — Segnale stale + Idempotenza combinati
- **Area**: Signal / LLM / Orders
- **Evidenza**:
  - `execution_decisions.signal_id=180` → `sentiment_signals.generated_at = 2026-06-16 21:52 UTC`
  - News sorgente: "Sensex surges… Iran-US peace deal" da 2026-06-15 18:30 UTC
  - 7 BUY separati, tutti con `reason="S4 news-driven: sentiment +0.423 (ensemble:qwen3.5:cloud)"`
- **Descrizione**: Il segnale INFY 180 era stato generato il 16-giu sera. Il 17-giu il sentiment worker non ha trovato nuovi articoli INFY (zero news INFY nella `news_log` del 17-giu), quindi Redis conteneva ancora il segnale stale che il portfolio scheduler ha riletto in ogni ciclo.
- **Impatto**: 7 BUY su news 2+ giorni vecchia; INFY scesa da $12 a $11.03 (–8.1%), perdita –$172 paper sulla posizione pyramidata.
- **Severità**: Critical
- **Confidenza**: High
- **Azione consigliata**: TTL Redis per segnali (max 4h o fine sessione). Check `signal.generated_at < now() – 4h → skip BUY`.

---

### [DAY-004] Ticker misattribution: "BofA lowers PT on MDT" → tagged GS

- **Tipo**: Bug — Ticker extraction
- **Area**: News / Data Quality
- **Evidenza**:
  - `news_log id=188`: title="BofA Lowers PT on Medtronic (MDT) Stock", ticker="GS", source=gdelt_gkg
  - `sentiment_signals id=188`: GS score=–0.549 (forte negativo)
  - L'articolo riguarda MDT (Medtronic), non GS (Goldman Sachs)
- **Descrizione**: GDELT `V2.1Organizations` per quell'articolo conteneva "Goldman Sachs" (menzionato come broker nei commenti). Il `TickerExtractor` l'ha mappato a GS. Misattribuzione chiara dal titolo.
- **Impatto**: Fortunatamente il segnale GS–0.549 **non ha guidato nessun trade** (segnali positivi successivi hanno dominato). Se fosse stato l'unico segnale GS, avrebbe generato un SELL inappropriato.
- **Severità**: High
- **Confidenza**: High
- **Azione consigliata**: Cross-validation ticker vs headline: se il ticker non appare nel titolo come whole-word, flaggare "cross-reference risk". Preferire NER su testo rispetto al solo database org→ticker GDELT.

---

### [DAY-005] Regime multiplier hardcodato 1.0 — de-risking assente

- **Tipo**: Bug — Risk control inattivo
- **Area**: Risk / Execution
- **Evidenza**:
  - Tutti i 59 trade in `trades`: `regime_mult=1.0`
  - `portfolio_scheduler.py:543,626`: `regime_mult=1.0` hardcoded
  - Regime detector schedulato 07:00 UTC ma nessuna tabella di output consultabile
- **Descrizione**: Il regime detector gira quotidianamente ma il suo output non viene letto dal portfolio scheduler (F-01 nella review del 17-giu).
- **Impatto**: In regime bear/high_vol il sistema mantiene sizing pieno. In questo caso il mercato era stabile, quindi l'impatto diretto è limitato. Ma il gap risk control è sistematico.
- **Severità**: High
- **Confidenza**: High
- **Azione consigliata**: Ticket T-REGIME-WIRE (già aperto). Wire immediato, moltiplicatori pre-specificati (no ottimizzazione su drawdown storico).

---

### [DAY-006] Nessun risk report prodotto per 2026-06-17

- **Tipo**: Anomalia operativa
- **Area**: Risk / Monitoring
- **Evidenza**:
  - `risk_reports` table: zero record con `timestamp` il 17-giu
  - Risk monitor schedulato a 22:30 UTC (corretto — post market)
  - Unico report DB è id=4, timestamp=2026-06-18 08:13 (dopo container restart)
- **Descrizione**: Il risk monitor del 17-giu (22:30 UTC) non ha prodotto output. Causa probabile: container crashato prima del 18-giu 08:11 (log non disponibili per il 17-giu). Il report del 18-giu mostra `total_exposure=100%` e `HHI=1.0` — alert che sarebbe stato emesso anche il 17-giu.
- **Impatto**: Nessun alert su esposizione totale 100% il 17-giu.
- **Severità**: Medium
- **Confidenza**: Medium (causa root non definitiva — log del 17-giu non accessibili)
- **Azione consigliata**: Healthcheck container worker; alert se `risk_reports` mancante da >24h.

---

### [DAY-007] Redis MISCONF (RDB persistence) — crash worker il 18-giu 09:02 UTC

- **Tipo**: Incidente operativo (colaterale al 17-giu)
- **Area**: Ops / Redis
- **Evidenza**:
  - `alembic-worker-1` log: `[2026-06-18 09:02:35] CRITICAL Unrecoverable error: ResponseError("MISCONF Redis is configured to save RDB snapshots, but it's currently unable to persist to disk...")`
  - Worker riconnesso a 09:02:43 UTC
- **Descrizione**: Redis non riesce a scrivere snapshot RDB (probabile disco pieno o permessi). Il worker perde la connessione e si riconnette dopo ~8s. Se Redis aveva problemi anche durante il 17-giu, il Deduplicator in-memory potrebbe aver perso stato → articoli già visti ri-accodati → segnali duplicati (potenziale concausa di DAY-002).
- **Impatto**: Potenziale causa del pyramiding; mancata persistenza dei segnali Redis.
- **Severità**: High
- **Confidenza**: Medium
- **Azione consigliata**: `appendonly yes` in Redis; resource limit disk; monitor disk usage. Ticket T-DOCKER-HARDENING (già aperto).

---

### [DAY-008] INFY con cost_bps ~20× (vs ~5 degli altri ticker)

- **Tipo**: Anomalia — Costi di transazione anomali
- **Area**: PnL / Costi
- **Evidenza**:
  - INFY trades: `cost_bps` = 20.04–20.26 su tutti e 7 i trade
  - Altri ticker: `cost_bps` = 1.57–5.26
  - INFY prezzo $11–12 (spread relativo elevato per ADR low-price)
- **Descrizione**: Il `RealisticCostModel` applica correttamente un costo in bps maggiore per titoli low-price. Tuttavia l'assenza di un filtro costo-aware ha consentito 7 BUY su INFY, accumulando ~$70 solo di costi su una posizione con drawdown di $100+.
- **Impatto**: Cost drag significativo su INFY.
- **Severità**: Medium
- **Confidenza**: High
- **Azione consigliata**: Filtro pre-trade: `if cost_bps > 10 AND score < 0.5 → skip`. Ticket T-S4-COST-FILTER (S4-5 della review del 17-giu).

---

### [DAY-009] GS: BUY-SELL-BUY nello stesso giorno (turnover eccessivo)

- **Tipo**: Anomalia — Turnover
- **Area**: Orders
- **Evidenza**:
  - GS: BUY 16:52, SELL 17:52 (1h holding), BUY 18:52, SELL 19:37 (45 min holding)
  - Perdita netta –$27 in 2 roundtrip
  - Motivazione: 2 segnali diversi in sequenza (signal_id=227 poi 228) con score +0.765 e +0.293
- **Descrizione**: Il sistema non ha un minimum holding period per S4. I segnali intraday si susseguono e il combiner genera SELL/BUY rapidi sullo stesso simbolo.
- **Impatto**: Turnover eccessivo, commissioni SEC/FINRA, slippage bid-ask reale.
- **Severità**: Medium
- **Confidenza**: High
- **Azione consigliata**: Min holding period 4h + debounce segnale per S4.

---

## 11. FALSI POSITIVI / AREE CORRETTE

| Area | Stato | Evidenza |
|---|---|---|
| LLM mai nel hot path | ✅ Confermato | Nessuna chiamata LLM in `portfolio_scheduler.py` o `execution.py` |
| Score formula polarity×confidence | ✅ Corretto | Verificato sui dati DB |
| Orari di trading | ✅ Dentro market hours | Primo 14:07, ultimo 19:52 UTC (NYSE 13:30–20:00 UTC) |
| Deduplicazione DB | ✅ Funziona | `ON CONFLICT (url, ticker) DO NOTHING` |
| SELL su posizioni chiuse correttamente | ✅ | `exit_reason = portfolio_sell` per tutti |
| LLM output validation | ✅ | 0 `ineligible` responses in `llm_responses` |
| Paper mode confermato | ✅ | Tutti i trade Alpaca paper (S4 capped 10%) |
| Audit trail | ✅ | Catena completa `execution_decisions → trades → portfolio_cycles` |
| CVX/XOM/XLE negativi non eseguiti | ✅ | Segnali negativi correttamente filtrati |
| GS segnale negativo (–0.549) non eseguito | ✅ | Signal id=188 non ha driven trade |

---

## 12. DATI MANCANTI / NON ACCESSIBILI

| Area | Gap | Causa | Come ottenere |
|---|---|---|---|
| Log worker 2026-06-17 | Non accessibili | Container riavviato il 18-giu 08:11; log precedenti persi | Diff `docker-compose.yml` corrente aggiunge `logging json-file` — risolutivo per i futuri |
| Root cause staleness GDELT | Non determinata | `gkg_url` non loggato | Loggare `gkg_url` e date range in ogni invocazione GDELT |
| Esito regime detector 2026-06-17 | Non verificabile | Nessuna `regime_history` table | Implementare T-REGIME-HISTORY |
| Stats ingestion per run | Non strutturate | Solo `log.info` — non persistito in DB | Creare tabella `ingestion_log` |
| Alpaca order fill confirmation | Non verificabile | Log non disponibili | `GET /v2/orders/{order_id}` via API Alpaca Paper |
| Forward returns segnali 17-giu | Non calcolati | `performance_metrics` vuota | Eseguire `run_forward_return_worker` retroattivamente |
| Risk report 2026-06-17 | Mancante | Container crashato prima del 22:30 | Non recuperabile |

---

## 13. RACCOMANDAZIONI IMMEDIATE

1. **[P0] Idempotenza BUY**: `get_orders(status=OPEN)` + idempotency token Redis per `signal_id` (TTL EOD). **Blocca capitale reale.**
2. **[P0] Freshness gate**: Prima di ogni portfolio cycle: `if max(fetched_at) > now() – 6h → skip S4 + alert Telegram`. **Blocca capitale reale.**
3. **[P0] TTL segnale Redis**: Segnali in `news:queue` non sopravvivono oltre 4h o fine sessione. Aggiungere TTL al `rpush`.
4. **[P0] Regime wire**: Collegare `regime_mult` dal detector (Ticket T-REGIME-WIRE già aperto).
5. **[P0] Log persistenti**: Verificare che il diff `docker-compose.yml` (logging json-file) sia deployato.
6. **[P1] Redis appendonly**: `appendonly yes` nel container Redis per preservare Deduplicator state.
7. **[P1] GDELT staleness logging**: Loggare `gkg_url` + date range a ogni fetch. Alert se `max(date_col) < now() – 6h`.
8. **[P1] Ticker cross-validation**: Verificare ticker nel headline come whole-word; flaggare "cross-reference" se solo in metadati GDELT.
9. **[P1] Filtro costo-aware S4**: `if cost_bps > 10 AND score < 0.5 → skip`.

---

## 14. TEST/MONITOR DA AGGIUNGERE

| Monitor | Trigger | Azione |
|---|---|---|
| News staleness | `max(fetched_at) < now() – 6h` durante market hours | Halt S4 + alert Telegram |
| Duplicate BUY | `signal_id` → 2+ BUY per sessione | Log + skip secondo BUY |
| Signal age | `generated_at < now() – 4h` prima di BUY | Skip + log warning |
| Risk report presenza | Nessun record in `risk_reports` nelle ultime 24h | Alert operatore |
| Redis MISCONF | CRITICAL log nel worker | Alert immediato |
| INFY/low-price costo | `cost_bps > 10 AND score < 0.5` | Skip pre-trade |
| Ticker misattribution | Ticker non in headline title come whole-word | Flag "cross-ref risk" in `news_log` |
| GDELT URL staleness | `gkg_url` punta a file > 2h fa | Warning ingest |

---

## 15. TICKET TECNICI SUGGERITI

| Ticket | Descrizione | Priorità | Blocca live |
|---|---|---|---|
| T-IDEMPOTENT-BUY | `get_orders(OPEN)` + idempotency token Redis per segnale | P0 | ✅ |
| T-FRESHNESS-GATE | Check staleness news pre-cycle; halt se > 6h | P0 | ✅ |
| T-SIGNAL-TTL | TTL Redis per segnali in `news:queue` (4h o EOD) | P0 | ✅ |
| T-REGIME-WIRE | Wire `regime_mult` dal detector (già aperto) | P0 | ✅ |
| T-GDELT-STALENESS-LOG | Log `gkg_url` + date range per ogni invocazione GDELT | P1 | — |
| T-TICKER-XREF | Cross-validation ticker vs headline | P1 | — |
| T-REDIS-APPENDONLY | `appendonly yes` nel container Redis | P1 | — |
| T-INGESTION-LOG-TABLE | Persistere stats ingestion in DB | P1 | — |
| T-RISK-REPORT-ALERT | Alert se `risk_reports` mancante da >24h | P1 | — |
| T-S4-MIN-HOLD | Min holding period 4h + debounce segnale per S4 | P1 | — |
| T-S4-COST-FILTER | Skip pre-trade se `cost_bps > 10 AND score < 0.5` | P1 | — |

---

*Report generato in read-only il 2026-06-19. Nessun file modificato, nessun commit, nessun ordine eseguito. Ogni raccomandazione è un ticket, non una patch. Autorizzazione richiesta prima di qualsiasi modifica operativa.*
