# Alpha Miss Report — 2026-09-14

Contratto: `alpha_miss_prompt_v2`, dossier `schema_version` 3.1. Fonte numerica unica: `docs/evidence/dossier/2026-09-14.json` (generato 2026-09-15T08:00:29Z, `fonte_prezzi`: Alpaca SIP adjustment=all). Sessione di **recupero** (report scritto il 2026-09-24): il testo degli articoli (`news_log`) e i log persistenti `logs/containers/*-2026-09-14.log` sono le sole letture qualitative aggiunte.

## 1. Decision card

1. **Rotazione dall'hardware AI al software nella stessa seduta: 29 mover ≥3% (9 su, 20 giù), dispersione σ 3,61%**. SOXX −5,63% contro PANW +13,09%, NOW +7,41%, SAP +5,78%; SPY −0,45%, QQQ −0,80%. 17 mover su 29 erano già a libro all'apertura (`held_at_open_rate`=0,586), 15 dei quali dal lato sbagliato (EXIT_RISK).
2. **I 7 mover d'ingresso non hanno prodotto nemmeno un P&L positivo**: `profitable_capture_rate`=0/7. PANW e NFLX sono stati comprati a `entry_percentile` 0,890 e 0,814 (`BAD_FILL`, `eod_net_pnl` −2,58 $ e −4,93 $); ADBE (+0,236) e PLTR (+0,174) avevano il segno giusto ma sono rimasti sotto il gate 0,30; SAP e INFY avevano zero righe news. `avoidable_miss_count`=5.
3. **Realizzato del giorno −113,79 $** (S4 −82,64 $, S1 −31,15 $) su 9 chiusure: la peggiore è ORCL S4 −88,68 $ (`portfolio_sell`). Equity Alpaca a fine seduta 109.245,16 $.

## 2. Stato carta

Da `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18). Il file è *posteriore* alla seduta del 14 e **non la contiene**: `scoreboard.giorno.osservati` salta da 2026-09-11 a 2026-09-15 (09-14 non ancora materializzata: questa è la sessione di recupero). I cumulati qui sotto sono quindi letti al giorno osservato precedente, **2026-09-11**, dalla serie `pnl_economico.cumulato`.

- Giorno **28/40** della finestra di osservazione in ordine cronologico (27 giorni osservati fino al 09-11; lo scoreboard all'as_of 09-17 dichiara 30/40 *senza* il 14, e con il 14 materializzato diventerebbe 31/40).
- Quota NO_NEWS dominante: **13/27 = 48,1%** al 09-11 (tutti i 13 giorni elencati in `no_news_dominant.giorni` sono ≤ 09-11), sotto la soglia carta 0,60. Oggi la causa dominante del dossier **non** è NO_NEWS (`aggregati.cause_del_giorno.dominante`="BELOW_GATE", 4/10): la quota scenderebbe a 13/28 = 46,4%.
- S4 economico cumulato al 09-11: **−647,26 $** vs banda ±200 $ — fuori banda (all'as_of 09-17 è −696,33 $, `s4_vs_200.within`=false).
- Book cumulato al 09-11: +267,94 $; S1 cumulato +950,04 $.

## 3. Miss del giorno

10 candidati in `candidati_miss`. Nessuno ha uno stadio `funnel_v2.pipeline` oltre il gate né una guardia che lo abbia bloccato: **nessun FILTERED oggi**. Come nelle sedute precedenti della serie, quando l'asse `actionability` (#509) e il campo grezzo `causa` divergono prevale il primo; la nota riporta comunque il valore legacy, che `aggregati.cause_del_giorno` continua a contare invariato ({"NO_NEWS":2,"BELOW_GATE":4,"OFF_TOPIC":1,"OFF_TOPIC_NON_DECIDIBILE":1,"NON_CLASSIFICATO":2}).

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| SAP | +5,78% | **NO_NEWS** | `news_count`=0, `segnali`=[]; `funnel_v2.righe[SAP].pipeline`="NO_RELEVANT_NEWS" (tutte le classi di `rilevanza` a 0). SAP è in `blind_set.ticker_allerta_zero_articoli`: **10 sedute consecutive** a zero articoli (tutta la finestra). `net_opportunity_usd` 51,41 $. |
| ADBE | +5,30% | **THIN_NEUTRAL** | `funnel_v2.righe[ADBE].pipeline`="BELOW_GATE", `score_firmato` **+0,236** < `soglia_gate` 0,30, segno corretto. Unico articolo: "DA Davidson Maintains Buy on Adobe, Raises Price Target to $290" (18:18Z), scorato in 1,3 minuti — ma a quel punto `gap_return` +3,68% era già fatto. `net_opportunity_usd` 20,61 $. |
| INFY | +4,79% | **NO_NEWS** | `news_count`=0; `pipeline`="NO_RELEVANT_NEWS". 2 sedute consecutive a zero articoli. `net_opportunity_usd` 40,69 $. |
| CRM | +4,73% | **THIN_NEUTRAL** | `pipeline`="BELOW_GATE", `score_firmato` +0,011, `fallback`=true; `causa` legacy "OFF_TOPIC_NON_DECIDIBILE". L'articolo ("Salesforce's AI Business Is Booming, Why Isn't CRM Stock?", 14:05Z, arrivato al modello con `&#39;`) è un pezzo di scenario pre-Dreamforce, non la notizia del movimento; scorato 45 minuti dopo la pubblicazione. `net_opportunity_usd` 37,83 $. |
| PLTR | +3,64% | **THIN_NEUTRAL** | `pipeline`="BELOW_GATE", `score_firmato` **+0,174** (19:20Z, "Palantir Stock Rises as AI Leaders Hint at Growth Slowdown"). Flusso a segno misto: −0,12 (fallback, 13:51Z) e −0,147 (16:48Z, "Nvidia, Palantir Pull Back From Anthropic Models…") prima del +0,174; `quota_righe_fanout`=0,75. `net_opportunity_usd` 47,96 $. |
| ARM | −9,74% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[ARM].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only"; legacy `causa`="BELOW_GATE" (−0,248, ISSUER_SPECIFIC, "Why Is Arm Holdings Stock Falling Monday?" — resoconto del calo). |
| INTC | −5,59% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; `causa_legacy`="NON_CLASSIFICATO". `max_score_own` **−0,396**: segno corretto e sopra il gate in magnitudine, non azionabile su libro long-only (cfr. F-040). |
| AVGO | −4,77% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; `causa_legacy`="NON_CLASSIFICATO"; `max_score_fanout` −0,301, `quota_righe_fanout`=1,0. |
| GS | −3,96% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="OFF_TOPIC": le 3 righe GDELT (`org_lookup`) parlano di un ETF Goldman, di robot umanoidi e dell'oro — nessuna del titolo GS (cfr. F-020). |
| NVDA | −3,36% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="BELOW_GATE" (`max_score_own` −0,276, 23 righe, `quota_righe_fanout`=0,78). |

Conteggio della tabella: NO_NEWS 2, THIN_NEUTRAL 3, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 5.

**Titoli catturati** (mover detenuti all'apertura o tradati, 19 su 29):

| Simbolo | Return% | Come | Esito |
|---|---:|---|---|
| PANW | +13,09% | ingresso S4 16:37Z a 374,40 $ | `pipeline`="BAD_FILL". `entry_percentile` **0,890**, `quota_movimento_precedente_al_segnale` 1,017: al segnale il titolo aveva già fatto tutto il movimento della giornata. Il segnale che passa il gate (+0,405) viene da "Microsoft's New AI Safety Rules Trigger Surge in 3 Cybersecurity Stocks", che scrive "PANW was up more than 12.7%" alle 11:30 ET. Aperto a fine seduta, `mtm_eod` −1,78 $ (`eod_net_pnl` −2,58 $). |
| NFLX | +3,77% | ingresso S4 19:07Z a 80,55 $ | `pipeline`="BAD_FILL". `entry_percentile` 0,814, `quota_movimento_precedente_al_segnale` 1,170. Segnale +0,322 da "Netflix Stock is Trending Higher: What's Going On?" (19:02Z), segnale→fill 0,9 minuti. `mtm_eod` −4,13 $ (`eod_net_pnl` −4,93 $). |
| MRVL / MU / BAC | −7,32% / −5,25% / −5,14% | detenuti, usciti in giornata per `sentiment_reversal` | EXIT_RISK. Realizzato MRVL (S1) −27,11 $, MU (S4) −49,53 $, BAC (S1) −4,03 $. Due uscite S1 chiuse da un segnale di sentiment (cfr. F-033). |
| ORCL | −3,65% | detenuto S4, uscito per `portfolio_sell` | EXIT_RISK. Realizzato **−88,68 $** dopo 68,3h di tenuta. |
| NOW | +7,41% | detenuto S4, uscito per `portfolio_sell` | PASSIVE_EXPOSURE. Realizzato **+51,06 $** — l'unico mover detenuto chiuso in utile. |
| GOOGL | +3,22% | detenuto S1 | PASSIVE_EXPOSURE, nessuna decisione della giornata. |
| NOK, ASML, AMAT, DELL, SOXX, WDC, AMD, CAT, VALE, MS, TSM | da −13,30% a −3,52% | detenuti, nessuna uscita | EXIT_RISK senza uscita. NOK (−13,30%) pesa solo **5,4 $** di nozionale (cfr. F-075). DELL e VALE hanno avuto **zero righe `news_log`** in giornata: vedi §5 e §8. |

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["AZN","HOOD","PANW","NFLX"],"chiusure":["MU","MRVL","SPCX","ORCL","NOW","TSLA","AZN","HOOD","BAC"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | AZN | S4 | 14:07 | $162.6732 | 8.8657 | — | percentile 22.13%; denominatore intraday degenere: quota non interpretabile |
| IN | HOOD | S4 | 15:07 | $114.2501 | 12.5771 | — | percentile 52.23%; denominatore intraday valido |
| IN | PANW | S4 | 16:37 | $374.4000 | 3.8762 | — | percentile 89.05%; denominatore intraday valido |
| IN | NFLX | S4 | 19:07 | $80.5500 | 17.9503 | — | percentile 81.42%; denominatore intraday valido |
| OUT | MU | S4 | — | $915.6260 | 0.4070 | −$49.53 | sentiment_reversal |
| OUT | MRVL | S1 | — | $204.5569 | 1.5515 | −$27.11 | sentiment_reversal |
| OUT | SPCX | S4 | — | $149.0000 | 9.7251 | +$7.88 | portfolio_sell |
| OUT | ORCL | S4 | — | $143.1096 | 9.3725 | −$88.68 | portfolio_sell |
| OUT | NOW | S4 | — | $138.5800 | 10.7571 | +$51.06 | portfolio_sell |
| OUT | TSLA | S4 | — | $362.1600 | 3.9400 | −$10.45 | portfolio_sell |
| OUT | AZN | S4 | — | $164.0900 | 8.8657 | +$11.77 | hold_minimum_expiry |
| OUT | HOOD | S4 | — | $113.9400 | 12.5771 | −$4.69 | portfolio_sell |
| OUT | BAC | S1 | — | $59.2100 | 11.4411 | −$4.03 | sentiment_reversal |
<!-- alpha-miss-book:end -->

4 ingressi S4 (AZN, HOOD, PANW, NFLX) e 9 chiusure (7 S4, 2 S1): realizzato **−113,79 $** (S4 −82,64 $, S1 −31,15 $). Gli ingressi del mattino sono entrati bassi (AZN 0,221, HOOD 0,522) e sono stati chiusi in giornata (AZN +11,77 $ per `hold_minimum_expiry`, HOOD −4,69 $ per `portfolio_sell`). Quelli del pomeriggio sui due mover sono entrati in punta (PANW 0,890, NFLX 0,814), contro una `mediana_mobile_20g` di `entry_percentile` di 0,616. Le quattro `portfolio_sell` su posizioni S4 di tre giorni (ORCL, NOW, TSLA, SPCX) pesano +7,88 − 88,68 + 51,06 − 10,45 = −40,19 $. `decision_signal_id_coverage` segnala regressioni su SELL (3/9 righe con `signal_id`) e SKIP_PYRAMIDING (2/6).

## 5. Cecità lato uscita

Da `copertura_uscita`: 45 posizioni, **2 cieche lato uscita**, `n_indeterminati`=0 — **nessuna riga con `cieco_lato_uscita: null`**. Nozionale cieco **1.456,30 $**, entrambe ancora aperte.

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| PFE | S1 | **−3,38%** | 0,00% | 2 | `alpaca_benzinga` | 804,25 $ |
| SBUX | S1 | **−6,00%** | +0,33% | 3 | `alpaca_benzinga` | 652,05 $ |

Nessuna delle due è uscita in giornata, quindi `ritorno_da_ingresso` termina al close; `ritorno_seduta` è piatto o positivo — la cecità di oggi non è costata denaro oggi. Il caso rilevante della giornata **non** rientra nella definizione: DELL (S1, −5,82% di seduta) e VALE (S1, −4,07%) erano detenute e a zero righe `news_log`, ma non sono "cieche" perché `ritorno_da_ingresso` è +24,92% e −0,20% (sopra la soglia −3%). Idem UNH (−10,31% dall'ingresso, zero righe) che ha solo 1 seduta consecutiva senza righe contro `sedute_minime`=2.

## 6. Backstop NO_NEWS

`no_news_backstop.population`: **38** simboli a zero righe `news_log`, di cui **4 mover** (SAP, INFY, DELL, VALE) e 34 non-mover, `return_missing`=0.

**Marker calendario**: `calendar_observation.mover_observed`=**0/4** e `non_mover_observed`=0/34. Le fonti hanno risposto (FMP earnings-calendar + Alpaca Corporate Actions API su tutte le righe; `calendario_earnings.status`="OBSERVED"): lo zero è un'osservazione, non un'indisponibilità.

| Simbolo | Settore | Return | `observed_catalysts` | `calendar.status` | `adv_ratio` (POST_HOC_EOD) |
|---|---|---:|---|---|---:|
| SAP | tech | +5,78% | *(vuoto)* | NOT_OBSERVED | 0,863 |
| INFY | tech | +4,79% | *(vuoto)* | NOT_OBSERVED | 1,650 |
| DELL | semis | −5,82% | *(vuoto)* | NOT_OBSERVED | 1,039 |
| VALE | materials | −4,07% | *(vuoto)* | NOT_OBSERVED | 0,748 |

**Volume**: mediana del blocco per i mover **−0,0490** contro **−0,0587** dei non-mover (`mover_observations`=4, `non_mover_observations`=34). Blocco `temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false: il volume di seduta è noto solo al close, **non era disponibile prima del movimento**; nessuna soglia scelta, nessun tasso di falsi positivi stimato (valutazione ex-ante in #451).

**Copertura raw di `news_log` per settore** (distinta dalla copertura effective-timely di `copertura_articoli.per_settore`, che oggi vale 46/96 = 47,9%):

| Settore | `ticker_with_news`/`ticker_universe` | `raw_news_coverage_rate` | mover a zero news | `calendar_observed_zero_news` |
|---|:-:|---:|:-:|:-:|
| consumer | 4/11 | 36,4% | 0 | 0 |
| energy | 2/6 | 33,3% | 0 | 0 |
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| financials | 9/14 | 64,3% | 0 | 0 |
| healthcare | 6/9 | 66,7% | 0 | 0 |
| industrials | 2/4 | 50,0% | 0 | 0 |
| materials | 0/2 | 0,0% | 1 | 0 |
| media | 3/5 | 60,0% | 0 | 0 |
| semis | 14/15 | 93,3% | 1 | 0 |
| tech | 12/21 | 57,1% | 2 | 0 |
| telecom | 2/5 | 40,0% | 0 | 0 |

Unico settore a 0 su N: **materials, 0/2** (RIO, VALE), e porta un mover zero-news (VALE, detenuto). Tech 12/21 porta i due mover d'ingresso zero-news (SAP, INFY), entrambi al rialzo nel tema del giorno.

**Attribuzione fonti per ticker** (#511 passo 2). I 38 ticker con `copertura_articoli.per_ticker.articoli_unici`=0 hanno tutti `fonti_osservate`={} e, da `blind_set.per_ticker`, `articoli_unici_giorno`=0 ed `effective_timely_articles_giorno`=0: ABBV, AXP, BABA, BIDU, BP, BRK.B, COST, CSCO, CVX, DB, DELL, ERIC, F, GE, HD, IBM, INFY, JD, MMM, PBR, PFE, PG, RDDT, RIO, ROKU, SAP, SBUX, SHEL, SNOW, SONY, T, TM, TMUS, UBS, UNH, VALE, WMT, XLF — **nessuna fonte ha reso righe**. Streak di `sedute_consecutive_zero_articoli` ≥5 (`ticker_allerta_zero_articoli`): BP 10, ERIC 10, JD 10, PBR 10, SAP 10, SONY 10, UBS 8, BRK.B 7, COST 5, MMM 5.

Ticker con fonte presente ma **zero effective-timely** (12):

| Ticker | `articoli_unici_giorno` | `effective_timely_articles_giorno` | `fonti_osservate` |
|---|---:|---:|---|
| AMZN | 6 | 0 | la fonte alpaca_benzinga ha reso 5 righe e gdelt_gkg 1, ma nessuna effective-timely |
| GOOGL | 7 | 0 | la fonte alpaca_benzinga ha reso 7 righe, ma nessuna effective-timely |
| XLK | 3 | 0 | la fonte alpaca_benzinga ha reso 3 righe, ma nessuna effective-timely |
| CMCSA | 2 | 0 | la fonte alpaca_benzinga ha reso 2 righe, ma nessuna effective-timely |
| IWM | 2 | 0 | la fonte alpaca_benzinga ha reso 2 righe, ma nessuna effective-timely |
| MRK | 2 | 0 | la fonte alpaca_benzinga ha reso 2 righe, ma nessuna effective-timely |
| QQQ | 2 | 0 | la fonte alpaca_benzinga ha reso 2 righe, ma nessuna effective-timely |
| V | 2 | 0 | la fonte alpaca_benzinga ha reso 2 righe, ma nessuna effective-timely |
| MA | 1 | 0 | la fonte alpaca_benzinga ha reso 1 riga, ma nessuna effective-timely |
| QCOM | 1 | 0 | la fonte alpaca_benzinga ha reso 1 riga, ma nessuna effective-timely |
| SOXX | 1 | 0 | la fonte alpaca_benzinga ha reso 1 riga, ma nessuna effective-timely |
| VZ | 1 | 0 | la fonte alpaca_benzinga ha reso 1 riga, ma nessuna effective-timely |

La decisione su quali connettori accendere resta dell'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Rotazione dall'hardware AI verso software e cybersecurity**, dichiarata dagli articoli stessi della giornata: "Wall Street split in two on Monday, with money pouring out of the AI hardware complex and straight into security software after frontier-lab chief executives spent the weekend arguing that model development is moving too fast" (Benzinga, 18:06Z), con il decennale al 5%. Nei numeri del dossier:

- **Al rialzo (9)**: PANW +13,09%, NOW +7,41%, SAP +5,78%, ADBE +5,30%, INFY +4,79%, CRM +4,73%, NFLX +3,77%, PLTR +3,64%, GOOGL +3,22% — 7 su 9 software/servizi IT. `event_market_context` dà residui vs XLK da +5,44% (PLTR) a +7,58% (SAP).
- **Al ribasso (20)**: 13 semis/hardware (ARM −9,74%, MRVL, ASML, AMAT, DELL, SOXX, INTC, MU, AVGO, WDC, AMD, TSM, NVDA), NOK −13,30%, 3 banche d'investimento/grandi banche (BAC −5,14%, GS −3,96%, MS −3,64%), più CAT, VALE, ORCL.
- ETF: SOXX −5,63%, XLK −1,81%, XLV +1,45%, XLF −0,38%.

Il libro era **dalla parte sbagliata della rotazione**: 15 dei 17 mover detenuti erano EXIT_RISK, quasi tutti semis/hardware (S1), e i due soli ingressi sui mover al rialzo (PANW, NFLX) sono arrivati a movimento fatto. Rispetto alle sedute precedenti della serie (09-16: "catture a perdere" su semis al rialzo, 3/3 BAD_FILL) si ripete lo stesso modo di perdere sul lato ingresso — segnale che passa il gate solo quando l'articolo *racconta* il movimento — mentre cambia il settore, oggi dal lato opposto.

## 8. Segnalazioni

Denominatori: `docs/evidence/longitudinal_panels.json` **non esiste** in questo repo; `giorni_distinti` e `distanza_soglia` non sono disponibili nella forma prevista. I denominatori qui sotto sono **contati sulle occorrenze di `findings.json`** e dichiarati come tali.

---

### [F-009] Il gate 0,30 scarta segnali col segno giusto sui mover forti — oggi 2 dei 5 mover d'ingresso con notizia tempestiva, tutti nel tema del giorno

Sul lato ingresso la giornata ha avuto 5 mover ENTRY_OPPORTUNITY con notizia tempestiva (`active_signal_recall` denominatore 5): PANW e NFLX hanno prodotto un punteggio qualificante, ADBE (+0,236) e PLTR (+0,174) avevano il segno corretto ma sono rimasti sotto il gate, CRM (+0,011, fallback) era piatto. Anche PANW ha attraversato la stessa zona: i primi due punteggi (13:23Z "Cybersecurity Stocks Rally as AI Safety Debate Heats Up" +0,130; 13:50Z "OpenAI, Anthropic Call for AI Slowdown: Chips Sink, Cybersecurity Stocks Jump" +0,184) avevano segno e tema giusti e non passavano il gate. Il +0,405 che è passato è arrivato alle 16:32Z, a 12,7% di movimento già fatto.

* **Esposizione oggi**: 5 mover ENTRY_OPPORTUNITY con notizia tempestiva su 29 mover; il fenomeno si è visto su 2 (ADBE, PLTR) più PANW in fase iniziale. Denominatore storico (occorrenze in `findings.json`): 22 occorrenze su 21 giorni distinti, prima 2026-08-03, ultima 2026-09-11; `costo_cumulato_usd` 2.464,50 $.
* **Evidenza contraria**: se il collo di bottiglia non fosse la magnitudine, i mover al rialzo non catturati avrebbero score col segno sbagliato o nessuno score. Invece ADBE e PLTR hanno `score_firmato` positivo e ISSUER_SPECIFIC (ADBE) o misto (PLTR), sotto 0,30.
* **Non-occorrenza**: NFLX è passato (+0,322) e PANW è passato al terzo articolo, quindi il gate non è impermeabile ai temi del giorno. Su ADBE la magnitudine non spiega tutto: l'unico articolo è un rialzo di target price (18:18Z) arrivato con `gap_return` +3,68% già fatto — anche sopra il gate sarebbe stato un ingresso tardivo (`net_opportunity_usd` 20,61 $ contro 116,6 $ lordi).
* **Next evidence** (read-only): sulle sedute della finestra, per i mover ENTRY_OPPORTUNITY in `pipeline`="BELOW_GATE", confrontare `net_opportunity_usd` (ingresso al ciclo eleggibile) con `gross_opportunity_usd`: se il rapporto mediano resta sotto 0,5 come oggi (68,57/196,6), il costo del gate è per lo più già assorbito dal ritardo della notizia (F-030) e la magnitudine non è il vincolo decisivo.
* **Meccanismo e fonte**: §3 di questo report; `funnel_v2.righe[ADBE|PLTR].pipeline`="BELOW_GATE" con `evidence.score_firmato`; `funnel_v2.kpi.active_signal_recall` 2/5; `timeline` segnali PANW 10685/10716/10802.
* **Costo**: **68,57 $** = `net_opportunity_usd` ADBE 20,61 + PLTR 47,96 (ingresso all'open della prima barra eleggibile dopo lo score, uscita al close, al netto del roundtrip del TradeCostCalculator, slot S4 2.200 $). Confidenza *congetturale*, come il record.

---

### [F-030] La notizia che passa il gate è il racconto del movimento: PANW e NFLX comprati al 89° e 81° percentile

Entrambi gli ingressi sui mover sono `BAD_FILL`. PANW: `quota_movimento_precedente_al_segnale` **1,017**, `entry_percentile` **0,890**, segnale da un articolo che riporta "PANW was up more than 12.7%". NFLX: 1,170 e 0,814, segnale da "Netflix Stock is Trending Higher: What's Going On?". Latenza nostra trascurabile su entrambi (published→scored 2,3 e 4,2 minuti, scored→filled 2,1 e 0,9 minuti).

* **Esposizione oggi**: 7 mover ENTRY_OPPORTUNITY, 2 arrivati all'ordine (`execution_conversion_rate` 2/2), 0 profittevoli (`profitable_capture_rate` 0/7). Denominatore storico: 20 occorrenze su 19 giorni distinti in `findings.json`, prima 2026-08-07; `costo_cumulato_usd` 369,00 $.
* **Evidenza contraria**: se il finding fosse falso, con latenza nostra sotto i 5 minuti almeno uno dei due fill sarebbe caduto sotto la mediana mobile di `entry_percentile` (0,616). Invece 0,890 e 0,814, e quota di movimento pre-segnale >1 su entrambi.
* **Non-occorrenza**: gli ingressi del mattino su non-mover — AZN (`entry_percentile` 0,221) e HOOD (0,522) — non hanno inseguito una punta; AZN ha chiuso +11,77 $. Il fenomeno si concentra sui mover, dove l'articolo nasce *dal* movimento.
* **Next evidence** (read-only): sulla finestra, per gli ingressi su mover, confrontare l'`entry_percentile` degli ingressi il cui articolo ha un titolo del tipo "Why Is X Stock…/What's Going On/Trending Higher/Surges" con quello degli altri. Se la differenza di mediana regge su ≥10 ingressi per gruppo, il fenomeno è identificabile dal testo prima dell'ordine.
* **Meccanismo e fonte**: §3 e §4; `funnel_v2.righe[PANW|NFLX].evidence.eod_net_pnl`; `ingressi[*].entry_percentile` e `quota_movimento_precedente_al_segnale`; `timeline[*].latenze_secondi`.
* **Costo**: **7,51 $** = |`eod_net_pnl`| PANW −2,58 + NFLX −4,93: mark fill→close EOD al netto del roundtrip. È P&L marcato, non una stima su size nominale.

---

### [F-001] Copertura news bassa: 38/96 a zero righe, e 2 mover detenuti in perdita senza una riga

`watchlist_zero_news`=**38/96 (39,6%)**, effective-timely 46/96 (47,9%). Sul lato uscita, DELL (−5,82%) e VALE (−4,07%) erano detenute (S1) e hanno avuto zero righe `news_log` in giornata: nessun segnale di uscita o riduzione era possibile. Non rientrano in `cieco_lato_uscita` solo perché il `ritorno_da_ingresso` resta sopra −3% (DELL +24,92%, VALE −0,20%). Sul lato ingresso SAP (+5,78%) è al decimo giorno consecutivo a zero articoli, cioè l'intera finestra del `blind_set`.

* **Esposizione oggi**: 96 ticker di watchlist per la copertura raw; 17 mover detenuti per il lato uscita; 45 posizioni per il controllo di cecità. Denominatore storico: 33 occorrenze su 32 giorni distinti in `findings.json`, prima 2026-07-31; `costo_cumulato_usd` 5.068,10 $.
* **Evidenza contraria**: se la copertura non fosse un vincolo, i mover a zero notizie sarebbero spiegati da un catalizzatore osservato altrove (calendario societario). Invece `calendar_observation.mover_observed`=0/4, con le fonti del calendario che hanno risposto.
* **Non-occorrenza**: 15 dei 17 mover detenuti avevano almeno una riga (es. MRVL 7, MU 7, NOK 7), e su tre di loro (MRVL, MU, BAC) c'è stata un'uscita per `sentiment_reversal`: dove la notizia c'è, il canale di uscita si attiva. Semis 14/15 di copertura raw.
* **Next evidence** (read-only): per DELL, VALE, SAP, INFY contare nelle 10 sedute della finestra le righe `news_log` nei giorni non-mover. Se sono nulle anche nei giorni piatti, è un buco di provider strutturale (input per #454/#455/#458/#459); se compaiono solo nei giorni piatti, è un problema di tempestività.
* **Meccanismo e fonte**: §5 e §6; `mercato.watchlist_zero_news`, `copertura_uscita.posizioni[DELL|VALE].righe_news_log_giorno`=0, `no_news_backstop.per_sector`, `blind_set.ticker_allerta_zero_articoli`.
* **Costo**: **60,42 $** = Σ `notional_usd × ritorno_seduta` sulle posizioni detenute a zero righe `news_log` con ritorno di seduta ≤ −3%: DELL 496,62 × −5,82% = −28,90 + VALE 774,38 × −4,07% = −31,52. Confidenza *congetturale*, come il record: presuppone che una riga avrebbe prodotto un'uscita, e per S1 questo non è stabilito (cfr. F-033).

---

**Alternative scartate** (comuni alle tre):

* *"È beta di mercato"* — scartata: SPY −0,45%, QQQ −0,80%, mentre i mover non catturati hanno residui vs XLK tra +5,44% e +7,58%; il fenomeno è di rotazione, non di direzione di mercato.
* *"È la latenza della nostra ingestione (F-019)"* — scartata per PANW/NFLX/ADBE (published→scored 1,3–4,2 minuti al momento del segnale decisivo). Vale in parte solo per la prima ora: vedi appendice (b), F-019.
* *"Il gate ha bloccato segnali ribassisti buoni"* — irrilevante per costruzione: i ribassisti non detenuti sono OUT_OF_STRATEGY_SCOPE (F-040).

## 9. Appendice

### (a) Rendimenti completi della watchlist

Da `mercato.rendimenti`, 96 simboli, dal più alto al più basso. `soglia_mover`=0,03 (●). `dispersione_sigma`=0,03611. `simboli_senza_dati`: lista vuota.

| # | Simbolo | Return | Mover | Stato |
|---:|---|---:|:-:|---|
| 1 | PANW | +13.09% | ● | ENTRY_OPPORTUNITY / BAD_FILL |
| 2 | NOW | +7.41% | ● | PASSIVE_EXPOSURE |
| 3 | SAP | +5.78% | ● | ENTRY_OPPORTUNITY / NO_RELEVANT_NEWS |
| 4 | ADBE | +5.30% | ● | ENTRY_OPPORTUNITY / BELOW_GATE |
| 5 | INFY | +4.79% | ● | ENTRY_OPPORTUNITY / NO_RELEVANT_NEWS |
| 6 | CRM | +4.73% | ● | ENTRY_OPPORTUNITY / BELOW_GATE |
| 7 | NFLX | +3.77% | ● | ENTRY_OPPORTUNITY / BAD_FILL |
| 8 | PLTR | +3.64% | ● | ENTRY_OPPORTUNITY / BELOW_GATE |
| 9 | GOOGL | +3.22% | ● | PASSIVE_EXPOSURE |
| 10 | RDDT | +2.92% |  | — |
| 11 | META | +2.71% |  | — |
| 12 | SONY | +2.38% |  | — |
| 13 | IBM | +2.38% |  | — |
| 14 | AZN | +2.25% |  | tradato in giornata (non mover) |
| 15 | LLY | +2.02% |  | detenuto (non mover) |
| 16 | MSFT | +1.97% |  | — |
| 17 | MCD | +1.96% |  | — |
| 18 | DIS | +1.91% |  | — |
| 19 | ABBV | +1.81% |  | detenuto (non mover) |
| 20 | WMT | +1.80% |  | — |
| 21 | UNH | +1.80% |  | detenuto (non mover) |
| 22 | GM | +1.80% |  | detenuto (non mover) |
| 23 | T | +1.73% |  | — |
| 24 | ROKU | +1.63% |  | detenuto (non mover) |
| 25 | HOOD | +1.56% |  | tradato in giornata (non mover) |
| 26 | COST | +1.56% |  | — |
| 27 | XLV | +1.45% |  | detenuto (non mover) |
| 28 | VZ | +1.34% |  | — |
| 29 | V | +1.30% |  | — |
| 30 | SNOW | +1.02% |  | detenuto (non mover) |
| 31 | AXP | +0.95% |  | — |
| 32 | MA | +0.92% |  | — |
| 33 | BRK.B | +0.90% |  | — |
| 34 | NVO | +0.88% |  | — |
| 35 | JD | +0.74% |  | — |
| 36 | HD | +0.69% |  | — |
| 37 | NKE | +0.68% |  | — |
| 38 | MRK | +0.64% |  | detenuto (non mover) |
| 39 | PG | +0.59% |  | — |
| 40 | BIDU | +0.55% |  | — |
| 41 | SBUX | +0.33% |  | detenuto (non mover) |
| 42 | TMUS | +0.31% |  | — |
| 43 | JNJ | +0.28% |  | detenuto (non mover) |
| 44 | AAPL | +0.24% |  | detenuto (non mover) |
| 45 | PFE | +0.00% |  | detenuto (non mover) |
| 46 | BABA | -0.06% |  | — |
| 47 | BA | -0.09% |  | — |
| 48 | PBR | -0.24% |  | detenuto (non mover) |
| 49 | TM | -0.32% |  | — |
| 50 | SHEL | -0.33% |  | detenuto (non mover) |
| 51 | IWM | -0.34% |  | — |
| 52 | BP | -0.37% |  | detenuto (non mover) |
| 53 | XLF | -0.38% |  | detenuto (non mover) |
| 54 | SPY | -0.45% |  | detenuto (non mover) |
| 55 | XOM | -0.55% |  | detenuto (non mover) |
| 56 | F | -0.79% |  | — |
| 57 | QQQ | -0.80% |  | — |
| 58 | CVX | -0.88% |  | detenuto (non mover) |
| 59 | XLE | -0.94% |  | detenuto (non mover) |
| 60 | QCOM | -1.00% |  | — |
| 61 | AMZN | -1.26% |  | — |
| 62 | CMCSA | -1.27% |  | — |
| 63 | JPM | -1.71% |  | detenuto (non mover) |
| 64 | WFC | -1.75% |  | — |
| 65 | TSLA | -1.77% |  | detenuto (non mover) |
| 66 | MMM | -1.79% |  | — |
| 67 | XLK | -1.81% |  | detenuto (non mover) |
| 68 | CSCO | -1.85% |  | detenuto (non mover) |
| 69 | GE | -1.88% |  | — |
| 70 | C | -1.90% |  | detenuto (non mover) |
| 71 | TXN | -1.97% |  | — |
| 72 | SPCX | -2.02% |  | detenuto (non mover) |
| 73 | RIO | -2.32% |  | detenuto (non mover) |
| 74 | ERIC | -2.52% |  | — |
| 75 | DB | -2.74% |  | — |
| 76 | UBS | -2.91% |  | detenuto (non mover) |
| 77 | NVDA | -3.36% | ● | NON_ACTIONABLE |
| 78 | TSM | -3.52% | ● | EXIT_RISK |
| 79 | MS | -3.64% | ● | EXIT_RISK |
| 80 | ORCL | -3.65% | ● | EXIT_RISK |
| 81 | GS | -3.96% | ● | NON_ACTIONABLE |
| 82 | VALE | -4.07% | ● | EXIT_RISK |
| 83 | CAT | -4.22% | ● | EXIT_RISK |
| 84 | AMD | -4.40% | ● | EXIT_RISK |
| 85 | WDC | -4.53% | ● | EXIT_RISK |
| 86 | AVGO | -4.77% | ● | NON_ACTIONABLE |
| 87 | BAC | -5.14% | ● | EXIT_RISK |
| 88 | MU | -5.25% | ● | EXIT_RISK |
| 89 | INTC | -5.59% | ● | NON_ACTIONABLE |
| 90 | SOXX | -5.63% | ● | EXIT_RISK |
| 91 | DELL | -5.82% | ● | EXIT_RISK |
| 92 | AMAT | -7.07% | ● | EXIT_RISK |
| 93 | ASML | -7.25% | ● | EXIT_RISK |
| 94 | MRVL | -7.32% | ● | EXIT_RISK |
| 95 | ARM | -9.74% | ● | NON_ACTIONABLE |
| 96 | NOK | -13.30% | ● | EXIT_RISK |

### (b) Altri finding aperti toccati dalla giornata

- [F-019] supported (solo prima ora) — `first_seen_to_ingested` mediano **51,6 min** sui 39 segnali pubblicati prima delle 13:30Z e 41,3 min fra 13:30 e 15:00Z, contro 4,2 min sui 141 successivi; `worker-inference-2026-09-14.log`: cicli sentiment da 1–11 articoli e 2–10 minuti l'uno fino alle ~15:00Z (PANW pubblicato 13:23Z a 347,23 $, scorato 14:06Z a 363,73 $).
- [F-069] supported — primo ciclo sentiment utile alle 13:34Z con `skipped_stale`=305: la cattura pre-market scade senza essere scorata.
- [F-040] supported — INTC `max_score_own` −0,396 (ISSUER_SPECIFIC, segno corretto, sopra gate in magnitudine), nessun ordine possibile su libro long-only.
- [F-020] supported — GS: 3 righe GDELT `org_lookup` su ETF Goldman/robot/oro, `causa`="OFF_TOPIC".
- [F-033] supported — MRVL (S1) e BAC (S1) chiuse per `sentiment_reversal`, P&L −27,11 $ e −4,03 $ attribuito a S1.
- [F-011] supported — `decision_signal_id_coverage.regressions`=["SELL","SKIP_PYRAMIDING"]: SELL 3/9, SKIP_PYRAMIDING 2/6 con `signal_id`.
- [F-012] supported — `cause_del_giorno.quota_righe_fanout`=0,708; `mapping_fanout_extra`=92 su 229 righe.
- [F-075] supported — NOK, il mover più grande del giorno (−13,30%), contato fra i detenuti con 5,4 $ di nozionale.
- [F-076] supported — testo scorato con entità HTML (`Salesforce&#39;s`, `S&amp;P 500`); seduta anteriore al fix del 2026-09-21.
- [F-082] not_exposed — `guardia_contraddizione.giorno`: 5 soppressi su 78 valutabili, 0 eseguiti; nessun ingresso contro-direzione oggi.

### (c) Casi di successo

Nessun mover catturato con P&L positivo sul lato ingresso. L'unica chiusura in utile su un mover è NOW (+7,41%), detenuto S4 dal venerdì e chiuso per `portfolio_sell` a **+51,06 $** — un'esposizione passiva, non una cattura della seduta. Fuori dai mover, AZN (ingresso 14:07Z a `entry_percentile` 0,221, chiuso per `hold_minimum_expiry` a +11,77 $) è l'unico ingresso della giornata chiuso in utile.
