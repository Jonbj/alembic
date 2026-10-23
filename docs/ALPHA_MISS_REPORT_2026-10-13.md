# Alpha-miss report 2026-10-13

(prompt alpha_miss_prompt_v2, dossier schema 3.1 generato il 2026-10-23T08:00:15Z; prezzi Alpaca SIP, adjustment=all)

## 1. Decision card
1. Terza seduta consecutiva con la pipeline sentiment ferma: 0 righe news_log su 96/96 simboli (`mercato.watchlist_zero_news` 96, `copertura_articoli.totali.righe_news_log` 0), nessun log di `worker-inference` del 10-13 (F-096). Dalle 11:03Z si aggiunge Redis MISCONF (disco pieno): il worker principale non riceve più task e la seduta passa con **0 cicli portfolio e 0 execution_decisions** (F-085).
2. 11 mover |ret|>=3% (4 su, 7 giù; dispersione 1,93%). Le 3 ENTRY_OPPORTUNITY sono tutte NO_NEWS: INFY +5,26%, ORCL +4,23%, ERIC +3,63% (`net_opportunity_usd` −14,68 / +52,92 / +49,83 $).
3. 5 mover in calo sono già a libro (AMAT −6,69%, JNJ −5,73%, C −5,60%, MU −3,62%, CAT −3,33%): tutti EXIT_RISK con STALE_EXIT_SIGNAL, `exit_signal_recall` 0/5. Nessun ingresso, nessuna chiusura; equity Alpaca 110.183,38 $ (−189,26 $).

## 2. Stato carta
as_of di economic_pnl.json: **2026-09-17** (generato 2026-09-18). I cumulati non coprono le sedute dal 2026-09-18 al 2026-10-12; i numeri sotto sono quelli che il file dichiara.
- Giorno 30/40 (al 2026-09-17).
- Quota NO_NEWS dominante: 13/30 giorni, contro una soglia della carta di 0,6. Non superata.
- S4 economico cumulato: −696,33 $ contro ±200 $, quindi fuori banda. S1 +664,95 $, BOOK −66,22 $.
- Oggi la seduta è NO_NEWS dominante (`aggregati.cause_del_giorno.dominante` = NO_NEWS, 5/5). Come il 10-09 e il 10-12, la causa è a valle dei provider (consumatore assente, poi stack giù), non una scopertura delle fonti. OBSERVATION_CHARTER.md non registra nessuna delle tre sedute come rottura della serie: contarle senza annotazione falsa la serie NO_NEWS. La registrazione spetta all'operatore.

## 3. Miss del giorno

| Simbolo | Return | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| INFY | +5,26% | NO_NEWS | `candidati_miss[INFY].causa` NO_NEWS, `news_count` 0; `funnel_v2.righe[INFY]` ENTRY_OPPORTUNITY, `pipeline` NO_RELEVANT_NEWS; `net_opportunity_usd` −14,68 $ (lordo 115,79 $: il movimento era nel gap, open 11,47 → close 11,40) |
| ORCL | +4,23% | NO_NEWS | `candidati_miss[ORCL].causa` NO_NEWS, `news_count` 0; ENTRY_OPPORTUNITY / NO_RELEVANT_NEWS; `net_opportunity_usd` +52,92 $ (lordo 93,03 $) |
| ERIC | +3,63% | NO_NEWS | `candidati_miss[ERIC].causa` NO_NEWS, `news_count` 0; ENTRY_OPPORTUNITY / NO_RELEVANT_NEWS; `net_opportunity_usd` +49,83 $ (lordo 79,83 $) |
| SPCX | −4,21% | non conteggiato (NON_ACTIONABLE, long-only) | `funnel_v2.righe[SPCX].pipeline_escluso_motivo` non_actionable_long_only; `accessible_opportunity_usd` 0; causa dossier NO_NEWS |
| WFC | −3,10% | non conteggiato (NON_ACTIONABLE, long-only) | `funnel_v2.righe[WFC].pipeline_escluso_motivo` non_actionable_long_only; `accessible_opportunity_usd` 0; causa dossier NO_NEWS |

Conteggi: NO_NEWS 3, THIN_NEUTRAL 0, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 0. I ribassi non detenuti (SPCX, WFC) restano fuori dal conteggio come nelle sedute precedenti; il dossier (`cause_del_giorno`) conta NO_NEWS 5 includendoli.

**Il NO_NEWS di oggi non è un vuoto delle fonti, e non esiste testo da leggere.** news_log non ha righe dal 2026-10-08 al 2026-10-16 (conteggi giornalieri su DB: 10-08 160, poi 10-16 205, nulla in mezzo; idem `sentiment_signals`). Il catalizzatore di INFY e ORCL non è ricostruibile (`event_market_context.*.catalyst.type` UNKNOWN, calendario NOT_OBSERVED); per ERIC il dossier vede solo un evento `dividend` (Alpaca Corporate Actions). Anche con le news, dalle 11:03Z nessun ciclo portfolio avrebbe potuto comprare (§8, F-085).

Mover detenuti all'open (non sono miss; `funnel_v2.righe` + `snapshot_apertura`):

| Simbolo | Strategia | Return | Stadio d'uscita (segnale stantio) | P&L di seduta (actual_intraday_pnl_usd) |
|---|---|---:|---|---:|
| AMAT | S1 | −6,69% | STALE_EXIT_SIGNAL (signal 14786 del 10-08, +0,039) | −18,13 $ |
| JNJ | S1 | −5,73% | STALE_EXIT_SIGNAL (signal 14768 del 10-08, +0,090) | −18,49 $ |
| C | S1 | −5,60% | STALE_EXIT_SIGNAL (signal 14703 del 10-08, +0,250) | −40,24 $ |
| MU | S4 | −3,62% | STALE_EXIT_SIGNAL (signal 14808 del 10-08, −0,829) | +8,86 $ (open→close; il calo è nel gap) |
| CAT | S1 | −3,33% | STALE_EXIT_SIGNAL (signal 14644 del 10-07, −0,205) | −16,70 $ |
| BP | S1 | +3,85% | PASSIVE_EXPOSURE (held_rising) | +10,24 $ |

Catturati: 6, cioè i mover detenuti all'open; 5 dal lato perdente. JNJ e C avevano earnings in giornata (`observed_catalysts` CALENDAR), visibili solo al calendario e non alla pipeline sentiment. Nessun ingresso nella seduta.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":[],"chiusure":[]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
<!-- alpha-miss-book:end -->
Il dossier non ha ingressi (`ingressi` = []), né chiusure (`chiusure` = []), né intenti S4 (`intenti_ingresso_s4` = []). Non è inattività per scelta: execution_decisions e portfolio_cycles hanno 0 righe il 10-13 (24 cicli il 10-12), e Alpaca non registra ordini nella seduta, nemmeno fill di stop. Il book detenuto all'open (39 posizioni) vale +55,29 $ open→close (S1 −85,94, S4 +141,23; `snapshot_apertura`), contro −189,26 $ close-to-close di Alpaca (110.183,38 $, riga timbrata 2026-10-14T00:00Z, cfr. F-053): la differenza è il gap d'apertura.

## 5. Cecita' lato uscita
Sei posizioni con `cieco_lato_uscita: true` su 39 (`copertura_uscita.aggregato`: soglia −3% dall'ingresso, `sedute_minime` 2, `n_indeterminati` 0, notional cieco 1.985,80 $: esposizione, non costo). Nessuna riga ha `cieco_lato_uscita` null.

| Ticker | Strategia | ritorno_da_ingresso | ritorno_seduta | sedute_consecutive_senza_righe | fonti_osservate_finestra | uscita nella seduta |
|---|---|---:|---:|---:|---|---|
| AMAT | S1 | −21,82% | −6,69% | 3 | alpaca_benzinga, gdelt_gkg | no |
| ARM | S1 | −11,49% | +0,06% | 3 | alpaca_benzinga | no (residuo 11,2 $) |
| C | S1 | −6,38% | −5,60% | 3 | alpaca_benzinga | no |
| CAT | S1 | −4,92% | −3,33% | 4 | alpaca_benzinga, gdelt_gkg | no |
| NOK | S1 | −15,87% | −0,40% | 5 | alpaca_benzinga, gdelt_gkg | no (residuo 5,6 $) |
| WDC | S4 | −30,68% | −1,61% | 5 | alpaca_benzinga | no |

Le fonti della finestra non sono vuote: i provider hanno reso su tutti e sei nelle sedute precedenti. Per AMAT, ARM e C lo streak di 3 coincide esattamente con l'interruzione (10-09, 10-12, 10-13). C entra oggi nella lista, con earnings in giornata. JNJ (−5,73% di seduta) non è cieca per la definizione perché il `ritorno_da_ingresso` è −1,62%, sopra la soglia. L'alert `held_news_loss_alert` delle 22:50Z non può essere girato: worker senza Redis dalle 11:03Z e 0 righe in `mobile_notification_deliveries` il 10-13.

## 6. Backstop NO_NEWS
Marker calendario: 4/11 mover hanno `observed_catalysts` CALENDAR (`calendar_observation.mover_observed` 4/11 contro 3/85 non-mover). Earnings FMP: C, JNJ, WFC; dividendo Alpaca: ERIC. Gli altri mover (AMAT, BP, CAT, INFY, MU, ORCL, SPCX) hanno calendario NOT_OBSERVED con entrambe le fonti riuscite. Fra i non-mover, earnings su GS, JPM, UNH. CALENDAR significa evento osservato, non segnale né ordine.

Volume (`POST_HOC_EOD`, `valid_for_signal_evaluation` false): mediana della sorpresa di volume +0,497 sui mover, −0,114 sui non-mover. È nota solo a chiusura e non era disponibile prima del movimento. Nessuna soglia, nessun false-positive rate (studio ex-ante in #451).

Copertura raw `news_log` per settore (`no_news_backstop.per_sector`; distinta dalla effective-timely di `copertura_articoli.per_settore`, anch'essa 0/96 oggi):

| Settore | ticker_with_news/ticker_universe | raw_news_coverage_rate | zero_news_movers | calendar_observed_zero_news |
|---|---|---:|---:|---:|
| consumer | 0/11 | 0,000 | 0 | 0 |
| energy | 0/6 | 0,000 | 1 | 0 |
| etf_broad | 0/4 | 0,000 | 1 | 0 |
| financials | 0/14 | 0,000 | 2 | 4 |
| healthcare | 0/9 | 0,000 | 1 | 2 |
| industrials | 0/4 | 0,000 | 1 | 0 |
| materials | 0/2 | 0,000 | 0 | 0 |
| media | 0/5 | 0,000 | 0 | 0 |
| semis | 0/15 | 0,000 | 2 | 0 |
| tech | 0/21 | 0,000 | 2 | 0 |
| telecom | 0/5 | 0,000 | 1 | 1 |

Attribuzione fonti per ticker (#511 passo 2): tutti i 96 ticker di `copertura_articoli.per_ticker` hanno `articoli_unici` 0 e `fonti_osservate` `{}`, con `blind_set.per_ticker.articoli_unici_giorno` 0 e `effective_timely_articles_giorno` 0 (`copertura_articoli.per_fonte` è `{}`). Ogni riga è quindi "nessuna fonte ha reso righe news_log"; oggi il motivo è a valle dei provider (consumatore assente), non i provider. Fino alle 11:00Z la coda continuava a crescere (`news_queue_census.queue_depth` 1.819 → 1.853), poi il censimento si ferma con lo stack. Ticker: tutti i 96 di `mercato.rendimenti` (appendice a). `blind_set.ticker_allerta_zero_articoli` (streak ≥5): ASML, BRK.B, CMCSA, CRM, DB, INFY, JD, MMM, NOK, PBR, RDDT, RIO, ROKU, TXN, UBS, UNH, VALE, WDC.

## 7. Pattern osservato
Apertura della stagione earnings, con le banche e JNJ in calo nel giorno del report: C −5,60%, WFC −3,10%, JNJ −5,73%, MS −1,78%, BAC −1,14%, JPM −0,86%, GS −0,23% (XLF −0,42%, XLV −1,35%). Seconda linea: semis equipment e memoria deboli (AMAT −6,69%, MU −3,62%, ASML −1,86%) mentre il resto dei semis sale (TXN +2,17%, AMD +1,90%, INTC +1,44%; SOXX −0,17%). La debolezza AMAT/MU ricorre dal 10-08 (report 10-09 e 10-12). Al rialzo: INFY +5,26%, ORCL +4,23%, ERIC +3,63%, e l'energia (BP +3,85%, XLE +1,80%). SPY −0,01%, QQQ −0,33%. I catalizzatori di INFY e ORCL non sono ricostruibili per assenza di testo.

## 8. Segnalazioni

* [F-085] Redis va in MISCONF (snapshot RDB non persistibile, disco pieno) alle 11:03:12Z. Il worker principale muore con "Unrecoverable error" e resta in reconnect fino alla fine dei log (16:08Z). La seduta RTH passa per intero senza un ciclo portfolio e senza alcun alert. Rispetto al record (11 minuti il 2026-09-16) è un peggioramento materiale: un'intera seduta.
  * esposizione: 1 seduta RTH intera (13:30–20:00Z). execution_decisions 0 righe e portfolio_cycles 0 il 10-13 (24 il 10-12); 0 righe anche il 10-14 e il 10-15, ripresa il 10-16 con 23 cicli. Ordini Alpaca nella seduta: 0. Il worker riceve 0 task dopo le 11:03:12Z; il beat registra 17.550 errori MISCONF. Il disco host oggi è al 93% (22 GB liberi). Non esistono file di log per il 10-14 (scrittura dei log interrotta alle 16:08Z).
  * evidenza contraria: se il finding fosse falso, il 10-13 avrebbe righe in execution_decisions o portfolio_cycles, task "received" nel worker dopo le 11:03Z, o un censimento della coda dopo le 11:00Z. Nessuna delle quattro esiste.
  * non-occorrenza: l'api ha continuato a rispondere a `/api/health` con 200 OK (0 righe MISCONF in `api-2026-10-13.log`). Il guasto colpisce chi scrive su Redis, e l'healthcheck non lo vede. Gli stop GTC al broker restano attivi ma non sono scattati.
  * next evidence: `docker logs alembic-redis-1` / log host del 10-13 per l'ora di riempimento del disco e cosa l'ha riempito; dossier 10-14 e 10-15 (attesi a 0 decisioni) per misurare l'estensione; `mobile_notification_deliveries` 10-13→10-16 per confermare che nessun alert sia partito (oggi 0 righe, ultimo `mobile_events` alle 06:14Z).
  * meccanismo e fonte: §1, §4, §5. Campi: `ingressi`/`chiusure`/`intenti_ingresso_s4` vuoti, `decision_signal_id_coverage.total_rows` 0. Log: `worker-2026-10-13.log` riga 6255 (CRITICAL MISCONF), `beat-2026-10-13.log`; DB portfolio_cycles/execution_decisions/news_queue_census. Difetto operativo: nessun watchdog su disco o su Redis in sola lettura, e un health dell'api che resta verde.
  * costo: non stimato (null). Nessun segnale fresco esisteva (F-096), quindi i cicli mancati non avrebbero aperto le 3 ENTRY_OPPORTUNITY: contarle qui le conterebbe due volte. Il costo lato uscita richiede un controfattuale per-ciclo che il dossier non fornisce. Alternativa scartata: «seduta vuota per scelta della strategia (nessun intento tradabile)», smentita da 0 righe in execution_decisions: il 10-12, con gli stessi segnali stantii, il ciclo aveva scritto 300 decisioni e 282 intent. Alternativa scartata: «outage di rete» (F-094), smentita dalla risposta esplicita di Redis (MISCONF) e dall'api viva.
* [F-096] Il consumatore della coda sentiment (`worker-inference`) resta assente per la terza seduta consecutiva (10-09, 10-12, 10-13) dopo il warm shutdown del 2026-10-08: 0 righe news_log e 0 segnali su 96/96 simboli, nessun alert.
  * esposizione: 1 seduta intera su 96/96 simboli (`mercato.watchlist_zero_news` 96; `copertura_articoli.totali.righe_news_log` 0). 3 ENTRY_OPPORTUNITY NO_NEWS (INFY, ORCL, ERIC) e 5 EXIT_RISK con `pipeline_uscita` STALE_EXIT_SIGNAL (segnali del 10-07/10-08). Nessun `worker-inference-2026-10-13.log`; il primo dopo il guasto è del 10-16. Fino alle 11:03Z il beat emette 9 `sentiment-worker` e 13 `sentiment-shadow-offsession`, mai eseguiti; la coda sale da 1.819 a 1.853.
  * evidenza contraria: se il finding fosse falso, il 10-13 avrebbe righe in news_log o sentiment_signals, o un log del worker-inference. Su DB i conteggi passano da 10-08 (160) a 10-16 (205) senza righe in mezzo.
  * non-occorrenza: fino alle 11:03Z worker principale e beat girano (1.464 task ricevuti nel log del worker). Il calendario earnings è OBSERVED e vede C/JNJ/WFC: il buco è circoscritto alla pipeline news→sentiment.
  * next evidence: `stale_drop_metrics_daily` del 10-16, per misurare quanta coda è scaduta alla ripartenza (cfr. F-069); confronto fra il primo log `worker-inference-2026-10-16.log` e il deploy del 10-16, per sapere cosa ha fatto ripartire il consumatore.
  * meccanismo e fonte: §1, §3, §5, §6. Campi: `copertura_articoli.totali`, `no_news_backstop.population.zero_news` 96, `funnel_v2.kpi.exit_signal_recall` 0/5, `copertura_uscita.aggregato.ticker_ciechi`. È lo stesso difetto del 10-09 e del 10-12; oggi le sue conseguenze sono mascherate dal F-085 dalle 11:03Z in poi.
  * costo: congetturale, 2.200 $ × (|ret INFY| + |ret ORCL| + |ret ERIC|) = 2.200 × (0,0526 + 0,0423 + 0,0363) = 288,65 $ (legacy `opportunity_v2.legacy.costo_usd`: 115,79 + 93,03 + 79,83). L'opportunità netta accessibile del dossier è 88,08 $ (−14,68 + 52,92 + 49,83). Alternativa scartata: «i provider non coprivano la watchlist» (F-001), smentita dalla coda in crescita (+34 elementi fino alle 11:00Z) con un consumatore assente. Alternativa scartata: «la mancanza di news è tutta colpa del F-085», smentita dal fatto che il vuoto di news_log inizia il 10-08, cinque giorni prima del MISCONF.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli)

| # | Simbolo | Return |
|---:|---|---:|
| 1 | INFY | +5,26% |
| 2 | ORCL | +4,23% |
| 3 | BP | +3,85% |
| 4 | ERIC | +3,63% |
| 5 | META | +2,63% |
| 6 | TXN | +2,17% |
| 7 | TM | +2,16% |
| 8 | GM | +1,98% |
| 9 | AMD | +1,90% |
| 10 | XLE | +1,80% |
| 11 | VZ | +1,75% |
| 12 | CRM | +1,75% |
| 13 | V | +1,74% |
| 14 | IBM | +1,66% |
| 15 | MA | +1,63% |
| 16 | T | +1,60% |
| 17 | INTC | +1,44% |
| 18 | QCOM | +1,39% |
| 19 | SHEL | +1,38% |
| 20 | CVX | +1,27% |
| 21 | TMUS | +1,22% |
| 22 | HOOD | +1,19% |
| 23 | MMM | +1,17% |
| 24 | HD | +1,14% |
| 25 | XOM | +1,12% |
| 26 | MRVL | +1,08% |
| 27 | NVDA | +0,97% |
| 28 | CMCSA | +0,97% |
| 29 | SAP | +0,87% |
| 30 | F | +0,83% |
| 31 | AVGO | +0,73% |
| 32 | BRK.B | +0,58% |
| 33 | MSFT | +0,43% |
| 34 | PBR | +0,31% |
| 35 | GOOGL | +0,30% |
| 36 | SONY | +0,29% |
| 37 | JD | +0,22% |
| 38 | TSM | +0,17% |
| 39 | AAPL | +0,09% |
| 40 | DIS | +0,08% |
| 41 | MCD | +0,07% |
| 42 | BABA | +0,06% |
| 43 | UBS | +0,06% |
| 44 | ARM | +0,06% |
| 45 | SPY | −0,01% |
| 46 | XLK | −0,04% |
| 47 | NKE | −0,06% |
| 48 | ROKU | −0,10% |
| 49 | PG | −0,11% |
| 50 | PFE | −0,11% |
| 51 | PLTR | −0,16% |
| 52 | SOXX | −0,17% |
| 53 | UNH | −0,20% |
| 54 | NFLX | −0,21% |
| 55 | GS | −0,23% |
| 56 | CSCO | −0,23% |
| 57 | SBUX | −0,31% |
| 58 | GE | −0,33% |
| 59 | QQQ | −0,33% |
| 60 | AMZN | −0,37% |
| 61 | NOK | −0,40% |
| 62 | XLF | −0,42% |
| 63 | IWM | −0,43% |
| 64 | COST | −0,50% |
| 65 | AXP | −0,54% |
| 66 | BIDU | −0,66% |
| 67 | WMT | −0,71% |
| 68 | SNOW | −0,72% |
| 69 | TSLA | −0,74% |
| 70 | DELL | −0,74% |
| 71 | ADBE | −0,78% |
| 72 | JPM | −0,86% |
| 73 | DB | −0,92% |
| 74 | VALE | −1,11% |
| 75 | BAC | −1,14% |
| 76 | NOW | −1,22% |
| 77 | RIO | −1,31% |
| 78 | NVO | −1,35% |
| 79 | XLV | −1,35% |
| 80 | LLY | −1,36% |
| 81 | AZN | −1,59% |
| 82 | BA | −1,59% |
| 83 | WDC | −1,61% |
| 84 | PANW | −1,68% |
| 85 | MS | −1,78% |
| 86 | ASML | −1,86% |
| 87 | MRK | −2,39% |
| 88 | ABBV | −2,40% |
| 89 | RDDT | −2,90% |
| 90 | WFC | −3,10% |
| 91 | CAT | −3,33% |
| 92 | MU | −3,62% |
| 93 | SPCX | −4,21% |
| 94 | C | −5,60% |
| 95 | JNJ | −5,73% |
| 96 | AMAT | −6,69% |
### (b) Altri finding aperti toccati dalla giornata

- [F-001] not_exposed: la copertura 0/96 oggi è prodotta dal consumatore assente (F-096), non dalla resa dei provider; non è misurabile.
- [F-036] not_exposed: 0 cicli portfolio, quindi nessuna revisione delle posizioni; WDC −30,68% e AMAT −21,82% dall'ingresso restano senza valutazione.
- [F-048] not_exposed: nessun fill di stop nella seduta (0 ordini Alpaca); la divergenza ARM/NOK del 10-12 resta aperta (residui 11,2 $ e 5,6 $ in `copertura_uscita`).
- [F-053] supported: la riga Alpaca della seduta 10-13 è timbrata 2026-10-14T00:00Z.
- [F-062] supported: 0 righe `mobile_notification_deliveries` il 10-13 nonostante uno stack giù per l'intera RTH.
- [F-094] not_exposed: il guasto è di Redis/disco (MISCONF esplicito), non di rete; resta valida la parte "nessun alert recapitato".
- [F-022] not_exposed: nessuno stop è scattato; le posizioni non proteggibili (qty < 1) restano esposte.

### (c) Casi di successo
Nessun mover catturato con P&L positivo da un ingresso della seduta (0 ingressi). L'unico mover detenuto in rialzo è BP +3,85% (PASSIVE_EXPOSURE, +10,24 $ open→close), ma è esposizione passiva, non una cattura.
