# Alpha-miss report 2026-10-08

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-20T08:00:37Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. 17 mover |ret|>=3% su 96 simboli (6 su, 11 giù, dispersione 2,26%); 11 erano già a libro all'open (held_at_open_rate 11/17). Le due ENTRY_OPPORTUNITY, HD +3,39% (NO_NEWS, 0 righe) e ADBE +3,56% (BELOW_GATE), non hanno prodotto ordini: profitable_capture_rate 0/2.
2. 3 ingressi S4 (PLTR, SPCX, SAP) e 1 chiusura: SPCX −24,03 $ (hold_minimum_expiry dopo 1,75 h; il titolo ha chiuso −4,19%, drift_post_uscita −29,54 $).
3. NOK (S1, −13,48% da ingresso) e WDC (S4, −28,39% da ingresso) sono ciechi lato uscita: 0 righe news_log oggi e 2 sedute consecutive senza righe; exit_signal_recall 2/7.

## 2. Stato carta
as_of economic_pnl.json: **2026-09-17** (generato 2026-09-18). Il file non copre le sedute dal 2026-09-18 al 2026-10-07 né quella di oggi: i numeri sono quelli dichiarati nel file, non stime.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni; soglia carta 0,6; superata: no.
- S4 economico cumulato −696,33 $ contro ±200 $: fuori banda. S1 +664,95 $; BOOK −66,22 $.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---|---|---|
| HD | +3,39% | NO_NEWS | `candidati_miss[HD].causa` = NO_NEWS, `news_count` 0; `funnel_v2.righe[HD].pipeline` = NO_RELEVANT_NEWS, actionability ENTRY_OPPORTUNITY |
| ADBE | +3,56% | THIN_NEUTRAL | `candidati_miss[ADBE].causa` = BELOW_GATE; segnali +0,042 e −0,137 (ISSUER_SPECIFIC, non fallback), entrambi sotto il gate 0,30; `funnel_v2.righe[ADBE].pipeline` = BELOW_GATE |
| INTC | −5,34% | non conteggiato (NON_ACTIONABLE, long-only) | `funnel_v2.righe[INTC].pipeline_escluso_motivo` = non_actionable_long_only; `causa` BELOW_GATE (−0,135, fallback); `accessible_opportunity_usd` 0 |
| AVGO | −4,35% | non conteggiato (NON_ACTIONABLE, long-only) | `pipeline_escluso_motivo` = non_actionable_long_only; `causa` BELOW_GATE (−0,18, fallback, FANOUT); `accessible_opportunity_usd` 0 |
| ORCL | −5,48% | non conteggiato (NON_ACTIONABLE, long-only) | `pipeline_escluso_motivo` = non_actionable_long_only; `causa` NON_ACTIONABLE, `causa_legacy` NON_CLASSIFICATO; segnale −0,720 fallback FANOUT TAG_UNCONFIRMED; `accessible_opportunity_usd` 0 |

Conteggi: NO_NEWS 1, THIN_NEUTRAL 1, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0 (tre ribassi non detenuti non conteggiati, come INTC il 09-02/10-07). Conteggi dossier `cause_del_giorno`: BELOW_GATE 3, NO_NEWS 1, NON_CLASSIFICATO 1; dominante BELOW_GATE, quota_righe_fanout 0,8.

Testo letto (news_log, dato non fidato): ADBE 13:57 Benzinga «What's Going On With Adobe Stock Thursday?» — rimbalzo dopo un calo prolungato, titolo in salita con Nasdaq −0,57%; ADBE 14:30 un pezzo sul Labor Secretary che sospende grandi società di IT sourcing (corpo = solo un link), score −0,137 col segno opposto al movimento. INTC 14:59 «Intel Stock Is Falling Thursday» (calo ~2% con tech debole). ORCL e AVGO: lo stesso articolo macro «8 Of 11 Sectors Fall In Thursday Trading As Energy Leads» (n_ticker_articolo 19), a ORCL −0,720 e ad AVGO −0,18. HD: nessuna riga.

Mover detenuti (non sono miss, `funnel_v2.righe`): ARM −6,48% EXIT_BELOW_THRESHOLD (score −0,312); MU −4,79% EXIT_WRONG_SIGN (+0,08); NOK −4,52% STALE_EXIT_SIGNAL (14382 del 10-06, +0,148); AMD −3,90% EXIT_WRONG_SIGN (+0,048); MRVL −3,52% STALE_EXIT_SIGNAL (+0,23); SOXX −3,35% EXIT_BELOW_THRESHOLD (−0,078); TSM −3,01% EXIT_WRONG_SIGN (+0,23); PASSIVE_EXPOSURE su BP +4,16%, SHEL +3,46%, SNOW +3,17%, CVX +3,12%.

Catturati/tradati: 11 mover già a libro all'open + SPCX (mover −4,19%, comprato 14:37 @165,9445 e venduto prima del close): vedi §4.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["PLTR","SPCX","SAP"],"chiusure":["SPCX"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | PLTR | S4 | 14:37 | $201.0500 | 7.9693 | — | percentile 61.43%; denominatore intraday degenere: quota non interpretabile |
| IN | SPCX | S4 | 14:37 | $165.9445 | 9.6552 | — | percentile 78.22%; denominatore intraday valido |
| IN | SAP | S4 | 15:07 | $207.9000 | 7.6717 | — | percentile 26.89%; denominatore intraday valido |
| OUT | SPCX | S4 | — | $163.6300 | 9.6552 | −$24.03 | hold_minimum_expiry |
<!-- alpha-miss-book:end -->
Tre ingressi S4 e una chiusura (SPCX −24,03 $ dopo 1,75 h). Il mark EOD degli ingressi: PLTR −18,09 $ (vs_apertura −1,75; denominatore degenere, quota_movimento_precedente_al_segnale −9,32 non interpretabile), SPCX −51,89 $ se tenuto (vs_apertura −66,57; ingresso al percentile 0,78, quota_movimento_precedente 0,22), SAP +34,52 $ (percentile 0,27). L'uscita di SPCX ha evitato parte della discesa successiva (drift_post_uscita −29,54 $).

## 5. Cecita' lato uscita
Due posizioni con `cieco_lato_uscita: true` (soglia −3% da ingresso, `sedute_minime` 2; `n_cieche_lato_uscita` 2 su 39 posizioni, n_indeterminati 0, notional cieco 137,36 $):

| Ticker | Strategia | ritorno_da_ingresso | ritorno_seduta | sedute_consecutive_senza_righe | fonti_osservate_finestra | uscita nella seduta |
|---|---|---:|---:|---:|---|---|
| NOK | S1 | −13,48% | −4,52% | 2 | alpaca_benzinga, gdelt_gkg | no |
| WDC | S4 | −28,39% | −2,99% | 2 | alpaca_benzinga | no |

Nessun `cieco_lato_uscita` null. `perdita_marcata` su 6 posizioni; copertura_nulla 12/39, copertura_effettiva_nulla 20/39. Nel log worker, `held_news_loss_alert` (22:50 UTC, dopo il close) ha segnalato NOK e WDC (`alerted` 2).

## 6. Backstop NO_NEWS
Marker `CALENDAR`: nessuno sui 4 mover NO_NEWS (BP, HD, MRVL, NOK: `observed_catalysts` vuoto, calendario NOT_OBSERVED con FMP earnings-calendar e Alpaca Corporate Actions riuscite); l'unico CALENDAR della giornata è CRM (dividendo, non mover). mover_observed 0/4, non-mover 1/36 (CRM).

Volume EOD (POST_HOC_EOD, valid_for_signal_evaluation=false): surprise mediana +0,279 sui 4 mover e +0,102 sui 36 non-mover. Misura sull'intera seduta, non disponibile prima del movimento: nessuna soglia né false-positive rate (valutazione ex-ante in #451).

Popolazione zero_news: 40 (4 mover, 36 non-mover). Copertura raw di `news_log` per settore (distinta dalla effective-timely di `copertura_articoli.per_settore`):

| Settore | ticker_with_news/ticker_universe | raw_news_coverage_rate | zero_news | mover zero_news |
|---|---:|---:|---:|---:|
| consumer | 6/11 | 54,5% | 5 | 1 |
| energy | 4/6 | 66,7% | 2 | 1 |
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| financials | 9/14 | 64,3% | 5 | 0 |
| healthcare | 5/9 | 55,6% | 4 | 0 |
| industrials | 0/4 | 0,0% | 4 | 0 |
| materials | 0/2 | 0,0% | 2 | 0 |
| media | 2/5 | 40,0% | 3 | 0 |
| semis | 11/15 | 73,3% | 4 | 1 |
| tech | 15/21 | 71,4% | 6 | 0 |
| telecom | 0/5 | 0,0% | 5 | 1 |

Attribuzione fonti (FASE 5): 40 ticker con `articoli_unici` 0 e `fonti_osservate` vuoto (nessuna fonte ha reso righe; nessun caso "fonte presente ma non effective-timely" fra questi). `articoli_unici_giorno` = `effective_timely_articles_giorno` = 0 (`blind_set.per_ticker`) per tutti:

| Ticker | articoli_unici_giorno | effective_timely_articles_giorno | fonti_osservate |
|---|---:|---:|---|
| ABBV | 0 | 0 | {} |
| ASML | 0 | 0 | {} |
| AXP | 0 | 0 | {} |
| BA | 0 | 0 | {} |
| BIDU | 0 | 0 | {} |
| BP | 0 | 0 | {} |
| BRK.B | 0 | 0 | {} |
| CAT | 0 | 0 | {} |
| CMCSA | 0 | 0 | {} |
| COST | 0 | 0 | {} |
| CRM | 0 | 0 | {} |
| DB | 0 | 0 | {} |
| ERIC | 0 | 0 | {} |
| GE | 0 | 0 | {} |
| HD | 0 | 0 | {} |
| HOOD | 0 | 0 | {} |
| IBM | 0 | 0 | {} |
| INFY | 0 | 0 | {} |
| JD | 0 | 0 | {} |
| MMM | 0 | 0 | {} |
| MRVL | 0 | 0 | {} |
| NKE | 0 | 0 | {} |
| NOK | 0 | 0 | {} |
| NOW | 0 | 0 | {} |
| NVO | 0 | 0 | {} |
| PBR | 0 | 0 | {} |
| PFE | 0 | 0 | {} |
| PG | 0 | 0 | {} |
| RDDT | 0 | 0 | {} |
| RIO | 0 | 0 | {} |
| ROKU | 0 | 0 | {} |
| T | 0 | 0 | {} |
| TM | 0 | 0 | {} |
| TMUS | 0 | 0 | {} |
| TXN | 0 | 0 | {} |
| UBS | 0 | 0 | {} |
| UNH | 0 | 0 | {} |
| VALE | 0 | 0 | {} |
| VZ | 0 | 0 | {} |
| WDC | 0 | 0 | {} |

Altri ticker con articoli ma 0 effective-timely: fonte alpaca_benzinga ha reso 1 articolo ma nessuno effective-timely (es. AVGO, DIS, F, GM, IWM; elenco completo in `copertura_articoli.per_ticker`).

## 7. Pattern osservato
Rotazione energia su / semiconduttori e AI-hardware giù. Al rialzo energia (BP +4,16%, SHEL +3,46%, CVX +3,12%, XLE +2,97%, XOM +2,71%, PBR +2,92%); in calo ARM −6,48%, INTC −5,34%, MU −4,79%, AVGO −4,35%, AMD −3,90%, MRVL −3,52%, SOXX −3,35%, TSM −3,01%, più ORCL −5,48% e NOK −4,52%. SPY −0,42%, QQQ −1,34%, XLK −1,79%. Coerente con l'articolo Benzinga «8 Of 11 Sectors Fall… Energy Leads». Il tema semis/AI-hardware in calo ricorre rispetto al 10-06 (AI networking/hardware) e al 10-07 (MU unico rialzo, PANW/NOK in calo): non speculo oltre.

## 8. Segnalazioni

* [F-001] Copertura news bassa: 40/96 simboli a zero righe (era 32 il 10-07), HD (+3,39%) mover NO_NEWS.
  * esposizione: 96 simboli, 40 a zero righe (`mercato.watchlist_zero_news`); telecom 0/5, industrials 0/4, materials 0/2 di copertura raw; 4 mover a zero righe (BP, HD, MRVL, NOK), di cui 1 ENTRY_OPPORTUNITY. Denominatore da findings.json (longitudinal_panels.json assente): 46 occorrenze su 44 giorni distinti all'ultima occorrenza (2026-10-06).
  * evidenza contraria: se falso, HD avrebbe righe in news_log o `fonti_osservate` non vuoto; invece 0 righe e nessuna fonte, con provider interrogati sull'intera watchlist.
  * non-occorrenza: etf_broad 4/4 coperti, energy 4/6, semis 11/15; i 7 mover detenuti con segnale non sono miss; i 36 non-mover a zero righe non hanno costo.
  * next evidence: confrontare per le prossime sedute `no_news_backstop.per_sector` di telecom e industrials (9 ticker, 0 righe oggi) per distinguere vuoto del provider da vuoto del filtro.
  * meccanismo e fonte: §3 e §6; `candidati_miss[HD].news_count` 0, `copertura_articoli.per_ticker[HD]`.
  * costo: legacy |ret|×size = 0,0339×2200 = 74,67 $ (congetturale); alternativa scartata: HD era detenibile long (accessible), ma l'ingresso su un movimento già avvenuto (F-030) non è dimostrabile.
* [F-036] Posizione oltre −20% dall'ingresso senza alert in seduta: WDC (S4, 0,3347 azioni) a −28,39% da ingresso, cieca lato uscita.
  * esposizione: 1 posizione oltre la soglia (WDC), NOK a −13,48% sotto la soglia −15%; 9/39 posizioni non proteggibili (qty<1, log #161 14:07). Occorrenze in findings.json: 5 su 5 giorni distinti (ultima 2026-10-06, WDC).
  * evidenza contraria: se falso, un alert sarebbe partito in seduta. Contraddizione parziale: `held_news_loss_alert` ha alertato NOK e WDC alle 22:50 UTC, dopo il close (consegna non verificata); in seduta nessun alert sul trigger.
  * non-occorrenza: NOK (−13,48%) è sotto la soglia −15% e non è un caso; le 37 posizioni restanti non sono cieche.
  * next evidence: verificare read-only se l'alert 22:50 è stato recapitato (`mobile_events`/Telegram) e se un alert in seduta è tecnicamente possibile (qty<1, nessuno stop).
  * meccanismo e fonte: §5; `copertura_uscita.posizioni[WDC]` (ritorno_da_ingresso −0,2839, sedute_consecutive_senza_righe 2).
  * costo: qty × (close precedente − mark) = 0,3347 × (405,42 − 393,31) = 4,05 $ (perdita di seduta di WDC, congetturale; close precedente da mark_close/(1+ritorno_seduta)). Alternativa scartata: perdita da ingresso 0,3347 × (549,24 − 393,31) = 52,19 $, non attribuibile alla mancanza di alert (posizione non proteggibile da stop).
* [F-060] Classificatore causale: ORCL −5,48% con segnale fallback −0,720 (sopra il gate 0,30) esce `NON_CLASSIFICATO` nella serie legacy.
  * esposizione: 5 candidati miss, 1 NON_CLASSIFICATO (ORCL); `funnel_v2` lo marca NON_ACTIONABLE (long-only), senza stadio `pipeline`. Occorrenze in findings.json: 4 su 4 giorni distinti (ultima 2026-09-03).
  * evidenza contraria: se falso, ORCL sarebbe etichettato FALLBACK_REJECT/RANKED_OUT dal funnel; invece `pipeline` è null e `causa_legacy` resta NON_CLASSIFICATO.
  * non-occorrenza: INTC e AVGO (fallback sotto gate) escono correttamente BELOW_GATE; HD NO_NEWS; ADBE BELOW_GATE.
  * next evidence: confrontare `candidati_miss.causa_legacy` e `funnel_v2.righe.pipeline` sulle sedute con segnali fallback sopra gate non detenuti.
  * meccanismo e fonte: §3; `candidati_miss[ORCL].causa_legacy`, `segnali[0].fallback` true, `attribution` FANOUT.
  * costo: 0 $ (`accessible_opportunity_usd` = 0: ORCL in discesa, book long-only); costo legacy |ret|×size = 0,0548×2200 = 120,59 $ non realizzabile. Alternativa scartata: miss reale su ORCL, perché la serie v2 lo dichiara inaccessibile.

## 9. Appendice

### (a) Rendimenti watchlist (`mercato.rendimenti`)

| # | Simbolo | Return |
|---:|---|---:|
| 1 | BP | +4,16% |
| 2 | ADBE | +3,56% |
| 3 | SHEL | +3,46% |
| 4 | HD | +3,39% |
| 5 | SNOW | +3,17% |
| 6 | CVX | +3,12% |
| 7 | XLE | +2,97% |
| 8 | PBR | +2,92% |
| 9 | IBM | +2,77% |
| 10 | XOM | +2,71% |
| 11 | NFLX | +2,68% |
| 12 | MCD | +2,61% |
| 13 | RDDT | +2,46% |
| 14 | PLTR | +2,40% |
| 15 | WMT | +2,22% |
| 16 | WFC | +2,21% |
| 17 | TMUS | +2,18% |
| 18 | DIS | +2,17% |
| 19 | PG | +1,87% |
| 20 | SONY | +1,83% |
| 21 | TM | +1,69% |
| 22 | T | +1,61% |
| 23 | GM | +1,56% |
| 24 | CRM | +1,44% |
| 25 | INFY | +1,42% |
| 26 | NOW | +1,36% |
| 27 | CMCSA | +1,29% |
| 28 | AXP | +1,27% |
| 29 | VZ | +1,26% |
| 30 | AAPL | +1,11% |
| 31 | NKE | +1,11% |
| 32 | SAP | +1,08% |
| 33 | F | +1,07% |
| 34 | BRK.B | +0,95% |
| 35 | MMM | +0,90% |
| 36 | XLF | +0,89% |
| 37 | MA | +0,82% |
| 38 | V | +0,81% |
| 39 | ROKU | +0,71% |
| 40 | GE | +0,66% |
| 41 | COST | +0,60% |
| 42 | C | +0,60% |
| 43 | JPM | +0,56% |
| 44 | ERIC | +0,42% |
| 45 | ABBV | +0,39% |
| 46 | DB | +0,24% |
| 47 | RIO | +0,19% |
| 48 | BAC | +0,17% |
| 49 | IWM | −0,05% |
| 50 | META | −0,06% |
| 51 | NVO | −0,21% |
| 52 | TXN | −0,27% |
| 53 | MRK | −0,29% |
| 54 | BA | −0,30% |
| 55 | XLV | −0,39% |
| 56 | SBUX | −0,40% |
| 57 | SPY | −0,42% |
| 58 | JD | −0,44% |
| 59 | GS | −0,52% |
| 60 | QCOM | −0,63% |
| 61 | GOOGL | −0,63% |
| 62 | PFE | −0,64% |
| 63 | TSLA | −0,74% |
| 64 | UBS | −0,76% |
| 65 | DELL | −0,76% |
| 66 | JNJ | −0,76% |
| 67 | AZN | −0,84% |
| 68 | MS | −1,20% |
| 69 | BABA | −1,21% |
| 70 | UNH | −1,34% |
| 71 | QQQ | −1,34% |
| 72 | MSFT | −1,35% |
| 73 | VALE | −1,40% |
| 74 | LLY | −1,61% |
| 75 | BIDU | −1,62% |
| 76 | PANW | −1,74% |
| 77 | XLK | −1,79% |
| 78 | ASML | −1,95% |
| 79 | AMAT | −2,13% |
| 80 | CSCO | −2,13% |
| 81 | CAT | −2,17% |
| 82 | AMZN | −2,25% |
| 83 | HOOD | −2,28% |
| 84 | NVDA | −2,94% |
| 85 | WDC | −2,99% |
| 86 | TSM | −3,01% |
| 87 | SOXX | −3,35% |
| 88 | MRVL | −3,52% |
| 89 | AMD | −3,90% |
| 90 | SPCX | −4,19% |
| 91 | AVGO | −4,35% |
| 92 | NOK | −4,52% |
| 93 | MU | −4,79% |
| 94 | INTC | −5,34% |
| 95 | ORCL | −5,48% |
| 96 | ARM | −6,48% |

### (b) Altri finding toccati
* [F-011] supported: `decision_signal_id_coverage` SELL 0/1 con signal_id (regressions ["SELL"]); BUY 3/3, SKIP_THRESHOLD 523/523.
* [F-012] supported: `quota_righe_fanout` 0,8 dei candidati; ORCL e AVGO scorati dallo stesso articolo macro (19 ticker); 86 articoli TAG_UNCONFIRMED su 160 righe.
* [F-030] contradicted (oggi): quota_movimento_precedente_al_segnale SPCX 0,22, SAP −2,02, PLTR degenere (denominatore_degenere true); nessun ingresso a movimento già consumato.
* [F-040] supported: ORCL −0,720 oltre il gate col segno corretto ma nessun ordine (long-only, fallback).
* [F-009] not_exposed: i segnali ADBE (+0,042, −0,137) erano ben sotto il gate 0,30, non vicini.

### (c) Casi di successo
SAP (S4, ingresso 15:07 @207,90, percentile 0,27): mtm_eod +34,52 $ (vs_apertura +11,43), ancora aperto. SAP non è un mover (+1,08%).
