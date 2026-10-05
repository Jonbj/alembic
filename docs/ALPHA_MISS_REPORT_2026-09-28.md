# Alpha Miss Report — 2026-09-28

Contratto `alpha_miss_prompt_v2` · dossier `docs/evidence/dossier/2026-09-28.json` (`schema_version` 3.1, generato 2026-10-05T08:00:34Z, prezzi Alpaca SIP `adjustment=all`). Soglia mover `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30.

## 1. Decision card

1. **12 mover su 13 al ribasso, nessun miss accessibile**: gli 8 candidati sono ribassi non detenuti (`net_opportunity_usd` 0 su tutti, lordo 932,38 $ non accessibile long-only). In testa ARM −8,70%, QCOM −7,17% e BA −6,91%. SPY −0,74%, QQQ −1,07%, SOXX −2,08%.
2. **INTC −5,67% (S4, −67,46 $) non esce**: alle 17:07 riceve un segnale fresco −0,184 sul proprio calo ("Why Is Intel Stock Falling on Monday?") e resta 12 cicli in `SKIP_THRESHOLD` senza flag d'uscita. Lo stesso giorno NVDA, fuori target, viene venduta su un −0,006 (F-089). I 4 mover detenuti in calo valgono `actual_intraday_pnl_usd` **−138,43 $**; PANW +4,63% ne recupera +83,26.
3. **Realizzato +32,72 $, tutto S4** (NVDA +27,98, COST +4,74). NVDA però viene venduta alle 14:52 a 229,12 e ricomprata alle 18:22 a 230,18: il churn costa **6,76 $** (F-013).

## 2. Stato carta

Fonte: `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18T10:14+02:00). I cumulati si fermano al 17/09 e non includono le sedute dal 18/09 a questa.

- Giorno **30/40** della finestra di osservazione (inizio 2026-08-03, `minimo_giorni`=40). La carta indica come scadenza attesa proprio il **2026-09-28**. Il file però conta 30 sedute osservate al 17/09, perché mancano le sedute non misurate (09-09, 09-10, 09-14). Il numero di giorno di oggi non si ricava dal file: **DATA_INCOMPLETE**.
- Quota NO_NEWS dominante **13/30 = 43,3%**, sotto la soglia carta 0,60 (`superata_soglia`=false).
- S4 economico cumulato **−696,33 $** contro la banda ±200 $: **fuori banda** (`within`=false). BOOK −66,22 $.
- `docs/evidence/longitudinal_panels.json` **non esiste**. I denominatori del §8 sono contati dalle occorrenze di `findings.json` (sedute distinte) e dichiarati come tali.

## 3. Miss del giorno

Il dossier ha 8 candidati in `candidati_miss`. La vista legacy `aggregati.cause_del_giorno` resta invariata (vincolo #288): {"NO_NEWS":2,"BELOW_GATE":3,"NON_CLASSIFICATO":3}, `dominante`="BELOW_GATE", `quota_righe_fanout` 0,56. Come nei report precedenti, dove l'asse `actionability` di `funnel_v2` e il campo grezzo `causa` divergono prevale il primo. Tutti e 8 sono `NON_ACTIONABLE` (`pipeline_escluso_motivo`="non_actionable_long_only"): ribassi su titoli non detenuti, che una strategia long-only non può catturare. `funnel_v2.conteggi_pipeline`={}: nessuno stadio oltre il gate e nessuna guardia, quindi **nessun FILTERED**.

| Simbolo | Return% | Categoria | Campo del dossier che decide · evidenza testuale |
|---|---:|---|---|
| ARM | −8,70% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="BELOW_GATE" (`max_score_own` +0,05, fallback, segno opposto). Unica riga: "Oil Rises; Meta's Muse Trade Extends To CPU Stocks Like Intel, AMD, Arm, Qualcomm" (17:12, 12 ticker), un commento tecnico su petrolio e CPU. Nessuna notizia specifica su Arm. `gross_opportunity_usd` 191,34 $, `accessible`=0. |
| QCOM | −7,17% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="NON_CLASSIFICATO". `max_score_own` −0,42 (segno giusto, ma fallback). "What Is Going on With Qualcomm Stock on Monday?" (16:37): prese di beneficio dopo il rally mensile, "without a single new negative company-specific headline". Lordo 157,84 $. |
| BA | −6,91% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="NON_CLASSIFICATO". Notizia idiosincratica: glitch software del 737 MAX (WSJ), "Why Is Boeing Stock Falling Monday?" pubblicata alle 14:04, scorata −0,409 non-fallback alle 14:31, sopra gate col segno giusto. Intenti: 6 `RANK_LONG_ONLY` sul segnale 12898 e 3 sul 13061 (−0,318, ritardo certificazione MAX 10). Lordo 151,95 $. |
| META | −4,79% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="BELOW_GATE" (`max_score_own` −0,28, fallback). 15 righe, tutte sotto gate: finanziamento del debito AI ("Oracle, Meta Financing Methods Mirror Enron Era", "Meta Is Coming for Europe's Bond Market") e privacy di Muse. Lordo 105,48 $. |
| RDDT | −4,51% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="NO_NEWS" (`news_count` 0). Sesta seduta consecutiva a zero articoli (`blind_set`). Lordo 99,25 $. |
| TSLA | −3,94% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="NON_CLASSIFICATO". `max_score_own` −0,214 (sotto gate), fan-out −0,30. JPM abbassa il target a 415 $; "Tesla Stock Drops: What's Going On Today?" (15:50). Lordo 86,67 $. |
| ORCL | −3,28% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="BELOW_GATE" (`max_score_own` −0,258). "Oracle Stock Slips as Google's Mandiant Flags New PeopleSoft Breach Wave" (14:38). 2 intenti `RANK_LONG_ONLY`. Lordo 72,21 $. |
| NOW | −3,07% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE"; legacy `causa`="NO_NEWS" (`news_count` 0, prima seduta a zero). Lordo 67,64 $. |

**Conteggi**: NO_NEWS 0 · THIN_NEUTRAL 0 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 8. Somma `gross_opportunity_usd` (legacy `costo_usd`) **932,38 $**. `accessible_opportunity_usd`=0 su tutte le righe (`missing_reason`="long_only_no_short_downside_not_held"), `avoidable_miss_count`=0.

### Mover detenuti all'open (5 su 13) e titoli catturati

Nessun mover è stato catturato con un ingresso del giorno: l'unico ingresso, NVDA (+1,68%), non è un mover.

| Simbolo | Return% | Posizione | Esito di seduta (`snapshot_apertura`, `funnel_v2`) |
|---|---:|---|---|
| PANW | +4,63% | S4, 1.436,56 $ (trade 1001) | PASSIVE_EXPOSURE (`held_rising`), `actual_intraday_pnl_usd` **+83,26 $** (residuo beta-1 +88,48). Segnale +0,422 alle 17:37, 10 intenti `SKIP_PYRAMIDING` (già detenuta). |
| INTC | −5,67% | S4, 1.752,64 $ (trade 1007) | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN", `evidence_uscita.score_firmato` +0,102. **−67,46 $** (residuo −43,05). `execution_decisions` mostra però un segnale fresco 12988 −0,184 dalle 17:07, con 12 `SKIP_THRESHOLD` fino alle 19:52 e nessuna SELL (§8, F-089). Il valore firmato del dossier e quello delle decisioni non sono riconciliati; per la categoria vale il dossier. |
| MRVL | −3,83% | S4, 1.655,08 $ (trade 1005) | EXIT_RISK, `pipeline_uscita`="STALE_EXIT_SIGNAL" (segnale 12512 del 24/09, −0,12, fallback). **−49,40 $** (residuo −26,35). Zero righe `news_log` oggi (2 sedute); osservata fino alle 14:52, poi assente dalle decisioni, senza SELL. |
| AMD | −3,61% | S1, 508,45 $ (trade 307) | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` +0,18, single-model fallback). **−13,85 $**. |
| DELL | −3,46% | S1, 512,85 $ (trade 293) | EXIT_RISK, `pipeline_uscita`="STALE_EXIT_SIGNAL" (segnale 12797 del 25/09, 0,000). Zero righe oggi. **−7,72 $**. |

KPI `funnel_v2.kpi`:
- `held_at_open_rate` 5/13;
- `active_signal_recall` null (0/0);
- `execution_conversion_rate` null (0/0);
- `profitable_capture_rate` null (0/0);
- `exit_signal_recall` **0/4**, `exit_conversion_rate` null (0/0).

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["NVDA"],"chiusure":["COST","NVDA"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | NVDA | S4 | 18:22 | $230.1800 | 6.3995 | — | percentile 41.39%; denominatore intraday degenere: quota non interpretabile |
| OUT | COST | S4 | — | $924.9000 | 1.6123 | +$4.74 | portfolio_sell |
| OUT | NVDA | S4 | — | $229.1230 | 6.6064 | +$27.98 | portfolio_sell |
<!-- alpha-miss-book:end -->

Un ingresso e due chiusure, tutti S4. Nessuna attività S1 (log: "S1: rebalance gate closed — holding 43 position(s)").

- **COST** esce alle 14:22 (`[fallback_filtered]`, decisione 48626) su un segnale FinBERT fallback +0,040 delle 13:58, escluso dal ranking (#108) e quindi a peso 0. `pnl_net` +4,74 $, `drift_post_uscita` −3,19 $: l'uscita ha evitato una perdita (§8, F-059).
- **NVDA** (trade 1032) esce alle 14:52 (`[below_entry_gate]`, decisione 48841) su un −0,006 delle 14:23, generato da un articolo su Anthropic Claude e gli enzimi. `pnl_net` +27,98 $, `drift_post_uscita` −1,74 $. Alle 18:22 rientra (trade 1034) sul +0,405 × velocity 1,20 di "Nvidia Stock Gains on Record Buyback": `entry_price` 230,18, `entry_percentile` 0,41, `mtm_eod` −8,45 $, `denominatore_degenere`=true.
- Realizzato **+32,72 $**. `decision_quality.summary`: passivo −102,72 $, `active_decision_pnl_usd` −3,52 $, `actual_intraday_pnl_usd` −106,24 $, beta-1 di mercato −136,97 $. Il libro ha perso meno del mercato.
- **Integrità**: le 2 SELL non hanno `signal_id` (`decision_signal_id_coverage.regressions`=["SELL"]). Guardia di contraddizione: 0 soppressi su 86 intenti tradabili. Intenti tradabili: 84 `SKIP_PYRAMIDING` (WDC 24, ABBV 22, XLE 11, PANW 10, AMD 8, NVDA 7, XOM 2), 1 `SUBMITTED`, 1 `SKIP_IDEMPOTENCY`.

## 5. Cecita' lato uscita

`copertura_uscita` conta 45 posizioni, con `n_indeterminati`=**0**: nessuna riga ha `cieco_lato_uscita: null`. Tre posizioni sono cieche, tutte ancora aperte:

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| NOK | S1 | **−13,65%** | −2,60% | 2 | `alpaca_benzinga`, `gdelt_gkg` | 5,71 $ |
| VALE | S1 | −7,17% | −0,15% | 8 | `alpaca_benzinga` | 720,32 $ |
| CSCO | S4 | −4,26% | +0,04% | 4 | `alpaca_benzinga`, `gdelt_gkg` | 1.822,04 $ |

Nessuna è uscita in seduta. `ritorno_da_ingresso` è la perdita dall'ingresso al close, mentre `ritorno_seduta` è il solo movimento del 28/09. Rispetto al 25/09 esce AMAT, che oggi ha righe, ed entra NOK. NOK ha però `qty_open` 0 in `snapshot_apertura` (residuo F-048), quindi il suo nozionale è quasi nullo. Nozionale cieco **2.548,06 $** (2.958,41 $ il 25/09). Aggregato: 12 posizioni a copertura grezza nulla, 18 a copertura effective-timely nulla, 10 in perdita marcata.

MRVL e DELL (mover in calo, zero righe oggi) non sono cieche per definizione: dall'ingresso sono in guadagno (+9,05% e +27,06%), quindi sopra la soglia −3%.

## 6. Backstop NO_NEWS

`no_news_backstop.population`: 34 simboli a zero righe `news_log`, **4 mover** (DELL, MRVL, NOW, RDDT) e 30 non-mover (`return_missing`=0).

### 6a. Marker calendario

| Mover NO_NEWS | Settore | Return% | `observed_catalysts` |
|---|---|---:|---|
| RDDT | media | −4,51% | [] (`NOT_OBSERVED`) |
| MRVL | semis | −3,83% | [] (`NOT_OBSERVED`) |
| DELL | semis | −3,46% | [] (`NOT_OBSERVED`) |
| NOW | tech | −3,07% | [] (`NOT_OBSERVED`) |

`mover_observed` 0/4. `non_mover_observed` 1/30: PBR ha il marker `CALENDAR` (dividendo). Un marker calendario non è un segnale né un ordine. `calendario_earnings.status`="OBSERVED", `simboli_flaggati`=[].

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false. Il volume di seduta e l'etichetta mover si conoscono solo al close, quindi nessuno di questi valori era disponibile prima del movimento. Non si fissano soglie né si stimano false-positive rate (#451).

- Mediana della sorpresa di volume sui mover a zero news: **−16,89%** (n=4: DELL −39,2%, NOW −18,0%, MRVL −15,8%, RDDT −8,6%).
- Mediana sui non-mover: **−6,62%** (n=30).

### 6c. Copertura raw di `news_log` per settore (tutti i settori)

Copertura **raw**, distinta dalla effective-timely di `copertura_articoli.effective_timely_coverage` (49/96, 51,0%).

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news | calendario su zero news |
|---|---:|---:|---:|---:|
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| energy | 5/6 | 83,3% | 0 | 1 |
| healthcare | 7/9 | 77,8% | 0 | 0 |
| industrials | 3/4 | 75,0% | 0 | 0 |
| semis | 11/15 | 73,3% | **2** | 0 |
| consumer | 8/11 | 72,7% | 0 | 0 |
| financials | 9/14 | 64,3% | 0 | 0 |
| media | 3/5 | 60,0% | **1** | 0 |
| tech | 11/21 | 52,4% | **1** | 0 |
| telecom | 1/5 | **20,0%** | 0 | 0 |
| materials | 0/2 | **0,0%** | 0 | 0 |

In totale 62/96 simboli hanno almeno una riga (`watchlist_zero_news`=34; erano 40 il 25/09).

### 6d. Attribuzione fonti per ticker (#511 passo 2)

Per tutti i 34 ticker con `articoli_unici`=0 vale `fonti_osservate`={} e `articoli_unici_giorno` = `effective_timely_articles_giorno` = 0 (da `blind_set.per_ticker`). Tra parentesi `sedute_consecutive_zero_articoli`:

ADBE (2), AXP (3), AZN (4), BABA (2), BIDU (2), CSCO (4), DELL (1), ERIC (4), HD (10), HOOD (1), IBM (2), INFY (1), JD (7), MA (4), MMM (1), MRVL (2), NOK (2), NOW (1), PBR (1), PFE (4), RDDT (6), RIO (2), ROKU (2), SAP (9), SBUX (1), SONY (3), SOXX (2), TM (2), TMUS (1), V (3), VALE (8), VZ (3), WDC (1), WFC (4).

`ticker_allerta_zero_articoli` (≥5 sedute): HD, JD, RDDT, SAP, VALE.

Fonte presente ma non utile: nei 13 casi seguenti la fonte `alpaca_benzinga` ha reso N righe, ma nessuna effective-timely. QQQ 7, AAPL 4, XLK 3; 2 righe ciascuno AVGO, IWM, WMT; 1 riga ciascuno CAT, CRM, JNJ, NFLX, NVO, PG, UBS.

Per fonte: `alpaca_benzinga` 137 articoli unici, di cui 92 effective-timely (67,2%); `gdelt_gkg` 11 su 11. La scelta dei connettori resta all'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Risk-off su AI, semiconduttori e software, con i difensivi in rialzo.** SPY −0,74%, QQQ −1,07%, SOXX −2,08%, `dispersione_sigma` 1,99%.

- **Ribassisti**: ARM −8,70%, QCOM −7,17%, INTC −5,67%, MRVL −3,83%, AMD −3,61%, DELL −3,46% e MU −2,61% fra semis e hardware. META −4,79%, ORCL −3,28%, NOW −3,07% e CRM −2,88% fra piattaforme e software.
  - Gli articoli letti parlano di prese di beneficio dopo il rally mensile (INTC "+28,42% over the past month"; QCOM "without a single new negative company-specific headline"), rendimenti dei Treasury più alti e timori sul finanziamento a debito dell'AI (META e ORCL).
  - L'unico ribasso idiosincratico chiaro è **BA −6,91%** (glitch software del 737 MAX).
- **Rialzisti**: PANW +4,63% (unico mover al rialzo), PG +1,91%, NKE +1,79%, NVDA +1,68% (riacquisto azioni record), ASML +1,58%. Energia: PBR +1,37%, XOM +1,20%, CVX +0,94%. Una riga Benzinga titola "8 Of 11 Sectors Fall In Monday Trading As Defensives Lead".
- **Rispetto al 25/09**: QCOM (+3,97% → −7,17%), DELL (+5,01% → −3,46%), ARM (+1,30% → −8,70%) e PANW (−3,89% → +4,63%) invertono il movimento. La stessa alternanza si era vista fra 24/09 e 25/09 (META, INTC, DELL): è la seconda inversione di fila su questo gruppo. È una lettura dei rendimenti, non una causa verificata.

## 8. Segnalazioni

Tre finding esposti oggi, tutti lato uscita. I denominatori sono contati dalle occorrenze di `findings.json` (sedute distinte), perché `longitudinal_panels.json` non esiste.

### [F-089] INTC riceve alle 17:07 un segnale fresco −0,184 sul proprio calo e non esce; NVDA, fuori dal target S1, viene venduta su un −0,006

- **Meccanismo e fonte**: §3 (mover detenuti) e §4. Campi del dossier:
  - `funnel_v2.righe[INTC].pipeline_uscita`="EXIT_WRONG_SIGN";
  - `timeline` segnale 12988: `eligible_cycle_at` 17:07:04, prezzo 115,38;
  - `snapshot_apertura[INTC]`: `qty_open` 14,523678, close 116,03, `actual_intraday_pnl_usd` −67,46.
  In `execution_decisions` ci sono 12 righe `SKIP_THRESHOLD` per INTC dalle 17:07 alle 19:52, sul segnale 12988 (−0,184, non-fallback, "Why Is Intel Stock Falling on Monday?"). Nel log worker le sole due righe "Exit hysteresis … flagged for exit" nominano COST (14:07) e NVDA (14:37). NVDA esce quindi sul −0,006 delle 14:23, con lo stesso schema segnale sotto gate → flag → SELL al ciclo successivo. Il log mostra "S1: rebalance gate closed — holding 43 position(s)" e `held=['S1']`, coerente con il combiner che somma il peso S1 congelato. Che INTC sia nel target S1 viene dal report del 22/09; oggi non è riverificato dal dossier.
- **Esposizione oggi**: 1 posizione S4 nel target con segnale fresco sotto gate (INTC), 0 uscite. 2 posizioni S4 fuori target con segnale sotto gate o a peso 0 (NVDA, COST), 2 uscite. F-089 conta 8 sedute distinte in `findings.json`.
- **Evidenza contraria**: se il finding fosse falso, INTC sarebbe stata segnata alle 17:22 e venduta alle 17:37, come NVDA (14:23 → 14:37 → 14:52). Il flag non c'è.
- **Non-occorrenza**: PANW, anch'essa S4 nel target, oggi riceve un segnale rialzista (+0,422) e non ha motivo d'uscire. MRVL ha solo un segnale stantio del 24/09, quindi il meccanismo "segnale fresco sotto gate" non si attiva.
- **Next evidence (read-only)**: invariato. Sulla finestra dal 20/08, per ogni posizione S4 dentro e fuori il target S1, contare i segnali freschi sotto gate e le SELL entro 2 cicli; un rapporto ~0 dentro e ~1 fuori conferma il meccanismo.
- **Costo**: **−9,44 $** (attribuita, controfattuale corto; negativo = restare ha reso più che uscire). Formula: qty × (close − prezzo al ciclo eleggibile) = 14,523678 × (116,03 − 115,38). Il titolo ha recuperato dopo le 17:07, quindi oggi il difetto non è costato. Il prezzo d'uscita con isteresi (17:37) non è nel dossier. Scartato come costo `actual_intraday_pnl_usd` intero (−67,46 $): include la perdita della mattina, quando nessun segnale fresco imponeva l'uscita.

### [F-013] NVDA venduta alle 14:52 su un −0,006 da un articolo su Anthropic e ricomprata alle 18:22 più in alto

- **Meccanismo e fonte**: §4. Campi:
  - `chiusure[NVDA]`: `exit_price` 229,123027, `pnl_net` +27,98, `drift_post_uscita` −1,74;
  - `ingressi[NVDA]`: `entry_price` 230,18, `qty` 6,399513, `mtm_eod` −8,45;
  - decisioni 48841 (SELL `[below_entry_gate]`, score −0,006, generato 14:23) e 50352 (BUY, +0,405 × 1,20 = 0,486).
  Il −0,006 viene da "Anthropic Claude's Claimed Breakthrough in Biology Faces a Major Question", un articolo che non riguarda Nvidia. Senza banda fra gate d'ingresso (0,30) e uscita (0), il segnale debole chiude la posizione. Il rientro avviene 3,5 ore dopo su una notizia vera (riacquisto azioni record).
- **Esposizione oggi**: 2 uscite S4 `below_entry_gate`/`fallback_filtered`; 1 seguita da un rientro sullo stesso simbolo in seduta. F-013 conta 27 sedute distinte in `findings.json`.
- **Evidenza contraria**: con una banda d'uscita, un −0,006 non avrebbe chiuso NVDA. Oppure il rientro sarebbe avvenuto sotto il prezzo d'uscita, rendendo il round-trip favorevole. Il rientro è invece 1,06 $ per azione più in alto.
- **Non-occorrenza**: COST esce su un fallback a peso 0 e non rientra (16 righe `OBSERVE_LATE_ENTRY`, 3 `SKIP_FALLBACK`); nessun altro round-trip in seduta.
- **Next evidence (read-only)**: invariato. Sulla finestra, per ogni SELL `below_entry_gate` seguita da un BUY sullo stesso simbolo in seduta, sommare qty_rientro × (prezzo_rientro − prezzo_uscita) col segno; separare i casi in cui la SELL nasce da una riga fan-out.
- **Costo**: **6,76 $** (attribuita). Formula: qty_rientro × (prezzo_rientro − prezzo_uscita) = 6,399513 × (230,18 − 229,123027). Commissioni escluse; il dossier non le separa. Scartato come costo il `mtm_eod` del rientro (−8,45 $): include il calo dopo le 18:22, che avrebbe colpito anche la posizione mai venduta (−1,74 $ di `drift_post_uscita` sulla quota originale).

### [F-059] COST liquidata alle 14:22 da una lettura FinBERT fallback +0,040, esclusa dal ranking e quindi a peso 0

- **Meccanismo e fonte**: §4. Decisione 48626: "[fallback_filtered] S4 signal excluded from the ranking as FinBERT fallback, #108 (age=0.4h … score=+0.040): weight 0.0%, position closed". `chiusure[COST]`: `pnl_net` +4,74, `drift_post_uscita` −3,19. Il log segna COST in uscita alle 14:07. Un segnale fallback, che non può comprare, liquida la posizione perché sostituisce il segnale d'ingresso e prende peso 0. Il segnale è persino positivo.
- **Esposizione oggi**: 1 uscita S4 su 2 avviene su una lettura fallback. F-059 conta 6 sedute distinte in `findings.json`.
- **Evidenza contraria**: se l'uscita richiedesse la stessa confidenza dell'ingresso, il +0,040 fallback sarebbe ignorato e COST resterebbe a libro: a peso 0 la porta solo una lettura che il ranking stesso rifiuta.
- **Non-occorrenza**: AMD (S1) riceve un fallback +0,18 alle 16:07 e non esce, perché S1 non applica la regola S4. MRVL ha un segnale fallback stantio del 24/09 e non è liquidata.
- **Next evidence (read-only)**: contare sulla finestra le SELL `fallback_filtered` e confrontarne la somma `drift_post_uscita` con le SELL su lettura ensemble; un segno sistematico deciderebbe se l'asimmetria costa.
- **Costo**: **−3,19 $** (misurata; negativo = l'uscita ha evitato una perdita). Formula: `drift_post_uscita` = qty × (close − exit) = 1,612325 × (922,92 − 924,90). Il meccanismo si è visto, il danno no. Scartato come costo il `pnl_net` +4,74 $: è il guadagno del trade, non l'effetto della regola.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli, dal più alto al più basso)

| | | | |
|---|---|---|---|
| PANW +4,63% | PG +1,91% | NKE +1,79% | NVDA +1,68% |
| ASML +1,58% | PBR +1,37% | XOM +1,20% | CVX +0,94% |
| ABBV +0,73% | SHEL +0,72% | WMT +0,69% | BP +0,63% |
| TMUS +0,62% | TSM +0,50% | SBUX +0,43% | JD +0,38% |
| AMAT +0,36% | UNH +0,33% | XLV +0,33% | JNJ +0,27% |
| INFY +0,19% | PFE +0,17% | LLY +0,11% | MA +0,11% |
| V +0,10% | XLE +0,10% | TXN +0,09% | CSCO +0,04% |
| COST +0,02% | ROKU −0,01% | MMM −0,04% | MRK −0,06% |
| VALE −0,15% | RIO −0,16% | CAT −0,20% | NVO −0,23% |
| AZN −0,26% | GOOGL −0,34% | BIDU −0,41% | BRK.B −0,47% |
| DIS −0,53% | CMCSA −0,55% | SAP −0,65% | IWM −0,69% |
| SPY −0,74% | AAPL −0,78% | WDC −0,78% | AXP −0,83% |
| VZ −0,85% | XLK −0,89% | BABA −0,89% | AVGO −0,92% |
| SONY −0,93% | QQQ −1,07% | TM −1,07% | HD −1,13% |
| ERIC −1,15% | PLTR −1,15% | XLF −1,19% | MCD −1,23% |
| DB −1,34% | MSFT −1,35% | MS −1,36% | AMZN −1,41% |
| JPM −1,89% | T −1,89% | ADBE −1,89% | GS −2,05% |
| SOXX −2,08% | UBS −2,11% | IBM −2,15% | SPCX −2,16% |
| BAC −2,17% | C −2,21% | SNOW −2,33% | GM −2,41% |
| HOOD −2,46% | F −2,60% | NOK −2,60% | WFC −2,60% |
| MU −2,61% | NFLX −2,69% | GE −2,70% | CRM −2,88% |
| NOW −3,07% | ORCL −3,28% | DELL −3,46% | AMD −3,61% |
| MRVL −3,83% | TSLA −3,94% | RDDT −4,51% | META −4,79% |
| INTC −5,67% | BA −6,91% | QCOM −7,17% | ARM −8,70% |

Mover |r| ≥ 3%: 13 (1 su, 12 giù). `simboli_senza_dati`=[].

### (b) Checklist degli altri finding toccati

- [F-001] supported — `watchlist_zero_news` 34/96. Effective-timely 49/96; 3 posizioni cieche (2.548,06 $); 4 mover NO_NEWS, di cui 2 detenuti (MRVL, DELL). Migliora rispetto al 25/09 (40/96).
- [F-005] supported — Telegram risponde 400 Bad Request alle 04:00 e alle 14:07 (log worker).
- [F-011] supported — SELL `signal_id` 0/2 (`decision_signal_id_coverage.regressions`=["SELL"]).
- [F-012] supported — `mapping_fanout_extra` 102 su 250 righe; `quota_righe_fanout` dei candidati 0,56; la SELL NVDA nasce da un articolo non su Nvidia.
- [F-018] supported — il bot token Telegram compare in chiaro negli URL httpx del log worker (non riportato qui).
- [F-021] supported — primo ciclo portfolio con decisioni alle 14:07 UTC, apertura EDT alle 13:30.
- [F-023] supported (parziale) — la SELL NVDA usa il segnale più recente (−0,006), ma il segnale precedente non era sopra gate. L'aggancio primario è F-013.
- [F-025] supported — MRVL (S4) è detenuta su un segnale del 24/09 e, dopo le 14:52, è assente dalle decisioni senza uscita (−49,40 $).
- [F-030] not_exposed — l'unico ingresso (NVDA) ha `quota_movimento_precedente_al_segnale` −0,48 con `denominatore_degenere`=true: non interpretabile.
- [F-031] supported — 84 intenti `SKIP_PYRAMIDING` (WDC 24, ABBV 22, XLE 11, PANW 10, AMD 8, NVDA 7, XOM 2).
- [F-040] supported — BA −0,409 non-fallback sopra gate col segno giusto su un mover −6,91%: solo `RANK_LONG_ONLY` (6 intenti); anche SNOW −0,378 (8). NKE −0,321 è `RANK_LONG_ONLY` ma il titolo sale (+1,79%).
- [F-043] supported — l'unico segnale non-fallback sopra gate che produce un ordine (NVDA +0,405) è rialzista; NVDA chiude +1,68% ma sotto il prezzo d'ingresso.
- [F-048] supported — NOK trade 314 a `qty_open` 0 in `snapshot_apertura`, ma ancora contata fra le posizioni cieche.
- [F-053] supported — Alpaca portfolio history 1D timbra la seduta del 28/09 a 2026-09-29T00:00Z con 109.984,27, lo stesso valore della seduta del 25/09. La serie 1H dà 109.764,58 alle 20:00Z, il valore usato nei candidati.
- [F-076] supported — `testo_scorato` con `&#39;` (BA, META, ORCL, TSLA).
- [F-082] not_exposed — 0 soppressi su 86 intenti valutabili.

### (c) Casi di successo

- **PANW +4,63%**: detenuta S4 all'open, `actual_intraday_pnl_usd` **+83,26 $** (residuo beta-1 +88,48 $). Era il mover in calo del 25/09 che non era uscito (F-089): oggi restare ha reso.
- **NVDA (trade 1032)**: uscita a `pnl_net` **+27,98 $** dopo circa 70 ore di tenuta, sopra il close (`drift_post_uscita` −1,74 $). Il rientro successivo è il costo del §8 (F-013).
