# Alembic — Review Funzionale Completa

**Data:** 2026-07-03
**Autore:** Claude (sessione di review funzionale read-only)
**Scope:** valutazione di prodotto, architettura funzionale e workflow decisionale — dalla notizia/evento fino all'ordine buy/sell e al monitoraggio post-trade. NON è una code review: qualità del codice, stile, naming e correttezza implementativa riga-per-riga sono fuori scope (coperti da `TECHNICAL_REVIEW_2026-07-02.md`).
**Fonti:** codice (`src/`, `config/`, `scripts/`), beat schedule reale (`src/workers/celery_app.py`), documenti (`ARCHITECTURE.md`, `strategies.md`, `ROADMAP_DATA_ALPHA_2026-07-02.md`, `S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md`, `TECHNICAL_REVIEW_2026-07-02.md`).

---

## Giudizio sintetico (TLDR)

Alembic è un sistema con un'architettura funzionale **sopra la media** — il paradigma Alpha Miner è rispettato davvero, la separazione dei moduli è corretta, la governance sulle promozioni è seria — ma con un problema di prodotto fondamentale: **ha molta più infrastruttura di controllo che alpha**. Oggi è un eccellente laboratorio di validazione costruito attorno a una materia prima — news editoriali aggregate — che i dati interni dimostrano non contenere edge (-$525 su 177 trade, hit-rate 29%, latenza p50 in giorni). Nessuna strategia ha superato un gate di validazione.

La diagnosi interna (pivot event-driven, `ROADMAP_DATA_ALPHA_2026-07-02.md`) è corretta e lucida. Il rischio principale è di **esecuzione fuori sequenza**: si sta già costruendo la fase P2 (worker earnings PEAD, harness backtest S7) mentre i fix P0 della stessa roadmap — spegnere le fonti che perdono soldi — non risultano applicati: MarketAux e RSS sono ancora schedulati nel beat (`src/workers/celery_app.py:140-170`).

---

## 1. Architettura funzionale

### 1.1 Moduli e separazione delle responsabilità

La catena funzionale è pulita e le responsabilità sono separate correttamente:

| Fase | Modulo | Valutazione |
|---|---|---|
| Raccolta dati | `src/connectors/` (GDELT, MarketAux, Alpaca/Benzinga, RSS, SEC EDGAR, Finnhub, macro FRED) | Struttura giusta, contenuto sbagliato (§2) |
| Interpretazione | `src/workers/sentiment.py` + `src/llm/` (ensemble 2 modelli cloud, FinBERT fallback, budget, sanitizzazione) | Solida, con guardrail reali |
| Generazione segnale | `score = polarity × confidence` → Redis (TTL 4h) + PostgreSQL | Semplice e corretta; sottodimensionata (§1.3) |
| Decisione | `PortfolioOrchestrator` weight-then-order, sleeve-local × `allocation_pct` | Design corretto e scalabile |
| Risk | `ConstraintEnforcer` (5 vincoli iterativi), `VolTargeter`, regime multiplier, kill-switch, loss feedback | Ricca ma con parametri incoerenti (§6) |
| Esecuzione | `portfolio_scheduler.py` → Alpaca (market order, bracket TP/SL dove possibile) | Funzionante; race note in parte fixate il 2026-07-02 |
| Post-trade | Riconciliazione fill, `trades`, postmortem, counterfactual, IC/ICIR, decay | Il punto più forte del sistema |

Il vincolo non-negoziabile (LLM mai nel hot path) è rispettato ovunque verificato: l'esecuzione legge solo Redis/PG pre-computati.

### 1.2 Cosa funziona bene

- **Weight-then-order con sleeve-local allocation** è la scelta giusta per scalare a più strategie: aggiungere S5/S6/S7 è un'operazione di config + registry, non di refactor. L'invariante "allocation_pct è l'unica leva di capitale" è chiara e verificata all'avvio.
- **Lifecycle a stati con audit immutabile** (`research → paper → supervised_paper → live`, `strategy_lifecycle_audit`, `GLOBAL_LIVE_PROMOTION_ENABLED=False`) è una governance rara in progetti di questo tipo, correttamente fail-closed.
- **Il loop di auto-miglioramento** (Fase A/B/C: analytics → loss feedback → counterfactual) è concettualmente il pezzo di prodotto più originale.

### 1.3 Cosa è fragile o mal organizzato

1. **Doppio motore di esecuzione ancora vivo.** `execution.engine: portfolio` è il path attivo, ma il legacy `ExecutionWorker` gira ogni 15 minuti (esce subito) con default di fallback *diversi* (B43: se `trading.yaml` non è leggibile, legacy defaulta a `legacy_sentiment` e portfolio a `portfolio` → con config corrotta potrebbero attivarsi **entrambi**).
   *Impatto:* ordini duplicati da due motori. *Proposta:* un solo helper in `src/config.py`, default `disabled`, deprecare `execution.py` come order-sender.
2. **Il segnale è mono-dimensionale rispetto all'architettura che lo circonda.** Tutta la pipeline converge su un solo numero (`score`) con un solo orizzonte implicito (TTL 4h) e una sola direzione utile (long). Lo schema arricchito (`event_type`, `materiality`, `directness`, `risk_flags`, `novelty`) esiste già nel prompt (`sentiment.py:115`) ma **non è usato da nessuna decisione** (il gating è correttamente gated su QX-01, ma nemmeno il routing per `event_type` è wired). L'architettura permette di scalare a più strategie, ma il *segnale* non scala a più ipotesi.
3. **Provenienza persa nel merge.** `ConstraintEnforcer` produce ordini `strategy_id="merged"`: non si può fare enforcement né attribution per sleeve a valle. Per un sistema il cui scopo è capire *quale* strategia genera edge, perdere la provenienza all'ultimo miglio è un difetto funzionale, non cosmetico.
4. **Config sparsa in quattro posti** (trading.yaml, strategies.yaml, workers.yaml *non caricato*, costanti hardcoded nei worker). Non è un problema di stile: è il motivo per cui il drawdown cap vale 5% in un path e 10% nell'altro (§6).

### 1.4 Passaggi mancanti nella catena

- **Event routing** tra interpretazione e strategia (earnings→S7, M&A→dedicato, macro→regime) — oggi tutto finisce indistintamente in S4.
- **Pre-trade check di microstruttura** (spread, halt, liquidità) prima del market order.
- **Protezione da eventi noti** (earnings calendar) per le posizioni S1/S4 — il connector calendar ora esiste (`src/connectors/earnings_calendar.py`) ma serve solo al PEAD, non protegge nessuno.

---

## 2. Fonti informative e dati

Qui sta il problema di prodotto n.1: **monocultura editoriale** (diagnosi già presente nella roadmap interna). Valutazione fonte per fonte, incrociando doc e beat schedule reale:

| Fonte | Stato reale (beat) | Giudizio funzionale |
|---|---|---|
| GDELT GKG | attiva, */15 | Latenza empirica ~7g (dati interni): inutilizzabile per un segnale con TTL 4h. Da spegnere o declassare a contesto |
| MarketAux | **ancora attiva** | 0/20 winner, -$14/trade, cap 100 req/g. FIX-01 (P0) dice di spegnerla: non risulta fatto |
| Alpaca/Benzinga | attiva | L'unica editoriale difendibile: metadata ticker, body completo, latenza minore. Fonte primaria naturale |
| RSS Reuters/CNBC | **ancora attiva** | 0 news in 17 giorni: feed morto che gira ogni 15 min. FIX-02 non applicato |
| SEC EDGAR | disabilitata (bug `ticker_symbol` → 0 segnali *da sempre*) | Rimasta "attiva sulla carta" per mesi producendo zero: sintomo della cecità per-fonte (FIX-04) |
| Finnhub news | shelved (flood 2115 art/fetch) | Decisione giusta |
| Finnhub earnings calendar | **nuova, attiva** (`earnings-pead` hourly) | La mossa giusta: surprise deterministico, no LLM, no NER |
| FRED/yfinance macro | attiva (regime) | OK ma povera: solo VIX + T10Y2Y + SPY EMA20 |

### 2.1 Risposte puntuali

- **Le fonti sono corrette/sufficienti?** No. Sono tutte della stessa classe (editoriale aggregato) e la classe è quella sbagliata per l'orizzonte tattico del sistema. Il problema non è "poche fonti" ma **zero diversità di classe**: mancano completamente dati primari (filings funzionanti, transcript, consensus, insider, rating changes) — esattamente ciò che un LLM interpreta meglio di un fattore numerico.
- **Il sistema distingue news rilevanti / rumor / price-sensitive?** Ha i campi per farlo (`risk_flags: rumor`, `materiality`, `novelty`) ma **non li usa in nessuna decisione**. Oggi un rumor con polarity alta e un 8-K ufficiale pesano uguale. Il gating è correttamente bloccato su QX-01, ma finché QX-01 non avanza (17/148 annotate all'ultimo dato) il sistema resta funzionalmente cieco alla qualità dell'informazione.
- **Deduplicazione:** wired solo `is_duplicate_by_id` (per URL+ticker); il **content-hash cross-source non è mai chiamato** (`deduplicator.py:66`, nessun call-site). Stesso articolo da 3 fonti = 3 inferenze LLM = 3 segnali che si sovrascrivono. È token sprecato *e* un bias di conferma artificiale (la stessa notizia "vota" tre volte).
- **Freshness:** esiste uno skip a 12h sull'età della news in inferenza (`sentiment.py:53`), ma 12h è incoerente con un TTL segnale di 4h e con l'ipotesi di trading tattico. E la freshness *decisionale* (portfolio) guarda l'età del *segnale*, non della *notizia*: una news di 11h processata ora produce un segnale "fresco". FIX-03 è il singolo fix a più alto ROI del backlog.
- **Scoring/priorità fonti:** implementare EN-04/EN-06 come già scritti (priorità Alpaca > resto, funnel per-fonte persistito) e aggiungere un **source trust score** dinamico: IC rolling per fonte che scala `confidence` a monte del segnale, con auto-quarantena. Le soglie di rimozione della roadmap (§7.4) vanno bene, ma vanno *eseguite da codice*, non da un umano che ricorda di guardare la dashboard.

### 2.2 Segnalazione non presente in altri documenti

L'aggiunta a watchlist del 2026-06-30 ("off-watchlist names with recurrent strong ensemble signals: ROKU, RDDT, HOOD, WDC, SPCX") è **selezione sull'intensità del segnale, non sull'edge del segnale** — il meccanismo con cui un sistema si auto-rinforza sul rumore. Se un nome genera segnali forti ma IC nullo, aggiungerlo peggiora il portafoglio. Criterio corretto: aggiungere solo nomi con IC per-simbolo positivo misurato.

---

## 3. Workflow end-to-end

### 3.1 Ingestione (connectors → `news:queue`)

- **Bene:** multi-fonte, per-ticker fan-out, dedup by-id, QT-01 (mai più watchlist fallback).
- **Fragile:** nessun `discarded_reason` persistito → gli scarti sono invisibili (FIX-06); il WebSocket news stream accoda un task sentiment per ogni articolo (storm su burst, B35).
- **Manca:** content-hash dedup; priorità tra fonti.
- **Falso negativo tipico:** news importante scartata per ticker non estratto — nessuno se ne accorge perché lo scarto non è loggato.

### 3.2 Normalizzazione / ticker

- **Bene:** la parte più matura del sistema. Sanitizzazione anti prompt-injection, cashtag guard, resolver deterministico con evidence pesata (SEC + OpenFIGI + alias) in shadow mode, provenance `extraction_method`. La scelta "measurement before enforcement" è giusta.
- **Rischio pratico:** baseline misurata **precision 0.24** — tre ticker su quattro estratti sono sbagliati. Finché l'enforcement non si attiva, il worst-case error (ordine su titolo sbagliato) resta *possibile ogni giorno di paper*.
- **Proposta:** attivare l'enforcement del resolver **prima** del completamento di QX-01, in modalità conservativa (solo `NO_TRADE_NOT_TRADABLE` e `NO_TRADE_LOW_CONF` con soglia altissima): il costo dei falsi scarti è trascurabile rispetto al costo di un ordine su entità sbagliata.

### 3.3 Interpretazione (LLM)

- **Bene:** DK-CoT, JSON schema, divergence check → FinBERT, budget cap, batch cap alzato 4→12 (commit `c305f74`).
- **Fragile:** 39-48% dei segnali è near-zero → metà dei token compra rumore; la mitigazione (skip MarketAux |sent|<0.2) cura il sintomo sulla fonte peggiore.
- **Manca:** short-circuit *pre*-LLM (FinBERT come triage: se FinBERT dice neutro con alta confidenza, non chiamare l'ensemble cloud — è l'inverso del fallback attuale e taglierebbe ~40% dei costi).
- **Dove si sbaglia:** l'ensemble di 2 modelli con divergence su std è statisticamente povero: con n=2 la "deviazione standard" è solo |a−b|/√2; tre modelli con voto mediano sarebbero molto più robusti allo stesso costo marginale.

### 3.4 Generazione segnale → validazione

- **Bene:** la catena di gate documentata (freshness → prefilter → feedback threshold → top-N) è chiara e la preferenza ensemble-over-fallback è corretta.
- **Incoerenza funzionale:** TTL 4h e freshness sul `generated_at` con news fino a 12h → l'orizzonte informativo effettivo arriva fino a ~16h dall'evento, su una watchlist large-cap dove il mercato prezza in minuti. **È qui che nascono i falsi positivi sistematici: si compra su informazione già prezzata.**
- **Proposta:** freshness sull'event-time (`published_at`), soglia ≤ 2h per il path tattico.

### 3.5 Decisione / sizing

- **Bene:** merge per allocation, constraints iterativi, vol targeting wired (verificato: `strategy_returns` passato a `run_cycle`, `portfolio_scheduler.py:1136-1145`), regime multiplier, hold-minimum 90 min + exit persistence 2 cicli (anti-churn ben pensato).
- **Fragile:** top-5 equal-weight butta via l'informazione di intensità del segnale appena validata; il regime multiplier è un singolo scalare giornaliero (07:00 + retry 13:30) — un crash intraday alle 16:00 non cambia il sizing fino al giorno dopo (il kill-switch VIX copre solo l'estremo).
- **Manca:** sizing proporzionale a score×IC; qualunque nozione di convessità di costo (un segnale marginale su un titolo illiquido e uno forte su AAPL pesano uguale).

### 3.6 Ordine

- **Bene:** market order con bracket TP/SL dove il titolo non è frazionabile, idempotenza S4 fail-closed, lock ciclo tokenizzato (B26/27/28 fixati il 2026-07-02).
- **Fragile:** stop-loss **sintetico** per i frazionabili: valutato sullo snapshot prezzi del ciclo, ogni 15 min, solo 14-21 UTC (B44).
- **Edge case scoperto:** gap-down all'open, halt di trading, crash del worker = posizioni senza protezione.
- **Manca:** controllo pre-ordine su spread/halt; limit order o marketable-limit per i nomi meno liquidi.

### 3.7 Post-trade

- **Bene:** best-in-class del progetto (riconciliazione intraday, `trades`, postmortem a 10 categorie, counterfactual sui trade saltati).
- **Bug funzionale concreto:** il beat `reconcile-fills-evening` punta a `run_daily_report` invece che alla riconciliazione (`celery_app.py:88-91`, B20 — ancora presente, verificato) → fill serali riconciliati solo il giorno dopo, e `qty` NULL può propagare P&L NULL nel loss-feedback.
- **Manca:** misura sistematica dello slippage realizzato vs stimato (il campo `slippage_est` esiste; manca il confronto con l'effettivo).

---

## 4. Strategie di trading

### 4.1 Stato reale

| Strategia | Allocazione | Stato | Nota funzionale |
|---|---|---|---|
| S1 momentum multi-lookback | 50% | supervised_paper | Backtest **invalidato** dalle sue stesse note (same-bar fill, survivorship, zero costi, regime hindsight, walk-forward decorativo) |
| S4 news tactical | 10% | promotion_blocked | IC>placebo mai confermato; perde soldi in paper |
| S2 VRP proxy | 0% | research | OOS Sharpe −0.55, correttamente spenta |
| S3 residual momentum | 0% | research | Gate falliti |
| S7 PEAD | 0% | research/contenuta | Costruita ma finora *a secco di dati*; ora in rifornimento con Finnhub |
| S5 crypto, S6 macro | — | solo roadmap | Non costruite |

**Giudizio:** le strategie *presenti* sono sensate come disegno, ma il portafoglio effettivo è: una strategia momentum con backtest inattendibile al 50% + un overlay news che perde soldi al 10% + 40% cash. La diversificazione per *stile* è assente: S1 e S4 sono entrambe long-only, entrambe sullo stesso universo mega-cap USA, entrambe trend/momentum-flavored. In un regime risk-off correlano verso 1.

### 4.2 Logica "quando NON tradare"

C'è ed è sopra la media — regime multiplier, feedback threshold dinamico, hold minimum, exit persistence, kill-switch multipli, SKIP_* tassonomizzati — ma è tutta *reattiva* (dopo le perdite) o *macro* (VIX). Manca il "non tradare" *ex-ante* informato dall'evento: blackout earnings, esclusione rumor, filtro already-priced (`novelty` c'è nello schema, non è usata).

### 4.3 Filtri

- Liquidità/spread: di fatto delegati alla watchlist large-cap (accettabile oggi, salta appena si va su small/mid per il PEAD — va costruito *prima* di quell'espansione).
- Orario di mercato: gestito.
- Correlazione: cluster cap 0.70 nel ConstraintEnforcer — bene.
- Rischio evento: assente.

### 4.4 Strategie da aggiungere (in ordine di coerenza col sistema)

1. **S7 PEAD small/mid-cap** — input: Finnhub surprise + transcript tone; logica: BUY beat>5% + tone positivo, hold 20d; rischio: liquidità; validazione: gate ALPHA-A5 (drift ≥1.5%, hit>55%) con split cap già previsto.
2. **S8 Insider (Form 4)** — input: EDGAR Form 4 RSS, filtro open-market purchase non-10b5-1, cluster di ≥2 insider; logica: BUY, hold 60d, sleeve ≤5%; rischio: rumore da exercise (filtro rigido); validazione: excess return vs settore, n≥100.
3. **S9 Guidance/8-K multi-evento** — input: 8-K item 7.01/8.01 + transcript; l'LLM classifica direzione guidance; il compito dove l'LLM ha edge genuino; validazione: concordanza ≥80% con surprise + IC su label set.
4. **S10 Earnings-reversal difensivo** — il duale del PEAD: *ridurre/uscire* da posizioni S1 nei 2 giorni pre-earnings (ALPHA-A1). Non genera alpha, taglia una coda nota. Quasi gratis dato che il calendar esiste già.
5. **S11 Revisions momentum (ALPHA-D1)** — BUY su revisione EPS up + rating upgrade, hold 20d; alimenta lo stesso meccanismo del drift.
6. **S5 Crypto momentum** (già a roadmap) — valore vero: decorrelazione dall'universo equity USA e mercato 24/7 dove la pipeline news gira anche quando NYSE è chiusa.
7. **S6 Sector rotation macro** — usare il regime detector esistente per tilt su ETF settoriali: riusa infrastruttura, aggiunge uno stile non-news.
8. **Short/hedge overlay** — oggi la polarity negativa produce solo reversal-exit. Anche solo "riduzione beta quando la media dei segnali negativi supera soglia" monetizzerebbe metà della distribuzione del segnale che oggi viene buttata.

**Sconsigliato** (concordando col REJECT della roadmap): social sentiment come alpha primario, options flow come segnale primario, altre fonti editoriali premium.

---

## 5. Alpha discovery

**I binari ci sono quasi tutti, il treno no.** Il sistema *può già*: misurare IC/ICIR per modello (Newey-West, LOO), rilevare drift (PSI+CUSUM) e decay (actual vs baseline), fare postmortem categorizzato delle perdite, misurare il costo-opportunità dei trade saltati (counterfactual — ben disegnato e funzionalmente raro da vedere), analytics per simbolo/regime/ora/score-bucket/hold-time, e ha un model tournament per gli LLM. È una base di alpha-*measurement* eccellente.

### 5.1 Cosa manca perché diventi alpha-*discovery*

- **Attribution per fonte e per event_type.** L'IC è calcolato per *modello*, non per *fonte* né per *tipo di evento*. Le due dimensioni dove vive l'ipotesi di alpha ("i filing battono gli editoriali", "earnings > product news") non sono misurabili oggi. FIX-04/FIX-05 sono esattamente questo — priorità massima.
- **Clustering di eventi simili:** non esiste. Con `event_type` + embedding dei titoli (costo trascurabile) si può costruire "reazione attesa vs realizzata per cluster di eventi".
- **Reazione attesa vs reale:** esiste solo per i *segnali* (forward_return vs score) e per gli *skip* (counterfactual). Manca a livello di *evento*: "il mercato ha già mosso il prezzo prima che il segnale arrivasse?" — il test diretto della tesi already-priced.
- **Generazione di ipotesi:** zero automazione. Asset insolito disponibile: la sessione Claude Code giornaliera già schedulata (07:00 CEST, citata in `celery_app.py:221`) è il posto naturale per un loop semi-automatico.

### 5.2 Workflow concreto di alpha discovery (semi-automatico, incrementale)

1. **Nightly (deterministico):** job che scrive `alpha_attribution` — IC e P&L rolling 30/60/90g per {fonte × event_type × score-bucket × market-cap-bucket × latenza-bucket}. Tutto dai dati già in PG.
2. **Weekly (LLM offline):** un worker legge quella tabella + i postmortem + i counterfactual e produce 3-5 *ipotesi strutturate* in una tabella `alpha_hypotheses` (formato: condizione, direzione, orizzonte, evidenza, backtest proposto). L'LLM propone, mai decide.
3. **Gate umano:** il PO promuove un'ipotesi → viene generato un backtest con l'harness esistente (`src/backtest/` + gates 1-5) su holdout.
4. **Decay loop:** il DecayMonitor esiste già; va esteso a chiudere il ciclo — un fattore che decade sotto soglia genera automaticamente una *ipotesi di rimozione* nella stessa coda.

Questo trasforma componenti già costruiti in un ciclo, con costo di sviluppo basso.

---

## 6. Risk management

**Il processo ha più controlli della media dei sistemi retail** (kill-switch multi-trigger con recovery OTP e cooldown, drawdown cap, constraint a 5 passaggi, HHI/correlation monitor, loss feedback con TTL 48h — il TTL sugli aggiustamenti è un dettaglio raffinato). Il problema non è la quantità: è la **coerenza e la copertura temporale**.

Problemi ordinati per gravità:

1. **Parametri incoerenti tra config/codice/doc** (B13/B14/B18): drawdown cap 5% in config ma 10% hardcoded nel path attivo; exposure 50% config vs 95% doc; stop-loss 2% config vs 5% doc.
   *Perché conta:* il risk management esiste solo se i numeri sono quelli che credi. *Rischio pratico:* il path attivo tollera il doppio del drawdown dichiarato. *Proposta:* una sola sezione `risk:` in `trading.yaml`, letta da un solo loader, loggata all'avvio, con un test che fallisce se un worker hardcoda un valore.
2. **Buco di copertura overnight/gap.** Stop sintetico ogni 15 min solo in market hours; niente stop broker-side sui frazionabili; il take-profit bracket esiste solo per i non-frazionabili.
   *Rischio pratico:* gap-down dell'8% all'open su una posizione S4 → perdita 4× lo stop nominale. *Proposta:* stop-loss order broker-side sempre (rinunciando al frazionamento sulle posizioni S4, che sono 2% NAV — arrotondare a share intere costa meno del buco di protezione).
3. **NAV sbagliato nel risk monitor** (B48: somma di P&L, non equity). Drawdown, Sharpe ed esposizione calcolati su denominatore errato → gli alert di rischio più importanti sono quantitativamente inattendibili.
4. **Rischio per settore/strategia dichiarato ma non enforceable a valle** (provenienza "merged", §1.3).
5. **Overtrading/duplicati/revenge:** ben coperti (idempotenza fail-closed, anti-pyramiding SKIP_POSITION, hold-minimum, cooldown 4h del feedback — che è l'anti-revenge-trading algoritmico nella direzione giusta: *alza* la soglia dopo le perdite invece di abbassarla).
6. **Controlli pre-ordine:** kill-switch re-check, quantità/fractionable, notional cap — ci sono; manca la microstruttura (spread/halt). **Post-esecuzione:** riconciliazione c'è ma con il bug B20; divergence alert (Jaccard segnali/ordini) è un'ottima idea già attiva.

---

## 7. Valutazione operativa

**Oggi Alembic è adatto a: paper trading supervisionato. Punto.** E il sistema *lo sa* — l'intera catena di autorizzazioni è correttamente bloccata. Non è pronto per trading assistito (le metriche esposte all'operatore hanno bug di attendibilità: NAV, scheduler endpoint stale, API strategie con valori hardcoded "validated") né ovviamente per automatico.

### 7.1 Cosa manca per l'affidabilità in produzione (in ordine)

1. Una strategia con edge dimostrato — tutto il resto è secondario.
2. Coerenza dei numeri di risk (§6.1).
3. Chiusura dei fix di sicurezza già elencati nella technical review (JWT, XSS, kill-switch resume).
4. Osservabilità per-fonte (senza, ogni discussione sulle fonti resta aneddotica).
5. Guard esplicito paper/live all'avvio.

### 7.2 Metriche da monitorare

Le prime cinque non esistono ancora:

1. IC per fonte
2. Latenza `published_at→signal` p50/p95 per fonte
3. Slippage realizzato vs stimato
4. % segnali near-zero (costo/rumore LLM)
5. Funnel scarti per motivo (`discarded_reason`)
6. Più le esistenti: drawdown, HHI, fill ratio, divergence, feedback threshold, budget LLM

### 7.3 Dashboard e alerting

- **Dashboard:** ne esistono già molte (Overview, Quality, Auto-Improve, Grafana). Ne manca una sola davvero: **Source P&L funnel** (FIX-04) — news→segnale→decisione→trade→P&L per fonte.
- **Alerting da aggiungere:** degrado-fonte (EN-07); fallimento regime task (oggi il fallback ×0.2 è silenzioso e ha già tenuto il deployment al 10% per giorni — episodio documentato); riconciliazione fallita.

---

## 8. Backtesting e validazione

L'infrastruttura è **sorprendentemente completa sulla carta**: engine event-driven con data replay, order simulation, costi realistici (impact model, spread tiers), 5 gate (significatività, walk-forward, robustness, regime, stress), DSR, harness forward-return da Alpaca point-in-time (scelta corretta, R-09).

Tre problemi funzionali però la svuotano in parte:

1. **I gate hanno soglie a 0.0** (`min_sharpe=0.0`) — passano quasi tautologicamente (B12). Un gate che non può fallire non è un gate. Le soglie del master roadmap (Sharpe>0.5, hit>55%, DD<15%) vanno messe *nel codice dei gate*, non nei documenti.
2. **Il backtest di S1 — la strategia col 50% del capitale — è dichiarato invalido dalle sue stesse note di config** (same-bar fill = look-ahead, survivorship, zero costi, regime hindsight, walk-forward decorativo, DSR n_trials=1). L'infrastruttura anti-look-ahead esiste, ma la strategia principale non l'ha mai attraversata. La rigenerazione PIT del backtest S1 è più urgente di qualsiasi nuova feature.
3. **Il delay delle news nel backtest S4** è stato sistemato solo di recente (QS-07: `_signals_as_of` con `max_signal_age_hours`) — giusto — ma il backtest S4 resta costruito su segnali storici la cui *latenza di ingestione* reale (quando la news sarebbe stata *nel sistema*) non è modellata: `raw_ingested_at` (EN-05) serve anche a questo, non solo alla telemetria.

Il nuovo harness S7 (`scripts/backtest_s7_pead.py`) è metodologicamente ben fatto: ingresso il giorno *dopo* l'annuncio, split large/small cap, gate quantitativo esplicito. È il template giusto per tutti i POC futuri.

### 8.1 Pipeline seria di evaluation

```
dati PIT (raw_ingested_at obbligatorio)
    → backtest con costi realistici + latenza di ingestione simulata
    → gate 1-5 con soglie reali
    → paper shadow (segnali loggati, zero ordini) 30g
      con confronto IC backtest-vs-shadow
    → paper con capitale
    → gate report
    → promozione
```

I pezzi esistono tutti; manca il confronto shadow-vs-backtest come passaggio formale.

---

## 9. Priorità

### 9.1 I 10 problemi funzionali più importanti (per impatto)

| # | Problema | Proposta |
|---|---|---|
| 1 | **Materia prima senza alpha ancora in produzione** — MarketAux+RSS+GDELT girano nel beat nonostante P&L negativo dimostrato | Applicare FIX-01/02 oggi (rimozione dal beat, 2 righe) |
| 2 | **Freshness sull'età del segnale, non dell'evento** (FIX-03) — si compra informazione già prezzata; causa strutturale del hit-rate 29% | Freshness su `published_at`, soglia ≤2h per il path tattico |
| 3 | **Precision estrazione ticker 0.24 senza enforcement** — worst-case error possibile ogni giorno | Enforcement conservativo del resolver subito, calibrazione fine dopo QX-01 |
| 4 | **Parametri di rischio incoerenti** (5% vs 10% drawdown, ecc.) | Unica sezione `risk:`, unico loader, test anti-hardcode |
| 5 | **Backtest S1 invalido con 50% dell'allocazione** | Rigenerazione PIT prima di qualsiasi nuova feature |
| 6 | **Nessuna attribution per fonte/evento** (FIX-04/05) — il sistema non può imparare quale input ha valore | Funnel + IC per fonte, blocco dell'intero loop di discovery |
| 7 | **Content-hash dedup non wired** (EN-03) — token sprecati e triplo conteggio della stessa notizia | Wire `is_duplicate()` cross-source pre-inferenza |
| 8 | **Protezione stop overnight assente sui frazionabili** | Stop broker-side sempre (share intere per S4) |
| 9 | **QX-01 fermo a 17/148 annotazioni** — collo di bottiglia dichiarato di *tutto* | Decidere budget/outsourcing annotazione: più importante di qualunque feature |
| 10 | **Gate di backtest con soglie zero + `reconcile-fills-evening` puntato al task sbagliato** | Soglie reali nei gate; fix del beat task |

### 9.2 Le 10 opportunità più interessanti

1. Finnhub earnings surprise già wired → sbloccare S7 col gate ALPHA-A5 (a un backtest di distanza).
2. Schema segnale arricchito già in produzione (`event_type`, `materiality`…) → routing e gating quasi gratis una volta misurato.
3. Resolver deterministico già costruito e in shadow → enforcement = flip di flag + soglie.
4. Sessione Claude Code giornaliera → sede naturale del loop di alpha hypothesis (§5.2).
5. Counterfactual engine unico nel suo genere → estenderlo dagli skip agli *eventi* (reazione attesa vs reale).
6. FinBERT locale gratuito → triage pre-LLM per tagliare ~40% dei costi cloud.
7. Regime detector esistente → riuso diretto per sector rotation (S6) senza nuova infrastruttura.
8. Transcript earnings (FMP/Polygon) → il compito dove l'LLM ha edge *vero* e competizione bassa.
9. Mercato crypto 24/7 (Alpaca già lo supporta) → la pipeline news gira anche a mercato USA chiuso: capacità oggi sprecata.
10. Model tournament + LOO-ICIR → estendibile da "quale LLM" a "quale prompt/schema" (A/B di prompt con IC come metrica).

### 9.3 Le 10 fonti dati/news da aggiungere (in ordine)

1. Consensus EPS/revenue (FMP o Finnhub — in parte fatto) — carburante S7
2. Earnings call transcripts (FMP/Polygon)
3. SEC EDGAR riparato: 8-K multi-evento (M&A, guidance, going-concern)
4. Form 4 insider transactions (EDGAR RSS, free)
5. Analyst revisions/price target changes (FMP/Tipranks)
6. Earnings calendar prospettico come *protezione* (blackout S1/S4)
7. Comunicati IR primari (PR Newswire/BusinessWire feed diretti — event-time vero, non aggregato)
8. 13F institutional changes (lento, uncrowded)
9. Credit spreads + put/call ratio (FRED/CBOE) per arricchire il regime detector
10. Short interest/borrow fee (FINRA) come filtro contrarian/squeeze

*Esplicitamente no: social sentiment, altre fonti editoriali premium — in accordo col REJECT della roadmap.*

### 9.4 Le 10 strategie da aggiungere/migliorare

1. S7 PEAD → validare su small/mid (gate A5)
2. S1 → rigenerare backtest PIT + protezione earnings calendar
3. S4 → freshness event-time + solo fonte primaria (Benzinga/filing), sizing proporzionale a score invece di equal-weight
4. S8 Insider Form 4 (nuova)
5. S9 Guidance/8-K event-driven LLM (nuova)
6. S10 Earnings-blackout difensivo (nuova, quasi gratis)
7. S11 Revisions momentum (nuova)
8. S6 Sector rotation da regime (roadmap esistente)
9. S5 Crypto momentum (roadmap esistente, per decorrelazione)
10. Short/hedge overlay sui segnali negativi (oggi usati solo per uscire)

### 9.5 Roadmap in 3 fasi

**Breve termine (1-3 settimane) — "smetti di perdere, inizia a misurare"**
- FIX-01/02: spegnere MarketAux/RSS
- FIX-03: freshness event-time
- Enforcement conservativo resolver
- Sblocco QX-01 (decisione budget annotazione)
- Unificazione parametri risk
- Fix `reconcile-fills-evening`
- EN-03: dedup content-hash
- Run del backtest S7 (gate A5)

**Medio termine (1-2 mesi) — "pivot event-driven e attribution"**
- FIX-04/05: funnel e P&L per fonte
- EN-05/06: campi DB + ingestion stats
- Consensus + transcript wired
- S7 in paper se il gate passa
- Blackout earnings per S1
- Rigenerazione backtest S1 PIT
- Gate con soglie reali
- Stop broker-side
- POC Form 4

**Lungo termine (3-6 mesi) — "loop di discovery e diversificazione"**
- Workflow alpha hypotheses (§5.2)
- Espansione universo small/mid con filtri liquidità
- S5/S6/S11
- Short overlay
- Shadow-vs-backtest come passaggio formale di promozione
- Valutazione go-live solo se almeno una strategia supera i gate con evidenza paper ≥90 giorni

---

## 10. Cosa non è verificabile dal repository

- I numeri di P&L paper (-$525/177 trade, hit-rate 29%, latenze p50, 0/20 MarketAux) vengono dai documenti interni di review, non da query sul DB vivo — trattati come attendibili ma non riprodotti in questa sessione.
- Lo stato runtime reale: chiavi Redis, regime corrente, avanzamento annotazioni oltre il 17/148 documentato, costi Ollama effettivi.
- L'eventuale disattivazione *operativa* di MarketAux/RSS via env/compose override (nel beat schedule risultano schedulate).

Per verificare questi punti servirebbe accesso ai container e al DB operativo (`alembic-postgres-1` / `alembic-redis-1`).

---

## Nota finale (product strategist)

La cosa più preziosa che Alembic ha costruito non è nessuna delle strategie — è la **macchina di validazione** (gates, lifecycle, labeling, IC, counterfactual). La tentazione da evitare nei prossimi mesi è aggiungere l'ennesima fonte o strategia prima di aver fatto passare *una sola cosa* attraverso quella macchina fino in fondo. S7 con il carburante Finnhub è il candidato giusto, ed è a un backtest di distanza dal primo verdetto onesto del sistema su se stesso.
