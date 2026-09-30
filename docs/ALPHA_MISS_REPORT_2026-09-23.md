# Alpha Miss Report — 2026-09-23

Contratto `alpha_miss_prompt_v2` · dossier `docs/evidence/dossier/2026-09-23.json` (`schema_version` 3.1, generato 2026-09-30T08:00:32Z, prezzi Alpaca SIP `adjustment=all`). Soglia mover `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30.

## 1. Decision card

1. **Un solo miss azionabile, sotto gate: PLTR +3,68%.** Il segnale issuer-specifico del segno giusto è +0,14 (fallback), sotto il gate 0,30 (`funnel_v2.righe[PLTR].pipeline`="BELOW_GATE"). `net_opportunity_usd` = **25,95 $**. Gli altri 5 candidati sono ribassi non detenuti su un book long-only (`accessible_opportunity_usd`=0).
2. **BP +3,23%, detenuta da S1, ha un segnale S4 +0,375 sopra gate col segno giusto, bloccato 9 volte da `SKIP_PYRAMIDING`.** Il blocco colpisce 55 dei 77 intenti tradabili (71,4%); in `guard_decisions` ne sono tracciati solo 2.
3. **Realizzato −58,71 $, tutto S4** (BABA −68,67, META +9,96). Entrambe le uscite arrivano al primo ciclo utile (14:22) su `below_entry_gate`. META viene ricomprata alle 18:07 a 750,15, cioè 5,94 $/azione sopra l'uscita (744,21).

## 2. Stato carta

Fonte: `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18T10:14+02:00). I cumulati si fermano al 17/09: non includono né le sedute 18, 21 e 22/09 né questa.

- Giorno **30/40** della finestra di osservazione (inizio 2026-08-03, `minimo_giorni`=40).
- Quota NO_NEWS dominante **13/30 = 43,3%**, sotto la soglia carta 0,60.
- S4 economico cumulato **−696,33 $** contro la banda ±200 $: **fuori banda**.
- `docs/evidence/longitudinal_panels.json` **non esiste**: i denominatori del §8 sono contati dalle occorrenze di `findings.json` e dichiarati come tali.

## 3. Miss del giorno

Il dossier ha 6 candidati in `candidati_miss`. Legacy `aggregati.cause_del_giorno` (invariato per il vincolo #288): {"NO_NEWS":2, "BELOW_GATE":2, "NON_CLASSIFICATO":2}, `dominante`=null. Come nei report precedenti, dove l'asse `actionability` di `funnel_v2` e il campo grezzo `causa` divergono prevale il primo. `funnel_v2.conteggi_pipeline`={"BELOW_GATE":1}: nessun candidato ha uno stadio oltre il gate né una guardia che lo abbia bloccato, quindi **oggi nessun FILTERED è possibile**.

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| MCD | −4,81% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[MCD].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only"; legacy `causa_legacy`="NON_CLASSIFICATO". Il segnale c'era, del segno giusto e sopra gate in valore assoluto: `max_score_own`=−0,405 (17:57, "McDonald's Admits It Is 'Falling Short' On Execution"), 2 intenti `RANK_LONG_ONLY`. Ma la prima riga (14:37, −0,18) arriva a mercato aperto e le successive ("Stock Slumps to 4-Year Lows", 18:16) sono retrospettive. Un ribasso non detenuto non si cattura long-only. |
| DB | −4,50% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[DB].actionability`="NON_ACTIONABLE"; legacy `causa`="NO_NEWS" (`news_count`=0, `segnali`=[]). |
| SPCX | −4,11% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[SPCX].actionability`="NON_ACTIONABLE"; legacy `causa`="BELOW_GATE" (`max_score_own`=−0,165). Nessuna delle 3 righe spiega il calo: Starlink contro l'alternativa Gogo, Fitch Tesla contro SpaceX, Meta Muse contro X. |
| PLTR | +3,68% | **THIN_NEUTRAL** | `funnel_v2.righe[PLTR].pipeline`="BELOW_GATE", `evidence.score_firmato`=+0,14 < `soglia_gate` 0,30; `actionability`="ENTRY_OPPORTUNITY". Legacy `causa_legacy`="NON_CLASSIFICATO". L'unica riga rialzista issuer-specifica è "Palantir Stock Flips $188 Into Support, Eyes $200 Next" (16:17, fallback), cioè tecnica e a movimento avvenuto. Il `max_score_own` −0,18 viene da un pezzo su **Micron** ("Micron Faces Short Pressure Ahead Earnings…") marcato ISSUER_SPECIFIC su PLTR; il −0,3175 da un roundup fan-out ("Nasdaq 100 Slips…"). Intenti: 14 `SKIP_ENTRY_GATE`, 9 `SKIP_ENTRY_FRESHNESS`, 1 `SKIP_FALLBACK`. `net_opportunity_usd` 25,95 $ (ingresso 189,45 alla prima barra eleggibile delle 14:25, costi 1,23 $). |
| NVO | −3,12% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[NVO].actionability`="NON_ACTIONABLE"; legacy `causa`="NO_NEWS" (`news_count`=0). |
| ORCL | −3,11% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[ORCL].actionability`="NON_ACTIONABLE"; legacy `causa`="BELOW_GATE" (`max_score_own`=−0,18, "Oracle unveils oncology EHR as shares slip on launch day", GDELT 18:47). |

**Conteggi**: NO_NEWS 0 · THIN_NEUTRAL 1 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 5. La somma di `gross_opportunity_usd` (legacy `costo_usd`) è 513,11 $. `net_opportunity_usd` è diverso da zero solo su PLTR (25,95 $); `avoidable_miss_count`=1.

### Titoli catturati (mover detenuti all'open: 4 su 10)

Nessun mover è stato comprato in giornata: gli ingressi del giorno (BA, META) non sono mover. Il P&L viene da `snapshot_apertura.actual_intraday_pnl_usd`.

| Simbolo | Return% | Detenuto da (nozionale all'open) | Esito di seduta |
|---|---:|---|---|
| PANW | +5,00% | S4, 1.472,18 $ | PASSIVE_EXPOSURE, **+52,33 $** (residuo beta-1 +62,21 $). |
| BP | +3,23% | S1, 831,25 $ | PASSIVE_EXPOSURE, **+12,71 $**. Il segnale S4 +0,375 ("BP Stock Gains Amid JPMorgan Upgrade, Oil Rally", 17:46) resta bloccato da `SKIP_PYRAMIDING` (§8, F-031). |
| GOOGL | −3,80% | S1, 866,55 $ | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` +0,175, annuncio YouTube, fallback). **−29,80 $**. La riga negativa issuer-specifica ("Alphabet Stock Dips…", −0,22, 16:53) è retrospettiva. |
| BABA | −4,74% | S4, 1.382,25 $ | EXIT_RISK → "EXITED" alle 14:22 @110,86. `pnl_net` **−68,67 $** (dall'ingresso del 22/09 a 116,36); `actual_intraday_pnl_usd` −14,07 $, `exit_active_effect_usd` +0,74 $ (l'uscita ha evitato una piccola perdita aggiuntiva). |

KPI: `held_at_open_rate` 4/10, `exit_signal_recall` 1/2, `exit_conversion_rate` 1/1, `active_signal_recall` 0/1, `profitable_capture_rate` 0/1.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["BA","META"],"chiusure":["META","BABA"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | BA | S4 | 16:22 | $201.8600 | 7.1904 | — | percentile 63.79%; denominatore intraday valido |
| IN | META | S4 | 18:07 | $750.1520 | 1.9350 | — | percentile 43.63%; denominatore intraday degenere: quota non interpretabile |
| OUT | META | S4 | — | $744.2100 | 1.9489 | +$9.96 | portfolio_sell |
| OUT | BABA | S4 | — | $110.8600 | 12.3415 | −$68.67 | portfolio_sell |
<!-- alpha-miss-book:end -->

Due ingressi S4, entrambi appena sopra il gate (+0,315) e dopo il movimento:

- **BA** alle 16:22 (labor deal + ordine Turkish Airlines): `quota_movimento_precedente_al_segnale` 1,99, `entry_percentile` 0,64, `mtm_eod` −13,88 $.
- **META** alle 18:07 (analista rialzista su Muse): `denominatore_degenere`=true, `mtm_eod` −11,71 $.

Due chiusure S4, entrambe al ciclo delle 14:22 dopo il flag "Exit hysteresis (2 cycles)" delle 14:07 (log worker), con `exit_reason` portfolio_sell:

- **BABA**: `execution_decisions` "[below_entry_gate] … generated 13:47, score=−0,007". La riga è un roundup pre-market che però cita esplicitamente BABA −3,4% pre-market. `pnl_net` −68,67 $, `drift_post_uscita` −0,74 $.
- **META**: "score=+0,101" su "What's Going On With Meta Platforms Stock Wednesday?". `pnl_net` +9,96 $, `drift_post_uscita` −0,21 $.

Realizzato −58,71 $. Le 2 SELL non hanno `signal_id` (`decision_signal_id_coverage.by_reason_code.SELL` 0/2, `regressions`=["SELL"]). Guardia di contraddizione: 0 soppressi su 77 intenti valutabili. `invariante_rank_ranking_score`: 0 violazioni su 77.

## 5. Cecita' lato uscita

`copertura_uscita` conta 46 posizioni, con `n_indeterminati`=**0**: nessuna riga ha `cieco_lato_uscita: null`. Tre posizioni sono cieche e tutte ancora aperte:

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| WDC | S4 | **−13,76%** | +1,96% | 2 | `alpaca_benzinga` | 158,54 $ |
| SBUX | S1 | −10,67% | −1,02% | 10 (troncato dalla finestra) | **vuota** | 619,61 $ |
| VALE | S1 | −5,60% | −2,61% | 5 | `alpaca_benzinga` | 732,51 $ |

Nessuna delle tre è uscita in seduta: `ritorno_da_ingresso` è la perdita dall'ingresso al close, `ritorno_seduta` il solo movimento del 23/09. Per SBUX, `fonti_osservate_finestra` vuota significa resa zero dei provider su tutta la finestra di 10 sedute, non fonte non configurata. WDC entra nella lista oggi (streak 2); AMAT ne esce, perché ha avuto 1 articolo. Aggregato: 20 posizioni a copertura grezza nulla, 28 a copertura effective-timely nulla, 11 in perdita marcata; nozionale cieco **1.510,66 $** (era 1.783,04 $ il 22/09).

## 6. Backstop NO_NEWS

`no_news_backstop.population`: 42 simboli a zero righe `news_log`, di cui 2 mover (DB, NVO) e 40 non-mover (`return_missing`=0).

### 6a. Marker calendario

| Simbolo | Return% | `observed_catalysts` | Calendario |
|---|---:|---|---|
| DB | −4,50% | `[]` | `NOT_OBSERVED` (FMP earnings-calendar e Alpaca Corporate Actions hanno risposto) |
| NVO | −3,12% | `[]` | `NOT_OBSERVED`, stesse fonti |

`mover_observed` 0/2, `non_mover_observed` 0/40: oggi nessun marker `CALENDAR`. `calendario_earnings.status`="OBSERVED", `simboli_flaggati`=[].

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false. Il volume di seduta e l'etichetta mover si conoscono solo al close, quindi nessuno di questi valori era disponibile prima del movimento. Qui non si fissano soglie né si stimano false-positive rate (la valutazione ex-ante è in #451).

- Mediana della sorpresa di volume: **+75,8%** sui mover a zero news (n=2), **−5,3%** sui non-mover (n=40).
- Per simbolo: DB +105,8% (`adv_ratio` 2,06), NVO +45,9%.

### 6c. Copertura raw di `news_log` per settore (tutti i settori)

Copertura **raw**, distinta dalla effective-timely di `copertura_articoli.per_settore` (oggi 40/96, 41,7% a livello di watchlist).

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news | calendario su zero news |
|---|---:|---:|---:|---:|
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| energy | 4/6 | 66,7% | 0 | 0 |
| semis | 10/15 | 66,7% | 0 | 0 |
| tech | 13/21 | 61,9% | 0 | 0 |
| consumer | 6/11 | 54,5% | 0 | 0 |
| financials | 7/14 | 50,0% | 1 (DB) | 0 |
| industrials | 2/4 | 50,0% | 0 | 0 |
| healthcare | 4/9 | 44,4% | 1 (NVO) | 0 |
| media | 2/5 | 40,0% | 0 | 0 |
| telecom | 2/5 | 40,0% | 0 | 0 |
| materials | 0/2 | **0,0%** | 0 | 0 |

In totale 54/96 simboli hanno almeno una riga (`watchlist_zero_news`=42, erano 45 il 22/09).

### 6d. Attribuzione fonti per ticker (#511 passo 2)

Per tutti i 42 ticker con `articoli_unici`=0, `fonti_osservate`={} e `articoli_unici_giorno` = `effective_timely_articles_giorno` = 0 (da `blind_set.per_ticker`). Tra parentesi `sedute_consecutive_zero_articoli`:

ADBE (7), ASML (2), AZN (1), BAC (4), BIDU (1), C (1), CAT (2), CMCSA (5), CSCO (1), CVX (2), DB (1), DELL (2), ERIC (1), F (3), HD (8), INFY (9), JD (4), JPM (1), MA (1), MMM (6), MRK (3), NOK (1), NOW (2), NVO (1), PFE (1), PG (3), QCOM (1), RDDT (3), RIO (8), ROKU (10), SAP (6), SBUX (10), SNOW (8), TM (2), TMUS (2), TXN (1), UBS (1), UNH (1), VALE (5), WDC (2), WFC (1), XOM (2).

`ticker_allerta_zero_articoli` (≥5): ADBE, CMCSA, HD, INFY, MMM, RIO, ROKU, SAP, SBUX, SNOW, VALE.

Fonte presente ma non utile: in tutti i 14 casi la fonte `alpaca_benzinga` ha reso N righe, ma nessuna effective-timely. SPY 29, QQQ 4, XLK 3, VZ 2, WMT 2, ABBV 1, AMAT 1, GM 1, HOOD 1, IBM 1, IWM 1, MRVL 1, V 1, XLF 1. Per fonte: `alpaca_benzinga` 129 articoli unici, 69 effective-timely (53,5%); `gdelt_gkg` 16 su 16. La scelta dei connettori resta all'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Seduta risk-off da tassi: le righe del giorno citano i rendimenti a 10 anni ai massimi da 19 anni ("Nasdaq 100 Slips, 10-Year Yields Hit 19-Year Highs", 17:08). L'energy sale, le large cap tech e gli ADR non statunitensi scendono.**

- **Rialzisti**: energy (BP +3,23%, con PBR +1,83%, XOM +1,59%, SHEL +1,58%, CVX +1,53% e XLE +0,96% contro SPY −0,72%; titolo "…JPMorgan Upgrade, Oil Rally") e software/cybersecurity (PANW +5,00%, PLTR +3,68%, NOW +2,76%, CRM +1,84%).
- **Ribassisti**: tre gruppi. Large cap tech (GOOGL −3,80%, ORCL −3,11%, con AVGO −2,62% e AMZN −2,24% sotto soglia; QQQ −0,84%, IWM −1,84%). ADR europei (DB −4,50%, NVO −3,12%, con AZN −2,99% e UBS −2,95% appena sotto). Idiosincratici: MCD sull'ammissione di esecuzione carente, BABA sulla notizia di un'indagine di Pechino sull'AI, SPCX senza una riga esplicativa.
- **Rispetto ai giorni precedenti**: la forza dei semis del 17–22/09 si interrompe (SOXX −1,23%, MU −2,22% dopo il +5,00% del 22/09). L'energy torna rialzista dopo la gamba ribassista del 21/09. `dispersione_sigma` 1,74% (1,82% il 22/09).

La lettura sui tassi è un'associazione dal testo di una sola riga, non una causa verificata.

## 8. Segnalazioni

Tre finding esposti oggi. I denominatori sono contati dalle occorrenze di `findings.json` (sedute distinte), perché `longitudinal_panels.json` non esiste.

### [F-031] BP (+3,23%) ha un segnale S4 +0,375 sopra gate col segno giusto, bloccato 9 volte perché la detiene S1; SKIP_PYRAMIDING vale 55 dei 77 intenti tradabili

- **Meccanismo e fonte**: §3 (catturati) e §4. Campi del dossier:
  - `intenti_ingresso_s4`: `final_reason_code` sui tradabili = 55 SKIP_PYRAMIDING, 20 SKIP_IDEMPOTENCY, 2 SUBMITTED. BP: signal 12382, +0,375, 9 cicli dalle 17:52 alle 19:52.
  - Per simbolo: NOW 24 (detenuto da S4), SOXX 12, GM 9 e BP 9 (detenuti da **S1**, `snapshot_apertura.strategia`), META 1 (S4).
  - Sui simboli detenuti da S1 cadono 30 blocchi su 55 (54,5%).
  - `guard_decisions` ne traccia 2 su 55 (3,6%): BP 17:52 e META 19:52.
- **Esposizione oggi**: 55 intenti. Tra i mover è toccata BP, l'unico mover rialzista con un segnale S4 sopra gate in giornata. F-031 conta 22 sedute distinte in `findings.json`.
- **Evidenza contraria**: se il guard proteggesse soprattutto dal raddoppio delle posizioni S4, i blocchi su posizioni S4 sarebbero la maggioranza. Sono 25/55.
- **Non-occorrenza**: nessun candidato miss del §3 è toccato (zero SKIP_PYRAMIDING su PLTR, MCD, ORCL, SPCX). BA, non detenuta, passa SUBMITTED.
- **Next evidence (read-only)**: invariato. Sulla finestra, la quota degli intenti tradabili in SKIP_PYRAMIDING per sleeve detentrice, con controfattuale a 1 h e al close; l'orizzonte va pre-registrato prima della misura.
- **Costo**: **−4,46 $** (congetturale, formula della serie). Σ `intended_notional_usd` × `counterfactual_return_1h` sulle righe `guard_decisions` SKIP_PYRAMIDING di simboli detenuti da S1 = 2.196,88 × (−0,002029) [BP]. Alternative scartate:
  - il controfattuale al close (prezzo al segnale 44,36 contro close 44,49, ≈ +6,4 $), perché l'orizzonte non è quello della serie;
  - la riga META 19:52, perché lì il guard blocca il raddoppio di una posizione S4, come progettato.

### [F-013] META venduta alle 14:22 @744,21 su un segnale positivo (+0,101) e ricomprata alle 18:07 @750,15

- **Meccanismo e fonte**: §4. Campi:
  - `chiusure[META]` (qty 1,9489, `pnl_net` +9,96, `ore_tenuta` 19,25);
  - `ingressi[META]` (trade 1027, 18:07, entry 750,152, qty 1,93497);
  - `execution_decisions` SELL "[below_entry_gate] … score=+0,101".
  Il segno del segnale d'uscita è lo stesso dell'ingresso: la posizione esce perché il punteggio è sotto 0,30, non perché sia negativo. Rientra appena un altro articolo porta lo score a +0,315 ("Meta Platforms: 4 Reasons Why This Analyst Is Bullish On Muse").
- **Esposizione oggi**: 2 uscite S4 `below_entry_gate`, 1 seguita da un rientro sullo stesso simbolo nella stessa seduta. F-013 conta 24 sedute distinte in `findings.json`.
- **Evidenza contraria**: se esistesse una banda fra ingresso e uscita, un +0,101 non avrebbe chiuso una posizione aperta a +0,3x e non ci sarebbe stato il riacquisto a un prezzo più alto.
- **Non-occorrenza**: BABA esce alla stessa regola e non viene ricomprata. Il suo segnale successivo è −0,42 (fallback GDELT, "Alibaba Falls 4% as Reported Beijing AI Probe…").
- **Next evidence (read-only)**: sulla finestra, per ogni SELL `below_entry_gate` con score dello stesso segno dell'ingresso, contare i BUY sullo stesso simbolo entro la seduta e sommare qty × (prezzo rientro − prezzo uscita).
- **Costo**: **11,50 $** (attribuita). Formula: qty rientro × (entry rientro − exit) = 1,93497 × (750,152 − 744,21). Alternativa scartata: il `pnl_realizzato` successivo del trade 1027 (+31,38 $) come compensazione, perché misura l'esito del rientro e non il costo del giro.

### [F-030] Gli ingressi e i segnali del giorno arrivano a movimento già avvenuto

- **Meccanismo e fonte**: §3 e §4. Campi:
  - `ingressi[BA].quota_movimento_precedente_al_segnale` 1,99 (`entry_percentile` 0,64, `mtm_eod` −13,88);
  - `ingressi[META].denominatore_degenere`=true;
  - `intenti_ingresso_s4[BP].ritorno_sessione_al_segnale` +2,92% su un close di +3,23% (90% del movimento già fatto).
  Anche le righe ISSUER_SPECIFIC dei mover sono descrittive del movimento: PLTR "Flips $188 Into Support" (16:17), MCD "Slumps to 4-Year Lows" (18:16), GOOGL "Alphabet Stock Dips" (16:53).
- **Esposizione oggi**: 2 ingressi S4 e 1 segnale sopra gate su un mover (BP). F-030 conta 20 sedute distinte in `findings.json`.
- **Evidenza contraria**: se il finding fosse falso, almeno un ingresso avrebbe `quota_movimento_precedente_al_segnale` < 0,5 e `mtm_eod` positivo. Oggi BA è a 1,99 e −13,88 $, META a −11,71 $.
- **Non-occorrenza**: ERIC il 22/09 aveva un segnale ANTICIPATORY prima dell'open. Oggi le uniche righe ANTICIPATORY sui mover sono SPCX (−0,14) e ORCL (−0,12), entrambe sotto gate.
- **Next evidence (read-only)**: invariato. `aggregati.late_entry_joint_distribution` (83 ingressi dal 14/08): somma P&L realizzato per fascia di quota. La fascia ≥1,0 vale oggi −227,83 $ su 21 trade chiusi, contro −23,71 $ su 7 nella fascia 0–0,5. Il test decisivo è la stessa tabella a finestra chiusa, con la soglia pre-registrata.
- **Costo**: **13,88 $** (congetturale). Formula: `ingressi[BA].mtm_eod` = qty × (close − entry) = −13,88. Scartato il `pnl_realizzato` successivo di BA (−40,49 $), perché include sedute successive alla misura.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli, dal più alto al più basso)

| | | | |
|---|---|---|---|
| PANW +5,00% | PLTR +3,68% | BP +3,23% | NOW +2,76% |
| TMUS +2,00% | WDC +1,96% | CRM +1,84% | PBR +1,83% |
| XOM +1,59% | SHEL +1,58% | CVX +1,53% | BA +1,12% |
| ADBE +1,02% | META +1,02% | XLE +0,96% | PFE +0,90% |
| T +0,80% | BRK.B +0,73% | MA +0,72% | IBM +0,60% |
| MMM +0,59% | COST +0,59% | CMCSA +0,58% | MSFT +0,52% |
| CAT +0,50% | TXN +0,45% | AMAT +0,41% | GM +0,38% |
| WMT +0,37% | TSLA +0,32% | GE +0,18% | DELL +0,17% |
| VZ +0,15% | JNJ −0,01% | CSCO −0,01% | SAP −0,03% |
| ABBV −0,05% | INFY −0,09% | NKE −0,14% | V −0,14% |
| ASML −0,19% | ARM −0,19% | DIS −0,35% | BAC −0,36% |
| C −0,41% | UNH −0,45% | XLK −0,47% | XLF −0,47% |
| ROKU −0,49% | QCOM −0,52% | SNOW −0,53% | MRVL −0,56% |
| PG −0,56% | XLV −0,64% | SPY −0,72% | JPM −0,73% |
| JD −0,80% | AAPL −0,80% | QQQ −0,84% | TM −0,89% |
| MS −0,89% | ERIC −0,92% | SONY −0,94% | INTC −1,02% |
| AXP −1,02% | SBUX −1,02% | NFLX −1,11% | TSM −1,20% |
| F −1,22% | SOXX −1,23% | HOOD −1,25% | GS −1,38% |
| NVDA −1,47% | AMD −1,47% | WFC −1,50% | LLY −1,64% |
| NOK −1,76% | IWM −1,84% | MRK −1,88% | MU −2,22% |
| AMZN −2,24% | RIO −2,30% | RDDT −2,37% | VALE −2,61% |
| AVGO −2,62% | HD −2,83% | BIDU −2,87% | UBS −2,95% |
| AZN −2,99% | ORCL −3,11% | NVO −3,12% | GOOGL −3,80% |
| SPCX −4,11% | DB −4,50% | BABA −4,74% | MCD −4,81% |

Mover |r| ≥ 3%: 10 (3 su, 7 giù). `simboli_senza_dati`=[].

### (b) Checklist degli altri finding toccati

- [F-001] supported — `watchlist_zero_news` 42/96; effective-timely 40/96.
- [F-008] contradicted (parziale) — BABA esce su un −0,007 da un roundup multi-ticker, ma la riga cita esplicitamente BABA −3,4% pre-market e `drift_post_uscita` è −0,74 $: l'uscita non era contro-tema.
- [F-009] supported — PLTR +3,68% con segnale issuer-specifico +0,14 del segno giusto, sotto gate.
- [F-011] supported — SELL `signal_id` 0/2 (`decision_signal_id_coverage.regressions`=["SELL"]).
- [F-012] supported — `mapping_fanout_extra` 69 su 214 righe; `cause_del_giorno.quota_righe_fanout` 0,47.
- [F-020] not_exposed — DB zero righe oggi, nessun `org_lookup` su ticker bancari fra i candidati.
- [F-021] supported — primo ciclo portfolio 14:07 UTC con l'apertura EDT alle 13:30 (log worker).
- [F-040] supported — MCD −0,405 sopra gate col segno giusto: solo `RANK_LONG_ONLY`, nessun ordine.
- [F-043] contradicted — oggi sopra gate ci sono anche segnali ribassisti non-fallback (MCD −0,405, −0,36).
- [F-046] not_exposed — non verificato sul testo passato al modello.
- [F-053] supported — Alpaca portfolio history timbra la seduta 23/09 alle 2026-09-24T00:00Z (equity 109.882,53).
- [F-076] supported — `testo_scorato` con `&#39;` su MCD, ORCL, SPCX, PLTR.
- [F-082] not_exposed — 0 soppressi su 77 intenti valutabili oggi.
- [F-089] not_exposed — nessuna posizione S4 mover con segnale fresco sotto gate e senza SELL.

### (c) Casi di successo

- **PANW +5,00%** — detenuta S4 all'open (1.472,18 $), `actual_intraday_pnl_usd` **+52,33 $**, residuo beta-1 +62,21 $. È il principale contributo positivo del libro nella seduta.
- **BP +3,23%** — detenuta S1 (831,25 $), +12,71 $.
