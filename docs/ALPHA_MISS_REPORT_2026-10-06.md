# Alpha-miss report 2026-10-06

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-16T08:00:33Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. 8 mover |ret|>=3% su 96 simboli (6 su, 2 giù); 6 erano già a libro all'open (held_at_open_rate 6/8). L'unico miss di giornata è INTC −3,18%, che con il book long-only non era tradabile (NON_ACTIONABLE): oggi non c'è nessun miss d'ingresso.
2. Unico mover d'ingresso tradato: AVGO +3,67%. L'ingresso S4 è delle 17:52 a entry_percentile 0,948, con quota_movimento_precedente_al_segnale 1,47 (BAD_FILL). L'uscita per hold_minimum_expiry dopo 1,75 h ha chiuso a pnl_net −11,32 $.
3. WDC (S4, residuo 0,3347 azioni) chiude −6,93% e arriva a −25,16% dall'ingresso. In uscita resta EXIT_WRONG_SIGN (score_firmato +0,08), con WARNING #161 "unprotected" a ogni ciclo dalle 14:07 alle 19:52 e nessun alert.

## 2. Stato carta
as_of economic_pnl.json: **2026-09-17** (generato 2026-09-18). Il file non copre le sedute dal 2026-09-18 al 2026-10-06: i numeri qui sotto sono quelli dichiarati nel file, non stime.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni; soglia carta 0,6; superata: no.
- S4 economico cumulato −696,33 $ contro ±200 $: fuori banda (within=false). S1 +664,95 $ (delta vs SPY −279,03 $); BOOK −66,22 $.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| INTC | −3,18% | non conteggiato (NON_ACTIONABLE, long-only) | `funnel_v2.righe[INTC].actionability` = NON_ACTIONABLE, `pipeline_escluso_motivo` = non_actionable_long_only; `opportunity_v2.accessible_opportunity_usd` = 0; `causa_legacy` NON_CLASSIFICATO |

Conteggi legacy: NO_NEWS 0, THIN_NEUTRAL 0, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. Il criterio è lo stesso del 2026-10-02 (NKE): un mover in calo, non detenuto, con book long-only non entra nei conteggi. Se lo si leggesse in legacy sarebbe un WRONG_SIGN sotto gate. `max_score_own` vale +0,1807 (Mizuho "Raises Price Target to $114", 13:57) contro un movimento di −3,18%. Il massimo fan-out +0,6774 è un articolo su Marvell (fallback, TAG_UNCONFIRMED) e `quota_righe_fanout` è 0,8.

Testo degli articoli (evidenza qualitativa, dati non fidati): nessuna delle 5 righe INTC spiega il calo. Due sono positive su Intel (alzata di target Mizuho, partnership con Applied Materials). Le altre tre parlano di AMD, FieldAI e Marvell. Il catalizzatore deterministico del dossier è ANALYST, il residuo vs SOXX −3,17% e il volume/ADV 0,92.

Mover catturati (in portafoglio o tradati, 7):

| Simbolo | Return | Stato | Esito (dal dossier) |
|---|---|---|---|
| AVGO | +3,67% | CAUGHT, ingresso S4 17:52 (trade 1055, signal 14315) | v2 BAD_FILL: fill 379,96, close 375,81, eod_net_pnl −18,03 $. Uscita 19:37 a 377,43 per hold_minimum_expiry, pnl_net −11,32 $, drift_post_uscita −6,71 $ |
| NOK | +7,55% | S1 detenuta (PASSIVE_EXPOSURE, held_rising) | residuo 0,564 azioni, notional 6,19 $; ritorno_da_ingresso −6,40% |
| MRVL | +5,81% | S4 detenuta (PASSIVE_EXPOSURE) | ritorno_da_ingresso +24,23%; investor day ("Targets Smash Wall Street Estimates"); 2 SKIP_PYRAMIDING (14:22, 18:37) |
| CSCO | +4,54% | S4 detenuta (PASSIVE_EXPOSURE) | ritorno_da_ingresso +6,19%; zero righe news_log nella seduta |
| DELL | +3,93% | S1 detenuta (PASSIVE_EXPOSURE) | ritorno_da_ingresso +34,21% |
| PANW | +3,23% | S4 detenuta (PASSIVE_EXPOSURE) | ritorno_da_ingresso +12,16% |
| WDC | −6,93% | S4 detenuta (EXIT_RISK, `pipeline_uscita` EXIT_WRONG_SIGN) | `evidence_uscita.score_firmato` +0,08; ritorno_da_ingresso −25,16%; notional 137,57 $ |

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["AVGO","NOW","SPCX"],"chiusure":["SPCX","BA","AVGO"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | AVGO | S4 | 17:52 | $379.9565 | 4.1392 | — | percentile 94.75%; denominatore intraday valido |
| IN | NOW | S4 | 18:37 | $136.7600 | 11.5098 | — | percentile 13.12%; denominatore intraday degenere: quota non interpretabile |
| IN | SPCX | S4 | 18:37 | $171.8000 | 9.1623 | — | percentile 8.24%; denominatore intraday degenere: quota non interpretabile |
| OUT | SPCX | S4 | — | $173.7854 | 9.2812 | +$58.70 | portfolio_sell |
| OUT | BA | S4 | — | $190.8000 | 8.0642 | −$17.79 | portfolio_sell |
| OUT | AVGO | S4 | — | $377.4300 | 4.1392 | −$11.32 | hold_minimum_expiry |
<!-- alpha-miss-book:end -->
Nella seduta ci sono 3 ingressi S4 (AVGO 17:52, NOW e SPCX 18:37) e 3 chiusure S4. Le chiusure sono SPCX (portfolio_sell, +58,70 $), BA (portfolio_sell, −17,79 $) e AVGO (hold_minimum_expiry, −11,32 $), per un realizzato netto di +29,58 $, tutto S4.

NOW e SPCX sono entrate in basso nel range della giornata (entry_percentile 0,13 e 0,08), ma su un denominatore degenere (`denominatore_degenere: true`). AVGO invece è entrata quasi al massimo (0,948).

Tutte e tre le uscite hanno drift_post_uscita negativo (SPCX −17,31, BA −7,90, AVGO −6,71 $): in ciascun caso i titoli hanno continuato a scendere dopo la vendita. I 3 BUY hanno signal_id, i 3 SELL no (`decision_signal_id_coverage.regressions: ["SELL"]`).

## 5. Cecita' lato uscita
Nessuna posizione con `cieco_lato_uscita: true` su 41. Non c'è nessun null: n_indeterminati è 0 e il notional cieco è 0 $.

Ci sono 5 perdite marcate (≤ −3% dall'ingresso), tutte con righe news nella seduta o con uno streak di sedute senza righe sotto le 2 richieste: AMAT −10,70%, C −3,38%, NOK −6,40%, PFE −4,15%, WDC −25,16%. Per NOK la perdita è accumulata prima di oggi (ritorno_seduta +7,55%). WDC non è cieca: ha 4 righe e 4 segnali nella seduta. Il problema lì è il segno del segnale letto, non la copertura (vedi §8, F-036).

## 6. Backstop NO_NEWS
L'unico mover nella popolazione zero_news è CSCO (+4,54%), che è detenuto da S4 e quindi non è un miss. `observed_catalysts` è vuoto e il calendario è NOT_OBSERVED, con FMP earnings-calendar e Alpaca Corporate Actions entrambe riuscite. Nessun marker CALENDAR: mover_observed 0/1, non-mover 0/32.

Volume EOD (POST_HOC_EOD, valid_for_signal_evaluation=false): la surprise mediana è +0,126 sull'unico mover e −0,151 sui 32 non-mover. È una misura sull'intera seduta: non era disponibile prima del movimento, e non se ne ricava né una soglia né un tasso di falsi positivi (la valutazione ex-ante è in #451).

Popolazione zero_news: 33 (1 mover, 32 non-mover).

Copertura raw di `news_log` per settore (diversa dalla copertura effective-timely di `copertura_articoli.per_settore`):

| Settore | ticker_with_news/universe | raw_news_coverage_rate | mover zero-news | calendario osservato zero-news |
|---|---|---|---|---|
| consumer | 8/11 | 72,7% | 0 | 0 |
| energy | 4/6 | 66,7% | 0 | 0 |
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| financials | 9/14 | 64,3% | 0 | 0 |
| healthcare | 5/9 | 55,6% | 0 | 0 |
| industrials | 3/4 | 75,0% | 0 | 0 |
| materials | 0/2 | 0,0% | 0 | 0 |
| media | 1/5 | 20,0% | 0 | 0 |
| semis | 12/15 | 80,0% | 0 | 0 |
| tech | 15/21 | 71,4% | 1 | 0 |
| telecom | 2/5 | 40,0% | 0 | 0 |

Per confronto, la copertura effective-timely (`copertura_articoli.per_settore`) è 46/96 complessiva. Industrials e materials sono a 0/4 e 0/2, telecom a 2/5.

### Attribuzione fonti per ticker (#511)
Ci sono 33 ticker con `articoli_unici == 0` e `fonti_osservate` vuoto. Per tutti, `blind_set.per_ticker` riporta articoli_unici_giorno 0 ed effective_timely_articles_giorno 0: nessuna fonte ha reso nulla, quindi non è il caso di una fonte presente ma inutile. I ticker sono: ADBE, ARM, ASML, AZN, BAC, BIDU, BP, C, CMCSA, COST, CSCO, ERIC, INFY, JD, MA, MMM, MRK, NFLX, NVO, PBR, PFE, RDDT, RIO, ROKU, SNOW, TM, TMUS, TXN, UBS, VALE, VZ, WFC, WMT.

Gli streak a zero articoli più lunghi sono ERIC (10 sedute, troncato dall'inizio della finestra), BIDU, RIO e ROKU (8), MMM (7), TXN (6) e ASML (5). Sono questi i ticker in `ticker_allerta_zero_articoli`.

Altri ticker hanno `fonti_osservate` non vuoto ma effective-timely a zero. Per BA, CAT, F, GE, GM, LLY, SHEL, SOXX e V alpaca_benzinga ha reso 1 riga, ma nessuna effective-timely. Lo stesso vale per HOOD, IWM, NKE e QCOM con 2 righe, per HD, XLE e XLV con 3 e per QQQ con 8. Tutte queste righe sono TAG_UNCONFIRMED.

## 7. Pattern osservato
Il tema è l'infrastruttura AI di rete e hardware: MRVL +5,81% (investor day), CSCO +4,54%, DELL +3,93%, AVGO +3,67%, PANW +3,23%, AMD +2,80%. NOK +7,55% ed ERIC +2,28% sono coerenti con lo stesso filone networking, ma per loro il dataset non ha notizie (zero righe).

Il lato debole è storage e semis legacy: WDC −6,93% ("Western Digital Stock Drops Tuesday"), INTC −3,18%, AMAT −2,21%, MU −1,73%. SOXX è piatto (−0,01%), quindi è una dispersione interna ai semis e non un movimento del settore.

Questo pattern si ripete. Il report del 2026-10-02 aveva come tema "rotazione verso semis/hardware AI contro storage (WDC −10,22%)": oggi la stessa rotazione si vede per la seconda volta in tre sedute.

## 8. Segnalazioni
Denominatori: longitudinal_panels.json non esiste, quindi i conteggi vengono dalle occorrenze di findings.json (occorrenze registrate, non giorni distinti verificati).

* **[F-030]** AVGO, l'unico ingresso su un mover della seduta, è entrato dopo che l'intero movimento intraday era già avvenuto: `quota_movimento_precedente_al_segnale` 1,47, entry_percentile 0,948, BAD_FILL. Occorrenze registrate prima di oggi: 27 (24 giorni distinti).
  - esposizione: 3 ingressi S4. Uno solo è su un mover (AVGO) e ha un denominatore non degenere. NOW e SPCX hanno `denominatore_degenere: true`, quindi non sono valutabili per questo finding.
  - evidenza contraria: se il finding fosse falso, l'articolo d'ingresso precederebbe il movimento e l'ingresso starebbe in basso nel range. Invece il segnale 14315 (0,3112, "Broadcom Pairs Custom TPU Chips with $60 Billion Debt Package", pubblicato 17:35) arriva dopo il rally del mattino. Già alle 16:50 c'era il fallback 14285 (0,4177, Cramer su Marvell/Broadcom), escluso dal ranking #108.
  - non-occorrenza: MRVL, il driver del tema, era già a libro dall'ingresso precedente (ritorno_da_ingresso +24,23%). Nessun ingresso tardivo sui movimenti della giornata ne ha preso il posto.
  - next evidence: distribuzione read-only di `quota_movimento_precedente_al_segnale` sugli ingressi archiviati con denominatore non degenere, contro il pnl realizzato. È già in `aggregati.late_entry_joint_distribution`: fascia ≥1,0, n 32, somma −241,41 $, mediana −2,98 $.
  - meccanismo e fonte: §3–§4; `ingressi[AVGO]`, `funnel_v2.righe[AVGO].evidence`, `chiusure[AVGO]`.
  - costo (misurato): pnl_net realizzato di AVGO = −11,32 $ (trade 1055). Il mark EOD alternativo (eod_net_pnl −18,03 $) non è stato realizzato.
  - alternative scartate: "fill cattivo per slippage". Non regge: il fill a 379,96 è coerente con l'ora d'ingresso, e il problema è il ritardo del segnale rispetto al movimento, non l'esecuzione.
* **[F-036]** WDC (S4, sub-share) arriva a −25,16% dall'ingresso. Il worker emette WARNING #161 "unprotected" da −23,9% (14:07) a −25,4% (19:52) a ogni ciclo, ma nessun alert risulta inviato. Occorrenze registrate: 4.
  - esposizione: 1 posizione oltre −15/−20% dall'ingresso (WDC), su 41 detenute. È esposta per l'intera seduta.
  - evidenza contraria: se il finding fosse falso, nei log della seduta ci sarebbe un invio Telegram o un evento d'allerta per WDC/#161. grep su `logs/containers/*-2026-10-06.log`: solo righe WARNING del worker, nessun invio collegato.
  - non-occorrenza: AMAT (−10,70%) e NOK (−6,40%) sono in perdita ma sotto la soglia di revisione, e il trigger lì giustamente non scatta.
  - next evidence: conteggio read-only, sulle sedute archiviate, delle righe "#161: X unprotected at" con perdita oltre −15%, contro le righe di invio alert nello stesso intervallo.
  - meccanismo e fonte: §3, `funnel_v2.righe[WDC]` (EXIT_RISK, EXIT_WRONG_SIGN, score_firmato +0,08), `copertura_uscita.posizioni[WDC]`. Il segnale −0,24 delle 17:55 ("Western Digital Stock Drops Tuesday", fallback) aveva il segno giusto ma non è quello letto dal funnel.
  - costo: perdita della seduta sul residuo = notional_close × r/(1+r) = 137,57 × 0,0693/0,9307 = 10,24 $ (congetturale).
  - alternative scartate: "la posizione non è significativa". Il notional è piccolo (137,57 $), ma il finding riguarda il canale d'allerta, non la size. Lo stesso silenzio vale per qualunque size.
* **[F-023]** AVGO: il segnale del BUY (14315, 0,3112) viene sostituito alle 18:57 da 14348 (0,0063, articolo fan-out "Warren Buffett Said Buy the S&P 500 — But This ETF…"). Il worker logga "Hold minimum (90 min): skipped 1 SELL" alle 19:07 e "Exit hysteresis … held AVGO" alle 19:22, poi vende alle 19:37. Occorrenze registrate: 28.
  - esposizione: 3 ingressi S4. Solo AVGO chiude nella seduta, ed è esposto. NOW e SPCX restano aperti fino al 2026-10-07.
  - evidenza contraria: oggi c'è. drift_post_uscita è −6,71 $, quindi l'uscita guidata dalla sostituzione ha evitato un'ulteriore perdita. Il meccanismo si ripete, il danno economico no.
  - non-occorrenza: NOW (14337) e SPCX (14340) non sono stati sostituiti da un segnale più debole prima del close.
  - next evidence: lo stesso join già indicato il 2026-10-05, fra SELL hold_minimum_expiry e il signal_id letto al primo ciclo post-BUY, con il segno di drift_post_uscita, per vedere se la sostituzione ha un effetto netto non nullo.
  - meccanismo e fonte: §4; `chiusure[AVGO]`, `guard_decisions[AVGO]` (19:07 e 19:22 SKIP_THRESHOLD su 14348, 19:37 su 14366), worker log.
  - costo: drift_post_uscita AVGO = qty × (close − exit) = 4,1392 × (375,81 − 377,43) = −6,71 $, cioè un beneficio, non un costo (attribuito).
  - alternative scartate: "uscita per reversal". Non regge: 14348 e 14366 sono quasi zero (0,0063 e −0,025), non un'inversione sopra soglia.

## 9. Appendice
### (a) Rendimenti watchlist (`mercato.rendimenti`)

| # | Simbolo | Return |
|---|---|---|
| 1 | NOK | +7.55% |
| 2 | MRVL | +5.81% |
| 3 | CSCO | +4.54% |
| 4 | DELL | +3.93% |
| 5 | AVGO | +3.67% |
| 6 | PANW | +3.23% |
| 7 | AMD | +2.80% |
| 8 | ERIC | +2.28% |
| 9 | GM | +2.22% |
| 10 | WMT | +2.03% |
| 11 | HD | +1.97% |
| 12 | AMZN | +1.95% |
| 13 | NKE | +1.91% |
| 14 | CAT | +1.80% |
| 15 | SBUX | +1.78% |
| 16 | NFLX | +1.76% |
| 17 | MRK | +1.72% |
| 18 | PG | +1.69% |
| 19 | ORCL | +1.61% |
| 20 | PLTR | +1.41% |
| 21 | NOW | +1.39% |
| 22 | AZN | +1.33% |
| 23 | SONY | +1.32% |
| 24 | COST | +1.32% |
| 25 | SAP | +1.31% |
| 26 | LLY | +1.26% |
| 27 | SHEL | +1.14% |
| 28 | F | +1.07% |
| 29 | GE | +1.00% |
| 30 | BP | +0.87% |
| 31 | T | +0.79% |
| 32 | TXN | +0.79% |
| 33 | TM | +0.79% |
| 34 | MSFT | +0.78% |
| 35 | TMUS | +0.78% |
| 36 | JNJ | +0.73% |
| 37 | UBS | +0.60% |
| 38 | SPY | +0.55% |
| 39 | CVX | +0.54% |
| 40 | XLK | +0.53% |
| 41 | JD | +0.53% |
| 42 | TSLA | +0.51% |
| 43 | SPCX | +0.49% |
| 44 | XLE | +0.47% |
| 45 | QQQ | +0.46% |
| 46 | DB | +0.46% |
| 47 | MS | +0.44% |
| 48 | GS | +0.42% |
| 49 | DIS | +0.41% |
| 50 | MA | +0.35% |
| 51 | GOOGL | +0.35% |
| 52 | ABBV | +0.35% |
| 53 | PFE | +0.33% |
| 54 | XOM | +0.29% |
| 55 | VZ | +0.29% |
| 56 | MMM | +0.28% |
| 57 | BRK.B | +0.25% |
| 58 | V | +0.25% |
| 59 | RIO | +0.25% |
| 60 | XLF | +0.24% |
| 61 | AAPL | +0.22% |
| 62 | AXP | +0.17% |
| 63 | BAC | +0.17% |
| 64 | JPM | +0.17% |
| 65 | NVDA | +0.14% |
| 66 | QCOM | +0.13% |
| 67 | WFC | +0.09% |
| 68 | BIDU | +0.07% |
| 69 | SOXX | -0.01% |
| 70 | C | -0.02% |
| 71 | NVO | -0.03% |
| 72 | CMCSA | -0.05% |
| 73 | ARM | -0.11% |
| 74 | IBM | -0.13% |
| 75 | XLV | -0.17% |
| 76 | MCD | -0.25% |
| 77 | ADBE | -0.28% |
| 78 | META | -0.41% |
| 79 | VALE | -0.49% |
| 80 | UNH | -0.60% |
| 81 | IWM | -0.72% |
| 82 | TSM | -0.72% |
| 83 | ROKU | -0.88% |
| 84 | SNOW | -0.90% |
| 85 | RDDT | -0.98% |
| 86 | ASML | -1.39% |
| 87 | BABA | -1.39% |
| 88 | PBR | -1.41% |
| 89 | BA | -1.50% |
| 90 | MU | -1.73% |
| 91 | HOOD | -1.85% |
| 92 | INFY | -1.95% |
| 93 | CRM | -2.09% |
| 94 | AMAT | -2.21% |
| 95 | INTC | -3.18% |
| 96 | WDC | -6.93% |

### (b) Checklist altri finding aperti toccati dalla giornata
- [F-001] supported: 33/96 simboli a zero righe news_log; effective-timely 46/96; CSCO, mover detenuto, a zero righe; ERIC con streak di 10 sedute.
- [F-011] supported: 0/3 SELL con signal_id (`decision_signal_id_coverage.regressions: ["SELL"]`); 3/3 BUY con signal_id.
- [F-012] supported: 163/262 mapping TAG_UNCONFIRMED (`mapping_fanout_extra` 128); INTC ha quota_righe_fanout 0,8.
- [F-031] not_exposed sul caso S1→S4: i 10 SKIP_PYRAMIDING (es. MRVL, SPCX, BA) riguardano simboli già detenuti da S4 stessa. SPCX 14144 (0,4046) è bloccato alle 13:45.
- [F-074] / [F-094] supported (debole): 6 NameResolutionError verso data.alpaca.markets fra le 15:42 e le 15:53 nel worker log. Le guard_decisions MRVL saltano dalle 15:37 alle 16:07: il ciclo delle 15:52 non lascia decisioni.
- [F-056] supported (debole): per WDC il funnel legge +0,08 (14220) mentre il segnale più recente prima del close è −0,24 (14327, fallback); il meccanismo esatto non è verificato.
- [F-060] supported: il fallback AVGO 14285 (0,4177, sopra gate) è escluso dal ranking (#108, worker log "dropped N fallback signal(s)" alle 16:52–17:37 con AVGO in lista); il dossier non lo distingue come stadio a sé.

### (c) Casi di successo
- SPCX (trade 1054, ingresso del 2026-10-05): uscita portfolio_sell con pnl_net +58,70 $ e drift_post_uscita −17,31 $. Il titolo ha continuato a scendere dopo l'uscita. Non è un mover del giorno (+0,49%).
- Nessun mover catturato con P&L positivo nella seduta: AVGO, l'unico ingresso su un mover, ha chiuso a −11,32 $.
