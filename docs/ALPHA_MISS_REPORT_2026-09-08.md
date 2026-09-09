# Alpha Miss Report — 2026-09-08

Fonte numeri: `docs/evidence/dossier/2026-09-08.json` (schema 2.8, generato 2026-09-09T08:00:30Z, Alpaca SIP `adjustment=all`). Nessun numero di mercato, copertura, funnel o cecità lato uscita è ricalcolato qui: dove il mio calcolo avrebbe potuto divergere ho letto il dossier. Log applicativi: `logs/containers/{worker,worker-inference,api,beat}-2026-09-08.log`. Periodo di sola osservazione attivo (`docs/evidence/OBSERVATION_CHARTER.md`, congelamento taratura fino al 2026-09-28): solo evidenza, nessuna proposta di taratura o fix.

## 1. Executive summary

**19 mover ≥3%** su 96 simboli watchlist (9 su, 10 giù), dispersione cross-sectional σ=2,50%, su indici quasi fermi (SPY −0,55%, QQQ −0,08%): giornata idiosincratica, non di beta. **10 mover su 19 catturati**: 6 già a libro all'apertura (INTC, NOK, AMD, AMAT, PBR, CRM — esposizione subita, nessuna decisione attiva) e 4 toccati da un ordine nella seduta (SPCX, QCOM, HOOD, NVO). **9 candidati miss**.

Causa prevalente: **THIN_NEUTRAL 5/9** (BIDU, F, TSLA, ARM, ADBE — notizia presente, segno per lo più corretto, magnitudine sotto il gate 0,30), poi **NO_NEWS 2/9** (INFY, SONY) e **WRONG_SIGN 2/9** (NOW, RDDT). Zero FILTERED e zero OUT_OF_STRATEGY_SCOPE. Caso limite della serie: **F** a −4,24% con score fan-out −0,2990 contro un gate 0,30 — **scarto 0,001**, ma inutilizzabile comunque perché long-only.

**Sette ingressi, tutti long, sei su sette in rosso a fine seduta** misurati fill→close (`mtm_eod`), sette su sette se si guarda il realizzato dei quattro chiusi in giornata. Due dei titoli comprati (HOOD −3,91%, NVO −3,09%) sono fra i dieci peggiori della watchlist, entrambi su segnali issuer-specific alti e non-fallback (0,414 e 0,409). Il miglior titolo della giornata, **INTC +9,05%**, era detenuto: il suo segnale issuer-specific più forte (0,498, "Intel Jumps 10%…", ore 17:09) è vissuto **7 minuti fra due cicli** ed è stato poi sostituito per dieci cicli filati, fino alla chiusura, da un macro fan-out a **−0,165**.

Book: equity fine giornata **109.910,06 $** (Alpaca), variazione **−63,61 $**, realizzato **−163,44 $** (interamente S4, S1 zero chiusure), MTM implicito del libro aperto **+99,83 $**. **37/96 simboli (38,5%) a zero righe `news_log`**: il valore più basso della finestra recente (48 il 09-01, 45 il 09-02, 50 il 09-03, 54 il 09-04). Copertura effective-timely 46/96 (47,9%).

## 2. Rendimenti — tabella completa (96 simboli)

Mover (|return| ≥ 3%) in grassetto. Soglia motivata in §3.

| Simbolo | Return % | Catturato |
|---|---:|---|
| **INTC** | **+9.05%** | sì (in portafoglio) |
| **NOK** | **+6.18%** | sì (in portafoglio) |
| **AMD** | **+5.90%** | sì (in portafoglio) |
| **TSLA** | **+3.98%** | no |
| **AMAT** | **+3.98%** | sì (in portafoglio) |
| **ARM** | **+3.74%** | no |
| **SPCX** | **+3.73%** | sì (ingresso S4 nella seduta) |
| **PBR** | **+3.53%** | sì (in portafoglio) |
| **QCOM** | **+3.17%** | sì (ingresso S4 nella seduta) |
| AVGO | +2.98% | no |
| ASML | +2.91% | sì (in portafoglio) |
| SHEL | +2.55% | sì (in portafoglio) |
| BP | +2.44% | sì (in portafoglio) |
| ORCL | +2.36% | no |
| TSM | +2.35% | sì (in portafoglio) |
| WDC | +2.14% | sì (in portafoglio) |
| VALE | +1.90% | sì (in portafoglio) |
| DELL | +1.86% | sì (in portafoglio) |
| SOXX | +1.64% | sì (in portafoglio) |
| PANW | +1.12% | no |
| XLE | +1.11% | sì (in portafoglio) |
| CAT | +1.05% | sì (in portafoglio) |
| UNH | +0.93% | sì (in portafoglio) |
| MRVL | +0.83% | sì (in portafoglio) |
| XOM | +0.75% | sì (in portafoglio) |
| CVX | +0.58% | sì (in portafoglio) |
| RIO | +0.54% | sì (in portafoglio) |
| VZ | +0.54% | no |
| XLK | +0.32% | sì (in portafoglio) |
| TXN | +0.19% | no |
| TMUS | +0.09% | no |
| MCD | +0.05% | no |
| AXP | -0.02% | no |
| CSCO | -0.03% | sì (in portafoglio) |
| GOOGL | -0.03% | sì (in portafoglio) |
| BRK.B | -0.04% | no |
| QQQ | -0.08% | sì (in portafoglio) |
| ROKU | -0.16% | sì (in portafoglio) |
| GS | -0.20% | no |
| DIS | -0.24% | no |
| ERIC | -0.30% | no |
| T | -0.31% | no |
| IWM | -0.45% | no |
| BAC | -0.46% | sì (in portafoglio) |
| SNOW | -0.50% | sì (in portafoglio) |
| BABA | -0.51% | no |
| META | -0.53% | no |
| SPY | -0.55% | sì (in portafoglio) |
| UBS | -0.56% | sì (in portafoglio) |
| PG | -0.59% | no |
| AMZN | -0.60% | no |
| CMCSA | -0.60% | no |
| COST | -0.61% | no |
| MMM | -0.62% | no |
| DB | -0.65% | no |
| GE | -0.66% | no |
| MS | -0.68% | sì (in portafoglio) |
| C | -0.71% | sì (in portafoglio) |
| BA | -0.72% | no |
| NKE | -0.78% | no |
| WMT | -1.02% | no |
| MSFT | -1.15% | no |
| AAPL | -1.17% | sì (in portafoglio) |
| IBM | -1.19% | no |
| MRK | -1.24% | sì (in portafoglio) |
| XLF | -1.38% | sì (in portafoglio) |
| JPM | -1.43% | sì (in portafoglio) |
| MA | -1.44% | no |
| MU | -1.61% | no |
| AZN | -1.63% | sì (ingresso S4 nella seduta) |
| SAP | -1.68% | no |
| V | -1.71% | no |
| NFLX | -1.89% | no |
| NVDA | -2.01% | sì (ingresso S4 nella seduta) |
| JD | -2.05% | no |
| LLY | -2.21% | sì (in portafoglio) |
| JNJ | -2.22% | sì (in portafoglio) |
| WFC | -2.23% | no |
| GM | -2.24% | sì (in portafoglio) |
| HD | -2.29% | no |
| PLTR | -2.31% | no |
| PFE | -2.32% | sì (in portafoglio) |
| SBUX | -2.35% | sì (in portafoglio) |
| XLV | -2.52% | sì (in portafoglio) |
| TM | -2.87% | no |
| ABBV | -2.99% | sì (in portafoglio) |
| **NVO** | **-3.09%** | sì (ingresso S4 nella seduta) |
| **RDDT** | **-3.29%** | no |
| **ADBE** | **-3.47%** | no |
| **CRM** | **-3.90%** | sì (in portafoglio) |
| **HOOD** | **-3.91%** | sì (ingresso S4 nella seduta) |
| **SONY** | **-4.19%** | no |
| **F** | **-4.24%** | no |
| **INFY** | **-4.87%** | no |
| **NOW** | **-4.99%** | no |
| **BIDU** | **-6.96%** | no |

Nessun simbolo senza barre: `mercato.simboli_senza_dati` è vuoto, 96/96 coperti.

## 3. Miss classificati

**Soglia |return| ≥ 3%** — la stessa usata dal dossier (`soglia_mover: 0.03`) e da tutti i report precedenti della serie: con σ cross-sectional 2,50% corrisponde a ~1,2σ, cioè il movimento oltre il quale un titolo si stacca dal rumore di giornata dell'universo. Cambiarla romperebbe la confrontabilità della serie in `market_daily.jsonl`.

I 9 candidati sono i mover **non detenuti e non tradati**. Sette dei nove sono ribassisti: il libro è long-only, quindi per quelli l'opportunità *accessibile* misurata dal dossier è 0,00 $ (`accessible_opportunity_usd`), e il lordo close-to-close × 2.200 $ è riportato solo per confrontabilità con la serie storica.

| Simbolo | Return % | Categoria | Evidenza |
|---|---:|---|---|
| BIDU | −6.96% | THIN_NEUTRAL | 3 articoli. Massimo score "proprio" **−0,099** (14:00, ISSUER_SPECIFIC, "What's Going On With Baidu Stock Tuesday?"): segno corretto, un terzo del gate. Terza riga alle 17:30 è un fan-out **+0,12** da un pezzo su Tesla/Uber robotaxi, di segno opposto al titolo. `quota_righe_fanout` 0,33. Lordo 153,05 $. |
| NOW | −4.99% | WRONG_SIGN | Una sola riga, e con **segno opposto**: score **+0,26**, ISSUER_SPECIFIC/`subject_ticker=NOW`, ma l'articolo è "Robinhood To Rally Around 23%? Here Are 10 Top Analyst Forecasts For Tuesday" — un digest multi-ticker la cui headline parla di HOOD. `quota_righe_fanout` 1,0: quarta seduta su cinque in cui NOW ha come unica fonte un pezzo di rassegna. Lordo 109,80 $. |
| INFY | −4.87% | NO_NEWS | Zero righe `news_log`, zero segnali. Settore `tech`, uno dei 37 simboli a copertura nulla. Lordo 107,18 $. |
| F | −4.24% | THIN_NEUTRAL | Score fan-out **−0,2990** alle 19:06 (lettera dell'amministrazione al CEO su CATL/Geely): segno corretto, contenuto pienamente ticker-specifico, e **0,001 sotto il gate 0,30** — il margine più stretto mai registrato nella serie. Nessun canale "proprio" (`max_score_own` null): l'articolo è marcato TAG_UNCONFIRMED nonostante il testo nomini Ford tre volte. Comunque non tradabile: ribassista, libro long-only. Lordo 93,30 $. |
| SONY | −4.19% | NO_NEWS | Zero righe `news_log`, zero segnali. Lordo 92,26 $. |
| TSLA | +3.98% | THIN_NEUTRAL | 8 segnali, il volume più alto della giornata dopo HOOD. Massimo "proprio" **+0,138** (15:25, "Tesla, XPENG Push Humanoid Robots Toward Mass Production"): segno corretto, **scarto 0,162 dal gate**. Due righe su otto valgono 0,000 esatto (lo stesso pezzo "How To Trade SPY, QQQ, AAPL…" scorato due volte alle 15:20 e 15:45). Dalle 17:23 alla chiusura il segnale attivo è il macro fan-out a **−0,2325**, di segno opposto al titolo. Unico mover ENTRY_OPPORTUNITY rialzista non catturato assieme ad ARM. Lordo 87,48 $, netto accessibile 21,48 $. |
| ARM | +3.74% | THIN_NEUTRAL | Una riga, ISSUER_SPECIFIC, headline corretta ("What's Going On With Arm Holdings Stock Tuesday?"), score **+0,028** — segno giusto, magnitudine praticamente nulla: il dossier lo classifica `OFF_TOPIC_NON_DECIDIBILE`. Lo stesso articolo, in fan-out, ha prodotto le uniche righe di INTC (+0,036) e AMD (+0,020, fallback) di metà mattina. Lordo 82,38 $, netto accessibile 34,42 $. |
| ADBE | −3.47% | THIN_NEUTRAL | Una sola riga, fan-out da "Oracle Could Swing By $47.8 Billion After Earnings", score **0,000 esatto**: presenza formale di copertura, contenuto informativo nullo su Adobe. Equivalente pratico di NO_NEWS. Lordo 76,36 $. |
| RDDT | −3.29% | WRONG_SIGN | 3 righe, tutte **positive** (0,000 / +0,192 / +0,100) contro un titolo a −3,29%. Le due non nulle sono dichiarazioni del CEO su download e retention (18:11, 18:29), cioè materiale rialzista pubblicato a movimento già avvenuto. Nessuna riga ISSUER_SPECIFIC: tutte TAG_UNCONFIRMED. Lordo 72,36 $. |

Conteggi: **NO_NEWS 2 · THIN_NEUTRAL 5 · WRONG_SIGN 2 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0**.

Il classificatore meccanico del dossier (`cause_del_giorno`) usa una tassonomia diversa e più grezza — NO_NEWS 2, BELOW_GATE 5, OFF_TOPIC_NON_DECIDIBILE 2 — perché non legge il testo degli articoli. Le due divergenze sono NOW e RDDT, che il dossier mette sotto BELOW_GATE/OFF_TOPIC e che io classifico WRONG_SIGN dopo aver letto le headline: in entrambi i casi il segno del punteggio è opposto al movimento, non semplicemente piccolo.

**Zero FILTERED.** Verificato: nella giornata non esiste una sola riga `s4_intent_events` con `reason_code='RANK_OUTSIDE_TOP_N'` e `is_tradable=true` (22 righe RANK_OUTSIDE_TOP_N, tutte su simboli già detenuti). Nessun candidato tradabile è stato tagliato dal ranking oggi.

## 4. Titoli catturati — esito

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["NVO","QCOM","HOOD","SPCX","AZN","NVDA","SPCX"],"chiusure":["CRM","HOOD","QCOM","SPCX","NVDA"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | NVO | S4 | 14:07 | $45.8611 | 31.3115 | — | percentile 93.60%; denominatore intraday valido |
| IN | QCOM | S4 | 14:07 | $176.5000 | 8.1359 | — | percentile 38.98%; denominatore intraday valido |
| IN | HOOD | S4 | 14:22 | $124.1800 | 11.5656 | — | percentile 86.90%; denominatore intraday valido |
| IN | SPCX | S4 | 15:37 | $152.8000 | 9.4232 | — | percentile 77.69%; denominatore intraday valido |
| IN | AZN | S4 | 16:22 | $160.1300 | 8.9792 | — | percentile 16.01%; denominatore intraday valido |
| IN | NVDA | S4 | 17:52 | $225.9800 | 6.3715 | — | percentile 12.75%; denominatore intraday valido |
| IN | SPCX | S4 | 18:52 | $153.6400 | 9.3552 | — | percentile 86.21%; denominatore intraday valido |
| OUT | CRM | S4 | — | $247.1900 | 5.1797 | −$106.01 | portfolio_sell |
| OUT | HOOD | S4 | — | $121.0900 | 11.5656 | −$36.53 | portfolio_sell |
| OUT | QCOM | S4 | — | $174.4700 | 8.1359 | −$17.31 | portfolio_sell |
| OUT | SPCX | S4 | — | $152.8400 | 9.4232 | −$1.14 | portfolio_sell |
| OUT | NVDA | S4 | — | $225.6400 | 6.3715 | −$2.45 | hold_minimum_expiry |
<!-- alpha-miss-book:end -->

Sei mover erano già a libro all'apertura (**PASSIVE_EXPOSURE**, nessuna decisione attiva nella seduta): INTC +9,05%, NOK +6,18%, AMD +5,90%, AMAT +3,98%, PBR +3,53%. Il sesto, **CRM −3,90%**, è l'unico classificato **EXIT_RISK** ed è stato chiuso (sotto).

Quattro mover hanno avuto un ordine nella seduta. Insieme a essi il libro ha aperto altri tre ingressi su non-mover (AZN, NVDA, e il secondo SPCX). Tutti e sette gli ingressi sono S4 e long.

| Simbolo | Ingresso UTC | Prezzo | `entry_percentile` | Esito | Nota |
|---|---|---:|---:|---|---|
| NVO | 14:07 | 45,86 | 0,936 | aperta, MTM EOD **−21,95 $** | Comprata sul giorno in cui il titolo fa **−3,09%**. Segnale 9854, +0,409, ISSUER_SPECIFIC non-fallback ("Wegovy for Overweight Young Children… Shows Effectiveness"). `quota_movimento_precedente_al_segnale` 0,669. |
| QCOM | 14:07 | 176,50 | 0,390 | chiusa 16:52 @174,47, **−17,31 $** (`portfolio_sell`) | Il funnel la marca **BAD_FILL**: fill 176,50 contro close 174,09, cioè sopra la chiusura di un titolo che pure ha fatto **+3,17%**. Segnale 9861 +0,424 (accordo AI chip con Amazon). L'uscita nasce dal fatto che il segnale *più recente* alle 16:32 vale 0,284 — sotto gate — pur essendo una headline positiva ("Strong Engagement With Another Hyperscaler Beyond Amazon"), mentre quello delle 16:25 valeva 0,382. Drift post-uscita −3,09 $. |
| HOOD | 14:22 | 124,18 | 0,869 | chiusa 16:52 @121,09, **−36,53 $** (`portfolio_sell`) | La perdita realizzata più grande fra gli ingressi del giorno. Comprata sul titolo che fa **−3,91%**, su segnale 9867 +0,414 ISSUER_SPECIFIC non-fallback. Drift post-uscita −43,37 $: l'uscita ha evitato altra perdita. |
| SPCX (1) | 15:37 | 152,80 | 0,777 | chiusa 18:07 @152,84, **−1,14 $** (`portfolio_sell`) | Unico ingresso del giorno con MTM EOD positivo (+6,31 $ misurato fill→close). Il funnel la marca **CAUGHT** e `net_profitable: true`. |
| SPCX (2) | 18:52 | 153,64 | 0,862 | aperta, MTM EOD **−1,59 $** | Ricomprata 45 minuti dopo la vendita, a **0,80 $/azione più caro**. `quota_movimento_precedente_al_segnale` **1,038**: il movimento era già più che completo. |
| AZN | 16:22 | 160,13 | 0,160 | aperta, MTM EOD **−0,81 $** | Non-mover (−1,63%). Segnale 9957 +0,566 (approvazione FDA). `quota_movimento_precedente_al_segnale` 0,977. |
| NVDA | 17:52 | 225,98 | 0,128 | chiusa 19:37 @225,64, **−2,45 $** (`hold_minimum_expiry`) | Non-mover (−2,01%). Il `signal_score` persistito sul trade è **0,2663**, cioè *sotto* il gate 0,30: è passato perché il moltiplicatore di velocità (×1,20, `SIGNAL_VELOCITY_BOOST`) lo ha portato a 0,3196. L'articolo è "Why Oracle Stock is the Trade to Watch After OpenAI's AGI Claim" — un pezzo su Oracle, mappato su NVDA in fan-out. |

Chiusura di una posizione ereditata: **CRM**, entrata il 09-04 alle 18:37 su un segnale a 0,744, chiusa il 09-08 alle 14:22 a 247,19, **−106,01 $** — la perdita realizzata più grande della giornata, 115,75 ore di detenzione, drift post-uscita +9,99 $.

Scomposizione del dossier (`decision_quality`): P&L intraday effettivo del libro **−161,63 $**, di cui **−132,57 $** spiegati da beta di mercato 1, **−73,24 $** passivi, **−118,35 $** di selezione e **+29,96 $** di effetto uscita. Gli assi non sono additivi per costruzione (`counterfactual_axes_are_additive: false`).

## 5. Cecità lato uscita

Dal dossier (`copertura_uscita`, non ricalcolato): 43 posizioni vive all'open RTH, 18 a copertura nulla, 24 a copertura effettiva nulla, 9 in perdita marcata ≥3% dall'ingresso, **3 cieche lato uscita**, 2 delle quali ancora aperte. **Zero indeterminati** (`n_indeterminati: 0`): nessuna riga con `cieco_lato_uscita: null`, quindi su nessuna posizione il dato è mancante. Nozionale cieco complessivo **2.725,04 $**.

| Ticker | Sleeve | `ritorno_da_ingresso` | Sedute consecutive senza righe | `fonti_osservate_finestra` | Stato |
|---|---|---:|---:|---|---|
| CRM | S4 | **−7,60%** | 2 | `alpaca_benzinga` | uscita nella seduta (exit 247,19) |
| PFE | S1 | **−3,14%** | 2 | `alpaca_benzinga` | ancora aperta |
| UNH | S1 | **−6,27%** | 3 | `alpaca_benzinga` | ancora aperta |

Attenzione a non confondere le due misure: `ritorno_da_ingresso` è la perdita subita mentre la posizione era detenuta e termina al prezzo d'uscita quando l'uscita è avvenuta intraday; `ritorno_seduta` è il movimento del titolo fino al close. Per CRM sono −7,60% e −3,90%; per UNH sono −6,27% e **+0,93%** — cioè UNH ha chiuso la seduta in rialzo pur restando in perdita del 6,27% dall'ingresso, e non ha comunque prodotto una sola riga di notizia da tre sedute.

`fonti_osservate_finestra` non è vuota su nessuna delle tre: `alpaca_benzinga` ha reso qualcosa su questi ticker nella finestra 08-25→09-08, semplicemente non nella seduta. **UNH è cieca per la terza seduta consecutiva** ed è già comparsa in questa sezione nel report del 09-04 (allora 2 sedute, −7,13% dall'ingresso): il fenomeno si sta allungando, non chiudendo.

## 6. Backstop NO_NEWS

Popolazione: 37 simboli a zero righe `news_log`, di cui **4 mover** (CRM, INFY, PBR, SONY — due di essi, CRM e PBR, erano detenuti) e 33 non-mover.

**Marker calendario.** `CALENDAR` compare su **un solo simbolo**, WMT, che è un **non-mover** (−1,02%): evento `dividend` del 2026-09-08 dall'Alpaca Corporate Actions API. **Zero mover** hanno un evento di calendario osservato (`mover_observed: 0` su 4). Il marker significa soltanto che il calendario societario riportava un evento: non implica l'esistenza di un segnale sentiment né di un ordine. Su tutte e 37 le righe il calendario earnings resta indisponibile (`missingness: ["earnings_calendar_unavailable"]`, `status: UNKNOWN`), quindi la copertura del backstop è limitata alle corporate action.

**Volume.** Mediana `adv_ratio` dei mover a zero news **0,3997** contro **0,0045** dei non-mover — differenza di due ordini di grandezza (il valore mediano dei non-mover è quello di MCD, sostanzialmente a volume medio). Fra i mover a zero news i valori sono SONY 1,449, PBR 1,410, INFY 1,389, CRM 1,064; **ERIC**, non-mover a −0,30%, sta a 0,659, sotto la propria media a 20 giorni. Il non-mover col rapporto più alto della popolazione è UNH a 1,733 — sopra tutti i mover — il che da solo mostra che il volume non separa i due gruppi caso per caso, solo in mediana. RDDT non appartiene a questa popolazione: ha tre righe `news_log`. **Caveat vincolante**: il blocco è marcato `temporal_validity: POST_HOC_EOD` e `valid_for_signal_evaluation: false` — volume di sessione ed etichetta mover sono noti **solo alla chiusura**. Non sto affermando che questo valore fosse disponibile prima del movimento, non scelgo una soglia e non stimo un tasso di falsi positivi operativo. La valutazione ex-ante pre-registrata è separata, in #451.

**Copertura raw per settore** (righe `news_log` grezze, popolazione intera, zero inclusi). Da non mescolare con la copertura *effective-timely* di `copertura_articoli.per_settore`, che è più restrittiva (ISSUER_SPECIFIC + timing anticipatorio/concorrente, deduplicata):

| Settore | `ticker_with_news` / `ticker_universe` | `raw_news_coverage_rate` | Mover a zero news | Calendario osservato | Copertura effective-timely (confronto) |
|---|---:|---:|---:|---:|---:|
| etf_broad | 4 / 4 | 100,0% | 0 | 0 | 75,0% |
| semis | 12 / 15 | 80,0% | 0 | 0 | 60,0% |
| telecom | 4 / 5 | 80,0% | 0 | 0 | 60,0% |
| healthcare | 7 / 9 | 77,8% | 0 | 0 | 66,7% |
| energy | 4 / 6 | 66,7% | 1 (PBR) | 0 | 33,3% |
| tech | 13 / 21 | 61,9% | 3 (CRM, INFY, SONY) | 0 | 52,4% |
| media | 3 / 5 | 60,0% | 0 | 0 | 40,0% |
| financials | 8 / 14 | 57,1% | 0 | 0 | 57,1% |
| industrials | 2 / 4 | 50,0% | 0 | 0 | 25,0% |
| consumer | 2 / 11 | 18,2% | 0 | 1 (WMT) | 9,1% |
| **materials** | **0 / 2** | **0,0%** | 0 | 0 | **0,0%** |

Due settori sono strutturalmente scoperti: **materials 0 su 2** (RIO, VALE — zero righe grezze e zero effective-timely) e **consumer 2 su 11**, che con 11 simboli è il buco più grande in valore assoluto. Nessuno dei due ha prodotto mover oggi, quindi il buco non è costato nulla in questa seduta.

## 7. Pattern osservato

**Rotazione dentro semis/hardware legacy ed energia, contro software enterprise e servizi IT, su indici quasi fermi.** Non è beta: SPY −0,55%, QQQ −0,08%, ma σ cross-sectional 2,50%.

Lato forte, il gruppo è compatto e coerente: INTC +9,05%, NOK +6,18%, AMD +5,90%, AMAT +3,98%, ARM +3,74%, QCOM +3,17%, AVGO +2,98%, ASML +2,91%, TSM +2,35%, WDC +2,14%, SOXX +1,64% — 11 nomi su 15 del settore `semis`, più l'energia al seguito (PBR +3,53%, SHEL +2,55%, BP +2,44%, XLE +1,11%, XOM +0,75%). Il catalizzatore è leggibile nei titoli della giornata: upgrade Northland su Intel a Outperform con PT 120 $ (15:46) e "Intel Jumps 10% as Analyst Says Musk's Terafab Could Give Foundry Much-Needed Scale" (17:09).

Lato debole, software e servizi: NOW −4,99%, INFY −4,87%, CRM −3,90%, ADBE −3,47%, più i nomi esteri/consumer discretionary BIDU −6,96%, INFY, SONY −4,19%, F −4,24%. L'articolo macro più diffuso della seduta — "S&P 500, Nasdaq Slip as $98 Brent Reignites Inflation Fears: Stock Market Today", 17:16–17:23 — è coerente con il petrolio forte, ma in pipeline ha prodotto **solo punteggi negativi sui semiconduttori** (INTC −0,165, NVDA −0,150, QCOM −0,154, TSLA −0,2325), cioè esattamente il gruppo che stava salendo: fan-out di segno rovesciato sul lato giusto della rotazione.

**Ricorrenza rispetto ai giorni precedenti.** È la stessa rotazione del 09-04 (semis/hardware su, software/growth giù), con **NOW e INFY fra i peggiori in entrambe le sedute** e INTC/AMD/AMAT/NOK fra i migliori in entrambe. Il 09-01 era la rotazione speculare (software giù, energia su); il 09-02 di nuovo software giù contro semis su. Quattro sedute su cinque della finestra mostrano lo stesso asse semis-vs-software, con il segno che si mantiene: non è un'inversione che si alterna, è un tema che persiste. Anche il modo in cui la pipeline lo vede è ricorrente: il 09-01 avevo annotato che l'articolo tematico del giorno era mappato su nove ticker software e zero petroliferi individuali; oggi l'articolo tematico è mappato su quattro semiconduttori con segno negativo mentre i semiconduttori salivano. La mappatura fan-out degli articoli macro continua a produrre segnale di segno arbitrario rispetto al gruppo che il pezzo descrive.

## 8. Segnalazioni

Ogni voce è agganciata a un id di `docs/evidence/findings.json`.

[F-051] **Il top-N di S4 è saturo di candidati non azionabili.** Su 109 slot top-5 assegnati nella giornata, **102 (93,6%) sono andati a simboli già detenuti** (`held_at_rank=true`), e le disposizioni finali dei 109 intent classificati sono 54 `SKIP_PYRAMIDING` + 48 `SKIP_IDEMPOTENCY` contro 7 `SUBMITTED`. Caso esemplare, slot 16:52: rank 1–5 = AZN, XLE, XOM, SPCX, NVO, **tutti e cinque già detenuti e tutti e cinque skippati**; rank 6 = INTC (ranking_score 0,411, il miglior titolo della giornata) e rank 7 = CVX, entrambi tagliati per `RANK_OUTSIDE_TOP_N`. Firma già nota anche allo slot 14:07, dove rank 3 = SNOW con un segnale vecchio di **3 giorni e 23 ore** che occupa uno slot per finire in `SKIP_PYRAMIDING`. **Oggi non è costato nulla in modo dimostrabile**: zero righe `RANK_OUTSIDE_TOP_N` con `is_tradable=true`, cioè nessun candidato realmente comprabile è stato tagliato dal ranking.

[F-023] **Il segnale più forte della giornata è vissuto sette minuti e non ha mai incontrato un ciclo.** INTC, miglior mover della watchlist a **+9,05%**: segnale 9984 non-fallback a **+0,498** generato alle **17:09** su "Intel Jumps 10% as Analyst Says Musk's Terafab Could Give Foundry Much-Needed Scale" (ISSUER_SPECIFIC). I cicli portfolio girano alle 17:07 e alle 17:22; alle **17:16** arriva il macro fan-out "S&P 500, Nasdaq Slip as $98 Brent Reignites Inflation Fears" a **−0,165**, e siccome S4 tiene per ogni simbolo solo il segnale *più recente*, da 17:22 fino alla chiusura (10 cicli consecutivi, `guard_decisions` signal_id=9984) il segnale attivo su INTC è quello negativo. Il segnale a 0,498 non è mai stato valutato da nessun ciclo. Stesso meccanismo su TSLA (da 17:23 il segnale attivo è il fan-out a −0,2325, contro un titolo a +3,98%). Costo `null`: INTC era detenuto e `is_tradable=false` per la guardia anti-pyramiding, quindi nessun ordine era comunque possibile — ma il meccanismo è identico a quello che nelle occorrenze precedenti ha chiuso posizioni.

[F-009] **Il gate 0,30 scarta segnali col segno corretto su tre mover.** F: fan-out **−0,2990** contro gate 0,30, **scarto 0,001**, il margine più stretto mai registrato nella serie (precedente: MU a 0,042 il 09-04); TSLA: own **+0,138**, scarto 0,162; ARM: own **+0,028**, scarto 0,272. In tutti e tre i casi il segno è quello giusto. Lordo close-to-close × 2.200 $ = **263,16 $** (F 93,30 + TSLA 87,48 + ARM 82,38), riportato per confrontabilità con la serie; l'accessibile misurato dal dossier sui soli due rialzisti non detenuti è TSLA 21,48 $ + ARM 34,42 $ = 55,90 $ (F è ribassista, libro long-only, accessibile 0).

[F-043] **Il gate seleziona magnitudine, non direzione.** I sette ingressi della seduta sono tutti long e tutti su segnali ≥0,30 (dopo boost di velocità); i rendimenti di giornata dei titoli comprati sono NVO −3,09%, HOOD −3,91%, QCOM +3,17%, AZN −1,63%, NVDA −2,01%, SPCX +3,73% (×2) — **quattro su sei negativi**, media −0,62%. Due dei titoli comprati sono fra i dieci peggiori della watchlist. Rispetto all'occorrenza dell'08-24 la firma è attenuata (allora 9 su 9 rialzisti con chiusura media −2,02%), qui sono 6 ingressi su 7 in rosso a fine seduta misurati fill→close (`mtm_eod`), 7 su 7 se si guarda il realizzato dei quattro chiusi in giornata. Costo attribuito **81,78 $**: realizzato dei quattro chiusi in giornata (QCOM −17,31 + HOOD −36,53 + SPCX −1,14 + NVDA −2,45 = −57,43) più MTM EOD dei tre ancora aperti (NVO −21,95 + AZN −0,81 + SPCX −1,59 = −24,35).

[F-001] **Copertura news bassa.** 37/96 simboli (38,5%) a zero righe `news_log`, e questo è il **valore migliore** della finestra recente (48/45/50/54 nelle quattro sedute precedenti) — ma la copertura effective-timely resta a 46/96 (47,9%) e due settori sono a zero o quasi: materials 0/2 grezzo, consumer 2/11. I due miss NO_NEWS puri (INFY −4,87%, SONY −4,19%) sommano un lordo close-to-close × 2.200 $ di **199,44 $**; entrambi ribassisti, quindi accessibile 0. Quattro dei 37 simboli scoperti erano mover, due dei quali detenuti (CRM, PBR): per PBR (+3,53%) l'esposizione è stata subita senza alcuna informazione, per CRM la mancanza ha coinciso con la cecità lato uscita (§5).

[F-011] **Il ramo d'uscita resta non ricostruibile per chiave esterna.** Su 682 `execution_decisions` della giornata il fill rate di `signal_id` è 99,1% (676/682) — nettamente meglio delle occorrenze passate — ma la distribuzione è polarizzata: BUY 7/7, SKIP_THRESHOLD 644/644, SKIP_FALLBACK 15/15, SKIP_STALE 3/3, e **SELL 0/5**. Tutte e cinque le vendite della giornata sono prive di `signal_id`; `decision_signal_id_coverage.regressions` elenca esattamente `["SELL", "SKIP_PYRAMIDING"]` (quest'ultimo 7/8). Il ramo d'ingresso è tracciabile, quello d'uscita no.

[F-019] **Un segnale sopra gate nasce già scaduto e resta inutilizzabile per nove cicli.** AZN, segnale 9833, score **+0,423** (sopra gate) generato alle 13:31 su "AstraZeneca Announces Tozorakimab Demonstrates Reduction…": disposizione **`SKIP_ENTRY_FRESHNESS` a ogni ciclo dalle 14:07 alle 16:07** — nove cicli consecutivi — perché l'articolo a monte supera già `MAX_NEWS_AGE_HOURS=2` quando il primo ciclo lo guarda. L'ingresso arriva solo alle 16:22 su un secondo articolo (9957, +0,566). Costo `null` e va detto che **stavolta il ritardo ha giovato**: AZN ha chiuso a −1,63% e l'ingresso posticipato ha subito un MTM di soli −0,81 $. Registro l'occorrenza per il meccanismo, non per il danno.

[F-013] **Churn intraday su SPCX.** Venduta alle 18:07 a 152,84 $ (flag `Exit hysteresis (2 cycles)` alle 17:52), **ricomprata alle 18:52 a 153,64 $**: 45 minuti, stesso simbolo, stessa sessione, **0,80 $/azione più caro** su 9,36 azioni. Costo attribuito **8,62 $** = 1,14 $ realizzati sulla prima gamba + 7,48 $ di peggior prezzo di rientro. Manifestazione dell'assenza di banda fra gate d'ingresso (0,30) e soglia d'uscita.

[F-030] **La notizia arriva a movimento fatto.** Mediana di `quota_movimento_precedente_al_segnale` sui sette ingressi: **0,849**; quattro dei sette sopra 0,95 (AZN 0,977, NVDA 0,966, SPCX-2 **1,038**, SPCX-1 0,849). Mediana `entry_percentile` **0,777** contro una mediana mobile a 20 giorni di 0,643: si è comprato più in alto del solito. Il caso oltre il 100% è SPCX alle 18:52, entrata quando il movimento della giornata era già più che completo: costo **1,59 $** (MTM EOD).

[F-012] **Un ordine nasce da un articolo su una società terza.** L'ingresso NVDA delle 17:52 (trade 987) poggia sul segnale 10014, generato da "Why Oracle Stock is the Trade to Watch After OpenAI's AGI Claim" — un pezzo su Oracle, mappato su NVDA in fan-out. Il trade chiude a **−2,45 $** per `hold_minimum_expiry`. Sull'intera giornata la pipeline ha 202 righe `news_log` per 122 articoli unici, con **118 mappature TAG_UNCONFIRMED contro 84 ISSUER_SPECIFIC** e 80 mappature fan-out extra; fra i nove candidati miss `quota_righe_fanout` complessiva è 0,632. Costo **2,45 $**.

[F-049] **Degrado dell'ensemble a metà sessione, senza allerta.** 64 timeout Ollama a 90 s nella giornata (33 su `gpt-oss:20b-cloud`, 31 su `glm-5.2:cloud`), con **80/214 segnali in fallback (37,4%)**; la concentrazione oraria è netta: 15:00Z 24/51 (47,1%) e 16:00Z **20/31 (64,5%)**, contro 2/9 alle 19:00Z. Non è l'outage completo delle occorrenze precedenti ma un degrado parziale che ha investito la finestra in cui sono state prese le decisioni su HOOD e QCOM. Nessun alert è arrivato — per il motivo descritto nella voce seguente. Costo `null`: i due ingressi persi in quella finestra hanno segnali non-fallback, quindi non attribuibili al degrado.

[F-071] **Nuovo. Il breaker del fallback spara e l'allerta muore in un'eccezione.** `logs/containers/worker-inference-2026-09-08.log`, 15:08:56Z: `WARNING … Fallback breaker alert callback failed for count=3: asyncio.run() cannot be called from a running event loop`. Il breaker ha rilevato correttamente la soglia (count=3, coerente col picco di fallback delle 15:00Z) e il callback di notifica ha sollevato un'eccezione invece di inviare. Aggravante minore: la chiave Redis si chiama `fallback:breaker_fired_at` ma contiene `1`, cioè un contatore e non un timestamp — non è possibile sapere da lì *quando* ha sparato. **Id nuovo giustificato**: F-049 attribuisce l'assenza di allerta al breaker come codice morto, meccanismo riparato da #427/PR #463; qui il breaker è vivo e funzionante e a fallire è il canale di notifica, con stack trace, punto di codice e correzione distinti — registrarlo sotto F-049 renderebbe falsa la descrizione di quel finding. Costo `null`.

[F-004] **Il decay monitor riemette lo stesso valore contro tre baseline.** Alle 21:00Z sei alert `DECAY CRITICAL` con valore corrente **identico** per S1, S2 e S4 (IC −0,049, hit rate 28,9%) confrontato contro tre baseline diverse (0,035 / 0,042 / 0,028 e 54,0% / 56,0% / 52,0%), incluso S2 che non ha mai tradato. Costo `null`.

[F-062] **Gli alert CRITICAL non hanno canale.** I sei `DECAY CRITICAL` delle 21:00Z esistono solo come `log.critical`. Costo `null`.

[F-005] **Alert Telegram rifiutati.** Sei `400 Bad Request` verso `api.telegram.org/sendMessage` nel log worker della giornata, il primo alle 14:07:07Z sull'alert #161 (posizioni non proteggibili). Costo `null`.

[F-018] **Bot token in chiaro.** Lo stesso URL loggato a livello INFO da httpx espone `bot8611445937:AAH3…` in chiaro, sia nei fallimenti Telegram del worker sia nel polling continuo di `worker-inference`. Costo `null`.

[F-022] **Posizioni non proteggibili.** `#161: 10/45 held positions are unprotectable (qty < 1)` — AMAT, AMD, ASML, CAT, DELL, LLY, MRVL, NOK, SPY, WDC — con `AMAT unprotected at -22.8%` alle 14:07 e ancora `-21.0%` alle 16:52. AMAT e NOK sono due dei sei mover detenuti della giornata, e sono entrambi in questa lista. Costo `null`.

[F-021] **Finestra operativa spostata dal DST.** Il 2026-09-08 è EDT: apertura RTH 13:30 UTC. Il primo `portfolio_cycle` è alle **14:07 UTC** e l'ultimo alle **19:52** (24 cicli, nessun gap oltre i 16 minuti sulla cadenza attesa di 15). I primi **37 minuti** di sessione non hanno alcun ciclo, e in quella finestra esistevano già cinque segnali, due dei quali sopra gate: AZN +0,423 (13:31) e NVO +0,409 (13:54), oltre a SPCX +0,373 (13:41) e due righe HOOD. Costo `null`.

## 9. Cosa sembra un difetto e non un limite noto

Segnalo, senza proporre alcuna correzione — la decisione se aprire un'issue è dell'operatore.

1. **Il callback di alert del fallback breaker solleva `asyncio.run() cannot be called from a running event loop`** ([F-071]). Non è una scelta di taratura né un limite di copertura dati: è un'eccezione a runtime su un percorso di notifica che il sistema crede funzionante. L'effetto osservabile è indistinguibile da "il breaker non ha sparato".
2. **La chiave Redis `fallback:breaker_fired_at` contiene un contatore (`1`) e non un timestamp** ([F-071]). Il nome del campo e il suo contenuto sono in disaccordo; qualunque lettura successiva che tratti quel valore come un istante otterrà un risultato sbagliato in silenzio.
3. **`execution_decisions.signal_id` è NULL su tutte e cinque le SELL della giornata mentre è popolato su tutto il resto** ([F-011]). Che il fill rate complessivo sia al 99,1% e il ramo SELL a 0% suggerisce un percorso di scrittura che non è stato aggiornato assieme agli altri, non un dato genuinamente non disponibile: il dossier stesso lo marca come regressione.

Non classifico invece come difetti — sono limiti noti e già registrati — la saturazione del top-N ([F-051]), la regola "solo il segnale più recente" ([F-023]), il gate a 0,30 ([F-009]) e la finestra beat in UTC fisso ([F-021]).
