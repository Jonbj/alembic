# Alembic — Guida Utente

> **Ultimo aggiornamento**: Giugno 2026  
> **Versione**: v3 (Phase A/B/C — Trade Analytics, Feedback Loop, Counterfactual)

---

## Indice

1. [Cos'è Alembic](#1-cosè-alembic)
2. [Il flusso di utilizzo corretto](#2-il-flusso-di-utilizzo-corretto)
3. [Le pagine della dashboard](#3-le-pagine-della-dashboard)
4. [Le metriche: come leggerle](#4-le-metriche-come-leggerle)
5. [Le strategie](#5-le-strategie)
6. [I validation gates](#6-i-validation-gates)
7. [Il sistema di score e segnali](#7-il-sistema-di-score-e-segnali)
8. [Glossario](#8-glossario)

---

## 1. Cos'è Alembic

Alembic è un **sistema di trading algoritmico** che combina analisi del sentiment con strategie quantitative sistematiche.

**Come funziona in soldoni:**

1. Ogni 15 minuti, un ensemble di LLM (Kimi, Qwen, DeepSeek, GLM) analizza le notizie finanziarie
2. Ogni articolo produce un **punteggio di sentiment** da -1.0 (molto bearish) a +1.0 (molto bullish)
3. I punteggi vengono aggregati e filtrati in **segnali di trading**
4. I segnali alimentano le strategie operative che decidono se comprare, vendere o restare fermi

**Stato attuale del portfolio:**

| Strategia | Tipo | Stato | Note |
|-----------|------|-------|------|
| S1 — Time-Series Momentum | Momentum cross-asset | supervised_paper, promotion_blocked | Re-promotion richiede evidenza aggiornata e sign-off |
| S2 — Volatility Risk Premium | Vendita opzioni put SPY | disabled/in sviluppo | Non nel portfolio operativo |
| S3 — Cross-Sectional Momentum | Momentum relativo equity | ⏸ R&D sleeve | Sharpe 0.15, gate 3&5 falliti |
| S4 — News-Driven Tactical | Sentiment ranking | paper, promotion_blocked | 10% paper overlay; non autorizzata live |

Il sistema è attualmente in **modalità backtest/paper**. Nessun capitale reale è a rischio.

---

## 2. Il flusso di utilizzo corretto

### Flusso giornaliero tipico

```
Mattina (9:00)
├── Overview
│   └── Controlla readiness, P&L, posizioni, signal gate e decision summary
│
├── Operations → System
│   └── Worker schedulati recenti? Activity log coerente? Kill-switch/mode corretti?
│
├── News
│   └── Verifica ingestion e notizie rilevanti prima di leggere i signal
│
├── Signals
│   └── Ci sono segnali estremi (>0.6 o <-0.6)?
│   └── Il modello è concorde (bassa ensemble_std)?
│
├── Quality
│   └── Near-zero/fallback/ticker precision stanno degradando?
│
Giorno per giorno
├── Performance → tab Analytics (dopo ≥20 trade chiusi nel periodo)
│   └── Quale simbolo/ora/score bucket sta trainando o drenando il P&L?
│   └── Win rate in calo? → controlla segnale per quei ticker
│
├── Se anomalie → LLM → tab Feedback
│   └── Controlla se un modello sta generando troppi fallback
│
├── LLM → tab Pesi (se cambiati)
│   └── Approva o rifiuta il suggerimento di ribilanciamento
│
├── Se vuoi capire un segnale → News
│   └── Filtra per ticker e vedi le notizie che l'hanno generato
│
Settimanalmente
├── Auto-Improve → tabella Phase C
│   └── SKIP_THRESHOLD ha avg_return positivo su ≥30 obs? Valuta il feedback gate con IC/label evidence
│   └── SKIP_EMA/SKIP_CAP con upside missed alto? Valuta solo se ancora rilevanti nel path attivo
│
├── Backtest
│   └── IC, ICIR, hit rate — la qualità predittiva si mantiene?
│
├── Strategies
│   └── I gate sono ancora tutti PASS? La sensitivity è stabile?
│
├── Operations → Config/Admin
│   └── Verifica watchlist, rischio, modalità e kill-switch
```

### Cosa NON fare

- ❌ Cambiare modalità da `paper` a `full_auto` senza autorizzazione
- ❌ Attivare il kill switch per test — è l'equivalente di un arresto di emergenza
- ❌ Modificare la watchlist senza capire l'impatto sul portafoglio
- ❌ Approvare sempre i pesi suggeriti senza controllare il delta

---

## 3. Le pagine della dashboard

L'applicazione è accessibile all'indirizzo **http://192.168.178.144:3000**. Il menu laterale segue il flusso operativo: Overview, News, LLM, Signals, Quality, Trading, Performance, Strategies, Auto-Improve, Validation, Labeling, Backtest, Admin e Docs. La vecchia pagina Dashboard/Grafana non è più una superficie utente: `/dashboard` reindirizza a Overview. La vecchia pagina Trades è stata rimossa: `/trades` reindirizza a Trading, mentre analytics e P&L restano in Performance.

I pulsanti **Trace** seguono la catena causale `News -> Signal -> Decision -> Order -> Performance`: aprono una drawer con i passaggi disponibili e marcano come non tracciati quelli non generati dal sistema.

---

### 3.1 Overview ⊞

**A cosa serve**: Fotografia istantanea dello stato del sistema. È la prima pagina da guardare ogni giorno.

**Cosa trovi:**

| Elemento | Significato |
|----------|------------|
| **Net P&L (month)** | Profitto/perdita cumulativo del mese corrente |
| **Open positions** | Numero di posizioni aperte e relative ai ticker |
| **Unrealized P&L** | Profitto/perdita non realizzato di tutte le posizioni aperte |
| **Signals today** | Quanti segnali Buy / Sell / Hold generati oggi |
| **Monthly P&L chart** | Grafico a barre del P&L mensile (verde = guadagno, rosso = perdita) |
| **Open positions table** | Tabella con Ticker, Quantità, P&L, P&L% di ogni posizione |
| **Latest Signals** | Ultimi 10 segnali generati con score, confidence e modello |

**Come usarla**: Apri la pagina al mattino. Se il P&L mensile è negativo, approfondisci su Performance. Se ci sono molte posizioni aperte, controlla che non siano tutte dalla stessa parte del mercato.

---

### 3.2 Signals ⚡

**A cosa serve**: Vedere tutti i segnali di sentiment generati dal sistema per ogni ticker.

**Cosa trovi:**

| Colonna | Significato |
|---------|------------|
| **Ticker** | Simbolo azionario (es. AAPL, NVDA) |
| **Direction** | Freccia verde (BUY) / rossa (SELL) / grigia (HOLD) |
| **Score** | Punteggio da -1.0 a +1.0 → il "segnale" vero e proprio |
| **Confidence** | Quanto il modello è sicuro del giudizio (0-100%) |
| **Model** | Quale ensemble ha prodotto il segnale |
| **Fallback** | Badge "FB" se il FinBERT di fallback è stato attivato (i modelli principali erano in disaccordo) |
| **Time** | Quando il segnale è stato generato |

> **Nota selezione (ciclo live)**: per ogni ticker il sistema usa, nella finestra di freschezza (4h), il segnale **ensemble più recente** — un fallback FinBERT "FB" debole generato *dopo* un ensemble forte **non** lo sovrascrive (il fallback si usa solo se non c'è ensemble fresco). La watchlist tradabile S4 è a **96 simboli** (aggiunti ROKU, RDDT, HOOD, WDC, SPCX il 2026-06-30).

**Filtri disponibili:**
- **Filter ticker**: cerca un ticker specifico (es. "NVDA")
- **All directions / BUY / SELL / HOLD**: filtra per direzione del segnale

**Come leggere i segnali:**

| Score | Interpretazione |
|-------|----------------|
| +0.6 → +1.0 | Fortemente bullish — segnale di acquistoConvinto |
| +0.3 → +0.6 | Moderatamente bullish |
| -0.3 → +0.3 | Neutrale / rumore — il sistema non agisce |
| -0.6 → -0.3 | Moderatamente bearish |
| -1.0 → -0.6 | Fortemente bearish — segnale di vendita |

**⚠️ Importante**: Il segnale efficace è `score × confidence`. Uno score di 0.9 con confidence 0.4 dà un segnale efficace di 0.36 (moderato, non forte). Non fidarti di un solo numero: guarda sempre la confidence.

---

### 3.3 Trading 📈

**A cosa serve**: Monitorare le posizioni aperte e lo storico degli ordini eseguiti.

**Due tab:**

**Posizioni aperte**:

| Colonna | Significato |
|---------|------------|
| **Ticker** | Simbolo della posizione |
| **Qty** | Numero di azioni |
| **Avg Price** | Prezzo medio di ingresso |
| **Market Value** | Valore corrente della posizione |
| **Unrealized P&L** | Profitto/perdita non realizzato in dollari |
| **P&L%** | Profitto/perdita in percentuale |

**Storico ordini**:

| Colonna | Significato |
|---------|------------|
| **Ticker** | Simbolo scambiato |
| **Side** | BUY o SELL |
| **Qty** | Quantità (può essere None per ordini fractional) |
| **Fill Price** | Prezzo medio di esecuzione |
| **Status** | Stato dell'ordine (filled, canceled, etc.) |
| **Submitted** | Data/ora di sottomissione |

**Nota**: In modalità `backtest` non ci sono posizioni reali. Le posizioni appaiono solo in modalità `paper` o superiore.

---

### 3.3b Performance — Daily & Analytics 📊

**A cosa serve**: Analisi dei trade chiusi e valutazione multidimensionale dell'edge del sistema. La vecchia pagina `Trades` non è più nel menu: lo storico operativo è in **Trading**, mentre la diagnosi post-trade è in **Performance**.

**Tab Giornaliero**

Mostra P&L lordo, costi e P&L netto per giorno, con dettaglio espandibile dei trade chiusi. Le metriche sommario mostrano:

| Metrica | Interpretazione |
|---------|----------------|
| **Total Trades** | Numero chiusure nel periodo (7/30/90 gg) |
| **Win Rate** | Target realistico S4: >52%. Sotto il 48% segnala deterioramento del segnale |
| **Avg Net P&L** | Media per trade dopo slippage stimato. Positivo ma vicino a zero indica edge sottile |
| **Total Net P&L** | P&L cumulativo. Verde = sistema in profitto netto |

Il **grafico P&L per giornata** mostra se le perdite sono concentrate in singole sessioni o distribuite. Una sequenza di perdite accentuata può attivare Phase B nella pagina Auto-Improve.

Clicca una giornata per espandere i dettagli: simbolo, motivo uscita, entry/exit, quantità, gross P&L, costi e net P&L.

**Tab Analytics (Phase A)**

Questa tab recupera gli analytics precedentemente indicati come `Trades → Analytics`. Risponde alla domanda: *dove guadagna e perde il sistema?*

| Grafico | Come leggerlo | Azione se negativo |
|---------|--------------|-------------------|
| **Per Simbolo** | P&L totale per ticker | Rimuovere i ticker sistematicamente negativi dalla watchlist |
| **Per Regime** | P&L medio per regime_mult bucket | Se perde solo in regime basso, il filtro funziona — non intervenire |
| **Per Ora** | P&L medio per ora di apertura (EST) | Aggiungere filtro orario per le fasce negative |
| **Per Score LLM** | P&L per bucket di score | Se bucket alti non battono quelli bassi, il segnale non ha edge discriminante |
| **Per Durata** | P&L per durata di detenzione | Trade <15min soffrono di spread; >2h il segnale è stantio |

Cambia il periodo (30/90/365 gg) per bilanciare freschezza e volume statistico. Con meno di 30 trade chiusi i grafici hanno bassa significatività.

---

### 3.3c Auto-Improve 🔧

**A cosa serve**: Monitorare il sistema di auto-correzione in tre fasi. Nessun intervento manuale richiesto in condizioni normali — il sistema si aggiusta da solo.

**Card: Phase B — Feedback Gate**

Il sistema controlla le perdite ogni 30 minuti durante gli orari di mercato e alza automaticamente la soglia di ingresso letta dal portfolio scheduler.

| Stato | Significato | Azione |
|-------|------------|--------|
| Entry Threshold = 0.30, Scale = 1.0× | Baseline, nessuna perdita recente | Nessuna |
| Threshold > 0.30 | Feedback attivo dopo perdite consecutive | Monitorare — normale in mercati difficili |
| Scale < 1.0× | Stato Redis legacy/audit; non interpretarlo come sizing ridotto nel path portfolio finché non è cablato | Monitorare |
| Attivo da >24h senza recovery | Mercato persistentemente avverso | Verificare Signals, Overview, considerare Halted |

**Trigger** (logica OR): 3 perdite consecutive, oppure P&L rolling negativo sugli ultimi 10 trade.
**Recovery**: 5 vincite consecutive riportano ai valori baseline.
**TTL**: ogni aggiustamento scade automaticamente dopo 48 ore.

**Card: Phase C — Gate Opportunity Cost (tabella)**

Analisi retrospettiva dei candidati scartati da gate/filtri. Il `counterfactual-worker` calcola nightly (22:45 UTC) il ritorno a 1h per i casi inclusi.

La card mostra anche lo stato operativo Phase C:

| Campo | Significato |
|-------|-------------|
| Last worker run | Ultima esecuzione osservata del `counterfactual-worker` salvata in Redis |
| Last processed row | Ultimo `counterfactual_computed_at` scritto su `execution_decisions` |
| Raw Phase C skips | Totale skip inclusi in Phase C, quanti sono pending e quanti hanno ritorno 1h disponibile |
| Raw skip counts | Conteggio grezzo di tutti gli `SKIP_*`, inclusi quelli esclusi intenzionalmente dalla Phase C |

Se la tabella opportunity-cost è vuota, leggi prima lo stato:

| Stato | Interpretazione |
|-------|-----------------|
| Worker not observed | Non c'è ancora metadata Redis dell'ultimo run: verificare scheduler/log se persiste |
| Last worker run skipped/failed | La Phase C non è affidabile finché il worker non torna `ok` |
| No Phase C skips in window | Vuoto reale: nessun `SKIP_THRESHOLD`, `SKIP_EMA` o `SKIP_CAP` nella finestra |
| Skips pending nightly processing | Esistono skip, ma mancano ancora i ritorni 1h; attendere il run 22:45 UTC |
| Phase C processed | I dati sono aggiornati rispetto all'ultimo run osservato |

| Tipo | Causa del filtro | Quando preoccuparsi |
|------|-----------------|---------------------|
| **SKIP_THRESHOLD** | Score sotto la soglia feedback attiva | avg_return >+0.5% e % profitable >55% su ≥30 obs, poi verificare IC/label evidence |
| **SKIP_EMA** | Prezzo sotto EMA20 al momento del segnale | avg_return >+0.5% e % profitable >55% su ≥30 obs |
| **SKIP_CAP** | Limite di allocazione per ciclo raggiunto | upside missed alto e ricorrente |

`SKIP_STALE`, `SKIP_FALLBACK` e `SKIP_POSITION` sono esclusi: non rappresentano filtri da allentare, ma signal non affidabili o posizioni già aperte.

**Regola decisionale**: agisci su un filtro solo se *avg_return > +0.5%* e *% profitable > 55%* su almeno 30 osservazioni computate. Sotto questa soglia i dati sono statisticamente rumorosi.

I dati del giorno corrente appariranno il giorno successivo. La tabella è vuota nei primi giorni di paper trading.

---

### 3.4 Performance 📊

**A cosa serve**: Valutare l'andamento del portafoglio nel tempo.

**Cosa trovi:**

- **Cumulative P&L**: Grafico a linee del profitto/perdita cumulativo
- **Portfolio Equity**: Grafico dell'equity (valore totale) del portafoglio
- **Monthly P&L Summary**: Tabella mese per mese con P&L e direzione (Gain/Loss)
- **Selettore periodo**: 1M, 3M, 6M, 1Y

**Come leggerla:**

- Una curva P&L che sale costantemente = buon segno
- Flat o discendente = il sistema sta sotto-performando
- Guarda sempre l'orizzonte lungo (6M+): un singolo mese negativo è normale

---

### 3.5 Strategies 🎯

**A cosa serve**: Ispezionare ogni strategia del v2 framework — parametri, validation gate, equity curve e sensitivity.

**Cosa trovi per ogni strategia:**

| Sezione | Cosa mostra |
|---------|------------|
| **Lifecycle verdict** | Mode corrente, stato promotion/live authorization e fonte metriche LIVE/BACKTEST |
| **KPI Cards** | OOS Sharpe (performance fuori campione), Max Drawdown, Annual Return, Total Trades |
| **Equity Curve** | Grafico del ritorno cumulativo e del drawdown nel tempo |
| **Validation Gates** | Tabella con 5 gate: Significance, Walk-Forward, Robustness, Regime, Stress — ognuno con PASS/FAIL |
| **Parameter Sensitivity** | Heatmap dello Sharpe ratio al variare dei parametri (lookback, vol_window) |
| **Strategy Parameters** | Valori dei parametri della strategia (lookback, vol target, leverage, etc.) |
| **Universe** | Lista dei ticker utilizzati dalla strategia |

**Come usarla:**

1. Seleziona la strategia dal menu a tendina
2. Controlla prima il **Lifecycle verdict** — se promotion/live sono false o blocked, i KPI sono solo evidenza
3. Controlla i **KPI** — OOS Sharpe ≥ 0.5 è il minimo per discutere promozione, non un'autorizzazione
4. Poi controlla i **gates** — devono essere tutti PASS (o con eccezioni documentate)
5. La **sensitivity** ti dice se la strategia è robusta o se funziona solo con parametri perfetti

---

### 3.6 Backtest 🔬

**A cosa serve**: Analizzare la qualità predittiva dei segnali LLM su dati storici.

**Cosa trovi:**

| Sezione | Significato |
|---------|------------|
| **Run selector** | Scegli quale backtest run analizzare (es. `gkg-jan26-v1`) |
| **IC (Spearman)** | Correlazione tra score e rendimento futuro — sopra 0.15 è buono |
| **ICIR** | IC diviso la sua deviazione standard — sopra 2.0 è robusto |
| **Hit Rate** | Percentuale di volte che il segnale ha anticipato correttamente la direzione |
| **Avg Long/Short Return** | Rendimento medio delle posizioni long/short |
| **Score Bucket Analysis** | Grafico: rendimento medio per decile di score. Monotono crescente = buon modello |
| **Cumulative P&L Curve** | Curva P&L simulata con soglia selezionabile (0.02, 0.05, 0.10) |
| **IC by Model** | Tabella con IC e hit rate per ogni modello LLM |
| **IC by Symbol** | Tabella con IC e hit rate per ogni ticker |

**Come leggere il bucket analysis:**

```
Score decile 1 (più bearish) → rendimento medio del decile
Score decile 5 (neutrale)     → rendimento vicino a zero
Score decile 10 (più bullish) → rendimento medio del decile
```

Se il grafico è **monotonamente crescente** (da sinistra a destra), il modello ha potere predittivo reale. Se è piatto o zigzaga, il segnale è rumore.

**Threshold**: La soglia dello score sopra la quale si attiva un trade. Più alta = meno trade ma più selettivi. Il default è 0.05 (per backtesting).

---

### 3.7 News 📰

**A cosa serve**: Vedere le notizie finanziarie che alimentano il sistema di sentiment.

**Cosa trovi:**

| Colonna | Significato |
|---------|------------|
| **Title** | Titolo dell'articolo (clicca per espandere e vedere URL) |
| **Source** | Fonte (`gdelt_gkg`, `gdelt`, `marketaux`, `alpaca_benzinga`, `finnhub`, `sec_edgar`, RSS live se attivi) |
| **Ticker** | Ticker associato all'articolo |
| **Sentiment** | Badge Positive/Negative/Neutral basato su raw_sentiment |
| **Time** | Quando l'articolo è stato acquisito |

**Source quality**: il pannello sopra la tabella confronta le fonti negli ultimi 7/30/90/180 giorni. Mostra il funnel `News -> Signal -> Decision -> Order`, copertura ticker, confidence media, latenza media publish-to-fetch e P&L chiuso quando disponibile. Usa questi dati per capire se una fonte produce segnali utili o solo volume.

**Decision outcome**: nel dettaglio di una news, se il ciclo portfolio ha valutato il segnale, vedi anche l'esito diagnostico. Esempio: `SKIP_THRESHOLD` indica che la news ha generato un segnale, ma lo score era sotto la soglia operativa attiva; non è quindi un errore né una news ignorata.

**Filtri:**
- **Filter ticker**: mostra solo notizie per un ticker specifico
- **Source filter**: filtra una fonte specifica, inclusi GDELT, MarketAux, Alpaca/Benzinga, Finnhub, SEC EDGAR e feed RSS live se attivi

**Come usarla**: Se un segnale su un ticker ti sembra strano, filtra per quel ticker e controlla quali notizie lo hanno generato. Un articolo singolo anomalo può distorcere il punteggio.

---

### 3.8 LLM 🤖

**A cosa serve**: Monitorare e gestire i modelli AI che producono i segnali.

**Due tab:**

**Feedback modelli**:

| Colonna | Significato |
|---------|------------|
| **Ticker** | Simbolo analizzato |
| **Model** | Quale modello ha prodotto l'analisi (es. `ensemble:kimi+qwen+deepseek+glm`) |
| **Polarity** | Sentiment del modello: ▲ positivo / ▼ negativo / — neutro |
| **Confidence** | Livello di certezza del modello |
| **Divergence σ** | Deviazione standard tra i modelli — alto (>0.3) = disaccordo |
| **Fallback** | "FB" se il FinBERT è stato attivato perché l'ensemble era in disaccordo |
| **Reasoning** | Breve spiegazione del perché il modello ha dato quel punteggio |

**Pesi ensemble**:

| Sezione | Significato |
|---------|------------|
| **Current Weights** | Pesi attivi di ogni modello nell'ensemble |
| **Suggested Weights** | Pesi suggeriti dal sistema (basati sulla performance recente) |
| **Δ vs Current** | Differenza tra suggerito e attuale |
| **Approve** | Pulsante per approvare i pesi suggeriti (richiede API key) |

**Quando approvare i pesi?**

Il sistema suggerisce automaticamente nuovi pesi basandosi sulla performance recente di ogni modello. Approva se:

- ✅ Il modello con IC migliore riceve più peso
- ✅ I delta sono piccoli (<5% per modello)
- ✅ Non ci sono freeze_reason

Non approvare se:

- ❌ Un modello con IC molto basso riceve più peso
- ❌ C'è un freeze_reason (il sistema blocca automaticamente i cambiamenti durante periodi instabili)

---

### 3.9 Operations ⚙

**A cosa serve**: Unifica System, Config e Admin in un unico punto operativo.

**Tab System**: scheduler, activity log e segnali PEAD.

**Tab Config**: watchlist, risk parameters e full config read-only.

**Tab Admin**: kill switch e operating mode, con conferme esplicite per le azioni critiche.

---

### 3.9a Config

**A cosa serve**: Configurare il comportamento del sistema in tempo reale.

**Cosa puoi modificare:**

| Parametro | Significato | Range tipico |
|-----------|------------|-------------|
| **Watchlist** | Lista dei ticker monitorati dal sistema | 10-150 ticker |
| **Max Drawdown** | Soglia massima di drawdown prima del killswitch | 5-20% |
| **Stop Loss** | Soglia di stop loss per singola posizione | 1-10% |

**⚠️ Attenzione**: Le modifiche alla config entrano in vigore al prossimo ciclo del worker (circa 15 minuti). La watchlist influisce direttamente su quali ticker ricevono segnali — rimuovere un ticker lo elimina dal monitoraggio.

**Full Config (read-only)**: Mostra l'intero file `trading.yaml` come JSON. Utile per verificare parametri avanzati come `signal_freshness_minutes`, `vix_spike`, `max_position_pct`.

---

### 3.9b Admin

**A cosa serve**: Controllare e modificare il funzionamento del sistema. **Richiede API key.**

**Kill Switch**:

Il kill switch è un **arresto di emergenza**. Quando attivato:

- 🛑 Tutti gli ordini vengono bloccati
- 🛑 La modalità passa a `halted`
- 🛑 Nessun nuovo trade viene eseguito

**Quando usarlo**: SOLO in caso di emergenza reale (mercato in crollo, comportamento anomalo del sistema). Per testare, usa la modalità `backtest`.

**Operating Mode**:

| Modalità | Significato |
|----------|------------|
| `backtest` | Simulazione su dati storici — nessun ordine reale o simulated |
| `paper` | Trading simulato con ordini fittizi — nessun capitale reale a rischio |
| `semi_auto` | Ogni ordine richiede approvazione Telegram prima dell'esecuzione |
| `full_auto` | Completamente automatizzato — gli ordini vengono eseguiti senza conferma |
| `halted` | Tutto fermo — kill switch attivo |

**⚠️ ATTENZIONE**: Passare da `paper` a `full_auto` significa che il sistema Traderà con **capitale reale** senza alcuna conferma. NON farlo senza autorizzazione esplicita.

**Economy Mode (sidebar)**:

Il bottone in basso a sinistra nella sidebar permette di commutare tra:

- **Full ensemble** (⚡): Tutti e 4 i modelli LLM analizzano ogni articolo. Più accurato ma più costoso.
- **Economy** (🪙): Solo il modello GLM analizza. Più economico ma meno accurato. Utile per risparmiare token quando il mercato è chiuso.

### 3.11 Labeling 🏷️

**A cosa serve**: Costruire il *golden label set* (QX-01) — la verità di riferimento contro cui si misura la qualità dell'estrazione ticker e del sentiment. È l'**unico passo umano** che sblocca calibrazione ed enforcement.

**Come si usa**: Per ogni news leggi **titolo + testo** (annotazione **blind**: NON vedi il ticker estratto dal sistema, per non farti influenzare), poi indichi:

| Campo | Cosa | 
|-------|------|
| **Ticker** | Le aziende quotate che la news riguarda davvero (vuoto se macro/irrilevante) |
| **Rilevanza** | company_specific / sector / macro / irrelevant |
| **Direzione** | positive / neutral / negative |
| **Forza** | 0 (debole/neutro) → ±1 (forte) |

~30-60s a news. La progress si salva. I **forward return** (1h/1d/2d) vengono calcolati automaticamente da Alpaca dopo l'annotazione — non li inserisci tu.

### 3.12 Quality 🔬

**A cosa serve**: Vedere empiricamente la qualità del segnale — i problemi che il quality review ha trovato, ora misurabili e aggiornati in tempo reale.

| Sezione | Cosa mostra |
|---------|-------------|
| **Sentiment per modello** | Polarity media (≠0 = bias), confidence media (compressa ≈0.65 = poco discriminante), near-zero rate, eligible rate |
| **Segnali ensemble** | Near-zero rate (rumore), fallback rate (FinBERT), ensemble std (divergenza) |
| **Estrazione ticker** (golden set) | Precision, recall, FP/articolo, macro-FP (dovrebbe ≈0) — si aggiorna man mano che annoti su Labeling |

Auto-refresh ogni 2 minuti. Finestra selezionabile (7/14/30 giorni).

---

## 4. Le metriche: come leggerle

### Metriche chiave e valori di riferimento

| Metrica | Cos'è | Valore buono | Valore debole |
|---------|-------|-------------|---------------|
| **Sharpe Ratio** | Rendimento aggiustato per il rischio (rendimento/volatilità) | > 0.5 (OOS) | < 0.3 |
| **IC (Information Coefficient)** | Correlazione tra segnale e rendimento futuro | > 0.15 | < 0.05 |
| **ICIR** | IC diviso la sua deviazione standard — misura consistenza | > 2.0 | < 1.0 |
| **Hit Rate** | Percentuale di previsioni corrette | > 55% | < 50% |
| **Max Drawdown** | Massima perdita dal picco | < 15% | > 25% |
| **OOS Sharpe** | Sharpe calcolato su dati non visti in training | > 0.5 | < 0.3 |

### Sharpe vs IC: qual è la differenza?

- **IC** misura la qualità del segnale: "Il punteggio LLM predice il rendimento futuro?"
- **Sharpe** misura la qualità della strategia: "Seguendo i segnali, quanto guadagno per unità di rischio?"

Una strategia può avere buon IC ma pessimo Sharpe (se i costi di trading mangiano il profitto), e viceversa.

### Come leggere l'IC per modello

Nella pagina **Backtest → IC by Model**, ogni riga mostra:

```
Modello         N      IC     Hit Rate   Avg Return
kimi-k2.6       5000   0.082  54.2%       +0.12%
deepseek-v4     4200   0.065  52.8%       +0.08%
qwen3.5         4500   0.041  51.1%       +0.03%
glm-5.1          3800  0.038  50.5%       +0.02%
```

- **N alto** = il modello copre molti articoli (buona copertura)
- **IC positivo** = il modello ha potere predittivo
- **Hit Rate > 50%** = il modello batte il caso

Se un modello ha IC negativo o N=0, non significa necessariamente che è rotto. FinBERT (N=0) è un fallback che si attiva solo quando l'ensemble principale è in disaccordo.

---

## 5. Le strategie

### S1 — Time-Series Momentum ✅

**Cosa fa**: Compra gli asset che sono saliti di più (momentum) e vende quelli che sono scesi di più, aggiustando il peso per la volatilità.

**Come funziona**:
- Guarda il rendimento degli ultimi 12 mesi (lookback lungo) e 1 mese (lookback corto)
- Normalizza per volatilità — assegna meno peso agli asset più volatili
- Ribilancia mensilmente

**Parametri**: Lookback lungo 252gg, corto 21gg, vol_window 60gg, vol_target 10%

**Universe**: 15 ETF cross-asset (SPY, QQQ, IWM, VEA, VWO, EWJ, TLT, IEF, SHY, LQD, HYG, TIP, GLD, DBC, VNQ)

**Stato**:VALIDATA — Sharpe OOS 0.51, 5/5 gate passati

### S2 — Volatility Risk Premium 🔄

**Cosa fa**: Vende opzioni put OTM su SPY per incassare il premio di assicurazione (la "volatility risk premium").

**Come funziona**:
- Seleziona put con delta -0.20, scadenza 30-45 giorni
- Incassa il premio e spera che l'opzione scada senza valore
- Modula l'aggressività in base al regime di mercato
- Filtra gli eventi rischiosi (FOMC, NFP) usando l'ensemble LLM

**Stato**: In sviluppo (Fase D)

**Nota su gate 4**: Per S2 è accettato passare con 2 regimi positivi + 1 neutro + 1 negativo, perché il VRP è intrinsecamente un premio assicurativo che sotto-performa negli stress.

### S3 — Cross-Sectional Momentum ⏸

**Cosa fa**: Ranking relativo — compra le azioni che performano meglio rispetto alla loro beta e vende quelle peggiori.

**Perché è in pausa**: Il backtest su dati reali ha dato Sharpe 0.15 (troppo basso), con alta fragilità ai parametri (CV=2.05 quando il massimo accettabile è 0.5). Il codice esiste e funziona, ma non entra nel portfolio live finché il tuning non migliora i risultati.

### S4 — News-Driven Tactical

**Cosa fa**: Strategia news/sentiment in modalità paper overlay. Usa segnali LLM pre-calcolati, feedback gate, filtri di freschezza e trend per decidere se proporre esposizione tattica su ticker della watchlist.

**Stato**: `paper`, `promotion_blocked`, `live_authorized=false`. Non è autorizzata al live; le metriche e i counterfactual servono solo come evidenza per revisione futura.

---

## 6. I validation gates

Ogni strategia deve superare 5 gate per entrare nel portfolio live. Ecco cosa significano:

### Gate 1 — Statistical Significance

**Verifica**: Il segnale ha una correlazione reale con il rendimento futuro, o è solo rumore?

**Misura**: IC (Information Coefficient) con p-value Newey-West < 0.01

**Se fallisce**: Il modello non predice nulla — è come tirare una moneta

### Gate 2 — Walk-Forward Consistency

**Verifica**: La performance fuori campione è comparabile a quella in campione?

**Misura**: Sharpe OOS > 50% dello Sharpe IS, e > 0.3 assoluto

**Se fallisce**: La strategia è overfittata — funziona solo sui dati usati per crearla

### Gate 3 — Parameter Robustness

**Verifica**: Se cambio i parametri del 20%, la strategia funziona ancora?

**Misura**: Mediana Sharpe > 0.5 su 20 varianti, IQR/mediana < 40%

**Se fallisce**: La strategia funziona solo con un set preciso di parametri — è fragile

### Gate 4 — Multi-Regime Stability

**Verifica**: La strategia funziona in diversi tipi di mercato?

**Misura**: Sharpe > 0.3 in almeno 3 dei 4 regimi (RISK_ON, RISK_OFF, GOLDILOCKS, STRESS)

**Eccezione**: S2 (VRP) è accettata con 2 regimi positivi perché è per natura un'assicurazione

### Gate 5 — Stress Test Survival

**Verifica**: La strategia sopravvive ai periodi storici peggiori?

**Misura**: Drawdown massimo < 30% in ogni periodo di stress (2008 GFC, 2020 COVID, 2022 Rate Hikes, 2018 Vol, 2018 Q4)

**Se fallisce**: La strategia può perdere troppo in un mercato in crisi

---

## 7. Il sistema di score e segnali

### Come viene generato un segnale

```
Notizia finanziaria
    ↓
Ensemble di LLM (Kimi, Qwen, DeepSeek, GLM)
    ↓ Ogni modello analizza l'articolo e produce:
    • polarity (-1 a +1)
    • confidence (0 a 1)
    • reasoning (spiegazione testuale)
    ↓
Aggregazione pesata (i pesi sono nella pagina LLM → Pesi)
    ↓ Score composito = Σ(weight_i × polarity_i)
    ↓ Confidence = media pesata delle confidenze
    ↓ Se i modelli sono in forte disaccordo (σ > 0.3):
      → FinBERT fallback viene attivato
    ↓
Score finale = polarity aggregata × confidence
    ↓
Se |score| > soglia di ingresso (default 0.05 per backtest, 0.3 per live)
  → Segnale BUY (score > 0) o SELL (score < 0)
```

### Cosa vuol dire "Fallback"

Quando vedi il badge **FB** nella tabella dei segnali, significa che i modelli principali erano in forte disaccordo e il sistema ha attivato FinBERT come giudice di riserva. Questo non è un problema, ma indica incertezza — tratta quei segnali con più cautela.

### Quando un segnale è "stale"

I segnali hanno una finestra di freschezza di **30 minuti**. Se `generated_at` risale a più di 30 minuti fa, il segnale potrebbe non riflettere le condizioni attuali del mercato. La colonna Time nella pagina Signals ti aiuta a verificarlo.

---

## 8. Glossario

| Termine | Definizione |
|---------|------------|
| **IC (Information Coefficient)** | Correlazione Spearman tra punteggio di sentiment e rendimento futuro. Misura la capacità predittiva del segnale |
| **ICIR** | IC diviso la sua deviazione standard. Un ICIR alto = la predizione è consistente nel tempo |
| **OOS (Out-of-Sample)** | Dati non usati per calibrare la strategia, solo per testarla. L'unico modo per verificare che non sia overfit |
| **Sharpe Ratio** | Rendimento annuo diviso per la volatilità annua. Misura il rendimento per unità di rischio |
| **Drawdown** | Massima perdita dal picco di equity. Un DD del 20% significa che da $100 il portafoglio è sceso a $80 |
| **Walk-Forward** | Tecnica dove la strategia viene calibrata su un periodo e testata sul periodo successivo, scorrendo nel tempo |
| **Ensemble** | Combinazione di più modelli LLM con pesi diversi |
| **Kill Switch** | Arresto di emergenza — ferma immediatamente tutti i trade |
| **Paper Trading** | Trading simulato senza capitale reale |
| **Score** | Punteggio di sentiment da -1.0 a +1.0 |
| **Confidence** | Quanto il modello è sicuro del suo punteggio |
| **Soglia di ingresso** | Score minimo assoluto per generare un trade (tipicamente 0.3 in live) |
| **Watchlist** | Lista dei ticker monitorati dal sistema |
| **Regime** | Classificazione del mercato: RISK_ON (bull), RISK_OFF (bear), GOLDILOCKS (neutrale favorevole), STRESS (crisi) |
| **VRP** | Volatility Risk Premium — il premio che i venditori di opzioni incassano per assicurare i compratori |
| **Gates** | I 5 test che ogni strategia deve superare per entrare nel portfolio |

---

## Risoluzione problemi

### "Nessun segnale appare"

1. **Controlla la modalità** in Operations → Admin — se è `backtest`, il sistema non genera segnali live
2. **Controlla la watchlist** in Operations → Config — se è vuota, non ci sono ticker da monitorare
3. **Controlla i worker** — i sentiment worker girano ogni 15 minuti, potresti dover aspettare

### "Il P&L è sempre zero"

1. Se il sistema è in modalità `backtest`, il P&L è simulato solo nei backtest run
2. Se è in `paper`, controlla che Alpaca paper account sia configurato correttamente

### "I pesi suggeriti non appaiono"

Il sistema calcola i pesi suggeriti periodicamente (tipicamente ogni notte). Se non ci sono abbastanza dati recenti, il suggerimento non viene generato.

### "Le notizie sono vecchie"

Le notizie vengono acquisite dai feed GDELT/MarketAux. Se il mercato è chiuso (weekend, festivi), non ci sono nuove notizie. Il sistema cancella automaticamente le notizie più vecchie di 180 giorni.

---

*Documento generato da Alembic v2. Per dettagli tecnici sui modelli, consulta i documenti in `docs/alembic_v2/`.*
