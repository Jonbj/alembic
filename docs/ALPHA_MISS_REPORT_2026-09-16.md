# Alpha Miss Report — 2026-09-16

Contratto: `alpha_miss_prompt_v2`, dossier `schema_version` 3.1. Fonte numerica unica: `docs/evidence/dossier/2026-09-16.json` (generato 2026-09-17T08:00:32Z, `fonte_prezzi`: Alpaca SIP adjustment=all). Ogni numero di mercato di questo report viene da lì; il testo degli articoli è l'unica lettura qualitativa aggiunta.

## 1. Decision card

1. **Tutti e tre i mover catturabili sono stati catturati e tutti e tre hanno perso**: `funnel_v2.kpi.active_signal_recall`=3/3=1,00 e `execution_conversion_rate`=3/3=1,00, ma `profitable_capture_rate`=0/3=0,00 — SPCX, INTC e MRVL finiscono tutti in `pipeline`="BAD_FILL", somma `eod_net_pnl` **−28,84 $**. Nessun miss evitabile oggi (`avoidable_miss_count`=0).
2. **16 mover ≥3%** (`soglia_mover`=0,03; 5 su, 11 giù), di cui **7 già detenuti all'apertura** (`held_at_open_rate`=7/16=43,8%) e **6 ribassisti non detenuti**, non azionabili su un libro long-only. Realizzato del giorno **−45,34 $**, tutto S4.
3. **AXP comprato alle 15:52 a 317,43 $ mentre era già a −2,23% di seduta** (`intenti_ingresso_s4` `signal_score`=+0,607, `ritorno_sessione_al_segnale`=−0,0223): ha chiuso a −3,70% e la posizione ha realizzato **−10,78 $**. La guardia ombra di contraddizione (#335, soglia 0,04) non ha registrato l'evento: `n_soppressi`=0 su 108 intenti valutabili.

## 2. Stato carta

Da `docs/evidence/economic_pnl.json`, **as_of 2026-09-15** (i cumulati arrivano al giorno osservato precedente al 09-16).

- Giorno **28/40** della finestra di osservazione (inizio 2026-08-03, scadenza attesa 2026-09-28).
- Quota NO_NEWS dominante: **13/28 = 46,4%**, sotto la soglia carta 0,60 (`superata_soglia`=false). Oggi la causa dominante del dossier è di nuovo NO_NEWS (`aggregati.cause_del_giorno.dominante`="NO_NEWS", 2/5), quindi la quota salirà a 14/29 = 48,3% al prossimo aggiornamento — ancora sotto soglia.
- S4 economico cumulato: **−855,58 $** vs banda ±200 $ (`s4_vs_200.within`=false — fuori banda, e in peggioramento: era −707,41 $ all'as_of 09-11).
- Book cumulato: **−330,81 $**. S1 cumulato: +559,60 $ (`delta_vs_spy` −78,41 $: S1 è passato sotto il benchmark SPY, era +105,60 $ all'as_of 09-11).

## 3. Miss del giorno

5 candidati in `candidati_miss`, **tutti ribassisti e nessuno detenuto**: su un libro long-only nessuno di essi era azionabile, per costruzione e non per qualità del segnale (`funnel_v2.conteggi_actionability`={"ENTRY_OPPORTUNITY":3,"EXIT_RISK":5,"PASSIVE_EXPOSURE":2,"NON_ACTIONABLE":6}). Nessun candidato ha raggiunto uno stadio `funnel_v2.pipeline` oltre il gate né una guardia che abbia bloccato: **nessun FILTERED è possibile oggi**.

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| HOOD | −5,46% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[HOOD].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only". Il segnale c'era ed era del segno giusto: score −0,325 alle 15:28, ISSUER_SPECIFIC, sopra il gate in magnitudine (`soglia_gate_usata`=0,30) — l'articolo Benzinga "Why Is Robinhood Markets Stock Falling Wednesday?" riporta le accuse penali di insider trading contro due ex ingegneri e la battuta d'arresto del CLARITY Act al Senato. Su libro long-only, un ribasso non detenuto non è catturabile. `causa`="NON_ACTIONABLE", `causa_legacy`="NON_CLASSIFICATO". |
| IBM | −4,38% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[IBM].actionability`="NON_ACTIONABLE". Il valore legacy `causa`/`legacy_causa`="BELOW_GATE" (score −0,12, `fallback`=true, modello singolo `gpt-oss:20b-cloud`) resta la vista #208 pre-#509, che misura score-vs-gate e non l'attuabilità. L'unico articolo ("Why Is IBM Stock Falling Wednesday?", 18:03) è già un resoconto del calo, con `n_ticker_articolo`=2 e `quota_righe_fanout`=1,0. |
| GS | −3,96% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[GS].actionability`="NON_ACTIONABLE"; `causa_legacy`="NON_CLASSIFICATO" promossa. 5 righe news, 4 delle quali dichiarazioni in diretta del CEO Solomon alla Barclays Global Financial Services Conference: il flusso oscilla da +0,291 ("doing better than our target to grow our asset wealth management business") a −0,386 ("non-compensation expenses to run more than $500M higher sequentially") in 18 minuti. `max_score_own`=−0,386, segno corretto e sopra gate in magnitudine, ma non azionabile per direzione. |
| VZ | −3,28% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[VZ].actionability`="NON_ACTIONABLE"; `causa`/`legacy_causa`="NO_NEWS" (`news_count`=0, `segnali`=[]). Buco di copertura reale — ma anche con la notizia il ribasso non detenuto sarebbe rimasto fuori portata. Registrato come NO_NEWS nella serie legacy, OUT_OF_STRATEGY_SCOPE nella categoria operativa. |
| T | −3,22% | **OUT_OF_STRATEGY_SCOPE** | Identico a VZ: `actionability`="NON_ACTIONABLE", `causa`/`legacy_causa`="NO_NEWS", `news_count`=0. `blind_set.per_ticker[T]` segnala 6 sedute consecutive a zero articoli e 10 a zero effective-timely — T è in `ticker_allerta_zero_articoli`. |

**Nota di metodo**: come nelle sedute precedenti della serie, quando l'asse `actionability` (#509) e il campo grezzo `causa` divergono ho preferito il primo, perché il campo grezzo non verifica l'attuabilità; la nota per riga riporta comunque il valore legacy, che `aggregati.cause_del_giorno` continua a contare invariato ({"NO_NEWS":2,"BELOW_GATE":1,"NON_CLASSIFICATO":2}, dominante "NO_NEWS") per il vincolo #288 Opzione 1. Conteggio della tabella: NO_NEWS 0, THIN_NEUTRAL 0, WRONG_SIGN 0, FILTERED 0, OUT_OF_STRATEGY_SCOPE 5.

**Titoli catturati** (mover detenuti o tradati, 11 su 16):

| Simbolo | Return% | Come | Esito |
|---|---:|---|---|
| SPCX | +5,15% | ingresso S4 15:52 a 152,23 $ | `pipeline`="BAD_FILL". `entry_percentile` **0,910** — comprato al 91° percentile del range di giornata. Chiuso in giornata a 151,08 $ per `hold_minimum_expiry`, P&L netto **−12,67 $** (mark fill→close `eod_net_pnl` −14,60 $). Segnale +0,390 alle 15:48 dall'articolo "SpaceX Stock Surges: What's Going On?" — cioè il rialzo stesso come notizia. `scored_to_filled` 224,5 s: latenza nostra ~4 minuti, e tanto è bastato. |
| INTC | +4,03% | ingresso S4 14:52 a 101,357 $ | `pipeline`="BAD_FILL". `entry_percentile` 0,403; `gap_return` +4,35% contro `intraday_return` −0,31%: il movimento era tutto nel gap notturno (SK Hynix/Ohio), la seduta è stata piatta. Posizione ancora aperta, `mtm_eod` −4,46 $ (`eod_net_pnl` −5,27 $). `denominatore_degenere`=true. |
| MRVL | +3,61% | ingresso S4 14:07 a 230,99 $ | `pipeline`="BAD_FILL". `entry_percentile` 0,698; `quota_movimento_precedente_al_segnale` **1,43** — al segnale il titolo aveva già superato il movimento poi chiuso a fine giornata. Posizione ancora aperta, `mtm_eod` −8,16 $ (`eod_net_pnl` −8,97 $). Segnale +0,325 alle 13:45 su "What's Going On With Marvell Technology Stock Wednesday?", pezzo pre-market che descrive il +2% già fatto. |
| AXP | −3,70% | ingresso S4 15:52 a 317,43 $, uscita 18:52 a 315,28 $ | `funnel_v2` lo classifica "NON_ACTIONABLE" perché all'apertura non era detenuto — ma è stato comprato in giornata. Segnale +0,607 (confidenza 0,825) da GDELT "American Express Sees Strong Spending, Raises Revenue Outlook at Conference": titolo rialzista su un titolo già a −2,23% di seduta. P&L realizzato **−10,78 $**; `drift_post_uscita` −13,21 $ (l'uscita ha evitato altre perdite). |
| BA | −3,69% | detenuto, uscita S4 in giornata a 207,72 $ | EXIT_RISK. P&L realizzato **−18,61 $** (`portfolio_sell`, 26,0h di tenuta); `drift_post_uscita` −39,77 $ — la peggiore chiusura del giorno ma l'uscita ha evitato il grosso. |
| PBR / XOM / SHEL / BP | −3,95% / −3,54% / −3,28% / −3,36% | detenuti S1, nessuna uscita | EXIT_RISK. PBR, XOM e SHEL a **zero righe `news_log`** in giornata; solo BP ha un articolo (1, effective-timely). Perdita marked-to-market della seduta sui tre ciechi: **−93,43 $** (nozionale × `ritorno_seduta`). |
| DELL / NOK | +3,64% / +3,05% | detenuti S1 | PASSIVE_EXPOSURE: nessuna decisione della giornata, il rialzo è arrivato su posizioni già a libro. Il nozionale di NOK è **5,72 $** (0,26% di uno slot S4 tipico da 2.200 $): contarlo come "mover detenuto" gonfia `held_at_open_rate` — vedi F-075 in appendice. |

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["MRVL","META","INTC","ORCL","AXP","SPCX","QQQ"],"chiusure":["META","ORCL","SPCX","BA","AXP"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | MRVL | S4 | 14:07 | $230.9900 | 6.3743 | — | percentile 69.75%; denominatore intraday valido |
| IN | META | S4 | 14:37 | $678.8300 | 2.1686 | — | percentile 51.63%; denominatore intraday valido |
| IN | INTC | S4 | 14:52 | $101.3572 | 14.5237 | — | percentile 40.30%; denominatore intraday degenere: quota non interpretabile |
| IN | ORCL | S4 | 15:07 | $143.2900 | 10.2714 | — | percentile 57.05%; denominatore intraday valido |
| IN | AXP | S4 | 15:52 | $317.4300 | 4.6368 | — | percentile 61.59%; denominatore intraday valido |
| IN | SPCX | S4 | 15:52 | $152.2300 | 9.6686 | — | percentile 90.98%; denominatore intraday valido |
| IN | QQQ | S4 | 17:07 | $709.4700 | 2.0745 | — | percentile 79.71%; denominatore intraday degenere: quota non interpretabile |
| OUT | META | S4 | — | $676.1800 | 2.1686 | −$6.04 | hold_minimum_expiry |
| OUT | ORCL | S4 | — | $143.6378 | 10.2714 | +$2.76 | hold_minimum_expiry |
| OUT | SPCX | S4 | — | $151.0800 | 9.6686 | −$12.67 | hold_minimum_expiry |
| OUT | BA | S4 | — | $207.7200 | 6.9038 | −$18.61 | portfolio_sell |
| OUT | AXP | S4 | — | $315.2800 | 4.6368 | −$10.78 | portfolio_sell |
<!-- alpha-miss-book:end -->

7 ingressi S4 e 5 chiusure S4, tutte le chiusure nella stessa strategia: realizzato **−45,34 $** (S4 −45,34 $, S1 0,00 $). Una sola chiusura positiva, ORCL (+2,76 $), che non è un mover. Le tre uscite per `hold_minimum_expiry` hanno tutte drift successivo negativo (mediana dei bucket `ore_tenuta_s4` a 105 minuti: −13,07 $), cioè uscire ha aiutato; le due `portfolio_sell` (BA, AXP) hanno evitato rispettivamente −39,77 $ e −13,21 $ di deriva ulteriore. La `mediana_mobile_20g` di `entry_percentile` è 0,616 e oggi 4 ingressi su 7 le stanno sopra, con SPCX a 0,910. La distribuzione per ora d'ingresso resta la solita: l'ora 14 UTC porta `somma_pnl` −1.600,67 $ su 153 osservazioni (t −4,52, non un test).

## 5. Cecità lato uscita

Da `copertura_uscita`: 40 posizioni, **4 cieche lato uscita**, `n_indeterminati`=0 — **nessuna riga con `cieco_lato_uscita: null`**, quindi nessun dato mancante da dichiarare in questa sezione. Nozionale cieco complessivo **2.181,85 $**, tutte e 4 ancora aperte.

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| ASML | S1 | **-9.41%** | +0.67% | 2 | `alpaca_benzinga` | 604.92 $ |
| PFE | S1 | **-4.29%** | -0.33% | 4 | `alpaca_benzinga` | 796.70 $ |
| SBUX | S1 | **-7.64%** | +0.79% | 5 | `alpaca_benzinga` | 640.67 $ |
| WDC | S4 | **-24.08%** | +1.22% | 2 | `alpaca_benzinga` | 139.56 $ |

Tutte e quattro hanno `fonti_osservate_finestra` = `["alpaca_benzinga"]`: la finestra a 10 sedute ha visto una sola fonte rendere righe su questi nomi, e in giornata zero. **WDC è il caso grave**: −24,08% dall'ingresso, seconda seduta consecutiva senza una riga, ed è una posizione S4 — cioè la sleeve che *dipende* dal sentiment per uscire. Peggioramento rispetto al 09-15 (3 posizioni cieche, 2.033,70 $) e al 09-11 (2 posizioni, 1.291,08 $): terza seduta consecutiva in cui il conteggio sale.

Attenzione a non confondere le due misure: `ritorno_da_ingresso` è la perdita subita mentre la posizione era detenuta (nessuna delle 4 è uscita in giornata, quindi termina al close); `ritorno_seduta` è il movimento del titolo nella sola giornata, e oggi è positivo o quasi piatto su tutte e quattro — la cecità di oggi non è costata denaro oggi.

## 6. Backstop NO_NEWS

`no_news_backstop.population`: 35 simboli a zero righe `news_log`, di cui **5 mover** e 30 non-mover, `return_missing`=0.

**Marker calendario**: `calendar_observation.mover_observed`=**0/5** e `non_mover_observed`=0/30 — nessun mover NO_NEWS aveva un evento societario osservato. Le fonti hanno risposto (`sources_succeeded`: FMP earnings-calendar + Alpaca Corporate Actions API su tutte le righe, `calendario_earnings.status`="OBSERVED", `streak_sedute_consecutive_unknown`=0): questa volta lo zero è un'osservazione, non un'indisponibilità.

| Simbolo | Settore | Return | `observed_catalysts` | `calendar.status` | `adv_ratio` (POST_HOC_EOD) |
|---|---|---:|---|---|---:|
| PBR | energy | -3.95% | *(vuoto)* | NOT_OBSERVED | 1.061 |
| SHEL | energy | -3.28% | *(vuoto)* | NOT_OBSERVED | 0.899 |
| T | telecom | -3.22% | *(vuoto)* | NOT_OBSERVED | 1.150 |
| VZ | telecom | -3.28% | *(vuoto)* | NOT_OBSERVED | 1.376 |
| XOM | energy | -3.54% | *(vuoto)* | NOT_OBSERVED | 0.954 |

**Volume**: mediana `adv_ratio` dei mover **+0,0613** contro **−0,1096** dei non-mover (`mover_observations`=5, `non_mover_observations`=30). Il blocco è marcato `temporal_validity`="POST_HOC_EOD" e `valid_for_signal_evaluation`=false: il volume di seduta e l'etichetta mover sono note solo al close, quindi **questo valore non era disponibile prima del movimento**, non scelgo alcuna soglia e non stimo alcun tasso di falsi positivi operativo. La valutazione ex-ante pre-registrata è separata (#451).

**Copertura raw di `news_log` per settore** (distinta dalla copertura effective-timely di `copertura_articoli.per_settore`, che si legge in §7 e non va mescolata con questa):

| Settore | `ticker_with_news`/`ticker_universe` | `raw_news_coverage_rate` | mover a zero news | `calendar_observed_zero_news` |
|---|:-:|---:|:-:|:-:|
| consumer | 6/11 | 54.5% | 0 | 0 |
| energy | 3/6 | 50.0% | 3 | 0 |
| etf_broad | 4/4 | 100.0% | 0 | 0 |
| financials | 11/14 | 78.6% | 0 | 0 |
| healthcare | 7/9 | 77.8% | 0 | 0 |
| industrials | 3/4 | 75.0% | 0 | 0 |
| materials | 1/2 | 50.0% | 0 | 0 |
| media | 3/5 | 60.0% | 0 | 0 |
| semis | 10/15 | 66.7% | 0 | 0 |
| tech | 12/21 | 57.1% | 0 | 0 |
| telecom | 1/5 | 20.0% | 2 | 0 |

Nessun settore è a 0 su N oggi; il minimo è **telecom, 1/5 = 20,0%**, ed è esattamente il settore che porta 2 dei 5 mover zero-news (T e VZ). Energy è a 3/6 = 50,0% e porta gli altri 3 (PBR, SHEL, XOM). I 5 mover zero-news della giornata stanno tutti in questi due settori.

## 7. Pattern osservato

**Rotazione value→growth in giornata FOMC, con reversal del greggio.** I 5 mover al rialzo sono tutti tech/semis/spazio (SPCX +5,15%, INTC +4,03%, DELL +3,64%, MRVL +3,61%, NOK +3,05%); degli 11 al ribasso, 4 sono energy (PBR, XOM, BP, SHEL), 2 telecom (T, VZ) e 2 financials (GS, AXP). Gli ETF settoriali della watchlist danno lo stesso quadro: XLE −2,88% e XLF −1,62% contro XLK +0,10% e SOXX +0,64%, con SPY −0,44% e QQQ +0,03%. Il contesto lo dichiarano gli articoli stessi della giornata — "A sharp reversal in crude oil handed U.S. equities a reprieve on Wednesday... just hours before the Federal Reserve is expected to raise interest rates for the first time since 2023" — e il pattern è coerente: greggio giù porta giù l'energy, l'attesa di rialzo dei tassi porta giù i bond-proxy telecom, mentre il tema AI/memoria (SK Hynix–Intel in Ohio) tira i semis.

Due sotto-pattern meritano una riga. Primo: **T e VZ si muovono insieme** (−3,22% e −3,28%) con un residuo vs settore di −2,32% e −2,38% (`event_market_context`), cioè un colpo condiviso specifico del comparto, e su entrambi abbiamo **zero righe di notizia** — il settore con la copertura raw peggiore è anche quello dove il movimento congiunto è più evidente. Secondo: **la rotazione non ci ha aiutato comunque**. Eravamo dalla parte giusta (3 ingressi su semis/spazio, tutti mover al rialzo) e abbiamo perso lo stesso, perché il segnale è arrivato a movimento fatto — vedi §8.

Rispetto alle sedute precedenti della serie, la novità non è la rotazione ma l'inversione del modo di perdere: il 09-15 la giornata era fatta di miss (0 catturati su 7 mover), oggi è fatta di catture a perdere (3 su 3 catturati, 0 profittevoli).

## 8. Segnalazioni

Denominatori: `docs/evidence/longitudinal_panels.json` **non esiste** in questo repo, quindi `giorni_distinti` e `distanza_soglia` non sono disponibili nella forma prevista; i denominatori qui sotto sono **contati sulle occorrenze di `findings.json`** e dichiarati come tali.

---

### [F-030] La notizia arriva quando il movimento è già avvenuto — oggi con latenza nostra quasi nulla, e si è perso lo stesso

Tutti e tre i mover ENTRY_OPPORTUNITY sono stati intercettati e tutti e tre hanno chiuso in perdita. Il punto nuovo di oggi è che **non è colpa della nostra latenza**: la mediana `published_to_scored` della giornata è **0,6 minuti** (SPCX 11,8 s, INTC 8,5 s), il valore migliore della serie, e SPCX ha fatto segnale→fill in **224,5 secondi** finendo comunque al **91° percentile** del range di giornata. I titoli degli articoli sono il movimento stesso: "SpaceX Stock Surges: What's Going On?", "Intel Stock Moves Higher: What's Going On Today?", "What's Going On With Marvell Technology Stock Wednesday?".

* **Esposizione oggi**: 3 mover ENTRY_OPPORTUNITY su 16 mover totali — le uniche 3 condizioni in cui il fenomeno poteva manifestarsi. Si è manifestato su 3 su 3. Denominatore storico: 14 occorrenze in `findings.json` (prima 2026-08-07), `costo_cumulato_usd` 253,77 $ con 6 occorrenze non stimate.
* **Evidenza contraria**: se il finding fosse falso, con `published_to_scored` mediano a 0,6 minuti almeno uno dei tre fill sarebbe caduto nella metà bassa del range di giornata e avrebbe chiuso in utile. Invece `profitable_capture_rate`=0/3 e `entry_percentile` 0,910 / 0,698 / 0,403 (mediana mobile 20g 0,616).
* **Non-occorrenza**: INTC è il controesempio parziale — `entry_percentile` 0,403, sotto la mediana mobile, e `gap_return` +4,35% contro `intraday_return` −0,31%: lì il movimento era nel gap notturno, non intraday, e il fill non ha inseguito una punta. Ha perso comunque, ma per −0,31% di seduta piatta, non per essere entrato in alto.
* **Next evidence** (read-only): sulle prossime sedute, correlare `quota_movimento_precedente_al_segnale` con `mtm_eod` per i soli ingressi su mover, separando i giorni con `published_to_scored` mediano sotto 5 minuti da quelli sopra. Se l'`entry_percentile` mediano dei fill su mover resta ≥0,60 anche nei giorni a bassa latenza, la latenza di ingestione (F-019) è definitivamente esclusa come causa e resta solo l'istante in cui la fonte scrive.
* **Meccanismo e fonte**: §3 e §1 di questo report; campi `funnel_v2.righe[*].pipeline`="BAD_FILL" con `evidence.eod_net_pnl`, `ingressi[*].entry_percentile` e `quota_movimento_precedente_al_segnale`, `timeline[*].latenze_secondi.published_to_scored`.
* **Costo**: **28,84 $** = somma di `funnel_v2.righe[*].evidence.eod_net_pnl` per i 3 BAD_FILL (SPCX −14,60 + INTC −5,27 + MRVL −8,97). È il mark fill→close EOD al netto del costo di roundtrip del TradeCostCalculator live, non una stima congetturale su size nominale.

---

### [F-NUOVO] La guardia ombra di contraddizione (#335) non ha mai intercettato un intento eseguito: 9 segnalazioni su 1.247 intenti tradabili in 15 sedute, **0 eseguite**

La guardia ombra esiste per censire il caso "compriamo mentre scende": `snapshot.score > 0` e `ritorno_sessione_al_segnale <= -0,04`. Oggi si è verificato esattamente quel caso su un ordine reale — AXP, `signal_score` +0,607 alle 15:39 con `ritorno_sessione_al_segnale` −0,0223, `final_reason_code`="SUBMITTED", trade 1009, realizzato −10,78 $ — e la guardia **non lo ha registrato**, perché −2,23% non raggiunge la soglia 0,04. L'unico firing della giornata (`guardia_contraddizione_ombra`=true su 4 intenti, tutti dello stesso segnale HOOD +0,141 a −4,92%) era su un intento `is_tradable`=false, scartato dal gate a monte: `n_soppressi`=0 su `n_valutabili`=108. Sulla finestra: `n_soppressi`=9 su `n_intenti_tradabili`=1.247 in 15 sedute, `n_soppressi_eseguiti`=**0**. Lo strumento non ha mai avuto intersezione con un ordine davvero passato.

Va detto esplicitamente: **questo non è un difetto della guardia**, che per design (#335) è read-only e non blocca ordini, ed è sotto congelamento di taratura. È un limite di copertura della *misura*: il fenomeno che deve quantificare non viene quantificato, e per 15 sedute si è letto "0 soppressi" come se volesse dire "non succede", mentre oggi mostra che succede sotto soglia.

* **Esposizione oggi**: 108 intenti `is_tradable`=true valutabili, 7 eseguiti. Di questi, 1 (AXP) era contro-direzione al momento del segnale. La condizione di firing si è presentata 4 volte, tutte su intenti non tradabili.
* **Evidenza contraria**: se il finding fosse falso, o la guardia avrebbe segnalato AXP (soglia raggiunta), oppure `n_soppressi_eseguiti` sarebbe >0 in almeno una delle 15 sedute della finestra. Entrambe smentite: −0,0223 > −0,04, e la serie è 0 su 1.247.
* **Non-occorrenza**: gli altri 6 ingressi della giornata (MRVL, META, INTC, ORCL, SPCX, QQQ) avevano `ritorno_sessione_al_segnale` coerente col segno del punteggio — il fenomeno non è generalizzato agli ingressi, è 1 su 7 oggi. E la guardia *funziona* meccanicamente: su HOOD ha calcolato e messo a true il campo, con `motivo_guardia_contraddizione` popolato. Non è codice morto come lo era prima di #398 (cfr. F-045, ora superato: `n_valutabili`=108, non più 0 per costruzione).
* **Next evidence** (read-only): ricostruire dalla finestra osservata la distribuzione di `ritorno_sessione_al_segnale` per i soli intenti con `final_reason_code`="SUBMITTED" e `signal_score`>0, e contare quanti stanno in (−0,04, 0). Se sono una frazione trascurabile degli eseguiti, la soglia copre il fenomeno e questo finding cade; se sono la maggioranza dei perdenti, la misura è cieca dove conta. Nessuna taratura proposta: la decisione sulla soglia è dell'operatore, e siamo dentro il congelamento.
* **Meccanismo e fonte**: §1 e §3 di questo report; campi `aggregati.guardia_contraddizione.giorno` (`n_valutabili`=108, `n_soppressi`=0, `soglia`=0,04) e `.finestra_osservazione` (`n_soppressi`=9, `n_soppressi_eseguiti`=0, `n_intenti_tradabili`=1.247), `intenti_ingresso_s4` per l'intento AXP `7aaf1d59-e392-5367-ab82-2a63e3aae020`.
* **Costo**: **10,78 $** = P&L realizzato del trade 1009 (AXP), cioè il costo dell'evento che la guardia esiste per censire e che non ha censito. **Non** è denaro che la guardia avrebbe salvato: essendo read-only non avrebbe comunque bloccato l'ordine. Confidenza *attribuita*, non misurata, perché l'attribuzione del P&L al fenomeno "ingresso contro-direzione" è un'inferenza, non una misura diretta.

---

### [F-001] Copertura news bassa — peggiorata su entrambi i lati: 35/96 a zero righe e i due settori scoperti portano tutti e 5 i mover zero-news

`watchlist_zero_news`=**35/96 (36,5%)**, contro 31 (32,3%) il 09-15: +4 simboli. La distribuzione è il punto: telecom 1/5 = 20,0% e energy 3/6 = 50,0% di copertura raw, e da quei due settori arrivano **tutti e 5** i mover a zero notizie (T, VZ, PBR, SHEL, XOM). T e VZ si muovono insieme (−3,22%/−3,28%, residuo vs settore −2,32%/−2,38%) con zero visibilità. Lato uscita, terzo peggioramento consecutivo: 4 posizioni cieche per 2.181,85 $ (era 3/2.033,70 $ il 09-15, 2/1.291,08 $ il 09-11), con WDC a −24,08% dall'ingresso.

* **Esposizione oggi**: 96 ticker di watchlist per la copertura raw; 16 mover per il lato ingresso; 40 posizioni aperte per il controllo di cecità (soglia −3% dall'ingresso, minimo 2 sedute senza righe). Denominatore storico: 31 occorrenze in `findings.json` (prima 2026-08-04), `costo_cumulato_usd` 4.974,67 $.
* **Evidenza contraria**: se il finding fosse falso, i mover si distribuirebbero indifferentemente fra settori coperti e scoperti. Oggi 5 mover su 16 sono a zero righe e **stanno tutti** nei due settori con la copertura raw peggiore — nessuno nei settori coperti (etf_broad 100%, financials 78,6%, healthcare 77,8%).
* **Non-occorrenza**: il fenomeno non tocca il lato ingresso oggi. Tutti e 5 i mover zero-news sono ribassisti e 3 dei 5 sono detenuti: nessuno era un'opportunità d'ingresso mancata, e il dossier lo conferma con `net_opportunity_usd`=0,0 su VZ e T. Inoltre 36 posizioni su 40 **non** sono cieche pur essendone 12 in perdita marcata: la cecità resta concentrata su 4 nomi, non generalizzata.
* **Next evidence** (read-only): per T, VZ, PBR, SHEL, XOM contare nella finestra a 10 sedute quante righe `news_log` sono arrivate nei giorni in cui *non* erano mover. Se la copertura di questi nomi è costantemente nulla anche nei giorni piatti, è un buco di provider strutturale per settore (input per #454/#455/#458/#459); se le righe compaiono nei giorni piatti e spariscono nei giorni di movimento, il problema è di tempestività, non di configurazione.
* **Meccanismo e fonte**: §5, §6 e §7 di questo report; campi `mercato.watchlist_zero_news`, `no_news_backstop.per_sector.raw_news_coverage_rate`, `copertura_uscita.aggregato` (`n_cieche_lato_uscita`=4, `notional_cieco_usd`=2.181,85), `blind_set.ticker_allerta_zero_articoli`.
* **Costo**: **93,43 $** = somma di `notional_usd × ritorno_seduta` sulle tre posizioni detenute a zero righe news che hanno perso oltre il 3% oggi (PBR 828,00 × −3,95%, SHEL 879,84 × −3,28%, XOM 897,98 × −3,54%). È la perdita realmente subita su posizioni per cui nessun segnale di uscita era possibile in mancanza di input. Confidenza *congetturale*, coerente col record: presuppone che una riga di notizia avrebbe prodotto un'uscita, cosa non stabilita — sono posizioni S1, e S1 non ha un'uscita da sentiment propria (può uscire solo via `sentiment_reversal`, cfr. F-033).

---

**Alternative scartate** (comuni alle tre segnalazioni):

* *"La giornata è andata male per beta di mercato, non per difetti"* — scartata: SPY −0,44% e QQQ +0,03%, mentre i tre ingressi su mover al rialzo hanno perso pur essendo su titoli che hanno chiuso a +3,6/+5,2%. Il segno del mercato e il segno del nostro P&L non coincidono.
* *"Il collo di bottiglia è la latenza della nostra ingestione (F-019)"* — scartata: mediana `published_to_scored` 0,6 minuti, SPCX segnale→fill 224,5 s, e il fill è comunque al 91° percentile.
* *"Il gate ha scartato i segnali giusti (F-009)"* — scartata: `active_signal_recall`=3/3, nessun mover al rialzo è stato fermato dal gate oggi.

## 9. Appendice

### (a) Rendimenti completi della watchlist

Da `mercato.rendimenti`, 96 simboli, dal più alto al più basso. `soglia_mover`=0,03 (●). `dispersione_sigma`=0,01905. `simboli_senza_dati`: lista vuota.

| # | Simbolo | Return | Mover | Stato |
|---:|---|---:|:-:|---|
| 1 | SPCX | +5.15% | ● | ENTRY_OPPORTUNITY / BAD_FILL |
| 2 | INTC | +4.03% | ● | ENTRY_OPPORTUNITY / BAD_FILL |
| 3 | DELL | +3.64% | ● | PASSIVE_EXPOSURE |
| 4 | MRVL | +3.61% | ● | ENTRY_OPPORTUNITY / BAD_FILL |
| 5 | NOK | +3.05% | ● | PASSIVE_EXPOSURE |
| 6 | SNOW | +2.49% |  | detenuto (non mover) |
| 7 | ORCL | +2.00% |  | — |
| 8 | GE | +1.91% |  | — |
| 9 | AMD | +1.65% |  | detenuto (non mover) |
| 10 | WDC | +1.22% |  | detenuto (non mover) |
| 11 | TSM | +1.17% |  | detenuto (non mover) |
| 12 | PLTR | +1.03% |  | — |
| 13 | ARM | +0.89% |  | — |
| 14 | NVDA | +0.82% |  | — |
| 15 | SBUX | +0.79% |  | detenuto (non mover) |
| 16 | MRK | +0.78% |  | detenuto (non mover) |
| 17 | ASML | +0.67% |  | detenuto (non mover) |
| 18 | SOXX | +0.64% |  | detenuto (non mover) |
| 19 | AZN | +0.64% |  | — |
| 20 | BRK.B | +0.59% |  | — |
| 21 | DIS | +0.54% |  | — |
| 22 | META | +0.46% |  | — |
| 23 | TSLA | +0.42% |  | — |
| 24 | AAPL | +0.32% |  | detenuto (non mover) |
| 25 | PG | +0.24% |  | — |
| 26 | LLY | +0.15% |  | detenuto (non mover) |
| 27 | PANW | +0.15% |  | detenuto (non mover) |
| 28 | XLK | +0.10% |  | detenuto (non mover) |
| 29 | AVGO | +0.07% |  | — |
| 30 | XLV | +0.07% |  | detenuto (non mover) |
| 31 | JNJ | +0.03% |  | detenuto (non mover) |
| 32 | QQQ | +0.03% |  | — |
| 33 | ERIC | -0.10% |  | — |
| 34 | CAT | -0.10% |  | detenuto (non mover) |
| 35 | MU | -0.11% |  | — |
| 36 | UNH | -0.18% |  | detenuto (non mover) |
| 37 | ABBV | -0.20% |  | detenuto (non mover) |
| 38 | PFE | -0.33% |  | detenuto (non mover) |
| 39 | IWM | -0.43% |  | — |
| 40 | SPY | -0.44% |  | detenuto (non mover) |
| 41 | WMT | -0.55% |  | — |
| 42 | GOOGL | -0.61% |  | detenuto (non mover) |
| 43 | JD | -0.70% |  | — |
| 44 | SONY | -0.79% |  | — |
| 45 | COST | -0.84% |  | — |
| 46 | DB | -0.85% |  | — |
| 47 | ROKU | -0.96% |  | detenuto (non mover) |
| 48 | MA | -0.96% |  | — |
| 49 | HD | -0.99% |  | — |
| 50 | AMZN | -0.99% |  | — |
| 51 | JPM | -1.01% |  | detenuto (non mover) |
| 52 | TXN | -1.05% |  | — |
| 53 | F | -1.11% |  | — |
| 54 | SAP | -1.15% |  | — |
| 55 | NKE | -1.21% |  | — |
| 56 | MMM | -1.23% |  | — |
| 57 | V | -1.25% |  | — |
| 58 | GM | -1.27% |  | detenuto (non mover) |
| 59 | RDDT | -1.27% |  | — |
| 60 | MSFT | -1.37% |  | — |
| 61 | AMAT | -1.37% |  | detenuto (non mover) |
| 62 | NOW | -1.47% |  | — |
| 63 | RIO | -1.51% |  | detenuto (non mover) |
| 64 | QCOM | -1.58% |  | — |
| 65 | XLF | -1.62% |  | detenuto (non mover) |
| 66 | TM | -1.67% |  | — |
| 67 | MCD | -1.67% |  | — |
| 68 | MS | -1.87% |  | detenuto (non mover) |
| 69 | BABA | -1.89% |  | — |
| 70 | NFLX | -1.91% |  | — |
| 71 | NVO | -1.93% |  | — |
| 72 | CRM | -2.00% |  | — |
| 73 | BIDU | -2.04% |  | — |
| 74 | UBS | -2.08% |  | detenuto (non mover) |
| 75 | CSCO | -2.12% |  | detenuto (non mover) |
| 76 | INFY | -2.12% |  | — |
| 77 | TMUS | -2.33% |  | — |
| 78 | VALE | -2.35% |  | detenuto (non mover) |
| 79 | C | -2.36% |  | detenuto (non mover) |
| 80 | BAC | -2.72% |  | — |
| 81 | ADBE | -2.82% |  | — |
| 82 | CMCSA | -2.83% |  | — |
| 83 | CVX | -2.86% |  | detenuto (non mover) |
| 84 | XLE | -2.88% |  | detenuto (non mover) |
| 85 | WFC | -2.98% |  | — |
| 86 | T | -3.22% | ● | NON_ACTIONABLE |
| 87 | SHEL | -3.28% | ● | EXIT_RISK |
| 88 | VZ | -3.28% | ● | NON_ACTIONABLE |
| 89 | BP | -3.36% | ● | EXIT_RISK |
| 90 | XOM | -3.54% | ● | EXIT_RISK |
| 91 | BA | -3.69% | ● | EXIT_RISK |
| 92 | AXP | -3.70% | ● | NON_ACTIONABLE |
| 93 | PBR | -3.95% | ● | EXIT_RISK |
| 94 | GS | -3.96% | ● | NON_ACTIONABLE |
| 95 | IBM | -4.38% | ● | NON_ACTIONABLE |
| 96 | HOOD | -5.46% | ● | NON_ACTIONABLE |

### (b) Checklist degli altri finding aperti toccati dalla giornata

| Finding | Stato oggi | Dato decisivo |
|---|---|---|
| [F-001] Copertura news bassa | **supported** | `watchlist_zero_news`=35/96 (36,5%), peggio di 31 il 09-15; telecom 1/5 raw. Trattato in §8. |
| [F-009] Il gate scarta segnali col segno corretto sui mover forti | **contradicted** | `funnel_v2.kpi.active_signal_recall`=3/3=1,00: nessun mover ENTRY_OPPORTUNITY è stato fermato dal gate. L'unico sotto-gate col segno corretto (IBM −0,12) era comunque non azionabile su libro long-only. |
| [F-012] Metà delle righe scorate viene da articoli fan-out | **supported** | `copertura_articoli.totali`: `mapping_fanout_extra`=92 su 215 righe (42,8%); `mapping_rilevanza` TAG_UNCONFIRMED 132 contro ISSUER_SPECIFIC 82. `aggregati.cause_del_giorno.quota_righe_fanout`=0,222. |
| [F-019] La latenza d'ingestione consuma la finestra di freshness | **contradicted** | Mediana `published_to_scored` **0,6 minuti** su 215 righe (SPCX 11,8 s, INTC 8,5 s). Oggi la latenza nostra non è il vincolo — il che è precisamente ciò che rende F-030 leggibile in isolamento. |
| [F-030] La notizia arriva a movimento avvenuto | **supported** | 3/3 BAD_FILL, `entry_percentile` fino a 0,910. Trattato in §8. |
| [F-031] Il guard anti-pyramiding blocca ingressi senza traccia | **supported** | 90 intenti `SKIP_PYRAMIDING` in `intenti_ingresso_s4` e 11 righe `SKIP_PYRAMIDING` in `guard_decisions` — su AXP il guard ha ripetuto lo skip per 9 cicli consecutivi sullo stesso `signal_id` 11172. |
| [F-043] Tutti i segnali sopra gate in una giornata sono rialzisti | **contradicted** | 10 segnali ≥ +0,30 ma anche **8 segnali ≤ −0,30** oggi (HOOD, IWM, BA, QQQ, SPY ×2, GS, SPCX). La formulazione "tutti rialzisti" non regge su questa seduta; resta vero che solo i rialzisti possono agire su libro long-only. |
| [F-045] La guardia ombra è zero per costruzione (parser `is_tradable`) | **contradicted / superato** | `n_valutabili`=108, `n_intenti_tradabili`=108 (non più 0): il confronto è stato corretto. Lo zero di oggi è un'osservazione, non un artefatto — ed è il motivo per cui il nuovo finding di §8 è distinto da questo. |
| [F-063] Calendario earnings indisponibile, guardia earnings cieca | **contradicted / superato** | `calendario_earnings.status`="OBSERVED", `sources_succeeded`=["FMP earnings-calendar"], `streak_sedute_consecutive_unknown`=0, e `giorno_di_earnings`=False (booleano, non None) su **1.787/1.787** intenti S4. |
| [F-027] I log dei container non sopravvivono al redeploy | **contradicted** | `logs/containers/{worker,worker-inference,api,beat,worker-news-stream}-2026-09-16.log` tutti presenti e leggibili (da 97 KB a 9,2 MB). La seduta analizzata ha i suoi log. |
| [F-075] `held_at_open_rate` conta come catturati mover con nozionale residuo trascurabile | **supported** | NOK entra nei 7 `held_at_open` con nozionale **5,72 $**, cioè lo 0,26% di uno slot S4 tipico (2.200 $). Senza NOK il rate sarebbe 6/16=37,5% invece di 7/16=43,8%. |
| [F-013] Nessuna banda fra gate d'ingresso e uscita | **supported** | AXP comprato alle 15:52 e già nella lista SELL alle 16:07 (log `worker`: "Hold minimum (90 min): skipped 2 SELL order(s) for recently-bought: ['AXP', 'INTC', 'ORCL', 'SPCX']"): 15 minuti fra la decisione di comprare e quella di vendere lo stesso nome, risolti solo dal minimo di tenuta. |
| [F-002] Attribuzione strategia mancante su trade legacy | **not_exposed** | Tutte e 5 le chiusure e tutti e 7 gli ingressi della giornata portano `strategia`="S4"; nessuna riga a strategia nulla fra le operazioni di oggi. (`aggregati.per_ora_ingresso` mostra ancora 252 osservazioni storiche a `stop_strategy`=null, ma non sono di questa seduta.) |
| [F-033] `sentiment_reversal` chiude posizioni di altre sleeve | **not_exposed** | Nessuna chiusura oggi ha `exit_reason`="sentiment_reversal": 3 `hold_minimum_expiry` e 2 `portfolio_sell`. |

### (c) Casi di successo

**Nessun mover catturato con P&L positivo oggi**: `funnel_v2.kpi.profitable_capture_rate`=0/3. L'unica chiusura in utile della giornata è **ORCL** (+2,76 $ netti, ingresso 15:07 a 143,29 $, uscita a 143,638 $ per `hold_minimum_expiry`), che con +2,00% non raggiunge la soglia mover e quindi non conta come cattura. Vale però come contro-esempio utile: `entry_percentile` 0,570, `quota_nel_gap` −0,11 — l'unico ingresso della giornata entrato *non* inseguendo una punta è anche l'unico che ha chiuso in utile.

### (d) Attribuzione fonti per ticker (#511 passo 2)

**35 ticker** con `articoli_unici == 0` **e** `fonti_osservate` vuoto — fonte assente, nessun provider ha reso righe:

| Ticker | Settore | `articoli_unici_giorno` | `effective_timely_articles_giorno` | `fonti_osservate` | sedute consec. 0 articoli | sedute consec. 0 eff.-timely |
|---|---|---:|---:|---|---:|---:|
| ADBE | tech | 0 | 0 | `{}` (vuoto) | 2 | 2 |
| ARM | semis | 0 | 0 | `{}` (vuoto) | 1 | 1 |
| ASML | semis | 0 | 0 | `{}` (vuoto) | 2 | 2 |
| BABA | tech | 0 | 0 | `{}` (vuoto) | 1 | 5 |
| CSCO | tech | 0 | 0 | `{}` (vuoto) | 3 | 4 |
| ERIC | telecom | 0 | 0 | `{}` (vuoto) | 10 | 10 |
| F | consumer | 0 | 0 | `{}` (vuoto) | 1 | 4 |
| HD | consumer | 0 | 0 | `{}` (vuoto) | 3 | 5 |
| INFY | tech | 0 | 0 | `{}` (vuoto) | 4 | 4 |
| JD | tech | 0 | 0 | `{}` (vuoto) | 10 | 10 |
| JNJ | healthcare | 0 | 0 | `{}` (vuoto) | 1 | 1 |
| MA | financials | 0 | 0 | `{}` (vuoto) | 2 | 6 |
| MMM | industrials | 0 | 0 | `{}` (vuoto) | 1 | 10 |
| NKE | consumer | 0 | 0 | `{}` (vuoto) | 1 | 1 |
| NOW | tech | 0 | 0 | `{}` (vuoto) | 1 | 2 |
| PBR | energy | 0 | 0 | `{}` (vuoto) | 1 | 1 |
| PFE | healthcare | 0 | 0 | `{}` (vuoto) | 4 | 4 |
| PG | consumer | 0 | 0 | `{}` (vuoto) | 3 | 3 |
| QCOM | semis | 0 | 0 | `{}` (vuoto) | 1 | 4 |
| RDDT | media | 0 | 0 | `{}` (vuoto) | 3 | 3 |
| RIO | materials | 0 | 0 | `{}` (vuoto) | 3 | 3 |
| ROKU | media | 0 | 0 | `{}` (vuoto) | 5 | 5 |
| SAP | tech | 0 | 0 | `{}` (vuoto) | 1 | 10 |
| SBUX | consumer | 0 | 0 | `{}` (vuoto) | 5 | 10 |
| SHEL | energy | 0 | 0 | `{}` (vuoto) | 1 | 1 |
| SNOW | tech | 0 | 0 | `{}` (vuoto) | 3 | 3 |
| SONY | tech | 0 | 0 | `{}` (vuoto) | 10 | 10 |
| T | telecom | 0 | 0 | `{}` (vuoto) | 6 | 10 |
| TMUS | telecom | 0 | 0 | `{}` (vuoto) | 3 | 3 |
| TXN | semis | 0 | 0 | `{}` (vuoto) | 2 | 2 |
| UBS | financials | 0 | 0 | `{}` (vuoto) | 1 | 10 |
| V | financials | 0 | 0 | `{}` (vuoto) | 1 | 4 |
| VZ | telecom | 0 | 0 | `{}` (vuoto) | 2 | 5 |
| WDC | semis | 0 | 0 | `{}` (vuoto) | 2 | 2 |
| XOM | energy | 0 | 0 | `{}` (vuoto) | 1 | 1 |

**15 ticker** con `fonti_osservate` non vuoto ma **zero effective-timely**. Per ognuno di questi vale: *la fonte `alpaca_benzinga` ha reso N righe, ma nessuna effective-timely* — condizione diversa da "fonte assente", ed è il dato che serve per prioritizzare i connettori non ancora deployati. Il caso più vistoso è **MSFT, 6 articoli e 0 effective-timely**, seguito da QQQ (6 e 0) e XLE (4 e 0):

| Ticker | Settore | `articoli_unici_giorno` | `effective_timely_articles_giorno` | `fonti_osservate` |
|---|---|---:|---:|---|
| ABBV | healthcare | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| AVGO | semis | 2 | 0 | `alpaca_benzinga: {articoli_unici: 2, articoli_effective_timely: 0}` |
| AZN | healthcare | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| BAC | financials | 2 | 0 | `alpaca_benzinga: {articoli_unici: 2, articoli_effective_timely: 0}` |
| CVX | energy | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| DIS | media | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| MSFT | tech | 6 | 0 | `alpaca_benzinga: {articoli_unici: 6, articoli_effective_timely: 0}` |
| NFLX | media | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| PANW | tech | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| QQQ | etf_broad | 6 | 0 | `alpaca_benzinga: {articoli_unici: 6, articoli_effective_timely: 0}` |
| SOXX | semis | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| UNH | healthcare | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| WMT | consumer | 1 | 0 | `alpaca_benzinga: {articoli_unici: 1, articoli_effective_timely: 0}` |
| XLE | energy | 4 | 0 | `alpaca_benzinga: {articoli_unici: 4, articoli_effective_timely: 0}` |
| XLF | financials | 2 | 0 | `alpaca_benzinga: {articoli_unici: 2, articoli_effective_timely: 0}` |

Nessuna raccomandazione operativa: quali connettori accendere è decisione dell'operatore (#454/#455/#458/#459).

**Concentrazione delle fonti**: `copertura_articoli.per_fonte` — `alpaca_benzinga` 111 articoli unici (62 effective-timely, 55,9%), `gdelt_gkg` 12 (11 effective-timely, 91,7%). HHI per fonte 0,744. GDELT rende poco in volume ma quasi tutto utile, ed è la fonte che ha generato il segnale AXP di §8.

---

*Report read-only. Nessuna taratura, soglia, peso, flag o ordine è stato toccato; il periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza attesa 2026-09-28) resta in vigore. `findings.json` e `market_daily.jsonl` non sono stati modificati: i candidati di questa seduta sono in `docs/evidence/candidates/2026-09-16.json` e li valida il materializzatore.*
