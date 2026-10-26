# Alpha-miss report 2026-10-14

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-26T09:00:18Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. Quarta seduta di pipeline sentiment assente (10-09, 10-12, 10-13, 10-14): 0 righe news_log su 96/96 simboli (`mercato.watchlist_zero_news` 96, `copertura_articoli.totali.righe_news_log` 0), 0 execution_decisions, nessun log applicativo del 10-14 (F-096, F-085).
2. 29 mover |ret|>=3% (6 su, 23 giù; dispersione 3,02%; SPY −1,08%, QQQ −1,97%): rotazione fuori da semis/tech (13 semis + 5 tech su 29) verso healthcare (5 su 29). Le 2 ENTRY_OPPORTUNITY sono entrambe NO_NEWS: UNH +4,73% e WMT +3,46% (`net_opportunity_usd` 38,17 / 32,23 $).
3. 15 dei 19 mover detenuti all'open sono EXIT_RISK con `exit_signal_recall` 0/15 (12 STALE_EXIT_SIGNAL, 3 NO_EXIT_SIGNAL); 9 posizioni cieche lato uscita (notional 3.956,60 $); nessun ingresso, nessuna chiusura; equity Alpaca 109.697,71 $ (−485,67 $).

## 2. Stato carta
as_of di economic_pnl.json: **2026-09-17** (generato 2026-09-18). I cumulati non coprono le sedute dal 2026-09-18 al 2026-10-13; i numeri sotto sono quelli che il file dichiara. `longitudinal_panels.json` non esiste: i denominatori del §8 vengono dalle occorrenze di `findings.json` e dai conteggi del dossier.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni contro la soglia della carta di 0,6 (non superata). Oggi `aggregati.cause_del_giorno.dominante` = NO_NEWS (10/10), causa a valle dei provider (consumatore assente), non scopertura delle fonti.
- S4 economico cumulato: −696,33 $ contro ±200 $, fuori banda. S1 +664,95 $, BOOK −66,22 $.
- Il 10-14 non è registrato come rottura della serie in OBSERVATION_CHARTER.md (verifica al 10-13, non rinnovata): contarlo senza annotazione falsa la serie NO_NEWS. La registrazione spetta all'operatore.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| UNH | +4,73% | NO_NEWS | `candidati_miss[UNH].causa` NO_NEWS, `news_count` 0; `funnel_v2.righe[UNH]` ENTRY_OPPORTUNITY / NO_RELEVANT_NEWS; `net_opportunity_usd` 38,17 $ (lordo 104,01 $; ingresso simulato 388,66 → close 395,62) |
| WMT | +3,46% | NO_NEWS | `candidati_miss[WMT].causa` NO_NEWS, `news_count` 0; ENTRY_OPPORTUNITY / NO_RELEVANT_NEWS; `net_opportunity_usd` 32,23 $ (lordo 76,02 $; 114,42 → 116,16) |
| ORCL | −8,83% | non conteggiato (NON_ACTIONABLE, long-only) | `opportunity_v2.missing_reason` long_only_no_short_downside_not_held; causa dossier NO_NEWS |
| HOOD | −8,54% | non conteggiato (NON_ACTIONABLE) | idem; causa dossier NO_NEWS |
| BAC | −4,76% | non conteggiato (NON_ACTIONABLE) | idem; causa NO_NEWS; calendario CALENDAR (earnings) |
| INTC | −4,56% | non conteggiato (NON_ACTIONABLE) | idem |
| RDDT | −4,31% | non conteggiato (NON_ACTIONABLE) | idem |
| PLTR | −3,69% | non conteggiato (NON_ACTIONABLE) | idem |
| META | −3,27% | non conteggiato (NON_ACTIONABLE) | idem |
| AVGO | −3,10% | non conteggiato (NON_ACTIONABLE) | idem |

Conteggi: NO_NEWS 2, THIN_NEUTRAL 0, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. Gli 8 ribassi non detenuti restano fuori dal conteggio come nelle sedute precedenti (`funnel_v2.esclusi_pipeline.non_actionable_long_only` 8); il dossier (`cause_del_giorno`) conta NO_NEWS 10 includendoli.

**Non esiste testo da leggere.** news_log non ha righe pubblicate né scaricate fra il 2026-10-08 e il 2026-10-16 (DB: 10-08 160 righe, poi 10-16 205; idem `sentiment_signals`). Il catalizzatore di UNH e WMT non è ricostruibile (`event_market_context.*.catalyst.type` UNKNOWN, calendario NOT_OBSERVED con entrambe le fonti riuscite). Anche con le news, nessun ciclo portfolio ha girato (execution_decisions 0 righe il 10-14).

Mover detenuti all'open (19: 15 EXIT_RISK, 4 PASSIVE_EXPOSURE; `funnel_v2.kpi.held_at_open`). Non sono miss; esito = nessuna uscita (`chiusure` vuoto):

| Simbolo | Strategia | Return | Stadio (`pipeline_uscita`) | Segnale |
|---|---|---:|---|---|
| DELL | S1 | −11,27% | STALE_EXIT_SIGNAL | 14664 del 10-08, +0,134 |
| MRVL | S4 | −8,72% | STALE_EXIT_SIGNAL | 14636 del 10-07, +0,230 |
| ARM | S1 | −6,81% | STALE_EXIT_SIGNAL | 14668 del 10-08, −0,312 |
| SNOW | S1 | −6,34% | STALE_EXIT_SIGNAL | 14757 del 10-08, 0,000 |
| AMD | S1 | −5,73% | STALE_EXIT_SIGNAL | 14811 del 10-08, +0,007 |
| PANW | S4 | −5,54% | STALE_EXIT_SIGNAL | 14756 del 10-08, +0,005 |
| NOK | S1 | −4,67% | NO_EXIT_SIGNAL | nessun segnale d'uscita |
| SOXX | S1 | −4,50% | STALE_EXIT_SIGNAL | 14809 del 10-08, −0,829 |
| WDC | S4 | −4,36% | NO_EXIT_SIGNAL | nessun segnale d'uscita |
| MU | S4 | −4,08% | STALE_EXIT_SIGNAL | 14808 del 10-08, −0,829 |
| ASML | S1 | −3,94% | NO_EXIT_SIGNAL | nessun segnale d'uscita |
| AMAT | S1 | −3,79% | STALE_EXIT_SIGNAL | 14786 del 10-08, +0,039 |
| TSM | S1 | −3,40% | STALE_EXIT_SIGNAL | 14747 del 10-08, +0,034 |
| NVDA | S1 | −3,16% | STALE_EXIT_SIGNAL | 14801 del 10-08, −0,829 |
| CAT | S1 | −3,08% | STALE_EXIT_SIGNAL | 14644 del 10-07, −0,205 |
| AZN | S1 | +3,99% | PASSIVE_EXPOSURE | — |
| MRK | S1 | +3,80% | PASSIVE_EXPOSURE | — |
| LLY | S1 | +3,62% | PASSIVE_EXPOSURE | — |
| ABBV | S1 | +3,32% | PASSIVE_EXPOSURE | — |

Il lato rialzista detenuto è tutto healthcare (4 su 4 PASSIVE_EXPOSURE): posizioni S1 già a libro, non catture di segnale. Il dossier non attribuisce loro P&L di cattura (nessun ingresso).

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":[],"chiusure":[]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
<!-- alpha-miss-book:end -->
Il dossier non ha ingressi (`ingressi` = []), né chiusure (`chiusure` = []), né intenti S4 (`intenti_ingresso_s4` = []). `decision_signal_id_coverage.total_rows` 0: nessuna execution_decision il 10-14 (DB). Il book ha chiuso la seduta con 39 posizioni, 9 con perdita marcata dall'ingresso, nessuna uscita. Equity Alpaca 109.697,71 $ (riga storico timbrata 2026-10-15T00:00Z, cfr. F-053), −485,67 $ rispetto ai 110.183,38 $ del 10-13.

## 5. Cecita' lato uscita
Nove posizioni con `cieco_lato_uscita: true` su 39 (`copertura_uscita.aggregato`: soglia −3% dall'ingresso, `sedute_minime` 2, `n_indeterminati` 0, notional cieco 3.956,60 $: esposizione, non costo). Nessuna riga ha `cieco_lato_uscita` null.

| Ticker | Strategia | ritorno_da_ingresso | ritorno_seduta | sedute_consecutive_senza_righe | fonti_osservate_finestra | uscita nella seduta |
|---|---|---:|---:|---:|---|---|
| AMAT | S1 | −24,78% | −3,79% | 4 | alpaca_benzinga, gdelt_gkg | no |
| ARM | S1 | −17,51% | −6,81% | 4 | alpaca_benzinga | no |
| ASML | S1 | −6,71% | −3,94% | 10 (finestra intera) | nessuna (`[]`) | no |
| C | S1 | −8,08% | −1,81% | 4 | alpaca_benzinga | no |
| CAT | S1 | −8,07% | −3,08% | 5 | alpaca_benzinga, gdelt_gkg | no |
| MU | S4 | −6,61% | −4,08% | 4 | alpaca_benzinga, gdelt_gkg | no |
| NOK | S1 | −19,80% | −4,67% | 6 | alpaca_benzinga | no |
| NVDA | S1 | −3,93% | −3,16% | 4 | alpaca_benzinga, gdelt_gkg | no |
| WDC | S4 | −33,71% | −4,36% | 6 | alpaca_benzinga | no |

Per ASML `fonti_osservate_finestra` è vuota: zero resa dei provider nella finestra di 10 sedute, non fonte non configurata. Gli altri otto hanno avuto resa nelle sedute precedenti all'interruzione. Il `ritorno_da_ingresso` è la perdita mentre detenute; `ritorno_seduta` è il movimento del titolo. L'alert `held_news_loss_alert` non risulta recapitato (0 righe `mobile_notification_deliveries` il 10-13/10-14, cfr. F-062).

## 6. Backstop NO_NEWS
Marker calendario: 1/29 mover ha `observed_catalysts` CALENDAR (BAC, earnings FMP; `calendar_observation.mover_rate` 0,034) contro 0/67 non-mover. Gli altri 28 mover hanno calendario NOT_OBSERVED con entrambe le fonti riuscite (FMP, Alpaca Corporate Actions). CALENDAR significa evento osservato, non segnale né ordine.

Volume (`POST_HOC_EOD`, `valid_for_signal_evaluation` false): mediana della sorpresa di volume +0,191 sui mover (29 osservazioni), +0,048 sui non-mover (67). È nota solo a chiusura e non era disponibile prima del movimento. Nessuna soglia, nessun false-positive rate (studio ex-ante in #451).

Copertura raw `news_log` per settore (`no_news_backstop.per_sector`; distinta dalla effective-timely di `copertura_articoli.per_settore`, anch'essa 0/96):

| Settore | ticker_with_news/ticker_universe | raw_news_coverage_rate | zero_news_movers | calendar_observed_zero_news |
|---|---|---:|---:|---:|
| consumer | 0/11 | 0.000 | 1 | 0 |
| energy | 0/6 | 0.000 | 0 | 0 |
| etf_broad | 0/4 | 0.000 | 0 | 0 |
| financials | 0/14 | 0.000 | 2 | 1 |
| healthcare | 0/9 | 0.000 | 5 | 0 |
| industrials | 0/4 | 0.000 | 1 | 0 |
| materials | 0/2 | 0.000 | 0 | 0 |
| media | 0/5 | 0.000 | 1 | 0 |
| semis | 0/15 | 0.000 | 13 | 0 |
| tech | 0/21 | 0.000 | 5 | 0 |
| telecom | 0/5 | 0.000 | 1 | 0 |

Attribuzione fonti per ticker (#511 passo 2): tutti i 96 ticker di `copertura_articoli.per_ticker` hanno `articoli_unici` 0 e `fonti_osservate` `{}`; `blind_set.per_ticker.articoli_unici_giorno` 0 e `effective_timely_articles_giorno` 0 per tutti (`copertura_articoli.per_fonte` è `{}`). Ogni riga vale quindi "nessuna fonte ha reso righe news_log"; non esiste nessun caso "fonte presente ma non effective-timely". Il motivo di oggi è a valle dei provider (consumatore assente). `blind_set.ticker_allerta_zero_articoli` (40 ticker): ABBV, ASML, AXP, BA, BIDU, BP, BRK.B, CAT, CMCSA, COST, CRM, DB, ERIC, GE, HD, HOOD, IBM, INFY, JD, MMM, MRVL, NKE, NOK, NOW, NVO, PBR, PFE, PG, RDDT, RIO, ROKU, T, TM, TMUS, TXN, UBS, UNH, VALE, VZ, WDC. Ticker coperti dalla riga: tutti i 96 di `mercato.rendimenti` (appendice a).

## 7. Pattern osservato
Rotazione fuori da semis/tech verso healthcare e difensivi. Al ribasso: DELL −11,27%, ORCL −8,83%, MRVL −8,72%, HOOD −8,54%, ARM −6,81%, SNOW −6,34%, AMD −5,73%, PANW −5,54%, WDC −4,36%, ASML −3,94%, AMAT −3,79% (SOXX −4,50%, XLK −2,98%, QQQ −1,97%; 13 dei 29 mover sono semis, 5 tech). Al rialzo: UNH +4,73%, AZN +3,99%, MRK +3,80%, LLY +3,62%, WMT +3,46%, ABBV +3,32% (XLV +2,53%, PFE +2,96%, COST +2,87%). Anche le banche sono deboli (BAC −4,76%, con earnings; XLF −0,55%). La debolezza di AMAT/MU/semis ricorre dal 10-08 (report 10-09, 10-12, 10-13). Non ho testo per attribuire un catalizzatore: il tema è descrittivo, non causale.

## 8. Segnalazioni

* [F-096] Il consumatore della coda sentiment (`worker-inference`) resta assente per la quarta seduta (10-09, 10-12, 10-13, 10-14) dopo il warm shutdown del 2026-10-08: 0 righe news_log e 0 segnali su 96/96 simboli, nessun alert.
  * esposizione: 1 seduta intera su 96/96 simboli (`mercato.watchlist_zero_news` 96; `copertura_articoli.totali.righe_news_log` 0). 2 ENTRY_OPPORTUNITY NO_NEWS (UNH, WMT), 15 EXIT_RISK con `exit_signal_recall` 0/15 (12 STALE_EXIT_SIGNAL su segnali del 10-07/10-08, 3 NO_EXIT_SIGNAL), 9 posizioni cieche lato uscita. Giorno più esposto della serie per numero di mover (29 contro 11 del 10-13).
  * evidenza contraria: se il finding fosse falso, il 10-14 avrebbe righe in news_log o sentiment_signals o un `worker-inference-2026-10-14.log`. DB: righe del 10-08 (160) poi del 10-16 (205), nulla in mezzo; il primo log worker-inference è del 10-16.
  * non-occorrenza: il calendario earnings è OBSERVED (vede BAC) e le fonti calendario sono riuscite: il buco è circoscritto alla pipeline news→sentiment. Il dossier stesso è stato calcolato (prezzi SIP, snapshot di apertura) e vede 39 posizioni.
  * next evidence: `stale_drop_metrics_daily` del 10-16 per quanta coda è scaduta alla ripartenza (cfr. F-069); confronto fra il primo log `worker-inference-2026-10-16.log` e il deploy del 10-16 per la causa della ripartenza.
  * meccanismo e fonte: §1, §3, §5, §6. Campi: `copertura_articoli.totali`, `no_news_backstop.population.zero_news` 96, `funnel_v2.kpi.exit_signal_recall`, `funnel_v2.conteggi_pipeline_uscita`, `copertura_uscita.aggregato.ticker_ciechi`. Stesso difetto delle tre sedute precedenti.
  * costo: congetturale, 2.200 $ × (|ret UNH| + |ret WMT|) = 2.200 × (0,0473 + 0,0346) = 180,04 $ (legacy `opportunity_v2.legacy.costo_usd`: 104,01 + 76,02). L'opportunità netta accessibile del dossier è 70,40 $ (38,17 + 32,23). Alternativa scartata: «i provider non coprivano la watchlist» (F-001), smentita dalle fonti osservate nelle sedute precedenti su 8 dei 9 ciechi. Alternativa scartata: «assenza di news dovuta solo allo stack giù (F-085)», smentita dal vuoto di news_log che inizia il 10-08, cinque sedute prima.
* [F-085] Il guasto Redis/disco del 10-13 (MISCONF, stack Celery fermo) si estende alla seconda seduta RTH consecutiva: nessun ciclo portfolio e nessun log applicativo il 10-14.
  * esposizione: 1 seduta RTH (13:30–20:00Z) con 0 execution_decisions (DB; ripresa il 10-16 con 1.634 righe), 0 ingressi, 0 chiusure, 0 intenti S4 (`ingressi`/`chiusure`/`intenti_ingresso_s4` vuoti, `decision_signal_id_coverage.total_rows` 0). 39 posizioni detenute senza alcuna valutazione d'uscita, di cui 9 con perdita ≥3% dall'ingresso. Con il 10-13 sono 2 sedute consecutive. Il disco host è al 94% (21 GB liberi).
  * evidenza contraria: se il finding fosse falso, il 10-14 avrebbe righe in execution_decisions o file di log di worker/beat/api. DB: nessuna riga fra 10-13 e 10-15 (solo 10-16); `logs/containers` non contiene alcun file del 10-14 per api/beat/worker/worker-inference.
  * non-occorrenza: non verificabile per il 10-14 sul lato log (file assenti: non si può escludere che il guasto sia cambiato di natura rispetto al MISCONF del 10-13). Gli stop GTC al broker restano attivi ma nessun fill di stop è nel dossier.
  * next evidence: `docker logs alembic-redis-1` / log host del 10-13→10-15 per ora di riempimento e di ripristino; conteggio portfolio_cycles 10-14 e 10-15; `mobile_notification_deliveries` 10-13→10-16 (0 righe il 10-13, 10-14).
  * meccanismo e fonte: §1, §4, §5. Campi: `ingressi`, `chiusure`, `intenti_ingresso_s4`, `decision_signal_id_coverage.total_rows`, `copertura_uscita.aggregato.n_cieche_lato_uscita` 9. L'attribuzione al MISCONF è un'ipotesi ereditata dal 10-13: per il 10-14 il dato misurato è solo l'assenza di decisioni e di log.
  * costo: non stimato (null). Nessun segnale fresco esisteva (F-096): contare qui UNH/WMT li conterebbe due volte; il costo lato uscita richiede un controfattuale per-ciclo che il dossier non fornisce. Alternativa scartata: «seduta vuota per scelta della strategia», smentita da 0 righe in execution_decisions (il 10-12 il ciclo ne aveva scritte 300). Alternativa scartata: «outage di rete (F-094)»: non distinguibile per il 10-14 senza log; nessuna evidenza a favore.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli)

| # | Simbolo | Return |
|---:|---|---:|
| 1 | UNH | +4,73% |
| 2 | AZN | +3,99% |
| 3 | MRK | +3,80% |
| 4 | LLY | +3,62% |
| 5 | WMT | +3,46% |
| 6 | ABBV | +3,32% |
| 7 | PFE | +2,96% |
| 8 | COST | +2,87% |
| 9 | TMUS | +2,64% |
| 10 | XLV | +2,53% |
| 11 | PG | +2,28% |
| 12 | JNJ | +2,13% |
| 13 | VZ | +2,04% |
| 14 | CVX | +1,98% |
| 15 | ADBE | +1,86% |
| 16 | PBR | +1,73% |
| 17 | XOM | +1,68% |
| 18 | SBUX | +1,36% |
| 19 | JPM | +1,16% |
| 20 | BRK.B | +1,11% |
| 21 | MCD | +1,06% |
| 22 | MMM | +1,04% |
| 23 | NOW | +0,99% |
| 24 | T | +0,88% |
| 25 | CMCSA | +0,81% |
| 26 | INFY | +0,70% |
| 27 | XLE | +0,64% |
| 28 | BP | +0,58% |
| 29 | SHEL | +0,57% |
| 30 | HD | +0,54% |
| 31 | AAPL | +0,50% |
| 32 | DIS | +0,38% |
| 33 | SAP | +0,34% |
| 34 | BABA | +0,29% |
| 35 | WFC | +0,20% |
| 36 | NVO | +0,16% |
| 37 | NFLX | +0,16% |
| 38 | SONY | +0,12% |
| 39 | TM | −0,06% |
| 40 | ROKU | −0,06% |
| 41 | NKE | −0,08% |
| 42 | GE | −0,20% |
| 43 | MA | −0,26% |
| 44 | JD | −0,37% |
| 45 | F | −0,41% |
| 46 | XLF | −0,55% |
| 47 | CRM | −0,87% |
| 48 | AXP | −0,93% |
| 49 | BA | −0,98% |
| 50 | SPY | −1,08% |
| 51 | GM | −1,13% |
| 52 | V | −1,17% |
| 53 | VALE | −1,20% |
| 54 | CSCO | −1,24% |
| 55 | IBM | −1,26% |
| 56 | ERIC | −1,34% |
| 57 | UBS | −1,46% |
| 58 | GS | −1,48% |
| 59 | DB | −1,62% |
| 60 | GOOGL | −1,74% |
| 61 | AMZN | −1,74% |
| 62 | MSFT | −1,80% |
| 63 | C | −1,81% |
| 64 | IWM | −1,93% |
| 65 | RIO | −1,94% |
| 66 | QQQ | −1,97% |
| 67 | TSLA | −2,15% |
| 68 | BIDU | −2,25% |
| 69 | QCOM | −2,40% |
| 70 | TXN | −2,50% |
| 71 | MS | −2,75% |
| 72 | SPCX | −2,80% |
| 73 | XLK | −2,98% |
| 74 | CAT | −3,08% |
| 75 | AVGO | −3,10% |
| 76 | NVDA | −3,16% |
| 77 | META | −3,27% |
| 78 | TSM | −3,40% |
| 79 | PLTR | −3,69% |
| 80 | AMAT | −3,79% |
| 81 | ASML | −3,94% |
| 82 | MU | −4,08% |
| 83 | RDDT | −4,31% |
| 84 | WDC | −4,36% |
| 85 | SOXX | −4,50% |
| 86 | INTC | −4,56% |
| 87 | NOK | −4,67% |
| 88 | BAC | −4,76% |
| 89 | PANW | −5,54% |
| 90 | AMD | −5,73% |
| 91 | SNOW | −6,34% |
| 92 | ARM | −6,81% |
| 93 | HOOD | −8,54% |
| 94 | MRVL | −8,72% |
| 95 | ORCL | −8,83% |
| 96 | DELL | −11,27% |

### (b) Altri finding aperti toccati dalla giornata

- [F-001] not_exposed: la copertura 0/96 è prodotta dal consumatore assente (F-096), non dalla resa dei provider; non misurabile.
- [F-036] supported: WDC −33,71%, AMAT −24,78%, NOK −19,80%, ARM −17,51% dall'ingresso, oltre il trigger −15/20%, nessun ciclo né alert nella seduta.
- [F-048] not_exposed: nessun fill di stop nel dossier (`chiusure` vuoto).
- [F-053] supported: la riga Alpaca della seduta 10-14 è timbrata 2026-10-15T00:00Z.
- [F-062] supported: 0 righe `mobile_notification_deliveries` il 10-13/10-14 con stack fermo.
- [F-094] not_exposed: nessuna evidenza di rete per il 10-14; senza log non decidibile.
- [F-022] not_exposed: nessuno stop scattato; le posizioni non proteggibili (qty < 1) restano esposte.
- [F-009] not_exposed: 0 segnali, quindi nessun gate valutabile.
- [F-040] not_exposed: 0 segnali; i 23 ribassi sono non detenuti/long-only (`non_actionable_long_only` 8) senza segnale.

### (c) Casi di successo
Nessun mover catturato con P&L positivo da un ingresso (0 ingressi). I quattro healthcare detenuti in rialzo (AZN +3,99%, MRK +3,80%, LLY +3,62%, ABBV +3,32%) sono PASSIVE_EXPOSURE, non catture.
