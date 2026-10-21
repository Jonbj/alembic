# Alpha-miss report 2026-10-09

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-21T08:00:27Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. Pipeline sentiment ferma per tutta la seduta: 0 righe news_log su 96/96 simboli (`mercato.watchlist_zero_news` 96, `copertura_articoli.totali.righe_news_log` 0). `worker-inference` è andato in warm shutdown il 2026-10-08 alle 16:20Z e non è tornato fino al 2026-10-16. Il news-stream intanto ha continuato ad accodare: la coda è passata da 326 a 1.008 elementi senza consumatore.
2. 11 mover |ret|>=3% (7 su, 4 giù, dispersione 2,65%). Il tema è il crollo delle telecom (TMUS −13,27%, T −9,80%, VZ −8,74%). Le 3 ENTRY_OPPORTUNITY (BABA +5,36%, ORCL +4,59%, AMZN +3,29%) risultano NO_NEWS, ma nel log del news-stream avevano titoli (5/25/107 righe) che non sono mai stati scorati. profitable_capture_rate 0/3.
3. Nessun ingresso e nessuna chiusura (2.075 intent S4, tutti su segnali di 10-05→10-08: 1.199 SKIP_ENTRY_FRESHNESS). Il book detenuto all'open chiude a +215,61 $ di seduta (S1 +98,06, S4 +117,55; `snapshot_apertura`).

## 2. Stato carta
as_of di economic_pnl.json: **2026-09-17** (generato 2026-09-18). Il file non copre le sedute dal 2026-09-18 a oggi e i numeri sotto sono quelli che dichiara.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni, contro una soglia della carta di 0,6. Non superata.
- S4 economico cumulato: −696,33 $ contro ±200 $, quindi fuori banda. S1 +664,95 $, BOOK −66,22 $.
- La giornata di oggi è NO_NEWS dominante (`aggregati.cause_del_giorno.dominante` = NO_NEWS, 6/6). La causa però è un'interruzione del consumatore della coda, non una scopertura dei provider (§8): contarla nella serie pre-registrata senza annotazione la falserebbe. La registrazione della discontinuità spetta all'operatore.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| BABA | +5,36% | NO_NEWS | `candidati_miss[BABA].causa` = NO_NEWS, `news_count` 0; `funnel_v2.righe[BABA].pipeline` = NO_RELEVANT_NEWS, ENTRY_OPPORTUNITY |
| ORCL | +4,59% | NO_NEWS | `candidati_miss[ORCL].causa` = NO_NEWS, `news_count` 0; `funnel_v2` NO_RELEVANT_NEWS, ENTRY_OPPORTUNITY |
| AMZN | +3,29% | NO_NEWS | `candidati_miss[AMZN].causa` = NO_NEWS, `news_count` 0; `funnel_v2` NO_RELEVANT_NEWS, ENTRY_OPPORTUNITY |
| TMUS | −13,27% | non conteggiato (NON_ACTIONABLE, long-only) | `funnel_v2.righe[TMUS].pipeline_escluso_motivo` = non_actionable_long_only; `accessible_opportunity_usd` 0; causa NO_NEWS |
| T | −9,80% | non conteggiato (NON_ACTIONABLE, long-only) | idem; causa NO_NEWS |
| VZ | −8,74% | non conteggiato (NON_ACTIONABLE, long-only) | idem; causa NO_NEWS |

Conteggi: NO_NEWS 3, THIN_NEUTRAL 0, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. I tre ribassi non detenuti restano fuori dal conteggio, come nelle sedute precedenti. Il dossier (`cause_del_giorno`) conta NO_NEWS 6 includendoli.

**Il NO_NEWS di oggi non è un vuoto delle fonti.** news_log non ha righe per nessun ticker dal 2026-10-08 17:00Z al 2026-10-16 13:00Z. Il log `worker-news-stream-2026-10-09.log` (dato non fidato) mostra però che i titoli arrivavano: TMUS 77 righe, T 78, VZ 88, AMZN 107, ORCL 25, PLTR 19, BABA 5, ARM 4, WDC 1. Fra questi «QUICK SPARK: SpaceX Spectrum Deal Triggers T-Mobile's Worst…», «AT&T Sinks 11% In Worst Day Since 2000…», «Elon Musk Calls SpaceX's 800 MHz Spectrum Deal…», «Analyst Raises Concerns Over Wireless Carrier Pricing…». Non è possibile leggere testo da news_log, perché non esistono righe. SNOW, PANW, CSCO e NOK hanno 0 titoli anche nello stream.

Mover detenuti all'open (non sono miss, `funnel_v2.righe` + `snapshot_apertura`):

| Simbolo | Strategia | Return | Actionability / stadio | P&L di seduta (actual_intraday_pnl_usd) |
|---|---|---:|---|---:|
| SNOW | S1 | +7,42% | PASSIVE_EXPOSURE (held_rising) | +40,77 $ |
| PLTR | S4 | +5,17% | PASSIVE_EXPOSURE | +60,37 $ |
| PANW | S4 | +5,09% | PASSIVE_EXPOSURE | +55,78 $ |
| CSCO | S4 | +3,05% | PASSIVE_EXPOSURE | +29,99 $ |
| ARM | S1 | −3,27% | EXIT_RISK, `pipeline_uscita` STALE_EXIT_SIGNAL (signal 14668 del 10-08, −0,312) | −0,60 $ (nozionale 12,29 $) |

Catturati: 5, cioè i mover detenuti all'open; nessun ingresso nella seduta.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":[],"chiusure":[]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
<!-- alpha-miss-book:end -->
Il dossier non riporta ingressi né chiusure (`ingressi` = [], `chiusure` = []). I 2.075 intent S4 della seduta poggiano tutti su segnali generati fra il 10-05 e il 10-08 (1.344 del 10-08) e sono stati scartati: 1.199 SKIP_ENTRY_FRESHNESS, 528 SKIP_FALLBACK, 204 SKIP_ENTRY_GATE, 96 SKIP_STALE, 48 SKIP_PYRAMIDING. Senza segnali nuovi, S4 non aveva niente di fresco da comprare. Le 41 posizioni detenute all'open hanno reso +215,61 $ di seduta.

## 5. Cecita' lato uscita
Due posizioni con `cieco_lato_uscita: true` (soglia −3% da ingresso, `sedute_minime` 2; `n_cieche_lato_uscita` 2 su 41, `n_indeterminati` 0, notional cieco 138,81 $):

| Ticker | Strategia | ritorno_da_ingresso | ritorno_seduta | sedute_consecutive_senza_righe | fonti_osservate_finestra | uscita nella seduta |
|---|---|---:|---:|---:|---|---|
| NOK | S1 | −11,60% | +2,17% | 3 | alpaca_benzinga, gdelt_gkg | no |
| WDC | S4 | −27,67% | +1,01% | 3 | alpaca_benzinga | no |

Nessuna riga ha `cieco_lato_uscita` null. Oggi la copertura_nulla vale 41/41, per l'interruzione e non per i provider. Le altre posizioni non sono cieche solo perché non superano la soglia di perdita (`perdita_marcata` 4/41: NOK, WDC, ARM, AMAT) o perché lo streak è di 1 seduta. AMAT (−14,61% da ingresso) ha `sedute_consecutive_senza_righe` 1: il 10-08 aveva righe. `held_news_loss_alert` (22:50 UTC, dopo il close) ha segnalato NOK e WDC (`alerted` 2).

## 6. Backstop NO_NEWS
Marker `CALENDAR`: nessuno. `calendar_observation.mover_observed` è 0/11 e `non_mover_observed` 0/85; tutti i mover hanno `observed_catalysts` vuoto, con FMP earnings-calendar e Alpaca Corporate Actions riuscite. La popolazione zero_news è 96 (11 mover, 85 non-mover).

Volume EOD (`temporal_validity` POST_HOC_EOD, `valid_for_signal_evaluation` false): la surprise mediana è +0,459 sugli 11 mover e −0,231 sugli 85 non-mover. Le tre telecom hanno adv_ratio 3,68 (TMUS), 3,95 (T) e 4,32 (VZ). La misura copre l'intera seduta e non era disponibile prima del movimento, quindi qui non si fissa nessuna soglia e non si stima nessun false-positive rate (la valutazione ex-ante è in #451).

Copertura raw di `news_log` per settore (distinta dalla effective-timely di `copertura_articoli.per_settore`, oggi anch'essa 0/96):

| Settore | ticker_with_news/ticker_universe | raw_news_coverage_rate | zero_news | mover zero_news |
|---|---:|---:|---:|---:|
| consumer | 0/11 | 0,0% | 11 | 0 |
| energy | 0/6 | 0,0% | 6 | 0 |
| etf_broad | 0/4 | 0,0% | 4 | 0 |
| financials | 0/14 | 0,0% | 14 | 0 |
| healthcare | 0/9 | 0,0% | 9 | 0 |
| industrials | 0/4 | 0,0% | 4 | 0 |
| materials | 0/2 | 0,0% | 2 | 0 |
| media | 0/5 | 0,0% | 5 | 0 |
| semis | 0/15 | 0,0% | 15 | 1 |
| tech | 0/21 | 0,0% | 21 | 7 |
| telecom | 0/5 | 0,0% | 5 | 3 |

Attribuzione fonti (FASE 5): 96 ticker con `articoli_unici` 0 e `fonti_osservate` vuoto. Nessuna fonte ha reso righe in news_log, perché il consumatore della coda era fermo (§8). Il vuoto non dice quindi nulla sulla resa dei singoli provider in questa seduta. Non c'è nessun caso di "fonte presente ma non effective-timely".

| Ticker | articoli_unici_giorno | effective_timely_articles_giorno | fonti_osservate |
|---|---:|---:|---|
| AAPL | 0 | 0 | {} |
| ABBV | 0 | 0 | {} |
| ADBE | 0 | 0 | {} |
| AMAT | 0 | 0 | {} |
| AMD | 0 | 0 | {} |
| AMZN | 0 | 0 | {} |
| ARM | 0 | 0 | {} |
| ASML | 0 | 0 | {} |
| AVGO | 0 | 0 | {} |
| AXP | 0 | 0 | {} |
| AZN | 0 | 0 | {} |
| BA | 0 | 0 | {} |
| BABA | 0 | 0 | {} |
| BAC | 0 | 0 | {} |
| BIDU | 0 | 0 | {} |
| BP | 0 | 0 | {} |
| BRK.B | 0 | 0 | {} |
| C | 0 | 0 | {} |
| CAT | 0 | 0 | {} |
| CMCSA | 0 | 0 | {} |
| COST | 0 | 0 | {} |
| CRM | 0 | 0 | {} |
| CSCO | 0 | 0 | {} |
| CVX | 0 | 0 | {} |
| DB | 0 | 0 | {} |
| DELL | 0 | 0 | {} |
| DIS | 0 | 0 | {} |
| ERIC | 0 | 0 | {} |
| F | 0 | 0 | {} |
| GE | 0 | 0 | {} |
| GM | 0 | 0 | {} |
| GOOGL | 0 | 0 | {} |
| GS | 0 | 0 | {} |
| HD | 0 | 0 | {} |
| HOOD | 0 | 0 | {} |
| IBM | 0 | 0 | {} |
| INFY | 0 | 0 | {} |
| INTC | 0 | 0 | {} |
| IWM | 0 | 0 | {} |
| JD | 0 | 0 | {} |
| JNJ | 0 | 0 | {} |
| JPM | 0 | 0 | {} |
| LLY | 0 | 0 | {} |
| MA | 0 | 0 | {} |
| MCD | 0 | 0 | {} |
| META | 0 | 0 | {} |
| MMM | 0 | 0 | {} |
| MRK | 0 | 0 | {} |
| MRVL | 0 | 0 | {} |
| MS | 0 | 0 | {} |
| MSFT | 0 | 0 | {} |
| MU | 0 | 0 | {} |
| NFLX | 0 | 0 | {} |
| NKE | 0 | 0 | {} |
| NOK | 0 | 0 | {} |
| NOW | 0 | 0 | {} |
| NVDA | 0 | 0 | {} |
| NVO | 0 | 0 | {} |
| ORCL | 0 | 0 | {} |
| PANW | 0 | 0 | {} |
| PBR | 0 | 0 | {} |
| PFE | 0 | 0 | {} |
| PG | 0 | 0 | {} |
| PLTR | 0 | 0 | {} |
| QCOM | 0 | 0 | {} |
| QQQ | 0 | 0 | {} |
| RDDT | 0 | 0 | {} |
| RIO | 0 | 0 | {} |
| ROKU | 0 | 0 | {} |
| SAP | 0 | 0 | {} |
| SBUX | 0 | 0 | {} |
| SHEL | 0 | 0 | {} |
| SNOW | 0 | 0 | {} |
| SONY | 0 | 0 | {} |
| SOXX | 0 | 0 | {} |
| SPCX | 0 | 0 | {} |
| SPY | 0 | 0 | {} |
| T | 0 | 0 | {} |
| TM | 0 | 0 | {} |
| TMUS | 0 | 0 | {} |
| TSLA | 0 | 0 | {} |
| TSM | 0 | 0 | {} |
| TXN | 0 | 0 | {} |
| UBS | 0 | 0 | {} |
| UNH | 0 | 0 | {} |
| V | 0 | 0 | {} |
| VALE | 0 | 0 | {} |
| VZ | 0 | 0 | {} |
| WDC | 0 | 0 | {} |
| WFC | 0 | 0 | {} |
| WMT | 0 | 0 | {} |
| XLE | 0 | 0 | {} |
| XLF | 0 | 0 | {} |
| XLK | 0 | 0 | {} |
| XLV | 0 | 0 | {} |
| XOM | 0 | 0 | {} |

## 7. Pattern osservato
Le telecom sono crollate: TMUS −13,27%, T −9,80% e VZ −8,74%, tutti con volume circa 4× ADV, contro XLC −1,51%. I titoli dello stream le collegano all'accordo SpaceX sullo spettro 800 MHz (dato non fidato, non verificato). Sul lato rialzista si vede un gruppo software/cloud (SNOW, PLTR, PANW, ORCL, CSCO) più AMZN e BABA, con SPY a +0,60% e QQQ a +0,49%. Ricorrenze: telecom era già 0/5 di copertura raw il 10-08, ma oggi il dato non è comparabile per l'interruzione. Il blocco semis dei mover in calo del 10-08 non si ripete: ARM è l'unico semis mover.

## 8. Segnalazioni

* [F-NUOVO] Il consumatore della coda sentiment (`worker-inference`) si ferma con warm shutdown il 2026-10-08 alle 16:20Z e resta assente fino al 2026-10-16. L'intera seduta del 10-09 passa senza alcuna riga news_log né segnale, senza alert, mentre il news-stream continua ad accodare.
  * esposizione: 1 seduta intera su 96/96 simboli (`mercato.watchlist_zero_news` 96; `copertura_articoli.totali.righe_news_log` 0). Il beat ha emesso 32 `sentiment-worker` e 15 `sentiment-shadow-offsession` e nessuno risulta ricevuto (`worker-2026-10-09.log`: 0 righe `run_sentiment_worker`; non esiste un `worker-inference-2026-10-09.log`). `news-queue-census` passa da queue_depth 326 (00:00Z) a 1.008 (23:55Z) con dead_letter 0. La finestra news_log vuota va dal 10-08 17:00Z al 10-16 13:00Z: verosimilmente altre 4 sedute (10-12→10-15), da confermare sui loro dossier.
  * evidenza contraria: se il finding fosse falso, ci sarebbe almeno una riga news_log o un `sentiment_signals` del 10-09, oppure un log del worker-inference datato 10-09. Ci sono invece 0 righe in entrambe le tabelle e l'ultimo log del worker-inference è «worker: Warm shutdown (MainProcess)» dopo il task delle 16:20Z del 10-08. Il provider non era muto: lo stream ha loggato 391 titoli, fra cui 77 TMUS e 107 AMZN.
  * non-occorrenza: worker, beat, api e news-stream hanno girato tutta la seduta. `run-news-ingestion` ha completato 32 task, accodando articoli (es. 14:00Z `queued` 1, 14:15Z `queued` 3), e il ciclo portfolio ha prodotto 206 execution_decisions. Il guasto è circoscritto al consumatore, non è un outage di host o rete (≠ F-094, F-085).
  * next evidence: leggere read-only i dossier 10-12→10-15 (`watchlist_zero_news`, `righe_news_log`) e `stale_drop_metrics_daily` del 10-16 per sapere quanta coda è scaduta alla ripartenza (cfr. F-069). In `docker events`/journal, se conservati, cercare la causa del warm shutdown delle 16:20Z.
  * meccanismo e fonte: §1, §3 e §6. Campi: `copertura_articoli.totali`, `no_news_backstop.population.zero_news` 96, `aggregati.cause_del_giorno` NO_NEWS 6/6, `funnel_v2.kpi.profitable_capture_rate` 0/3. Log: `beat-`, `worker-`, `worker-news-stream-2026-10-09.log`, `worker-inference-2026-10-08.log`. Sembra un difetto operativo, non un limite noto della strategia: nessun watchdog ha rilevato l'assenza del worker né la coda in crescita. Effetto collaterale sulla misura: la serie NO_NEWS pre-registrata conta come vuoto delle fonti una seduta in cui le fonti hanno reso.
  * costo: formula congetturale 2.200 $ × Σ|ret| delle ENTRY_OPPORTUNITY = 2.200 × (0,0536 + 0,0459 + 0,0329) = 291,55 $. Il dossier stima un'opportunità netta accessibile minore, `net_opportunity_usd` 8,30 + 14,52 + 26,66 = 49,48 $. Alternativa scartata: «le fonti non coprivano BABA/ORCL/AMZN» (F-001), smentita dallo stream con 5/25/107 titoli sugli stessi ticker. Alternativa scartata: «outage di host/rete» (F-094), smentita dalle 3.357 righe 'received' del worker principale nella seduta.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli)

| # | Simbolo | Return |
|---:|---|---:|
| 1 | SNOW | +7,42% |
| 2 | BABA | +5,36% |
| 3 | PLTR | +5,17% |
| 4 | PANW | +5,09% |
| 5 | ORCL | +4,59% |
| 6 | AMZN | +3,29% |
| 7 | CSCO | +3,05% |
| 8 | V | +2,76% |
| 9 | MA | +2,66% |
| 10 | PBR | +2,47% |
| 11 | MSFT | +2,38% |
| 12 | UBS | +2,27% |
| 13 | MRK | +2,26% |
| 14 | UNH | +2,25% |
| 15 | RDDT | +2,20% |
| 16 | NOK | +2,17% |
| 17 | TSLA | +2,05% |
| 18 | DELL | +2,00% |
| 19 | JNJ | +1,93% |
| 20 | HOOD | +1,88% |
| 21 | WFC | +1,85% |
| 22 | BIDU | +1,68% |
| 23 | PFE | +1,65% |
| 24 | XLV | +1,58% |
| 25 | RIO | +1,54% |
| 26 | VALE | +1,49% |
| 27 | ABBV | +1,48% |
| 28 | GS | +1,44% |
| 29 | BA | +1,40% |
| 30 | MS | +1,38% |
| 31 | BAC | +1,32% |
| 32 | SPCX | +1,25% |
| 33 | C | +1,22% |
| 34 | NVO | +1,20% |
| 35 | SAP | +1,12% |
| 36 | WDC | +1,01% |
| 37 | GOOGL | +0,97% |
| 38 | DIS | +0,96% |
| 39 | XLF | +0,92% |
| 40 | BRK.B | +0,89% |
| 41 | GE | +0,84% |
| 42 | LLY | +0,83% |
| 43 | NOW | +0,79% |
| 44 | WMT | +0,71% |
| 45 | SONY | +0,71% |
| 46 | JD | +0,67% |
| 47 | SPY | +0,60% |
| 48 | ASML | +0,60% |
| 49 | CRM | +0,58% |
| 50 | GM | +0,58% |
| 51 | ERIC | +0,58% |
| 52 | CAT | +0,54% |
| 53 | ADBE | +0,51% |
| 54 | XLK | +0,51% |
| 55 | QQQ | +0,49% |
| 56 | IWM | +0,49% |
| 57 | JPM | +0,47% |
| 58 | PG | +0,42% |
| 59 | AVGO | +0,39% |
| 60 | AXP | +0,33% |
| 61 | INFY | +0,28% |
| 62 | AZN | +0,26% |
| 63 | XOM | +0,26% |
| 64 | MRVL | +0,25% |
| 65 | IBM | +0,23% |
| 66 | CVX | +0,20% |
| 67 | DB | +0,15% |
| 68 | SHEL | -0,02% |
| 69 | NKE | -0,09% |
| 70 | COST | -0,11% |
| 71 | BP | -0,24% |
| 72 | XLE | -0,25% |
| 73 | QCOM | -0,29% |
| 74 | META | -0,31% |
| 75 | TM | -0,38% |
| 76 | AMAT | -0,50% |
| 77 | NVDA | -0,52% |
| 78 | ROKU | -0,62% |
| 79 | F | -0,65% |
| 80 | MU | -0,66% |
| 81 | SOXX | -0,69% |
| 82 | MCD | -0,70% |
| 83 | TSM | -1,02% |
| 84 | AAPL | -1,11% |
| 85 | TXN | -1,55% |
| 86 | HD | -1,60% |
| 87 | NFLX | -1,77% |
| 88 | AMD | -2,03% |
| 89 | MMM | -2,21% |
| 90 | INTC | -2,22% |
| 91 | CMCSA | -2,59% |
| 92 | SBUX | -2,64% |
| 93 | ARM | -3,27% |
| 94 | VZ | -8,74% |
| 95 | T | -9,80% |
| 96 | TMUS | -13,27% |

### (b) Altri finding aperti toccati dalla giornata

- [F-001] not_exposed: 0/96 a news, ma per il consumatore fermo; lo stream ha reso titoli su 9 dei 13 simboli verificati, quindi la seduta non misura la copertura dei provider.
- [F-036] supported: WDC (S4) a −27,67% da ingresso, oltre −20%, cieca per 3 sedute; l'alert `held_news_loss_alert` è delle 22:50 UTC, dopo il close. Oggi la seduta di WDC è +1,01%, senza costo incrementale.
- [F-016] supported: «SPY benchmark fetch failed: subscription does not permit querying recent SIP data» ripetuto in `worker-2026-10-09.log`, nessun alert.
- [F-018] supported: il token del bot Telegram compare in chiaro negli URL httpx a livello INFO (`worker-inference-2026-10-08.log`, ultime righe).
- [F-019] not_exposed: nessun articolo ingerito.
- [F-030] not_exposed: nessun punteggio prodotto.
- [F-031] supported: 48 intent SKIP_PYRAMIDING e 2 guard_decisions SKIP_PYRAMIDING, tutti su segnali vecchi.
- [F-049] not_exposed: l'ensemble non è stato invocato.
- [F-069] supported, in forma aggravata: la coda dello stream è cresciuta da 326 a 1.008 senza consumatore (`news_queue_census`).
- [F-075] not_exposed: i mover detenuti hanno nozionali da 596 a 1.999 $, tranne ARM (12,29 $, EXIT_RISK e non catturato).

### (c) Casi di successo
Nessun ingresso nella seduta, quindi nessun mover catturato con un trade del giorno. Le posizioni detenute in rialzo (PLTR +60,37 $, PANW +55,78 $, SNOW +40,77 $ di seduta) sono esposizione passiva, non catture.
