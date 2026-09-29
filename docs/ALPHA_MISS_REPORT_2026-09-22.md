# Alpha Miss Report — 2026-09-22

Contratto `alpha_miss_prompt_v2` · dossier `docs/evidence/dossier/2026-09-22.json` (`schema_version` 3.1, generato 2026-09-29T08:00:30Z, prezzi Alpaca SIP `adjustment=all`). Soglia mover `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30.

## 1. Decision card

1. **Nessun miss azionabile.** Gli 11 mover (3 al rialzo, 8 al ribasso) erano o già a libro (7, `held_at_open_rate` 7/11) o ribassi non detenuti su un book long-only (4: ADBE, ERIC, WFC, BAC). `net_opportunity_usd` dei 4 candidati è **0,00 $**.
2. **Il danno della seduta sta dal lato uscita.** CSCO (S4, −4,50%) riceve segnali freschi sotto gate (−0,150 alle 16:11, −0,294 alle 18:06), ma produce solo 15 `SKIP_THRESHOLD` e nessuna SELL, perché è nel target S1 congelato. ARM, fuori da quel target, esce alla stessa regola su un −0,011. `actual_intraday_pnl_usd` di CSCO è **−65,72 $**, la peggiore riga del libro.
3. **Il realizzato è +16,59 $, tutto S4** (ARM +19,14, BABA −2,54). La somma di `actual_intraday_pnl_usd` sui 7 mover detenuti è **−20,23 $** (MU +92,65, CSCO −65,72, JPM −27,34, DELL −19,41, UBS −14,76, ARM +14,35, WDC 0,00).

## 2. Stato carta

Fonte: `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18T10:14+02:00). I cumulati si fermano al 17/09, quindi né le sedute 18/09 e 21/09 né questa sono incluse.

- Giorno **30/40** della finestra di osservazione (inizio 2026-08-03, `minimo_giorni`=40).
- Quota NO_NEWS dominante **13/30 = 43,3%**, sotto la soglia carta 0,60 (`superata_soglia`=false).
- S4 economico cumulato **−696,33 $** contro la banda ±200 $ (`within`=false): fuori banda.
- Book cumulato −66,22 $. S1 cumulato +664,95 $ contro un benchmark SPY di +943,98 $ (`delta_vs_spy` −279,03 $).
- `docs/evidence/longitudinal_panels.json` **non esiste**. I denominatori del §8 vengono quindi contati dalle occorrenze di `findings.json` e sono dichiarati come tali.

## 3. Miss del giorno

Il dossier ha 4 candidati in `candidati_miss`, tutti mover **ribassisti e non detenuti**. `funnel_v2.conteggi_pipeline`={} (nessun candidato entra nella pipeline d'ingresso). `esclusi_pipeline`.`non_actionable_long_only`=4. Nessun candidato ha uno stadio `funnel_v2.pipeline` oltre il gate né una guardia che lo abbia bloccato, quindi **oggi nessun FILTERED è possibile**. Come nei report precedenti (15, 16, 17 e 18/09), dove i due assi divergono prevale l'asse `actionability` di `funnel_v2` sul campo grezzo `causa`. Il valore legacy è riportato per riga.

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| ADBE | −4,52% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[ADBE].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only". Legacy `causa`="NO_NEWS": `news_count`=0, `segnali`=[]. Zero articoli da **6** sedute consecutive (`blind_set.per_ticker[ADBE].sedute_consecutive_zero_articoli`); `residual_vs_sector` −5,25% contro XLK. |
| ERIC | −4,20% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[ERIC].actionability`="NON_ACTIONABLE"; `causa`="NON_ACTIONABLE", `legacy_causa`="NON_CLASSIFICATO". **Il segnale c'era, anticipatorio e del segno giusto**: `max_score_own`=−0,450, due righe ISSUER_SPECIFIC `timing`=ANTICIPATORY scorate alle 13:41, cioè prima dell'open. Dal testo: Morgan Stanley declassa Ericsson da Equal-Weight a Underweight con PT da 11 a 9 $ (pubblicato 11:56). Un ribasso non detenuto però non è catturabile da un book long-only. `catalyst.type`="ANALYST". |
| WFC | −3,92% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[WFC].actionability`="NON_ACTIONABLE"; `legacy_causa`="OFF_TOPIC_NON_DECIDIBILE". Due righe, nessuna spiega il calo: una filing sull'acquisto di azioni WFC da parte del senatore McConnell (+0,010) e il roundup "Nasdaq 100 Flirts with Records…" (fan-out, 0,000). |
| BAC | −3,04% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[BAC].actionability`="NON_ACTIONABLE"; legacy `causa`="NO_NEWS" (`news_count`=0). Zero articoli da 3 sedute. L'unica menzione del giorno è nel titolo di un articolo GDELT taggato GS ("…Goldman Sachs Eases, Bank of America Slips", 17:30), che è retrospettivo. |

**Conteggi**: NO_NEWS 0 · THIN_NEUTRAL 0 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 4. La vista legacy `aggregati.cause_del_giorno` resta invariata per il vincolo #288: {"NO_NEWS":2, "OFF_TOPIC_NON_DECIDIBILE":1, "NON_CLASSIFICATO":1}, `dominante`="NO_NEWS". `gross_opportunity_usd` (legacy `costo_usd`) somma 344,64 $, ma `accessible_opportunity_usd`=0 su tutte e quattro le righe (`missing_reason`="long_only_no_short_downside_not_held").

### Titoli catturati (mover detenuti all'open o tradati: 7 su 11)

Nessun mover è stato comprato in giornata: i 3 ingressi (BABA ×2, META) non sono mover. Il P&L viene da `snapshot_apertura.actual_intraday_pnl_usd`, la pipeline d'uscita da `funnel_v2.righe[*].pipeline_uscita`.

| Simbolo | Return% | Detenuto da (nozionale all'open) | Esito di seduta |
|---|---:|---|---|
| MU | +5,00% | S4, 1.511,5 $ | PASSIVE_EXPOSURE, **+92,65 $**. 9 righe `news_log`, fra cui un'anteprima degli utili Q4 ("Micron Likely To Report Higher Q4 Earnings…", +0,320, 11:50). |
| WDC | +3,67% | S4, **0,0 $** secondo lo snapshot | PASSIVE_EXPOSURE, 0,00 $. Lo snapshot ha `qty_open`=0 con `missingness`=["exit_fill_qty_exceeds_trade_qty"], mentre `copertura_uscita` riporta qty 0,3347 (155,50 $) e il log #161 la mostra detenuta a −15/−18% per tutta la seduta. Il dossier è incoerente fra i due blocchi (§9b, F-048 e F-075). |
| ARM | +3,19% | S4, 418,5 $ | Uscita alle 17:22 @330,36, `pnl_net` **+19,14 $**, `drift_post_uscita` +3,72 $. L'uscita è decisa da un −0,011 fan-out (§8, F-008). |
| JPM | −3,42% | S1, 801,9 $ | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` +0,1725), **−27,34 $**. La riga issuer-specifica delle 17:56 ("JPMorgan Stock Slips as Traders Shift to Tech Sector", −0,200) è retrospettiva. |
| UBS | −3,66% | S1, 657,4 $ | EXIT_RISK, "EXIT_WRONG_SIGN" (+0,05, patteggiamento da 5 M€ con la procura olandese su Credit Suisse), −14,76 $. |
| CSCO | −4,50% | S4, 1.889,6 $ | EXIT_RISK, "EXIT_BELOW_THRESHOLD" (`score_firmato` −0,15), **−65,72 $**. Piper Sandler taglia il PT a 125 $ (16:09); il segnale non genera nessuna SELL (§8, F-089). |
| DELL | −4,59% | S1, 529,6 $ | EXIT_RISK, "STALE_EXIT_SIGNAL" (signal 11950 del 21/09, +0,125), −19,41 $. Zero righe `news_log`. |

KPI: `exit_signal_recall` 1/4, `active_signal_recall`/`execution_conversion_rate`/`profitable_capture_rate` 0/0 (nessun mover ENTRY_OPPORTUNITY), `avoidable_miss_count` 0.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["BABA","BABA","META"],"chiusure":["BABA","ARM"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | BABA | S4 | 15:07 | $116.7025 | 12.3054 | — | percentile 14.80%; denominatore intraday valido |
| IN | BABA | S4 | 17:37 | $116.3600 | 12.3415 | — | percentile 6.91%; denominatore intraday valido |
| IN | META | S4 | 19:07 | $738.9500 | 1.9489 | — | percentile 32.82%; denominatore intraday valido |
| OUT | BABA | S4 | — | $116.5600 | 12.3054 | −$2.54 | hold_minimum_expiry |
| OUT | ARM | S4 | — | $330.3600 | 1.3104 | +$19.14 | portfolio_sell |
<!-- alpha-miss-book:end -->

Il libro ha registrato 3 ingressi S4, nessuno su un mover: BABA alle 15:07 e alle 17:37, META alle 19:07. Il nozionale è di circa 1.436–1.440 $ ciascuno, coerente con `regime_mult` 0,7 (regime SIDEWAYS, VIX 14,21: oggi il fallback ×0,20 del 21/09 non si ripete). Tutti e tre gli ingressi arrivano a movimento fatto o oltre: `quota_movimento_precedente_al_segnale` vale BABA 0,90 e 0,99, META 1,45; `entry_percentile` 0,148, 0,069 e 0,328; `vs_apertura` −47,25 $ e −47,39 $ su BABA, che aveva aperto in gap e stava rientrando.

Le chiusure sono 2, entrambe S4 e decise nel log da `below_entry_gate`:

- **BABA**: uscita alle 16:52 su un +0,188, `pnl_net` −2,54 $, `drift_post_uscita` −3,08 $ (l'uscita ha evitato una perdita). BABA viene ricomprata 45 minuti dopo su un +0,348 (F-013).
- **ARM**: uscita alle 17:22 su un −0,011, `pnl_net` +19,14 $, drift +3,72 $.

Realizzato +16,59 $. `mtm_eod` degli ingressi ancora aperti: BABA#1024 −0,62 $, META −4,59 $. Degli intenti tradabili, 102 su 117 sono `SKIP_PYRAMIDING` (§8, F-031). Le 2 SELL non hanno `signal_id` (`decision_signal_id_coverage.by_reason_code.SELL` 0/2).

## 5. Cecita' lato uscita

`copertura_uscita` conta 45 posizioni, con `n_indeterminati`=**0**: nessuna riga ha `cieco_lato_uscita: null`. Tre posizioni sono cieche, tutte S1 e tutte ancora aperte:

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| AMAT | S1 | **−20,43%** | +1,77% | 2 | `alpaca_benzinga`, `gdelt_gkg` | 404,93 $ |
| SBUX | S1 | −9,75% | +0,22% | 9 | `alpaca_benzinga` | 625,99 $ |
| VALE | S1 | −3,07% | +0,28% | 4 | `alpaca_benzinga` | 752,12 $ |

Nessuna delle tre è uscita in seduta, quindi `ritorno_da_ingresso` misura la perdita dall'ingresso al close. `ritorno_seduta` è il solo movimento del 22/09: positivo per tutte e tre, nessuna è un mover. AMAT rientra nella lista perché la sua streak arriva a 2 (`sedute_minime`). Oltre a essere cieca, è anche senza stop (sub_one_share, log #161). La streak di SBUX continua a crescere (8 il 21/09, 9 oggi). `fonti_osservate_finestra` non è mai vuota: le fonti interrogano questi ticker ma non hanno reso righe, cioè resa zero e non fonte assente.

Aggregato: 20 posizioni a copertura grezza nulla, 31 a copertura effective-timely nulla, 10 in perdita marcata. Il nozionale cieco è **1.783,04 $** (era 1.374,61 $ il 21/09).

## 6. Backstop NO_NEWS

`no_news_backstop.population`: 45 simboli a zero righe `news_log`, di cui 4 mover e 41 non-mover (`return_missing`=0).

### 6a. Marker calendario

| Simbolo | Return% | `observed_catalysts` | Calendario |
|---|---:|---|---|
| ADBE | −4,52% | `[]` | `NOT_OBSERVED` (FMP earnings-calendar e Alpaca Corporate Actions hanno risposto) |
| DELL | −4,59% | `[]` | `NOT_OBSERVED`, stesse fonti (detenuto S1, EXIT_RISK) |
| WDC | +3,67% | `[]` | `NOT_OBSERVED`, stesse fonti (detenuto S4, PASSIVE_EXPOSURE) |
| BAC | −3,04% | `[]` | `NOT_OBSERVED`, stesse fonti |

`mover_observed` è 0/4 contro 0/41 fra i non-mover: oggi nessun marker `CALENDAR`. `calendario_earnings.status`="OBSERVED", `simboli_flaggati`=[]. Un marker CALENDAR indicherebbe un evento a calendario, non un segnale né un ordine.

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false. Il volume di seduta si conosce solo alla chiusura, quindi nessuno di questi valori era disponibile prima del movimento. Qui non si fissano soglie né si stimano false-positive rate: la valutazione ex-ante è in #451.

- Mediana della sorpresa di volume: **+28,7%** sui mover a zero news (n=4), **−10,7%** sui non-mover (n=41).
- Per simbolo: ADBE +33,1%, WDC +32,0%, BAC +25,3%, DELL −6,1%.

### 6c. Copertura raw di `news_log` per settore (tutti i settori)

Questa è la copertura **raw**. È distinta dalla copertura effective-timely di `copertura_articoli.per_settore`, che oggi è 31/96 (32,3%) a livello di watchlist.

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news | calendario su zero news |
|---|---:|---:|---:|---:|
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| financials | 12/14 | 85,7% | 1 (BAC) | 0 |
| semis | 11/15 | 73,3% | 2 (DELL, WDC) | 0 |
| healthcare | 6/9 | 66,7% | 0 | 0 |
| tech | 12/21 | 57,1% | 1 (ADBE) | 0 |
| telecom | 2/5 | 40,0% | 0 | 0 |
| media | 1/5 | 20,0% | 0 | 0 |
| consumer | 2/11 | 18,2% | 0 | 0 |
| energy | 1/6 | 16,7% | 0 | 0 |
| industrials | 0/4 | **0,0%** | 0 | 0 |
| materials | 0/2 | **0,0%** | 0 | 0 |

In totale 51/96 simboli hanno almeno una riga (`watchlist_zero_news`=45, erano 40 il 21/09). Rispetto al 21/09: consumer scende da 6/11 a 2/11, energy da 3/6 a 1/6, industrials da 3/4 a 0/4, mentre financials sale da 5/14 a 12/14.

### 6d. Attribuzione fonti per ticker (#511 passo 2)

Per tutti i 45 ticker con `articoli_unici`=0, `fonti_osservate`={} e `articoli_unici_giorno` = `effective_timely_articles_giorno` = 0 (da `blind_set.per_ticker`). Tra parentesi `sedute_consecutive_zero_articoli`:

ABBV (1), ADBE (6), AMAT (2), ASML (1), AXP (2), BA (1), BAC (3), BP (4), CAT (1), CMCSA (4), COST (1), CRM (1), CVX (1), DELL (1), DIS (1), F (2), GE (1), GM (1), HD (7), IBM (2), INFY (8), JD (3), JNJ (1), MCD (1), MMM (5), MRK (2), NOW (1), PBR (2), PG (2), RDDT (2), RIO (7), ROKU (9), SAP (5), SBUX (9), SHEL (5), SNOW (7), SONY (2), T (1), TM (1), TMUS (1), VALE (4), VZ (6), WDC (1), WMT (3), XOM (1).

`ticker_allerta_zero_articoli` (≥5): ADBE, HD, INFY, MMM, RIO, ROKU, SAP, SBUX, SHEL, SNOW, VZ. ERIC esce dall'allerta: aveva 10 sedute a zero il 21/09, oggi 3 articoli (il downgrade).

Fonte presente ma non utile (articoli > 0, effective-timely 0): in tutti i casi la fonte `alpaca_benzinga` ha reso N righe, ma nessuna effective-timely. SPY 39, XLK 3, ARM 2, AVGO 2, HOOD 2, NVO 2, SOXX 2, XLF 2, XLV 2, AZN 1, BIDU 1, DB 1, IWM 1, MRVL 1, NOK 1, QCOM 1, TSM 1, UNH 1, V 1, XLE 1. Nel blocco `per_fonte`: `alpaca_benzinga` ha 135 articoli unici, di cui 71 effective-timely (52,6%); `gdelt_gkg` 11 su 11. La scelta dei connettori resta all'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Rotazione dai finanziari verso i semis: quarta seduta di forza sui semis e vendite compatte sulle banche.**

- **Ribassisti finanziari**: 4 degli 8 mover ribassisti sono `financials` (WFC −3,92%, UBS −3,66%, JPM −3,42%, BAC −3,04%). Appena sotto soglia ci sono MS −2,88%, AXP −2,72%, V −2,14% e MA −2,07%; XLF fa −1,97% contro SPY −0,02%. L'unica riga che nomina un movente è "JPMorgan Stock Slips as Traders Shift to Tech Sector" (17:56), che descrive il movimento a cose fatte. Nel testo letto non c'è un catalizzatore societario comune.
- **Rialzisti**: sono tutti e 3 semis/memoria (MU +5,00%, WDC +3,67%, ARM +3,19%), con SOXX +2,40% e QQQ +0,81%. Il tema dei semis era già presente il 17, 18 e 21/09: è una continuazione.
- **Altri ribassisti**: sono idiosincratici e senza tema comune. CSCO −4,50% (Piper Sandler taglia il PT), ERIC −4,20% (downgrade di Morgan Stanley), ADBE −4,52% e DELL −4,59% (zero righe).
- **Novità rispetto al 21/09**: la gamba ribassista si sposta dall'energy ai finanziari, e `dispersione_sigma` scende a 1,82% (era 3,14%).

## 8. Segnalazioni

Tre finding esposti oggi. I denominatori vengono contati dalle occorrenze di `findings.json`, perché `longitudinal_panels.json` non esiste. Nota: il forense del 22/09 ha già registrato occorrenze degli stessi tre id sulla stessa seduta, ma senza dossier. Qui i costi sono ricalcolati solo con i campi del dossier.

### [F-089] CSCO, S4 nel target S1 congelato, riceve tre segnali freschi sotto gate e non esce: 15 cicli di `SKIP_THRESHOLD` su una posizione da 1.824 $ a −4,50%

- **Meccanismo e fonte**: §3 (titoli catturati) e §4. Campi del dossier:
  - `funnel_v2.righe[CSCO].pipeline_uscita`="EXIT_BELOW_THRESHOLD";
  - `intenti_ingresso_s4` (signal 12114 −0,150 alle 16:11 ensemble, 12176 −0,294 alle 18:06 ensemble; `prezzo_al_segnale` 105,22);
  - `guard_decisions`: 15 righe `SKIP_THRESHOLD` su CSCO dalle 16:22 alle 19:52;
  - `copertura_uscita[CSCO]`: trade 830, S4 dal 25/08, qty 17,1357.
  Il target S1 (`strategy:rebalance_state:S1`, `last_rebalance` 2026-09-01) contiene CSCO a peso 0,0236. Il log registra "Exit hysteresis (2 cycles)" solo per BABA (16:37) e ARM (17:07), mai per CSCO.
- **Esposizione oggi**: tutti i cicli dopo le 16:11 sulla posizione S4 più grande fra i mover (nozionale 1.823,92 $, 83% di uno slot) e sul peggior `actual_intraday_pnl_usd` del libro (−65,72 $). F-089 conta 3 sedute distinte in `findings.json` (17, 18 e 22/09, quest'ultima dal forense).
- **Evidenza contraria**: se il finding fosse falso, CSCO sarebbe stata segnata per l'uscita due cicli dopo il primo segnale sotto gate, come ARM (segnale alle 17:05, flag alle 17:07, SELL alle 17:22) e BABA (segnale alle 15:27, flag alle 16:37, SELL alle 16:52). Oggi non si vede né il flag né la SELL.
- **Non-occorrenza**: ARM e BABA, fuori dal target S1, escono alla stessa regola `below_entry_gate`. Sulle altre posizioni S4 nel target (MU, WDC, MRVL, INTC, QQQ, XLE, PANW) il fenomeno non si decide oggi dal dossier, perché nessun loro segnale compare fra i mover.
- **Next evidence (read-only)**: sulla finestra dal 20/08, per ogni posizione S4 dentro il target S1, contare i segnali ensemble freschi sotto gate e le SELL seguite entro 2 cicli, e confrontarli con le posizioni S4 fuori target. Se il rapporto SELL/segnale è ~0 dentro e ~1 fuori, il meccanismo è confermato indipendentemente dal P&L.
- **Costo**: **−20,91 $** (attribuita, stessa confidenza del record). Formula: qty trade 830 × (`prezzo_al_segnale` intento 12114 − `mark_close`) = 17,1357 × (105,22 − 106,44). Oggi il disarmo dell'uscita ha giovato: il segnale arriva vicino al minimo (`ritorno_sessione_al_segnale` −5,6% contro il −4,50% del close). Alternativa scartata: il prezzo al 2° ciclo (16:37, 105,03, usato dal forense per −23,99 $) non è nel dossier. Scartato anche il totale sulle 7 posizioni (−72,50 $ nel forense), per lo stesso motivo.

### [F-008] ARM (+3,19%) esce su una riga fan-out a −0,011 dopo un ingresso issuer-specifico a +0,581

- **Meccanismo e fonte**: §3 e §4. Campi: `chiusure[ARM]` (`exit_reason` portfolio_sell, `drift_post_uscita` 3,72) e `copertura_uscita[ARM]` (2 articoli, 0 effective-timely: nessuna riga ISSUER_SPECIFIC nella seduta). `execution_decisions` SELL 17:22: "[below_entry_gate] … generated 2026-09-22 17:05 UTC, score=-0.011". Il signal 12137 viene dall'editoriale "Commodity ETF Delivers Double Nvidia's YTD Returns; Muse Ignites CPU Fever", che non tratta di Arm. L'ingresso del 21/09 era sul signal 11898, +0,581.
- **Esposizione oggi**: 2 chiusure S4, di cui una (ARM) decisa da una riga senza conferma di rilevanza. F-008 conta 15 sedute distinte in `findings.json` (ultima 22/09, dal forense).
- **Evidenza contraria**: se il finding fosse falso, l'uscita ARM avrebbe una causa issuer-specifica negativa oppure il titolo sarebbe sceso dopo. Invece il segnale è −0,011, non parla di Arm, e il close (333,20) è sopra l'uscita (330,36).
- **Non-occorrenza**: BABA esce su un segnale on-topic (+0,188, notizia Alibaba) con `drift_post_uscita` −3,08 $: l'uscita ha evitato una perdita. Il costo compare solo sull'uscita decisa dalla riga off-topic.
- **Next evidence (read-only)**: invariato. Per tutte le SELL S4 `below_entry_gate` della finestra, classificare il segnale citato nel `reason` per `attribution` e confrontare la mediana di `drift_post_uscita` fra FANOUT/UNKNOWN e ISSUER_SPECIFIC. Il join va fatto sul timestamp del testo, perché `signal_id` è NULL sulle SELL (F-011).
- **Costo**: **3,72 $** (attribuita). Formula: `drift_post_uscita` = qty × (close − exit) = 1,3104 × (333,20 − 330,36). Scartato come alternativa il realizzato +19,14 $, perché misura l'ingresso e non l'uscita.

### [F-031] SKIP_PYRAMIDING sale a 102 intenti su 117 tradabili (87,2%), con 4 righe tracciate in `execution_decisions`

- **Meccanismo e fonte**: §4. Campi: `intenti_ingresso_s4` (`final_reason_code`: 102 SKIP_PYRAMIDING, 12 SKIP_IDEMPOTENCY, 3 SUBMITTED) e `guard_decisions` (4 righe SKIP_PYRAMIDING). Blocchi per simbolo: NOW 24, GM 24, AMAT 19, SOXX 14, ARM 12, MRK 5, JPM 3, GOOGL 1. Sui simboli detenuti da **S1** (GM, AMAT, SOXX, MRK, JPM, GOOGL) cadono 66/102 blocchi (64,7%); su quelli detenuti da S4 stessa, cioè il guard come progettato (NOW, ARM), 36.
- **Esposizione oggi**: 102 intenti. Fra i mover sono toccati ARM (detenuta da S4) e JPM (S1, −3,42%, dove il blocco ha evitato un ingresso su un titolo in calo). F-031 conta 22 sedute distinte in `findings.json` (inclusa la 22/09 del forense). La quota sui tradabili è 87,2%, contro il 78,3% del 21/09. La traccia in `guard_decisions` copre 4/102 (3,9%, era 7,4%).
- **Evidenza contraria**: se il guard proteggesse soprattutto dal raddoppio delle posizioni S4, i blocchi su posizioni S4 sarebbero la maggioranza. Sono 36/102.
- **Non-occorrenza**: nessuno dei 4 candidati miss del §3 è toccato (zero intenti SKIP_PYRAMIDING su ADBE, ERIC, WFC, BAC). BABA e META, non detenute, passano (SUBMITTED).
- **Next evidence (read-only)**: invariato. Sulla finestra, calcolare la quota degli intenti tradabili in SKIP_PYRAMIDING per sleeve detentrice, con controfattuale a 1 h e al close; l'orizzonte va pre-registrato prima della misura.
- **Costo**: **−4,40 $** (congetturale). Formula: Σ `intended_notional_usd` × `counterfactual_return_1h` sulle righe `guard_decisions` SKIP_PYRAMIDING di simboli detenuti da S1 = 2.199,84 × (−0,003430) [GOOGL] + 2.198,72 × 0,001429 [SOXX] = −7,54 + 3,14. È la stessa famiglia di formula del 21/09. Scartate le righe ARM e NOW (+18,00 $), perché lì il guard blocca il raddoppio di una posizione S4, cioè fa quello per cui è progettato. Scartata anche l'estrapolazione ai 66 intenti non tracciati: il controfattuale esiste solo per le righe in `guard_decisions`.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli, dal più alto al più basso)

| | | | |
|---|---|---|---|
| MU +5,00% | WDC +3,67% | ARM +3,19% | HD +2,74% |
| MMM +2,62% | WMT +2,49% | SOXX +2,40% | ASML +2,14% |
| QCOM +2,08% | MRVL +1,93% | SPCX +1,89% | AMAT +1,77% |
| INTC +1,71% | TSM +1,54% | PG +1,46% | AMD +1,34% |
| PLTR +1,04% | MCD +1,00% | TSLA +0,96% | MRK +0,94% |
| QQQ +0,81% | HOOD +0,77% | PANW +0,76% | XLK +0,73% |
| SHEL +0,71% | SAP +0,70% | PFE +0,68% | NVDA +0,66% |
| PBR +0,63% | IWM +0,57% | XLV +0,52% | AVGO +0,52% |
| BABA +0,48% | RIO +0,46% | LLY +0,45% | ORCL +0,43% |
| JD +0,37% | BRK.B +0,29% | VALE +0,28% | ABBV +0,28% |
| XOM +0,26% | BIDU +0,24% | AAPL +0,23% | SBUX +0,22% |
| TXN +0,20% | AZN +0,16% | COST +0,10% | GE +0,07% |
| NKE +0,00% | SPY −0,02% | ROKU −0,05% | JNJ −0,10% |
| BP −0,14% | TM −0,23% | IBM −0,24% | DIS −0,39% |
| NOW −0,49% | F −0,53% | GM −0,60% | CVX −0,62% |
| META −0,63% | MSFT −0,72% | SONY −0,72% | SNOW −0,83% |
| NVO −1,01% | GS −1,03% | CAT −1,04% | GOOGL −1,07% |
| XLE −1,09% | NOK −1,10% | INFY −1,19% | UNH −1,22% |
| CRM −1,33% | AMZN −1,34% | T −1,38% | NFLX −1,64% |
| BA −1,71% | TMUS −1,73% | DB −1,80% | C −1,91% |
| RDDT −1,93% | XLF −1,97% | MA −2,07% | V −2,14% |
| CMCSA −2,22% | VZ −2,58% | AXP −2,72% | MS −2,88% |
| BAC −3,04% | JPM −3,42% | UBS −3,66% | WFC −3,92% |
| ERIC −4,20% | CSCO −4,50% | ADBE −4,52% | DELL −4,59% |

`dispersione_sigma` 1,82%; `mover_3pct` 11 (3 al rialzo, 8 al ribasso); `simboli_senza_dati`=[].

### (b) Checklist degli altri finding toccati

- [F-001] supported: 45/96 simboli a zero righe `news_log` (erano 40 il 21/09); 4 mover a zero news, 2 dei quali fra i candidati.
- [F-011] supported: 2/2 SELL senza `signal_id` (`decision_signal_id_coverage.by_reason_code.SELL` 0/2).
- [F-012] supported: 232 righe su 146 articoli (`mapping_fanout_extra` 86), TAG_UNCONFIRMED 137/232 (59,1%).
- [F-013] supported: BABA venduta alle 16:52 su +0,188 e ricomprata alle 17:37 su +0,348, sulla stessa seduta.
- [F-017] not_exposed: `event_market_context.regime` SIDEWAYS 0,7 con VIX 14,21 sui cicli; nozionale d'ingresso ~1.436–1.440 $, nessun fallback ×0,20.
- [F-022] supported: il log #161 riporta "10/44-46 held positions are unprotectable (qty < 1)" per tutta la seduta, con AMAT a −21% e WDC a −15/−18%.
- [F-030] supported: `quota_movimento_precedente_al_segnale` BABA 0,90 e 0,99, META 1,45; il downgrade ERIC pubblicato alle 11:56 viene scorato alle 13:41. Mediana mobile a 20 gg di `entry_percentile` 0,522.
- [F-040] supported: ERIC −0,450 ISSUER_SPECIFIC ANTICIPATORY, sopra gate e col segno corretto su un −4,20%, senza percorso nel book long-only (`accessible_opportunity_usd` 0).
- [F-048] supported: `snapshot_apertura[WDC]` ha `qty_open` 0 con "exit_fill_qty_exceeds_trade_qty", mentre `copertura_uscita[WDC]` ha qty 0,3347 e il log #161 la mostra detenuta.
- [F-073] supported: BUY META con `signal_score` 0,354 persistito, mentre il gate ha valutato 0,424 (× velocity 1,2).
- [F-075] supported: WDC (155,50 $ in `copertura_uscita`, 7% di uno slot, 0 $ nello snapshot) è contata come mover detenuto alla pari di MU (1.511,5 $), in `held_at_open_rate` 7/11.
- [F-078] supported: 29 righe `SKIP_FALLBACK` (`decision_signal_id_coverage`); il log le chiama "dropped N fallback signal(s) from BUY ranking (#108)" (CSCO, UBS e WDC in ogni ciclo fino alle 16:07).
- [F-082] supported: la guardia ombra ha 19 soppressioni su 117 tradabili, `n_soppressi_eseguiti`=0.

### (c) Casi di successo

- **MU +5,00%**: posizione S4 già a libro (1.511,5 $ all'open), passiva nella seduta, **+92,65 $**. È il miglior contributo della giornata; nessuna decisione attiva.
- **ARM +3,19%**: ingresso del 21/09 su +0,581 issuer-specifico, uscita alle 17:22 con **+19,14 $** realizzati. L'esito è ridotto di 3,72 $ dall'uscita su fan-out (§8, F-008).
