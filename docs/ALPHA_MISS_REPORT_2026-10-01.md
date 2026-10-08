# ALPHA MISS REPORT 2026-10-01

Contratto alpha_miss_prompt_v2 · dossier schema_version 3.1 · generato_il dossier 2026-10-08T08:00Z · prezzi Alpaca SIP adjustment=all · soglia_mover 0,03.

## 1. Decision card
1. 8 mover ≥3% (soglia_mover 0,03): up 7, down 1 (INFY +5,48%, RDDT +4,98%, AMAT +3,50%, BA +3,35%, CRM +3,10%, MU +3,03%, GM +3,00%; DIS −3,40%); dispersione σ 1,55%; SPY +0,18%, QQQ +0,31%.
2. Dei 8 mover: 3 già detenuti all'open (AMAT, MU, GM: PASSIVE_EXPOSURE), 1 catturato (INFY, ingresso S4 14:52Z, net_pnl −2,18 $), 1 non azionabile long-only (DIS), 3 miss (RDDT BELOW_GATE, CRM BELOW_GATE, BA RANKED_OUT con segnale 0,371 sopra gate); active_signal_recall 2/3, profitable_capture_rate 0/4.
3. Book: 12 chiusure, net_pnl realizzato −369,81 $ (S1 −342,82 su 8 `portfolio_sell`; S4 −26,99 su 4); 9 ingressi (5 S1, 4 S4); 28 simboli a zero news; 2 posizioni cieche lato uscita (SBUX, WDC).

## 2. Stato carta
- as_of `economic_pnl.json`: **2026-09-17** (generato 2026-09-18); non include il 10-01. A quella data: giorno **30/40** (minimo_giorni 40).
- Quota NO_NEWS dominante: 13/30 giorni (43,3%) contro soglia carta 0,60: non superata (as_of 09-17).
- S4 economico cumulato: **−696,33 $** vs ±200 $: fuori banda (`within: false`, as_of 09-17).
- Nota: la scadenza attesa della carta (2026-09-28) è passata; il 10-01 è il 43° giorno di borsa dal 2026-08-03 (conteggio mio, esteso dal 42° del report 09-30, non dal file). Stato aggiornato al 10-01: DATA_INCOMPLETE.

## 3. Miss del giorno
| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| RDDT | +4,98% | (b) THIN_NEUTRAL (v2: BELOW_GATE) | `candidati_miss[RDDT].max_score_own` +0,0218 < `cause_del_giorno.soglie.thin` 0,05 < gate 0,30; legacy `causa` = OFF_TOPIC_NON_DECIDIBILE, ma l'articolo è ISSUER_SPECIFIC CONCURRENT (`segnali[0].relevance`) |
| CRM | +3,10% | (b) THIN_NEUTRAL (v2: NO_RELEVANT_NEWS) | `causa` = BELOW_GATE; `max_score_own` null, `max_score_fanout` +0,2136; `quota_righe_fanout` 1,0; `funnel_v2.pipeline` = NO_RELEVANT_NEWS (TAG_UNCONFIRMED 1) |
| BA | +3,35% | (d) FILTERED (v2: RANKED_OUT) | `funnel_v2.righe[BA].pipeline` = RANKED_OUT, `reason_codes` SKIP_ENTRY_GATE, SKIP_ENTRY_FRESHNESS, RANK_LONG_ONLY; `max_score_own` +0,3712 ≥ gate; legacy `causa` NON_CLASSIFICATO |
| DIS | −3,40% | (b) THIN_NEUTRAL (legacy BELOW_GATE); v2 NON_ACTIONABLE long-only | `causa` = BELOW_GATE (`max_score_own` −0,1689, segno corretto); `esclusi_pipeline.non_actionable_long_only`; `net_opportunity_usd` 0 |

Testo degli articoli (news_log, evidenza qualitativa):
- **RDDT**: un solo articolo, alpaca_benzinga 16:37Z, «Reddit Stock Rises: What's Happening?» — commento tecnico («testing a floor that's held multiple times since July», range stabile), nessun catalizzatore societario. Opportunità v2: entry 146,49 (16:52Z), close 149,53, `net_opportunity_usd` +43,33; legacy 109,51. Residuo vs XLC +5,91%.
- **CRM**: un solo articolo, alpaca_benzinga 15:47Z, sui risultati Accenture FY26 Q4 («Accenture stock traded 19% higher… Cognizant, IBM, Wipro Rise»): catalizzatore di settore, CRM non è il soggetto. v2: entry 231,07, close 236,69, net +52,28; legacy 68,23.
- **BA**: 6 articoli. Il segnale più forte (13555, 13:32Z, ISSUER_SPECIFIC, +0,3712) è stato seguito alle 13:56Z da 13571 (+0,1324, ISSUER_SPECIFIC) che le `guard_decisions` usano per i cicli 14:07 e 14:22Z (SKIP_THRESHOLD su signal_id 13571). Possibile difetto (non limite noto): vedi F-023 in §8. v2: entry 186,455 (14:07Z), close 192,28, net +67,50; legacy 73,67.

Mover non-miss:
| Simbolo | Return | Stato | Campo |
|---|---|---|---|
| AMAT | +3,50% | detenuto S1, PASSIVE_EXPOSURE | `funnel_v2.righe` held_rising; `copertura_uscita` ritorno_da_ingresso −10,86% (3 righe news) |
| MU | +3,03% | detenuto S4, PASSIVE_EXPOSURE | `funnel_v2.righe` held_rising; ritorno_da_ingresso +12,11% (25 righe news) |
| GM | +3,00% | detenuto S1, PASSIVE_EXPOSURE; chiuso intraday `portfolio_sell` | `funnel_v2.righe` held_rising; `chiusure` GM −8,28 $, drift_post_uscita +26,03 |

Catturato:
| Simbolo | Ingresso | mtm_eod | Chiusura | pnl_net | drift_post_uscita |
|---|---|---|---|---|---|
| INFY (+5,48%) | S4 14:52Z @11,39, percentile 0,142, quota prima del segnale 0,60, quota_nel_gap 1,17; `pipeline` BAD_FILL | −5,32 | `hold_minimum_expiry` @11,38 dopo 1,75 h | −2,18 | −3,99 (uscire ha risparmiato) |

Giudizio INFY: ingresso 7 minuti dopo la headline GDELT delle 14:45Z («Accenture Soars 23%… Infosys Jumps 8%»), cioè a movimento già in corso (`vs_apertura` −13,30 $); `evidence.eod_net_pnl` −6,17 $ se tenuto al close (`funnel_v2`, close 11,35 < fill 11,39) — il titolo ha chiuso +5,48% sul close precedente ma sotto il fill.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["TXN","AZN","IWM","NVDA","ARM","INFY","SPCX","MSFT","HOOD"],"chiusure":["JPM","GM","UBS","MS","SBUX","VALE","XLF","UNH","INFY","MSFT","SPCX","HOOD"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | TXN | S1 | 14:07 | $279.7600 | 3.6564 | — | percentile 29.89%; denominatore intraday degenere: quota non interpretabile |
| IN | AZN | S1 | 14:07 | $160.2900 | 6.3816 | — | percentile 72.66%; denominatore intraday valido |
| IN | IWM | S1 | 14:07 | $275.9500 | 3.7069 | — | percentile 9.69%; denominatore intraday valido |
| IN | NVDA | S1 | 14:07 | $230.3600 | 4.4405 | — | percentile 53.33%; denominatore intraday degenere: quota non interpretabile |
| IN | ARM | S1 | 14:07 | $288.5400 | 2.0439 | — | percentile 10.79%; denominatore intraday valido |
| IN | INFY | S4 | 14:52 | $11.3900 | 133.0140 | — | percentile 14.16%; denominatore intraday valido |
| IN | SPCX | S4 | 15:22 | $152.2400 | 9.9329 | — | percentile 80.13%; denominatore intraday valido |
| IN | MSFT | S4 | 15:37 | $513.2600 | 2.9343 | — | percentile 10.21%; denominatore intraday valido |
| IN | HOOD | S4 | 17:52 | $111.8200 | 13.5765 | — | percentile 36.83%; denominatore intraday valido |
| OUT | JPM | S1 | — | $326.5600 | 2.2781 | −$32.52 | portfolio_sell |
| OUT | GM | S1 | — | $76.7411 | 10.1314 | −$8.28 | portfolio_sell |
| OUT | UBS | S1 | — | $46.8500 | 13.0652 | −$69.35 | portfolio_sell |
| OUT | MS | S1 | — | $184.5700 | 0.0528 | −$2.39 | portfolio_sell |
| OUT | SBUX | S1 | — | $94.4800 | 6.5817 | −$72.18 | portfolio_sell |
| OUT | VALE | S1 | — | $13.2600 | 53.0034 | −$73.57 | portfolio_sell |
| OUT | XLF | S1 | — | $52.9700 | 13.6496 | −$47.10 | portfolio_sell |
| OUT | UNH | S1 | — | $365.1020 | 0.5926 | −$37.43 | portfolio_sell |
| OUT | INFY | S4 | — | $11.3800 | 133.0140 | −$2.18 | hold_minimum_expiry |
| OUT | MSFT | S4 | — | $514.5170 | 2.9343 | +$3.39 | hold_minimum_expiry |
| OUT | SPCX | S4 | — | $149.7692 | 9.9329 | −$26.13 | portfolio_sell |
| OUT | HOOD | S4 | — | $111.7300 | 13.5765 | −$2.06 | hold_minimum_expiry |
<!-- alpha-miss-book:end -->
9 ingressi (5 S1 alle 14:07Z: TXN, AZN, IWM, NVDA, ARM; 4 S4: INFY 14:52Z, SPCX 15:22Z, MSFT 15:37Z, HOOD 17:52Z) e 12 chiusure (8 S1 `portfolio_sell` con ore_tenuta 1.320–1.992 h, tutte in perdita, somma −342,82 $; 4 S4: 3 `hold_minimum_expiry`, 1 `portfolio_sell`, somma −26,99 $). I 4 ingressi S4 hanno tutti `mtm_eod` negativo (INFY −5,32, SPCX −41,42, MSFT −1,35, HOOD −9,10). `drift_post_uscita` positivo su 5 chiusure S1 (JPM +11,32, GM +26,03, UBS +9,41, VALE +10,07, XLF +6,69): le uscite S1 sono avvenute prima di un rialzo del titolo. Il cron sostituisce questa sezione col blocco riconciliato.

## 5. Cecità lato uscita
2 posizioni con `cieco_lato_uscita: true` (`n_cieche_lato_uscita` 2, `n_cieche_ancora_aperte` 1, `n_indeterminati` 0: nessun campo null; `notional_cieco_usd` aggregato 776,66):
| Ticker | Strategia | ritorno_da_ingresso | ritorno_seduta | sedute senza righe | fonti_osservate_finestra | Stato |
|---|---|---|---|---|---|---|
| SBUX | S1 | −10,35% (fino all'exit 94,48) | +0,98% | 2 | alpaca_benzinga, gdelt_gkg | uscita nella seduta (`portfolio_sell`, −72,18 $) |
| WDC | S4 | −15,78% (al close 462,56) | +1,78% | 2 | alpaca_benzinga | ancora aperta, notional 154,82 $ |

Le due misure di ritorno non coincidono: `ritorno_da_ingresso` è la perdita subita da detenuta; `ritorno_seduta` è il movimento del titolo fino al close (SBUX +0,98% dopo l'uscita non è attribuito al book). Totale: 43 posizioni, 13 con copertura nulla, 22 con copertura effettiva nulla, 11 con perdita marcata.

## 6. Backstop NO_NEWS
- Mover NO_NEWS: 0 (`no_news_backstop.population.movers` 0; 28 zero-news tutti non-mover). Marker CALENDAR: sui mover 0/0 (n.d.); sui non-mover zero-news 0/28 (`calendar_observation.non_mover_rate` 0,0). `observed_catalysts` vuoto su tutti e 28 (FMP earnings-calendar e Alpaca Corporate Actions riuscite).
- Volume EOD (**POST_HOC_EOD**, non è un segnale point-in-time, `valid_for_signal_evaluation: false`): mediana mover DATA_INCOMPLETE (n=0); mediana surprise non-mover −0,0262 (n=28). Solo descrittivo; la valutazione ex-ante è in #451.
- Copertura raw `news_log` per settore (distinta dalla effective-timely di `copertura_articoli.per_settore`):

| Settore | ticker_with_news/universe | raw_news_coverage_rate | zero-news | mover zero-news | CALENDAR su zero-news |
|---|---|---|---|---|---|
| consumer | 6/11 | 54,5% | 5 | 0 | 0 |
| energy | 4/6 | 66,7% | 2 | 0 | 0 |
| etf_broad | 4/4 | 100,0% | 0 | 0 | 0 |
| financials | 10/14 | 71,4% | 4 | 0 | 0 |
| healthcare | 6/9 | 66,7% | 3 | 0 | 0 |
| industrials | 3/4 | 75,0% | 1 | 0 | 0 |
| materials | 0/2 | 0,0% | 2 | 0 | 0 |
| media | 3/5 | 60,0% | 2 | 0 | 0 |
| semis | 11/15 | 73,3% | 4 | 0 | 0 |
| tech | 17/21 | 81,0% | 4 | 0 | 0 |
| telecom | 4/5 | 80,0% | 1 | 0 | 0 |

### Attribuzione fonti (FASE 5)
Ticker con `articoli_unici == 0` / `fonti_osservate` vuoto: 28, tutti con `articoli_unici_giorno` 0 e `effective_timely_articles_giorno` 0 (`blind_set.per_ticker`) e `fonti_osservate` `{}` (zero resa dei provider, non fonte non configurata): ASML, AZN, BIDU, BRK.B, CMCSA, DB, ERIC, F, HD, JNJ, MCD, MMM, MRK, PANW, PBR, PG, QCOM, RIO, ROKU, SAP, SBUX, SHEL, SNOW, TXN, UBS, V, VALE, WDC.

Fonte presente ma nessuna effective-timely (19 ticker, tutti alpaca_benzinga; formato righe/effective-timely): AMD 1/0, ARM 1/0, BABA 1/0, CAT 2/0, COST 1/0, CRM 1/0, CSCO 1/0, CVX 1/0, GE 1/0, IWM 2/0, JD 1/0, JPM 2/0, MA 1/0, MRVL 3/0, QQQ 5/0, SPY 24/0, TMUS 1/0, VZ 3/0, XLF 2/0. Es.: «la fonte alpaca_benzinga ha reso 1 riga su CRM, ma nessuna effective-timely» (TAG_UNCONFIRMED, articolo Accenture).

## 7. Pattern osservato
Tema parziale: **IT services / software dopo i risultati Accenture** (articoli del 15:47Z e GDELT 14:45Z: ACN +19–23%): INFY +5,48%, CRM +3,10%, NOW +2,80%, IBM +2,59% (sotto soglia), XLK +1,05%. Gli altri mover non rientrano nel tema: AMAT/MU (semis/memorie), BA, GM, RDDT (commento tecnico). Lato ribassista: DIS −3,40%, e healthcare debole (XLV −1,32%, AZN −2,33%, JNJ −2,30%). Ricorrenza: il 09-30 il mover NOW era già descritto come «relief bid across the software sector»; due sedute consecutive con leg software/IT in rialzo. Nessun'altra ricorrenza dichiarabile.

## 8. Segnalazioni

* **[F-011]** execution_decisions.signal_id NULL: regressione di copertura su BUY, SELL e SKIP_PYRAMIDING.
  * esposizione: `decision_signal_id_coverage`: SELL 0/12, BUY 4/9, SKIP_PYRAMIDING 1/29, totale 809/854 (94,73%); `regressions` = BUY, SELL, SKIP_PYRAMIDING. Ledger: 34 giorni distinti, 36 occorrenze (findings.json; longitudinal_panels.json non esiste).
  * evidenza contraria: signal_id pieno sulle SELL/BUY: oggi SELL 0/12 e BUY 4/9, il finding regge e si estende ai BUY (il 09-30 erano BUY 3/3).
  * non-occorrenza: SKIP_THRESHOLD 763/763 e SKIP_FALLBACK 41/41 con signal_id.
  * next evidence: lettura di `execution_decisions` per le 12 SELL e i 5 BUY senza signal_id (id, motivo), sola lettura.
  * meccanismo e fonte: §3/§4, `decision_signal_id_coverage.by_reason_code`.
  * costo: non stimabile (catena segnale→decisione→trade non ricostruibile per chiave esterna), null.

* **[F-023]** BA: un segnale forte (+0,3712, 13:32Z) è stato sovrascritto da uno più debole (+0,1324, 13:56Z) e il mover +3,35% non è stato comprato.
  * esposizione: 1 mover ENTRY_OPPORTUNITY con ≥1 segnale ISSUER_SPECIFIC sopra gate oggi. Ledger: 20 giorni distinti, 25 occorrenze.
  * evidenza contraria: se S4 usasse il segnale con |score| massimo, le `guard_decisions` di BA citerebbero 13555 e non 13571; citano 13571 (SKIP_THRESHOLD alle 14:07 e 14:22Z). Resta la possibilità che 13555 fosse oltre `max_signal_age`/freshness (SKIP_ENTRY_FRESHNESS fra i reason_codes): il dossier non separa le due cause.
  * non-occorrenza: negli altri due ENTRY_OPPORTUNITY (RDDT, CRM) il segnale più recente coincide col più forte (un solo segnale ciascuno).
  * next evidence: per BA confrontare `signal_id` 13555 vs 13571 nel ciclo 14:07Z (età segnale, score, ranking) in `s4_intent_events`, sola lettura.
  * meccanismo e fonte: §3, `funnel_v2.righe[BA]` (RANKED_OUT, SKIP_ENTRY_GATE/FRESHNESS/RANK_LONG_ONLY) e `candidati_miss[BA].segnali`. Se confermato è un difetto, non un limite noto; decisione sull'issue = operatore.
  * costo (congetturale, serie legacy): |return| × size = 0,033486 × 2.200 = 73,67 $; v2: accessibile 68,73 $, netto 67,50 $.

* **[F-009]** Gate S4 0,30 scarta un segno corretto su un mover: CRM +3,10% con score +0,2136.
  * esposizione: 1 mover con segnale di segno corretto sotto gate (CRM; RDDT +0,0218 è sotto `thin` 0,05, non vicino al gate). Ledger: 24 giorni distinti su 43 sedute, 25 occorrenze.
  * evidenza contraria: lo score di CRM viene da un articolo fan-out su Accenture (`attribution` FANOUT, `max_score_own` null): l'enforcement del gate qui non è un'anomalia (F-012); la v2 dà `net_opportunity_usd` +52,28, quindi il costo accessibile esiste ma non da un segnale issuer-specifico.
  * non-occorrenza: nessun altro mover ENTRY_OPPORTUNITY con score issuer sotto gate di segno corretto tranne RDDT (sotto `thin`).
  * next evidence: aggregare `net_opportunity_usd` v2 sulle occorrenze F-009, separando score own da fan-out (sola lettura).
  * meccanismo e fonte: §3, `candidati_miss[CRM]` (`max_score_fanout` 0,2136 < `soglia_gate_usata` 0,30) e `funnel_v2.pipeline` NO_RELEVANT_NEWS.
  * costo (legacy): 0,031015 × 2.200 = 68,23 $ (congetturale); v2 netto 52,28 $. Alternativa scartata: usare RDDT (+109,51 legacy): score 0,0218 è rumore sotto `thin`, non un caso di gate.

## 9. Appendice

### (a) Rendimenti watchlist (`mercato.rendimenti`, alto → basso)
| Simbolo | Return |
|---|---|
| INFY | +5,48% |
| RDDT | +4,98% |
| AMAT | +3,50% |
| BA | +3,35% |
| CRM | +3,10% |
| MU | +3,03% |
| GM | +3,00% |
| NOW | +2,80% |
| IBM | +2,59% |
| NOK | +2,27% |
| XLE | +1,95% |
| CAT | +1,92% |
| WDC | +1,78% |
| F | +1,74% |
| PLTR | +1,60% |
| MRVL | +1,46% |
| CVX | +1,42% |
| SOXX | +1,35% |
| BP | +1,16% |
| SAP | +1,11% |
| NVDA | +1,09% |
| CSCO | +1,05% |
| XLK | +1,05% |
| SBUX | +0,98% |
| ARM | +0,93% |
| SNOW | +0,72% |
| JPM | +0,71% |
| ERIC | +0,71% |
| DELL | +0,70% |
| TSM | +0,66% |
| XOM | +0,66% |
| AMD | +0,65% |
| SHEL | +0,59% |
| ORCL | +0,56% |
| ADBE | +0,56% |
| PBR | +0,53% |
| BRK,B | +0,51% |
| COST | +0,51% |
| TXN | +0,44% |
| IWM | +0,41% |
| MCD | +0,39% |
| WMT | +0,33% |
| QQQ | +0,31% |
| VALE | +0,30% |
| WFC | +0,25% |
| VZ | +0,24% |
| SPY | +0,18% |
| V | +0,14% |
| TM | +0,13% |
| XLF | +0,11% |
| META | +0,10% |
| GE | +0,03% |
| MSFT | -0,02% |
| MS | -0,04% |
| BABA | -0,08% |
| SONY | -0,17% |
| ASML | -0,18% |
| INTC | -0,19% |
| TSLA | -0,20% |
| MA | -0,27% |
| PANW | -0,27% |
| CMCSA | -0,28% |
| AMZN | -0,37% |
| T | -0,41% |
| GS | -0,41% |
| UNH | -0,51% |
| LLY | -0,62% |
| ABBV | -0,63% |
| AXP | -0,66% |
| ROKU | -0,67% |
| MMM | -0,69% |
| NKE | -0,71% |
| HD | -0,71% |
| AAPL | -0,81% |
| TMUS | -0,83% |
| JD | -0,86% |
| PG | -0,92% |
| MRK | -1,03% |
| QCOM | -1,06% |
| UBS | -1,16% |
| HOOD | -1,20% |
| BAC | -1,29% |
| XLV | -1,32% |
| NVO | -1,35% |
| RIO | -1,38% |
| PFE | -1,40% |
| BIDU | -1,47% |
| GOOGL | -1,70% |
| SPCX | -1,85% |
| C | -1,92% |
| DB | -2,12% |
| AVGO | -2,15% |
| JNJ | -2,30% |
| AZN | -2,33% |
| NFLX | -2,49% |
| DIS | -3,40% |

### (b) Altri finding aperti toccati dalla giornata
- [F-030] supported: INFY ingresso 14:52Z con quota prima del segnale 0,60 e quota_nel_gap 1,17 (headline GDELT 14:45Z a movimento in corso); net_pnl −2,18 $.
- [F-012] supported: CRM 100% fan-out (`quota_righe_fanout` 1,0); BA 2/6 articoli TAG_UNCONFIRMED con score −0,34 e +0,17; articoli ACN/IBM/Wipro mappati su CRM.
- [F-031] not_exposed: nessun SKIP_PYRAMIDING su un mover; 28 SKIP_PYRAMIDING senza signal_id (rientrano in F-011).
- [F-089] supported: SPCX (S4) chiusa `portfolio_sell` dopo 2,75 h con −26,13 $, drift_post_uscita −16,88 (S1 `portfolio_sell` simultanei suggeriscono ribilanciamento mensile; non verificato).
- [F-001] contradicted: nessun mover NO_NEWS oggi (28 zero-news, tutti non-mover).

### (c) Casi di successo
Nessun mover catturato con P&L positivo (profitable_capture_rate 0/4). Unico trade S4 positivo: MSFT +3,39 $ (`hold_minimum_expiry`), non mover.
