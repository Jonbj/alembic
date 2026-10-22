# Alpha-miss report 2026-10-12

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-22T08:00:18Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. Seconda seduta intera con la pipeline sentiment ferma: 0 righe news_log su 96/96 simboli (`mercato.watchlist_zero_news` 96, `copertura_articoli.totali.righe_news_log` 0). Nessun log di `worker-inference` del 10-12; la coda news (`news_queue_census.queue_depth`) sale da 1.154 a 1.819 senza consumatore (F-096).
2. 7 mover |ret|>=3% (1 su, 6 giù; dispersione 1,56%). L'unica ENTRY_OPPORTUNITY è META +3,38%, NO_NEWS (`net_opportunity_usd` 0,97 $). 5 dei 6 ribassi sono già a libro (NOK, ARM, MU, PANW, MRVL): tutti EXIT_RISK con `pipeline_uscita` STALE_EXIT_SIGNAL, `exit_signal_recall` 0/5.
3. Nessun ingresso. Due chiusure S4 per assenza di segnale, PLTR +47,53 $ e SAP +70,08 $ (`portfolio_sell`, "no S4 signal found in DB"). Il book detenuto all'open perde −248,15 $ di seduta (S1 −50,96, S4 −197,19; `snapshot_apertura`).

## 2. Stato carta
as_of di economic_pnl.json: **2026-09-17** (generato 2026-09-18). I cumulati non coprono le sedute dal 2026-09-18 al 2026-10-09 e i numeri sotto sono quelli che il file dichiara.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni, contro una soglia della carta di 0,6. Non superata.
- S4 economico cumulato: −696,33 $ contro ±200 $, quindi fuori banda. S1 +664,95 $, BOOK −66,22 $.
- Anche oggi la seduta è NO_NEWS dominante (`aggregati.cause_del_giorno.dominante` = NO_NEWS, 2/2), ma la causa è l'assenza del consumatore della coda, non una scopertura dei provider (§8). Contarla nella serie pre-registrata senza annotazione falsa la serie, come per il 10-09. La registrazione della discontinuità spetta all'operatore.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| META | +3,38% | NO_NEWS | `candidati_miss[META].causa` = NO_NEWS, `news_count` 0; `funnel_v2.righe[META]` ENTRY_OPPORTUNITY, `pipeline` NO_RELEVANT_NEWS; `opportunity_v2.net_opportunity_usd` 0,97 $ (lordo 74,36 $) |
| INTC | −3,20% | non conteggiato (NON_ACTIONABLE, long-only) | `funnel_v2.righe[INTC].pipeline_escluso_motivo` = non_actionable_long_only; `accessible_opportunity_usd` 0; causa dossier NO_NEWS |

Conteggi: NO_NEWS 1, THIN_NEUTRAL 0, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. Il ribasso non detenuto (INTC) resta fuori dal conteggio, come nelle sedute precedenti; il dossier (`cause_del_giorno`) conta NO_NEWS 2 includendolo.

**Il NO_NEWS di oggi non è un vuoto delle fonti.** news_log non ha righe per nessun ticker dal 2026-10-08 16:15Z al 2026-10-16 (verifica read-only su DB). I poller REST hanno girato tutta la seduta e hanno accodato: `run_news_ingestion_worker` 24 run, 19 articoli; `run_alpaca_ingestion_worker` 24 run, 14 articoli (`worker-2026-10-12.log`). La coda è però cresciuta di 665 elementi, quindi quasi tutto l'afflusso viene da un altro produttore. Probabilmente è il news-stream, ma non c'è un `worker-news-stream-2026-10-12.log` per verificarlo. Non esiste testo da leggere: senza righe news_log, il catalizzatore di META non è ricostruibile (`event_market_context.META.catalyst.type` UNKNOWN; calendario NOT_OBSERVED).

Mover detenuti all'open (non sono miss; `funnel_v2.righe` + `snapshot_apertura`):

| Simbolo | Strategia | Return | Stadio d'uscita (segnale stantio) | P&L di seduta (actual_intraday_pnl_usd) |
|---|---|---:|---|---:|
| NOK | S1 | −4,44% | STALE_EXIT_SIGNAL (signal 14382 del 10-06, +0,148) | −0,00 $ (qty_open 0, missingness `exit_fill_qty_exceeds_trade_qty`) |
| ARM | S1 | −4,15% | STALE_EXIT_SIGNAL (signal 14668 del 10-08, −0,312) | −3,00 $ (stop GTC di 2 azioni fillato 18:49Z @253,85) |
| MU | S4 | −3,88% | STALE_EXIT_SIGNAL (signal 14808 del 10-08, −0,829) | −6,21 $ |
| PANW | S4 | −3,57% | STALE_EXIT_SIGNAL (signal 14756 del 10-08, +0,005) | −68,14 $ |
| MRVL | S4 | −3,42% | STALE_EXIT_SIGNAL (signal 14636 del 10-07, +0,230) | −55,07 $ |

Catturati: 5, cioè i mover detenuti all'open, tutti dal lato perdente. Nessun ingresso nella seduta.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":[],"chiusure":["PLTR","SAP"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| OUT | PLTR | S4 | — | $207.1252 | 7.9693 | +$47.53 | portfolio_sell |
| OUT | SAP | S4 | — | $217.1500 | 7.6717 | +$70.08 | portfolio_sell |
<!-- alpha-miss-book:end -->
Il dossier non ha ingressi (`ingressi` = []) e ha due chiusure S4, PLTR (+47,53 $) e SAP (+70,08 $), entrambe `portfolio_sell` dopo circa 96 ore di tenuta. Le due SELL in execution_decisions portano la stessa ragione: "[no_signal] … no S4 signal found in DB". L'uscita è stata quindi forzata dall'invecchiamento dei segnali durante l'interruzione, non da un segnale contrario. Il `drift_post_uscita` è +14,94 $ e +5,37 $ (il titolo ha chiuso sopra il prezzo d'uscita). I 282 intent S4 poggiano tutti su segnali del 10-08: SKIP_FALLBACK 126, SKIP_ENTRY_FRESHNESS 124, SKIP_ENTRY_GATE 16, SKIP_STALE 10, SKIP_PYRAMIDING 6. Le 6 tradabili sono PLTR/SAP, già detenuti. Equity Alpaca a fine seduta 110.372,64 $ (P&L −263,43 $; riga timbrata 2026-10-13T00:00Z, cfr. F-053).

## 5. Cecita' lato uscita
Quattro posizioni con `cieco_lato_uscita: true`. Il dossier dichiara soglia −3% dall'ingresso e `sedute_minime` 2; `n_cieche_lato_uscita` è 4 su 41, `n_indeterminati` 0, notional cieco 572,71 $ (esposizione, non costo). Nessuna riga ha `cieco_lato_uscita` null.

| Ticker | Strategia | ritorno_da_ingresso | ritorno_seduta | sedute_consecutive_senza_righe | fonti_osservate_finestra | uscita nella seduta |
|---|---|---:|---:|---:|---|---|
| AMAT | S1 | −16,21% | −1,87% | 2 | alpaca_benzinga, gdelt_gkg | no |
| ARM | S1 | −11,54% | −4,15% | 2 | alpaca_benzinga | no (residuo frazionario; vedi §8) |
| NOK | S1 | −15,53% | −4,44% | 4 | alpaca_benzinga, gdelt_gkg | no |
| WDC | S4 | −29,55% | −2,60% | 4 | alpaca_benzinga | no |

Le fonti della finestra non sono vuote: i provider hanno reso su questi ticker nelle sedute precedenti. La cecità di AMAT e ARM (streak 2 = 10-09 + 10-12) coincide con l'interruzione del consumatore. NOK e WDC (streak 4) erano già senza righe dal 10-06/10-07. `held_news_loss_alert` alle 22:50Z ha emesso 4 alert sugli stessi ticker (`worker-2026-10-12.log`); il recapito non è verificato qui.

## 6. Backstop NO_NEWS
Marker calendario: nessuno. `observed_catalysts` è vuoto per tutti e 7 i mover (META, INTC, NOK, ARM, MU, PANW, MRVL), e `calendar_observation.mover_observed` è 0/7, con il calendario OBSERVED su FMP e su Alpaca Corporate Actions.

Volume (`POST_HOC_EOD`, non point-in-time, `valid_for_signal_evaluation` false): la mediana della sorpresa di volume è −0,151 sui mover e −0,291 sui non-mover. Il volume è noto solo a chiusura e non era disponibile prima del movimento. Nessuna soglia, nessun false-positive rate.

Copertura raw `news_log` per settore (`no_news_backstop.per_sector`; distinta dalla effective-timely di `copertura_articoli.per_settore`, anch'essa 0/96 oggi):

| Settore | ticker_with_news/ticker_universe | raw_news_coverage_rate | zero_news_movers | calendar_observed_zero_news |
|---|---|---:|---:|---:|
| consumer | 0/11 | 0,000 | 0 | 0 |
| energy | 0/6 | 0,000 | 0 | 0 |
| etf_broad | 0/4 | 0,000 | 0 | 0 |
| financials | 0/14 | 0,000 | 0 | 0 |
| healthcare | 0/9 | 0,000 | 0 | 0 |
| industrials | 0/4 | 0,000 | 0 | 0 |
| materials | 0/2 | 0,000 | 0 | 0 |
| media | 0/5 | 0,000 | 0 | 0 |
| semis | 0/15 | 0,000 | 4 | 0 |
| tech | 0/21 | 0,000 | 2 | 0 |
| telecom | 0/5 | 0,000 | 1 | 0 |

Attribuzione fonti per ticker (#511 passo 2): tutti i 96 ticker di `copertura_articoli.per_ticker` hanno `articoli_unici` 0 e `fonti_osservate` `{}`, con `blind_set.per_ticker.articoli_unici_giorno` 0 e `effective_timely_articles_giorno` 0. Ogni riga è quindi "nessuna fonte ha reso righe news_log", e oggi il motivo è a valle dei provider (consumatore assente), non i provider stessi. Ticker: AAPL, ABBV, ADBE, AMAT, AMD, AMZN, ARM, ASML, AVGO, AXP, AZN, BA, BABA, BAC, BIDU, BP, BRK.B, C, CAT, CMCSA, COST, CRM, CSCO, CVX, DB, DELL, DIS, ERIC, F, GE, GM, GOOGL, GS, HD, HOOD, IBM, INFY, INTC, IWM, JD, JNJ, JPM, LLY, MA, MCD, META, MMM, MRK, MRVL, MS, MSFT, MU, NFLX, NKE, NOK, NOW, NVDA, NVO, ORCL, PANW, PBR, PFE, PG, PLTR, QCOM, QQQ, RDDT, RIO, ROKU, SAP, SBUX, SHEL, SNOW, SONY, SOXX, SPCX, SPY, T, TM, TMUS, TSLA, TSM, TXN, UBS, UNH, V, VALE, VZ, WDC, WFC, WMT, XLE, XLF, XLK, XLV, XOM. `blind_set.ticker_allerta_zero_articoli` (streak ≥5): ASML, CMCSA, INFY, JD, MMM, PBR, RDDT, RIO, ROKU, TXN, UBS, VALE.

## 7. Pattern osservato
Debolezza semis/hardware: MU −3,88%, ARM −4,15%, MRVL −3,42%, INTC −3,20%, SOXX −2,60%, WDC −2,60%, AMD −2,28%. Si aggiungono PANW −3,57% e NOK −4,44%, contro XLK −1,22% e SPY −0,06%. L'unico mover rialzista è META +3,38% (residuo vs XLK +4,60%). Sul lato difensivo telecom/energia sono in rialzo (VZ +2,71%, TMUS +2,21%, XOM +1,90%, XLE +1,43%): è il rimbalzo dei titoli telecom dopo il crollo del 10-09. La debolezza semis ricorre dal 10-08 (blocco semis in calo annotato nel report del 10-09). Il catalizzatore non è ricostruibile oggi per assenza di testo.

## 8. Segnalazioni

* [F-096] Il consumatore della coda sentiment (`worker-inference`) resta assente per una seconda seduta intera dopo il warm shutdown del 2026-10-08 16:20Z. Il 10-12 passa senza righe news_log né segnali su 96/96 simboli e senza alert, con la coda in crescita.
  * esposizione: 1 seduta intera su 96/96 simboli (`mercato.watchlist_zero_news` 96; `copertura_articoli.totali.righe_news_log` 0). 1 ENTRY_OPPORTUNITY (META) e 5 EXIT_RISK (`funnel_v2.conteggi_pipeline_uscita.STALE_EXIT_SIGNAL` 5) senza segnale fresco. 2 uscite S4 forzate da "no S4 signal found in DB". Il beat ha emesso 32 `sentiment-worker` e 15 `sentiment-shadow-offsession`, nessuno dei quali risulta eseguito (nessun `worker-inference-2026-10-12.log`). Seconda occorrenza dopo il 10-09; la finestra vuota in news_log arriva al 10-16.
  * evidenza contraria: se il finding fosse falso, il 10-12 avrebbe almeno una riga in news_log o sentiment_signals, oppure un log del worker-inference. Su DB invece i conteggi giornalieri passano da 10-08 (160) a 10-16 (205) senza righe in mezzo, e la coda non scende mai (1.154 alle 00:00Z, 1.392 alle 14:00Z, 1.819 alle 22:00Z, dead_letter 0).
  * non-occorrenza: worker principale (3.359 righe "received"), beat, api e ciclo portfolio (300 execution_decisions) hanno girato tutta la seduta. I poller REST hanno accodato 33 articoli. Il guasto è circoscritto al consumatore (≠ F-094/F-085).
  * next evidence: dossier 10-13→10-15 (`watchlist_zero_news`, `righe_news_log`) per chiudere l'estensione dell'interruzione; `stale_drop_metrics_daily` del 10-16 per misurare quanta coda è scaduta alla ripartenza (cfr. F-069); `mobile_notification_deliveries` del 10-12 per verificare se qualche alert (anche `held_news_loss_alert`) è stato recapitato.
  * meccanismo e fonte: §1, §3, §4, §5. Campi: `copertura_articoli.totali`, `no_news_backstop.population.zero_news` 96, `funnel_v2.kpi.exit_signal_recall` 0/5, `chiusure[*].exit_reason`. Log: `beat-`/`worker-2026-10-12.log`. È un difetto operativo, non un limite della strategia: nessun watchdog sull'assenza del consumatore o sulla profondità della coda. Effetto sulla misura: la serie NO_NEWS pre-registrata conta come vuoto delle fonti una seduta in cui le fonti hanno reso.
  * costo: congetturale, 2.200 $ × |ret META| = 2.200 × 0,0338 = 74,36 $. L'opportunità netta accessibile del dossier è molto minore (`net_opportunity_usd` 0,97 $). Il costo lato uscita non è stimato: nessun controfattuale dice che un segnale fresco avrebbe venduto prima. Alternativa scartata: «i provider non coprivano la watchlist» (F-001), smentita da 33 articoli accodati dai poller REST e +665 elementi in coda. Alternativa scartata: «outage di host/rete» (F-094), smentita dai 3.359 task ricevuti dal worker principale.
* [F-048] Lo stop protettivo GTC di ARM (2 azioni, `ambc-pstop-ARM-20261001T1422`, stop 253,92) si è fillato alle 18:49:25Z @253,85, ma il trade 1041 su DB resta aperto con qty 2,0439 e senza `exit_time`.
  * esposizione: 1 fill di stop nella seduta; il dossier lo vede solo come `quantity_changes_intraday` con missingness `exit_fill_qty_exceeds_trade_qty` (ARM e NOK). Non compare in `chiusure`, quindi il realizzato S1 di oggi risulta 0.
  * evidenza contraria: se il finding fosse falso, `trades` mostrerebbe per il 1041 una quantità ridotta a ~0,0439 o una riga di uscita parziale, e il dossier non segnalerebbe `exit_fill_qty_exceeds_trade_qty`.
  * non-occorrenza: le uscite per `portfolio_sell` di PLTR e SAP sono state scritte correttamente su `trades` e compaiono in `chiusure`.
  * next evidence: confronto read-only fra `trades.qty` dei trade aperti e le posizioni Alpaca (`/v2/positions`) per ARM e NOK.
  * meccanismo e fonte: §3 e §5. Campi: `snapshot_apertura[ARM].quantity_changes_intraday`, `missingness`; ordine Alpaca 17ac2b8c. Difetto già noto (F-048, con F-022 per lo stop sulla sola parte intera).
  * costo: misurata, |(253,85 − 288,54) × 2| = 69,38 $ di perdita realizzata non registrata (entry_price 288,54 da `copertura_uscita[ARM]`). È P&L assente dal ledger S1, non un'opportunità persa.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli)

| # | Simbolo | Return |
|---:|---|---:|
| 1 | META | +3,38% |
| 2 | VZ | +2,71% |
| 3 | TMUS | +2,21% |
| 4 | CRM | +2,09% |
| 5 | XOM | +1,90% |
| 6 | NKE | +1,84% |
| 7 | C | +1,76% |
| 8 | SBUX | +1,69% |
| 9 | ABBV | +1,68% |
| 10 | WMT | +1,55% |
| 11 | SAP | +1,43% |
| 12 | XLE | +1,43% |
| 13 | CVX | +1,42% |
| 14 | SHEL | +1,41% |
| 15 | T | +1,40% |
| 16 | COST | +1,32% |
| 17 | PG | +1,30% |
| 18 | AAPL | +1,29% |
| 19 | MSFT | +1,14% |
| 20 | AXP | +1,09% |
| 21 | BP | +1,04% |
| 22 | MA | +1,01% |
| 23 | V | +0,99% |
| 24 | INFY | +0,93% |
| 25 | JNJ | +0,88% |
| 26 | XLV | +0,69% |
| 27 | XLF | +0,58% |
| 28 | MMM | +0,58% |
| 29 | SONY | +0,58% |
| 30 | SPCX | +0,52% |
| 31 | BAC | +0,48% |
| 32 | PBR | +0,47% |
| 33 | NFLX | +0,44% |
| 34 | PFE | +0,42% |
| 35 | DIS | +0,41% |
| 36 | JPM | +0,39% |
| 37 | BRK.B | +0,38% |
| 38 | GOOGL | +0,30% |
| 39 | LLY | +0,28% |
| 40 | HOOD | +0,18% |
| 41 | MCD | +0,18% |
| 42 | GE | +0,14% |
| 43 | CMCSA | +0,10% |
| 44 | RDDT | +0,01% |
| 45 | MS | +0,00% |
| 46 | PLTR | −0,02% |
| 47 | ROKU | −0,03% |
| 48 | HD | −0,04% |
| 49 | IBM | −0,05% |
| 50 | SPY | −0,06% |
| 51 | DB | −0,09% |
| 52 | MRK | −0,10% |
| 53 | CAT | −0,14% |
| 54 | GS | −0,15% |
| 55 | NVO | −0,16% |
| 56 | UNH | −0,21% |
| 57 | WFC | −0,28% |
| 58 | TM | −0,31% |
| 59 | IWM | −0,37% |
| 60 | NOW | −0,38% |
| 61 | GM | −0,44% |
| 62 | BA | −0,46% |
| 63 | RIO | −0,51% |
| 64 | BABA | −0,53% |
| 65 | AZN | −0,55% |
| 66 | QCOM | −0,61% |
| 67 | UBS | −0,64% |
| 68 | QQQ | −0,70% |
| 69 | TXN | −0,70% |
| 70 | VALE | −0,73% |
| 71 | AMZN | −1,11% |
| 72 | BIDU | −1,21% |
| 73 | XLK | −1,22% |
| 74 | TSLA | −1,22% |
| 75 | NVDA | −1,29% |
| 76 | JD | −1,37% |
| 77 | F | −1,40% |
| 78 | DELL | −1,59% |
| 79 | ASML | −1,69% |
| 80 | ADBE | −1,70% |
| 81 | AMAT | −1,87% |
| 82 | AVGO | −1,88% |
| 83 | ERIC | −1,94% |
| 84 | TSM | −1,98% |
| 85 | AMD | −2,28% |
| 86 | SNOW | −2,31% |
| 87 | CSCO | −2,58% |
| 88 | SOXX | −2,60% |
| 89 | WDC | −2,60% |
| 90 | ORCL | −2,84% |
| 91 | INTC | −3,20% |
| 92 | MRVL | −3,42% |
| 93 | PANW | −3,57% |
| 94 | MU | −3,88% |
| 95 | ARM | −4,15% |
| 96 | NOK | −4,44% |

### (b) Altri finding aperti toccati dalla giornata

- [F-001] not_exposed: la copertura 0/96 di oggi è causata dal consumatore assente (F-096), non dai provider, e non misura la copertura delle fonti.
- [F-011] supported: `decision_signal_id_coverage.by_reason_code.SELL` 0/2 (PLTR, SAP), `regressions` = [SELL].
- [F-022] supported: lo stop GTC di ARM copriva 2 azioni su 2,0439 (la sola parte intera); il residuo detenuto vale 11,20 $ (`copertura_uscita[ARM].notional_usd`).
- [F-053] supported: la seduta 10-12 compare in `/v2/account/portfolio/history` come riga 2026-10-13T00:00Z.
- [F-059] not_exposed: nessun segnale d'uscita fresco nella seduta (5 EXIT_RISK tutti STALE_EXIT_SIGNAL), quindi l'asimmetria delle soglie non è stata esercitata.
- [F-069] not_exposed: la coda cresce ma il consumatore manca anche in seduta, quindi lo scarto stale alla ripartenza si misura il 10-16.
- [F-062] not_exposed: `decay_check` ha loggato 3 "DECAY CRITICAL" (`worker-2026-10-12.log`) senza recapito verificato; dato non approfondito.

### (c) Casi di successo
Nessun mover catturato con P&L positivo: i 5 mover detenuti erano tutti in ribasso. Le due chiusure positive (PLTR +47,53 $, SAP +70,08 $) non sono mover della seduta (PLTR −0,02%, SAP +1,43%).
