# Alpha Miss Report — 2026-09-09

Contratto `alpha_miss_prompt_v2` · dossier `docs/evidence/dossier/2026-09-09.json`, `schema_version` 3.1, `generato_il` 2026-09-24T07:07:42Z (seduta **recuperata** 15 giorni dopo: prezzi Alpaca SIP `adjustment=all`). Soglia mover `soglia_mover` = 3%. Periodo di sola osservazione (charter): nessuna taratura proposta.

## 1. Decision card

1. **7 mover su 96, nessuno catturato da un ingresso del giorno**: META +6,55% (score 0,234 < gate 0,30), IBM +3,38% (zero righe `news_log`); i 3 mover in portafoglio (MRVL, AMD, SPCX) erano già detenuti all'open (`funnel_v2.kpi.held_at_open_rate` = 3/7).
2. **La coda notturna delle news ha buttato come stale 177 righe (58 articoli) alle 13:37 UTC, al primo drenaggio della seduta**. Fra queste c'erano il pezzo pre-market su Muse (META, 04:02) e l'unica notizia societaria su UNH (vendita WellMed a TPG, 08:12). UNH è una delle 2 posizioni cieche lato uscita (−8,65% dall'ingresso, 4 sedute senza righe).
3. **Book S4 realizzato −59,51 $** (SPCX chiusa per `sentiment_reversal` su un articolo issuer-specific relativo al lockup; `drift_post_uscita` +1,03%); equity Alpaca a fine seduta 109.766,92 $.

## 2. Stato carta

Fonte `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18). **Il 2026-09-09 non figura fra i giorni osservati** (`scoreboard.giorno.osservati` passa da 09-08 a 09-11): è una seduta persa, recuperata ora. I cumulati qui sotto non la contengono.

- Giorno **30/40** della finestra (`scoreboard.giorno.n`); 09-09 ne resta fuori finché il materializzatore non la registra.
- Giorni con NO_NEWS dominante: **13/30** (43,3%), sotto la soglia carta 0,60 (`superata_soglia` false). Oggi la causa dominante non è NO_NEWS ma `BELOW_GATE` (`aggregati.cause_del_giorno.dominante`).
- S4 economico cumulato: **−696,33 $**, fuori dalla banda ±200 $ (`s4_vs_200.within` false).
- Per contesto: S1 cumulato +664,95 $, −279,03 $ rispetto a SPY sulla stessa base. Il book cumulato vale −66,22 $.

## 3. Miss del giorno

4 candidati in `candidati_miss`, tutti mover non detenuti. **Nessun FILTERED possibile**: `funnel_v2.conteggi_pipeline` = {"NO_RELEVANT_NEWS":1,"BELOW_GATE":1}, cioè nessuna riga arriva oltre il gate. Le guardie del giorno sono solo `SKIP_THRESHOLD` (715, che *è* il gate) e `SKIP_PYRAMIDING` (13), e nessuna delle due tocca un candidato del giorno oltre il gate.

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| META | +6,55% | **THIN_NEUTRAL** | `funnel_v2.righe[META].pipeline`="BELOW_GATE", `evidence.score_firmato`=0,2338 contro `soglia_gate`=0,30: segno corretto, sotto il gate. Lettura degli articoli: il punteggio massimo viene da "Meta Trending After Unveiling Muse, Its First Personal AI Agent", pubblicato alle **11:44** ma acquisito e scorato alle **13:38**. Latenza `first_seen_to_ingested` di 6.857 s nella `timeline`, e il pezzo constata il trend, non lo anticipa. Il catalizzatore vero, "Meta's Muse AI Agent Promises to Handle Your Digital Life…" delle **04:02**, è stato scartato come `stale` alle 13:37 (`news_queue_drops`, vedi §8 F-069). Il movimento era quasi tutto nel gap: `movimento.gap_return` +5,73% contro `intraday_return` +0,78%. Per questo `opportunity_v2.net_opportunity_usd` vale solo **6,13 $** a fronte di 144,17 $ lordi. 4 delle 7 righe sono fan-out (`quota_righe_fanout` 0,571), e una è un pezzo su Snap taggato META. |
| IBM | +3,38% | **NO_NEWS** | `news_count`=0, `funnel_v2.righe[IBM].pipeline`="NO_RELEVANT_NEWS" con `evidence.rilevanza` tutto a zero. `blind_set.per_ticker[IBM].sedute_consecutive_zero_articoli` = **7**, ed è in `ticker_allerta_zero_articoli`. `event_market_context[IBM].catalyst.type`="UNKNOWN". In coda c'era una sola riga, scartata stale alle 13:37: un editoriale generico ("AI Will Transform the World, but Legendary Investor Warns…", 10:56), non sull'emittente. `net_opportunity_usd` = **82,29 $**, il miss più costoso della giornata in termini accessibili. |
| CMCSA | −6,61% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[CMCSA].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only": ribasso, non detenuto, book long-only. Il campo grezzo `causa` è "NON_ACTIONABLE" (`causa_legacy` "NON_CLASSIFICATO"). Da annotare: il segnale **−0,386** ha il segno corretto, è sopra il gate, ISSUER_SPECIFIC ("Comcast CFO Says Q3 Broadband Subscriber Losses Unlikely To Improve…", 15:27), e non poteva produrre ordini per costruzione (F-040, §9b). |
| F | −3,93% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[F].actionability`="NON_ACTIONABLE" (ribasso non detenuto). Il campo grezzo `causa` è "BELOW_GATE": `max_score_own` null, `max_score_fanout` −0,204, 3 righe tutte TAG_UNCONFIRMED. Lettura degli articoli: il tema è l'ipotesi di auto cinesi vendute negli USA (Slotkin, 16:22), segno corretto ma nessuna riga issuer-specific. |

**Conteggi**: NO_NEWS 1 · THIN_NEUTRAL 1 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 2. `aggregati.cause_del_giorno` resta invariato per il vincolo #288: {"NO_NEWS":1,"BELOW_GATE":2,"NON_CLASSIFICATO":1}, dominante "BELOW_GATE".

Metodo: come il 09-15 e il 09-17, dove i due campi divergono preferisco l'asse `actionability`/`pipeline` di `funnel_v2` al campo grezzo `causa`.

### Titoli catturati (mover in portafoglio)

Nessun ingresso del giorno è su un mover: MU chiude a +2,75%, DIS a −0,84%. Nessuna riga `CAUGHT`/`BAD_FILL` in `funnel_v2`.

| Simbolo | Return% | Come | Esito |
|---|---:|---|---|
| MRVL | +4,26% | detenuto all'apertura (S1, trade 312) | `PASSIVE_EXPOSURE`. `snapshot_apertura[MRVL].passive_pnl_usd` = **+6,18 $**. 4 intenti S4 sono finiti in `SKIP_PYRAMIDING`. |
| AMD | +3,04% | detenuto all'apertura (S1, trade 307) | `PASSIVE_EXPOSURE`, +11,06 $ sulla seduta; `ritorno_da_ingresso` resta −5,91%. |
| SPCX | −3,86% | detenuto all'apertura (S4, trade 988), **uscito** | `EXIT_RISK`. Chiuso alle 15:22 @ 147,44 per `sentiment_reversal`, `pnl_net` **−59,51 $**. Il segnale 10117 (−0,435, ISSUER_SPECIFIC) è "SpaceX Lockup Alert — 319 Million SPCX Shares Unlock Today": è un'uscita su una notizia vera dell'emittente, non un fan-out. `drift_post_uscita` +1,03%: tenere fino al close avrebbe reso poco di più. `actual_intraday_pnl_usd` −43,03 contro `passive_pnl_usd` −42,00. |

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["MU","DIS"],"chiusure":["SPCX"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | MU | S4 | 14:52 | $1035.4060 | 0.4070 | — | percentile 86.04%; denominatore intraday valido |
| IN | DIS | S4 | 18:52 | $104.4935 | 13.8433 | — | percentile 77.50%; denominatore intraday degenere: quota non interpretabile |
| OUT | SPCX | S4 | — | $147.4400 | 9.3552 | −$59.51 | sentiment_reversal |
<!-- alpha-miss-book:end -->

Due ingressi S4 sopra il gate, entrambi su non-mover. MU alle 14:52 (score 0,325) con `entry_percentile` 0,860 e `quota_movimento_precedente_al_segnale` **1,26**, cioè dopo che il movimento del giorno era già stato consumato; `mtm_eod` −3,11 $. DIS alle 18:52 (0,351) con denominatore degenere; `mtm_eod` −4,34 $. Una chiusura, SPCX −59,51 $, vedi §3. Nella seduta gli intenti S4 tradabili sono 120: 114 `SKIP_PYRAMIDING`, 4 `SKIP_IDEMPOTENCY`, 2 `SUBMITTED`.

## 5. Cecità lato uscita

Fonte `copertura_uscita`, 45 posizioni, `n_indeterminati` 0 (nessun `cieco_lato_uscita: null`). Sono cieche **2** posizioni, entrambe S1, entrambe ancora aperte, per 1.428,15 $ di nozionale (`aggregato.notional_cieco_usd`).

| Ticker | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` |
|---|---:|---:|---:|---|
| UNH | **−8,65%** | −1,94% | 4 | ["alpaca_benzinga"] |
| PFE | −3,17% | −0,04% | 3 | ["alpaca_benzinga"] |

Nota su UNH: nel mondo di `news_log` risulta a zero righe, ma la notizia societaria c'era. "'UnitedHealth Sells Interest in Florida WellMed Clinics to TPG' - Bloomberg" (08:12) e un pezzo CMS/Oz (08:22) sono entrati nella coda notturna e sono stati scartati stale alle 13:37 (`news_queue_drops`, età 5,4 h). La cecità di oggi su UNH non viene dal provider: viene dalla coda (§8, F-069). Su PFE nessuna riga in coda nella seduta.

## 6. Backstop NO_NEWS

- **Marker calendario**: l'unico mover NO_NEWS, IBM, ha `observed_catalysts` = [] e `calendar.status` "NOT_OBSERVED" (FMP e Alpaca Corporate Actions entrambi riusciti). Nessun evento societario osservato; `calendar_observation.mover_rate` 0/1.
- **Volume, marcato `POST_HOC_EOD`**: la mediana della volume surprise vale +0,353 sui mover (n=1, IBM, `adv_ratio` 1,35) e −0,113 sui non-mover (n=37). Il valore è noto solo al close, quindi non era disponibile prima del movimento. Non è un segnale e non va usato per scegliere una soglia; la valutazione ex-ante resta #451.
- **Copertura raw `news_log` per settore** (`no_news_backstop.per_sector`, distinta dalla effective-timely di `copertura_articoli.per_settore`):

| Settore | con news / universo | `raw_news_coverage_rate` | mover zero-news | calendario osservato (zero-news) |
|---|---:|---:|---:|---:|
| consumer | 8/11 | 72,7% | 0 | 0 |
| energy | 3/6 | 50,0% | 0 | 0 |
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| financials | 5/14 | 35,7% | 0 | 0 |
| healthcare | 6/9 | 66,7% | 0 | 0 |
| industrials | 3/4 | 75,0% | 0 | 0 |
| materials | 2/2 | 100,0% | 0 | 0 |
| media | 3/5 | 60,0% | 0 | 0 |
| semis | 10/15 | 66,7% | 0 | 0 |
| tech | 12/21 | 57,1% | 1 | 0 |
| telecom | 2/5 | 40,0% | 0 | 0 |

Totale zero-news: 38/96 (`population.zero_news`), di cui 1 mover.

### Attribuzione fonti per ticker (#511 passo 2)

I 38 ticker con `articoli_unici == 0` hanno tutti `fonti_osservate` = {}. Nessuna fonte ha reso righe su di loro, quindi è il caso "fonte assente", non "fonte presente ma non utile". Per ognuno `articoli_unici_giorno` = 0 e `effective_timely_articles_giorno` = 0 (`blind_set.per_ticker`). Fra parentesi `sedute_consecutive_zero_articoli`, sulla finestra 2026-08-26 → 2026-09-09:

AMAT (1), ARM (1), ASML (2), AXP (1), BAC (3), BIDU (1), BP (7), BRK.B (4), C (2), COST (2), CSCO (6), DB (1), ERIC (7), IBM (7), INFY (5), JD (7), MA (1), MCD (3), MMM (2), NFLX (1), NOK (1), NOW (1), NVO (1), PANW (1), PBR (7), PFE (3), RDDT (1), SAP (7), SHEL (1), SONY (7), T (1), TXN (3), UBS (5), UNH (4), V (1), WDC (1), WFC (5), WMT (2).

`ticker_allerta_zero_articoli` (soglia 5 sedute): BP, CSCO, ERIC, IBM, INFY, JD, PBR, SAP, SONY, UBS, WFC. Nessun ticker ha `fonti_osservate` non vuoto con effective-timely a zero. Per fonte (`copertura_articoli.per_fonte`): alpaca_benzinga ha reso 117 articoli unici, 67 effective-timely; gdelt_gkg 8, tutti e 8 effective-timely.

## 7. Pattern osservato

**Pattern non chiaro.** I mover sono pochi (7) e hanno catalizzatori propri, visibili nel testo degli articoli:
- META: agente AI Muse e acquisizione di Stilla.ai;
- CMCSA: guidance sugli abbonati broadband;
- F: voci sulle auto cinesi vendute negli USA;
- SPCX: sblocco di 319 milioni di azioni.

Il contesto macro, sempre dal testo degli articoli, è greggio sopra i 100 $ e rendimento del decennale al massimo triennale: SPY −0,46%, IWM −1,37%, mentre l'energia sale (XOM +2,22%, CVX +1,91%, XLE +0,82%). Ci sono due richiami alla seduta del 09-17: MRVL e AMD, entrambi detenuti da S1, sono di nuovo fra i mover rialzisti, e CMCSA fra i ribassisti. Su due sole sedute non basta per parlare di un tema ricorrente.

## 8. Segnalazioni

Denominatori: `docs/evidence/longitudinal_panels.json` **non esiste**. I conteggi sono quindi quelli delle occorrenze di `findings.json`, contati da me e dichiarati come tali.

### [F-069] La coda notturna viene drenata all'apertura e scarta come stale proprio le notizie pre-market sui mover e sulle posizioni cieche

- **Esposizione**: 1 seduta. Nella finestra 00:00–20:00Z del 09-09, `news_queue_drops` conta 177 righe `stale` con `enqueued_off_session`=true (58 articoli), contro 18 righe (7 articoli) accodate in seduta. Il lotto off-session è caduto quasi tutto alle 13:37, come già registrato nel charter (analisi #432, 15/09). In `findings.json` il finding ha 4 occorrenze su 4 giorni distinti (09-07 → 09-22); questa è la quinta seduta.
- **Meccanismo e fonte**: il WebSocket riceve il pezzo (`published_to_first_seen` 0,19 s), ma il consumatore è gated da `market_closed`. All'apertura il backlog scade oltre `MAX_NEWS_AGE_HOURS`=2 e viene scartato; sopravvive solo ciò che è stato pubblicato meno di 2 ore prima. Oggi il meccanismo ha colpito due punti:
  - (i) META: il pezzo Muse delle 04:02 è stato scartato, quello delle 11:44 è sopravvissuto ed è stato scorato alle 13:38 con 0,234 (§3; `timeline` signal 10049, `latenze_secondi.first_seen_to_ingested` 6.856,9);
  - (ii) UNH: le uniche due notizie societarie della seduta sono state scartate, e la posizione figura come `cieco_lato_uscita: true` (§5; `copertura_uscita.posizioni[UNH]`).
  Il meccanismo non è un bug nuovo: è il limite noto già registrato in F-069.
- **Costo**: **19,18 $** (misurata) = `snapshot_apertura[UNH].passive_pnl_usd`, cioè la perdita subita nella seduta dalla posizione UNH mentre la sua sola notizia societaria del giorno veniva scartata. È un'esposizione misurata, non un costo causale: nessuno sa se quel titolo avrebbe prodotto un segnale d'uscita.
- **Evidenza contraria**: se il finding fosse falso, le righe scartate stale all'apertura sarebbero rumore già prezzato o non riferito a titoli rilevanti. Oggi fra le 17 righe stale sui ticker del §3/§5 ci sono il catalizzatore di META (+6,55%) e l'unica notizia societaria di UNH (Bloomberg). Il finding sarebbe contraddetto anche da un segnale utile arrivato comunque su META prima dell'apertura: il primo punteggio è alle 13:38, dopo l'open delle 13:30.
- **Non-occorrenza**: su IBM la coda non spiega il NO_NEWS. L'unica riga scartata è un editoriale generico, non sull'emittente, quindi lì il vuoto è del provider. Su PFE, l'altra posizione cieca, non c'è nessuna riga in coda. Su CMCSA la notizia decisiva è arrivata in seduta (15:27) ed è stata scorata in un minuto.
- **Next evidence**: su tutte le sedute dal 2026-09-01, incrociare `news_queue_drops` (`stale`, `enqueued_off_session`=true) con `copertura_uscita.posizioni` dei dossier. Contare quante posizioni marcate cieche lato uscita avevano almeno una riga issuer-specific scartata in coda nella stessa seduta. Se la quota è materiale, "cieco" misura la coda e non la copertura dei provider. Sola lettura.
- **Alternative scartate**: che il vuoto su UNH sia una lacuna del provider. Scartata: le due righe UNH erano in coda con `source` Benzinga, e l'ultima è stata scartata alle 13:37 con `age_hours` 5,24–5,41.

### [F-009] Il gate 0,30 scarta META, segno corretto su un +6,55%, ma oggi il gate non è il vincolo che lega

- **Esposizione**: 1 solo mover ENTRY_OPPORTUNITY con notizia tempestiva (`funnel_v2.kpi.active_signal_recall` 0/1), cioè META. In `findings.json` il finding ha 21 occorrenze su 20 giorni distinti (08-03 → 09-11).
- **Meccanismo e fonte**: §3; `funnel_v2.righe[META].evidence.score_firmato` = 0,2338 < `soglia_gate` 0,30. Il pezzo migliore constata un trend ("Trending After Unveiling Muse") e la magnitudine resta sotto soglia. Le righe successive (acquisizione di Stilla.ai 0,083, "Meta and Cloudflare Jump" 0,091) scorano ancora meno. `intenti_ingresso_s4`: META 15 `SKIP_ENTRY_GATE` e 9 `SKIP_ENTRY_FRESHNESS`.
- **Costo**: **6,13 $** (congetturale) = `candidati_miss[META].opportunity_v2.net_opportunity_usd`. Formula del dossier: (exit_close 653,17 − entry_open 651,22 al primo ciclo eleggibile) × azioni su uno slot da 2.200 $, meno 0,45 $ di costi di roundtrip. Il lordo close-to-close di 144,17 $ non è accessibile.
- **Evidenza contraria**: se il gate fosse il collo di bottiglia, superarlo avrebbe catturato il movimento. Non è così: l'87% del rendimento è nel gap (`gap_return` +5,73% su +6,55%). Anche un segnale sopra soglia alle 13:38 sarebbe arrivato al primo ciclo delle 14:07 con il movimento già consumato. Oggi il gate costa 6 $, non 144.
- **Non-occorrenza**: nessun altro mover rialzista ha avuto uno score col segno corretto sotto il gate. IBM non ha righe, MRVL e AMD erano detenuti.
- **Next evidence**: sulle sedute con occorrenze F-009, separare il costo accessibile (`opportunity_v2.net_opportunity_usd`) da quello lordo e contare in quante il gap supera metà del rendimento di seduta. Se nella maggioranza il gap domina, il costo del gate è sovrastimato dalla serie legacy. Sola lettura sui dossier.
- **Alternative scartate**: che META sia un NO_NEWS mascherato, con le 7 righe tutte fan-out. Scartata: la riga che decide (signal 10049) è ISSUER_SPECIFIC su META, ed è il `max_score_own`.

### [F-030] L'unico ingresso "vicino a un mover" nasce a movimento già consumato

- **Esposizione**: 2 ingressi nella seduta, di cui 1 con quota non degenere (MU, `quota_movimento_precedente_al_segnale` 1,264, `entry_percentile` 0,860). In `findings.json` il finding ha 19 occorrenze su 18 giorni distinti (08-07 → 09-22).
- **Meccanismo e fonte**: §4; `ingressi[MU]`. Il segnale 0,325 supera il gate quando il 126% del movimento intraday è già avvenuto, e il fill nasce all'86° percentile del range. `aggregati.late_entry_joint_distribution`: la fascia ≥1,0 somma −205,40 $ su 14 ingressi (9 con P&L realizzato, win rate 0,22), contro −10,24 $ su 2 della fascia 0,0–0,5.
- **Costo**: **3,11 $** (congetturale) = −`ingressi[MU].mtm_eod` = −(−3,108). È un mark fill→close su 0,407 azioni, non realizzato.
- **Evidenza contraria**: se il finding fosse falso, un ingresso con quota >1 non sarebbe peggiore degli altri. Oggi MU a −3,11 $ è in linea con DIS a −4,34 $, che ha denominatore degenere. Il campione del giorno (n=2) non distingue niente; resta la serie cumulata.
- **Non-occorrenza**: MU non è un mover (+2,75% < 3%), quindi oggi la tardività non ha bruciato un mover forte. La mediana mobile di `entry_percentile` vale 0,593 (20 giorni) e il valore di oggi, 0,860, sta sopra: tardività presente, costo piccolo.
- **Next evidence**: quello già dichiarato il 09-17. Regressione di `pnl_netto` su `quota_movimento_precedente_al_segnale` limitata agli ingressi su mover ≥3%, con INSUFFICIENT_N dichiarato se n non regge. Sola lettura su trades e s4_intent_events.
- **Alternative scartate**: che il −3,11 $ sia costo di esecuzione. Scartata: il roundtrip stimato su uno slot analogo vale 0,45 $ (`candidati_miss[META].opportunity_v2.costi.total_usd`), un ordine di grandezza sotto il mark negativo.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, dal più alto al più basso)

| # | Simbolo | Return | |
|---:|---|---:|---|
| 1 | META | +6,55% | mover |
| 2 | MRVL | +4,26% | mover |
| 3 | IBM | +3,38% | mover |
| 4 | AMD | +3,04% | mover |
| 5 | MU | +2,75% | |
| 6 | XOM | +2,22% | |
| 7 | WFC | +1,94% | |
| 8 | CVX | +1,91% | |
| 9 | BP | +1,78% | |
| 10 | INTC | +1,69% | |
| 11 | QCOM | +1,33% | |
| 12 | WDC | +1,04% | |
| 13 | NOK | +1,03% | |
| 14 | ARM | +1,03% | |
| 15 | TXN | +1,03% | |
| 16 | ABBV | +0,86% | |
| 17 | XLE | +0,82% | |
| 18 | C | +0,78% | |
| 19 | SOXX | +0,68% | |
| 20 | PBR | +0,48% | |
| 21 | BAC | +0,45% | |
| 22 | JPM | +0,34% | |
| 23 | SHEL | +0,29% | |
| 24 | DELL | +0,26% | |
| 25 | CSCO | +0,24% | |
| 26 | BRK,B | +0,18% | |
| 27 | LLY | +0,03% | |
| 28 | XLK | +0,00% | |
| 29 | PFE | -0,04% | |
| 30 | RIO | -0,09% | |
| 31 | TSLA | -0,10% | |
| 32 | ERIC | -0,10% | |
| 33 | WMT | -0,21% | |
| 34 | TM | -0,25% | |
| 35 | AAPL | -0,28% | |
| 36 | QQQ | -0,29% | |
| 37 | XLV | -0,33% | |
| 38 | V | -0,34% | |
| 39 | SONY | -0,38% | |
| 40 | MS | -0,41% | |
| 41 | UBS | -0,42% | |
| 42 | XLF | -0,42% | |
| 43 | PLTR | -0,45% | |
| 44 | SPY | -0,46% | |
| 45 | MSFT | -0,47% | |
| 46 | ORCL | -0,55% | |
| 47 | PANW | -0,56% | |
| 48 | BIDU | -0,56% | |
| 49 | MA | -0,59% | |
| 50 | MRK | -0,63% | |
| 51 | GS | -0,75% | |
| 52 | JNJ | -0,76% | |
| 53 | VALE | -0,77% | |
| 54 | TSM | -0,83% | |
| 55 | COST | -0,83% | |
| 56 | AMAT | -0,83% | |
| 57 | DIS | -0,84% | |
| 58 | CAT | -0,84% | |
| 59 | MCD | -0,91% | |
| 60 | NVDA | -0,91% | |
| 61 | ADBE | -0,93% | |
| 62 | NFLX | -0,96% | |
| 63 | DB | -0,97% | |
| 64 | HD | -1,04% | |
| 65 | SAP | -1,11% | |
| 66 | AVGO | -1,13% | |
| 67 | SNOW | -1,20% | |
| 68 | AXP | -1,32% | |
| 69 | NVO | -1,33% | |
| 70 | VZ | -1,33% | |
| 71 | IWM | -1,37% | |
| 72 | ROKU | -1,57% | |
| 73 | HOOD | -1,76% | |
| 74 | T | -1,76% | |
| 75 | AMZN | -1,78% | |
| 76 | INFY | -1,80% | |
| 77 | MMM | -1,86% | |
| 78 | SBUX | -1,93% | |
| 79 | AZN | -1,94% | |
| 80 | UNH | -1,94% | |
| 81 | RDDT | -1,97% | |
| 82 | NKE | -1,97% | |
| 83 | CRM | -1,99% | |
| 84 | ASML | -2,00% | |
| 85 | PG | -2,02% | |
| 86 | BA | -2,05% | |
| 87 | GOOGL | -2,28% | |
| 88 | NOW | -2,31% | |
| 89 | GM | -2,37% | |
| 90 | TMUS | -2,39% | |
| 91 | JD | -2,46% | |
| 92 | GE | -2,83% | |
| 93 | BABA | -2,89% | |
| 94 | SPCX | -3,86% | mover |
| 95 | F | -3,93% | mover |
| 96 | CMCSA | -6,61% | mover |

### (b) Checklist degli altri finding aperti toccati dalla giornata

| Finding | Esito | Dato decisivo |
|---|---|---|
| [F-001] copertura news bassa | supported | 38/96 a zero righe (`watchlist_zero_news`); 11 ticker in `ticker_allerta_zero_articoli` (≥5 sedute) |
| [F-012] righe fan-out | supported | `mapping_rilevanza.TAG_UNCONFIRMED` 115/199 righe (57,8%); `cause_del_giorno.quota_righe_fanout` 0,545; un pezzo su Snap taggato META |
| [F-019] latenza di ingestione | supported | META signal 10049 `published_to_scored` 6.857 s, però per drenaggio della coda (F-069), non per latenza del worker |
| [F-021] finestre beat in UTC fisso | supported | META scorato 13:38, primo ciclo portfolio 14:07 (`guard_decisions` primo `tick_time`) |
| [F-031] P0-05 blocca S4 su titoli S1 | contradicted in parte | 114 `SKIP_PYRAMIDING` tradabili: 74 su posizioni S4 (NVO 24, AZN 24, XLE 23, SPCX 3), cioè il guard che funziona come progettato, e 40 su titoli S1 (CVX 19, MRK 12, MRVL 4, DELL 3, XOM 1, AMD 1). Tracciabilità: 13 righe in `execution_decisions` su 114 (11,4%) |
| [F-011] signal_id NULL in execution_decisions | contradicted | `decision_signal_id_coverage.totals_fill_rate` 735/736; unica regressione `SKIP_PYRAMIDING` 12/13 |
| [F-040] segnali ribassisti sopra gate senza ordine | supported | CMCSA −0,386 ISSUER_SPECIFIC, segno corretto su −6,61%, nessun ordine (long-only) |
| [F-008] articolo macro forza l'uscita | not_exposed | l'unica uscita (SPCX) nasce da un articolo ISSUER_SPECIFIC sul lockup, non da un fan-out |
| [F-076] entità HTML non decodificate | supported | titoli scorati con `&#39;` (META "What&#39;s Going On With Snap…", "&#39;Meta acquires Swedish AI startup…") |

### (c) Casi di successo

Nessun mover catturato con P&L positivo da un'azione del giorno. Le sole marcature positive sui mover sono passive, su posizioni S1 già a libro: AMD +11,06 $, MRVL +6,18 $.
