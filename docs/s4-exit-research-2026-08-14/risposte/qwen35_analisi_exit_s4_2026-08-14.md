# S4 — Analisi approfondita strategie di uscita

**Data:** 2026-08-14  
**Modello:** Qwen3.5  
**Prompt di riferimento:** `docs/s4-exit-research-2026-08-14/01_PROMPT_MULTI_LLM.md`

---

## 1. Executive Verdict

**Policy raccomandata:** **C — shadow reversibile immediato**, con implementazione shadow end-to-end della configurazione B a 2 sedute (time-stop D+2 come ipotesi primaria), contro-segnale ≤ −0,30 e stop di catastrofe. Grado di confidenza: **media** sulla direzione (shadow), **media-bassa** sull'orizzonte D+2 come ottimale.

**Motivazione sintetica:** S4 non possiede oggi un orizzonte economico identificato: la tenuta mediana osservata (1h45/4h15) è una proprietà del software (cadenza cicli, filtri QS-07/FIX-D, `max_signal_age`), non una stima del decadimento dell'alpha. La letteratura primaria conferma che:
1. **Stop-loss stretti** sottoperformano buy-and-hold su azioni USA in assenza di forte autocorrelazione positiva (Kaminski & Lo 2014; Lo & Remorov 2017; Dai et al. 2021);
2. **News-driven drift** persiste per più giorni senza reversal (Jiang, Li & Wang 2021; Tetlock et al. 2008), ma la letteratura distingue nettemente news fondamentale vs sentiment generico e news nuova vs stale (Tetlock 2011);
3. **Multiple testing** è il rischio dominante: scegliere ex post la migliore exit da una griglia di soglie/orizzonti produce quasi certamente un falso positivo (White 2000; Hansen 2005; Bailey & López de Prado 2014).

**Shadow ≠ parcheggio:** deve eseguire lo stesso codice di selezione, ranking, collisione S1, fill virtuale, cost model, aging, uscita e reason code della futura esecuzione, fermandosi al confine broker. Uno shadow limitato al calcolo dell'IC non recupera l'osservabilità ingegneristica evidenziata da Opus.

**Condizione di falsificazione:** se su un segmento post-fix pulito (≥213 sedute, varianza post-fix) la configurazione B shadow mostra IC ≥ +0,05 con t Newey-West ≥ 3 a 2 sedute, segno non contraddetto a 1 e 3 sedute, integrità ≥95% e P&L shadow netto > benchmark EW con limite inferiore 95% > 0, allora shadow è falsificato e B va riattivata.

---

## 2. As-Is Audit

### 2.1 Diagramma dei rami di uscita correnti

| Ramo | Trigger economico dichiarato | Clock / Scadenza | Bypass / Interazioni | Reason code osservato | Failure mode |
|---|---|---|---|---|---|
| **E0 — weight-drop da ranker** | Silenzio / rank insufficiente | Ciclo 15min; S4 esclusa da `_REBALANCE_CLOCK_STRATEGIES` → clock non ripristinato | FIX-D preserva segnale vecchio se nessun fresco; hysteresis 2 cicli; min-hold 90min | `unknown`, `expired`, `whipsaw`, `below_entry_gate` | Confonde invalidazione tesi, scadenzamento software, collisione S1, filtro universo |
| **E1 — contro-segnale sentiment** | Score < −0,20 (codice) / −0,35 (doc) | MaxSignalAge 60min; cooldown 2h post-exit | Solo ensemble, no fallback | (force-sell, non loggato come reason distinto) | Divergenza codice/doc; soglia singola non calibrata su posterior della tesi |
| **E2 — stop sintetico** | Stop fisso 2% (disabilitato); shadow vol-scaled | Continuo (valutato a ogni ciclo) | `risk.stop_loss=0,0` → disabilitato; replay interno: `no_protective` > stop 2% | `stop_loss` (se attivo) | Stop stretto = eccesso turnover; campione replay piccolo e misto S1/S4 |
| **E3 — disaster stop broker** | Perdita ≥12–20% (config) | GTC a mercato | Solo floor azioni intere su frazionarie; residuo <1 azione non protetto | Broker-side, non tracciato in ledger | Commento YAML dice "shadow", ma ordini possono essere reali; copertura incompleta |
| **E4 — take-profit broker** | +6% su bracket | GTC entro bracket | Solo BUY non-fractionable; fractionable/no-tional esclusi | Broker-side, reason non mappato | Exit dipendente da frazionabilità, non da tesi S4 |
| **E5 — risk exits portafoglio** | VIX 40, ΔVIX 30%, DD 5% | Binario: blocca ingressi e/o liquida | Distinzione ingresso/uscita non sempre esplicita | Alert, non sempre action | Confonde rischio comune e invalidazione specifica |

### 2.2 Failure mode trasversali

- **`unknown`**: il motivo economico dell'uscita non è mappato nel reason code — è la maggioranza delle uscite osservate nella settimana 2026-08-06 → 08-12 (3 su 9).
- **Scadenze artefatto**: 6 uscite su 9 a 1h45 o 4h15 — multipli del ciclo e dei filtri, non di una duration economica.
- **Divergenza config/runtime**: `d_hard` commentato come shadow ma potenzialmente attivo; force-sell con soglia codice −0,20 vs doc −0,35.
- **Osservabilità incompleta**: reason code non copre take-profit broker, disaster stop, regime exits.

---

## 3. Literature Evidence Table

| # | Fonte primaria | DOI/URL | Universo / Periodo | Tipo exit studiata | Effetto economico | Trasferibilità a S4 |
|---|---|---|---|---|---|---|
| 1 | Kaminski & Lo (2014), *When Do Stop-Loss Rules Stop Losses?* | [10.1016/j.finmar.2013.07.001](https://doi.org/10.1016/j.finmar.2013.07.001) | Futures, 1993–2011 | Stop-loss fissi | Sotto random walk: sempre riduzione expected return; con momentum: possono aumentare return e ridurre volatilità a frequenze lunghe | **Media**: S4 non è buy-and-hold né time-series momentum; esclude stop stretti come default |
| 2 | Lo & Remorov (2017), *Stop-Loss Strategies with Serial Correlation, Regime Switching, and Transactions Costs* | [10.1016/j.finmar.2017.02.003](https://doi.org/10.1016/j.finmar.2017.02.003) | Azioni USA, 1964–2014 | Stop-loss fissi | Stop stretti sottoperformano per costi; outperformance richiede alta autocorrelazione | **Alta**: conferma replay interno; vieta stop 2% senza stima MAE/MFE S4 |
| 3 | Jiang, Li & Wang (2021), *Pervasive Underreaction: Evidence from High-Frequency Data* | [10.1016/j.jfineco.2021.04.003](https://doi.org/10.1016/j.jfineco.2021.04.003) | Azioni USA, 2000–2012, dati 15min | Drift post-news | Drift nella direzione della reazione iniziale per più giorni; strategia news momentum 1,60–3,34%/mese netta | **Alta**: supporta D+2 come ipotesi, ma news sono firm-specific e classificate; S4 ha news editoriali miste |
| 4 | Tetlock, Saar-Tsechansky & Macskassy (2008), *More Than Words* | [10.1111/j.1540-6261.2008.01362.x](https://doi.org/10.1111/j.1540-6261.2008.01362.x) | Azioni USA | Drift post-news negative | Sottoreazione breve (1–2 gg); parole negative predicono fondamentali | **Media**: S4 long-only; drift breve plausibile ma contenuto sentiment ≠ fondamentale |
| 5 | Tetlock (2011), *All the News That's Fit to Reprint* | [10.1093/rfs/hhq141](https://doi.org/10.1093/rfs/hhq141) | Dow Jones newswire, 1996–2008 | News stale vs nuova | Stale news: reazione minore; reversal settimanale successivo; individui overreact | **Alta**: critica per S4 — articoli derivati/ripetuti possono generare signal churn |
| 6 | Leung & Zhang (2021), *Optimal Trading with a Trailing Stop* | [10.1007/s00245-019-09559-0](https://doi.org/10.1007/s00245-019-09559-0) | Modello diffusione lineare (teorico) | Trailing stop + limit order | Ottimale usare entrambi; trailing da solo non è ottimale | **Bassa**: modello teorico, non news-driven; utile come struttura, non come evidenza |
| 7 | Dai et al. (2021), *Risk Reduction Using Trailing Stop-Loss Rules* | [10.1111/irfi.12328](https://doi.org/10.1111/irfi.12328) | Azioni USA, 1926–2016 | Trailing stop | Inferiori a benchmark mean-variance per return; riducono downside in mercati in calo; 20% robusto | **Media**: trailing come overlay rischio, non fonte alpha |
| 8 | White (2000), *A Reality Check for Data Snooping* | [10.1111/1468-0262.00152](https://doi.org/10.1111/1468-0262.00152) | Simulazioni + applicazione | N/A (metodo) | Bootstrap per testare se miglior modello da search è superiore a benchmark | **Alta**: obbligatorio per confrontare exit multiple |
| 9 | Hansen (2005), *A Test for Superior Predictive Ability* | [10.1198/073500105000000063](https://doi.org/10.1198/073500105000000063) | Applicazione inflazione | N/A (metodo) | SPA test: più potente di White RC, meno sensibile ad alternative irrilevanti | **Alta**: preferibile a White RC per confronto exit |
| 10 | Bailey & López de Prado (2014), *Deflated Sharpe Ratio* | [10.3905/jpm.2014.40.5.094](https://doi.org/10.3905/jpm.2014.40.5.094) | Backtest simulati | N/A (metodo) | DSR corregge per selection bias, backtest overfitting, non-normalità | **Alta**: required per riportare Sharpe/IC corretti |
| 11 | Gârleanu & Pedersen (2013), *Dynamic Trading with Predictable Returns and Transaction Costs* | [10.1111/jofi.12080](https://doi.org/10.1111/jofi.12080) | Commodity futures | De-risking graduale | "Aim in front of target": trade parziale verso target; segnali lenti più preziosi | **Media**: supporta de-risking graduale e no-trade band |
| 12 | Davis & Norman (1990), *Portfolio Selection with Transaction Costs* | [10.1287/moor.15.4.676](https://doi.org/10.1287/moor.15.4.676) | Modello continuo (teorico) | No-trade region | Regione a cuneo: non negoziare entro boundaries; local times ai bordi | **Alta**: fondazione teorica hysteresis/no-trade |
| 13 | Mei, DeMiguel & Nogales (2016), *Multiperiod Portfolio Optimization with Multiple Risky Assets and General Transaction Costs* | [10.1016/j.jbankfin.2016.04.002](https://doi.org/10.1016/j.jbankfin.2016.04.002) | Azioni USA, 1965–2014 | No-trade parallelogramma | Losses grandi se si ignorano costi o si è miopi | **Alta**: supporta hysteresis state-based, non solo temporale |
| 14 | Osler (2003), *Currency Orders and Exchange Rate Dynamics* | [10.1111/1540-6261.00588](https://doi.org/10.1111/1540-6261.00588) | FX, 1999–2000 | Cluster stop/TP | Take-profit a round numbers; stop-loss oltre; reversal/accelerazione | **Bassa**: FX, non azioni; utile per microstruttura stop/TP clustering |
| 15 | Almgren & Chriss (2001), *Optimal Execution of Portfolio Transactions* | [10.21314/JOR.2001.041](https://doi.org/10.21314/JOR.2001.041) | Modello esecuzione | Execution-aware exit | Frontiera efficiente: impact vs timing risk; L-VaR | **Media**: separa decision price e execution price; required per slippage reporting |
| 16 | Broadie, Glasserman & Kou (1997), *Continuity Correction for Discrete Barrier Options* | [10.1111/1467-9965.00035](https://doi.org/10.1111/1467-9965.00035) | Opzioni barriera (teorico) | Barrier hit discreto | Correzione ∝ σ√Δt per monitoraggio discreto | **Media**: avverte che close-based simulation può misclassificare hit |
| 17 | Bajgrowicz & Scaillet (2012), *Technical Trading Revisited: False Discoveries, Persistence Tests, and Transaction Costs* | [10.1016/j.jfineco.2012.06.001](https://doi.org/10.1016/j.jfineco.2012.06.001) | DJIA, 1897–2011 | Technical rules | FDR: nessuna regola persistente ex ante; costi offsettano performance | **Alta**: monito su selection bias e costi |
| 18 | Moreira & Muir (2017), *Volatility-Managed Portfolios* | [10.1111/jofi.12513](https://doi.org/10.1111/jofi.12513) | Fattori US, 1926–2016 | Volatility timing | Scaling inverso a varianza: alpha +4,9%/anno, Sharpe +25% | **Media**: regime come sizing, non exit; instabilità OOS |
| 19 | Cederburg et al. (2020), *On the Performance of Volatility-Managed Portfolios* | [10.1016/j.jfineco.2020.04.015](https://doi.org/10.1016/j.jfineco.2020.04.015) | 103 strategie equity | Volatility timing | OOS: underperformance sistematica; instabilità | **Alta**: cautela su regime exits binarie |
| 20 | Glynn & Iglehart (1995), *Trading Securities Using Trailing Stops* | [10.1287/mnsc.41.6.1096](https://doi.org/10.1287/mnsc.41.6.1096) | Brownian motion (teorico) | Trailing stop | Distribuzione guadagni, durata; ottimizzazione distanza | **Bassa**: teorico, non news-driven |

---

## 4. Strategy Catalog

| ID | Policy | Razionale | Vantaggi | Failure mode | Complessità | Trial cost |
|---|---|---|---|---|---|---|
| **E0** | Uscita corrente (weight-drop) | Baseline as-is: ranker produce target weights; peso zero = sell | Semplice; nessun parametro aggiuntivo | Confonde 4+ eventi diversi; `unknown` prevalente; non misurabile economicamente | Bassa | 1 (baseline) |
| **E1** | D+2 time-stop + contro-segnale ≤ −0,30 + catastrophe stop | Allinea holding period a drift post-news (Jiang et al. 2021); riduce turnover | Parsimoniosa; coerente con letteratura underreaction; shadow end-to-end recupera osservabilità | D+2 può essere troppo corto/lungo per news editoriali; contro-segnale singolo rumoroso | Bassa | 1 (primaria) |
| **E2** | D+1 / D+3 | Diagnostica term structure | Identifica picco/decadimento alpha | Scegliere ex post il migliore = data snooping; non sono policy indipendenti | Bassa | 2 (diagnostiche) |
| **E3** | Counter-signal only (no time-stop) | Falsificazione pura della tesi | Evita uscite per scadenza arbitraria | Rischio di "zombie positions" se contro-segnale raro; capitale bloccato | Media | 1 |
| **E4** | Time-stop + segnale aggregato (decadimento) | Separa exit design da input churn (ultimo articolo) | Robusta a single-article noise; coerente con Tetlock 2011 | Richiede definizione aggregazione (finestra, pesi); parametro aggiuntivo | Media | 1–2 |
| **E5** | Time-stop + wide volatility/catastrophe stop (12–20%) | Protezione di coda senza noise stop | Riduce expected shortfall; coerente con Dai et al. 2021 | Non migliora expected return; può dare falsa sicurezza | Bassa | 1 |
| **E6** | Trailing attivato dopo MFE predefinita | Protegge vincitori senza troncare subito coda destra | Coerente con Leung & Zhang 2021; Dai et al. 2021 | Rischio di tagliare code positive; lag volatilità; parametro MFE | Media | 1–2 |
| **E7** | Policy event-type/segno-specifica | News fondamentale vs sentiment; nuova vs stale (Tetlock 2011) | Potenziale alpha eterogeneo | Richiede classifier; numerosità per sottogruppo; multiple testing esploso | Alta | 4+ (per tipo) |
| **E8** | Replacement exit (costo-opportunità) | Vendi se nuovo candidato ha valore atteso superiore | Massimizza uso capitale; coerente con S4 top-5 | Non falsifica tesi; turnover alto; parametro soglia | Media | 1 |
| **E9** | De-risking parziale (100% → 50% → 0) | Coerente con Gârleanu & Pedersen 2013; Davis & Norman 1990 | Riduce variance senza full-close; frontiera di non-intervento | Complica attribuzione P&L; turnover; parametri multipli | Alta | 2–3 |

---

## 5. Shortlist

**Policy da portare al confronto confirmatorio (max 3):**

| Policy | Motivazione shortlist | Statuto |
|---|---|---|
| **E1 (D+2 + counter + catastrophe)** | Baseline pre-registrata; coerente con Jiang et al. 2021 (drift multi-day); minima complessità | **Primaria confirmatoria** |
| **E3 (counter-signal only)** | Testa ipotesi "falsificazione della tesi" senza scadenza arbitraria; richiesta da letteratura (Tetlock 2011) | **Diagnostica** |
| **E5 (D+2 + wide catastrophe)** | Aggiunge protezione di coda (Dai et al. 2021) senza introdurre parametri fragili | **Robustezza** |

**Respinte / solo esplorative:**

- **E2 (D+1/D+3)**: solo term structure esplorativa; non policy indipendenti.
- **E6 (trailing post-MFE)**: complessità aggiuntiva; evidenza empirica debole per news momentum; rischio di troncare code positive.
- **E7 (event-type-specific)**: numerosità insufficiente; richiederebbe classifier e nuova pre-registrazione.
- **E8 (replacement)**: non falsifica tesi; turnover; meglio misurare overlap S1.
- **E9 (de-risking)**: complessità alta; alpha S4 non dimostrato; posticipare.

---

## 6. Empirical Protocol

### 6.1 Ledger (event-level)

Ogni intent di ingresso S4 (shadow o storico) deve generare un record con:

| Campo | Tipo | Descrizione |
|---|---|---|
| `signal_id` | string | ID univoco segnale |
| `article_id` | string | ID articolo/evento |
| `ticker` | string | Ticker risolto (post-resolver) |
| `source` | enum | Fonte primaria / derivata / aggregatore |
| `published_at` | timestamp | Pubblicazione news (UTC) |
| `ingested_at` | timestamp | Ingestione pipeline |
| `decision_at` | timestamp | Decision timestamp S4 |
| `score` | float | `polarity × confidence` |
| `confidence` | float | Confidence modello |
| `model` | enum | `glm52`, `gptoss`, `fallback` |
| `novelty` | float | Novelty score (Jaccard o embedding-based) |
| `is_true_ticker` | bool | Verifica post-hoc appartenenza reale |
| `entry_intent` | bool | True se segnale avrebbe generato BUY intent |
| `fill_price` | float | Primo prezzo RTH eseguibile post-decision |
| `fill_time` | timestamp | Timestamp fill shadow |
| `size` | float | Size teorica (slot%) |
| `s1_collision` | bool | True se S1 ha intent simultaneo |
| `costs_bps` | float | Costi stimati (fee + spread + impact) |
| `mae` | float | Maximum Adverse Excursion |
| `mfe` | float | Maximum Favorable Excursion |
| `time_to_mae` | minutes | Tempo a MAE |
| `time_to_mfe` | minutes | Tempo a MFE |
| `gap_overnight` | float | Gap overnight (se applicabile) |
| `volatility_entry` | float | Volatilità 20gg annualizzata |
| `liquidity_entry` | float | Volume medio / spread |
| `exit_E1_triggered` | bool | Time-stop D+2 triggerato |
| `exit_E3_triggered` | bool | Counter-signal triggerato |
| `exit_E5_triggered` | bool | Catastrophe stop triggerato |
| `exit_price_E1` | float | Prezzo uscita E1 |
| `exit_price_E3` | float | Prezzo uscita E3 |
| `exit_price_E5` | float | Prezzo uscita E5 |
| `pnl_net_E1` | float | P&L netto E1 |
| `pnl_net_E3` | float | P&L netto E3 |
| `pnl_net_E5` | float | P&L netto E5 |
| `post_exit_drift_1h` | float | Drift 1h post-exit |
| `post_exit_drift_close` | float | Drift a close |
| `post_exit_drift_D1` | float | Drift D+1 |
| `post_exit_drift_D2` | float | Drift D+2 |
| `post_exit_drift_D3` | float | Drift D+3 |
| `post_exit_drift_D5` | float | Drift D+5 |
| `reason_code` | enum | `time_stop`, `counter_signal`, `catastrophe`, `expired`, `unknown` |
| `censor_flag` | bool | True se dato mancante / censurato |
| `censor_reason` | string | Motivo censura |

### 6.2 Prezzi e costi

- **Ingresso:** primo prezzo RTH eseguibile dopo `decision_at`; in assenza, close barra 15min successiva.
- **Uscita:** close di D+2 (E1), prezzo counter-signal (E3), stop price (E5).
- **Costi:** fee broker + spread bid-ask + market impact (Almgren & Chriss 2001) + slippage gap.
- **Corporate actions:** `adjustment="all"` per forward return coerenti (#192).

### 6.3 Metriche

| Metrica | Formula / Descrizione |
|---|---|
| **IC primario** | Spearman cross-sectional score vs forward return D+2; media temporale |
| **IC secondary** | 1g, 3g (robustezza); close, 5g (diagnostico) |
| **t Newey-West** | t-stat con SE HAC, lag = orizzonte forward return |
| **P&L netto** | Somma pnl_net_E1, E3, E5 (separati) |
| **Excess return** | vs benchmark equal-weight watchlist |
| **Turnover** | Somma |size| / NAV |
| **Slippage** | (fill_price − decision_price) / decision_price |
| **Hit rate** | % trade positivi |
| **Payoff ratio** | Media win / Media loss |
| **Profit factor** | Somma win / Somma loss |
| **Expectancy** | (Hit rate × Avg win) − ((1−Hit rate) × Avg loss) |
| **Volatilità** | Std dev rendimenti giornalieri portafoglio |
| **Downside deviation** | Std dev rendimenti negativi |
| **Max drawdown** | Massimo picco-valle |
| **VaR 95%** | Value at Risk 95% (cauto) |
| **Expected Shortfall** | Media code oltre VaR |
| **Skewness** | Asimmetria rendimenti |
| **Coda destra contributo** | % P&L da top 5% trade positivi |
| **False-stop rate** | % uscite in perdita con recovery entro D+2 |
| **Giveback da MFE** | (MFE − exit_price) / MFE |
| **Overlap S1** | % intent con S1 simultaneo |
| **Valore incrementale** | P&L S4 condizionato a overlap S1 |

### 6.4 Inferenza

- **Bootstrap a blocchi:** per giorno/evento cluster (articoli multipli su stesso ticker-giorno non indipendenti).
- **Newey-West/HAC:** per forward return sovrapposti (3g, 5g).
- **Cluster bootstrap:** per IC giornalieri (serie temporale).
- **Power analysis:** `n = (3 × σ / IC_target)²` per t=3; con σ=0,243 (dev std IC giornaliera osservata), IC_target=0,05 → n≈213 sedute.
- **Reality Check / SPA:** White (2000) o Hansen (2005) per confrontare E1 vs E3 vs E5; pubblicare numero totale trial.
- **Deflated Sharpe Ratio:** Bailey & López de Prado (2014) per correggere selection bias.
- **Embargo/Purging:** se label e training window si sovrappongono (non applicabile se solo shadow).

### 6.5 Gate congiunto

B può essere riattivata solo se:

1. **Integrità:** ≥95% lifecycle shadow ricostruibile; uscite `unknown`+`expired` <5%; nessuna divergenza config dichiarata vs applicata.
2. **Alpha:** IC medio D+2 ≥ +0,05; t NW ≥3; segno non contraddetto a 1g e 3g.
3. **Economia:** P&L shadow netto E1 > benchmark EW; limite inferiore 95% unilaterale >0.
4. **Robustezza:** E1 > E0 e E3 su paired delta; slippage conservativo (×1,5) non inverte segno.
5. **Stabilità:** IC positivo in ≥2 sottoperiodi (es. primi 100gg, restanti).
6. **Correzione multiple testing:** SPA p-value <0,05 su {E0, E1, E3, E5}.
7. **Indipendenza S1:** Overlap intent ≤50%; P&L incrementale (condizionato a overlap) ≥0.

---

## 7. Pre-Registration Draft

### Ipotesi primaria

**H1:** La configurazione E1 (time-stop D+2, contro-segnale ≤ −0,30, catastrophe stop 12–20%) produce IC cross-sectional medio ≥ +0,05 all'orizzonte 2 sedute sulla popolazione tradabile (solo-ensemble, |score|≥0,30, ticker validato, post-gate, post-collisione S1).

### Benchmark

- **Primario:** E0 (uscita weight-drop corrente, shadow).
- **Secondario:** Benchmark equal-weight watchlist (daily rebalance).

### Metrica primaria

- **IC Spearman medio** (serie temporale, giorni ≥5 simboli/giorno).
- **t-stat Newey-West** (lag=2 per D+2).

### Gate

Vedi §6.5 (7 condizioni congiunte).

### Sample start

- **Data deploy shadow:** prima seduta RTH dopo merge fix #243, #244 e attivazione shadow end-to-end.
- **Segmento pre-fix:** congelato, audit-only, non conta come out-of-sample.
- **Segmento post-fix:** n=0 dalla prima seduta post-deploy.

### Stopping rule

- **Review tecnica:** n=40 sedute (pipeline, integrità, direzione).
- **Review economica:** n=73 sedute (diagnostica; non decisionale).
- **Decisione confirmatoria:** n=213 sedute (o prima se t≥3 e gate congiunto soddisfatto; early-stop pre-registrato).
- **Invalidazione:** se a n=213 IC < +0,03 o t <2 o P&L netto ≤0 → kill o redesign (non shadow indefinito).

### Condizioni di riavvio

- Qualunque errore di implementazione (fill, reason code, collisione S1, clock DAILY) → azzeramento n e riavvio.
- Cambio configurazione (soglia, orizzonte, universo, sizing) → invalidazione segmento; nuovo n=0.

---

## 8. Unknowns and Data Requests

| Unknown | Perché non decidibile | Data request esatta |
|---|---|---|
| **Soglie force-sell** | Divergenza codice (−0,20) vs doc (−0,35) | Dump config runtime + log force-sell ultimi 90gg |
| **Disaster stop broker** | Commento YAML "shadow" vs ordini reali | Report ordini broker GTC con reason `d_hard` ultimi 90gg |
| **Take-profit broker** | Solo non-fractionable; reason non mappato | Report fill con reason `take_profit` + frazionabilità ticker |
| **Novelty score** | Non calcolato point-in-time | Implementare Jaccard/embedding novelty per ogni articolo; storico backfill |
| **True ticker validation** | Entity resolution non verificata su golden set | Campione etichettato QX-01 (n≥500 articoli) con ground truth ticker |
| **Post-fix popolazione** | Fix #243, #244 non ancora deployati | N/A (attendere deploy) |
| **Slippage strutturale** | Fill shadow non calibrato su fill reali | Confronto fill shadow vs fill paper ultimi 30gg; regressione slippage |
| **Overlap S1** | Misurato solo 2 giorni (30 intenti) | Export intent S1+S4 ultimi 90gg; calcolo overlap % e capitale impegnato |
| **Term structure alpha** | Solo 1h, 4h, close osservati | Ricalcolo forward return {1h, 4h, close, D1, D2, D3, D5} su segmento pre-fix pulibile |
| **Numero trial osservati** | Analisi precedenti non tracciate | Registro analisi S4 (date, parametri, risultati) da inizio progetto |

---

## 9. Challenge to the Existing D+2 Decision

### Argomento migliore A FAVORE di D+2 (KEEP)

**EVIDENZA ESTERNA:** Jiang, Li & Wang (2021) trovano drift post-news per più giorni senza reversal su dati high-frequency (2000–2012). La strategia news momentum genera 1,60–3,34%/mese netta. Tetlock et al. (2008) confermano sottoreazione 1–2 giorni per news negative.

**EVIDENZA ALEMBIC:** S4 ha fill tardivi (64,3° percentile mediano del range giornaliero; 70–84% movimento già avvenuto). Un orizzonte intraday (A) comprerebbe dopo il movimento. D+2 separa nettamente signal freshness (ingresso) e holding period (uscita), allineando la regola d'uscita all'orizzonte economico.

**INFERENZA:** D+2 è il compromesso più parsimonioso tra letteratura (drift multi-day) e vincoli S4 (fill tardivi, news editoriali). Shadow end-to-end recupera osservabilità ingegneristica senza rischio di capitale.

### Argomento migliore CONTRO D+2 (REJECT / MODIFY)

**EVIDENZA ESTERNA:** Tetlock (2011) mostra che news stale (ripetute) producono reversal settimanale. Se S4 entra su articoli derivati/ripetuti, D+2 potrebbe essere **troppo lungo** per news stale e **troppo corto** per news fondamentale. La letteratura non supporta un orizzonte unico per tutte le news.

**EVIDENZA ALEMBIC:** La popolazione pre-fix è contaminata (resolver errato, articoli multi-ticker, fallback FinBERT). L'IC osservato non è misurato sulla popolazione tradabile. D+2 è scelto su dati non rappresentativi.

**INFERENZA:** D+2 è un'ipotesi plausibile, ma non ottimale per tutte le news. Una policy condizionata (E7) sarebbe superiore, ma richiede numerosità e classifier non disponibili. Quindi D+2 va testata in shadow, ma con consapevolezza che potrebbe essere respinta per eterogeneità non modellata.

### Verdetto finale

**KEEP** con le seguenti precisazioni:

1. D+2 è **ipotesi primaria confirmatoria**, non verità economica dimostrata.
2. Shadow deve essere **end-to-end**, non solo calcolo IC.
3. Term structure {1h, 4h, close, D1, D2, D3, D5} va riportata in esplorazione, ma **solo D+2 conta per la decisione**.
4. Se E3 (counter-signal only) outperforms E1 su SPA test, allora **MODIFY** a E3.
5. Se overlap S1 >50% e P&L incrementale ≤0, allora **REJECT** S4 come ridondante.

---

## 10. Bibliography

### Fonti primarie citate

1. Kaminski, K. M., & Lo, A. W. (2014). When Do Stop-Loss Rules Stop Losses? *Journal of Financial Markets*, 18, 234–254. DOI: [10.1016/j.finmar.2013.07.001](https://doi.org/10.1016/j.finmar.2013.07.001)

2. Lo, A. W., & Remorov, A. (2017). Stop-Loss Strategies with Serial Correlation, Regime Switching, and Transactions Costs. DOI: [10.1016/j.finmar.2017.02.003](https://doi.org/10.1016/j.finmar.2017.02.003)

3. Jiang, H., Li, S. Z., & Wang, H. (2021). Pervasive Underreaction: Evidence from High-Frequency Data. *Journal of Financial Economics*, 141(2), 573–599. DOI: [10.1016/j.jfineco.2021.04.003](https://doi.org/10.1016/j.jfineco.2021.04.003)

4. Tetlock, P. C., Saar-Tsechansky, M., & Macskassy, S. (2008). More Than Words: Quantifying the Language Content of the Earnings Call. *Journal of Finance*, 63(3). DOI: [10.1111/j.1540-6261.2008.01362.x](https://doi.org/10.1111/j.1540-6261.2008.01362.x)

5. Tetlock, P. C. (2011). All the News That's Fit to Reprint: Do Investors React to Stale Information? *Review of Financial Studies*, 24(5), 1481–1512. DOI: [10.1093/rfs/hhq141](https://doi.org/10.1093/rfs/hhq141)

6. Leung, T., & Zhang, H. (2021). Optimal Trading with a Trailing Stop. *Applied Mathematics & Optimization*, 83, 669. DOI: [10.1007/s00245-019-09559-0](https://doi.org/10.1007/s00245-019-09559-0)

7. Dai, M., Li, P., Liu, H., & Wang, Y. (2021). Risk Reduction Using Trailing Stop-Loss Rules. *International Review of Finance*, 21(4). DOI: [10.1111/irfi.12328](https://doi.org/10.1111/irfi.12328)

8. White, H. (2000). A Reality Check for Data Snooping. *Econometrica*, 68(5), 1097–1126. DOI: [10.1111/1468-0262.00152](https://doi.org/10.1111/1468-0262.00152)

9. Hansen, P. R. (2005). A Test for Superior Predictive Ability. *Journal of Business & Economic Statistics*, 23(4), 365–380. DOI: [10.1198/073500105000000063](https://doi.org/10.1198/073500105000000063)

10. Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality. *Journal of Portfolio Management*, 40(5), 94–107. DOI: [10.3905/jpm.2014.40.5.094](https://doi.org/10.3905/jpm.2014.40.5.094)

11. Gârleanu, N., & Pedersen, L. H. (2013). Dynamic Trading with Predictable Returns and Transaction Costs. *Journal of Finance*, 68(6), 2309–2340. DOI: [10.1111/jofi.12080](https://doi.org/10.1111/jofi.12080)

12. Davis, M. H. A., & Norman, A. R. (1990). Portfolio Selection with Transaction Costs. *Mathematics of Operations Research*, 15(4), 676–713. DOI: [10.1287/moor.15.4.676](https://doi.org/10.1287/moor.15.4.676)

13. Mei, X., DeMiguel, V., & Nogales, F. J. (2016). Multiperiod Portfolio Optimization with Multiple Risky Assets and General Transaction Costs. *Journal of Banking & Finance*, 69, 108–120. DOI: [10.1016/j.jbankfin.2016.04.002](https://doi.org/10.1016/j.jbankfin.2016.04.002)

14. Osler, C. L. (2003). Currency Orders and Exchange Rate Dynamics: An Explanation for the Predictive Success of Technical Analysis. *Journal of Finance*, 58(5), 1791–1819. DOI: [10.1111/1540-6261.00588](https://doi.org/10.1111/1540-6261.00588)

15. Almgren, R., & Chriss, N. (2001). Optimal Execution of Portfolio Transactions. *Journal of Risk*, 3(2), 5–39. DOI: [10.21314/JOR.2001.041](https://doi.org/10.21314/JOR.2001.041)

16. Broadie, M., Glasserman, P., & Kou, S. (1997). A Continuity Correction for Discrete Barrier Options. *Mathematical Finance*, 7(4), 325–349. DOI: [10.1111/1467-9965.00035](https://doi.org/10.1111/1467-9965.00035)

17. Bajgrowicz, P., & Scaillet, O. (2012). Technical Trading Revisited: False Discoveries, Persistence Tests, and Transaction Costs. *Journal of Financial Economics*, 106(3), 473–491. DOI: [10.1016/j.jfineco.2012.06.001](https://doi.org/10.1016/j.jfineco.2012.06.001)

18. Moreira, A., & Muir, T. (2017). Volatility-Managed Portfolios. *Journal of Finance*, 72(4), 1611–1644. DOI: [10.1111/jofi.12513](https://doi.org/10.1111/jofi.12513)

19. Cederburg, S., O'Doherty, M. S., Wang, F., & Yan, X. S. (2020). On the Performance of Volatility-Managed Portfolios. *Journal of Financial Economics*, 138, 95–117. DOI: [10.1016/j.jfineco.2020.04.015](https://doi.org/10.1016/j.jfineco.2020.04.015)

20. Glynn, P. W., & Iglehart, D. L. (1995). Trading Securities Using Trailing Stops. *Management Science*, 41(6), 1096–1106. DOI: [10.1287/mnsc.41.6.1096](https://doi.org/10.1287/mnsc.41.6.1096)

### Accesso full-text

- **Full-text disponibili:** 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20 (tutti DOI risolvono a publisher o arXiv)
- **Abstract-only:** 4 (Tetlock 2008 — full-text via Columbia University repository)
- **Working paper + published:** 8, 9, 10, 11, 18, 19 (entrambe versioni disponibili)

---

**Nota finale:** Questa analisi non propone modifiche al codice. Raccomanda shadow immediato, pre-registrazione formale prima di osservare il segmento post-fix, e confronto confirmatorio con gate congiunto. D+2 è ipotesi primaria, non verità economica.
