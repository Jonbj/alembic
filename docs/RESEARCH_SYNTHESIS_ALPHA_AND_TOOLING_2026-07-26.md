# Sintesi consolidata — Alpha, tooling e governance da ricerca esterna

**Data:** 2026-07-26
**Scopo:** razionalizzare in **un unico documento** i tre passaggi di ricerca esterna prodotti
il 25–26 luglio, applicando un filtro coerente (alpha vero vs idraulica vs cose-che-Alembic-ha-già)
e una scala di priorità onesta ancorata allo stack reale di Alembic (US equities, Alpaca,
LLM offline/Alpha-Miner, ciclo ~15 min, IBKR dormiente).

**Fonti razionalizzate (i tre doc grezzi, ora superati da questo):**
1. `docs/RESEARCH_TRADING_BOT_ALPHA_IDEAS_2026-07-25.md` — alpha da letteratura, tracciato a fonti
   primarie, onesto su decay/crowding (Tier A/B/C).
2. `docs/RESEARCH_ALPACA_TRADING_PROJECTS_2026-07-26.md` — 14 progetti Alpaca + 3 tutorial;
   focus connettori/architettura event-driven.
3. `docs/research/2026-07-26-trading-algorithms-research.md` — 30 risorse; strategie, risk,
   execution, portfolio-optimization, alt-data.

> Nota: research note, non status tracker. Lo stato roadmap vive nelle GitHub issue sotto la map `#21`.

---

## 0. Bottom line (leggi solo questo se hai fretta)

I tre passaggi, filtrati, **convergono su un unico messaggio strategico**:

> Il prossimo alpha di Alembic è **segnali strutturati, ortogonali, event-driven** (revisioni
> analisti, diff dei filing, insider) validati con **rigore** (walk-forward purged/embargo,
> IC/ICIR, sector-neutral) — **non** più LLM-sentiment, **non** RL, **non** bot a indicatori.

Tre evidenze indipendenti puntano nella stessa direzione:
- **StockBench (ott-2025)**: la maggior parte degli LLM-agent trader **non batte un equal-weight
  buy&hold** → non raddoppiare su S4.
- **FinGPT**: accuracy di movimento 45–53% (≈ coin flip) → il sentiment LLM da solo non è alpha.
- **LLM_Alpha** (il progetto esterno più vicino al nostro pivot event-driven): metodologia
  eccellente ma **α OOS t-stat +1.35 < 1.96, non significativo** → è un blueprint di **metodo**,
  non una prova di edge.

**Prima mossa concreta:** A1 — segnale revisioni stime analisti / SUE, riattivando gli endpoint
Finnhub già presenti, validato con la metodologia LLM_Alpha (feature schema + purged walk-forward +
gate IC/ICIR). È l'unico Tier A a effort basso.

**Da NON fare:** trattare RL (FinRL/LSTM-PPO/Ray-PPO), bot a indicatori (StochRSI/EMA/Bollinger),
crypto carry/opzioni (fuori mandato equity), o repo hype (Vibe-Trading 27K★) come alpha. Vedi §5.

---

## 1. Il filtro (come ho razionalizzato)

Ogni item dei tre doc è passato per tre domande:

1. **È alpha o idraulica?** Alpha = un *motivo economico documentato* per cui i rendimenti
   sono positivi al netto dei costi, con sopravvivenza OOS. Idraulica = risk/execution/portfolio/
   backtest/dashboard. Un backtest Sharpe alto senza meccanismo **non è edge** (overfit).
2. **Alembic ce l'ha già?** Molte "raccomandazioni" dei due nuovi doc sono cose già in codice:
   costi realistici nel backtest, vol-scaled stops, sector cap (`_enforce_sector_exposure`),
   drawdown kill-switch, regime_mult, approval flow Telegram, forensic report, cancel-before-sell
   anti-loop. Non le ri-raccomando: le segnalo come *conferma esterna*.
3. **Fitta lo stack reale?** US equities su Alpaca, LLM offline, ciclo giornaliero/15-min,
   long-only unlevered, **niente futures**, opzioni solo via IBKR (adapter dormiente).

Discount applicati sistematicamente: Sharpe/return self-reported → trattati come in-sample fino a
prova OOS; McLean-Pontiff crowding decay (−58% post-pubblicazione) su ogni anomalia; RL e
indicator-fitting → nessun alpha documentato per definizione di metodo.

Le tre ricerche hanno anche **molti duplicati** (pairs trading ×5, insider ×3, VRP/opzioni ×3,
Finnhub-reactivation ×3, event-driven ×4): consolidati in una voce ciascuno.

---

## 2. LANE 1 — ALPHA (nuovo edge ortogonale)

### Tier A — implementa (reale, ortogonale, fattibile ora su Alpaca equities)

#### A1. Revisioni stime analisti / SUE  ⭐ prima mossa
- **Edge + fonte:** Chan-Jegadeesh-Lakonishok (*Momentum Strategies*, earnings-momentum distinto e
  additivo al price-momentum); Jung-Keeley-Ronen (predittività delle revisioni). Meccanismo:
  under-reaction + diffusione graduale dell'informazione analista.
- **Ortogonale a** S1 (price) e S4 (text sentiment): è un delta strutturato di stime.
- **Effort BASSO — conferma incrociata su tutti i doc:** Finnhub è **già integrato**
  (`src/connectors/finnhub_news.py`) ma cabla **solo `api/v1/company-news`** (verificato nel codice);
  gli endpoint estimate/surprise/recommendation sono lì, da accendere. costajohnt/alpaca-trader usa
  già segnali Finnhub in produzione. Riattivazione tracciata come `FINNHUB_INGESTION_ENABLED`.
- **Rischi:** coverage/latenza del tier Finnhub; look-ahead point-in-time sulle revisioni;
  sovrapposizione col trigger-earnings di S4 (misurare IC incrementale).
- **Verdetto: Tier A, priorità #1.**

#### A2. "Lazy Prices" — diff testo 10-K/10-Q anno-su-anno
- **Edge + fonte:** Cohen-Malloy-Nguyen, JF 2020. Chi **cambia** il linguaggio dei filing
  (risk-factor, litigation, MD&A) sottoperforma; i "non-changers" rendono positivo. ~188 bps/mese
  in-sample, **nessun announcement effect** (l'inattenzione è il meccanismo, resiste all'arbitraggio
  perché quasi nessuno diffa i filing interi).
- **Fit:** miglior estensione NLP dello stack S4 — cosine/embedding sui filing, muscolo che S4 ha già.
- **Effort MEDIO-ALTO (correzione onesta vs i doc grezzi):** `src/connectors/sec_edgar.py` prende
  **solo gli hit del full-text-search** (title/form/data/url), **non il corpo del filing**
  (verificato). Serve aggiungere retrieval del documento intero + storage keyed CIK+form+periodo +
  diff section-aware. Non è "diffa quello che già salviamo".
- **Validazione esterna del metodo:** LLM_Alpha, ED-ALPHA e small-cap-signal usano tutti
  **estrazione LLM di feature strutturate su filing 8-K** (polarity/magnitude/event-type/tense/
  specificity/novelty) — stessa famiglia, conferma che l'approccio è vivo.
- **Verdetto: Tier A** — l'edge NLP-native più difendibile per questo sistema.

#### A3. Insider trades — subset "opportunistic" (SEC Form 4) + congressional
- **Edge + fonte:** Cohen-Malloy-Pomorski, JF 2012. Oltre metà degli insider trade sono "routine"
  (stesso mese ogni anno) e **non predicono nulla**; il subset **opportunistic** tiene tutto il
  segnale (~82 bps/mese value-weight). **Il classificatore routine/opportunistic È l'alpha** — è la
  parte che tutti saltano.
- **Consolidamento di 3 fonti:** il mio A3 (Form 4 rigoroso) + Alpatrader (OpenInsider CEO/CFO +
  Senate Stock Watcher congressional, gerarchia segnale 2x/1x/0.5x) + costajohnt (insider via Finnhub).
  → **Congressional trades (Senate Stock Watcher) = add-on ortogonale a costo quasi zero.**
- **Fit:** dati **gratis** da EDGAR (fitta la filosofia "resolver deterministico, non LLM"),
  event-driven, plain equity. Ortogonale a S1/S2/S4.
- **Effort MEDIO:** nuovo form type + parser XML ownership + backfill storia insider per la
  classificazione routine/opportunistic. (Il connector EDGAR attuale non prende Form 4.)
- **Verdetto: Tier A.**

### Tier B — promettente, ma serve dato/strumento/validazione

#### B1. Pairs trading / statistical arbitrage market-neutral  🆕 sleeve nuovo
- **Consolidamento:** appare ovunque — Cointrader (Engle-Granger/Johansen + **Kalman hedge ratio
  dinamico** + walk-forward + FDR), Statistical-Arbitrage-Engine (dual cointegration + OU half-life,
  Sharpe 1.63 OOS *self-reported*), Bayesian-Optimized-Pairs (skopt su Backtrader), davidalv2/pacabot
  (z-score OLS). 
- **Perché conta:** è l'**unica strategia genuinamente market-neutral e ortogonale** a tutto lo stack
  attuale (S1 momentum, S4 news), a basso costo dati (solo prezzi Alpaca). Mean-reversion in Alembic
  esiste solo come *fallback deterministico*, non come sleeve.
- **Note tecniche da adottare:** Kalman hedge ratio dinamico > OLS statico; filtro OU half-life (5–60gg)
  per selezionare coppie tradabili; FDR correction contro il multiple-testing (essenziale: lo screening
  di N² coppie è una fabbrica di falsi positivi).
- **Rischi onesti:** crowded, cost-sensitive, e i Sharpe citati sono in-sample. Serve pipeline di
  screening cointegrazione + validazione OOS seria prima di crederci.
- **Verdetto: Tier B** — miglior candidato "strategia nuova" dopo i tre event-driven.

#### B2. Residual / idiosyncratic momentum (upgrade di S1, lo de-crowda)
- Blitz-Huij-Martens / Blitz-Hanauer-Vidojevic: momentum sui **residui** di una regressione fattoriale
  → ~2× profitto risk-adjusted, **~metà crash risk**, quasi doppio Sharpe. Dato = solo prezzi Alpaca +
  fattori French (free). È un **upgrade di S1**, non net-new alpha, ma riduce crowding/crash. **Tier B.**

#### B3. Quality / gross-profitability tilt (Novy-Marx)
- Gross-profit/assets predice la cross-section ~come book/price, **negativamente correlato al value**.
  Overlay difensivo lento, ortogonale a S1/S4. **Serve un feed fundamentals** (Finnhub `/stock/financials`);
  attenzione point-in-time (no look-ahead su restated). **Tier B.** (Nota: OpenFactor/MultiFactorStockRS
  dai doc grezzi sono il *tooling* per misurarlo, vedi §3.)

#### B4. Filing-tone change (Loughran-McDonald) + 8-K item drift — estensione S4
- Dizionario LM finance-specific + tone *change* YoY + drift per item-type degli 8-K + readability/
  complexity. On-mission (stessi filing dell'EDGAR connector). **Rischio: overlap con S4** → costruirlo
  come segnale *distinto* (tone-change strutturato per-filing) e misurare IC incrementale. **Tier B.**

### Fuori mandato (correzione ai doc grezzi)
- **Crypto carry trade** (funding rates) e **crypto options VRP**: il doc #3 li mette come "Priority 1
  quick win". **Non lo sono**: richiedono integrazione exchange crypto che Alembic non ha e sono **fuori
  dal mandato US-equities**. Sono un *pivot strategico*, non un quick win. Down-rank.
- **Time-series momentum / cross-asset carry / dispersion**: fenomeni **futures/multi-asset**; Alpaca non
  dà futures. Rimandati a un'eventuale era IBKR multi-asset.

---

## 3. LANE 2 — IDRAULICA (risk / execution / portfolio / backtest)

**Regola:** Alembic ha già molta idraulica migliore della media. Qui tengo solo i *veri upgrade* e
segnalo i duplicati di ciò che esiste.

| Risorsa | Cosa aggiunge | Verdetto per Alembic |
|---|---|---|
| **VectorBT** | param-sweep vettoriale ~40–950× più veloce di Backtrader | **ADOTTA** per il research layer (sweep veloce → validazione finale su Backtrader). Convergenza su tutti; già raccomandato. Basso effort. |
| **RiskKit** (`riskkit-quant`, da MMR) | PositionSizer half-Kelly, DrawdownManager tiered, vol-target, inverse-vol | **VALUTA**: Alembic ha già vol-scaled sizing + drawdown kill-switch. Utile come reference per **half-Kelly** (sizing più principiato senza amplificare edge stimato male). Non sostituire ciò che c'è. |
| **PyPortfolioOpt** (HRP, Black-Litterman) | allocazione dinamica S1/S4 vs 50/10 statico | **Tier B/idea**: HRP ha senso *quando ci saranno più sleeve*; con 2-3 strategie il beneficio è sottile. Black-Litterman per foldare le "view" LLM è elegante ma speculativo. Non urgente. |
| **Nautilus Trader** (anti-churn: in-flight checks, fill dedup, retry limits) | logica anti-churn best-in-class | **STUDIA i pattern** contro gli incidenti noti di Alembic (loop reversal #67/#68, cancel-before-sell, 5-SELL senza trace). Non adottare il framework (Rust). Estrarre principi. |
| **Smart Order Router / TWAP-VWAP** | routing multi-venue, riduzione slippage | **PREMATURO**: post-IBKR e a size ben maggiore di ~$110K. Rimanda. |
| **FRTB IMA / VaR-ES Basel** | VaR/Expected Shortfall compliant | **OVERKILL** per un book paper ~$110K. Down-rank; ES può tornare utile solo come metrica di monitoraggio leggera. |
| **Backtesting.py / Bayesian pairs (skopt)** | backtest leggero / tuning bayesiano | Minori; VectorBT copre il bisogno di velocità. Il tuning bayesiano è utile *dentro* B1 (pairs). |

**IBKR — stato reale (correzione al doc #3):** non è "migrazione da pianificare da zero".
`src/brokers/ibkr_adapter.py` (via `ib_insync`) **esiste già, dormiente**, con `get_option_chain`,
dietro l'ABC `BrokerAdapter` — costruito apposta per **S2 (short put SPY/QQQ)**. Manca il pezzo
operativo: **IB Gateway headless nello stack** (pattern ibg-controller/gnzsnz, 2FA/TOTP, health check)
+ dati opzioni reali + wiring esecuzione. Nota: `ib_insync` è deprecato → migrare a **`ib_async`**
(ib-api-reloaded) prima di investirci. Tutti gli item "opzioni/vol/SOR post-IBKR" dipendono da questo
unico programma, non sono quick-win separati.

---

## 4. LANE 3 — DATI, CONNETTORI, GOVERNANCE

**Connettori (convergenza forte tra i doc):**
- **Finnhub reactivation** (`FINNHUB_INGESTION_ENABLED`): oltre a company-news, accendere estimate/
  surprise/insider → alimenta **A1** e **A3**. Standard de-facto in tutti i progetti Alpaca.
- **SEC EDGAR full-text retrieval**: prerequisito di **A2** (oggi solo hit di ricerca).
- **Senate Stock Watcher** (congressional): add-on ortogonale gratis per **A3**.
- **Reddit/social** (SentXStock, social-arbitrage): **crowded/rumoroso**, predice volume/volatilità non
  return risk-adjusted, overlap con S4 → **skip come alpha**; al più flag di crowding (idraulica).
- **Satellite (Sentinel-2, Alternate-Alpha-Generator)**: alt-data esotica, setup Google Earth Engine
  pesante, ROI incerto → curiosità, non priorità.
- **mimic-signal** (PyPI): layer ingestion/event-detection su GDELT/EDGAR/FRED con 10 "weak-signal
  precursors" precostruiti → riusabile come idea di *feature aggiuntiva*, non come sistema.

**Governance — la conferma esterna più preziosa:**
- **costajohnt/alpaca-trader** + blog: **86 decisioni agent loggate in 3 mesi → 0 deploy reali**; cron
  autonomo settimanale disattivato, passaggio a **operatore-in-loop** (brief → sessione Claude locale).
  Più safety rails hardcoded (min 50 trade per cambio parametro, max 2 deploy/settimana, 14gg cooling,
  5% max position, max-loss non disattivabile). **Valida in pieno la direzione di Alembic** (shadow-first,
  F8/regime_scale, operatore approva il merge). Argomento forte per **tenere l'operatore nel loop**.
- **MMR** (Propose→Review→Approve, LLM non tradda diretto) e **Samvid** (consensus multi-agent): stessa
  filosofia human-in-the-loop dell'approval flow di Alembic. Conferma, non novità.
- **Vibe-Trading "Shadow Account"** (trade journal): idea di journaling post-trade — ma Alembic ha già i
  forensic report giornalieri. Estrai l'idea, non il framework da 27K★.
- **LLM_Alpha — la vera lezione metodologica:** walk-forward **purged 5gg + embargo 5gg** (López de
  Prado), sentiment-acceleration (short MA − long MA del polarity), **GICS sector-neutralization**,
  netto di 5 bps round-trip. **Usa questo come template di validazione per A1/A2/A3.** E ricorda il suo
  esito onesto: α non significativo (t +1.35) → il metodo è oro, l'edge va dimostrato sui *nostri* dati.

---

## 5. Da IGNORARE (consolidato, con motivo)

- **RL bots** — FinRL-Trading, LSTM-PPO, Ray-PPO-Transformer (+57% con 30× leva su BTC futures): nessun
  alpha durabile documentato; i framework stessi mettono overfitting/survivorship/basso SNR come problema
  centrale. Sandbox di ricerca al massimo — idraulica che Alembic ha già.
- **Indicator-fitting** — StochRSI/EMA/Bollinger/"auto-optimization" bot: curve-fit senza meccanismo
  economico; le docs di Freqtrade stesse avvisano di non fidarsi dei loro backtest. Zero edge da importare.
- **Raw PEAD standalone** — morto post-2006 per non-microcap (Martineau), coincide col FAIL del vostro
  S7 rimosso. L'evento earnings resta come *trigger* per A1/B4, non come drift-trade.
- **Repo-hype presi alla lettera** — Vibe-Trading (27K★, "462 alpha precostruiti"): estrai componenti,
  non adottare. I "462 alpha" sono formule price/volume decayate stile Alpha101 (utili come *feature
  library*, non come edge live).
- **Sharpe/return self-reported senza OOS/costi/decay** — Stat-Arb 1.63, Ray-PPO +57%, ogni "beat the
  market" di backtest non contaminato: scontati fino a validazione indipendente.
- **TradingAgents / FinGPT come motori di alpha** — buoni per *design* (supervisor/debate) e tooling
  sentiment, ma outperformance = backtest non contaminato, non live OOS. FinGPT movimento 45–53%.

---

## 6. Tabella di priorità consolidata

| # | Item | Lane | Fitta Alembic ora? | Effort | Priorità |
|---|------|------|--------------------|--------|----------|
| A1 | Revisioni analisti / SUE | Alpha | Sì (Finnhub già integrato) | Basso | **1 — fai partire** |
| — | VectorBT (research layer) | Idraulica | Sì | Basso | **2 — quick win** |
| — | Finnhub reactivation (estimate/surprise/insider) | Dati | Sì | Basso | **2 — abilita A1/A3** |
| A3 | Insider opportunistic (Form 4) + congressional | Alpha | Sì (EDGAR free) | Medio | **3** |
| A2 | Lazy Prices — diff 10-K YoY | Alpha | Sì (serve full-text retrieval) | Medio-alto | **3** |
| B1 | Pairs / stat-arb market-neutral (Kalman + OU + FDR) | Alpha | Sì (solo prezzi) | Medio | **4 — sleeve nuovo** |
| — | LLM_Alpha come template di validazione (purged/embargo, IC/ICIR, sector-neutral) | Metodo | Sì | — | **trasversale a A1/A2/A3/B1** |
| B4 | Filing-tone LM + 8-K item drift | Alpha | Sì (misura overlap S4) | Medio | 5 |
| B2 | Residual momentum (upgrade S1) | Alpha | Sì | Basso | 5 |
| B3 | Quality/gross-profitability tilt | Alpha | Serve fundamentals feed | Medio | 5 |
| — | Nautilus anti-churn (studia pattern) | Idraulica | Sì (estrai principi) | — | 6 |
| — | RiskKit half-Kelly / PyPortfolioOpt HRP | Idraulica | Parziale (già ha sizing) | Basso | 6 — valuta |
| — | IB Gateway → sblocca S2 + opzioni | Programma | Adapter già c'è, manca gateway | Alto | programma a parte |
| — | SOR / TWAP-VWAP / FRTB-VaR | Idraulica | No (prematuro/overkill) | — | rimanda |
| — | Crypto carry/options, TS-momentum, cross-asset carry | Alpha | No (fuori mandato) | — | pivot, non ora |
| — | Reddit/social, satellite, RL, indicator-bot | — | No | — | **ignora (§5)** |

---

## 7. Raccomandazione operativa

**Sequenza a basso rischio, ognuno con gate OOS prima di attivare lo scoring (disciplina QX-01):**

1. **Quick wins (settimana 1):** VectorBT nel research layer + Finnhub reactivation. Sbloccano il resto.
2. **Primo alpha nuovo (A1):** segnale revisioni analisti/SUE, validato col template LLM_Alpha
   (purged/embargo walk-forward + IC/ICIR + sector-neutral). Misurare IC incrementale su/oltre S4.
3. **Secondo/terzo alpha (A3, A2):** insider opportunistic (+congressional) e Lazy Prices, in parallelo.
4. **Sleeve market-neutral (B1):** pairs/stat-arb con Kalman+OU+FDR — il candidato "strategia nuova"
   più ortogonale.
5. **Programma separato:** IB Gateway per sbloccare S2/opzioni (migra a `ib_async` prima).

Il prossimo passo naturale è **brainstorming/spec su A1** (feed, coverage-check, forma del segnale,
gate OOS) oppure **grigliarlo** prima (trappole: coverage/latenza Finnhub, look-ahead point-in-time,
overlap col trigger-earnings di S4).

---

## Fonti

I link completi e le schede per-progetto sono nei tre doc sorgente (§ intestazione). Ancoraggi primari
principali riportati qui:

- **Letteratura alpha:** Chan-Jegadeesh-Lakonishok (*Momentum Strategies*); Jung-Keeley-Ronen
  (revisioni); Cohen-Malloy-Nguyen (*Lazy Prices*, JF 2020); Cohen-Malloy-Pomorski (*Decoding Inside
  Information*, JF 2012); Loughran-McDonald (JF 2011); Blitz-Huij-Martens (*Residual Momentum*);
  Novy-Marx (gross profitability, JFE 2013); Martineau (*Rest in Peace PEAD*); McLean-Pontiff (JF 2016).
- **Benchmark sobri:** StockBench (arXiv 2510.02209); FinGPT (arXiv 2306.06031).
- **Progetti-blueprint:** LLM_Alpha (github.com/quangkhaidataka/LLM_Alpha); costajohnt/alpaca-trader +
  jcosta.tech blog; MMR (github.com/9600dev/mmr) + RiskKit; ED-ALPHA; small-cap-signal; mimic-signal.
- **Tooling:** VectorBT (polakowo/vectorbt); PyPortfolioOpt; Cointrader / Statistical-Arbitrage-Engine;
  Nautilus Trader; OpenFactor; Kakushadze *101 Formulaic Alphas*; Microsoft Qlib.
- **Ancoraggio interno (verificato):** `src/connectors/finnhub_news.py` (solo company-news),
  `src/connectors/sec_edgar.py` (solo hit di ricerca, non corpo filing), `src/brokers/ibkr_adapter.py`
  (dormiente, option chain), `src/strategies/{s1,s2,s3,s4}`, `docs/strategies/s2-vrp-theory.md`.
