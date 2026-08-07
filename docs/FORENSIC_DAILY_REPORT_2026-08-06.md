# Forensic Daily Report — 2026-08-06

**Giornata di borsa:** giovedì 2026-08-06 (EDT, sessione 13:30–20:00 UTC)
**Report generato:** 2026-08-07
**Modalità:** read-only. Nessun ordine inviato, nessun worker avviato, nessuna patch applicata.
**Periodo di osservazione:** giorno 4 di 40 (`docs/evidence/OBSERVATION_CHARTER.md`, inizio 2026-08-03).
Nessuna proposta di taratura in questo report: solo difetti di correttezza e registrazione di evidenza.

**Nota di metodo — sovrapposizione con il report alpha-miss.** Il ciclo `alpha_miss_analysis` ha
girato stamattina alle 08:00 sullo stesso giorno e ha già scritto 11 occorrenze nel ledger
(`ALPHA_MISS_REPORT_2026-08-06.md`, commit `58058aa`). Dove questo report conferma una di quelle
osservazioni **non aggiungo una seconda occorrenza con lo stesso costo**: sarebbe doppio conteggio
in dollari sullo stesso giorno. Le conferme stanno in §11; le occorrenze che aggiungo io sono
elencate esplicitamente in §10 e §15.

---

## 1. Executive summary

La catena end-to-end ha funzionato: 2.473 articoli grezzi da 2 fonti, 162 righe in `news_log`,
163 segnali scorati, 705 decisioni persistite, 13 ordini inviati, 13 riempiti, 0 rifiutati,
riconciliazione ordini→fill→trade completa. Realizzato **−46,26 $** su 7 uscite, MTM del libro
aperto **−292,31 $**, NAV di chiusura **110.051,33 $** (−187,77 $ sul giorno). Nessun ordine fuori
orario, nessun duplicato, nessun BUY su segnale fallback, idempotenza dimostrata (6
`SIGNAL_DUPLICATE_SKIP`), regime rilevato correttamente (`sideways ×0,7`, applicato a tutte le 705
decisioni).

Il difetto nuovo più grave non è nel trading ma **nel protocollo di osservazione**: il ciclo forense
del 08-05, girato ieri, ha scritto il suo report ma **non ha mai aggiornato `findings.json`** — le
quattro anomalie che aveva trovato (test che scrivono nel DB di produzione, DNS tradotto in «mercato
chiuso», `BRKB` vs `BRK.B`, soglia S4 che si muove da sola) non esistono nel ledger, e gli id
`F-025..F-028` che quel report cita **collidono** con il vero F-025. In più, il redeploy delle 11:08
di oggi ha distrutto **tutti i log dei container del 2026-08-06**: questa giornata è ricostruibile
solo da Postgres e da Redis.

Sul trading il fatto del giorno è il **churn di S1**: cinque round-trip intraday su tre simboli
(MMM venduta e ricomprata due volte, ABBV ricomprata **15 minuti** dopo la vendita, BRK.B dopo 3
ore), ~16,20 $ di drag puro, con S1 che dichiara ribilanciamento mensile. E il segnale più forte
della giornata — **TSM +0,610**, ensemble, conf 0,80, su un articolo TSM-specifico — non ha
prodotto né ordine né **una sola riga** di `execution_decisions`: il guard anti-pyramiding P0-05
fa `continue` prima della persistenza perché S1 già teneva TSM.

## 2. Verdict finale

> **OK CON WARNING — con una riserva grave sulla conservazione dell'evidenza.**

La catena decisionale del 2026-08-06 è funzionalmente corretta e verificabile riga per riga: nessun
ordine senza segnale, nessun segnale sotto soglia che abbia generato un ordine, guard hold-minimum e
anti-pyramiding rispettati, riconciliazione completa, paper/live coerente (`system:mode=paper`,
`source=alpaca_paper`), risk limit lontani dalle soglie (gross 28,8 % su 50 %, drawdown 0,52 % su
5 %). Il warning riguarda ciò che serve a *misurare* questa finestra: il ledger ha perso un giorno
intero di findings, i log dei container del giorno analizzato non esistono più, l'API REST è
inaccessibile per il terzo giorno consecutivo, e il `risk_report` di chiusura emette un ALERT su un
drawdown del 13,9 % che non corrisponde a nulla di reale. Il sistema tratta correttamente; è
l'apparato che deve dimostrarlo a essere fragile.

---

## 3. Timeline del 2026-08-06

Tutti gli orari in **UTC**. Timezone confermato dal codice: `src/workers/celery_app.py` usa
`crontab(hour="14-21")`; i timestamp Postgres sono `timestamptz` in UTC. **Ambiguità nota e
ricorrente:** gli USA sono in EDT, la sessione è 13:30–20:00 UTC, ma le finestre beat sono cablate
su 14:00–21:00 UTC (EST) — vedi [DAY-009].

| Ora UTC | Fase | Componente | Evento | Esito |
|---|---|---|---|---|
| 13:30:01 | apertura | `portfolio_monitor` | primo snapshot della sessione, NAV 110.239,74 | OK — 82 snapshot fino alle 20:00, nessun buco |
| 13:30:38 | pre-market | `regime.detect_regime` | safety-net P0-09 | **OK** — `sideways ×0,7`, `disagreement=False`, VIX 16,5, momentum 20g +2,41 % |
| 13:30–14:15 | apertura | ingest + sentiment | **nessun ciclo** — beat parte alle 14:00 | **45 minuti di sessione scoperti** ([DAY-009]) |
| 14:00:00 | feedback | `loss_feedback` S1 | 3 perdite consecutive (trade 658) → soglia 0,30 → **0,000**, scale 0,25 → 0,20 | ramo **inerte** ([DAY-004]) |
| 14:00:00 | coda | `news_queue_drops` | inizio scarti per staleness | 196 scarti nella giornata, età media **10,93 h** |
| 14:07:00 | portfolio | `run_portfolio_cycle` | ciclo 1/24 — 47 target, 0 ordini | OK |
| 14:07:15 | decisioni | Decision Log | 30 `SIGNAL_STALE_SKIP` + primi `SKIP_THRESHOLD` a **0,350** | soglia S4 già sopra il baseline 0,30 |
| 14:15:07 | ingest | `alpaca_benzinga` | prima riga di `news_log` del giorno | OK |
| 14:15:32 | LLM | sentiment | **MSFT +0,5075** conf 0,725 (ensemble) — *«AI Hyperscaler Spending Is Entering Uncharted Territory»* | primo segnale sopra soglia |
| 14:22:00 | decisione | portfolio cycle | **BUY MSFT** (S4, signal 6689) + **SELL BRK.B** e **SELL SBUX** (`s1_weight_drop`) | 3 ordini, tutti riempiti |
| 14:30:17 | LLM | sentiment | **SPCX +0,4021** conf 0,650 (ensemble) — *«SpaceX's Real Financial Engine Isn't Rockets or AI»* | secondo segnale sopra soglia |
| 14:37:00 | decisione | portfolio cycle | **BUY SPCX** (S4, signal 6699) + **SELL ABBV** (`s1_weight_drop`) | OK |
| 14:37:13 | guard | idempotenza | `SIGNAL_DUPLICATE_SKIP` MSFT signal 6689 | **corretto** |
| 14:45:09 | ingest | `gdelt_gkg` | prima riga GDELT del giorno | OK |
| **14:45:25** | LLM | sentiment | **TSM +0,6104** conf 0,800 (ensemble) — *«TSM Raised Its 2026 Outlook as AI Demand…»* | **massimo assoluto del giorno; nessun ordine, nessuna riga di decisione** ([DAY-005]) |
| 14:52:00 | decisione | portfolio cycle | **BUY ABBV** (S1) — **15 minuti** dopo la SELL su ABBV | ([DAY-006]) |
| 15:07:xx | guard | hold-minimum 90 min | 1 SELL su SPCX bloccata, 30 min dopo l'acquisto | guard corretto; log fuorviante (F-014) |
| 15:15:06 | LLM | sentiment | **WDC −0,3128** conf 0,550 sul giorno del crollo −13,03 % | sotto soglia, nessun effetto |
| 15:15:46 | LLM | sentiment | **TSM −0,0573** — sovrascrive il +0,6104 delle 14:45 | ([DAY-005], F-023) |
| 16:07:00 | decisione | portfolio cycle | **SELL MSFT** `[whipsaw]` dopo 1h45, net −7,79 + **SELL MMM** `[s1_weight_drop]` (trade 584, +18,16) | F-013, F-023 |
| 16:15:29 | LLM | sentiment | **GS +0,4225** conf 0,650 ma `single:gpt-oss` | escluso dal ranking per design #108 |
| 16:22:00 | decisione | portfolio cycle | **BUY MMM** (S1) a 180,05 — 15 min dopo averla venduta a 179,75 | ([DAY-006]) |
| **16:37:10** | feedback | ratchet S4 | soglia d'ingresso **0,350 → 0,400 in piena sessione** | nessuna tabella lo registra (F-009) |
| 16:45:34 | LLM | sentiment | **SPCX +0,5600** conf 0,700 ma `single:glm-5.2` | invisibile al gate e al testo delle decisioni (F-006) |
| 17:22:00 | decisione | portfolio cycle | **BUY BRK.B** (S1) a 522,35 — venduta alle 14:22 a 518,04 | ([DAY-006]) |
| 18:07:00 | decisione | portfolio cycle | **SELL MMM** (S1), net −1,66 | secondo round-trip su MMM |
| 18:52:00 | decisione | portfolio cycle | **BUY MMM** (S1) + **SELL SPCX** `[expired]` (4,4 h > 4 h), net −34,98 | F-024; SPCX chiuderà a 114,92 |
| 19:46:00 | LLM | sentiment | ultimo segnale del giorno (SONY −0,2016); `consecutive_fallback` azzerato | OK |
| 19:52:00 | portfolio | ciclo 24/24 | 48 target, 0 ordini | ultimo ciclo |
| 20:00:00 | chiusura | `portfolio_monitor` | NAV **110.051,33 $**, 48 posizioni, gross 28,77 %, drawdown 0,52 % | OK |
| **20:30:00** | feedback | ratchet S4 | EWMA R −0,56 + 5 perdite consecutive (trade 667 = SPCX) → soglia **0,400 → 0,450**, scale 0,64 → 0,512, TTL 3,4 g | F-009 |
| 21:00:00 | monitor | `decay_monitor` | 12 righe: 4 CRITICAL, tutte con lo **stesso** `actual_value` su S1/S2/S4 | F-004 ([DAY-011]) |
| 22:30:00 | risk | `risk_report` | ALERT «portfolio drawdown 13,9 % exceeds 10 %», `combined_drawdown` = 1,24 % | F-003 ([DAY-010]) |

---

## 4. Tabella news ingest

### Per fonte

| Fonte | fetched | queued | duplicates | scartati (no ticker) | righe `news_log` | segnali | metodo estrazione |
|---|--:|--:|--:|--:|--:|--:|---|
| `gdelt_gkg` | 1.940 | 108 | 101 | 1.742 | 87 | 87 | `org_lookup` |
| `alpaca_benzinga` | 533 | 285 | 2.126 | 0 | 75 | 75 | `source_metadata` |
| `reuters` | 4 | 4 | 0 | 1 | **0** | 0 | — **artefatto di test** ([DAY-003]) |
| **Totale reale** | **2.473** | **393** | **2.227** | **1.742** | **162** | **163** | |

Copertura temporale: prima riga 14:15:07, ultima 19:46:00. **Nessun buco** nei 23 slot da 15 minuti
fra le 14:15 e le 20:00; **nessuna copertura** fra le 13:30 e le 14:15 ([DAY-009]).
Latenza di ingestione (published_at → created_at): mediana **30,4 min** GDELT / **44,6 min**
Benzinga, range 15,1–106,3 min. **Nessun timestamp futuro** (0 righe con `published_at > created_at`).
`discarded_reason` NULL su tutte le 162 righe.

**Deduplicazione.** 162 righe su **108 URL distinti** e 104 titoli distinti: la differenza non sono
duplicati non rimossi ma il **fan-out multi-ticker** (una riga per coppia URL×ticker). Il contatore
`duplicates` = 2.227 resta non verificabile indipendentemente (F-007): i duplicati non lasciano riga.

**Scarti in coda.** 196 item scartati per staleness, età media **10,93 h**: sono articoli entrati in
coda nelle sessioni precedenti e mai scorati.

### Fan-out per articolo

| ticker per URL | URL | righe generate |
|--:|--:|--:|
| 1 | 86 | 86 |
| 2 | 10 | 20 |
| 3 | 7 | 21 |
| 4 | 1 | 4 |
| 6 | 2 | 12 |
| 8 | 1 | 8 |
| 11 | 1 | 11 |

**77 segnali su 163 (47,2 %)** nascono da articoli-lista multi-ticker. I due estremi:
*«World's Smartest Banker Warns Of Hidden Margin Debt; SanDisk, WDC Disappoint»* → 11 ticker;
*«S&P 500, Dow Fall as Brent Jumps 4%»* → 8 ticker. Entrambi i BUY del giorno (MSFT e SPCX)
provengono dallo stesso articolo a 6 ticker, e l'uscita di MSFT da un altro articolo a 6 ticker.

### Per ticker (top 20 di 57)

| Ticker | segnali | score medio | max | min | note |
|---|--:|--:|--:|--:|---|
| **MS** | **30** | +0,005 | +0,045 | −0,020 | **nessun articolo riguarda Morgan Stanley** (F-020) |
| **GS** | **10** | +0,099 | +0,423 | −0,042 | idem per Goldman Sachs |
| SPCX | 7 | +0,094 | +0,560 | −0,360 | 4 su 7 single-model |
| MU | 7 | −0,053 | +0,169 | −0,324 | |
| SONY | 6 | −0,018 | +0,080 | −0,202 | |
| LLY | 6 | +0,069 | +0,257 | 0,000 | |
| TSLA | 5 | +0,060 | +0,299 | 0,000 | |
| **TSM** | 5 | +0,186 | **+0,610** | −0,057 | massimo del giorno, nessuna decisione |
| MSFT | 5 | +0,100 | +0,508 | −0,018 | unico BUY che ha prodotto un trade S4 |
| AMZN | 4 | +0,025 | +0,125 | −0,025 | |
| NVDA | 4 | −0,009 | 0,000 | −0,038 | |
| DIS | 4 | +0,078 | +0,212 | 0,000 | |
| GOOGL | 4 | +0,006 | +0,233 | −0,229 | |
| PLTR / BIDU / C / ASML / HD / BAC / BA | 1–3 | 0,000 | 0,000 | 0,000 | score identicamente nullo |
| WDC | 3 | −0,031 | +0,120 | −0,313 | il crollo del giorno, −13,03 % |
| BRKB | 3 | +0,012 | +0,035 | 0,000 | **simbolo non tradabile** (il tradabile è `BRK.B`) |

**Top news per impatto sul segnale**

| Ora | Ticker | Score | Conf | Modello | Titolo | Effetto |
|---|---|--:|--:|---|---|---|
| 14:45 | TSM | **+0,6104** | 0,800 | ensemble | *TSM Raised Its 2026 Outlook as AI Demand…* | **nessuno** — P0-05 |
| 16:45 | SPCX | +0,5600 | 0,700 | single:glm | *SpaceX, Tesla Confirm Terafab Site…* | nessuno — escluso #108 |
| 14:15 | MSFT | +0,5075 | 0,725 | ensemble | *AI Hyperscaler Spending Is Entering Uncharted Territory* | **BUY 14:22** |
| 16:15 | GS | +0,4225 | 0,650 | single:gptoss | *AI's Capital-Spending Boom…* | nessuno — escluso #108 |
| 16:02 | TSM | +0,4062 | 0,625 | ensemble | *TSMC's $64 Billion Investment Signals Mega-Growth* | nessuno — P0-05 |
| 14:30 | SPCX | +0,4021 | 0,650 | ensemble | *SpaceX's Real Financial Engine Isn't Rockets or AI* | **BUY 14:37** |
| 15:15 | MU | −0,3239 | 0,600 | ensemble | *SK Hynix Shares Plunge 10%…* | sotto soglia (long-only) |
| 15:15 | WDC | −0,3128 | 0,550 | ensemble | *Western Digital Stock's Worst Drop Since March 2020* | nessuno; WDC resta in libro |

---

## 5. Tabella performance modelli LLM

| Modello | risposte | polarity media | confidence media | `eligible` | segnali dove ha dominato |
|---|--:|--:|--:|--:|--:|
| `glm-5.2:cloud` | 163 | +0,044 | **0,231** | 28 (17,2 %) | 8 (`single:glm-5.2:cloud`) |
| `gpt-oss:20b-cloud` | 157 | +0,018 | **0,359** | 28 (17,8 %) | 39 (`single:gpt-oss:20b-cloud`) |
| **FinBERT** | **0** | — | — | — | **0** |

| Composizione del segnale | n | quota | conf media | \|score\| medio | ensemble_std medio |
|---|--:|--:|--:|--:|--:|
| `ensemble:glm-5.2+gpt-oss` | 116 | 71,2 % | 0,280 | 0,0604 | 0,0504 |
| `single:gpt-oss:20b-cloud` | 39 | 23,9 % | 0,478 | 0,0747 | 0 |
| `single:glm-5.2:cloud` | 8 | 4,9 % | 0,363 | 0,0803 | 0 |

* **Richieste/timeout/refusal:** non ricostruibili. La tabella `llm_responses` registra solo le
  risposte **riuscite**; latenza, timeout, output non parsabili e retry vivono solo nei log dei
  container, distrutti ([DAY-002]). I 6 segnali con una sola risposta glm (163 vs 157) indicano
  almeno 6 mancate risposte di `gpt-oss`, ma non se per timeout o per output invalido.
* **Fallback rate:** 47/163 = **28,8 %** dei segnali sono single-model. **Zero FinBERT**: il
  contatore `consecutive_fallback` vale 0, azzerato alle 19:46. Ollama **up** per l'intera sessione.
* **Distribuzione degli score:** 84/163 (**51,5 %**) sono esattamente 0,000; 11 (6,7 %) hanno
  |score| ≥ 0,30; 6 (3,7 %) ≥ 0,40. Confidence mediana molto bassa (glm 0,231): giornata di
  informazione debole, non di modelli rotti.
* **Disaccordo:** `ensemble_std` massimo 0,354, mediana 0,071. Nessun caso di divergenza estrema.

### Verifiche funzionali

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Sì** — polarity/confidence tipizzate, `score = polarity × confidence`, JSON strutturato | 0 righe malformate su 163 |
| L'ensemble gestisce la varianza alta? | **Sì, ma in modo grossolano** — se un modello non risponde il segnale diventa `single:*` con `fallback_used=true` ed è escluso da BUY e da force-SELL (#108) | `portfolio_scheduler.py:1005-1016, 3429-3438, 4043-4046` |
| Le news duplicate pesano più volte? | **No per URL identico** (vincolo `uq_news_log_url_ticker`); **sì di fatto** per fan-out: lo stesso articolo produce fino a 11 segnali su ticker diversi | §4 |
| La stessa news può generare segnali multipli? | **Sì**, e l'ultimo vince (F-023) | TSM 14:45 +0,610 → 15:15 −0,057 |
| La confidence bassa riduce il peso? | **Sì, per costruzione** — `score = polarity × confidence`. 51,5 % degli score è 0 anche per confidence 0,10–0,20 | §5 |
| I modelli sono chiamati offline? | **Sì** — coda `inference` dedicata, `worker-inference` concurrency=1; il portfolio cycle legge da Postgres | `celery_app.py` |
| Una hallucination può entrare in decisione? | **Sì, ma filtrata** — serve superare gate + freschezza + ensemble non-fallback. Il rischio residuo reale non è l'hallucination ma la **mis-attribuzione del ticker** ([F-020]) | §4 |

---

## 6. Tabella segnali finali per ticker (sopra 0,20 in valore assoluto)

| Ora UTC | Ticker | Score | Conf | Modello | Sopra soglia? | Decisione |
|---|---|--:|--:|---|---|---|
| 14:15 | MSFT | +0,5075 | 0,725 | ensemble | **sì** (0,350) | **BUY 14:22** |
| 14:15 | SPCX | +0,2400 | 0,600 | single | no (escluso #108) | — |
| 14:30 | SPCX | +0,4021 | 0,650 | ensemble | **sì** (0,350) | **BUY 14:37** |
| 14:45 | TSM | +0,6104 | 0,800 | ensemble | **sì** | **nessuna riga** — P0-05 |
| 14:16 / 14:46 | NVO | +0,2082 / +0,2215 | 0,575 / 0,650 | ensemble | no (0,266 < 0,350) | `SKIP_THRESHOLD` ×9 — **mover +3,23 %** |
| 15:15 | GS | +0,3897 | 0,675 | ensemble | no | `SKIP_THRESHOLD` |
| 15:15 | MU | −0,3239 | 0,600 | ensemble | n/a (long-only) | — |
| 15:15 | WDC | −0,3128 | 0,550 | ensemble | n/a | posizione S4 **mantenuta** |
| 16:02 | TSM | +0,4062 | 0,625 | ensemble | **sì** | **nessuna riga** — P0-05 |
| 16:15 | GS | +0,4225 | 0,650 | single | no (escluso #108) | — |
| 16:45 | SPCX | +0,5600 | 0,700 | single | no (escluso #108) | — |
| 16:45 | TSLA | +0,2985 | 0,625 | ensemble | no | `SKIP_THRESHOLD` |
| 17:00 | SPCX | −0,3600 | 0,600 | single | n/a | — |
| 19:00 | IWM | −0,3600 | 0,600 | single | n/a | — |
| 19:15 | XLE | +0,2700 | 0,675 | ensemble | no | `SKIP_THRESHOLD` |
| 15:31 | LLY | +0,2574 | 0,550 | ensemble | no | `SKIP_THRESHOLD` |

**Decisioni persistite: 705.** `SKIP_THRESHOLD` 690 (244 a soglia 0,350 fino alle 16:22; 446 a
soglia 0,400 dalle 16:37), `SELL` 7, `BUY` 6, `SKIP_STALE` 2. In più 411 `SIGNAL_STALE_SKIP` in
`audit_log` (non in `execution_decisions`).

---

## 7. Tabella ordini generati/eseguiti

Tutti gli ordini sono **paper** (`system:mode=paper`, `portfolio_monitor.source=alpaca_paper`,
`execution.engine=portfolio`). Tutti market, tutti riempiti nello stesso ciclo, **0 reject**,
**0 cancellazioni**.

| # | Ora UTC | Strategia | Ticker | Azione | Qty | Prezzo fill | Nozionale | Peso dichiarato | Peso reale | Trade | Segnale | Esito | Risk check |
|--:|---|---|---|---|--:|--:|--:|--:|--:|--:|--:|---|---|
| 1 | 14:22 | S4 | MSFT | BUY | 2,3543 | 498,34 | 1.173,24 | 2,0 % | 1,07 % | 666 | 6689 (+0,508) | filled | regime ×0,7, gate 0,350 |
| 2 | 14:22 | S1 | BRK.B | SELL | 1,8577 | 518,04 | 962,36 | 0,0 % | — | 659 (close) | — | filled +0,77 | `s1_weight_drop` |
| 3 | 14:22 | S1 | SBUX | SELL | 9,0192 | 103,93 | 937,36 | 0,0 % | — | 655 (close) | — | filled −13,87 | `s1_weight_drop` |
| 4 | 14:37 | S4 | SPCX | BUY | 10,3750 | 113,07 | 1.173,11 | 2,0 % | 1,07 % | 667 | 6699 (+0,402) | filled | regime ×0,7, gate 0,350 |
| 5 | 14:37 | S1 | ABBV | SELL | 2,7192 | 241,51 | 656,68 | 0,0 % | — | 650 (close) | — | filled −6,89 | `s1_weight_drop` |
| 6 | 14:52 | S1 | ABBV | BUY | 2,8867 | 243,18 | 701,99 | 1,2 % | 0,64 % | 668 | — | filled | **15 min dopo la #5** |
| 7 | 16:07 | S1 | MMM | SELL | 4,2278 | 179,75 | 759,96 | 0,0 % | — | 584 (close) | — | filled +18,16 | `s1_weight_drop` |
| 8 | 16:07 | S4 | MSFT | SELL | 2,3543 | 495,13 | 1.165,68 | 0,0 % | — | 666 (close) | — | filled −7,79 | `whipsaw`, shadow `would_suppress=True` |
| 9 | 16:22 | S1 | MMM | BUY | 3,8831 | 180,05 | 699,16 | 1,2 % | 0,64 % | 669 | — | filled | **15 min dopo la #7** |
| 10 | 17:22 | S1 | BRK.B | BUY | 1,3089 | 522,35 | 683,73 | 1,2 % | 0,62 % | 670 | — | filled | **3 h dopo la #2** |
| 11 | 18:07 | S1 | MMM | SELL | 3,8831 | 179,72 | 697,88 | 0,0 % | — | 669 (close) | — | filled −1,66 | hold-min 105 min ✔ |
| 12 | 18:52 | S1 | MMM | BUY | 3,7981 | 180,16 | 684,28 | 1,2 % | 0,62 % | 671 | — | filled | **45 min dopo la #11** |
| 13 | 18:52 | S4 | SPCX | SELL | 10,3750 | 109,93 | 1.140,54 | 0,0 % | — | 667 (close) | — | filled −34,98 | `expired` 4,4 h > 4 h |

Riconciliazione: 13 `order_id` in `execution_decisions` → 6 `INSERT` in `audit_log` + 6 righe nuove
in `trades` + 7 chiusure con `exit_price`, `exit_time`, `net_pnl` valorizzati. **Nessun orfano in
nessuna delle due direzioni.**

---

## 8. Tabella PnL / rendimento

### Realizzato (7 uscite)

| Trade | Ticker | Strategia | Aperta | Chiusa | Ore | Gross | Costi | **Net** | Drift post-uscita |
|--:|---|---|---|---|--:|--:|--:|--:|--:|
| 584 | MMM | S1 | 2026-07-30 | 16:07 | 167,8 | +18,56 | 0,40 | **+18,16** | +4,06 |
| 659 | BRK.B | S1 | 2026-08-05 | 14:22 | 19,5 | +1,29 | 0,52 | **+0,77** | +12,21 |
| 669 | MMM | S1 | 2026-08-06 16:22 | 18:07 | 1,75 | −1,28 | 0,38 | **−1,66** | +3,84 |
| 650 | ABBV | S1 | 2026-08-04 | 14:37 | 43,8 | −6,53 | 0,36 | **−6,89** | +6,42 |
| 655 | SBUX | S1 | 2026-08-05 | 14:22 | 23,5 | −13,35 | 0,52 | **−13,87** | +11,09 |
| 666 | MSFT | S4 | 2026-08-06 14:22 | 16:07 | 1,75 | −7,56 | 0,23 | **−7,79** | +11,14 |
| 667 | SPCX | S4 | 2026-08-06 14:37 | 18:52 | 4,25 | −32,57 | 2,40 | **−34,98** | **+51,77** |
| | | | | | | | | **−46,26** | **+100,53** |

**Per strategia:** S1 **−3,49 $** (5 uscite) · S4 **−42,77 $** (2 uscite).
**Per origine:** posizioni aperte **prima** del 08-06 → −1,83 $ (4 uscite); posizioni aperte **il**
08-06 → −44,43 $ (3 uscite). Il rosso del giorno è tutto intraday.

### Non realizzato e NAV

| Grandezza | Valore |
|---|--:|
| NAV 08-05 → 08-06 | 110.239,74 → **110.051,33 $** = **−187,77 $** (−0,17 %) |
| Realizzato | −46,26 $ |
| MTM del libro aperto (dossier) | **−292,31 $** |
| di cui WDC da sola | **−201,67 $** = 100 % dell'MTM S4 |
| Unrealized cumulato a libro (snapshot 20:00) | +892,36 $ |
| Gross exposure a chiusura | 28,77 % (limite 50 %) |
| Drawdown a chiusura | 0,5172 % (limite 5 %) |
| Posizioni aperte | 48 |
| Benchmark: SPY −0,16 % · QQQ −0,37 % · dispersione 2,24 % | |

### Costi

| Voce | Valore |
|---|--:|
| Costi espliciti registrati sulle 10 gambe tradate | **5,89 $** |
| di cui SPCX (spread 20 bps su un nome largo) | 2,40 $ |
| Costo medio delle gambe S1 | 5,19 bps (spread 5,00 + impact ~0,19) |
| **Slippage stimato** | **non misurato** — `slippage_est` è una copia esatta di `cost_usd` su tutte e 10 le righe ([DAY-008], F-015) |

*Non ricalcolabile senza dati aggiuntivi:* lo slippage vero richiede il mid al momento del submit,
che non è persistito da nessuna parte. Query che servirebbe se lo fosse:
`SELECT symbol, entry_price, mid_at_submit FROM trades …` — la colonna non esiste.

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|:-:|---|
| BUY generati solo quando consentito | ✔ | 6 BUY: 2 S4 sopra gate 0,350 con segnale ensemble fresco, 4 S1 da ranking momentum |
| SELL/exit generati correttamente | ✔ | 7 SELL: 5 `s1_weight_drop`, 1 `whipsaw`, 1 `expired`; tutte con `exit_mechanism` popolato |
| Stop-loss rispettati | ⚠ non verificabile | `stop_decisions` vuoto per il giorno; il sync degli stop vive solo nei log ([DAY-002]) |
| Signal flip rispettato | ✔ | MSFT uscita su score sceso a +0,012; nessun flip ignorato |
| Max holding days rispettato | ✔ | S4: `max_signal_age` 4 h applicato a SPCX (4,4 h). S1: nessun limite di tempo per design |
| Rebalance band rispettata | ✘ | `abs(delta) < max(1e-4, target_qty*0.02)` è l'unica banda; **nessuna isteresi temporale** su S1, che ricalcola il ranking ogni 15 min ([DAY-006]) |
| Nessun ordine duplicato | ✔ | 13 ordini, 13 `order_id` distinti, nessuna coppia stesso simbolo/stesso minuto |
| Nessun ordine contrario senza rationale | ⚠ | i 5 round-trip hanno un rationale (`s1_weight_drop` ↔ ranking) ma il rationale è generato da un ribilanciamento a frequenza sbagliata ([DAY-006]) |
| Nessun ordine su ticker non consentiti | ✔ | 13 ordini su 6 simboli, tutti in `symbols.watchlist` |
| Nessun ordine fuori orario | ✔ | primo 14:22, ultimo 18:52 — dentro 13:30–20:00 |
| Nessun trade su dati stale | ✔ | 411 `SIGNAL_STALE_SKIP` + 2 `SKIP_STALE`; entrambi i BUY S4 su segnali di 7 e 7 minuti |
| Nessun trade su output LLM invalido | ✔ | 0 righe malformate; i 47 single-model esclusi per design (#108) |
| Nessun trade con circuit breaker attivo | ✔ | nessuna chiave `halt` in Redis; drawdown 0,52 % ≪ 5 % |
| Nessun trade su strategia disabilitata | ✔ | `strategies_run = ["S1","S4"]` su tutti e 24 i cicli |
| Paper/live coerente | ✔ | `system:mode=paper`, `source=alpaca_paper`, S1 `supervised_paper`, S4 `paper` |
| Idempotenza su retry Celery | ✔ | 6 `SIGNAL_DUPLICATE_SKIP` (MSFT 6689 ×2, SPCX 6699 ×4) |
| Riconciliazione ordini↔fill↔posizioni | ✔ | 13 ordini → 13 fill → 6 aperture + 7 chiusure, 0 orfani |
| **SELL con sentiment positivo** | ✘ | MSFT venduta con score **+0,012** (F-013): l'uscita non richiede un segnale negativo, solo un peso a 0 |
| **Roundtrip < 30 min** | ✘ | ABBV SELL 14:37 → BUY 14:52 (**15 min**); MMM SELL 16:07 → BUY 16:22 (**15 min**) |
| Pyramiding (> 3 BUY consecutivi) | ✔ | P0-05 blocca ogni BUY su simbolo con trade aperto — è ciò che ha neutralizzato TSM |
| `fallback_used=True` su tutti i simboli | ✔ no | 28,8 %, con Ollama up tutto il giorno |
| NO-ORDER (decisione senza ordine) | ✔ no | tutte e 13 le decisioni con `order_id` hanno un fill |
| Score < 0,05 che generano ordini | ✔ no | il campo `score` delle decisioni S1 (0,0117–0,0120) è il **peso target**, non il sentiment |
| Ordini identici nello stesso minuto | ✔ no | — |

---

## 10. Anomalie trovate

### [DAY-001] Il ciclo forense del 2026-08-05 non ha mai aggiornato il ledger delle evidenze

* **Tipo:** Bug
* **Area:** Ops (protocollo di osservazione)
* **Evidenza:**
  * file: `docs/evidence/findings.json`, `logs/daily_analysis_2026-08-06.log`, `git log`
  * timestamp: run iniziato `2026-08-06T12:30:01Z`, mai completato
  * query / snippet:
    ```
    $ git log --format="%h %ad %s" --date=iso -- docs/evidence/findings.json
    58058aa 2026-08-07 10:10:46  evidence: ledger 2026-08-06     ← alpha-miss di oggi
    865a408 2026-08-06 10:11:25  evidence: ledger 2026-08-05     ← alpha-miss di ieri
    13e87af 2026-08-05 14:50:59  evidence: forensic 2026-08-04   ← ultimo commit forense
    #  NESSUN "evidence: forensic 2026-08-05"

    $ cat logs/daily_analysis_2026-08-06.log
    === Alembic Daily Analysis 2026-08-06 (target: 2026-08-05) ===
    Started: 2026-08-06T12:30:01Z
    Report: .../FORENSIC_DAILY_REPORT_2026-08-05.md
    #  nessuna riga "Completed:", a differenza di tutti gli altri log
    ```
* **Descrizione:** il report `FORENSIC_DAILY_REPORT_2026-08-05.md` è stato scritto per intero
  (1.079 righe, 15 anomalie) ma la sessione è terminata prima dell'aggiornamento del ledger. Il file
  del report è finito in git solo per caso, catturato il 08-07 da un commit di roadmap non correlato
  (`406c2dc`). Conseguenze: (a) le quattro anomalie **nuove** di quel report — la suite di test che
  scrive nel DB di produzione, il guasto DNS tradotto in «mercato chiuso», i segnali scritti come
  `BRKB` invece di `BRK.B`, la soglia S4 che si muove da sola — **non esistono in `findings.json`**;
  (b) le ricorrenze di quel giorno su F-003, F-004, F-010, F-014, F-015, F-016, F-018, F-021, F-022,
  F-024 sono perse; (c) il report cita gli id `F-025..F-028` per le sue anomalie nuove, ma **F-025 è
  già stato assegnato** dall'alpha-miss di oggi a un finding diverso: due documenti nel repo usano
  ora lo stesso id per due cose diverse.
* **Impatto:** la carta di osservazione decide cosa merita lavoro il 28/09 sulla base di soglie di
  **ricorrenza e costo cumulato** lette da `findings.json`. Un giorno di findings mancante abbassa
  di uno la ricorrenza di dieci difetti e riduce il costo cumulato; quattro difetti nuovi restano
  fuori dal conteggio del tutto. È il difetto più grave possibile in questa finestra perché **non
  degrada il trading, degrada la misura**.
* **Severità:** High
* **Confidenza:** High — assenza di commit e di riga `Completed:` verificabili entrambe.
* **Azione consigliata:** ticket di correttezza (esente dal congelamento). (a) Scrivere il ledger
  **prima** del report, non dopo, così che un timeout perda la prosa e non l'evidenza; (b) far
  fallire lo script con exit code ≠ 0 se il commit del ledger non avviene; (c) riconciliare gli id:
  i quattro findings del 08-05 vanno creati con id nuovi e il report del 08-05 va annotato.
* **Test/monitor consigliato:** un check giornaliero che verifica l'esistenza di un commit
  `evidence: forensic <data>` per ogni giorno di borsa della finestra, e allerta se manca.

---

### [DAY-002] Il redeploy delle 11:08 di oggi ha distrutto tutti i log dei container del 2026-08-06

* **Tipo:** Bug
* **Area:** Ops / Data
* **Evidenza:**
  * comando: `docker inspect --format '{{.State.StartedAt}} {{.RestartCount}}'`
  * timestamp: `2026-08-07T11:08:12Z`, `restarts=0` su tutti e quattro i container della pipeline
  * snippet:
    ```
    /alembic-worker-1            started=2026-08-07T11:08:12Z restarts=0
    /alembic-beat-1              started=2026-08-07T11:08:12Z restarts=0
    /alembic-api-1               started=2026-08-07T11:08:12Z restarts=0
    /alembic-worker-inference-1  started=2026-08-07T11:08:12Z restarts=0

    $ docker compose logs worker --since 60h | grep -c "2026-08-06"
    0
    #  il log più vecchio disponibile è 2026-08-07 11:08:17
    ```
* **Descrizione:** `restarts=0` con `StartedAt` di oggi significa che i container sono stati
  **ricreati** (deploy della PR #194, `fix(fwd-returns)`), non riavviati: il buffer di log del
  vecchio container è stato eliminato con esso. Non esiste logging su file per la pipeline. Il ciclo
  alpha-miss delle 08:00 di stamattina ha ancora potuto leggerli — cita testualmente
  `S4 feedback gate: dropped 33/35 signals below threshold 0.350` e
  `Hold minimum (90 min): skipped 1 SELL order(s)` — mentre questa sessione, tre ore dopo, non può.
  È lo stesso incidente del 2026-07-15 (log persi da restart), mai corretto.
* **Impatto:** per il 2026-08-06 non sono verificabili: latenza e timeout LLM, sync degli stop
  protettivi (`fractional_stop_sync`), conteggio dei segnali scartati dal gate, consegna degli
  alert Telegram, eccezioni non propagate, e in generale **ogni fallimento che non lasci una riga in
  Postgres**. Il protocollo forense di questa finestra dipende da una fonte che qualunque deploy può
  cancellare, e i deploy sono attesi (la carta ne prevede almeno due, #185 e #191).
* **Severità:** High
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza. Configurare un driver di logging persistente
  (`json-file` con rotazione su volume, o `journald`) per i quattro servizi, così che i log
  sopravvivano al ciclo di vita del container.
* **Test/monitor consigliato:** il preflight del cron forense verifica che i log del container
  coprano il giorno target; se non lo coprono, lo dichiara in testa al report invece di produrre
  silenziosamente un'analisi parziale.

---

### [DAY-003] La suite di test continua a scrivere in `ingestion_stats_daily` del database di produzione

* **Tipo:** Bug
* **Area:** Data / Ops
* **Evidenza:**
  * tabella: `ingestion_stats_daily`, righe `source='reuters'`
  * timestamp: `2026-08-06 12:35:58`, `2026-08-07 09:02:07`
  * query:
    ```sql
    SELECT * FROM ingestion_stats_daily WHERE day >= '2026-08-04' ORDER BY day, source;
    -- 2026-08-06 | reuters |  4 |  4 | 0 | 1 | 0 | 0 | 2026-08-06 12:35:58
    -- 2026-08-07 | reuters | 16 | 16 | 0 | 4 | 0 | 0 | 2026-08-07 09:02:07
    SELECT count(*) FROM news_log WHERE source='reuters';  -- 0
    ```
* **Descrizione:** ricorrenza esatta del difetto isolato dal report del 08-05 (che però non è mai
  entrato nel ledger, vedi [DAY-001]): `tests/workers/test_rss_ingestion.py` forza
  `RSS_INGESTION_ENABLED=1` e chiama `run_rss_ingestion_worker()` senza mockare `PostgreSQLStore`,
  che apre una connessione al `DATABASE_URL` d'ambiente — il Postgres di produzione. **Novità di
  oggi:** la riga del 2026-08-07 ha `fetched=16, discarded_no_ticker=4`, quattro volte i valori
  canonici (4/1): la suite è stata eseguita **quattro volte** stamattina. Il difetto non è
  stazionario, sta accelerando con l'attività di sviluppo.
* **Impatto:** `ingestion_stats_daily` è una delle tabelle di audit di questo stesso protocollo e
  contiene dati falsi indistinguibili dai veri. Il rischio strutturale è più ampio: **una `pytest`
  lanciata nella directory del repo scrive nel DB live**, e nulla impedisce che un test futuro
  tocchi `trades` o `execution_decisions` durante la finestra di osservazione.
* **Severità:** High
* **Confidenza:** High — i numeri della riga sono derivabili dal codice dei due test.
* **Azione consigliata:** ticket di correttezza. (a) `conftest.py` che fallisce se `DATABASE_URL`
  punta al DB `trading` di produzione; (b) mockare `PostgreSQLStore` nei test RSS; (c) ripulire le
  righe `source='reuters'` con una migrazione tracciata.
* **Test/monitor consigliato:** fixture autouse che asserisce l'assenza di connessioni al DB live
  durante la suite; check giornaliero su `source` non presenti nel beat schedule attivo.

---

### [DAY-004] Il ramo S1 del loop di loss-feedback è interamente inerte

* **Tipo:** Rischio
* **Area:** Risk
* **Evidenza:**
  * chiave Redis: `feedback:state:S1`, `feedback:entry_threshold:S1`, `feedback:regime_scale:S1`
  * timestamp: `2026-08-06T14:00:00.062890+00:00`
  * snippet:
    ```
    feedback:state:S1 = {"reason": "3 consecutive losses", "ewma_r": -0.4965,
      "consecutive_losses": 3, "rolling_net_pnl": -169.07,
      "threshold_before": 0.3, "threshold_after": 0.0,
      "scale_before": 0.25, "scale_after": 0.2}
    feedback:entry_threshold:S1 = 0.0
    feedback:regime_scale:S1    = 0.2
    ```
    ```python
    # src/workers/performance.py:1975-1980
    new_threshold = min(current_threshold + cfg["threshold_step"], cfg["threshold_max"])
    new_scale = max(current_scale * cfg["regime_scale_factor"], cfg["regime_min_scale"])
    # S1 has no discrete entry-threshold gate; persist state only.
    if strategy == "S1":
        new_threshold = 0.0
    ```
    ```yaml
    # config/trading.yaml:350
    apply_regime_scale: false
    ```
* **Descrizione:** alle 14:00, dopo tre perdite consecutive, il loop si è attivato su S1. Le sue due
  leve sono: (1) alzare la soglia d'ingresso — **azzerata per design**, perché S1 non ha un gate
  discreto; (2) ridurre il `regime_scale` — che è **shadow-only** (`apply_regime_scale: false`, F8
  ritirato con #134). Il risultato è che l'unico effetto dell'attivazione è la scrittura di una
  chiave di stato. S1 ha continuato a operare identica per il resto della sessione, aprendo tre
  posizioni **dopo** l'attivazione (MMM 16:22, BRK.B 17:22, MMM 18:52). Da notare l'asimmetria con
  S4, che nella stessa giornata ha visto la propria soglia salire due volte (0,350 → 0,400 → 0,450).
* **Impatto:** la strategia che muove il 50 % dell'allocazione non ha **nessuna** protezione
  automatica dalle perdite consecutive, mentre quella che ne muove il 10 % ne ha una che si stringe
  fino a fermarla. Il rischio non è che il loop sbagli, è che il suo stato in Redis (`"reason": "3
  consecutive losses"`, `threshold_after: 0.0`) faccia sembrare che una protezione ci sia. Va
  registrato ora perché **è un fatto sulla finestra di osservazione**: la domanda di uscita n.2
  chiede se S1 abbia un edge, e la risposta va letta sapendo che S1 non è mai stata frenata.
* **Severità:** Medium
* **Confidenza:** High — le tre righe di codice e la chiave di config lo determinano.
* **Azione consigliata:** **nessuna modifica ora** — cambiare il comportamento di S1 sarebbe
  taratura, che la carta congela. Ticket di sola **osservabilità**: rendere esplicito nello stato
  che il ramo S1 è no-op (`"applied": false`) invece di scrivere numeri che sembrano applicati.
* **Test/monitor consigliato:** un test che asserisce che `feedback:*:S1` non influenzi la size di
  nessun ordine finché `apply_regime_scale` è false, così che il giorno in cui il flag viene
  flippato la differenza sia visibile.

---

### [DAY-005] Il segnale più forte della giornata (TSM +0,610) non produce né ordine né riga di decisione

* **Tipo:** Bug (ricorrenza di **F-023**, in forma nuova)
* **Area:** Signal / Orders
* **Evidenza:**
  * tabelle: `sentiment_signals` id 6706, `execution_decisions`, `trades`
  * timestamp: segnale `2026-08-06 14:45:25`, cicli scoperti 14:52 e 15:07
  * query:
    ```sql
    SELECT id, generated_at, score, confidence, model_id, fallback_used
    FROM sentiment_signals WHERE symbol='TSM' AND created_at::date='2026-08-06';
    -- 6706 | 14:45:25 |  0.6104 | 0.800 | ensemble:glm-5.2+gpt-oss | f   ← max del giorno
    -- 6725 | 15:15:46 | -0.0573 | 0.225 | ensemble:glm-5.2+gpt-oss | f
    -- 6756 | 16:02:09 |  0.4062 | 0.625 | ensemble:glm-5.2+gpt-oss | f

    SELECT tick_time, decision, signal_score FROM execution_decisions
    WHERE symbol='TSM' AND tick_time::date='2026-08-06' ORDER BY 1;
    -- 14:07:15 | SKIP_STALE     | -0.1439
    -- 15:22:10 | SKIP_THRESHOLD | -0.0573     ← nessuna riga alle 14:52 né alle 15:07
    ```
    ```python
    # src/workers/portfolio_scheduler.py:2676-2678
    if order.side.value == "BUY" and isinstance(open_db_symbols, set) and order.symbol in open_db_symbols:
        log.info("P0-05: skipping BUY decision for %s — already has an open trade", order.symbol)
        continue          # ← esce PRIMA di persistere la decisione
    ```
* **Descrizione:** TSM ha prodotto il segnale più convinto della giornata (+0,6104, confidence 0,800,
  ensemble non-fallback, su un articolo TSM-specifico e materiale: *«Taiwan Semiconductor Raised Its
  2026 Outlook as AI Demand…»*). Non ha generato nulla, per due meccanismi sovrapposti. **Primo:**
  S1 tiene TSM dal 2026-07-14, quindi il guard anti-pyramiding P0-05 ha scartato il BUY — e lo ha
  fatto con un `continue` che precede la scrittura in `execution_decisions`, lasciando **zero
  tracce** in Postgres. L'unica traccia era una riga `log.info` nel container, oggi distrutta
  ([DAY-002]). **Secondo:** entro le 15:15 il segnale era comunque stato sovrascritto da uno a
  −0,057 su un articolo diverso, che è quello con cui i cicli successivi hanno valutato TSM — F-023
  esatta, con l'aggravante che qui l'intervallo è 30 minuti e la caduta è da +0,61 a −0,06.
* **Impatto:** il Decision Log, che è la fonte primaria di questo protocollo, **non contiene** il
  segnale più forte della giornata. Un'analisi che parta da `execution_decisions` conclude che TSM
  non è mai stato un candidato. In termini di alpha il costo è nullo o negativo (TSM ha fatto
  +1,01 %, e la posizione S1 lo catturava già), ma in termini di **misurabilità** questa è la classe
  di buchi che rende la finestra meno leggibile: non sappiamo quante volte al giorno succeda.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza (osservabilità, non taratura): persistere una riga
  `SKIP_PYRAMIDING` in `execution_decisions` prima del `continue`, come già si fa per
  `SKIP_THRESHOLD` e `SKIP_STALE`. Il comportamento di trading resta invariato.
* **Test/monitor consigliato:** invariante giornaliera — ogni segnale con score sopra la soglia
  d'ingresso effettiva deve avere almeno una riga in `execution_decisions` nel ciclo successivo.

---

### [DAY-006] Churn di S1: cinque round-trip intraday su tre simboli, uno a 15 minuti di distanza

* **Tipo:** Bug (ricorrenza di **F-013**, con meccanismo distinto)
* **Area:** Orders
* **Evidenza:**
  * tabelle: `trades` id 584/650/659/668/669/670/671, `execution_decisions`
  * timestamp: 14:22–18:52
  * query:
    ```sql
    SELECT tick_time, symbol, decision, left(reason,45) FROM execution_decisions
    WHERE tick_time::date='2026-08-06' AND order_id IS NOT NULL AND symbol IN ('ABBV','MMM','BRK.B')
    ORDER BY tick_time;
    -- 14:22 | BRK.B | SELL | [s1_weight_drop] S1 target weight dropped to 0%
    -- 14:37 | ABBV  | SELL | [s1_weight_drop] …
    -- 14:52 | ABBV  | BUY  | S1 momentum: time-series momentum signal, 1.2%   ← +15 min
    -- 16:07 | MMM   | SELL | [s1_weight_drop] …
    -- 16:22 | MMM   | BUY  | S1 momentum …                                    ← +15 min
    -- 17:22 | BRK.B | BUY  | S1 momentum …                                    ← +3 h
    -- 18:07 | MMM   | SELL | [s1_weight_drop] …
    -- 18:52 | MMM   | BUY  | S1 momentum …                                    ← +45 min
    ```
* **Descrizione:** S1 dichiara ribilanciamento **mensile** ma il path live ricalcola il ranking a
  ogni ciclo da 15 minuti (#185, deroga registrata nella carta il 2026-08-06 ma **non ancora
  deployata**: nessun commit corrispondente in `git log`). Il risultato osservato: MMM venduta e
  ricomprata **due volte** nella stessa sessione, ABBV ricomprata 15 minuti dopo essere stata
  venduta, BRK.B ricomprata dopo 3 ore. Ogni round-trip paga due volte lo spread (5,19 bps a gamba)
  e ricompra sistematicamente **più caro** di quanto ha venduto (ABBV 243,18 vs 241,51; MMM 180,05
  vs 179,75 e 180,16 vs 179,72; BRK.B 522,35 vs 518,04). Il guard hold-minimum a 90 minuti non
  interviene perché protegge il lato SELL-dopo-BUY, non BUY-dopo-SELL.
* **Impatto:** costo attribuito del giorno **16,20 $**, calcolato come somma su ogni round-trip di
  (prezzo di riacquisto − prezzo di vendita) × qty riacquistata, più i costi espliciti delle due
  gambe: BRK.B (522,354−518,04)×1,3089 + 0,88 = 6,53 $; ABBV (243,18−241,51)×2,7192 + 0,72 = 5,26 $;
  MMM gamba 1 (180,05−179,75)×3,8831 + 0,78 = 1,95 $; MMM gamba 2 (180,16−179,72)×3,7981 + 0,73 =
  2,40 $. Il controfattuale è corto e non ambiguo: senza ribilanciamento a 15 minuti nessuno dei
  quattro round-trip avviene. Su base annua a questa cadenza il drag è di ordine ×250.
* **Severità:** Medium
* **Confidenza:** High (misura) / Medium (attribuzione — il controfattuale «S1 non avrebbe tradato»
  discende dalla frequenza dichiarata, non da un replay).
* **Azione consigliata:** **già coperta dalla deroga #185** registrata nella carta. Questo report ne
  misura il costo su un giorno; non propone taratura aggiuntiva. Da notare che il deploy non è
  avvenuto: le evidenze S1 continuano a essere raccolte sull'oggetto sbagliato.
* **Test/monitor consigliato:** contatore giornaliero dei round-trip intraday per strategia
  (`SELL` e `BUY` sullo stesso simbolo nella stessa sessione), con soglia di allerta.

---

### [DAY-007] Il peso dichiarato nel Decision Log è quasi il doppio di quello eseguito, e `constraints_fired` è vuoto

* **Tipo:** Bug (ricorrenza di **F-014**, meccanismo nuovo)
* **Area:** Orders / Ops
* **Evidenza:**
  * tabelle: `execution_decisions.reason`, `trades.entry_notional`, `portfolio_cycles.constraints_fired`
  * timestamp: tutti e 6 i BUY del giorno
  * query:
    ```sql
    SELECT symbol, entry_notional, entry_notional/110200.0*100 AS pct_reale FROM trades
    WHERE entry_time::date='2026-08-06';
    -- MSFT  | 1173.24 | 1.065 %   ← reason dice "portfolio weight 2.0%"
    -- SPCX  | 1173.11 | 1.064 %   ← reason dice "portfolio weight 2.0%"
    -- ABBV  |  701.99 | 0.637 %   ← reason dice "portfolio weight 1.2%"
    -- MMM   |  699.16 | 0.634 %   ← reason dice "portfolio weight 1.2%"
    -- BRK.B |  683.73 | 0.620 %   ← reason dice "portfolio weight 1.2%"
    SELECT DISTINCT constraints_fired FROM portfolio_cycles WHERE timestamp::date='2026-08-06';
    -- []   (su tutti e 24 i cicli)
    ```
    ```python
    # src/portfolio/orchestrator.py:295  → quantità = nav * target_wt / price
    # src/workers/portfolio_scheduler.py:2683 → wt_pct = order.allocation_weight * 100
    # src/portfolio/combiner.py:104-107 → il vol-targeter scala le quantità DOPO,
    #                                     senza toccare allocation_weight
    ```
* **Descrizione:** il testo della decisione riporta `allocation_weight`, cioè il peso **target
  pre-vincoli**. Fra quel valore e l'ordine effettivo agiscono il moltiplicatore di regime (×0,7,
  registrato a parte in `regime_mult`) e il vol-targeter, che riscala le quantità aggregate senza
  aggiornare `allocation_weight`. Il fattore residuo osservato è uniforme su tutti e sei gli ordini
  (0,758 dopo il regime, 0,532 in totale), il che conferma che si tratta di uno scaling di
  portafoglio e non di un arrotondamento per simbolo. Nessuno dei due passaggi lascia una riga:
  `constraints_fired` è `[]` su tutti e 24 i cicli.
* **Impatto:** chiunque legga il Decision Log — questo protocollo per primo — conclude che S4 ha
  preso una posizione al 2 % del NAV quando ne ha presa una all'1,07 %. Per la carta di osservazione
  la conseguenza è diretta: il **P&L economico** di S4 sulla finestra, che è il criterio della
  domanda di uscita n.1, dipende dalla size, e la size dichiarata è sbagliata di un fattore 1,9.
* **Severità:** Medium
* **Confidenza:** High per la discrepanza (aritmetica); Medium per l'attribuzione al vol-targeter
  (dedotta dal codice, non da un replay, perché i log del ciclo non esistono più).
* **Azione consigliata:** ticket di correttezza (osservabilità): scrivere nel `reason` il peso
  **effettivo** post-vincoli, o aggiungere un campo separato; popolare `constraints_fired` con lo
  scaling applicato e il suo motivo.
* **Test/monitor consigliato:** invariante — per ogni BUY, `entry_notional / nav` deve stare entro
  il 5 % del peso dichiarato nel `reason`, o il ciclo deve registrare quale vincolo ha fatto la
  differenza.

---

### [DAY-008] `slippage_est` è una copia esatta di `cost_usd` su tutte le gambe del giorno

* **Tipo:** Bug (ricorrenza di **F-015**)
* **Area:** PnL
* **Evidenza:**
  * tabella: `trades`
  * timestamp: tutte e 10 le gambe tradate il 2026-08-06
  * query:
    ```sql
    SELECT id, symbol, cost_usd, slippage_est FROM trades
    WHERE entry_time::date='2026-08-06' OR exit_time::date='2026-08-06';
    -- 584 MMM   0.403 | 0.403     667 SPCX  2.402 | 2.402
    -- 650 ABBV  0.359 | 0.359     669 MMM   0.379 | 0.379
    -- 655 SBUX  0.519 | 0.519     668 ABBV  0.364 | (null)
    -- 659 BRK.B 0.524 | 0.524     670 BRK.B 0.355 | (null)
    -- 666 MSFT  0.231 | 0.231     671 MMM   0.355 | (null)
    ```
* **Descrizione:** ricorrenza invariata. `slippage_est` non stima nulla: replica il costo modellato
  (`spread_cost_bps` + `impact_cost_bps`, cioè 5,00 + 0,19 bps per i nomi liquidi e 20,00 + 0,24 per
  SPCX), che è a sua volta un modello a priori e non una misura. Nessuna colonna contiene il mid al
  momento del submit, quindi la differenza fra prezzo atteso e prezzo ottenuto **non è calcolabile
  a posteriori**.
* **Impatto:** su una giornata con 5 round-trip intraday ([DAY-006]) e un BUY nel quartile alto del
  range su entrambi gli ingressi S4 (`entry_percentile` 0,753 e 0,748 contro mediana mobile 0,526),
  la qualità di esecuzione è esattamente la grandezza che servirebbe misurare, e non esiste.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza: persistere il mid (o il last trade) al momento del
  submit e calcolare `slippage_est = (fill − mid_submit) × qty × segno`.
* **Test/monitor consigliato:** test che fallisce se `slippage_est == cost_usd` su una riga con
  `exit_price` valorizzato.

---

### [DAY-009] Quarantacinque minuti di sessione senza ingest né scoring: le finestre beat sono in UTC fisso

* **Tipo:** Bug (ricorrenza di **F-021**)
* **Area:** Ops / News
* **Evidenza:**
  * file: `src/workers/celery_app.py` (`crontab(hour="14-21")`)
  * timestamp: 13:30:00 → 14:15:07 UTC
  * query:
    ```sql
    SELECT min(created_at), max(created_at) FROM news_log WHERE created_at::date='2026-08-06';
    -- 2026-08-06 14:15:07  |  2026-08-06 19:46:00
    SELECT min(timestamp) FROM portfolio_cycles WHERE timestamp::date='2026-08-06';
    -- 2026-08-06 14:07:00        (apertura NYSE: 13:30 UTC)
    ```
* **Descrizione:** gli USA sono in EDT, la sessione è 13:30–20:00 UTC, ma il beat è cablato su
  14:00–21:00 UTC (orario EST). Ogni giorno di ora legale la pipeline **perde i primi 37–45 minuti
  di sessione** — la finestra in cui si concentra la reazione alle news pre-market — e spreca otto
  cicli dopo la chiusura. Sul 2026-08-06 la prima riga di news è delle 14:15 e il primo ciclo di
  portafoglio delle 14:07.
* **Impatto:** non stimabile in dollari sul singolo giorno, perché per definizione non sappiamo cosa
  ci fosse nella finestra non osservata. Struttrualmente rilevante per la domanda di uscita n.1: i
  40 giorni misureranno la news editoriale **al netto dei primi 45 minuti di ogni sessione**, che è
  proprio dove la letteratura colloca la reazione più forte.
* **Severità:** Medium
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza: agganciare le finestre beat al calendario Alpaca
  (`GetCalendarRequest`, già usato da `scripts/daily_alpha_miss_analysis.sh`) invece che a un'ora
  UTC fissa.
* **Test/monitor consigliato:** check giornaliero che confronta l'ora del primo ciclo con l'apertura
  di mercato del calendario e allerta se il ritardo supera 5 minuti.

---

### [DAY-010] Il `risk_report` di chiusura emette un ALERT su un drawdown del 13,9 % che non corrisponde a nulla

* **Tipo:** Bug (ricorrenza di **F-003**, con un secondo numero incoerente)
* **Area:** Risk
* **Evidenza:**
  * tabella: `risk_reports`
  * timestamp: `2026-08-06 22:30:00.960042+00`
  * query:
    ```sql
    SELECT nav, combined_drawdown, alerts, per_strategy_metrics->'portfolio'
    FROM risk_reports WHERE timestamp::date='2026-08-06';
    -- nav 110091.43 | combined_drawdown 0.012429
    -- alerts: [{"level":"ALERT","message":"Strategy portfolio drawdown 13.9% exceeds 10%"}]
    -- portfolio: {"drawdown":0.1387,"daily_pnl":-800.43,"sharpe":-4.806,"volatility":0.1905}
    ```
* **Descrizione:** tre grandezze che dovrebbero descrivere lo stesso portafoglio ne descrivono tre
  diversi. `combined_drawdown` = **1,24 %**; `per_strategy_metrics.portfolio.drawdown` = **13,87 %**
  ed è quello che fa scattare l'ALERT; il drawdown reale misurato dallo snapshot delle 20:00 è
  **0,52 %**. In più `daily_pnl` = **−800,43 $** contro un realizzato di −46,26 $ e una variazione
  di NAV di −187,77 $. Nessuno dei due numeri anomali è riconducibile a una grandezza osservabile
  del giorno.
* **Impatto:** il report di rischio produce un ALERT giornaliero su una soglia (10 %) violata da un
  numero che non misura il rischio reale. Un ALERT che scatta sempre e per il motivo sbagliato è
  peggio di nessun ALERT: quando il drawdown vero supererà il 5 %, nessuno lo distinguerà dal rumore
  di fondo. Il kill-switch reale legge un'altra grandezza, quindi il libro non è a rischio; è la
  sorveglianza a esserlo.
* **Severità:** Medium
* **Confidenza:** High per l'incoerenza; Low sulla causa (i log del job non esistono più).
* **Azione consigliata:** ticket di correttezza: far leggere all'ALERT la stessa serie di equity
  usata dal kill-switch, e riconciliare `daily_pnl` con la somma dei `net_pnl` del giorno.
* **Test/monitor consigliato:** invariante — `|combined_drawdown − per_strategy_metrics.portfolio.drawdown| < 0,005`,
  e `|daily_pnl − Σ net_pnl del giorno| < 1 $`.

---

### [DAY-011] `decay_monitor` confronta le stesse metriche globali contro tre baseline diverse, S2 inclusa

* **Tipo:** Bug (ricorrenza di **F-004**)
* **Area:** Ops
* **Evidenza:**
  * tabella: `decay_reports`
  * timestamp: `2026-08-06 21:00:00`
  * query:
    ```sql
    SELECT strategy_id, metric, baseline_value, round(actual_value,4), alert_level
    FROM decay_reports WHERE timestamp::date='2026-08-06' ORDER BY 2,1;
    -- S1/S2/S4 hit_rate      0.54/0.56/0.52  →  0.3982 (identico)
    -- S1/S2/S4 ic            0.035/0.042/0.028 → 0.0043 (identico)  CRITICAL ×3
    -- S1/S2/S4 max_drawdown  0.08/0.06/0.10  →  0.1071 (identico)
    -- S1/S2/S4 sharpe        0.95/1.10/0.80  → -6.2973 (identico)  CRITICAL ×3
    ```
* **Descrizione:** ricorrenza invariata. `actual_value` è identico su tutte e tre le strategie:
  sono metriche **pipeline-globali**, non per-strategia, confrontate contro tre baseline distinte.
  **S2 non ha mai tradato**, e riceve comunque due CRITICAL e un WARNING.
* **Impatto:** quattro allarmi CRITICAL al giorno che non discriminano fra strategie. Nella finestra
  di osservazione questo è il monitor che dovrebbe segnalare il decadimento di S1 o S4 separatamente
  — la domanda di uscita n.2 è esattamente su S1 — e non è in grado di farlo.
* **Severità:** Low (nessun effetto sul trading) / Medium come strumento di misura
* **Confidenza:** High
* **Azione consigliata:** ticket di correttezza: calcolare le metriche filtrando per
  `trades.stop_strategy`, ed escludere le strategie senza trade dal report invece di valutarle.
* **Test/monitor consigliato:** test che fallisce se due strategie con trade diversi producono lo
  stesso `actual_value`.

---

## 11. False positive e aree risultate corrette

| Area | Esito | Evidenza |
|---|---|---|
| **Ingest** | **corretto** | 2.473 articoli, 2 fonti, nessun buco fra 14:15 e 20:00, 0 timestamp futuri, 0 `parse_fail`, dedup per `(url,ticker)` attivo |
| **Idempotenza Celery** | **corretta** | 6 `SIGNAL_DUPLICATE_SKIP`; nessun doppio ordine sullo stesso `signal_id` |
| **Guard anti-pyramiding P0-05** | **funziona** (ma cieco) | ha bloccato TSM; vedi [DAY-005] per il difetto di tracciabilità, non di comportamento |
| **Guard hold-minimum 90 min** | **funziona** | SELL su SPCX bloccata alle 15:07, 30 min dopo l'acquisto; MMM venduta a 105 min |
| **Riconciliazione ordini→fill→posizioni** | **completa** | 13 ordini, 13 fill, 6 aperture + 7 chiusure, 0 orfani in entrambe le direzioni |
| **Rilevazione di regime** | **corretta** | 13:30:38, `sideways ×0,7`, `disagreement=False`, dati macro completi; `regime_mult=0,7` su **tutte** le 705 decisioni. Nessuna ricorrenza di F-017 |
| **Circuit breaker / risk limit** | **correttamente inattivi** | gross 28,77 % su 50 %, drawdown 0,52 % su 5 %, nessuna chiave `halt` |
| **Paper/live** | **coerente** | `system:mode=paper`, `source=alpaca_paper`, nessun ordine su conto live |
| **FinBERT / Ollama** | **nessun problema** | 0 fallback FinBERT, `consecutive_fallback=0`, Ollama up per l'intera sessione |
| **Latenza di ingestione (F-019)** | **non ricorre oggi** | mediana 30,4/44,6 min contro l'1h50 che aveva motivato il finding: oggi consuma il 25-37 % della finestra di freschezza, non il 92 % |
| **Esclusione dei segnali single-model** | **comportamento di design** | 47/163 (28,8 %) esclusi da BUY e force-SELL per #108; include SPCX +0,560 delle 16:45. Non è un bug: è la scelta presa dopo la perdita SPCX del 2026-07-01. Il difetto **derivato** — che il testo della decisione non li veda e attribuisca la causa sbagliata — è già registrato oggi su F-006 dall'alpha-miss |
| **Snapshot di monitoraggio** | **completi** | 82 punti fra 13:30:01 e 20:00:00, NAV coerente col dossier |

### Già registrate oggi dal ciclo alpha-miss — confermate, non ri-conteggiate

Le seguenti sono state verificate indipendentemente da questa sessione e **coincidono**; le loro
occorrenze del 2026-08-06 sono già nel ledger con il loro costo, e non ne aggiungo di nuove:

| Finding | Conferma indipendente di questa sessione |
|---|---|
| **F-001** copertura news bassa | 40/96 simboli senza righe; TMUS +3,75 % senza alcuna catena decisionale |
| **F-006** causa dell'uscita non ricostruibile | SPCX: 3 segnali fra le 14:30 e le 18:52 invisibili al testo della decisione |
| **F-009** gate S4 sopra il baseline | 244 `SKIP_THRESHOLD` a 0,350 + 446 a 0,400; salita **in sessione** alle 16:37 e di nuovo a 0,450 alle 20:30 |
| **F-011** `signal_id` NULL | 703/705 decisioni senza `signal_id`; solo i 2 BUY S4 lo hanno |
| **F-012** fan-out multi-ticker | 77/163 segnali (47,2 %) da articoli multi-ticker; entrambi i BUY del giorno |
| **F-013** churn e SELL su sentiment positivo | MSFT venduta con score **+0,012** dopo 1h45 |
| **F-014** telemetria del ciclo | log hold-minimum che dichiara 1 ed elenca 3 (vedi anche [DAY-007]) |
| **F-020** ticker resolution bancaria | 40/162 righe (24,7 %) su MS e GS, **nessuna** su quelle due società |
| **F-023** segnale forte sovrascritto | MSFT +0,508 → +0,012 a 45 min (vedi anche TSM in [DAY-005]) |
| **F-024** `max_signal_age` in tempo di parete | SPCX chiusa `expired` a 4,4 h lasciando +51,77 $ |
| **F-025** nessun orizzonte di uscita per le posizioni tiepide | WDC aperta dal 21/07, −201,67 $ di MTM in un giorno |

---

## 12. Dati mancanti o non accessibili

| Fonte | Stato | Impatto sull'analisi | Rimedio |
|---|---|---|---|
| **Log dei container (worker, beat, api, inference) del 2026-08-06** | **distrutti** dal redeploy delle 11:08 del 08-07 | **alto** — latenza/timeout LLM, sync degli stop, conteggio degli scarti del gate, consegna degli alert e ogni eccezione non persistita sono inanalizzabili | [DAY-002]: logging persistente su volume |
| **API REST locale (`localhost:8001`)** | **non accessibile** — tutti e 5 gli endpoint rispondono `{"detail":"Invalid or expired JWT token"}` | **nullo** — ogni grandezza è stata ricavata da Postgres, Redis e dal dossier deterministico | rigenerare il token. **Terza giornata consecutiva** |
| **Latenza per chiamata LLM** | non persistita | medio — non si distingue un modello lento da uno che non risponde | aggiungere `latency_ms` a `llm_responses` |
| **Richieste LLM fallite** | non persistite | medio — `llm_responses` registra solo i successi; i 6 mancati `gpt-oss` sono inferiti dal conteggio | contatore di timeout/refusal per modello |
| **`stop_decisions` per il 2026-08-06** | **0 righe** | medio — la copertura degli stop protettivi (F-022) non è verificabile | capire se è atteso (una sola posizione S4 aperta) o se il job non ha scritto |
| **Mid al submit** | inesistente | medio — slippage non calcolabile ([DAY-008]) | vedi [DAY-008] |
| **Consegna degli alert Telegram** | non verificabile | basso — `mobile_events` è vuoto per il giorno, i log non ci sono | F-005 resta in sospeso |
| **Verifica indipendente di `duplicates`** | **impossibile** | basso — F-007 resta non verificabile | i duplicati non lasciano riga |

---

## 13. Raccomandazioni immediate

Tutte di sola **correttezza o osservabilità**: nessuna tocca soglie, pesi, flag o parametri di
strategia, coerentemente con la carta di osservazione.

1. **Scrivere il ledger prima del report** nel cron forense, e far fallire lo script se il commit
   non avviene ([DAY-001]). È la raccomandazione con la priorità più alta: senza di essa ogni altro
   lavoro di questa finestra può evaporare in silenzio.
2. **Riconciliare gli id `F-025..F-028`** citati nel report del 08-05 con il ledger reale, e creare
   i quattro findings mancanti (fatto in parte oggi, vedi §15).
3. **Logging persistente sui quattro container** ([DAY-002]) — altrimenti i deploy attesi di #185 e
   #191 cancelleranno altre giornate.
4. **Isolare `DATABASE_URL` nei test** ([DAY-003]) — la suite sta scrivendo in produzione più spesso
   di ieri, non meno.
5. **Persistere una riga `SKIP_PYRAMIDING`** prima del `continue` di P0-05 ([DAY-005]).
6. **Verificare lo stato di deploy di #185**: la deroga è registrata nella carta dal 08-06 ma il
   codice non è in `main`, e S1 continua a ribilanciare ogni 15 minuti ([DAY-006]).

## 14. Test o monitor da aggiungere

| # | Monitor | Difende da |
|---|---|---|
| M-1 | Check giornaliero: esiste un commit `evidence: forensic <data>` per ogni giorno di borsa della finestra? | [DAY-001] |
| M-2 | Preflight del cron forense: i log del container coprono il giorno target? Se no, dichiararlo in testa al report | [DAY-002] |
| M-3 | Fixture autouse che asserisce l'assenza di connessioni al DB live durante `pytest` | [DAY-003] |
| M-4 | Invariante: ogni segnale sopra la soglia effettiva ha ≥ 1 riga in `execution_decisions` nel ciclo successivo | [DAY-005] |
| M-5 | Contatore giornaliero di round-trip intraday per strategia, con soglia di allerta | [DAY-006] |
| M-6 | Invariante: `entry_notional / nav` entro il 5 % del peso dichiarato nel `reason` | [DAY-007] |
| M-7 | Test: `slippage_est != cost_usd` su ogni riga con `exit_price` valorizzato | [DAY-008] |
| M-8 | Check: ritardo del primo ciclo rispetto all'apertura del calendario Alpaca < 5 min | [DAY-009] |
| M-9 | Invarianti sul `risk_report`: drawdown coerenti fra loro, `daily_pnl` = Σ `net_pnl` | [DAY-010] |
| M-10 | Test: due strategie con trade diversi non possono avere lo stesso `actual_value` in `decay_reports` | [DAY-011] |

## 15. Ticket tecnici suggeriti

| Ticket | Descrizione | Severità | Finding |
|---|---|---|---|
| **TCK-A** | Il cron forense deve committare il ledger **prima** di scrivere il report e fallire se il commit non riesce | **High** | **F-026** (nuovo) |
| **TCK-B** | Logging persistente (volume o journald) per worker/beat/api/inference | **High** | **F-027** (nuovo) |
| **TCK-C** | `conftest.py` che rifiuta il `DATABASE_URL` di produzione + mock di `PostgreSQLStore` nei test RSS + pulizia tracciata delle righe `reuters` | **High** | **F-028** (nuovo) |
| **TCK-D** | Rendere esplicito che il ramo S1 del loss-feedback è no-op (`"applied": false`) invece di scrivere numeri che sembrano applicati | **Medium** | **F-029** (nuovo) |
| **TCK-E** | Persistere `SKIP_PYRAMIDING` in `execution_decisions` prima del `continue` di P0-05 | **Medium** | F-023 |
| **TCK-F** | Scrivere nel `reason` il peso post-vincoli e popolare `constraints_fired` con lo scaling applicato | **Medium** | F-014 |
| **TCK-G** | Persistere il mid al submit e calcolare uno slippage vero | **Medium** | F-015 |
| **TCK-H** | Agganciare le finestre beat al calendario Alpaca (DST) | **Medium** | F-021 |
| **TCK-I** | Riconciliare `combined_drawdown`, `portfolio.drawdown` e `daily_pnl` nel `risk_report` | **Medium** | F-003 |
| **TCK-J** | `decay_monitor` per-strategia, escludendo le strategie senza trade | **Low** | F-004 |
| — | *(già aperti nelle giornate precedenti)* benchmark SPY, token Telegram, `signal_id` NULL, gate S4 (#191), rebalance S1 (#185) | — | F-016, F-018, F-011, F-009 |

## 16. Stato sistema

| Grandezza | Valore |
|---|---|
| **Ollama** | **up** per l'intera sessione. 320 risposte (163 glm-5.2, 157 gpt-oss), 0 finestre di indisponibilità rilevabili. **Downtime: 0 h** |
| **FinBERT fallback** | **0 %** delle decisioni. Zero segnali con `model_id` FinBERT; `fallback_counters.consecutive_fallback = 0`, azzerato alle 19:46 |
| **Fallback single-model** | **28,8 %** dei segnali (47/163): 39 `single:gpt-oss`, 8 `single:glm-5.2`. Non è FinBERT ed è escluso dal trading per design (#108) |
| **Worker restart** | **nessuno durante il 2026-08-06**. I quattro container sono stati **ricreati** il 2026-08-07 alle 11:08 (deploy PR #194), distruggendo i log del giorno analizzato ([DAY-002]) |
| **Beat** | 24 cicli di portafoglio su 24 attesi (14:07 → 19:52), nessun ciclo saltato |
| **Postgres / Redis** | up da 2 settimane, nessuna interruzione |
| **Modalità** | `paper` — `system:mode=paper`, S1 `supervised_paper`, S4 `paper`, nessuna strategia approvata per il live |
| **Regime** | `sideways ×0,7`, rilevato 13:30:38, `disagreement=False`, VIX 16,5 |
| **Soglia d'ingresso S4** | 0,350 (14:07–16:22) → 0,400 (16:37–20:00) → 0,450 (20:30), TTL 3,4 giorni |
| **Soglia d'ingresso S1** | 0,000 dalle 14:00 (ramo inerte, [DAY-004]) |
| **Alert emessi** | 1 `ALERT` nel `risk_report` delle 22:30, su un numero incoerente ([DAY-010]); 4 `CRITICAL` da `decay_monitor` non discriminanti ([DAY-011]); consegna non verificabile |
