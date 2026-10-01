# Alpha Miss Report — 2026-09-24

Contratto `alpha_miss_prompt_v2` · dossier `docs/evidence/dossier/2026-09-24.json` (`schema_version` 3.1, generato 2026-10-01T08:00:37Z, prezzi Alpaca SIP `adjustment=all`). Soglia mover `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30.

## 1. Decision card

1. **Nessun miss azionabile: 6 mover, 4 già a libro all'open** (`held_at_open_rate` 4/6). Gli altri due sono ribassi non detenuti: ARM −7,88% e ORCL −3,47%, sul tema Oracle "force majeure". Con un book long-only `net_opportunity_usd` è 0 per entrambi.
2. **META +4,50%: due vendite e un riacquisto S4 nella stessa seduta.** Venduta alle 14:22 @766,52 su un +0,131 (Citizens alza il target a $885), ricomprata alle 15:37 @767,07, rivenduta alle 18:52 @776,91 su uno 0,000 da un articolo fan-out su AST SpaceMobile. La prima uscita vale `exit_active_effect_usd` **−21,42 $**.
3. **Realizzato +10,84 $, tutto S4**: META +31,38 e +18,26, NOW +1,69, BA −40,49. BA è chiusa alle 15:37 perché una lettura single-model fallback a −0,04 ha fatto da controsegnale (F-059).

## 2. Stato carta

Fonte: `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (generato 2026-09-18T10:14+02:00). I cumulati si fermano al 17/09: non includono le sedute dal 18/09 a questa.

- Giorno **30/40** della finestra di osservazione (inizio 2026-08-03, `minimo_giorni`=40).
- Quota NO_NEWS dominante **13/30 = 43,3%**, sotto la soglia carta 0,60.
- S4 economico cumulato **−696,33 $** contro la banda ±200 $: **fuori banda**.
- `docs/evidence/longitudinal_panels.json` **non esiste**. I denominatori del §8 sono contati dalle occorrenze di `findings.json` (sedute distinte) e dichiarati come tali.

## 3. Miss del giorno

Il dossier ha 2 candidati in `candidati_miss`. Legacy `aggregati.cause_del_giorno` (invariato per il vincolo #288): {"BELOW_GATE":2}, `dominante`="BELOW_GATE". Come nei report precedenti, dove l'asse `actionability` di `funnel_v2` e il campo grezzo `causa` divergono, prevale il primo. `funnel_v2.conteggi_pipeline`={}: nessun candidato ha uno stadio oltre il gate né una guardia che lo abbia bloccato, quindi **oggi nessun FILTERED è possibile**.

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| ARM | −7,88% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[ARM].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only"; legacy `causa`="BELOW_GATE". Una sola riga, delle 18:06 e quindi a movimento in corso: "Arm Stock Dips Amid Oracle's 'Force Majeure' Reports", −0,20, fallback. Intenti: 16 `SKIP_ENTRY_FRESHNESS`, 8 `SKIP_FALLBACK`. `gross_opportunity_usd` 173,45 $, `accessible`=0. |
| ORCL | −3,47% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[ORCL].actionability`="NON_ACTIONABLE"; legacy `causa`="BELOW_GATE" (`max_score_own` −0,255, "Oracle shares fall as company invokes 'force majeure' over New Mexico data center project", GDELT 16:30). La notizia c'era prima dell'open: "Oracle Cites 'Force Majeure'…" (Bloomberg, pubblicata 12:37, ingerita 13:43) è stata però scorata **+0,04** (fallback). Il primo ensemble è −0,135 alle 13:33 ("What's Going On With Oracle Stock Thursday?"). 24 intenti, tutti `SKIP_ENTRY_GATE`. Anche col segno giusto e sopra gate, un ribasso non detenuto non si cattura long-only. |

**Conteggi**: NO_NEWS 0 · THIN_NEUTRAL 0 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 2. La somma di `gross_opportunity_usd` (legacy `costo_usd`) è 249,85 $ (ARM 173,45 + ORCL 76,40), con `net_opportunity_usd` 0 su entrambi e `avoidable_miss_count`=0.

Discontinuità da tenere presente su ORCL: il 24/09 l'operatore ha aggiunto 28 alias bare-stem a `ticker_lookup`, tra cui "Oracle" (charter, riga #566/F-077). L'ora del backfill rispetto alla seduta non è nel dossier, quindi resta DATA_INCOMPLETE quali righe ORCL ne abbiano beneficiato.

### Titoli catturati (mover detenuti all'open: 4 su 6)

Il P&L di seduta viene da `snapshot_apertura.actual_intraday_pnl_usd`.

| Simbolo | Return% | Detenuto da (nozionale all'open) | Esito di seduta |
|---|---:|---|---|
| META | +4,50% | S4, 1.440,30 $ (trade 1027) | PASSIVE_EXPOSURE, ma è uscita alle 14:22 @766,52: `actual_intraday_pnl_usd` **+42,89 $** contro `passive_pnl_usd` +64,31 $ (`exit_active_effect_usd` −21,42). Rientro con il trade 1028 alle 15:37, chiuso alle 18:52 a +18,26 $ (§4, §8). |
| INTC | +3,91% | S4, 1.751,70 $ (trade 1007) | PASSIVE_EXPOSURE, **+98,47 $** (residuo beta-1 +63,21 $). Nessuna riga rialzista spiega il movimento: TD Cowen "Reiterates Hold" a 0,000 e due fan-out negativi. |
| GM | −3,82% | S1, 844,51 $ | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` +0,08, "GM's AI Battery Play Could Chip Away at China's Data Center Grip", fallback, 18:58). **−28,22 $** (residuo −31,66 $). |
| WDC | −4,94% | S4, trade 373 | EXIT_RISK, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato` +0,40 su "Sandisk Dips Premarket…", articolo su un'altra società, fallback). P&L di seduta **DATA_INCOMPLETE**: `snapshot_apertura` riporta `qty_open` 0 con `missingness`=["exit_fill_qty_exceeds_trade_qty"], mentre `copertura_uscita` e il log worker (15:37, "WDC unprotected at −17.2% (qty 0.3347)") la danno ancora a libro (F-048). |

KPI: `held_at_open_rate` 4/6, `exit_signal_recall` **0/2**, `exit_conversion_rate` null (0/0), `active_signal_recall` null (0/0), `profitable_capture_rate` null (0/0).

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["META"],"chiusure":["META","BA","NOW","META"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | META | S4 | 15:37 | $767.0700 | 1.8855 | — | percentile 65.37%; denominatore intraday valido |
| OUT | META | S4 | — | $766.5200 | 1.9350 | +$31.38 | portfolio_sell |
| OUT | BA | S4 | — | $196.3400 | 7.1904 | −$40.49 | portfolio_sell |
| OUT | NOW | S4 | — | $138.1800 | 2.9791 | +$1.69 | portfolio_sell |
| OUT | META | S4 | — | $776.9100 | 1.8855 | +$18.26 | portfolio_sell |
<!-- alpha-miss-book:end -->

Un ingresso e quattro chiusure, tutti S4.

- **Ingresso: META alle 15:37 @767,07** (trade 1028), sul segnale 12532 +0,306 ("JP Morgan Maintains Overweight on Meta Platforms, Raises Price Target to $920", 15:28). Gate 0,367 con velocity 1,20. `quota_movimento_precedente_al_segnale` 0,68, `entry_percentile` 0,65, `mtm_eod` **+19,84 $**.
- **Chiusure** (`execution_decisions`):
  - META 14:22 `[below_entry_gate]` score +0,131;
  - BA 15:37 `[fallback_filtered]` (vedi §8);
  - NOW 18:07 `[below_entry_gate]` score 0,000, dopo 73,75 h di tenuta;
  - META 18:52 `[below_entry_gate]` score 0,000.

Realizzato +10,84 $. `drift_post_uscita` vale +21,42 $ sulla prima uscita META, +3,31 $ su BA, +1,28 $ sulla seconda META e −1,19 $ su NOW. Le 4 SELL non hanno `signal_id` (`decision_signal_id_coverage.by_reason_code.SELL` 0/4, `regressions`=["SELL"]). Guardia di contraddizione: 0 soppressi su 31 intenti tradabili. `invariante_rank_ranking_score`: 0 violazioni su 31.

## 5. Cecita' lato uscita

`copertura_uscita` conta 46 posizioni, con `n_indeterminati`=**0**: nessuna riga ha `cieco_lato_uscita: null`. Tre posizioni sono cieche e tutte ancora aperte:

| Ticker | Strategia | `ritorno_da_ingresso` | `ritorno_seduta` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---:|---|---:|
| VALE | S1 | **−7,38%** | −1,88% | 6 | `alpaca_benzinga` | 718,73 $ |
| UBS | S1 | −7,04% | +1,51% | 2 | `alpaca_benzinga` | 633,14 $ |
| CSCO | S4 | −3,68% | +0,51% | 2 | `alpaca_benzinga`, `gdelt_gkg` | 1.833,01 $ |

Nessuna delle tre è uscita in seduta: `ritorno_da_ingresso` è la perdita dall'ingresso al close, `ritorno_seduta` il solo movimento del 24/09. Rispetto al 23/09 entrano CSCO (l'unica S4, 24 intenti `SKIP_STALE`) e UBS, ed escono WDC (2 righe oggi) e SBUX (1 riga GDELT). Aggregato: 8 posizioni a copertura grezza nulla, 20 a copertura effective-timely nulla, 10 in perdita marcata. Il nozionale cieco sale a **3.184,87 $**, contro 1.510,66 $ il 23/09.

## 6. Backstop NO_NEWS

`no_news_backstop.population`: 31 simboli a zero righe `news_log`, **0 mover** e 31 non-mover (`return_missing`=0).

### 6a. Marker calendario

Nessun mover NO_NEWS, quindi non ci sono righe `observed_catalysts` da riportare. `mover_observed` 0/0, `non_mover_observed` 0/31: oggi nessun marker `CALENDAR` sui simboli a zero news. `calendario_earnings.status`="OBSERVED", `simboli_flaggati`=["COST"]: COST ha news (2 effective-timely), quindi non entra nel backstop.

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false. Il volume di seduta e l'etichetta mover si conoscono solo al close, quindi nessuno di questi valori era disponibile prima del movimento. Qui non si fissano soglie né si stimano false-positive rate (la valutazione ex-ante è in #451).

- Mediana della sorpresa di volume sui mover a zero news: **null** (n=0). Sui non-mover: **−9,36%** (n=31).

### 6c. Copertura raw di `news_log` per settore (tutti i settori)

Copertura **raw**, distinta dalla effective-timely di `copertura_articoli.per_settore` (oggi 45/96, 46,9% a livello di watchlist).

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news | calendario su zero news |
|---|---:|---:|---:|---:|
| energy | 6/6 | 100,0% | 0 | 0 |
| etf_broad | 4/4 | 100,0% | 0 | 0 |
| semis | 13/15 | 86,7% | 0 | 0 |
| media | 4/5 | 80,0% | 0 | 0 |
| industrials | 3/4 | 75,0% | 0 | 0 |
| consumer | 8/11 | 72,7% | 0 | 0 |
| healthcare | 6/9 | 66,7% | 0 | 0 |
| tech | 13/21 | 61,9% | 0 | 0 |
| materials | 1/2 | 50,0% | 0 | 0 |
| financials | 6/14 | 42,9% | 0 | 0 |
| telecom | 1/5 | **20,0%** | 0 | 0 |

In totale 65/96 simboli hanno almeno una riga (`watchlist_zero_news`=31, erano 42 il 23/09).

### 6d. Attribuzione fonti per ticker (#511 passo 2)

Per tutti i 31 ticker con `articoli_unici`=0 vale `fonti_osservate`={} e `articoli_unici_giorno` = `effective_timely_articles_giorno` = 0 (da `blind_set.per_ticker`). Tra parentesi `sedute_consecutive_zero_articoli`:

AMAT (1), AXP (1), AZN (2), BRK.B (1), C (2), CRM (1), CSCO (2), ERIC (2), HD (9), INFY (10, troncato dalla finestra), JD (5), JPM (2), MA (2), MMM (7), NKE (1), NVO (2), PFE (2), PG (4), PLTR (1), RDDT (4), SAP (7), SNOW (9), SONY (1), T (1), TMUS (3), TXN (2), UBS (2), V (1), VALE (6), VZ (1), WFC (2).

`ticker_allerta_zero_articoli` (≥5 sedute): HD, INFY, JD, MMM, SAP, SNOW, VALE.

Fonte presente ma non utile: nei 20 casi seguenti la fonte `alpaca_benzinga` ha reso N righe, ma nessuna effective-timely. SPY 26, AMZN 6, QQQ 5, XLK 3, BABA 2, CVX 2, HOOD 2, SOXX 2, e 1 riga ciascuno ABBV, ADBE, ASML, BIDU, F, IBM, JNJ, NFLX, NOW, SHEL, UNH, XOM.

Per fonte: `alpaca_benzinga` 113 articoli unici, di cui 69 effective-timely (61,1%); `gdelt_gkg` 15 su 15. La scelta dei connettori resta all'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Seduta piatta sugli indici (SPY −0,08%, QQQ −0,01%, `dispersione_sigma` 1,66%) con un tema idiosincratico sull'infrastruttura dati AI: la "force majeure" di Oracle sul data center del New Mexico.**

- **Ribassisti**: ORCL −3,47%, poi i nomi citati nelle stesse righe: ARM −7,88% ("Arm Stock Dips Amid Oracle's…"), DELL −2,51% ("Dell Stock Edges Lower…", taggata ORCL), e Blue Owl e Bloom Energy, fuori watchlist. WDC −4,94% e IBM −2,45% vanno nella stessa direzione, ma nessuna riga li collega al tema. L'auto è ribassista (GM −3,82%, F −2,63%) senza una riga esplicativa.
- **Rialzisti**: META +4,50% su una serie di rialzi di target price (Citizens $885, JPMorgan $920, Tigress $995, Raymond James $860); INTC +3,91% e AMD +2,38%. Nessuna riga spiega INTC. SOXX resta piatto (+0,06%): dentro i semis c'è dispersione, non una rotazione di settore.
- **Rispetto ai giorni precedenti**: ORCL scende per la seconda seduta (−3,11% il 23/09, su un'altra notizia). Il risk-off da tassi del 23/09 non si ripete. Oltre a questo il pattern non è chiaro.

Il legame ARM/DELL con ORCL è un'associazione dal testo dei titoli, non una causa verificata.

## 8. Segnalazioni

Tre finding esposti oggi, tutti lato uscita S4 e tutti su un mover o una posizione chiusa in seduta. I denominatori sono contati dalle occorrenze di `findings.json` (sedute distinte), perché `longitudinal_panels.json` non esiste.

### [F-013] META venduta alle 14:22 su un rialzo di target price scorato +0,131, e ricomprata alle 15:37 più in alto

- **Meccanismo e fonte**: §3 (catturati) e §4. Campi del dossier:
  - `chiusure[META]` #1: exit 766,52, qty 1,934968, `pnl_net` +31,38, `drift_post_uscita` 21,42;
  - `snapshot_apertura[META].exit_active_effect_usd` −21,42;
  - `ingressi[META]`: trade 1028, 15:37, entry 767,07, qty 1,885512;
  - `execution_decisions` 42936, "[below_entry_gate] … score=+0.131".
  Il segnale d'uscita 12477 è ISSUER_SPECIFIC e del segno giusto: "Citizens Maintains Market Outperform on Meta Platforms, Raises Price Target to $885". È pubblicato alle 13:11 e ingerito alle 14:20. La posizione esce perché +0,131 < 0,30, non perché la notizia sia negativa. Rientra 75 minuti dopo, sul JPMorgan +0,306.
- **Esposizione oggi**: 3 uscite S4 `below_entry_gate` (META due volte, NOW); 1 seguita da un rientro sullo stesso simbolo in seduta. F-013 conta 25 sedute distinte in `findings.json`.
- **Evidenza contraria**: se esistesse una banda fra ingresso e uscita, un +0,131 non avrebbe chiuso una posizione aperta sopra 0,30. Il prezzo di rientro non sarebbe stato superiore a quello d'uscita, e `exit_active_effect_usd` non sarebbe stato negativo su un titolo chiuso a +4,50%.
- **Non-occorrenza**: NOW esce sullo stesso codice con uno 0,000, non viene ricomprata e `drift_post_uscita` è −1,19 $: lì l'uscita ha evitato una piccola perdita.
- **Next evidence (read-only)**: invariato. Sulla finestra, per ogni SELL `below_entry_gate` con score dello stesso segno dell'ingresso, contare i BUY sullo stesso simbolo entro la seduta e sommare qty × (prezzo rientro − prezzo uscita).
- **Costo**: **1,04 $** (attribuita). Formula della serie: qty rientro × (entry rientro − exit) = 1,885512 × (767,07 − 766,52). Alternativa scartata: `exit_active_effect_usd` −21,42 $ come costo. Ignora il rientro, che recupera buona parte del movimento con `pnl_net` +18,26 $, quindi conterebbe due volte.

### [F-023] META rivenduta alle 18:52: il Raymond James +0,293 delle 18:27 è sovrascritto otto minuti dopo da uno 0,000 su un articolo AST SpaceMobile

- **Meccanismo e fonte**: §4. Campi:
  - `chiusure[META]` #2: exit 776,91, qty 1,885512, `pnl_net` +18,26, `drift_post_uscita` 1,28, `ore_tenuta` 3,25;
  - `copertura_articoli.segnali`: 12628 (+0,2925, ISSUER_SPECIFIC, "Raymond James Maintains Strong Buy on Meta Platforms, Raises Price Target to $860", 18:27) e 12637 (0,000, `attribution`="FANOUT", `relevance`="TAG_UNCONFIRMED", 18:35, "Why Is AST SpaceMobile Stock Surging on Thursday?", taggato META e GOOGL);
  - `execution_decisions` 45066, "[below_entry_gate] … generated 18:35 UTC, score=+0.000".
  S4 legge solo il segnale più recente per simbolo. Un segnale issuer-specifico appena sotto gate viene rimpiazzato da uno neutro, a confidenza 0,20, su un articolo che parla di un'altra società, e la posizione esce.
- **Esposizione oggi**: 1 uscita su un mover causata da una riga FANOUT più recente. F-023 conta 16 sedute distinte in `findings.json`.
- **Evidenza contraria**: se il finding fosse falso, la SELL delle 18:52 citerebbe il segnale 12628 (+0,2925) o un segnale ISSUER_SPECIFIC negativo. Cita invece "generated 18:35, score=+0.000", che è l'id 12637.
- **Non-occorrenza**: l'uscita delle 14:22 sullo stesso titolo non è di questo tipo. Il +0,131 è ISSUER_SPECIFIC e non sovrascrive un segnale più forte e più recente: è quello d'ingresso a essere vecchio di 20 ore.
- **Next evidence (read-only)**: sulla finestra, per ogni SELL S4 contare quelle il cui ultimo segnale ha `attribution`="FANOUT" mentre un segnale ISSUER_SPECIFIC più forte dello stesso simbolo è più recente di 4 h, e sommare qty × (close − exit).
- **Costo**: **1,28 $** (congetturale). Formula: `drift_post_uscita` = qty × (close − exit) = 1,885512 × (777,59 − 776,91). Scartato il controfattuale "tenere fino al giorno dopo", perché esce dalla seduta misurata.

### [F-059] BA chiusa alle 15:37 da una lettura single-model fallback a −0,04 (confidenza 0,40), esclusa dal ranking BUY ma usata come controsegnale

- **Meccanismo e fonte**: §4. Campi:
  - `chiusure[BA]`: exit 196,34, qty 7,19038, `pnl_net` −40,49, `drift_post_uscita` 3,31, `ore_tenuta` 23,25;
  - `snapshot_apertura[BA].exit_active_effect_usd` −3,31;
  - `execution_decisions` 43512, "[fallback_filtered] … generated 2026-09-23 16:19 UTC, score=+0.315".
  L'ultima lettura BA prima dell'uscita è il segnale 12527 delle 15:14 (`single:gpt-oss:20b-cloud`, `fallback_used`=true, −0,04, conf 0,40, `attribution`="UNKNOWN"/TAG_UNCONFIRMED). Il log worker delle 15:22 e delle 15:37 mette BA tra i "dropped … fallback signal(s) from BUY ranking (#108)". FIX-D preserva 8 segnali stantii "with no counter-signal" e BA non c'è: la lettura fallback conta come controsegnale. La ragione persistita cita invece il segnale d'ingresso 12338 (ensemble, `fallback_used`=false), quindi dalla riga di `execution_decisions` la causa reale dell'uscita non si ricostruisce.
- **Esposizione oggi**: 1 posizione S4 con segnale d'ingresso stantio e una sola lettura fallback successiva. F-059 conta 5 sedute distinte in `findings.json`. L'occorrenza del 18/09 è lo stesso simbolo con la stessa forma.
- **Evidenza contraria**: se le letture fallback non contassero come controsegnale, BA sarebbe stata preservata da FIX-D come AMAT, C, DELL, JNJ, JPM, NOW, PBR e PFE, oppure sarebbe uscita sul primo ensemble fresco (12547, −0,1225, 15:53). Non sarebbe uscita alle 15:37.
- **Non-occorrenza**: NOW, con segnale stantio dal 21/09 e senza letture fallback fino al ciclo delle 18:07, resta preservata da FIX-D fino all'ensemble 0,000 delle 17:43.
- **Next evidence (read-only)**: sulla finestra, per ogni SELL S4 `fallback_filtered`, verificare se l'ultima lettura prima della decisione ha `fallback_used`=true e se esiste un ensemble fresco successivo entro due cicli; prezzare l'uscita all'ensemble con l'isteresi di 2 cicli.
- **Costo**: **3,31 $** (misurata). Formula: `drift_post_uscita` = qty × (close − exit) = 7,19038 × (196,80 − 196,34). Scartato il controfattuale "uscita al primo ensemble fresco" (12547, 15:53, poi isteresi): richiede un prezzo di barra fuori dal dossier.

## 9. Appendice

### (a) Rendimenti della watchlist (`mercato.rendimenti`, 96 simboli, dal più alto al più basso)

| | | | |
|---|---|---|---|
| META +4,50% | INTC +3,91% | LLY +2,68% | AMD +2,38% |
| DIS +2,03% | V +1,79% | VZ +1,72% | UBS +1,51% |
| GOOGL +1,34% | AXP +1,23% | NVO +1,18% | MA +1,10% |
| TSM +1,03% | UNH +1,00% | PFE +0,82% | MU +0,81% |
| AZN +0,75% | XLV +0,63% | T +0,59% | XOM +0,56% |
| JNJ +0,56% | CSCO +0,51% | NFLX +0,50% | RDDT +0,49% |
| PLTR +0,42% | XLE +0,37% | WFC +0,34% | JPM +0,31% |
| CRM +0,27% | SHEL +0,20% | C +0,13% | CVX +0,07% |
| SOXX +0,06% | BAC +0,05% | AMZN +0,04% | ABBV +0,02% |
| GE −0,01% | QQQ −0,01% | XLF −0,02% | AMAT −0,03% |
| MRK −0,07% | SPY −0,08% | IWM −0,09% | ROKU −0,10% |
| BABA −0,15% | NKE −0,17% | BP −0,18% | TMUS −0,19% |
| SPCX −0,22% | SNOW −0,24% | XLK −0,32% | AAPL −0,33% |
| BRK.B −0,39% | NVDA −0,41% | SBUX −0,52% | MSFT −0,53% |
| MCD −0,55% | TSLA −0,57% | DB −0,70% | SAP −0,72% |
| TXN −0,72% | ADBE −0,73% | MRVL −0,75% | RIO −0,82% |
| CAT −0,83% | PANW −0,86% | SONY −0,91% | COST −0,91% |
| MS −1,04% | PG −1,16% | ASML −1,27% | AVGO −1,30% |
| GS −1,40% | PBR −1,42% | JD −1,51% | QCOM −1,51% |
| HD −1,53% | HOOD −1,53% | BA −1,57% | MMM −1,63% |
| CMCSA −1,86% | VALE −1,88% | NOK −1,88% | BIDU −1,89% |
| TM −1,91% | NOW −2,13% | ERIC −2,26% | INFY −2,33% |
| IBM −2,45% | DELL −2,51% | F −2,63% | WMT −2,66% |
| ORCL −3,47% | GM −3,82% | WDC −4,94% | ARM −7,88% |

Mover |r| ≥ 3%: 6 (2 su, 4 giù). `simboli_senza_dati`=[].

### (b) Checklist degli altri finding toccati

- [F-001] supported — `watchlist_zero_news` 31/96; effective-timely 45/96; 3 posizioni cieche lato uscita per 3.184,87 $ (§5).
- [F-008] supported (parziale) — l'uscita META delle 18:52 è su una riga FANOUT (§8, F-023); lo score è 0,000 e non invertito, quindi l'aggancio primario è F-023.
- [F-011] supported — SELL `signal_id` 0/4 (`decision_signal_id_coverage.regressions`=["SELL"]).
- [F-012] supported — `mapping_fanout_extra` 94 su 222 righe; `cause_del_giorno.quota_righe_fanout` 0,5.
- [F-019] supported — righe pre-open ingerite circa un'ora dopo: INTC 13:16→14:20, META Citizens 13:11→14:20, WDC 12:39→13:46, ORCL Bloomberg 12:37→13:43.
- [F-021] supported — primo ciclo portfolio con decisioni alle 14:07 UTC (`guard_decisions` 42804/42827), con l'apertura EDT alle 13:30.
- [F-030] contradicted (parziale) — META 15:37 con `quota_movimento_precedente_al_segnale` 0,68 (sotto 1) e `mtm_eod` +19,84 $: oggi l'unico ingresso ha chiuso la seduta in utile.
- [F-031] supported — 23 dei 31 intenti tradabili sono `SKIP_PYRAMIDING` (NOW 15, BA 5: S4; LLY 3: detenuta da **S1**, segnale 12553 +0,3675); in `guard_decisions` ne sono tracciati 2 su 23. LLY `counterfactual_return_1h` −0,80% su 2.197,84 $: il blocco di oggi non è costato.
- [F-040] not_exposed — i segnali ribassisti con |score| ≥ 0,30 (AVGO −0,42, MS −0,42, NFLX −0,36, GOOGL −0,30) sono tutti fallback.
- [F-043] supported — gli unici segnali non-fallback sopra gate in giornata sono rialzisti (META +0,306, LLY +0,3675).
- [F-048] supported — WDC trade 373 a `qty_open` 0 in `snapshot_apertura` (`exit_fill_qty_exceeds_trade_qty`) contro qty 0,3347 in `copertura_uscita` e nel log worker.
- [F-053] supported — Alpaca portfolio history timbra la seduta del 24/09 a 2026-09-25T00:00Z (equity 109.953,87).
- [F-076] supported — `testo_scorato` con `&#39;` / `&#34;` su ARM e ORCL.
- [F-082] not_exposed — 0 soppressi su 31 intenti valutabili.
- [F-089] not_exposed — CSCO (S4) senza segnali freschi oggi (24 `SKIP_STALE`): il meccanismo "segnale fresco sotto gate senza SELL" non si attiva.

### (c) Casi di successo

- **INTC +3,91%**: detenuta S4 all'open (1.751,70 $), `actual_intraday_pnl_usd` **+98,47 $**, residuo beta-1 +63,21 $. È il maggior contributo positivo del libro nella seduta.
- **META +4,50%**: due gambe in utile nonostante il churn. Trade 1027 chiuso a `pnl_net` +31,38 $, trade 1028 (ingresso del giorno sul JPMorgan +0,306) chiuso a +18,26 $.
