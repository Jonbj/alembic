# Alpha Miss Report — 2026-09-17

Contratto: `alpha_miss_prompt_v2`, dossier `schema_version` 3.1. Fonte numerica unica: `docs/evidence/dossier/2026-09-17.json` (generato 2026-09-18T08:00:30Z, `fonte_prezzi`: Alpaca SIP adjustment=all). Soglia mover pre-registrata `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30.

## 1. Decision card

1. **Giornata di rotazione AI/semis: 15 mover ≥3%, 12 su e 3 giù, e 8 dei 12 rialzisti sono semis** (ARM +8,57%, INTC +7,67%, AMD +6,36%, MU +5,50%, MRVL +4,81%, DELL +4,46%, SOXX +3,39%, TSM +3,00%); SOXX +3,39% contro SPY +1,13% e QQQ +1,73%, dispersione cross-sectional 2,22%.
2. **Il book era già dentro il tema per eredità, non per decisione di giornata**: 7 dei 15 mover erano già a libro all'apertura (`funnel_v2.kpi.held_at_open_rate`=7/15=46,7%), mentre dei 5 mover ENTRY_OPPORTUNITY solo 1 ha chiuso in utile dopo i costi (`profitable_capture_rate`=1/5=0,20) — l'unico semis comprato oggi, MU, è entrato a movimento già interamente consumato (`quota_movimento_precedente_al_segnale`=1,0588) e marca −1,97 $.
3. **Il guard anti-pyramiding è il destino dominante degli intenti eseguibili**: 75 dei 102 intenti S4 tradabili (73,5%) finiscono `SKIP_PYRAMIDING`, contro 5 `SUBMITTED`; 43 dei 75 sono su simboli detenuti da S1/legacy e solo 15 dei 75 lasciano una riga in `execution_decisions`.

## 2. Stato carta

Da `docs/evidence/economic_pnl.json`, **as_of 2026-09-16** (i cumulati arrivano al giorno osservato precedente al 09-17; la seduta di oggi non è ancora nel ledger).

- Giorno **29/40** della finestra di osservazione (inizio 2026-08-03, scadenza attesa 2026-09-28).
- Quota NO_NEWS dominante: **13/29 = 44,8%**, sotto la soglia carta 0,60 (`superata_soglia`=false).
- S4 economico cumulato: **−979,55 $** vs banda ±200 $ (`within`=false — fuori banda, ed è il valore peggiore della finestra: era −855,58 $ il 09-15 e −707,41 $ il 09-11).
- Book cumulato: **−654,00 $**. S1 cumulato: +360,38 $, contro un benchmark SPY di +441,89 $ sulla stessa base di capitale (`delta_vs_spy` = **−81,51 $**).
- `docs/evidence/longitudinal_panels.json` **non esiste**: i denominatori di falsificabilità del §8 sono contati dalle occorrenze di `findings.json` e dichiarati come tali, non letti da `falsifiability.views`.

## 3. Miss del giorno

6 candidati in `candidati_miss`, tutti mover non detenuti. **Nessun FILTERED possibile oggi**: `funnel_v2.conteggi_pipeline`={"NO_RELEVANT_NEWS":1,"BELOW_GATE":2,"BAD_FILL":1,"CAUGHT":1} — nessuna riga raggiunge uno stadio oltre il gate, e le uniche guardie della giornata sono `SKIP_THRESHOLD` (che *è* il gate) e `SKIP_PYRAMIDING` (che non ha colpito nessun candidato miss).

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| ARM | +8,57% | **THIN_NEUTRAL** | `funnel_v2.righe[ARM].pipeline`="BELOW_GATE", `evidence.score_firmato`=0,0292 contro `soglia_gate`=0,30 — sotto anche la soglia `thin`=0,05 di `aggregati.cause_del_giorno.soglie`. Segno corretto, magnitudine nulla. Il campo grezzo `causa`="OFF_TOPIC_NON_DECIDIBILE" (`mapping_legacy_v2` lo manda su NO_RELEVANT_NEWS senza promuoverlo). Lettura degli articoli: le 2 righe `news_log` sono un roundup macro sui futures (12:43, fan-out) e un pezzo "Vicor, Arm Holdings, Micron And Other Big Stocks Moving Higher On Thursday" (15:58) — quest'ultimo è l'unico ISSUER_SPECIFIC ed è **retrospettivo**: constata il rialzo, non lo anticipa. Nessuna riga spiega un +8,57%. |
| ORCL | +5,19% | **THIN_NEUTRAL** | `funnel_v2.righe[ORCL].pipeline`="BELOW_GATE", `evidence.score_firmato`=**0,22** contro gate 0,30: segno corretto, sotto soglia — il caso tipico di F-009. Lettura degli articoli: quel 0,22 viene dal pezzo macro "Nasdaq 100 Rallies as Oil Slides, Yields Retreat" (17:22, TAG_UNCONFIRMED, fan-out), **non** dall'unico articolo ISSUER_SPECIFIC su Oracle ("Oracle Stock Trends Higher: What's Going On Today?", 18:20), che ha scorato 0,021 ed è anch'esso retrospettivo. `max_score_own`=0,021 contro `max_score_fanout`=0,22: il segnale che più si avvicina al gate non parla di Oracle. |
| HOOD | +5,16% | **NO_NEWS** | `funnel_v2.righe[HOOD].pipeline`="NO_RELEVANT_NEWS", `evidence.rilevanza`={ISSUER_SPECIFIC:0, TAG_UNCONFIRMED:2}: due righe in `news_log`, zero confermate rilevanti — `mapping_legacy_v2` manda NO_RELEVANT_NEWS su legacy NO_NEWS. Non un buco letterale a zero righe, ma zero copertura confermata. Il campo grezzo `causa`="BELOW_GATE" è la vista legacy pre-#509 (score-vs-gate puro). Lettura degli articoli: entrambi di settore cripto (esenzione SEC su tokenized stocks; nota Bitwise sul CLARITY Act), nessuno su Robinhood. |
| TMUS | −5,57% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[TMUS].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only": ribasso, non detenuto, book long-only — nessuna azione possibile per costruzione. Il campo grezzo `causa`="BELOW_GATE". Da annotare: l'unico segnale è **+0,12**, di segno opposto a un −5,57%, e viene dallo stesso pezzo macro delle 17:22 (vedi §8, F-012). |
| CMCSA | −3,46% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[CMCSA].actionability`="NON_ACTIONABLE" (ribasso non detenuto). È anche l'unico candidato a zero righe `news_log` (`news_count`=0, `causa` grezza="NO_NEWS", `no_news_backstop` lo elenca fra i 2 mover a zero notizie): la vista legacy lo conterebbe NO_NEWS, l'asse actionability lo rende comunque non azionabile a prescindere dalla notizia. |
| RDDT | −3,03% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[RDDT].actionability`="NON_ACTIONABLE" (ribasso non detenuto). Campo grezzo `causa`="BELOW_GATE". Stessa annotazione di TMUS: unico segnale **+0,20** su un −3,03%, dallo stesso articolo macro delle 17:22. |

**Conteggi**: NO_NEWS 1 · THIN_NEUTRAL 2 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 3. (`aggregati.cause_del_giorno` resta invariato per vincolo #288 Opzione 1: {"NO_NEWS":1,"BELOW_GATE":4,"OFF_TOPIC_NON_DECIDIBILE":1}, dominante "BELOW_GATE".)

**Nota di metodo**: come il 09-15, dove i due divergono preferisco l'asse `actionability`/`pipeline` di `funnel_v2` (introdotto da #509) al campo grezzo `causa`, che non verifica l'attuabilità; il valore legacy è comunque riportato per riga. Tre dei sei candidati sono ribassisti non detenuti: su un libro long-only nessuno di essi era catturabile, indipendentemente dalla qualità del segnale.

### Titoli catturati

| Simbolo | Return% | Come | Esito |
|---|---:|---|---|
| MU | +5,50% | **tradato oggi** — ingresso S4 15:52 @ 978,848, qty 1,4634 | `funnel_v2.righe[MU].pipeline`="BAD_FILL", `evidence.eod_net_pnl`=**−2,76 $**; `mtm_eod`=−1,97 $. Posizione ancora aperta a fine seduta. **Timing pessimo**: `entry_percentile`=0,775 (77° percentile del range di seduta) e `quota_movimento_precedente_al_segnale`=**1,0588** — al momento del segnale il movimento intraday era già interamente consumato. Il titolo fa +5,50%, il book ne cattura −0,14%. |
| NVO | +3,55% | **tradato oggi** — ingresso S4 16:52 @ 43,1093, qty 33,2014 | `funnel_v2.righe[NVO].pipeline`="CAUGHT", `evidence.eod_net_pnl`=**+1,89 $**, `net_profitable`=true; `mtm_eod`=+2,68 $. Unica cattura profittevole della giornata. Anche qui entrata tardi: `entry_percentile`=0,777, `quota_movimento_precedente_al_segnale`=0,9333. |
| INTC | +7,67% | detenuto all'apertura (S4) | `PASSIVE_EXPOSURE`. Nozionale 1.580 $, `ritorno_da_ingresso`=+7,34% → ~+121 $ di marcatura sulla seduta. Non è una cattura di giornata: nessuna decisione del 09-17 l'ha prodotta. |
| MRVL | +4,81% | detenuto all'apertura (S4) | `PASSIVE_EXPOSURE`. Nozionale 1.535 $, ~+74 $ sulla seduta. **Un intento d'ingresso alle 14:07 è stato bloccato da `SKIP_PYRAMIDING`** (vedi §8, F-031). |
| AMD | +6,36% | detenuto all'apertura (S1) | `PASSIVE_EXPOSURE`. Nozionale 444 $, ~+28 $ sulla seduta; `ritorno_da_ingresso` resta **−1,58%**. |
| DELL | +4,46% | detenuto all'apertura (S1) | `PASSIVE_EXPOSURE`. Nozionale 547 $, ~+24 $; `ritorno_da_ingresso` +37,58%. Zero righe `news_log` oggi (è uno dei 2 mover NO_NEWS). |
| SOXX | +3,39% | detenuto all'apertura (S1) | `PASSIVE_EXPOSURE`. Nozionale 599 $, ~+20 $. |
| TSM | +3,00% | detenuto all'apertura (S1) | `PASSIVE_EXPOSURE`. Nozionale 787 $, ~+24 $. |
| NOK | +4,54% | detenuto all'apertura (S1) | `PASSIVE_EXPOSURE` **nominale**: nozionale **6,00 $**, ~+0,27 $ sulla seduta. Conta come mover detenuto nel KPI `held_at_open_rate` pur essendo lo 0,27% di uno slot S4 — è il caso descritto da F-075 (vedi §9b). |

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["SPCX","META","MU","BA","NVO"],"chiusure":["SPCX","META"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | SPCX | S4 | 15:07 | $154.1900 | 9.3537 | — | percentile 36.83%; denominatore intraday valido |
| IN | META | S4 | 15:37 | $675.4300 | 2.1248 | — | percentile 51.89%; denominatore intraday degenere: quota non interpretabile |
| IN | MU | S4 | 15:52 | $978.8480 | 1.4634 | — | percentile 77.52%; denominatore intraday valido |
| IN | BA | S4 | 16:07 | $199.2300 | 7.1955 | — | percentile 33.57%; denominatore intraday valido |
| IN | NVO | S4 | 16:52 | $43.1093 | 33.2014 | — | percentile 77.66%; denominatore intraday valido |
| OUT | SPCX | S4 | — | $154.9600 | 9.3537 | +$5.69 | portfolio_sell |
| OUT | META | S4 | — | $681.0900 | 2.1248 | +$11.74 | portfolio_sell |
<!-- alpha-miss-book:end -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

5 ingressi, tutti S4, tutti in una finestra di 1h45 (15:07→16:52 UTC), e 2 chiusure, entrambe `portfolio_sell` su posizioni aperte in giornata. Il realizzato della seduta è **+17,43 $**, interamente S4 (SPCX +5,69 $ dopo 2,5h, META +11,74 $ dopo 4,25h); S1 non ha realizzato nulla. Il dato che pesa è a monte del P&L: su 1.973 intenti S4 della giornata solo 102 sono tradabili, e di quei 102 ne vengono sottomessi **5** — il resto è 75 `SKIP_PYRAMIDING` e 22 `SKIP_IDEMPOTENCY`. Fra i 5 ingressi, 3 entrano oltre il 50° percentile del range di seduta (MU 0,775, NVO 0,777, META 0,519) contro una mediana mobile a 20 giorni di 0,569: la giornata è in linea con l'abitudine, non peggiore. L'ingresso peggiore è BA (16:07 @ 199,23, `mtm_eod` **−16,05 $**), che non è un mover e chiude la seduta a −2,46%. Le due chiusure hanno drift post-uscita di segno opposto (SPCX −1,40, META +2,59): su n=2 non c'è nulla da leggere.

## 5. Cecità lato uscita

Da `copertura_uscita`: 42 posizioni, `n_indeterminati`=**0** — nessuna riga con `cieco_lato_uscita: null`, quindi nessun dato mancante da dichiarare in questa sezione. 2 posizioni cieche, entrambe ancora aperte.

| Ticker | Strategia | `ritorno_da_ingresso` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---|---:|
| PFE | S1 | **−3,66%** | 5 | `alpaca_benzinga` | 801,93 $ |
| SBUX | S1 | **−8,27%** | 6 | `alpaca_benzinga` | 636,26 $ |

Entrambe le streak sono cresciute rispetto al 09-15 (PFE 3→5, SBUX 4→6), contate da `copertura_uscita` sulla sua finestra di 10 sedute. Da non confondere con l'omonimo contatore di `copertura_articoli.blind_set.per_ticker`, che per entrambe vale **1** con `zero_articoli_streak_troncato_da`="dossier_mancante": quel contatore è troncato da un dossier assente, quindi **non** è confrontabile con la soglia `soglia_allerta_sedute_zero_articoli`=5 e non va letto come un rientro nella copertura. `fonti_osservate_finestra` non è vuota in nessuno dei due casi: i connettori per-ticker erano vivi e interrogavano l'intera watchlist: semplicemente non hanno reso nulla su questi due ticker nella finestra — è zero resa, non fonte non configurata.

`ritorno_da_ingresso` è la perdita accumulata dall'ingresso al close di oggi (`uscita_nella_seduta`=false per entrambe, quindi il mark è il close). Non va confuso con `ritorno_seduta`, che è il movimento del solo 09-17: **PFE +0,66%** e **SBUX −0,69%**, entrambi sotto la soglia mover. Il problema non è il movimento di oggi, è che da 5-6 sedute nessuna riga `news_log` può produrre un segnale di uscita o riduzione su queste due posizioni.

Aggregato `aggregati.copertura_uscita`: 42 posizioni, 18 a copertura grezza nulla, 25 a copertura effective-timely nulla, 8 in perdita marcata, **2 cieche**, nozionale cieco **1.438,18 $**, `n_notional_non_stimato`=0.

## 6. Backstop NO_NEWS

Popolazione `no_news_backstop.population`: 36 simboli a zero righe `news_log` (2 mover, 34 non-mover, `return_missing`=0).

### 6a. Marker calendario

| Simbolo | Return% | `observed_catalysts` | Calendario |
|---|---:|---|---|
| CMCSA | −3,46% | `[]` | `NOT_OBSERVED` — entrambe le fonti hanno risposto (`sources_succeeded`: FMP earnings-calendar, Alpaca Corporate Actions API) |
| DELL | +4,46% | `[]` | `NOT_OBSERVED` — stesse due fonti, entrambe hanno risposto |

Nessun marker `CALENDAR` sui due mover a zero notizie: `calendar_observation.mover_observed`=0 su `mover_population`=2 (tasso 0,0%), contro 1/34 (2,9%) fra i non-mover. Lo 0/2 è un'osservazione, non un fallimento di fetch — `calendario_earnings.status`="OBSERVED", `streak_sedute_consecutive_unknown`=0. Il marker, quando c'è, dice solo che il calendario societario registrava un evento: **non** che esista un segnale sentiment o un ordine.

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`volume_observation.temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=**false**. Il volume di seduta e l'etichetta mover sono noti solo alla chiusura: quanto segue descrive la giornata intera a posteriori, non un valore disponibile prima del movimento. Nessuna soglia scelta, nessun false-positive rate stimato — la valutazione ex-ante pre-registrata è separata in #451.

- Mediana della sorpresa di volume, mover a zero notizie (n=2): **+26,9%**. Non-mover (n=34): **−2,5%**.
- CMCSA: volume 36.260.649, ADV20 23.023.165, sorpresa **+57,5%**.
- DELL: volume 9.354.360, ADV20 9.703.751, sorpresa **−3,6%** — un mover a +4,46% con volume *sotto* la media. I due casi non concordano fra loro: su n=2 la mediana non descrive nulla.

### 6c. Copertura raw di `news_log` per settore (tutti i settori, inclusi gli zero su N)

Questa è copertura **raw** di `news_log`, distinta dalla quota effective-timely di `copertura_articoli.per_settore` (§7 e §9): non vanno mescolate.

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news |
|---|---:|---:|---:|
| etf_broad | 4/4 | 100,0% | 0 |
| financials | 12/14 | 85,7% | 0 |
| semis | 11/15 | 73,3% | 1 (DELL) |
| consumer | 8/11 | 72,7% | 0 |
| tech | 12/21 | 57,1% | 0 |
| energy | 3/6 | 50,0% | 0 |
| industrials | 2/4 | 50,0% | 0 |
| healthcare | 4/9 | 44,4% | 0 |
| media | 2/5 | 40,0% | 1 (CMCSA) |
| telecom | 2/5 | 40,0% | 0 |
| materials | 0/2 | **0,0%** | 0 |

Totale watchlist: 60/96 con almeno una riga = **62,5%** di copertura raw, cioè `watchlist_zero_news`=36/96 (37,5%). `materials` (RIO, VALE) resta a zero per la seconda seduta consecutiva osservata.

## 7. Pattern osservato

**Rotazione verso l'hardware AI, uscita da telecom e media.** Il tema è netto e non richiede di inventare settori: 8 dei 12 mover rialzisti sono `semis` (ARM, INTC, AMD, MU, MRVL, DELL, SOXX, TSM) e il nono, ORCL, è il proxy AI del comparto `tech`; il settore intero si muove, non i singoli — SOXX +3,39% contro SPY +1,13%. Sull'altro lato, i 3 mover ribassisti sono **tutti** telecom o media (TMUS −5,57%, CMCSA −3,46%, RDDT −3,03%), con TMUS che è anche il mover più estremo della giornata in valore assoluto dopo ARM e INTC.

`event_market_context` conferma la lettura sui 6 candidati: ARM porta `theme`="AI_SEMIS" e `catalyst`="MACRO" con residuo vs settore ancora **+5,18%** (quindi c'è anche un pezzo idiosincratico che nessuna riga `news_log` spiega); TMUS e RDDT portano `catalyst`="IDIOSYNCRATIC" con residui vs settore −4,99% e −2,45%. Il `regime` osservato è "SIDEWAYS" (`regime_mult`=0,7, VIX 17,71 al 09-16 da FRED:VIXCLS) — la rotazione è avvenuta dentro un regime che scala il notional a 0,7.

Rispetto ai giorni precedenti: il 09-15 la giornata era speculare (6 mover su 7 ribassisti, nessuna cattura) e il 09-16 tutti e tre i mover azionabili chiusero in perdita. Oggi il segno del mercato si inverte e il book ne beneficia, ma **per posizioni ereditate**: 7 mover su 15 erano già a libro, e delle 5 opportunità d'ingresso solo 1 è finita in utile. Il pattern che si ripete non è direzionale, è di tempistica — vedi F-030 al §8.

## 8. Segnalazioni

Tre finding, scelti fra quelli materialmente esposti oggi con una conseguenza in dollari. I denominatori di falsificabilità sono **contati dalle occorrenze di `findings.json`** (file `docs/evidence/longitudinal_panels.json` assente), e sono dichiarati come tali. Le cause di miss del §3 non diventano segnalazioni: sono già contate in `aggregati.cause_del_giorno`.

### [F-031] Il guard anti-pyramiding è il destino del 73,5% degli intenti eseguibili, e 43 su 75 sono su posizioni che S4 non ha aperto

- **Meccanismo e fonte**: §4 di questo report; `intenti_ingresso_s4` (1.973 righe, `final_reason_code`) e `guard_decisions` (795 righe) del dossier. Dei 102 intenti con `is_tradable`=true, **75 finiscono `SKIP_PYRAMIDING`**, 22 `SKIP_IDEMPOTENCY` e **5 `SUBMITTED`**. Incrociando i simboli bloccati con `copertura_uscita.posizioni`: 43 dei 75 blocchi sono su titoli detenuti da **S1** (SHEL 14, XLK 10, XOM 9, MS 6, AAPL 3, LLY 1), 11 su titoli detenuti da S4 (QQQ 10, MRVL 1), e 21 su posizioni che **S4 ha aperto oggi stesso** (BA 9, META 8, SPCX 4) — questi ultimi sono il guard che funziona come progettato. La metà restante è il difetto descritto dal finding: S4 non può prendere posizione su un simbolo perché un'altra sleeve ce l'ha già.
- **Esposizione oggi**: 102 intenti tradabili, di cui 75 esposti al guard; 1 mover della giornata direttamente colpito (MRVL, +4,81%, intento bloccato alle 14:07 sul ciclo d'apertura).
- **Evidenza contraria**: se il finding fosse falso, i blocchi sarebbero concentrati sulle posizioni aperte da S4 stessa — cioè le 21 righe BA/META/SPCX sarebbero la maggioranza, non la minoranza. Sono 21 su 75 (28%); le 43 su simboli S1 sono il 57,3%.
- **Non-occorrenza**: il guard **non** ha colpito nessuno dei 6 candidati miss del §3 — ARM, ORCL, HOOD, TMUS, CMCSA, RDDT hanno zero righe `SKIP_PYRAMIDING` e zero righe in `guard_decisions` (HOOD, TMUS, RDDT, CMCSA ne hanno zero in assoluto). Su quei sei il collo di bottiglia è a monte, nel gate: quindi il guard non è la spiegazione universale dei miss, solo di quelli sui titoli già a libro.
- **Tracciabilità, seconda metà del finding**: `execution_decisions` registra **15** righe `SKIP_PYRAMIDING` contro 75 intenti — tasso di traccia 20%. Il 09-16 il rapporto era 11 contro 90 (12%). La traccia esiste ma resta parziale; `decision_signal_id_coverage.regressions` elenca `SKIP_PYRAMIDING` fra le regressioni (13/15 con `signal_id`, attese 15/15). Plausibile interazione con F-080 (chiave di deduplica di `SKIP_PYRAMIDING` senza il giorno), non verificata qui.
- **Next evidence (read-only)**: contare, su tutta la finestra 08-03→09-17, la quota di intenti `is_tradable` che finiscono `SKIP_PYRAMIDING` separata per strategia detentrice (S1/legacy vs S4 stessa vs S4 dello stesso giorno), e affiancarla al `counterfactual_return_1h` già presente in `guard_decisions`. Se la quota S1/legacy è stabilmente >50% e i controfattuali sono positivi in mediana, il costo è strutturale e non aneddotico. Nessuna scrittura, solo query su `s4_intent_events` e `execution_decisions`.
- **Costo**: **3,20 $**. Formula: `2200 × counterfactual_return_1h(MRVL)` = 2200 × 0,001453 = 3,20 $ — slot S4 da 2% del NAV sul solo mover bloccato, valutato sull'orizzonte a 1 ora che il dossier prezza. È deliberatamente il limite inferiore: gli altri 74 blocchi non hanno un controfattuale di giornata perché i simboli non erano mover, e MRVL ha poi fatto +4,81% sulla seduta intera, che questa formula **non** conta.

### [F-012] Un solo articolo macro è l'unica fonte di segnale su tre ticker, e su due dei tre il segno è opposto al prezzo

- **Meccanismo e fonte**: §3 di questo report (righe TMUS, RDDT, ORCL); `candidati_miss[*].segnali` e `copertura_articoli.totali` del dossier. L'articolo "Nasdaq 100 Rallies as Oil Slides, Yields Retreat: Stock Market Today" (published 17:22 UTC, `alpaca_benzinga`, `relevance`=TAG_UNCONFIRMED, `attribution`=FANOUT) genera alle 17:30-17:35 il segnale **+0,22 su ORCL** (prezzo +5,19%, segno corretto), **+0,12 su TMUS** (prezzo −5,57%, segno opposto) e **+0,20 su RDDT** (prezzo −3,03%, segno opposto). Per TMUS e RDDT è l'**unico** segnale della giornata (`news_count`=1 per entrambi). Per ORCL è il `max_score_fanout`=0,22 contro un `max_score_own`=0,021: il punteggio che più si avvicina al gate non parla di Oracle.
- **Esposizione oggi**: 215 righe scorate da 123 articoli unici, `mapping_fanout_extra`=92; `TAG_UNCONFIRMED` 132/215 = **61,4%**; `aggregati.cause_del_giorno.quota_righe_fanout` = **0,818** (9 righe su 11 fra i candidati miss). Cinque dei sei candidati hanno almeno una riga fan-out.
- **Evidenza contraria**: se il finding fosse falso, le righe fan-out sarebbero rumore innocuo perché non arrivano mai in cima alla classifica di un ticker. Oggi il contrario: su ORCL la riga fan-out è il massimo assoluto della giornata (0,22 contro 0,021 della riga ISSUER_SPECIFIC), e su TMUS e RDDT è l'unica esistente. Sarebbe falsificato anche da un segno concorde: 2 su 3 sono discordi.
- **Non-occorrenza**: su ARM il fan-out **non** domina — `max_score_own`=0,021 e `max_score_fanout`=0,0292 sono entrambi sotto la soglia `thin`=0,05, quindi lì il fan-out non cambia nulla; e su AAPL `max_score_own`=0,42 supera `max_score_fanout`=−0,04, cioè su un ticker ben coperto la riga propria vince. Il fenomeno morde dove la copertura issuer-specific manca, non ovunque.
- **Next evidence (read-only)**: per la finestra 08-03→09-17, calcolare la concordanza di segno fra `score` e rendimento di seduta separatamente per `attribution`=FANOUT e `attribution`=ISSUER_SPECIFIC, sui soli ticker-giorno con entrambe le attribuzioni presenti (così il confronto è appaiato e non confonde copertura con qualità). Se la concordanza FANOUT non è distinguibile da 0,5 mentre quella ISSUER_SPECIFIC la supera, il fan-out è rumore che occupa lo slot del segnale. Query su `sentiment_signals` + `news_log`, nessuna scrittura.
- **Costo**: **0,00 $**, e il valore è misurato, non un segnaposto. Formula: nessuna delle tre righe fan-out ha superato il gate (max 0,22 < `soglia_gate_usata` 0,30), quindi zero ordini generati e zero P&L realizzato attribuibile. Il costo **evitato** è invece stimabile e va detto: `candidati_miss[TMUS].opportunity_v2.gross_opportunity_usd` = 122,44 $ — è la perdita che uno slot da 2.200 $ aperto su quel +0,12 avrebbe prodotto sul −5,57% di TMUS. Oggi il gate ha coperto un difetto di provenienza; è una copertura fortuita, non un controllo sulla rilevanza.

### [F-030] L'unico semis comprato nella giornata dei semis è entrato a movimento già interamente consumato

- **Meccanismo e fonte**: §3 (riga MU fra i catturati) e §4; blocco `ingressi` e `funnel_v2.righe[MU]` del dossier. Ingresso S4 su MU alle 15:52 @ 978,848 con `quota_movimento_precedente_al_segnale`=**1,0588** (`denominatore_degenere`=false, quindi la quota è leggibile) e `entry_percentile`=**0,775**. Il titolo chiude a 977,50: `funnel_v2.righe[MU].pipeline`="BAD_FILL", `evidence.eod_net_pnl`=−2,76 $, `net_profitable`=false. MU fa **+5,50%** sulla seduta e il book ne cattura **−0,14%**.
- **Esposizione oggi**: 5 ingressi, di cui 4 con `quota_movimento_precedente_al_segnale` non degenere — SPCX 0,386, BA 0,575, NVO 0,933, MU 1,059. Due dei quattro sopra 0,9. 5 mover `ENTRY_OPPORTUNITY`, di cui 2 effettivamente presi.
- **Evidenza contraria**: se il finding fosse falso, gli ingressi tardivi non sarebbero peggio degli altri. Oggi la relazione tiene sul campione del giorno (MU quota 1,059 → −2,76 $; NVO quota 0,933 → +1,89 $; SPCX quota 0,386 → +5,69 $ realizzati), ma **n=5 non decide niente**, e META è un controesempio interno: quota degenere, mtm +14,62 $, il miglior ingresso della giornata. La distribuzione congiunta cumulata (`aggregati.late_entry_joint_distribution`, 65 ingressi su 22 giornate dal 08-14) è più informativa della giornata: fascia ≥1,0 somma **−192,71 $** su 22 ingressi con win rate 0,33; fascia 0,0-0,5 somma −6,89 $ su 5 con win rate 0,60.
- **Non-occorrenza**: `mediane_mobili_20g.entry_percentile`=0,569 contro una mediana di giornata sui 5 ingressi di 0,519 — **oggi il timing non è peggiorato** rispetto all'abitudine delle ultime 20 sedute. Il fenomeno non si è visto come deterioramento; si è visto come costo su un singolo mover forte, che è esattamente il caso di PANW del 09-14 (quota 1,0168).
- **Next evidence (read-only)**: sulla finestra 08-14→oggi, regredire `pnl_netto` (o `mtm_eod` per le posizioni ancora aperte) su `quota_movimento_precedente_al_segnale` limitandosi agli ingressi su **mover ≥3%**, che è la popolazione in cui la quota ha significato — oggi la distribuzione congiunta mescola mover e non-mover, e su un non-mover una quota alta non è tardività ma denominatore piccolo. n atteso ~15-20: se `INSUFFICIENT_N`, dichiararlo invece di leggere il segno.
- **Costo**: **80,74 $**. Formula: `nozionale × (rendimento_di_seduta − rendimento_catturato)` = (1,463424 × 978,848) × (0,054989 − (−0,001377)) = 1.432,47 × 0,056366 = 80,74 $. Dati citati: `ingressi[MU].qty` e `.entry_price`, `mercato.rendimenti[MU]`, `funnel_v2.righe[MU].evidence.close`. Uso il nozionale reale della posizione invece dello slot congetturale da 2.200 $ perché qui la size è nota. Alternativa scartata: contare come costo l'intero +5,50% del titolo (1.432,47 × 0,054989 = 78,77 $ sullo stesso nozionale) — sarebbe un controfattuale d'apertura, non d'ingresso, e presupporrebbe un segnale che alle 14:07 non esisteva.

## 9. Appendice

### (a) Rendimenti completi della watchlist — `mercato.rendimenti`, 96 simboli, dal più alto al più basso

`M` = mover ≥ |3%| (`soglia_mover`=0,03). "Art." = `copertura_articoli.per_ticker[*].articoli_unici`. "Det." = presente in `copertura_uscita.posizioni` all'apertura.

| Simbolo | Return% | Settore | Art. | Det. | Mover |
|---|---:|---|---:|---|---|
| ARM | +8.57% | semis | 2 | no | **M** |
| INTC | +7.67% | semis | 9 | si | **M** |
| AMD | +6.36% | semis | 4 | si | **M** |
| MU | +5.50% | semis | 6 | no | **M** |
| ORCL | +5.19% | tech | 5 | no | **M** |
| HOOD | +5.16% | financials | 2 | no | **M** |
| MRVL | +4.81% | semis | 3 | si | **M** |
| NOK | +4.54% | telecom | 6 | si | **M** |
| DELL | +4.46% | semis | 0 | si | **M** |
| NVO | +3.55% | healthcare | 2 | no | **M** |
| SOXX | +3.39% | semis | 1 | si | **M** |
| TSM | +3.00% | semis | 1 | si | **M** |
| GM | +2.76% | consumer | 3 | si |  |
| SPCX | +2.60% | etf_broad | 9 | no |  |
| ERIC | +2.59% | telecom | 0 | no |  |
| NVDA | +2.54% | semis | 18 | no |  |
| VALE | +2.41% | materials | 0 | si |  |
| RIO | +2.35% | materials | 0 | si |  |
| CSCO | +2.32% | tech | 0 | si |  |
| AVGO | +2.29% | semis | 1 | no |  |
| TSLA | +2.27% | consumer | 6 | no |  |
| XLK | +2.25% | tech | 3 | si |  |
| SNOW | +2.23% | tech | 0 | si |  |
| AMZN | +2.13% | tech | 13 | no |  |
| QCOM | +2.09% | semis | 0 | no |  |
| CAT | +2.02% | industrials | 0 | si |  |
| AZN | +2.00% | healthcare | 0 | no |  |
| F | +1.95% | consumer | 1 | no |  |
| DB | +1.80% | financials | 1 | no |  |
| QQQ | +1.73% | etf_broad | 5 | si |  |
| ASML | +1.71% | semis | 1 | si |  |
| BIDU | +1.67% | tech | 0 | no |  |
| WDC | +1.65% | semis | 1 | si |  |
| NKE | +1.62% | consumer | 1 | no |  |
| MRK | +1.55% | healthcare | 2 | si |  |
| MSFT | +1.52% | tech | 7 | no |  |
| GS | +1.44% | financials | 2 | no |  |
| AAPL | +1.38% | tech | 6 | si |  |
| META | +1.34% | tech | 4 | no |  |
| GOOGL | +1.30% | tech | 6 | si |  |
| LLY | +1.28% | healthcare | 3 | si |  |
| MMM | +1.27% | industrials | 0 | no |  |
| BABA | +1.18% | tech | 1 | no |  |
| SPY | +1.13% | etf_broad | 21 | si |  |
| JNJ | +1.10% | healthcare | 0 | si |  |
| PLTR | +1.09% | tech | 1 | no |  |
| TM | +0.88% | consumer | 1 | no |  |
| ADBE | +0.87% | tech | 0 | no |  |
| XLE | +0.70% | energy | 2 | si |  |
| PFE | +0.66% | healthcare | 0 | si |  |
| XLV | +0.62% | healthcare | 1 | si |  |
| ABBV | +0.58% | healthcare | 0 | si |  |
| MS | +0.54% | financials | 3 | si |  |
| IWM | +0.53% | etf_broad | 1 | no |  |
| AMAT | +0.49% | semis | 0 | si |  |
| BAC | +0.48% | financials | 2 | no |  |
| SONY | +0.42% | tech | 0 | no |  |
| UBS | +0.40% | financials | 0 | si |  |
| PG | +0.36% | consumer | 0 | no |  |
| SAP | +0.22% | tech | 0 | no |  |
| GE | +0.18% | industrials | 2 | no |  |
| PBR | +0.14% | energy | 0 | si |  |
| SHEL | +0.13% | energy | 0 | si |  |
| JPM | +0.11% | financials | 4 | si |  |
| IBM | +0.11% | tech | 0 | no |  |
| BP | +0.09% | energy | 0 | si |  |
| COST | +0.02% | consumer | 1 | no |  |
| CVX | +0.01% | energy | 1 | si |  |
| HD | +0.01% | consumer | 0 | no |  |
| UNH | -0.01% | healthcare | 0 | si |  |
| XOM | -0.03% | energy | 1 | si |  |
| MCD | -0.03% | consumer | 2 | no |  |
| XLF | -0.09% | financials | 2 | si |  |
| INFY | -0.09% | tech | 0 | no |  |
| PANW | -0.16% | tech | 3 | si |  |
| WFC | -0.18% | financials | 2 | no |  |
| C | -0.19% | financials | 0 | si |  |
| V | -0.27% | financials | 2 | no |  |
| MA | -0.36% | financials | 2 | no |  |
| AXP | -0.40% | financials | 2 | no |  |
| WMT | -0.66% | consumer | 1 | no |  |
| ROKU | -0.67% | media | 0 | si |  |
| SBUX | -0.69% | consumer | 0 | si |  |
| NOW | -0.97% | tech | 0 | no |  |
| JD | -0.97% | tech | 1 | no |  |
| TXN | -0.97% | semis | 0 | no |  |
| NFLX | -1.44% | media | 0 | no |  |
| DIS | -1.53% | media | 1 | no |  |
| T | -1.82% | telecom | 0 | no |  |
| BRK.B | -2.04% | financials | 2 | no |  |
| BA | -2.46% | industrials | 3 | no |  |
| VZ | -2.87% | telecom | 0 | no |  |
| CRM | -2.90% | tech | 14 | no |  |
| RDDT | -3.03% | media | 1 | no | **M** |
| CMCSA | -3.46% | media | 0 | no | **M** |
| TMUS | -5.57% | telecom | 1 | no | **M** |

### (b) Checklist degli altri finding aperti toccati dalla giornata

| Finding | Esito | Dato decisivo |
|---|---|---|
| F-001 — copertura news bassa sulla watchlist | **supported** | `watchlist_zero_news`=36/96 = 37,5%, in peggioramento sul 09-16 (35/96 = 36,5%) e sul minimo di finestra del 09-15 (31/96). `materials` 0/2, `media` e `telecom` 2/5 ciascuno. |
| F-009 — il gate 0,30 scarta segnali col segno corretto su mover forti | **contradicted** | ORCL è il caso da manuale (score firmato +0,22, segno corretto, mover +5,19%) **ma** `candidati_miss[ORCL].opportunity_v2.net_opportunity_usd` = **−3,20 $**: entrando al primo ciclo eleggibile il trade sarebbe stato in perdita dopo i costi. Oggi il gate non è costato, ha risparmiato. Da notare che il segnale a 0,22 non è nemmeno issuer-specific (vedi F-012): il finding sarebbe stato "confermato" da un segnale che non parla di Oracle. |
| F-012 — righe scorate da articoli fan-out multi-ticker | **supported** | Vedi §8. `TAG_UNCONFIRMED` 132/215 = 61,4%; `quota_righe_fanout`=0,818 sui candidati. |
| F-011 — `execution_decisions.signal_id` NULL | **supported (parziale)** | `decision_signal_id_coverage`: 828/832 = 99,5% complessivo — molto migliorato — ma `regressions`=["SELL","SKIP_PYRAMIDING"]: **SELL 0/2** (fill rate 0,0 contro `must_be_full`) e SKIP_PYRAMIDING 13/15. La catena resta rotta esattamente sul lato uscita. |
| F-019 — latenza di ingestione consuma la finestra di freshness | **supported** | `SKIP_ENTRY_FRESHNESS` è il secondo motivo di scarto della giornata: **742 su 1.973 intenti** (37,6%), dietro `SKIP_ENTRY_GATE` (780, 39,5%). |
| F-030 — la notizia arriva a movimento avvenuto | **supported** | Vedi §8. MU `quota_movimento_precedente_al_segnale`=1,0588; su ARM l'unica riga ISSUER_SPECIFIC è un roundup delle 15:58 che constata il rialzo. |
| F-031 — guard anti-pyramiding su posizioni di altre sleeve | **supported** | Vedi §8. 75/102 intenti tradabili, 43 su titoli S1. |
| F-063 — calendario earnings indisponibile | **contradicted** | `calendario_earnings.status`="OBSERVED", `sources_succeeded`=["FMP earnings-calendar"], `streak_sedute_consecutive_unknown`=**0**, `missingness`=[]. Nel backstop entrambe le fonti (FMP + Alpaca Corporate Actions) rispondono su tutti i 36 simboli a zero news. |
| F-075 — `held_at_open_rate` conta mover detenuti con nozionale trascurabile | **supported** | **NOK**, +4,54%, nozionale **6,00 $** = 0,27% di uno slot S4 da 2.200 $, conta come mover detenuto in `held_at_open`=7/15. Senza NOK il KPI sarebbe 6/15 = 40,0% invece di 46,7%. Il caso si è ripresentato proprio nel giorno in cui il KPI viene letto come buona notizia. |
| F-082 — la guardia ombra di contraddizione non intercetta nulla | **supported** | `aggregati.guardia_contraddizione.giorno`: 102 intenti valutabili, `n_soppressi`=**0**. Sulla finestra: 1.241 valutabili, 9 soppressi, **0 eseguiti**, P&L soppresso 0,00 $ — 15 giorni coperti senza una singola intercettazione utile. |
| F-004 / F-062 — decay monitor: metriche pipeline-globali e alert CRITICAL senza canale | **supported** | `logs/containers/worker-2026-09-17.log` 21:00:00Z: **11 righe `DECAY CRITICAL`** (4 S1, 4 S2, 3 S4) — S1: IC da 0,035 a −0,054, hit rate −17,5pp, Sharpe 0,37 vs 0,95, drawdown 13,4% vs 8,0%. Solo `log.critical`, nessun altro canale (F-062). **S2 non è una sleeve operativa** e riceve comunque 4 alert CRITICAL con la stessa IC corrente di S1 (−0,054) confrontata contro una baseline diversa (0,042 vs 0,035): è esattamente il confronto di metriche pipeline-globali contro baseline distinte descritto da F-004. |
| F-053 — lo storico P&L etichetta la seduta col giorno successivo | **supported** | `/v2/account/portfolio/history` restituisce l'equity di chiusura del 09-17 (109.458,50 $) marcata `2026-09-18`. Confermato da `last_equity` del `/v2/account`, che vale 109.458,499. Usato con la correzione di uno slittamento, non a valore nominale. |
| F-057 — il resolver dei ticker non ha mai prodotto RESOLVED | **not_exposed** | Nessun campo del dossier del 09-17 espone verdetti del resolver; `extraction_method` è `source_metadata` su tutte le righe `news_log` lette in §3. Non misurabile oggi. |
| F-016 — il fetch del benchmark SPY fallisce | **contradicted** | SPY è presente in `mercato.rendimenti` (+1,13%) e in `event_market_context` come benchmark dell'attribuzione beta=1 su tutti e 6 i candidati. |

### (c) Casi di successo della giornata

Solo uno pieno, e due parziali:

1. **NVO +3,55%** — unica cattura d'ingresso profittevole (`funnel_v2.righe[NVO].pipeline`="CAUGHT", `net_profitable`=true, `eod_net_pnl`=+1,89 $, `mtm_eod`=+2,68 $). Mover intercettato, ordine eseguito, chiusura di seduta in utile dopo i costi. Va detto quanto è piccolo: +1,89 $ su un titolo che ha fatto +3,55%, perché l'ingresso è avvenuto al 77° percentile del range con il 93% del movimento già passato.
2. **META +1,34%** — non un mover, ma il miglior ingresso della giornata in valore assoluto: aperto alle 15:37 @ 675,43 e chiuso a 681,09 dopo 4,25h, **+11,74 $ realizzati** (`portfolio_sell`), con `drift_post_uscita`=+2,59 — cioè l'uscita ha lasciato qualcosa sul tavolo, non ha anticipato un ritracciamento.
3. **INTC +7,67%** — il secondo mover della giornata era già a libro da S4 (nozionale 1.580 $, `ritorno_da_ingresso` +7,34%, ~+121 $ di marcatura sulla seduta). È esposizione passiva ereditata, non una decisione del 09-17, e va contata come tale: `funnel_v2` la esclude infatti dal funnel con `pipeline_escluso_motivo`="held".

---

*Report prodotto sotto `alpha_miss_prompt_v2` in periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`, freeze della taratura fino al 2026-09-28). Nessuna proposta di taratura o correzione è contenuta in questo documento: solo evidenza. `findings.json` e `market_daily.jsonl` non sono stati toccati — i candidati per il ledger sono in `docs/evidence/candidates/2026-09-17.json` e passano per il materializzatore deterministico.*
