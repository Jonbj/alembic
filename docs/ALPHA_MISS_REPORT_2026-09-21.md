# Alpha Miss Report — 2026-09-21

Contratto `alpha_miss_prompt_v2` · dossier `docs/evidence/dossier/2026-09-21.json` (`schema_version` 3.1, generato 2026-09-28T08:00:28Z, prezzi Alpaca SIP `adjustment=all`). Soglia mover `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30.

## 1. Decision card

1. **S4 ha tradato tutta la seduta a un quinto della size perché il regime era assente, non perché la volatilità fosse alta**: entrambi i giri di `detect_regime` (07:00, 13:30) falliscono su FRED e risultano `succeeded: None`, e ogni ciclo applica il fallback "×0.20 (vix=absent)" (`event_market_context.regime` = HIGH_VOL, `multiplier` 0,2, con `vix` 14,87). I 5 ingressi S4 hanno nozionale tra 409,75 e 420,86 $ contro uno slot da 2.200 $. Tenuti al moltiplicatore SIDEWAYS 0,7 osservato il 18/09 e il 22/09, gli stessi trade avrebbero reso circa **+52,35 $** in più.
2. **Rally dei semis/AI con 14 mover (11 al rialzo)** guidato da ARM +17,16%, INTC +12,14%, META +11,43%, AMD +9,95% e QCOM +9,29%. Dei mover, 7 su 14 erano già a libro all'open (`held_at_open_rate` 0,5) e 2 sono stati catturati in ingresso (META, ARM). I 4 miss valgono al massimo **21,42 $** netti (`net_opportunity_usd` RDDT).
3. **META (+11,43%) è stata venduta alle 16:07 su un segnale di +0,027**, generato da un articolo sul gasolio taggato fan-out ("$6.51 Diesel Should Be Crushing the Economy"). L'ultimo segnale issuer-specifico era +0,435 alle 15:15. Realizzato +5,63 $, `drift_post_uscita` **+11,20 $**. Realizzato della seduta **+10,94 $**, tutto S4.

## 2. Stato carta

Da `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18T10:14+02:00). I cumulati arrivano al 17/09: né il 18/09 né questa seduta sono nel file.

- Giorno **30/40** della finestra di osservazione (inizio 2026-08-03, `minimo_giorni`=40).
- Quota NO_NEWS dominante **13/30 = 43,3%**, sotto la soglia carta 0,60 (`superata_soglia`=false).
- S4 economico cumulato **−696,33 $** contro la banda ±200 $ (`within`=false, fuori banda).
- Book cumulato −66,22 $. S1 cumulato +664,95 $ contro un benchmark SPY di +943,98 $ (`delta_vs_spy` −279,03 $).
- `docs/evidence/longitudinal_panels.json` **non esiste**: i denominatori del §8 sono contati dalle occorrenze di `findings.json` e dichiarati come tali.

## 3. Miss del giorno

4 candidati in `candidati_miss`, tutti mover rialzisti non detenuti. `funnel_v2.conteggi_pipeline` = {"NO_RELEVANT_NEWS":3, "BELOW_GATE":1, "CAUGHT":2}. Come nei report precedenti, dove i due assi divergono prevale `funnel_v2.pipeline` sul campo grezzo `causa`; il valore legacy è riportato per riga (`mapping_legacy_v2`: NO_RELEVANT_NEWS → NO_NEWS, BELOW_GATE → THIN_NEUTRAL).

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| QCOM | +9,29% | **NO_NEWS** | `funnel_v2.righe[QCOM].pipeline`="NO_RELEVANT_NEWS", `evidence.rilevanza`={TAG_UNCONFIRMED:1, resto 0}. Una riga sola in `news_log`: il roundup "Nasdaq 100 Rallies, Intel Soars 14%: Stock Market Today" (17:51, 11 ticker, `attribution` FANOUT) con score +0,193. Non è un buco a zero righe, ma nessuna copertura confermata su Qualcomm. Legacy `causa`="BELOW_GATE". `net_opportunity_usd`=16,19 $ (ingresso al primo ciclo eleggibile, 18:07 @192,705); il lordo close-to-close 204,38 $ non era accessibile. |
| RDDT | +5,22% | **NO_NEWS** | `news_count`=0, `segnali`=[], `funnel_v2.righe[RDDT].pipeline`="NO_RELEVANT_NEWS" con tutte le classi a 0. `net_opportunity_usd`=21,42 $ (ingresso all'open di sessione 14:07). |
| PLTR | +3,07% | **NO_NEWS** | `funnel_v2.righe[PLTR].pipeline`="NO_RELEVANT_NEWS", TAG_UNCONFIRMED:1. L'unica riga è un comunicato del Dipartimento dei Trasporti sul tool AI della FAA (17:17, score +0,020, `fallback`=true), che nel testo letto non nomina Palantir. Legacy `causa`="OFF_TOPIC_NON_DECIDIBILE". `net_opportunity_usd`=14,08 $. |
| TSLA | +3,03% | **THIN_NEUTRAL** | `funnel_v2.righe[TSLA].pipeline`="BELOW_GATE", `evidence.score_firmato`=+0,142 < `soglia_gate` 0,30, segno corretto. 4 righe ISSUER_SPECIFIC: audit dei fornitori per Optimus e il record di 580 MW di Sunrun/Tesla (13:33–16:33, score 0,081–0,142). `net_opportunity_usd`=**−3,09 $**: entrando al primo ciclo (14:07 @375,75) si chiudeva a 375,30, quindi il gate qui non è costato nulla. |

**Conteggi**: NO_NEWS 3 · THIN_NEUTRAL 1 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0. `aggregati.cause_del_giorno` (vista legacy, invariata per vincolo #288) = {"NO_NEWS":1, "BELOW_GATE":2, "OFF_TOPIC_NON_DECIDIBILE":1}, `dominante`="BELOW_GATE". Somma di `net_opportunity_usd` sui 4 miss: **48,60 $**.

### Titoli catturati

| Simbolo | Return% | Come | Esito |
|---|---:|---|---|
| META | +11,43% | ingresso S4 alle 14:07 @712,616, signal 11827 +0,409 ISSUER_SPECIFIC (Wells Fargo alza il PT a 796 $) | Uscita alle 16:07 @722,284 `below_entry_gate` su +0,027 fan-out; `pnl_net` +5,63 $, `drift_post_uscita` +11,20 $ (§8, F-008). `entry_percentile` 0,450; il 53% del movimento era già avvenuto al segnale. |
| ARM | +17,16% | ingresso S4 alle 15:37 @315,584, signal 11898 +0,581 ("What Is Going On With Arm Holdings Stock on Monday?") | Aperta a fine seduta, `mtm_eod` +9,59 $. `entry_percentile` 0,724, `quota_movimento_precedente_al_segnale` 0,744: ingresso tardivo, a movimento largamente fatto. |
| NVO | −7,96% | ingresso S4 alle 14:07 @39,737 su signal 11824 +0,295 × velocity 1,2 (Capital Markets Day: +8 punti di quota nell'obesità). `funnel_v2`: `non_actionable_long_only` | Comprata con la seduta già a −7,41% (`ritorno_sessione_al_segnale`). La guardia ombra di contraddizione l'ha segnalata (`guardia_contraddizione_ombra`=true), ma solo in ombra. Uscita alle 15:52 `below_entry_gate` @39,85, `pnl_net` +0,97 $. |

Mover detenuti all'apertura (`funnel_v2.kpi.held_at_open` = 7, di cui 5 PASSIVE_EXPOSURE e 2 EXIT_RISK). P&L intraday da `snapshot_apertura.actual_intraday_pnl_usd`:

| Simbolo | Return% | Detenuto da (nozionale all'open) | Esito di seduta |
|---|---:|---|---|
| INTC | +12,14% | S4, 1.692,4 $ | PASSIVE_EXPOSURE, +76,25 $ |
| MRVL | +5,38% | S4, 1.602,5 $ | PASSIVE_EXPOSURE, +38,12 $ |
| AMD | +9,95% | S1, 475,1 $ | PASSIVE_EXPOSURE, +25,74 $. Il signal S4 +0,710 è stato bloccato 10 volte da `SKIP_PYRAMIDING` (§8, F-031). |
| SOXX | +4,93% | S1, 629,4 $ | PASSIVE_EXPOSURE, +16,47 $ |
| AMAT | +4,42% | S1, 390,8 $ | PASSIVE_EXPOSURE, +7,11 $; `ritorno_da_ingresso` −21,82%, zero righe `news_log` |
| XOM | −3,20% | S1, 885,0 $ | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` +0,025), −14,63 $ |
| BP | −3,19% | S1, 848,1 $ | EXIT_RISK, "STALE_EXIT_SIGNAL" (signal 11260 del 16/09, score 0,0), −29,40 $; zero righe `news_log` |

Somma sui 7 mover detenuti: **+119,66 $**. KPI: `active_signal_recall` 2/3, `execution_conversion_rate` 2/2, `profitable_capture_rate` 2/6, `exit_signal_recall` 0/2.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["META","NVO","HOOD","ARM","NOW"],"chiusure":["NVO","META","HOOD"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | META | S4 | 14:07 | $712.6160 | 0.5906 | — | percentile 44.98%; denominatore intraday valido |
| IN | NVO | S4 | 14:07 | $39.7366 | 10.5912 | — | percentile 12.06%; denominatore intraday valido |
| IN | HOOD | S4 | 14:22 | $122.7800 | 3.4023 | — | percentile 25.99%; denominatore intraday valido |
| IN | ARM | S4 | 15:37 | $315.5840 | 1.3104 | — | percentile 72.41%; denominatore intraday valido |
| IN | NOW | S4 | 16:22 | $137.5400 | 2.9791 | — | percentile 42.29%; denominatore intraday valido |
| OUT | NVO | S4 | — | $39.8500 | 10.5912 | +$0.97 | hold_minimum_expiry |
| OUT | META | S4 | — | $722.2840 | 0.5906 | +$5.63 | portfolio_sell |
| OUT | HOOD | S4 | — | $124.1200 | 3.4023 | +$4.33 | hold_minimum_expiry |
<!-- alpha-miss-book:end -->

Ci sono stati 5 ingressi S4 (META, NVO, HOOD, ARM, NOW) e 3 chiusure S4 (NVO, META, HOOD), tutte e tre decise da `below_entry_gate` nel log decisionale. Il dossier etichetta NVO e HOOD come `hold_minimum_expiry` e META come `portfolio_sell`. Ogni ingresso ha un nozionale tra 409,75 e 420,86 $ (`regime_mult` 0,2 su tutte le righe BUY/SELL, vedi §8 F-017). Il realizzato è di +10,94 $ (NVO +0,97, META +5,63, HOOD +4,33). Le posizioni ARM e NOW restano aperte, con `mtm_eod` rispettivamente di +9,59 $ e +0,42 $.

Le tre uscite si dividono per `drift_post_uscita`. Su HOOD (−2,79 $) e NVO (−0,53 $) l'uscita ha evitato una perdita. META invece ha lasciato sul tavolo 11,20 $. Le uscite sono state innescate da segnali diversi:

- NVO: −0,036, ISSUER_SPECIFIC, dichiarazione del CFO sui margini.
- HOOD: +0,183, TAG_UNCONFIRMED, pezzo sulle liquidazioni crypto.
- META: +0,027, FANOUT, articolo sul gasolio.

Quattro ingressi su cinque hanno `quota_movimento_precedente_al_segnale` ≥ 0,74 (HOOD 1,30, NVO 1,05, NOW 0,84, ARM 0,74).

A monte degli ordini ci sono 120 intenti tradabili su 1.715: 94 `SKIP_PYRAMIDING` (78,3%), 21 `SKIP_IDEMPOTENCY` e 5 `SUBMITTED`. Le 3 righe SELL di `execution_decisions` non hanno `signal_id` (`decision_signal_id_coverage.regressions`=["SELL"]).

## 5. Cecita' lato uscita

`copertura_uscita` conta 43 posizioni, con `n_indeterminati`=**0**: nessuna riga ha `cieco_lato_uscita: null`. Due posizioni sono cieche, entrambe ancora aperte:

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| SBUX | S1 | **−9,95%** | −0,97% | 8 | `alpaca_benzinga` | 624,61 $ |
| VALE | S1 | −3,35% | −0,42% | 3 | `alpaca_benzinga` | 750,00 $ |

`ritorno_da_ingresso` è la perdita dall'ingresso al close (nessuna delle due è uscita in seduta). `ritorno_seduta` è il solo movimento del 21/09, sotto la soglia mover per entrambe. La streak di SBUX continua a crescere (7 il 18/09, 8 oggi). `fonti_osservate_finestra` non è vuota: Benzinga interroga i due ticker ma non ha reso nulla, quindi si tratta di resa zero e non di una fonte non configurata. VALE entra nella lista oggi: `materials` è a zero articoli.

Aggregato: 13 posizioni a copertura grezza nulla, 21 a copertura effective-timely nulla, 9 in perdita marcata, nozionale cieco **1.374,61 $** (era 630,73 $ il 18/09).

## 6. Backstop NO_NEWS

`no_news_backstop.population`: 40 simboli a zero righe `news_log` (3 mover, 37 non-mover, `return_missing`=0).

### 6a. Marker calendario

| Simbolo | Return% | `observed_catalysts` | Calendario |
|---|---:|---|---|
| RDDT | +5,22% | `[]` | `NOT_OBSERVED` (FMP earnings-calendar e Alpaca Corporate Actions hanno risposto entrambe) |
| AMAT | +4,42% | `[]` | `NOT_OBSERVED`, stesse due fonti (detenuto S1: non è fra i candidati miss) |
| BP | −3,19% | `[]` | `NOT_OBSERVED`, stesse due fonti (detenuto S1: EXIT_RISK) |

`mover_observed` = 0/3 contro 1/37 (2,7%) fra i non-mover: SHEL, dividendo in contanti con data 2026-09-21 (Alpaca Corporate Actions), settore energy. `calendario_earnings.status`="OBSERVED", `simboli_flaggati`=[]. Un marker `CALENDAR` indica un evento a calendario, non un segnale né un ordine.

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false. Il volume di seduta si conosce solo alla chiusura, quindi niente di quanto segue era disponibile prima del movimento. Qui non si fissano soglie né si stimano false-positive rate: la valutazione ex-ante sta in #451.

- Mediana della sorpresa di volume: **+46,2%** sui mover a zero news (n=3), **−7,8%** sui non-mover (n=37).
- Per simbolo: BP +71,0% (16,53 M contro un ADV20 di 9,67 M), AMAT +46,2%, RDDT +16,9%.

### 6c. Copertura raw di `news_log` per settore (tutti i settori)

Questa è la copertura **raw**, distinta dalla quota effective-timely di `copertura_articoli.per_settore`, che oggi è 41/96 a livello di watchlist.

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news | calendario su zero news |
|---|---:|---:|---:|---:|
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| semis | 13/15 | 86,7% | 1 (AMAT) | 0 |
| industrials | 3/4 | 75,0% | 0 | 0 |
| healthcare | 6/9 | 66,7% | 0 | 0 |
| telecom | 3/5 | 60,0% | 0 | 0 |
| tech | 12/21 | 57,1% | 0 | 0 |
| consumer | 6/11 | 54,5% | 0 | 0 |
| energy | 3/6 | 50,0% | 1 (BP) | 1 (SHEL) |
| financials | 5/14 | 35,7% | 0 | 0 |
| media | 1/5 | 20,0% | 1 (RDDT) | 0 |
| materials | 0/2 | **0,0%** | 0 | 0 |

Totale 56/96 con almeno una riga (`watchlist_zero_news`=40, era 34 il 18/09). `materials` è a 0/2 (RIO 6 sedute consecutive a zero articoli, VALE 3). `financials` scende a 5/14.

### 6d. Attribuzione fonti per ticker (#511 passo 2)

Ticker con `articoli_unici`=0: per tutti `fonti_osservate`={} e `articoli_unici_giorno` = `effective_timely_articles_giorno` = 0 (da `blind_set.per_ticker`). Tra parentesi `sedute_consecutive_zero_articoli`:

ADBE (5), AMAT (1), AXP (1), AZN (1), BABA (1), BAC (2), BIDU (3), BP (3), C (1), CMCSA (3), DB (2), ERIC (10, troncato), F (1), GS (1), HD (6), IBM (1), INFY (7), JD (2), MA (1), MMM (4), MRK (1), NFLX (1), PBR (1), PFE (1), PG (1), RDDT (1), RIO (6), ROKU (8), SAP (4), SBUX (8), SHEL (4), SNOW (6), SONY (1), TXN (5), UBS (4), V (2), VALE (3), VZ (5), WFC (2), WMT (2).

`ticker_allerta_zero_articoli` (≥5): ADBE, ERIC, HD, INFY, RIO, ROKU, SBUX, SNOW, TXN, VZ.

Fonte presente ma non utile (articoli > 0, effective-timely 0), sempre e solo `alpaca_benzinga`: per ciascuno di questi ticker la fonte `alpaca_benzinga` ha reso N righe, ma nessuna effective-timely. AMZN 8, QQQ 5, SOXX 3, XLE 3, BA 1, CAT 1, COST 1, CRM 1, CSCO 1, IWM 1, PLTR 1, QCOM 1, UNH 1, XLF 1, XLV 1. Per `per_fonte`: `alpaca_benzinga` 111 articoli unici, di cui 71 effective-timely (64,0%); `gdelt_gkg` 11 su 11. La scelta dei connettori resta all'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Terza seduta di forza sui semis/hardware AI, con rotazione in uscita dall'energy.**

- **Semis**: 6 degli 11 mover rialzisti sono `semis` (ARM +17,16%, INTC +12,14%, AMD +9,95%, QCOM +9,29%, MRVL +5,38%, AMAT +4,42%). SOXX fa +4,93% contro SPY +1,55%. QQQ e XLK fanno entrambi +2,88/2,89%. QCOM batte SOXX di +4,36% (`residual_vs_sector`), `theme`="AI_SEMIS".
- **Altri rialzisti**: sono titoli growth/AI (META +11,43%, PLTR +3,07%, TSLA +3,03%) e RDDT +5,22%.
- **Ribassisti**: sono energy (XOM −3,20%, BP −3,19%, con CVX −2,79% e XLE −2,30% appena sotto soglia). L'unica riga Benzinga pertinente è "Crude Oil Down 4%" (16:04). NVO −7,96% è idiosincratico: Capital Markets Day, "Falls 7% as Post-Wegovy Growth Plan Fails to Ease Competition Fears".
- **Continuità**: il 17/09 e il 18/09 il tema era lo stesso (8/12 e 6/8 mover rialzisti nei semis). È una continuazione, non un tema nuovo. La novità di oggi è l'ampiezza (dispersione `dispersione_sigma` 3,14% contro 2,18% il 18/09) e il ribasso compatto dell'energy.

## 8. Segnalazioni

Tre finding esposti oggi con una conseguenza in dollari. I denominatori sono contati dalle occorrenze di `findings.json`, perché `longitudinal_panels.json` non esiste.

### [F-017] La rilevazione di regime fallisce due volte e risulta `succeeded`: tutta la seduta gira al fallback ×0,20 con VIX a 14,87

- **Meccanismo e fonte**: §4. Campi del dossier: `ingressi` (qty × entry_price) e `event_market_context.per_symbol[*].regime` = {type HIGH_VOL, multiplier 0,2, source `execution_decisions.regime_mult`, vix 14,87 da FRED:VIXCLS}. Log `worker-inference-2026-09-21.log`:
  - 07:00:15: "Failed to fetch macro data for regime detection: The read operation timed out", poi `succeeded ... None`.
  - 13:30:04: T10Y2Y "502 Bad Gateway", poi `succeeded ... None`.
  - `worker-2026-09-21.log` contiene 62 righe "P0-09: regime:current absent — deterministic VIX fallback ×0.20 (vix=absent)", dalle 14:07:03 alle 19:52:05. Nelle sedute 14–18/09 le righe sono 0.
- **Esposizione oggi**: tutti i cicli della seduta e tutti e 5 gli ingressi S4 (nozionale 409,75–420,86 $, cioè ~19% di uno slot da 2.200 $), in una giornata con 14 mover. F-017 conta 5 occorrenze in `findings.json`, l'ultima il 22/09. Il 22/09 il giro delle 13:30 era riuscito; oggi falliscono entrambi.
- **Evidenza contraria**: se il ×0,20 riflettesse un vero regime HIGH_VOL, il VIX della seduta sarebbe alto. È 14,87, lo stesso livello per cui il 18/09 il sistema aveva SIDEWAYS 0,7 (VIX 14,81).
- **Non-occorrenza**: S1 non è esposta. Il suo gate di ribilanciamento è chiuso ("rebalance gate closed — holding 43 position(s)"), quindi nessun ordine S1 viene scalato. Le uscite S4 vendono l'intera quantità, per cui il moltiplicatore non tocca il lato uscita.
- **Next evidence (read-only)**: incrociare, sulla finestra 08-03→09-26, le sedute con `execution_decisions.regime_mult`=0,2 con il VIX FRED dello stesso giorno e con l'esito di `detect_regime` nei log `worker-inference`. Se ogni seduta a 0,2 coincide con un giro fallito e non con un VIX alto, il moltiplicatore misura la disponibilità di FRED, non il regime. Poi confrontare il P&L S4 di quelle sedute con quello delle sedute a 0,7.
- **Sembra un difetto di correttezza, non un limite noto**: il fallback con input mancante ("vix=absent") applica il moltiplicatore più severo della mappa, e per costruzione la serie S4 di questa seduta è ridotta di 3,5 volte rispetto a quelle adiacenti. La decisione sull'esenzione dal freeze spetta all'operatore.
- **Costo**: **52,35 $** (congetturale, segue la confidenza del record). Formula: (0,7/0,2 − 1) × (Σ `chiusure.pnl_net` + Σ `ingressi.mtm_eod` delle posizioni ancora aperte) = 2,5 × (0,97 + 5,63 + 4,33 + 9,59 + 0,42) = 2,5 × 20,95. Ipotesi: stessi trade, P&L lineare nel nozionale (F-038: il moltiplicatore scala solo il nozionale, non la selezione). Scartato come alternativa il costo "a slot pieno" (2.200/420 × 20,95 − 20,95 ≈ 88,8 $), perché il regime osservato nelle sedute adiacenti è 0,7 e non 1,0.

### [F-008] META (+11,43%) esce su un articolo sul gasolio taggato fan-out, due ore dopo un ingresso issuer-specifico

- **Meccanismo e fonte**: §3 e §4. Campi: `ingressi[META]`, `chiusure[META]` e `copertura_articoli.segnali`; `execution_decisions` 36172. Sequenza:
  - Ingresso alle 14:07 su signal 11827, +0,409 ISSUER_SPECIFIC (Wells Fargo PT 640 → 796 $).
  - Alle 15:15 arriva 11884, +0,435 ISSUER_SPECIFIC ("Meta Stock Is Surging"), bloccato come SKIP_PYRAMIDING perché META è già a libro.
  - Seguono 11895 (−0,050, TAG_UNCONFIRMED, pezzo su Eisman/Anthropic), 11901 (+0,150, Galloway sulla privacy) e 11904 (+0,027, **FANOUT**, "$6.51 Diesel Should Be Crushing the Economy").
  - Il log delle 15:52 riporta "Exit hysteresis (2 cycles): held 2 position(s) flagged for exit: ['HOOD', 'META']".
  - Alle 16:07 la SELL con motivo "[below_entry_gate] ... generated 2026-09-21 15:52 UTC, score=+0.027" esce a 722,284.
- **Esposizione oggi**: 3 chiusure S4, tutte `below_entry_gate`; una sola (META) nasce da una riga FANOUT. F-008 conta 15 occorrenze in `findings.json`, l'ultima il 22/09 (ARM, lo stesso trade 1021 aperto oggi).
- **Evidenza contraria**: se il finding fosse falso, l'uscita META avrebbe una causa issuer-specifica negativa oppure il titolo sarebbe sceso dopo l'uscita. Invece il segnale d'uscita è positivo e non parla di Meta, e il titolo chiude a 741,245.
- **Non-occorrenza**: NVO esce su una riga ISSUER_SPECIFIC (−0,036, CFO sui margini) con `drift_post_uscita` −0,53 $. HOOD esce su una riga TAG_UNCONFIRMED ma non fan-out (+0,183, liquidazioni crypto) con drift −2,79 $. In entrambi i casi l'uscita ha evitato una perdita, quindi il costo compare solo sull'uscita decisa da una riga fan-out.
- **Next evidence (read-only)**: per tutte le SELL S4 `below_entry_gate`/`sentiment_reversal` della finestra, classificare il segnale citato nel `reason` per `attribution` (FANOUT, UNKNOWN, ISSUER_SPECIFIC) e confrontare la mediana di `drift_post_uscita` fra i gruppi. Il join va fatto sul timestamp nel testo, perché `signal_id` è NULL sulle SELL (F-011).
- **Costo**: **11,20 $** (attribuita). Formula: `drift_post_uscita` = qty × (close − exit) = 0,59058 × (741,245 − 722,284). Scartato come alternativa il P&L realizzato +5,63 $, perché misura l'ingresso e non l'uscita. Scartato anche il costo a slot pieno (×5,2), per non contare due volte l'effetto del §8 F-017.

### [F-031] Il guard anti-pyramiding blocca 10 volte il segnale più forte della giornata (AMD +0,710) perché S1 detiene 475 $ del titolo

- **Meccanismo e fonte**: §3 e §4. Campi: `intenti_ingresso_s4` (`final_reason_code`) e `guard_decisions`.
  - I 120 intenti `is_tradable` si dividono in 94 `SKIP_PYRAMIDING`, 21 `SKIP_IDEMPOTENCY` e 5 `SUBMITTED`.
  - Blocchi per simbolo: GM 24, PBR 24, AMD 10, JPM 10, QQQ 8, NOK 5, AMAT 4, MRK 3, LLY 2, META 2, INTC 2.
  - Detenuti da **S1**: 82/94 (87%, GM, PBR, AMD, JPM, NOK, AMAT, MRK, LLY). Detenuti da S4 stessa (il guard come progettato): 12 (QQQ, META, INTC).
  - AMD: signal 11896 +0,710 ISSUER_SPECIFIC ("AMD Stock Hits Fresh Record High", 15:34), bloccato dalle 15:37 alle 17:52.
- **Esposizione oggi**: 94 intenti; 3 mover colpiti. AMD (+9,95%) e AMAT (+4,42%) sono detenuti da S1, INTC (+12,14%) da S4. Tracciabilità: `guard_decisions` ha **7** righe `SKIP_PYRAMIDING` contro 94 intenti (7,4%; era 7,3% il 18/09). F-031 conta 22 occorrenze in `findings.json`, l'ultima il 18/09.
- **Evidenza contraria**: se il guard proteggesse soprattutto contro il raddoppio delle posizioni S4, i blocchi su posizioni S4 sarebbero la maggioranza. Sono 12/94.
- **Non-occorrenza**: nessuno dei 4 candidati miss del §3 è stato toccato dal guard (zero intenti `SKIP_PYRAMIDING` per QCOM, RDDT, PLTR, TSLA). ARM, non detenuta, è passata (`SUBMITTED` alle 15:37 nello stesso ciclo in cui AMD veniva bloccata).
- **Next evidence (read-only)**: invariato rispetto al 18/09. Sulla finestra, calcolare la quota degli intenti tradabili in `SKIP_PYRAMIDING` separata per sleeve detentrice, con il controfattuale a 1 h e al close. Oggi i due orizzonti hanno segno opposto su AMD, quindi l'orizzonte va pre-registrato prima della misura.
- **Costo**: **−1,65 $** (congetturale). Formula: `guard_decisions[35973].intended_notional_usd × counterfactual_return_1h` = 2.198,64 × (−0,000752). Stessa formula del 18/09, per coerenza della serie. Alternativa riportata ma non usata: al close sarebbe +16,05 $ = 2.198,64 × ((1 + 0,09950)/(1 + 0,09153) − 1), con prezzo al segnale 611,06 (open 15:35). Con il regime a 0,2 (§8 F-017) il nozionale reale sarebbe stato ~1/5 di `intended_notional_usd`: il costo è un limite superiore della size.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli, dal più alto al più basso)

| | | | |
|---|---|---|---|
| ARM +17,16% | INTC +12,14% | META +11,43% | AMD +9,95% |
| QCOM +9,29% | MRVL +5,38% | RDDT +5,22% | SOXX +4,93% |
| AMAT +4,42% | PLTR +3,07% | TSLA +3,03% | HOOD +2,90% |
| XLK +2,89% | QQQ +2,88% | MU +2,77% | BIDU +2,54% |
| C +2,49% | NOK +2,43% | TSM +2,41% | NVDA +2,30% |
| PANW +2,25% | BABA +2,22% | NFLX +2,19% | GM +2,13% |
| SNOW +2,09% | ASML +1,87% | AMZN +1,87% | GS +1,85% |
| MRK +1,79% | CSCO +1,78% | MS +1,75% | NKE +1,66% |
| NOW +1,63% | AVGO +1,60% | TXN +1,59% | MSFT +1,59% |
| GOOGL +1,55% | SPY +1,55% | WDC +1,54% | DIS +1,52% |
| GE +1,51% | BA +1,49% | JD +1,34% | DELL +1,28% |
| AZN +1,22% | LLY +1,04% | IBM +1,04% | CAT +0,93% |
| AAPL +0,85% | CMCSA +0,84% | ERIC +0,79% | XLV +0,75% |
| UBS +0,73% | DB +0,71% | JPM +0,68% | WMT +0,67% |
| AXP +0,65% | INFY +0,65% | ORCL +0,64% | SONY +0,55% |
| IWM +0,52% | TM +0,51% | WFC +0,49% | V +0,45% |
| ROKU +0,45% | XLF +0,43% | MA +0,43% | BAC +0,40% |
| COST +0,35% | PFE +0,29% | ADBE +0,24% | ABBV +0,20% |
| T +0,20% | UNH +0,18% | SAP −0,11% | MCD −0,15% |
| JNJ −0,19% | PG −0,21% | F −0,30% | RIO −0,34% |
| VALE −0,42% | MMM −0,55% | SPCX −0,56% | CRM −0,63% |
| PBR −0,82% | VZ −0,85% | HD −0,93% | SBUX −0,97% |
| SHEL −1,34% | BRK.B −1,52% | TMUS −1,73% | XLE −2,30% |
| CVX −2,79% | BP −3,19% | XOM −3,20% | NVO −7,96% |

`dispersione_sigma` 3,14%; `mover_3pct` 14 (11 al rialzo, 3 al ribasso); `simboli_senza_dati`=[].

### (b) Checklist degli altri finding toccati

- [F-001] supported: 40/96 simboli a zero righe `news_log`; 3 mover NO_NEWS (1 fra i candidati).
- [F-009] supported: TSLA +0,142 sotto gate col segno corretto, ma `net_opportunity_usd` −3,09 $, quindi oggi il gate non costa.
- [F-011] supported: 3/3 SELL senza `signal_id`, `decision_signal_id_coverage.regressions`=["SELL"].
- [F-012] supported: 189 righe su 122 articoli (`mapping_fanout_extra` 67), TAG_UNCONFIRMED 102/189 (54,0%).
- [F-013] supported: 3 SELL `below_entry_gate`, di cui 2 su score positivo (HOOD +0,183, META +0,027). Nessun riacquisto nella seduta.
- [F-022] supported: il log delle 16:07 riporta "#161: 10/45 held positions are unprotectable (qty < 1)", con AMAT a −22,3% e WDC a −19,7%.
- [F-023] supported: su META il +0,435 issuer-specifico delle 15:15 è sostituito entro 37 minuti da tre segnali più deboli, l'ultimo dei quali decide l'uscita (§8 F-008).
- [F-030] supported: 4/5 ingressi con `quota_movimento_precedente_al_segnale` ≥ 0,74. Mediana mobile a 20 gg di `entry_percentile` 0,538.
- [F-038] supported: `regime_mult` 0,2 su tutte le righe BUY; nozionale per ingresso ~420 $ contro un `portfolio weight 2.0%` dichiarato nel `reason`.
- [F-051] supported: AMAT signal 11781 del 18/09 19:15 ancora nel ranking il 21/09 (4 `SKIP_PYRAMIDING`, 20 `RANK_OUTSIDE_TOP_N`).
- [F-053] supported: nello storico Alpaca la seduta del 21/09 è etichettata 2026-09-22 (equity 110.025,01 $).
- [F-073] supported: BUY NVO persistita con `signal_score` 0,295 (grezzo) mentre il gate ha valutato 0,354 (× velocity 1,2).
- [F-075] supported: i mover PASSIVE_EXPOSURE AMAT (390,8 $, 17,8% di uno slot) e AMD (475,1 $, 21,6%) sono contati come held quanto INTC (1.692,4 $).
- [F-082] contradicted: la guardia ombra ha segnalato un intento poi eseguito (NVO, `n_soppressi_eseguiti`=1, `somma_pnl_realizzato_soppressi` +0,97 $).

### (c) Casi di successo

- **ARM +17,16%**: ingresso alle 15:37 su +0,581 × velocity 1,2, due minuti dopo l'articolo issuer-specifico (pubblicato 15:33, scorato 15:35). `mtm_eod` +9,59 $ a nozionale ridotto (413,53 $), `vs_apertura` +37,40 $.
- **META +11,43%**: ingresso al primo ciclo della seduta (14:07) su un upgrade di PT pubblicato alle 12:38. Realizzato +5,63 $, `entry_percentile` 0,450. L'esito è dimezzato dall'uscita del §8.
- **HOOD +2,90%** (non mover): +4,33 $ realizzati, con l'uscita che ha evitato 2,79 $ di drift negativo.
