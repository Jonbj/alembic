# Alpha Miss Report — 2026-09-25

Contratto `alpha_miss_prompt_v2` · dossier `docs/evidence/dossier/2026-09-25.json` (`schema_version` 3.1, generato 2026-10-02T08:00:34Z, prezzi Alpaca SIP `adjustment=all`). Soglia mover `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30.

## 1. Decision card

1. **Un solo miss d'ingresso, sotto gate: QCOM +3,97%**, `max_score_own` +0,174 ("What Is Going on With Qualcomm Stock on Friday?", 17:15, a movimento quasi finito). Con ingresso al ciclo eleggibile `net_opportunity_usd` sarebbe stato **−14,92 $**: il miss non è costato. MSFT +3,66% è stato catturato (S4, `pnl_net` +11,27 $).
2. **INTC −3,45% e PANW −3,89%, entrambe S4 a libro, non escono**: alle 17:35 ricevono un segnale fresco 0,000 e restano 11 cicli in `SKIP_THRESHOLD` senza flag d'uscita. ARM, HOOD e MSFT, sulla stessa regola, escono. Insieme valgono `actual_intraday_pnl_usd` **−106,80 $** (−55,63 e −51,17), il peggior contributo del libro (F-089).
3. **Realizzato −17,07 $, tutto S4** (ARM −29,19, HOOD +0,84, MSFT +11,27). Tutte e tre le uscite partono da un segnale più recente nato da un articolo fan-out. Il loro `drift_post_uscita` netto è −23,26 $: oggi le uscite hanno evitato perdite.

## 2. Stato carta

Fonte: `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18T10:14+02:00). I cumulati si fermano al 17/09 e non includono le sedute dal 18/09 a questa.

- Giorno **30/40** della finestra di osservazione (inizio 2026-08-03, `minimo_giorni`=40).
- Quota NO_NEWS dominante **13/30 = 43,3%**, sotto la soglia carta 0,60 (`superata_soglia`=false).
- S4 economico cumulato **−696,33 $** contro la banda ±200 $: **fuori banda** (`within`=false).
- `docs/evidence/longitudinal_panels.json` **non esiste**. I denominatori del §8 sono contati dalle occorrenze di `findings.json` (sedute distinte) e dichiarati come tali.

## 3. Miss del giorno

Il dossier ha 2 candidati in `candidati_miss`. Legacy `aggregati.cause_del_giorno` (invariato, vincolo #288): {"BELOW_GATE":2}, `dominante`="BELOW_GATE", `quota_righe_fanout` 0,57. Come nei report precedenti, dove l'asse `actionability` di `funnel_v2` e il campo grezzo `causa` divergono prevale il primo. `funnel_v2.conteggi_pipeline`={"BELOW_GATE":1,"CAUGHT":1}: nessun candidato ha uno stadio oltre il gate né una guardia che l'abbia bloccato, quindi **oggi nessun FILTERED**.

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| QCOM | +3,97% | **THIN_NEUTRAL** | `funnel_v2.righe[QCOM].pipeline`="BELOW_GATE", `evidence.score_firmato` +0,174 < `soglia_gate` 0,30, segno giusto. Due righe: un fan-out delle 15:29 (+0,0175, TAG_UNCONFIRMED, "Akamai, Atlas Energy Solutions, People And Other Big Stocks Moving Higher On Friday") e l'issuer-specific delle 17:15 (+0,174) che riassume la settimana: nuovi Snapdragon AI, estensione dell'accordo brevetti con Apple. Entrambe CONCURRENT. Al ciclo eleggibile (17:22) il titolo era a 204,81 contro il close di 201,97. `opportunity_v2`: gross 87,32 $, accessible −13,69 $, **net −14,92 $**. Intenti: 14 `SKIP_ENTRY_GATE`, 10 `SKIP_ENTRY_FRESHNESS`. Il log mette QCOM in `SHADOW_LATE_ENTRY` (percentile 0,92 ≥ 0,75). |
| META | −3,33% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[META].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only"; legacy `causa`="BELOW_GATE". `max_score_own` +0,2625, di segno opposto al movimento ("TD Cowen Maintains Buy on Meta Platforms, Raises Price Target to $865", 14:26). L'unico issuer-specific ribassista è "Jury Finds Meta Platforms Misled New Mexico Consumers In Cambridge Analytica Trial" (17:28, −0,2025). Intenti: 24 `SKIP_ENTRY_GATE`. `gross_opportunity_usd` 73,36 $, `accessible`=0. Un ribasso non detenuto non si cattura long-only. |

**Conteggi**: NO_NEWS 0 · THIN_NEUTRAL 1 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 1. Somma `gross_opportunity_usd` (legacy `costo_usd`) 160,68 $ (QCOM 87,32 + META 73,36). `net_opportunity_usd` è −14,92 $ e 0, `avoidable_miss_count`=0.

### Titoli catturati e mover detenuti all'open (4 su 6)

| Simbolo | Return% | Posizione | Esito di seduta |
|---|---:|---|---|
| MSFT | +3,66% | S4, ingresso del giorno (trade 1031) | `pipeline`="CAUGHT". Entrata alle 14:37 @514,00 sul segnale GDELT +0,31, "Microsoft Shares Jump 3.15% as Broader Market Rally Builds on Stifel's Recent Buy Upgrade". Il titolo della riga *è* il movimento: `quota_movimento_precedente_al_segnale` 0,87. Uscita alle 16:52 @518,00, `pnl_net` **+11,27 $**, `drift_post_uscita` −5,29 $ (uscita buona). `eod_net_pnl` del funnel +5,99 $. |
| DELL | +5,01% | S1, 507,78 $ (trade 293) | PASSIVE_EXPOSURE (`held_rising`), `actual_intraday_pnl_usd` **+15,43 $** (residuo beta-1 +12,58). Nessuna riga spiega il movimento: "Why Is Dell Stock Surging on Friday?" (+0,07) parla di rimbalzo dopo −4,90% in cinque sedute. |
| INTC | −3,45% | S4, 1.842,04 $ (trade 1007) | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` 0,000), **−55,63 $** (residuo −65,98). Righe: BofA "Everyone Bought Nvidia for AI: Now AMD Could Win the $211 Billion CPU Race" (−0,24, fallback, `SKIP_FALLBACK`) e un fan-out "10 Information Technology Stocks With Whale Alerts" (0,000, 17:35). Nessuna SELL (§8, F-089). |
| PANW | −3,89% | S4, 1.503,73 $ (trade 1001) | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` 0,000), **−51,17 $** (residuo −56,86). Unica riga lo stesso fan-out "Whale Alerts" (0,000, 17:35). Fino alle 17:22 il segnale stantio è preservato da FIX-D, poi 11 `SKIP_THRESHOLD` senza SELL (§8). |

KPI `funnel_v2.kpi`:
- `held_at_open_rate` 3/6;
- `active_signal_recall` 1/2;
- `execution_conversion_rate` 1/1;
- `profitable_capture_rate` 1/2;
- `exit_signal_recall` **0/2**, `exit_conversion_rate` null (0/0).

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["ARM","HOOD","MSFT","NVDA","COST"],"chiusure":["ARM","HOOD","MSFT"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | ARM | S4 | 14:07 | $321.9500 | 4.6203 | — | percentile 77.08%; denominatore intraday valido |
| IN | HOOD | S4 | 14:22 | $118.6777 | 12.5315 | — | percentile 26.26%; denominatore intraday valido |
| IN | MSFT | S4 | 14:37 | $514.0000 | 2.8959 | — | percentile 75.62%; denominatore intraday valido |
| IN | NVDA | S4 | 16:52 | $224.8421 | 6.6064 | — | percentile 44.90%; denominatore intraday degenere: quota non interpretabile |
| IN | COST | S4 | 17:52 | $921.4520 | 1.6123 | — | percentile 91.23%; denominatore intraday valido |
| OUT | ARM | S4 | — | $315.8100 | 4.6203 | −$29.19 | hold_minimum_expiry |
| OUT | HOOD | S4 | — | $118.8100 | 12.5315 | +$0.84 | hold_minimum_expiry |
| OUT | MSFT | S4 | — | $517.9965 | 2.8959 | +$11.27 | portfolio_sell |
<!-- alpha-miss-book:end -->

Cinque ingressi e tre chiusure, tutti S4.

- **Ingressi**:
  - ARM 14:07 @321,95, sul +0,3225 "Arm Stock Rises on Possible Continued Momentum From Meta's Muse AI Launch". Pubblicato 12:14, ingerito 13:40. `entry_percentile` 0,77, `quota_nel_gap` 3,06: il movimento della notizia era già nel gap d'apertura.
  - HOOD 14:22 @118,68, su un articolo crypto multi-ticker (+0,3225, "XRP, Solana Surge 22% After Clarity Act Failure…").
  - MSFT 14:37 @514,00 (§3).
  - NVDA 16:52 @224,84, sul +0,265 "Nvidia GPU Demand Is So Extreme…". Passa il gate solo grazie a velocity 1,20 (0,318). `denominatore_degenere`=true.
  - COST 17:52 @921,45, sul +0,326 ("Costco Save Members $3.2 Billion for Gas…") dopo nove tagli di target price scorati in fallback. `entry_percentile` 0,91.
  - Somma `mtm_eod` sui cinque: −34,78 $, di cui ARM −53,73.
- **Chiusure**, tutte `[below_entry_gate]` in `execution_decisions` (il dossier riporta ARM e HOOD come `hold_minimum_expiry`, MSFT come `portfolio_sell`):
  - ARM 15:52 su +0,035 (14:49, articolo BofA su AMD);
  - HOOD 16:07 su +0,021 (14:28, "Forget Bitcoin, XRP: These 2 Coins Could Explode This Weekend");
  - MSFT 16:52 su +0,165 (16:43, articolo SemiAnalysis su NVDA).
  - Realizzato **−17,07 $**.
- **Integrità**: le 3 SELL non hanno `signal_id` (`decision_signal_id_coverage.regressions`=["SELL"]). Guardia di contraddizione: 0 soppressi su 70 intenti tradabili. `invariante_rank_ranking_score`: 0 violazioni su 70. Degli intenti tradabili 39 sono `SKIP_PYRAMIDING` (AMD 21, detenuta da S1; WDC 18), 26 `SKIP_IDEMPOTENCY` e 5 `SUBMITTED`.

## 5. Cecita' lato uscita

`copertura_uscita` conta 43 posizioni, con `n_indeterminati`=**0**: nessuna riga ha `cieco_lato_uscita: null`. Tre posizioni sono cieche, tutte ancora aperte:

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| AMAT | S1 | **−18,32%** | +2,27% | 2 | `alpaca_benzinga`, `gdelt_gkg` | 415,68 $ |
| VALE | S1 | −7,04% | +0,37% | 7 | `alpaca_benzinga` | 721,38 $ |
| CSCO | S4 | −4,29% | −0,25% | 3 | `alpaca_benzinga`, `gdelt_gkg` | 1.821,35 $ |

Nessuna è uscita in seduta. `ritorno_da_ingresso` è la perdita dall'ingresso al close, `ritorno_seduta` il solo movimento del 25/09. Rispetto al 24/09 entra AMAT ed esce UBS (1,05 $ di P&L di seduta, ha righe oggi). Nozionale cieco **2.958,41 $** (3.184,87 $ il 24/09). Aggregato: 16 posizioni a copertura grezza nulla, 28 a copertura effective-timely nulla, 9 in perdita marcata.

INTC e PANW non sono cieche (hanno righe), ma il loro unico segnale fresco è uno 0,000 da fan-out: sono il caso `EXIT_WRONG_SIGN` del §3, non questo.

## 6. Backstop NO_NEWS

`no_news_backstop.population`: 40 simboli a zero righe `news_log`, **0 mover** e 40 non-mover (`return_missing`=0).

### 6a. Marker calendario

Nessun mover NO_NEWS, quindi nessuna riga `observed_catalysts` da riportare. `mover_observed` 0/0 e `non_mover_observed` 0/40: nessun marker `CALENDAR` sui simboli a zero news. `calendario_earnings.status`="OBSERVED", `simboli_flaggati`=[].

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false. Il volume di seduta e l'etichetta mover si conoscono solo al close, quindi nessuno di questi valori era disponibile prima del movimento. Non si fissano soglie né si stimano false-positive rate (#451).

- Mediana della sorpresa di volume sui mover a zero news: **null** (n=0). Sui non-mover: **−25,10%** (n=40).

### 6c. Copertura raw di `news_log` per settore (tutti i settori)

Copertura **raw**, distinta dalla effective-timely di `copertura_articoli.per_settore` (35/96, 36,5% sulla watchlist).

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news | calendario su zero news |
|---|---:|---:|---:|---:|
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| industrials | 4/4 | 100,0% | 0 | 0 |
| healthcare | 6/9 | 66,7% | 0 | 0 |
| semis | 10/15 | 66,7% | 0 | 0 |
| financials | 9/14 | 64,3% | 0 | 0 |
| media | 3/5 | 60,0% | 0 | 0 |
| tech | 11/21 | 52,4% | 0 | 0 |
| energy | 3/6 | 50,0% | 0 | 0 |
| consumer | 5/11 | 45,5% | 0 | 0 |
| telecom | 1/5 | **20,0%** | 0 | 0 |
| materials | 0/2 | **0,0%** | 0 | 0 |

In totale 56/96 simboli hanno almeno una riga (`watchlist_zero_news`=40; erano 31 il 24/09).

### 6d. Attribuzione fonti per ticker (#511 passo 2)

Per tutti i 40 ticker con `articoli_unici`=0 vale `fonti_osservate`={} e `articoli_unici_giorno` = `effective_timely_articles_giorno` = 0 (da `blind_set.per_ticker`). Tra parentesi `sedute_consecutive_zero_articoli`:

ADBE (1), AMAT (2), ASML (1), AXP (2), AZN (3), BABA (1), BIDU (1), BP (1), CRM (2), CSCO (3), CVX (1), DB (1), ERIC (3), GM (1), HD (10), IBM (1), JD (6), MA (3), MCD (1), MRK (1), MRVL (1), NOK (1), PFE (3), PG (5), RDDT (5), RIO (1), ROKU (1), SAP (8), SHEL (1), SNOW (10), SONY (2), SOXX (1), T (2), TM (1), TXN (3), V (2), VALE (7), VZ (2), WFC (3), WMT (1).

`ticker_allerta_zero_articoli` (≥5 sedute): HD, JD, PG, RDDT, SAP, SNOW, VALE.

Fonte presente ma non utile: nei 21 casi seguenti la fonte `alpaca_benzinga` ha reso N righe, ma nessuna effective-timely. SPY 24, AMZN 6, AAPL 3, CAT 3, e poi 2 righe ciascuno HOOD, INTC, IWM, JPM, QQQ, XOM. Una riga ciascuno ABBV, AVGO, BAC, C, DIS, GE, NFLX, PANW, TMUS, UNH, XLE.

Per fonte: `alpaca_benzinga` 103 articoli unici, di cui 57 effective-timely (55,3%); `gdelt_gkg` 10 su 10. La scelta dei connettori resta all'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Indici in rialzo moderato (SPY +0,54%, QQQ +0,46%, `dispersione_sigma` 1,48%), con hardware/semis su e software giù. Su tre nomi, inversione dei movimenti del 24/09.**

- **Rialzisti**: DELL +5,01%, QCOM +3,97%, MSFT +3,66% (rinnovo di Copilot), TXN +2,74%, AMAT +2,27% (SOXX +1,17%). COST +2,93% sui risultati del trimestre, nonostante una raffica di tagli di target price. Banche europee: DB +2,67%, UBS +2,50%.
- **Ribassisti**: PANW −3,89%, INTC −3,45%, META −3,33% (verdetto della giuria nel New Mexico alle 17:28). Software debole senza mover: CRM −1,76%, ORCL −1,75%, NOW −1,57%, PLTR −1,52%, ADBE −1,45%.
- **Rispetto al 24/09**: META (+4,50% → −3,33%), INTC (+3,91% → −3,45%) e DELL (−2,51% → +5,01%) invertono il movimento della seduta precedente.

La divisione hardware/software è una lettura dei rendimenti, non una causa verificata: nessuna riga la collega esplicitamente. Oltre a questo il pattern non è chiaro.

## 8. Segnalazioni

Tre finding esposti oggi, tutti lato uscita o copertura. I denominatori sono contati dalle occorrenze di `findings.json` (sedute distinte), perché `longitudinal_panels.json` non esiste.

### [F-089] INTC e PANW, S4 nel target S1 congelato, ricevono un segnale fresco 0,000 alle 17:35 e restano a libro per 11 cicli; ARM, HOOD e MSFT, fuori target, escono sulla stessa regola

- **Meccanismo e fonte**: §3 (catturati) e §4. Campi del dossier:
  - `funnel_v2.righe[INTC|PANW].pipeline_uscita`="EXIT_WRONG_SIGN", `evidence_uscita.score_firmato` 0,000;
  - `timeline` segnali 12802 (INTC) e 12805 (PANW): `eligible_cycle_at` 17:37, prezzo 124,2356 e 378,525;
  - `snapshot_apertura`: INTC −55,63 $, PANW −51,17 $.
  In `execution_decisions` ci sono 11 righe `SKIP_THRESHOLD` per simbolo ("score 0.000 < feedback threshold 0.300", 17:37→19:52). Nessuna riga "Exit hysteresis … flagged for exit" li nomina nel log worker. Le tre posizioni fuori target vengono invece segnate un ciclo dopo il segnale sotto gate ed escono al successivo: ARM 14:49→15:37→15:52, HOOD 14:28→15:52→16:07, MSFT →16:37→16:52. Lo stesso log mostra "S1: rebalance gate closed — holding 43 position(s)" e "held=['S1'] merged_weights=45". È coerente con il combiner che somma il peso S1 congelato. Che INTC e PANW siano nel target S1 viene dal report del 22/09 (§8 F-089); oggi non è riverificato dal dossier.
- **Esposizione oggi**: 2 posizioni S4 su 2 dentro il target S1 con segnale fresco sotto gate; 3 su 3 fuori target uscite. F-089 conta 6 sedute distinte in `findings.json`.
- **Evidenza contraria**: se il finding fosse falso, INTC e PANW sarebbero state segnate alle 17:52 e vendute alle 18:07 come le tre fuori target. Oppure FIX-D le avrebbe preservate esplicitamente come stantie senza controsegnale. Non c'è né il flag né la preservazione: PANW esce dalla lista FIX-D proprio dopo le 17:22.
- **Non-occorrenza**: CSCO, anch'essa S4 nel target, oggi non ha righe (3 sedute di fila), quindi il meccanismo "segnale fresco sotto gate senza SELL" non si attiva. Le uscite fuori target funzionano alla regola.
- **Next evidence (read-only)**: invariato. Sulla finestra dal 20/08, per ogni posizione S4 dentro e fuori il target S1, contare i segnali freschi sotto gate e le SELL entro 2 cicli; un rapporto ~0 dentro e ~1 fuori conferma il meccanismo indipendentemente dal P&L.
- **Costo**: **33,74 $** (attribuita, controfattuale corto). Formula: Σ qty × (prezzo al ciclo eleggibile del segnale − close) = 14,523678 × (124,2356 − 122,96) + 3,876202 × (378,525 − 374,60) = 18,53 + 15,21. È un'approssimazione per eccesso del prezzo d'uscita con isteresi (vendita alle 18:07), il cui prezzo di barra non è nel dossier. Scartato come costo `actual_intraday_pnl_usd` intero (−106,80 $): include la perdita della mattina, quando nessun segnale fresco imponeva l'uscita.

### [F-023] Le tre uscite S4 di oggi partono tutte da un segnale più recente nato da un articolo su un'altra società

- **Meccanismo e fonte**: §4. Campi:
  - `chiusure[ARM|HOOD|MSFT]`: `drift_post_uscita` −25,37 / +7,39 / −5,29;
  - `execution_decisions` 46491, 46612, 46980 ("[below_entry_gate] … generated 14:49 / 14:28 / 16:43").
  Gli articoli che generano quei segnali:
  - ARM, +0,035: "Everyone Bought Nvidia for AI: Now AMD Could Win the $211 Billion CPU Race, Bank Of America Says";
  - HOOD, +0,021: "Forget Bitcoin, XRP: These 2 Coins Could Explode This Weekend" (su Chainlink e Hyperliquid);
  - MSFT, +0,165: "Nvidia GPU Demand Is So Extreme, Even Bad Cloud Infrastructure Is Selling".
  Ognuno sovrascrive un segnale d'ingresso più forte (+0,3225, +0,3225, +0,31). Tutti e tre sono positivi: la SELL non nasce da una notizia negativa.
- **Esposizione oggi**: 3 uscite S4 su 3. F-023 conta 17 sedute distinte in `findings.json`.
- **Evidenza contraria**: se S4 non leggesse solo l'ultimo segnale per simbolo, le SELL citerebbero un segnale ISSUER_SPECIFIC negativo o la scadenza a 4 h. Citano invece età 1,0 h, 1,6 h e 0,1 h, con score positivi da articoli fan-out.
- **Non-occorrenza**: NVDA e COST, entrate nel pomeriggio, non ricevono un segnale più recente prima del close e restano a libro.
- **Next evidence (read-only)**: invariato. Sulla finestra, contare le SELL S4 il cui ultimo segnale è fan-out mentre un segnale ISSUER_SPECIFIC più forte dello stesso simbolo è più recente di 4 h, e sommare qty × (close − exit) **col segno**: oggi il segno è a favore dell'uscita.
- **Costo**: **−23,26 $** (congetturale; negativo = le uscite hanno evitato perdite). Formula: Σ `drift_post_uscita` = 7,39 − 25,37 − 5,29. Il meccanismo si è visto, il danno no. Scartato riportare il solo HOOD (+7,39 $): sarebbe selezione delle uscite sfavorevoli.

### [F-001] Copertura watchlist peggiorata: 40/96 simboli a zero righe (31 il 24/09), 3 posizioni cieche lato uscita per 2.958 $

- **Meccanismo e fonte**: §5 e §6. Campi:
  - `mercato.watchlist_zero_news` 40;
  - `copertura_articoli.effective_timely_coverage` 35/96 (36,5%);
  - `no_news_backstop.per_sector`: materials 0/2, telecom 1/5;
  - `copertura_uscita.aggregato`: 3 cieche, `notional_cieco_usd` 2.958,41;
  - `blind_set.ticker_allerta_zero_articoli`: 7 ticker (HD e SNOW a 10 sedute, SAP a 8, VALE a 7).
  Il connettore WS è sottoscritto a tutti i 96 simboli (log `worker-news-stream`), quindi lo zero è resa della fonte, non configurazione.
- **Esposizione oggi**: 96 simboli, 43 posizioni. F-001 conta 38 sedute distinte in `findings.json`.
- **Evidenza contraria**: con una copertura adeguata la maggioranza della watchlist avrebbe almeno una riga effective-timely. Oggi ne ha 35/96.
- **Non-occorrenza**: nessun mover è a zero news (`population.movers` 0). La copertura bassa non ha prodotto miss NO_NEWS in questa seduta: i 6 mover avevano tutti righe.
- **Next evidence (read-only)**: serie giornaliera di `watchlist_zero_news` e della quota di mover NO_NEWS sulla finestra. Va letta tenendo conto della discontinuità alias del 24/09 (charter, #566), che tocca la rilevanza ma non il conteggio raw.
- **Costo**: **4,97 $** (congetturale). Formula: perdita di seduta delle posizioni cieche in perdita = |`passive_pnl_usd` CSCO| = 4,97 (AMAT +5,24 e VALE +2,65 sono guadagni e non compensano). Scartato il nozionale cieco (2.958 $) come costo: è esposizione, non perdita.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli, dal più alto al più basso)

| | | | |
|---|---|---|---|
| DELL +5,01% | QCOM +3,97% | MSFT +3,66% | COST +2,93% |
| TXN +2,74% | DB +2,67% | GM +2,56% | UBS +2,50% |
| SONY +2,44% | GE +2,29% | AMAT +2,27% | CAT +2,03% |
| TM +1,94% | C +1,65% | AAPL +1,53% | WDC +1,44% |
| JPM +1,33% | GS +1,32% | ARM +1,30% | SBUX +1,29% |
| ASML +1,24% | AZN +1,23% | MMM +1,21% | BAC +1,20% |
| SOXX +1,17% | MRVL +1,15% | AXP +1,06% | WFC +0,96% |
| PFE +0,92% | F +0,87% | XLK +0,80% | SAP +0,75% |
| AVGO +0,70% | BA +0,65% | SNOW +0,58% | XLF +0,57% |
| DIS +0,56% | SPY +0,54% | MRK +0,54% | XLV +0,49% |
| NVO +0,47% | QQQ +0,46% | GOOGL +0,46% | SPCX +0,44% |
| UNH +0,42% | PG +0,38% | VALE +0,37% | WMT +0,36% |
| HD +0,35% | MA +0,28% | NVDA +0,22% | AMD +0,22% |
| ERIC +0,21% | JNJ +0,20% | SHEL +0,19% | MU +0,16% |
| LLY +0,13% | AMZN +0,12% | IWM +0,11% | RIO +0,10% |
| BRK.B +0,06% | TMUS +0,05% | INFY +0,00% | MS −0,01% |
| TSM −0,12% | V −0,16% | MCD −0,22% | CSCO −0,25% |
| T −0,28% | ABBV −0,29% | NOK −0,38% | ROKU −0,42% |
| VZ −0,51% | CVX −0,58% | BP −0,59% | NKE −0,67% |
| IBM −0,68% | NFLX −0,80% | BABA −0,80% | BIDU −0,85% |
| XLE −0,89% | JD −0,90% | XOM −0,96% | CMCSA −0,99% |
| HOOD −1,18% | ADBE −1,45% | PLTR −1,52% | TSLA −1,54% |
| NOW −1,57% | ORCL −1,75% | CRM −1,76% | RDDT −1,89% |
| PBR −2,26% | META −3,33% | INTC −3,45% | PANW −3,89% |

Mover |r| ≥ 3%: 6 (3 su, 3 giù). `simboli_senza_dati`=[].

### (b) Checklist degli altri finding toccati

- [F-008] supported (parziale) — le uscite di oggi nascono da articoli multi-ticker, ma lo score non è invertito (resta positivo): l'aggancio primario è F-023.
- [F-009] supported — QCOM +3,97% con segno giusto e `score_firmato` +0,174 < 0,30.
- [F-011] supported — SELL `signal_id` 0/3 (`decision_signal_id_coverage.regressions`=["SELL"]).
- [F-012] supported — `mapping_fanout_extra` 65 su 178 righe; `quota_righe_fanout` dei candidati 0,57; tutte e tre le uscite su fan-out.
- [F-013] contradicted (sul costo) — 3 SELL `below_entry_gate` con score positivi e nessun rientro in seduta. `drift_post_uscita` netto −23,26 $: oggi l'assenza di banda non è costata.
- [F-019] supported — nessuna riga `news_log` con `fetched_at` prima delle 13:33 UTC, mentre `raw_ingested_at` parte dalle 11:36. Le righe pre-open sono ingerite fra le 13:39 e le 13:57, con un ritardo mediano di 91 min (ARM 12:14→13:40, MSFT Reuters 12:07→13:39, COST Mizuho 12:17→13:43). Su ARM non è costato: il vincolo è stato il primo ciclo delle 14:07 (F-021).
- [F-021] supported — primo ciclo portfolio con decisioni alle 14:07 UTC (`guard_decisions` 45646), apertura EDT alle 13:30.
- [F-030] contradicted (parziale) — `quota_movimento_precedente_al_segnale` HOOD 1,32, MSFT 0,87, COST 0,96, ma `mtm_eod` positivo su tutti e tre (+9,05, +6,28, +2,12). La perdita del giorno è ARM, entrata nel gap (`quota_nel_gap` 3,06).
- [F-031] supported — 39 intenti `SKIP_PYRAMIDING` (AMD 21 detenuta da S1, WDC 18), 2 tracciati in `guard_decisions`. `counterfactual_return_1h`: WDC +1,03% e AMD −0,77% su circa 2.199 $.
- [F-043] contradicted — i segnali non-fallback sopra gate (ARM, HOOD, MSFT, COST; NVDA con velocity) sono rialzisti e i titoli chiudono in rialzo, salvo HOOD −1,18%.
- [F-048] supported — WDC trade 373 e NOK trade 314 a `qty_open` 0 in `snapshot_apertura` (`exit_fill_qty_exceeds_trade_qty`); WDC ha ancora intenti `SKIP_PYRAMIDING`, quindi risulta detenuta.
- [F-053] supported — Alpaca portfolio history timbra la seduta del 25/09 a 2026-09-26T00:00Z (equity 109.984,27).
- [F-059] not_exposed — nessuna uscita su lettura fallback oggi; INTC ha un fallback −0,24 che non la fa uscire.
- [F-076] supported — `testo_scorato`/titoli con `&#39;` su META, MSFT, ARM e DELL.
- [F-082] not_exposed — 0 soppressi su 70 intenti valutabili.

### (c) Casi di successo

- **MSFT +3,66%**: catturato dallo S4 alle 14:37, uscito alle 16:52 a `pnl_net` **+11,27 $**. Il close a 516,17 sta sotto l'uscita (`drift_post_uscita` −5,29 $), quindi anche il timing d'uscita è stato favorevole.
- **DELL +5,01%**: detenuta S1 all'open, `actual_intraday_pnl_usd` **+15,43 $** (residuo +12,58 $).
