# Forensic Daily Report — 2026-08-10 (lunedì)

**Generato:** 2026-08-11 ~12:30 UTC · **Analista:** sessione forense automatica
**Perimetro:** news ingest → dedup → scoring LLM → segnali → decisioni → ordini → fill → posizioni → P&L
**Modalità:** read-only. Nessun ordine, nessun worker avviato, nessuna patch.
**Timezone:** UTC — `src/workers/celery_app.py:51-52` fissa `timezone="UTC"`, `enable_utc=True`.
Nessuna ambiguità: tutti i timestamp di questo report sono UTC. Sessione EDT = 13:30–20:00 UTC.
**Ambiente:** `paper` / `alpaca_paper` (`portfolio_monitor_snapshots.mode`), `execution.engine=portfolio`
(`config/trading.yaml:142`) — solo `portfolio-cycle` invia ordini.

**Nota di coordinamento.** Il ciclo alpha-miss ha già analizzato questa giornata alle 08:00 UTC del
2026-08-11 (`docs/ALPHA_MISS_REPORT_2026-08-10.md`) e ha già scritto nel ledger le occorrenze
**F-001, F-002, F-008, F-010, F-011, F-012, F-020, F-021, F-027, F-030, F-031, F-032**. Questo report
non le ri-quantifica: dove le tocca lo fa per completezza narrativa, e le occorrenze che aggiunge al
ledger portano `costo_usd: null` con nota esplicita di non-doppio-conteggio, secondo la convenzione
già in uso. I contributi **nuovi** di questa run sono [DAY-003], [DAY-004] e [DAY-007].

---

## 1. Executive summary

Giornata funzionalmente pulita sul piano meccanico e povera sul piano dell'alpha. 196 articoli
scorati da 131 URL distinti, ensemble completo (entrambi i modelli hanno risposto su **tutti** i 196
segnali: zero timeout, zero FinBERT, Ollama Cloud su del 100%). 463 decisioni, di cui 4 BUY e 4 SELL,
tutte eseguite e riconciliate: 8 ordini generati, 8 inviati, 8 fill, 4 trade aperti, 4 chiusi, nessun
duplicato, nessun ordine fuori orario, nessun ordine senza segnale, 48 posizioni a libro sia sul
broker sia in DB. Il P&L realizzato del giorno è **−2,76 $** (S1 +1,89, S4 −4,65) su un NAV che chiude
a 110.344,06 $, **+162,43 $ (+0,15%)** contro SPY −0,03%. Le due macchine anti-churn nuove hanno
funzionato: `#185` tiene S1 fermo dal ribilanciamento del 07-08 (zero `portfolio_sell` S1 dal 08-07) e
`#184` scrive `exit_mechanism` osservato, non dedotto dall'orologio.

Il fatto della giornata è che **tre posizioni S4 aperte fra le 17:22 e le 17:52 su segnali
ticker-specifici forti (+0,441 / +0,515 / +0,470) sono state chiuse 1h45 dopo da un unico
morning-brief macro generico** che ha prodotto tre segnali a 0,000 con confidenza 0,05–0,175. Il
controfattuale è già misurato dall'alpha-miss ed è **sfavorevole al mantenimento** (−2,46 $): il
difetto esiste, oggi ha fatto guadagnare. Sotto restano tre difetti di **misura**, non di esecuzione:
`sentiment_reversal` chiude posizioni di qualunque strategia e ne attribuisce il P&L alla sleeve
sbagliata; 25 dei 96 simboli di watchlist cadono nel tier di costo di default a 20 bps; e i tre
report di controllo del giorno (`risk_reports`, `decay_reports`, `portfolio_cycles.orders_count`)
contengono numeri che non corrispondono a nulla di reale.

## 2. Verdict

> **OK con warning.**

Il processo end-to-end ha funzionato: nessun ordine errato, nessuna posizione non riconciliata,
nessun trade su dati stale, nessuna allucinazione LLM arrivata a un ordine. I warning riguardano
**la strumentazione di misura** (P&L attribuito, modello costi, report di rischio e decadimento) e
**la logica di uscita S4**, che non ha banda di isteresi. Nessuna anomalia richiede intervento sul
path d'ordine.

Non è "OK" pieno per un motivo preciso: siamo dentro la finestra di osservazione (#171) e le
soglie di uscita sono espresse in dollari; tre dei difetti trovati oggi **sporcano proprio i numeri
che decideranno il 28/09**.

---

## 3. Timeline del 2026-08-10 (UTC)

| ora | componente | evento | evidenza | finding |
|---|---|---|---|---|
| 04:00:05 | ensemble | LOO ICIR: auto-apply **bloccato**, `IC variance = 0.188 ≥ 0.15`. Pesi invariati (glm 0,601 / gptoss 0,399). ICIR gptoss **negativo** (−0,084) | `weight_update_log` id 15 | — (guardrail corretto) |
| 13:30:01 | mobile | incidente **CRITICAL** "Ciclo di portafoglio in ritardo" + WARNING "Segnali sentiment in ritardo", entrambi `recovered` | `mobile_events` | [DAY-006] |
| 13:30–14:00 | beat | apertura EDT: **nessun ingest, nessuno scoring, nessun ciclo** — il beat parte da `hour="14-21"` | `celery_app.py:78,201` | [DAY-006] |
| 14:01:34 | LLM | primo scoring del giorno | `llm_responses` min | — |
| 14:07:00 | portfolio | **primo ciclo**, 37 min dopo l'apertura | `portfolio_cycles` | [DAY-006] |
| 14:52→15:52 | portfolio | 5 cicli consecutivi con `orders_count = 0` | `portfolio_cycles` | — |
| 15:00:53→15:30:09 | LLM | unico buco > 20 min nella produzione segnali (29,3 min) | `sentiment_signals` | [DAY-013] |
| 15:24:00 | mobile | WARNING "Segnali sentiment in ritardo", `recovered` | `mobile_events` | [DAY-013] |
| 16:00:45 | LLM | SONY **+0,451** conf 0,765 (ensemble) da *"Nvidia Built the AI Brain, Now TSMC Wants to Give It Eyes"* | `sentiment_signals` 7046 | — |
| **16:07:00** | ordini | **BUY SONY** 50,281 az. @ 23,77 = 1.195,19 $ · order `75e91abe` · `signal_id` **NULL**, reason cita score **+0,541** che non esiste in DB | `execution_decisions` 8544, `trades` 695 | [DAY-010] |
| 16:16:15 | LLM | INTC **−0,553** conf 0,850 (ensemble) — collocamento azionario 15 mld | `sentiment_signals` 7063 | — |
| **16:22:00** | ordini | **SELL INTC** @ 98,274 dopo 598 h di tenuta · `sentiment_reversal: −0,553 < −0,35` · net **+1,89 $** · trade taggato **S1** | `trades` 356 | [DAY-003] |
| 17:15:37 | LLM | NVDA **+0,441** conf 0,700 (*"Rubin Era Begins: a Top Pick, BofA"*) | 7098 | — |
| **17:22:00** | ordini | **BUY NVDA** 5,462 az. @ 218,89 = 1.195,55 $ | 8657 / trade 696 | — |
| 17:31:09 | LLM | META **+0,515** conf 0,775 (*"What's Going On With Meta Platforms Stock Monday?"*) | 7109 | — |
| **17:37:00** | ordini | **BUY META** 2,010 az. @ 594,69 = 1.195,50 $ | 8680 / trade 697 | — |
| 17:45:42 | LLM | MSFT **+0,470** conf 0,750 (*"Maia 300 Chip Launch"*) | 7116 | — |
| 17:45:46 | LLM | **NVDA −0,121** dallo *stesso* articolo Maia 300 (fan-out): il pezzo che compra MSFT vende NVDA | 7117 | [DAY-011] |
| **17:52:00** | ordini | **BUY MSFT** 2,364 az. @ 505,87 = 1.195,73 $ | 8703 / trade 698 | — |
| 19:00:40–53 | LLM | un solo articolo — *"S&P 500 Earnings Growth May Be Less Impressive Than It Looks; SpaceX Short Squeeze; Inflation Data Ahead"* — genera **META 0,000 (conf 0,175)**, **MSFT 0,000 (conf 0,050)**, **NVDA 0,000 (conf 0,150)** | 7149/7150/7151 | [DAY-001] |
| **19:07:00** | ordini | **SELL NVDA** @ 219,17 · `[below_entry_gate]` · tenuta 1h45 · net **+1,29 $** | 8789 | [DAY-001][DAY-002] |
| **19:22:00** | ordini | **SELL META** @ 593,03 · `[below_entry_gate]` · tenuta 1h45 · net **−3,57 $** | 8806 | [DAY-001][DAY-002] |
| **19:37:00** | ordini | **SELL MSFT** @ 504,97 · `[below_entry_gate]` · tenuta 1h45 · net **−2,37 $** | 8824 | [DAY-001][DAY-002] |
| 19:45–19:46 | LLM | ultimo scoring (INTC −0,444, NVDA +0,013) | 7174/7180 | — |
| 19:52:00 | portfolio | **ultimo ciclo** (24° del giorno); chiusura mercato alle 20:00 | `portfolio_cycles` | [DAY-006] |
| 20:00:00 | monitor | NAV 110.344,22 · +162,59 · 48 posizioni · unrealized +1.189,73 | `portfolio_monitor_snapshots` | — |
| 21:00:00 | decay | `sharpe` **CRITICAL** per S1, S2 e S4 con **valore identico** (−6,4151) su tre baseline diverse | `decay_reports` | [DAY-005] |
| 22:05:37 | ingest | riga `ingestion_stats_daily` `source='reuters'` fetched=12 — **nessun connettore RSS nel beat, 0 righe in `news_log`** | `ingestion_stats_daily` | [DAY-009] |
| 22:30:01 | risk | unico `risk_reports`: ALERT "portfolio drawdown 14,3% > 10%", `combined_drawdown` 1,24%, `daily_pnl` **−77,15** in una giornata chiusa a **+162,43** | `risk_reports` | [DAY-004] |
| 23:41:09 | mobile | CRITICAL "Dati broker non aggiornati" + "Degradazione market_clock", entrambi `recovered` | `mobile_events` | — |
| 23:42:00 | monitor | ultimo snapshot: NAV 110.344,06 · drawdown 0,25% · 48 posizioni | — | — |

---

## 4. News ingest

### 4.1 Per fonte

| fonte | fetched | queued | duplicates | scartate no-ticker | righe in `news_log` | latenza mediana pub→fetch |
|---|---|---|---|---|---|---|
| `alpaca_benzinga` | 844 | 347 | **3.122 (3,7×)** | 0 | 85 | 75,2 min (range 17,4–120,7) |
| `gdelt_gkg` | 2.061 | 158 | 121 | 1.810 | 111 | 75,5 min (range 60,1–107,0) |
| `reuters` | 12 | 12 | 0 | 3 | **0** | — |
| **totale utile** | 2.905 | 505 | 3.243 | 1.810 | **196** | **~75 min** |

Scarti a valle della coda: `news_queue_drops` registra **253 articoli** scartati per età
(211 benzinga, età media 32,2 h; 42 gdelt, 53,4 h). Nessun `parse_fail`, nessuna `discarded_stale`.

**Igiene dei dati: pulita.** Zero timestamp futuri (`published_at > fetched_at`), zero
`published_at` nulli, zero `discarded_reason` valorizzati, zero buchi > 16 min nella cadenza di
ingest. Copertura oraria continua 14:00 → 19:46.

Problemi: (a) `duplicates` (3.122) supera `fetched` (844) di 3,7× — contatore additivo cross-run,
[DAY-008]; (b) la riga `reuters` non ha alcuna controparte in `news_log` né alcun task RSS nel
beat, [DAY-009]; (c) 131 URL distinti producono 196 righe → 65 righe sono fan-out multi-ticker,
[DAY-011]; (d) latenza mediana 75 min contro una finestra di entry-freshness di 30 min, [DAY-012].

### 4.2 Per ticker (top 15 su 54 coperti)

| ticker | righe | nota |
|---|---|---|
| **MS** | 33 | nessuna riguarda Morgan Stanley — `org_lookup` sul boilerplate della casa d'analisi, [DAY-011] |
| **GS** | 15 | idem |
| TSM | 13 | copertura genuina (JV Sony, espansione 64 mld) |
| **DB** | 11 | idem MS/GS |
| **BRKB** | 11 | forma non canonica del simbolo → **zero decisioni**, F-032 (già corretto il 08-11) |
| AMZN / NVDA | 6 | — |
| AMAT / MSFT / SONY | 5 | — |
| GOOGL / INTC / MU / AMD / SPCX | 4 | — |

**53 dei 96 simboli di watchlist hanno almeno una riga; 43 (45%) ne hanno zero** — dentro la
banda 42-57% delle sei sedute precedenti (F-001).

### 4.3 Top news per impatto sul segnale

| articolo | ticker | score | esito |
|---|---|---|---|
| *Sony Pledges $6.3B to Build Sensors with TSMC* / *Nvidia Built the AI Brain…* | SONY, TSM | +0,451 / +0,691 | **BUY SONY**; TSM bloccato dal guard anti-pyramiding (F-031) |
| *Intel plans $15B share sale* (7 versioni, 4 provider) | INTC | −0,553 | **SELL INTC** — miglior decisione del giorno |
| *Rubin Era Begins: a Top Pick, BofA Says* | NVDA | +0,441 | **BUY NVDA**, chiuso 1h45 dopo |
| *What's Going On With Meta Platforms Stock Monday?* | META | +0,515 | **BUY META**, chiuso 1h45 dopo |
| *Microsoft Stock Rises 2%: Maia 300 Chip Launch* | MSFT / **NVDA** | +0,470 / **−0,121** | **BUY MSFT** e contemporaneo affossamento del segnale NVDA |
| *S&P 500 Earnings Growth May Be Less Impressive…* | META, MSFT, NVDA (+3) | **0,000** ×3 | **3 SELL**, [DAY-001] |

**Confidenza dell'analisi ingest: Alta** — `news_log`, `ingestion_stats_daily` e `news_queue_drops`
sono concordi e completi. L'unico punto cieco è il conteggio `duplicates`, non verificabile
indipendentemente.

---

## 5. Performance modelli LLM

### 5.1 Disponibilità e volumi

| metrica | glm-5.2:cloud | gpt-oss:20b-cloud |
|---|---|---|
| richieste (= segnali scorati) | 196 | 196 |
| risposte ottenute | **196 (100%)** | **196 (100%)** |
| timeout / errori / refusal / output invalido | **0** | **0** |
| `eligible = true` | 47 (24%) | 47 (24%) |
| polarity media | +0,091 | +0,084 |
| deviazione std polarity | 0,240 | 0,223 |
| confidence media | 0,293 | **0,411** |
| finestra | 14:01:34 → 19:46:41 | idem |

**Ollama Cloud: up 100% della sessione, 0 h di downtime.** `fallback_counters.consecutive_fallback = 0`
(ultimo incremento 2026-08-05, reset alle 19:46:41 del 08-10). **FinBERT: 0 invocazioni** — nessun
segnale porta `model_id` FinBERT. Latenza per-chiamata non misurabile: `llm_responses` non ha un
campo di durata e i log del giorno non esistono più ([DAY-014]).

Costo: **0,2307 $** (115.374 token in, 15.129 out), `budget_exhausted = false`.

### 5.2 Composizione dei segnali

| tag | n | % |
|---|---|---|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 144 | 73,5% |
| `single:gpt-oss:20b-cloud` (`fallback_used=true`) | 49 | 25,0% |
| `single:glm-5.2:cloud` (`fallback_used=true`) | 3 | 1,5% |

**`fallback_used = true` non significa FinBERT e non significa che un modello sia caduto**: entrambi
i modelli hanno risposto su tutti e 196 i segnali. Il tag `single:` nasce dal filtro di eligibilità,
non da un guasto — e a valle il filtro #108 li scarta *come se* fossero FinBERT. [DAY-014].

### 5.3 Dispersione ensemble

| `ensemble_std` | segnali |
|---|---|
| 0,00 | 125 (64%) |
| 0,01–0,10 | 30 |
| 0,11–0,20 | 24 |
| 0,21–0,30 | 13 |
| > 0,30 | 4 (max 0,39) |

Il disaccordo forte è raro (4 casi su 196). Nessuno dei quattro ha generato un ordine.

### 5.4 Verifica funzionale

| domanda | risposta | evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Sì (parziale)** — parsing JSON strutturato, `polarity`/`confidence` tipizzate, ma `eligible` è incoerente ([DAY-014]) | `llm_responses` |
| L'ensemble gestisce la varianza alta? | **Sì** — `ensemble_std` persistito; a livello di pesi il LOO ICIR ha **congelato** l'aggiornamento con `IC variance 0.188 ≥ 0.15` | `weight_update_log` 15 |
| Le news duplicate pesano più volte? | **Sì, per costruzione** — 131 URL → 196 righe; un articolo può produrre fino a 6 segnali | [DAY-011] |
| La stessa news può generare segnali multipli? | **Sì**, uno per ticker estratto | [DAY-011] |
| Confidence bassa riduce il peso? | **No sulla soglia d'ingresso** — il gate confronta `abs(score)` con 0,300, e `score` non è pesato per confidenza a valle. I tre segnali che hanno chiuso le posizioni avevano conf 0,05–0,175 e hanno avuto pieno effetto | `portfolio_scheduler.py:3717` |
| I modelli sono chiamati offline/background? | **Sì** — worker Celery `inference`, mai dentro il ciclo d'ordine. Il ciclo legge `sentiment_signals`/Redis | `celery_app.py` |
| Un'allucinazione LLM può entrare direttamente in decisione? | **Sì in linea di principio**, mitigata dall'ensemble e dal gate 0,300; nessun supervisore incrociato. Oggi non è successo | — |

---

## 6. Segnali finali per ticker

196 segnali su 54 simboli. Sopra o vicino al gate `feedback:entry_threshold:S4 = 0,300`
(TTL 291.514 s, valore ripristinato con la deroga #191):

| simbolo | segnali | score max | conf media | esito | motivo |
|---|---|---|---|---|---|
| **TSM** | 13 | **+0,691** | 0,59 | nessuna decisione | guard anti-pyramiding, già a libro (F-031) |
| **CAT** | 3 | +0,520 | 0,58 | 17× `SKIP_THRESHOLD` | idem |
| **XLE** | 2 | +0,516 | 0,50 | 16× `SKIP_THRESHOLD` | idem — **mover #2 del giorno (+4,66%)** |
| **META** | 3 | +0,515 | 0,52 | **BUY 17:37 → SELL 19:22** | [DAY-001] |
| **SHEL** | 1 | +0,482 | 0,73 | **nessuna riga** | F-031 |
| **BRKB** | 11 | +0,480 | 0,45 | **nessuna riga** | forma non canonica (F-032) |
| **MSFT** | 5 | +0,470 | 0,45 | **BUY 17:52 → SELL 19:37** | [DAY-001] |
| **SONY** | 5 | +0,451 | 0,56 | **BUY 16:07**, tuttora aperta | ok |
| **NVDA** | 6 | +0,441 | 0,43 | **BUY 17:22 → SELL 19:07** | [DAY-001] |
| MRVL | 1 | +0,423 | 0,65 | nessuna | già a libro S1 |
| **GE** | 1 | +0,345 | 0,68 | **nessuna riga** | F-031 |
| **PANW** | 3 | +0,327 | 0,46 | 8× `SKIP_THRESHOLD` | **mover #1 (+5,82%)**, già a libro S1 |
| MU | 4 | +0,300 | 0,35 | 17× `SKIP_THRESHOLD` | esattamente al gate |
| **INTC** | 4 | **−0,553** | 0,74 | **SELL 16:22** | `sentiment_reversal` ✓ |

Ripartizione decisioni: **454 `SKIP_THRESHOLD`, 4 BUY, 4 SELL, 1 `SKIP_STALE`** (463 righe).
`audit_log`: 263 `SIGNAL_STALE_SKIP` (top: C 24, ROKU 24, GM 24, AAPL 20) e 9 `SIGNAL_DUPLICATE_SKIP`.

---

## 7. Ordini generati / eseguiti

Tutti e 8 gli ordini sono **paper** (`alpaca_paper`), generati dall'orchestratore `portfolio-cycle`,
inviati e riempiti. Nessun reject, nessun cancel, nessun parziale non riconciliato.

| # | ora decis. | strat. | ticker | azione | qty | prezzo fill | stato | order_id | segnale causante | risk check | anomalia |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 16:07:00 | S4 | SONY | BUY | 50,281 | 23,77 | filled | `75e91abe` | **NULL** (reason cita +0,541, inesistente) | gate 0,300 ✓, peso 2,0% ✓, cap settore ✓ | [DAY-010] |
| 2 | 16:22:00 | S1 | INTC | SELL | 0,895 | 98,274 | filled | `48815c38` | 7063 (−0,553) | `sentiment_reversal` bypassa hold-min ✓ | [DAY-003] |
| 3 | 17:22:00 | S4 | NVDA | BUY | 5,462 | 218,89 | filled | `9d813042` | 7098 (+0,441) | ✓ | — |
| 4 | 17:37:00 | S4 | META | BUY | 2,010 | 594,69 | filled | `ba598276` | 7109 (+0,515) | ✓ | — |
| 5 | 17:52:00 | S4 | MSFT | BUY | 2,364 | 505,87 | filled | `e012c597` | 7116 (+0,470) | ✓ | — |
| 6 | 19:07:00 | S4 | NVDA | SELL | 5,462 | 219,17 | filled | `181e9233` | 7151 (0,000, conf 0,150) | hold-min 90' ✓, persistence 2 cicli ✓ | [DAY-001][DAY-002] |
| 7 | 19:22:00 | S4 | META | SELL | 2,010 | 593,03 | filled | `ff3df6a7` | 7149 (0,000, conf 0,175) | idem | [DAY-001][DAY-002] |
| 8 | 19:37:00 | S4 | MSFT | SELL | 2,364 | 504,97 | filled | `dd25ca4e` | 7150 (0,000, conf 0,050) | idem | [DAY-001][DAY-002] |

**Prezzo atteso vs fill:** non ricostruibile — il sistema non persiste un prezzo di riferimento
pre-invio, e `slippage_est` è una copia di `cost_usd` ([DAY-007]).

**Telemetria del ciclo:** `portfolio_cycles.orders_count` somma **70** sul giorno contro **8** ordini
realmente inviati (rapporto 8,8:1). I cicli 17:22→18:52 dichiarano 5 ordini ciascuno mentre ne
inviano 1, 1, 1, 0, 0, 0, 0. [DAY-008].

---

## 8. P&L / rendimento del 2026-08-10

### 8.1 Libro

| voce | valore | fonte |
|---|---|---|
| NAV apertura (`previous_close_equity`) | 110.181,63 $ | snapshot 20:00 |
| NAV chiusura | **110.344,06 $** | snapshot 23:42 |
| **variazione giorno** | **+162,43 $ (+0,147%)** | — |
| SPY / QQQ | −0,03% / −0,30% | dossier, Alpaca SIP `adjustment=all` |
| cash | 77.268,64 $ | snapshot |
| gross exposure | 29,97% | snapshot |
| unrealized totale | +1.189,64 $ | snapshot |
| drawdown corrente | 0,25% | snapshot |
| posizioni aperte | 48 (broker) = 48 (DB: 35 S1 + 2 S4 + 11 legacy) | **riconciliato ✓** |

### 8.2 Realizzato

| trade | ticker | strat. | aperta il | net P&L | costo modellato | `exit_reason` | drift post-uscita |
|---|---|---|---|---|---|---|---|
| 356 | INTC | **S1** | 2026-07-16 | **+1,89** | 0,19 | `sentiment_reversal` | −0,67 (uscita ha aggiunto valore) |
| 696 | NVDA | S4 | **08-10 17:22** | **+1,29** | 0,24 | `portfolio_sell` | −8,85 (uscita ha aggiunto valore) |
| 697 | META | S4 | **08-10 17:37** | **−3,57** | 0,24 | `portfolio_sell` | +3,80 (uscita è costata) |
| 698 | MSFT | S4 | **08-10 17:52** | **−2,37** | 0,24 | `portfolio_sell` | +2,59 (uscita è costata) |
| | | | **totale** | **−2,76** | 0,91 | | **−2,46 netto** |

Ripartizione: **S1 +1,89 · S4 −4,65**. Concorda al centesimo con
`docs/evidence/market_daily.jsonl` riga 2026-08-10.

### 8.3 Non realizzato aperto oggi

| ticker | qty | entry | MtM a chiusura |
|---|---|---|---|
| SONY | 50,281 | 23,77 | **+2,51** |

### 8.4 P&L da posizioni preesistenti

Le 47 posizioni antecedenti al 08-10 producono il resto dei +162,43 $, cioè **≈ +162,7 MtM**
(dossier). I cinque mover al rialzo detenuti (PANW, XOM, CVX, XLE, LLY) valgono **+185,85**, erosi
dal blocco semiconduttori.

### 8.5 Slippage e costi

- **Slippage: non misurato.** `trades.slippage_est` è identico a `cost_usd` su tutte le righe
  (0,2368 / 0,2361 / 0,2363). [DAY-007].
- **Commissioni reali: zero** (Alpaca paper, `commission_per_share: 0.0`). Il `cost_usd` è
  interamente **modellato** da `config/cost_model.yaml`.
- **Il modello costi è sbagliato su SONY**: 20,24 bps contro 1,74 bps di NVDA/META/MSFT — SONY non
  è in nessun tier e cade nel default `tier_d` "small-cap illiquid". [DAY-004].

### 8.6 Cosa manca

Il **P&L economico** definito dalla carta di osservazione (§ "Definizione") non è calcolato da
nessun processo automatico su base giornaliera. La query mancante è: per ogni posizione aperta o
chiusa, `(min(prezzo_uscita, prezzo_corrente) − max(close_primo_giorno_finestra, entry_price)) × qty`
sommata su tutto il libro, con i prezzi da Alpaca `adjustment=all`. Oggi esiste solo come
`mtm` nel dossier, che non è la stessa grandezza.

---

## 9. Analisi correttezza buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY generati solo quando consentito | **✓** | 4 BUY, tutte con `abs(score) ≥ 0,300`, ensemble non-fallback, età < 4 h, peso 2,0% |
| SELL/exit generati correttamente | **✓ meccanicamente** | 3 su gate, 1 su reversal; tutte con reason strutturata e `exit_mechanism` **osservato** (#184 deployato) |
| Stop-loss rispettati | **N/A — non esistono** | `config/trading.yaml:183` `stop_loss: 0.0`, decisione paper esplicita del 2026-07-15. `stop_d_init = 0` sui 4 trade è **corretto**, non un bug. `stop_decisions` vuota |
| Signal flip rispettato | **✓** | `sentiment_reversal` su INTC a −0,553 < −0,35, ensemble non-fallback, età < 60 min, consume-on-fire attivo |
| Max holding days rispettato | **⚠ violato in senso lato** | WDC (S4) aperta dal 2026-07-21, **21 giorni** contro `max_signal_age_hours = 4`, tenuta in vita da `preserve-stale` (FIX-D) → [DAY-015] |
| Rebalance band rispettata | **✓** | S1 fermo dal ribilanciamento del 2026-08-07 14:07 (`strategy:rebalance_state:S1`), zero `portfolio_sell` S1 dal 08-07: **#185 funziona** |
| Ordini duplicati | **✓ nessuno** | 8 `order_id` distinti, nessuna coppia stesso simbolo/stesso minuto |
| Ordini contrari ravvicinati senza rationale | **⚠** | 3 BUY→SELL entro 1h45 sullo stesso simbolo — rationale c'è ed è tracciata, ma il meccanismo è il gate d'ingresso usato come uscita → [DAY-002] |
| Ordini su ticker non consentiti | **✓ nessuno** | tutti in watchlist |
| Ordini fuori orario | **✓ nessuno** | primo 16:07, ultimo 19:37, sessione 13:30–20:00 |
| Trade su dati stale | **✓ nessuno** | 1 `SKIP_STALE` + 263 `SIGNAL_STALE_SKIP` correttamente bloccati |
| Trade su output LLM non valido | **✓ nessuno** | 0 errori di parsing |
| Trade con circuit breaker attivo | **✓ N/A** | `system:halted_by_operator` assente, drawdown 0,25% contro trigger 5% |
| Trade su strategia disabilitata | **✓ nessuno** | `strategies_run = ["S1","S4"]` in tutti i 24 cicli |
| Paper/live coerente | **✓** | `mode=paper`, `broker_environment=paper`, `engine=portfolio` |
| Idempotenza su retry Celery | **✓ indiretta** | delta-ordering: se la quantità target è già detenuta, delta ≈ 0 e nessun ordine. Non verificabile direttamente senza log ([DAY-014]) |
| Riconciliazione ordini↔fill↔posizioni | **✓** | 8 ordini → 8 fill → 4 aperture + 4 chiusure; 48 posizioni broker = 48 in DB |

### Pattern operativi richiesti

| pattern | esito |
|---|---|
| Roundtrip < 30 min | **nessuno** — il più corto è 1h45 |
| BUY ripetuto > 3× senza SELL (pyramiding) | **nessuno inviato**. 6 simboli sopra gate (TSM, CAT, XLE, SHEL, GE, PANW) sono stati bloccati dal guard P0-05 senza lasciare riga (F-031) |
| SELL con sentiment positivo | **nessuno** — le 3 SELL sono su score 0,000, non positivo |
| `fallback_used=True` su tutti i simboli | **no** — 26,5%, e non è un fallback vero ([DAY-014]) |
| NO-ORDER (decisione creata, ordine non generato) | **nessuno** — le 8 decisioni BUY/SELL hanno tutte `order_id` valorizzato |
| Score < 0,05 che hanno generato ordini | **3** — le SELL su score 0,000 → [DAY-002] |
| Ordini identici nello stesso minuto | **nessuno** |

---

## 10. Anomalie trovate

### [DAY-001] Un morning-brief macro generico chiude tre posizioni S4 aperte da 1h45

* **Tipo:** Bug
* **Area:** LLM / Signal / Orders
* **Evidenza:**
  * tabella: `sentiment_signals` 7149/7150/7151, `news_log` id 7149-7151, `execution_decisions` 8789/8806/8824, `trades` 696-698
  * timestamp: segnali 2026-08-10 19:00:40 / 19:00:49 / 19:00:53 UTC; SELL 19:07 / 19:22 / 19:37
  * query: `SELECT id,symbol,score,confidence,news_log_id FROM sentiment_signals WHERE id IN (7149,7150,7151);`
* **Descrizione:** l'articolo *"S&P 500 Earnings Growth May Be Less Impressive Than It Looks;
  SpaceX Short Squeeze; Inflation Data Ahead"* — un riepilogo di mercato senza contenuto
  societario — è stato attribuito a 6 ticker e ha prodotto per META, MSFT e NVDA tre segnali a
  `score = 0.000` con confidenza 0,175 / 0,050 / 0,150. Essendo i più **recenti** per quei simboli,
  hanno sostituito i segnali ticker-specifici forti (+0,515 conf 0,775; +0,470 conf 0,750;
  +0,441 conf 0,700) su cui le posizioni erano nate 1h30 prima. Le tre posizioni sono state chiuse
  al primo ciclo utile dopo la scadenza dell'hold-minimum.
* **Impatto:** tre roundtrip da ~1.195 $ ciascuno in 1h45. Controfattuale già misurato
  dall'alpha-miss: tenendo fino alla chiusura NVDA −8,85, META +3,80, MSFT +2,59 = **−2,46 $**,
  cioè le uscite anticipate hanno **fatto risparmiare** denaro. Il difetto è reale, l'esito di
  giornata è favorevole.
* **Severità:** High · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — pesare per confidenza la sostituzione del segnale
  corrente, o non far sostituire un segnale ticker-specifico da uno fan-out con confidenza inferiore.
  **Non una taratura di soglia** (congelata da #171).
* **Test/monitor:** test che un segnale con confidenza < X non possa azzerare il peso di una
  posizione aperta su un segnale con confidenza > Y; monitor giornaliero "posizioni chiuse da un
  articolo taggato a ≥ 3 ticker".
* **Ledger:** F-008 (occorrenza 08-10 già scritta dall'alpha-miss, costo 0,0 verificato)

---

### [DAY-002] Il gate d'ingresso S4 funge anche da gate d'uscita: nessuna banda di isteresi

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Evidenza:**
  * file: `src/workers/portfolio_scheduler.py:3716-3722`
  * snippet: `dropped_df = signals_df[signals_df["score"].abs() < _fb_threshold]` — il filtro è
    applicato all'**intero** `signals_df`, non ai soli candidati nuovi
  * timestamp: SELL 19:07 / 19:22 / 19:37 con reason `[below_entry_gate]`
* **Descrizione:** un simbolo già in posizione il cui ultimo segnale scende sotto `0,300` sparisce
  da `signals_df`, quindi il suo peso target diventa 0 e l'orchestratore genera una SELL. La stessa
  soglia governa entrata e uscita: uno score che passa da +0,441 a +0,299 chiude la posizione.
  `_fresh_signal_protected_symbols` protegge solo i simboli con `score ≥ entry_threshold`, cioè
  esattamente quelli che non hanno bisogno di protezione. `hold_minimum_minutes = 90` e
  `exit_persistence_cycles = 2` **hanno funzionato** (l'uscita è arrivata a 105 min invece che a
  23 min per NVDA) ma sono calibrati sul churn a 15 min, non su questo.
* **Impatto:** tre posizioni su quattro aperte oggi chiuse in meno di due ore. Struttura di churn
  ricorrente: 5 occorrenze in ledger prima di oggi.
* **Severità:** High · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — separare `exit_threshold` da `entry_threshold`
  nel codice, anche lasciando i due valori uguali alla consegna. Oggi la banda **non esiste come
  concetto**, quindi al 28/09 non sarà tarabile.
* **Test/monitor:** test che una posizione con peso > 0 al ciclo N-1 non sia azzerata da uno score
  compreso fra `exit_threshold` e `entry_threshold`; monitor "roundtrip < 4 h" giornaliero.
* **Ledger:** F-013 (nuova occorrenza, costo null — i dollari del giorno sono su F-008)

---

### [DAY-003] `sentiment_reversal` chiude posizioni di qualunque strategia, ma il P&L è attribuito alla sleeve che le deteneva

* **Tipo:** Rischio (correttezza dell'evidenza)
* **Area:** PnL / Signal
* **Evidenza:**
  * file: `src/workers/portfolio_scheduler.py:4159-4165` — `for pos in alpaca_positions:` senza
    alcun filtro di strategia
  * tabella: `trades` 356 (INTC, `stop_strategy='S1'`, `exit_reason='sentiment_reversal'`)
  * timestamp: 2026-08-10 16:22:00 UTC
  * query: `SELECT stop_strategy, exit_reason, count(*), sum(net_pnl) FROM trades WHERE exit_time>='2026-07-01' AND stop_strategy='S1' GROUP BY 1,2;`
    → `portfolio_sell` 34 trade −400,62 $ · **`sentiment_reversal` 19 trade −349,01 $**
* **Descrizione:** la regola di uscita per reversal di sentiment è **globale e documentata**
  (`docs/strategies.md:273` la elenca fra i path che restano attivi fuori dalla finestra di
  ribilanciamento di S1): non è un bug di esecuzione. Il problema è di **misura**: il trade resta
  taggato `S1` e il suo P&L confluisce in `s1_realizzato` (oggi +1,89 $ su
  `market_daily.jsonl`), ma la decisione di uscita è stata presa da un segnale S4. Dal 2026-07-01,
  **19 uscite su 53 di S1 (36%) e il 47% della sua perdita realizzata** provengono da questa via.
* **Impatto:** la domanda di uscita n. 2 della carta — *"S1 ha un edge una volta corretta la
  misura?"* — verrà risposta su una serie in cui più di un terzo delle uscite non è prodotta da S1.
  Nella finestra di osservazione l'effetto è finora piccolo (1 uscita su 13 dal 08-03), ma cresce.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza sulla **sola strumentazione** — registrare in
  `trades` la strategia che ha *originato l'uscita* accanto a quella che deteneva la posizione, e
  separare le due serie nel ledger. Nessun cambio di comportamento: la regola resta com'è.
* **Test/monitor:** colonna `exit_strategy` (o `exit_origin`) popolata su ogni uscita; report
  giornaliero che spezza il realizzato per coppia (sleeve detentrice, sleeve che ha deciso).
* **Ledger:** **F-033 (nuovo)**

---

### [DAY-004] 25 dei 96 simboli di watchlist cadono nel tier di costo di default a 20 bps

* **Tipo:** Bug
* **Area:** PnL / Data
* **Evidenza:**
  * file: `config/cost_model.yaml:7-38` — `tier_d` è `default: true`, `spread_bps: 20.0`,
    descrizione *"Default: small-cap, illiquid"*
  * tabella: `trades` 695 (SONY) `cost_bps = 20,24`, `cost_usd = 2,4196` contro NVDA/META/MSFT a
    `1,74 bps` / `0,236 $`
  * timestamp: 2026-08-10 16:07:00 UTC
  * query: simboli di `trading.yaml:watchlist` assenti da tutti i tier →
    `PANW, IBM, SAP, SHEL, BP, AZN, UBS, DB, ERIC, NOK, BABA, BIDU, JD, TM, SONY, INFY, RIO, VALE, PBR, SOXX, ROKU, RDDT, HOOD, WDC, SPCX`
* **Descrizione:** i 17 ADR aggiunti con la migrazione `010_add_adr_tickers.sql` e 8 altri simboli
  non sono mai stati inseriti in `config/cost_model.yaml`, che è fermo a `last_modified: 2026-05-29`.
  Cadono quindi nel tier di default pensato per small-cap illiquide: **20 bps invece dei 5 bps del
  tier_b**, 13× il tier_a. Fra loro ci sono IBM, SAP, Toyota, Shell, BP, AstraZeneca e **SOXX**,
  che è un ETF liquido. Effetto collaterale: anche `stop_loss_pct` per questi simboli è quello
  small-cap (5% invece di 3,5%) — oggi inerte perché gli stop protettivi sono disattivati.
* **Impatto:** **non tocca gli ordini** (il modello costi è usato solo per la contabilità in
  `pg_store` e per il fallback di sigma; nessun gate pre-trade lo legge), ma **falsifica il P&L
  registrato**. Dal 2026-07-01: 52 trade su questi simboli hanno accumulato **135,94 $** di costo
  modellato a ~20,2 bps; a `tier_b` sarebbero stati ~34 $. **≈ 100 $ di perdita fittizia** iscritta
  a libro in sei settimane. Le soglie della carta di osservazione sono ±200 $: è materiale.
* **Severità:** High · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — assegnare esplicitamente un tier a tutti i 96
  simboli di watchlist e far fallire l'avvio (o emettere un WARNING tracciato) quando un simbolo di
  watchlist cade nel default. **Non è taratura:** non cambia una soglia di strategia, corregge una
  classificazione di dato palesemente errata che sporca la serie che decide il 28/09.
* **Test/monitor:** test che `set(watchlist) ⊆ set(simboli con tier esplicito)`; alert al primo
  trade su un simbolo servito dal tier di default.
* **Ledger:** **F-034 (nuovo)**

---

### [DAY-005] `decay_reports` produce metriche identiche per S1, S2 e S4 — inclusa S2, che è morta

* **Tipo:** Bug
* **Area:** Ops / PnL
* **Evidenza:**
  * tabella: `decay_reports`, 12 righe del 2026-08-10 21:00:00
  * snippet: `hit_rate` 0,3702 · `ic` 0,0150 · `max_drawdown` 0,0858 · `sharpe` −6,4151 —
    **gli stessi quattro valori** confrontati contro tre baseline diverse
* **Descrizione:** le metriche osservate sono globali di pipeline, non per-strategia, ma vengono
  confrontate con le baseline specifiche di ciascuna sleeve. Il risultato: `sharpe` CRITICAL per
  tutte e tre, S2 compresa — che non ha posizioni né trade e il cui audit del 2026-08-04 l'ha
  dichiarata morta.
* **Impatto:** l'unico sistema di rilevazione del decadimento delle strategie è ceco per costruzione.
  Un CRITICAL che compare ogni giorno su tre sleeve, una delle quali non esiste, non è un segnale.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — calcolare le metriche per `strategy_id` a partire
  da `trades.stop_strategy` (con [DAY-003] risolto), ed escludere le sleeve senza posizioni.
* **Test/monitor:** test che due strategie con trade diversi producano `actual_value` diversi;
  assert che una sleeve senza trade nella finestra non generi righe.
* **Ledger:** F-004 (nuova occorrenza, costo null)

---

### [DAY-006] Le finestre beat sono in ora UTC fissa: 37 minuti di sessione scoperti, con incidente CRITICAL auto-risolto ogni mattina

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * file: `src/workers/celery_app.py:78,142,153,175,201` — `crontab(..., hour="14-21")`
  * tabella: `portfolio_cycles` (primo 14:07:00, ultimo 19:52:00, 24 cicli), `mobile_events`
  * timestamp: incidente `critical` "Ciclo di portafoglio in ritardo" alle 2026-08-10 13:30:01,
    stato `recovered`
* **Descrizione:** in EDT l'apertura è alle 13:30 UTC ma il beat parte da `hour=14`: i primi 37
  minuti non hanno ingest, scoring né cicli. **Faccia nuova rispetto alle occorrenze precedenti:**
  il sistema *rileva* la condizione — `mobile_events` scrive un incidente CRITICAL alle 13:30:01 di
  ogni mattina — ma lo marca `recovered` appena il primo ciclo parte, così il sintomo strutturale
  è indistinguibile da un ritardo transitorio.
* **Impatto:** già misurato dall'alpha-miss sul 08-10: al primo ciclo AMAT aveva già percorso il
  76,0% del suo movimento intraday e MRVL il 58,2%, entrambe posizioni S1 lunghe chiuse in perdita.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — derivare la finestra beat dal calendario Alpaca
  (`GetCalendarRequest`, già usato da `scripts/daily_alpha_miss_analysis.sh`) invece che da un'ora
  UTC costante.
* **Test/monitor:** test parametrico su una data EST e una EDT che verifichi che il primo ciclo cada
  entro N minuti dall'apertura; l'incidente mobile non deve auto-risolversi se la causa è strutturale.
* **Ledger:** F-021 (nuova occorrenza, costo null — il giorno è già contato dall'alpha-miss)

---

### [DAY-007] `trades.slippage_est` è una copia di `cost_usd`: la qualità di esecuzione non è misurata

* **Tipo:** Bug
* **Area:** PnL
* **Evidenza:**
  * tabella: `trades` 696/697/698 — `slippage_est` = 0,2368 / 0,2361 / 0,2363 e
    `cost_usd` = 0,2368 / 0,2361 / 0,2363, identici alla quarta cifra
  * timestamp: 2026-08-10 17:22 / 17:37 / 17:52
* **Descrizione:** il campo dichiara di stimare lo slippage ma riporta il costo modellato. Non
  esiste alcun prezzo di riferimento pre-invio persistito, quindi lo scarto fra prezzo atteso e
  prezzo di fill non è calcolabile a posteriori da DB.
* **Impatto:** l'esecuzione è un punto cieco. Ogni conclusione su "quanto ci costa entrare" oggi
  è tautologica: misura il modello, non il mercato.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — persistere il mid (o il last) al momento della
  decisione e calcolare `slippage_est = (fill − reference) × qty × segno`.
* **Test/monitor:** test che `slippage_est ≠ cost_usd` su un fill con prezzo diverso dal riferimento.
* **Ledger:** F-015 (nuova occorrenza, costo null)

---

### [DAY-008] `portfolio_cycles.orders_count` conta gli ordini target, non quelli inviati: 70 contro 8

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * tabella: `portfolio_cycles`, 24 righe del 2026-08-10, `sum(orders_count) = 70`
  * confronto: 8 righe BUY/SELL in `execution_decisions` con `order_id` valorizzato
  * snippet: i cicli 18:07→18:52 dichiarano 5 ordini ciascuno e ne inviano **zero**
* **Descrizione:** il contatore registra la dimensione della lista di ordini target prodotta
  dall'orchestratore prima dei guard (pyramiding, hold-minimum, exit-persistence, delta≈0), non gli
  ordini effettivamente inviati.
* **Impatto:** rapporto 8,8:1 oggi (era 34:1 il 08-07). Chi legge la telemetria vede un sistema
  che tratta 70 volte al giorno mentre ne tratta 8.
* **Severità:** Low · **Confidenza:** High
* **Azione consigliata:** ticket — separare `orders_targeted` da `orders_submitted`.
* **Test/monitor:** assert `orders_submitted == len(order_ids persistiti nel ciclo)`.
* **Ledger:** F-014 (nuova occorrenza, costo null)

---

### [DAY-009] Righe `ingestion_stats_daily` con `source='reuters'` senza connettore e senza dati

* **Tipo:** Bug
* **Area:** Data / Ops
* **Evidenza:**
  * tabella: `ingestion_stats_daily` — `2026-08-10 | reuters | fetched 12 | queued 12 | discarded_no_ticker 3`, `updated_at 22:05:37`
  * controprova: `SELECT count(*) FROM news_log WHERE source='reuters'` → **0**, su tutta la storia
  * serie: righe `reuters` anche il 08-05, 08-06, 08-07 e **08-11 alle 10:52:53** (fetched 24)
* **Descrizione:** nessun task RSS/Reuters esiste nel beat. Le righe compaiono a orari sparsi
  (22:05, 09:02, 12:35, 10:52) compatibili con esecuzioni della suite di test contro il database di
  produzione.
* **Impatto:** la tabella che documenta la copertura delle fonti contiene fonti inesistenti.
  Qualunque analisi di copertura fatta su `ingestion_stats_daily` è contaminata. Rischio più
  generale: se i test scrivono qui, possono scrivere altrove.
* **Severità:** Medium · **Confidenza:** Medium (la firma è dei test; senza log non è confermata)
* **Azione consigliata:** ticket di correttezza — isolare il database di test da quello di
  produzione (env var obbligatoria, o rifiuto di connettersi se `PGDATABASE == trading`).
* **Test/monitor:** vincolo che `ingestion_stats_daily.source` appartenga all'insieme dei connettori
  registrati nel beat.
* **Ledger:** F-028 (nuova occorrenza, costo null)

---

### [DAY-010] La BUY su SONY non ha `signal_id` e cita un punteggio che non esiste in DB

* **Tipo:** Bug
* **Area:** Data / Orders
* **Evidenza:**
  * tabella: `execution_decisions` 8544 — `signal_id NULL`, `signal_score = +0,541`
  * controprova: nessun segnale SONY del giorno vale +0,541; il più vicino è `sentiment_signals`
    7046 delle 16:00:45 a **+0,451**, di cui la decisione cita *verbatim* il reasoning
  * controprova inversa: le altre 3 BUY hanno `signal_id` valorizzato e punteggio coincidente al
    millesimo (7098→0,441 · 7109→0,515 · 7116→0,470)
* **Descrizione:** 3 righe su 463 hanno la chiave esterna. Quando `signal_id` non viene catturato,
  anche il numero stampato nel `reason` diventa non riconciliabile.
* **Impatto:** auditabilità. La catena segnale→decisione→trade si ricostruisce a mano, per orario e
  per testo del reasoning.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — propagare `signal_id` su ogni riga di
  `execution_decisions` e derivare `signal_score` dalla riga referenziata, mai da una variabile locale.
* **Test/monitor:** assert che ogni decisione BUY/SELL abbia `signal_id NOT NULL` e
  `signal_score = (SELECT score FROM sentiment_signals WHERE id = signal_id)`.
* **Ledger:** F-011 (occorrenza 08-10 già scritta dall'alpha-miss, con questa stessa faccia)

---

### [DAY-011] Metà delle righe scorate nasce da articoli fan-out multi-ticker; `org_lookup` regala 59 righe a tre banche che non c'entrano

* **Tipo:** Bug
* **Area:** News / LLM
* **Evidenza:**
  * query: 131 URL distinti → 196 segnali su 54 simboli; 36 articoli taggati a ≥ 2 ticker
  * casi: *"S&P 500 Earnings Growth…"* → 6 ticker; *"Oil Jumps 3%, Yields Climb"* → 6;
    *"Microsoft Stock Rises 2%: Maia 300"* → 5, e produce MSFT **+0,470** e NVDA **−0,121**
  * ticker: MS 33 righe, GS 15, DB 11 = **59 su 196 (30%)**, nessuna sulle tre banche
* **Descrizione:** un articolo su una società produce un punteggio "ticker-specifico" su tutte le
  altre nominate, e il boilerplate della casa d'analisi fa attribuire a MS/GS/DB articoli estranei.
  Il caso più netto di oggi: lo stesso pezzo che ha comprato MSFT ha spinto NVDA a −0,121, e
  quel segnale ha poi contribuito a farla uscire.
* **Impatto:** il 51,5% dell'input scorato non è ticker-specifico. È il collo di bottiglia della
  qualità del dato, non della soglia.
* **Severità:** High · **Confidenza:** High
* **Azione consigliata:** già coperto dalla roadmap QX-01 (enforcement del resolver, gated sul
  golden set). Nessun ticket nuovo.
* **Test/monitor:** rapporto `segnali / URL distinti` come metrica giornaliera; alert se un articolo
  genera più di N segnali.
* **Ledger:** F-012 e F-020 (occorrenze 08-10 già scritte dall'alpha-miss)

---

### [DAY-012] Latenza di ingestione ~75 minuti contro una finestra di freschezza di 30

* **Tipo:** Rischio
* **Area:** News
* **Evidenza:**
  * query: mediana `fetched_at − published_at` = 75,2 min (benzinga) e 75,5 min (gdelt);
    massimo 120,7 min
  * config: `signal_freshness_minutes: 30` (`config/trading.yaml:149`)
* **Descrizione:** la notizia entra nel sistema in mediana 75 minuti dopo la pubblicazione, poi
  serve un ciclo di scoring e uno di portafoglio. In miglioramento rispetto alla mediana di ~110
  min misurata in precedenza, ma sempre oltre il doppio della finestra di freschezza dichiarata.
* **Impatto:** misurato dall'alpha-miss sui nove mover con copertura: al primo segnale utile era
  già avvenuta in mediana il **69,9%** del movimento intraday.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** nessun ticket in finestra di osservazione — è una proprietà della fonte,
  e la conseguenza è già registrata come F-030. Da riprendere alla scelta della fonte dati per S4
  (domanda di uscita n. 1).
* **Test/monitor:** percentile 50/90 della latenza pubblicato ogni giorno nel dossier.
* **Ledger:** F-019 (nuova occorrenza, costo null)

---

### [DAY-013] Buco di 29 minuti nella produzione di segnali, segnalato e auto-risolto

* **Tipo:** Osservazione
* **Area:** LLM / Ops
* **Evidenza:**
  * tabella: `sentiment_signals` — ultimo alle 15:00:53, successivo alle 15:30:09 (29,3 min)
  * `mobile_events`: WARNING "Segnali sentiment in ritardo" alle 15:24:00, `recovered`
  * beat: scoring su `minute="12,27,42,57"` → la corsa delle 15:12 non ha prodotto righe
* **Descrizione:** unico buco > 20 min della giornata. L'ingest delle 15:00 aveva portato 30
  articoli, quindi non è assenza di input. Senza i log del giorno ([DAY-014]) non è possibile
  distinguere fra "nessun articolo eleggibile in coda" e "corsa fallita in silenzio".
* **Impatto:** nullo osservabile — nei cicli 14:52–15:52 il sistema non aveva comunque ordini target.
* **Severità:** Low · **Confidenza:** Low
* **Azione consigliata:** nessuna. Da riosservare quando i log saranno conservati.
* **Test/monitor:** contatore di corse di scoring completate, così che "0 articoli" e "corsa
  fallita" siano distinguibili senza log.
* **Ledger:** nessuno (osservazione singola, sotto la soglia di apertura di un finding)

---

### [DAY-014] `llm_responses.eligible` è incoerente: 97 segnali "ensemble" hanno zero risposte eleggibili, e una risposta a confidenza 0,9 è ineleggibile mentre una a 0,4 è eleggibile

* **Tipo:** Bug
* **Area:** LLM / Data
* **Evidenza:**
  * query: fra i 144 segnali taggati `ensemble`, **97 hanno `n_elig = 0`** e 47 ne hanno 2 —
    nessuno ne ha 1
  * query: `min(confidence) WHERE eligible` = **0,40** · `max(confidence) WHERE NOT eligible` = **0,90**
  * volumi: 52 segnali su 196 (26,5%) taggati `single:<model>` con `fallback_used = true`, pur
    avendo **entrambi** i modelli risposto
* **Descrizione:** faccia nuova e più nitida di un difetto già noto. `eligible` non è una soglia di
  confidenza (le due distribuzioni si sovrappongono da 0,40 a 0,90) e non è coerente con il tag del
  segnale (97 "ensemble" senza alcun contributore eleggibile). A valle, il filtro #108 scarta dal
  ranking BUY i segnali `fallback_used = true` **come se fossero FinBERT**, mentre FinBERT non è
  stato invocato nemmeno una volta oggi.
* **Impatto:** un quarto dei segnali è escluso dal ranking d'ingresso per una ragione che il dato
  non sostiene. Costo verificato 0,00 $ per la seconda volta: nessuno dei 52 avrebbe generato un
  ordine oggi comunque.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — far corrispondere `eligible` a una regola
  documentata e verificabile, e distinguere nel tag il fallback FinBERT dal degrado a modello
  singolo. È correttezza dell'evidenza: oggi non sappiamo dire quali modelli abbiano davvero
  formato un segnale.
* **Test/monitor:** assert che un segnale `ensemble:A+B` abbia esattamente 2 risposte con
  `eligible=true`; assert che `fallback_used=true` implichi `model_id` che nomina FinBERT.
* **Ledger:** F-010 (occorrenza 08-10 già scritta dall'alpha-miss; questa run aggiunge la faccia
  dell'incoerenza `eligible`)

---

### [DAY-015] WDC è aperta da 21 giorni sotto una regola che dichiara un orizzonte di 4 ore

* **Tipo:** Rischio
* **Area:** Orders / PnL
* **Evidenza:**
  * tabella: `trades` 373 — WDC, `stop_strategy='S4'`, `entry_time = 2026-07-21`, nozionale 1.637 $,
    tuttora aperta al 2026-08-11
  * config: `max_signal_age_hours = 4`; il meccanismo che la tiene è `preserve-stale` (FIX-D)
* **Descrizione:** S4 non ha un orizzonte di uscita per le posizioni che restano tiepidamente
  positive: `preserve-stale` re-ammette il segnale vecchio a ogni ciclo perché la posizione è
  aperta e non c'è contro-segnale, e la posizione non esce mai. Delle due posizioni S4 a libro, una
  è entrata oggi, l'altra 21 giorni fa.
* **Impatto:** una sleeve che dichiara un orizzonte di ore detiene una posizione da tre settimane.
  Le statistiche di holding period di S4 non descrivono S4.
* **Severità:** Medium · **Confidenza:** High
* **Azione consigliata:** ticket già tracciato dal ledger; la correzione (un orizzonte massimo) è
  **taratura** e resta al 28/09.
* **Test/monitor:** alert su posizione S4 con `entry_time` più vecchio di N giorni.
* **Ledger:** F-025 (nuova occorrenza, costo null — nessun evento nuovo oggi, solo persistenza)

---

### [DAY-016] `risk_reports` emette un ALERT "drawdown 14,3%" e un `daily_pnl` di −77 $ in una giornata chiusa a +162 $

* **Tipo:** Bug
* **Area:** Risk / PnL
* **Evidenza:**
  * tabella: `risk_reports` del 2026-08-10 22:30:01 — `combined_drawdown = 0,012429` (1,24%),
    `per_strategy_metrics.portfolio.drawdown = 0,142574` (14,26%, quello che genera l'ALERT),
    `daily_pnl = −77,15`, `sharpe = −4,82`, `nav = 110.358,03`
  * controprova: `portfolio_monitor_snapshots` 23:42 → NAV 110.344,06, `nav_change_today = +162,43`,
    `current_drawdown = 0,002526` (0,25%)
  * serie: `daily_pnl` non corrisponde mai alla variazione di NAV — 08-03 +1.807,84 contro
    +191,58 reali; 08-04 **−1.645,86** contro **+591,85** reali (segno invertito)
* **Descrizione:** tre numeri di drawdown coesistono nella stessa riga (1,24% / 14,26% / 0,25%) e
  `daily_pnl` è scollegato dal NAV, con il segno invertito in almeno due giornate su otto. Poiché
  `sharpe` è derivato dalla stessa serie, anche il CRITICAL di [DAY-005] poggia su di essa.
* **Impatto:** il report di rischio non è utilizzabile. Emette un ALERT ogni sera da otto giorni:
  chi lo legge non può distinguere un drawdown vero da questo.
* **Severità:** High · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — una sola definizione di drawdown e un `daily_pnl`
  derivato dagli snapshot NAV, che sono la fonte verificata.
* **Test/monitor:** assert `abs(daily_pnl − (nav − previous_close_equity)) < ε`; assert che i
  drawdown pubblicati nella stessa riga concordino entro ε.
* **Ledger:** F-003 (nuova occorrenza, costo null)

---

### [DAY-017] I log dei container del giorno analizzato non esistono più — secondo redeploy in 14 ore

* **Tipo:** Bug
* **Area:** Ops
* **Evidenza:**
  * `docker inspect` → `alembic-worker-1`, `beat-1`, `api-1`, `worker-inference-1`, `frontend-1`
    tutti con `StartedAt = 2026-08-11T12:20:10Z`, `RestartCount = 0` → **ricreati**
  * `docker compose logs worker` → **120 righe totali**, tutte successive al riavvio; zero righe
    del 2026-08-10
  * storia: l'alpha-miss delle 08:00 di oggi aveva log a partire dalle 22:13:38 del 08-10 (già
    dopo la chiusura); il redeploy delle 12:20 ha cancellato anche quelli
* **Descrizione:** i 14 merge su `main` del 2026-08-11 hanno comportato due ricreazioni dei
  container. Il buffer di log non sopravvive.
* **Impatto:** diretto su questo report. Le categorie **eccezioni silenziose**, **errori non
  propagati ad alert**, **latenza LLM**, **retry**, **guard che hanno bloccato ordini** e
  **idempotenza Celery** non sono verificabili: tutto ciò che segue è inferenza su DB. Le tre
  categorie richieste dalla fase 8 che dipendono dai log sono dichiarate non verificabili in §12.
* **Severità:** High · **Confidenza:** High
* **Azione consigliata:** ticket di correttezza — driver di logging persistente (file o journald)
  con rotazione, o spedizione a un sink esterno. Senza questo, ogni giorno con un deploy è
  parzialmente non analizzabile, e i deploy sono quotidiani.
* **Test/monitor:** verifica automatica che i log coprano le 24 h precedenti prima di avviare il
  ciclo forense.
* **Ledger:** F-027 (occorrenza 08-10 già scritta dall'alpha-miss; qui si registra il **secondo**
  redeploy)

---

### [DAY-018] `ingestion_stats_daily.duplicates` supera `fetched` di 3,7×

* **Tipo:** Osservazione
* **Area:** News / Data
* **Evidenza:** `2026-08-10 | alpaca_benzinga | fetched 844 | queued 347 | duplicates 3.122`
* **Descrizione:** il contatore è un UPSERT additivo cross-run (`src/store/pg_store.py:369`), quindi
  somma i duplicati di ogni corsa mentre `fetched` conta gli articoli visti. Verifica indipendente
  su `news_log`: 131 `content_hash` distinti su 196 righe — la deduplicazione **funziona**, il
  contatore no. Rapporto in calo da 5,3× (08-07) a 3,7×.
* **Impatto:** solo di lettura. Nessun articolo perso.
* **Severità:** Low · **Confidenza:** High
* **Azione consigliata:** rinominare il campo o azzerarlo per giorno.
* **Test/monitor:** assert `duplicates ≤ fetched` per (day, source).
* **Ledger:** F-007 (nuova occorrenza, costo null)

---

## 11. False positive e aree risultate corrette

Verificate esplicitamente e **corrette**:

| area | verifica | esito |
|---|---|---|
| **#185 — frequenza di ribilanciamento S1** | `strategy:rebalance_state:S1` fermo al 2026-08-07 14:07; zero `portfolio_sell` S1 dal 08-07 | ✓ la deroga funziona come progettata |
| **#184 — `exit_mechanism`** | le 3 SELL portano `below_entry_gate`, che è una **disposizione osservata** registrata dove avviene, non dedotta dall'orologio (`src/portfolio/exit_classification.py`). Le righe del 08-10 sono **post-fix**: il conteggio è una misura, non una stima per età | ✓ |
| **#191 — gate d'ingresso S4** | `feedback:entry_threshold:S4 = 0.30`, non risalito | ✓ |
| **Ollama Cloud** | 392 risposte su 392 attese, 0 errori, 0 timeout, `consecutive_fallback = 0` | ✓ up 100% |
| **FinBERT** | 0 invocazioni | ✓ nessun fallback deterministico necessario |
| **LOO ICIR** | auto-apply **bloccato** con `IC variance 0.188 ≥ 0.15`, pesi invariati | ✓ guardrail corretto |
| **`stop_d_init = 0`** | non è un bug: `stop_loss: 0.0` è una decisione paper esplicita e documentata (`config/trading.yaml:170-183`) | ✓ falso allarme escluso |
| **`hold_minimum` + `exit_persistence`** | NVDA era sotto gate dalle 17:45 ed è uscita alle 19:07: i due guard hanno aggiunto 82 minuti di tenuta | ✓ funzionano, ma non bastano contro [DAY-002] |
| **`sentiment_reversal` su INTC** | ensemble non-fallback, conf 0,850, età < 60 min, consume-on-fire, quattro articoli concordi. `drift_post_uscita = −0,67` | ✓ **miglior decisione della giornata** |
| **Riconciliazione posizioni** | 48 broker = 48 DB | ✓ |
| **Ordini duplicati / fuori orario / senza segnale / su ticker non consentiti** | zero in tutte e quattro le categorie | ✓ |
| **Circuit breaker** | `system:halted_by_operator` assente, drawdown reale 0,25% contro trigger 5% | ✓ correttamente inattivo |
| **Igiene timestamp news** | 0 timestamp futuri, 0 `published_at` nulli, 0 `parse_fail` | ✓ |

---

## 12. Dati mancanti o non accessibili

| risorsa | stato | conseguenza | rimedio |
|---|---|---|---|
| **API REST locale** (`localhost:8001`) | **403 su tutti gli endpoint autenticati** — `{"detail":"Invalid or expired JWT token"}` su `/decisions`, `/trades`, `/signals`, `/positions`, `/orders`; solo `/health` risponde 200 | nessuna: l'intera analisi è stata condotta su Postgres e Redis, che sono la fonte primaria di quegli endpoint | rigenerare il token nel prompt del cron (**secondo giorno consecutivo**) |
| **Log container 2026-08-10** | **inesistenti** — due redeploy, l'ultimo alle 12:20 UTC del 08-11 | eccezioni silenziose, errori non propagati ad alert, latenza LLM, retry, guard che hanno bloccato ordini, idempotenza Celery: **non verificabili** | [DAY-017] |
| **Latenza per-chiamata LLM** | `llm_responses` non ha campo durata | distribuzione delle latenze non calcolabile | aggiungere `latency_ms` |
| **Prezzo di riferimento pre-invio** | non persistito | slippage reale non calcolabile | [DAY-007] |
| **P&L economico** (definizione della carta) | non calcolato da alcun processo | la domanda di uscita n. 2 non ha oggi una serie pronta | query indicata in §8.6 |
| **Stato dei guard per ciclo** | il blocco anti-pyramiding non lasciava riga il 08-10 | "bloccato di proposito" e "mai valutato" indistinguibili da DB | **già corretto**: `SKIP_PYRAMIDING` mergiato il 08-11 (commit `099b6fd`, #231) |

---

## 13. Raccomandazioni immediate

Tutte compatibili con il freeze #171: nessuna tocca una soglia, un peso o un parametro di strategia.

1. **Rigenerare il bearer token** usato dai cron forensi. È il secondo giorno che l'API è
   inaccessibile; finora il DB ha coperto, ma la Quality/Decision UI non è verificabile.
2. **Assegnare un tier di costo a tutti i 96 simboli di watchlist** ([DAY-004]). È la
   raccomandazione con il rapporto sforzo/effetto migliore: una modifica di configurazione elimina
   ~100 $ di perdita fittizia già iscritta e impedisce che ne maturi altra prima del 28/09.
3. **Persistere i log dei container** ([DAY-017]). Senza, ogni giorno con deploy è parzialmente
   cieco, e i deploy sono quotidiani.
4. **Registrare la strategia che origina l'uscita** ([DAY-003]), separatamente da quella che detiene
   la posizione. Senza, la domanda di uscita n. 2 verrà risposta su una serie contaminata al 36%.
5. **Non intervenire su [DAY-001] e [DAY-002] con una taratura.** La banda di isteresi va
   *introdotta come concetto nel codice* (oggi non esiste), con i due valori uguali alla consegna;
   la calibrazione è materia del 28/09.

## 14. Test e monitor da aggiungere

| # | test/monitor | difende |
|---|---|---|
| T1 | `set(watchlist) ⊆ set(simboli con tier di costo esplicito)` | [DAY-004] |
| T2 | assert `abs(daily_pnl − (nav − previous_close_equity)) < ε` e coerenza fra i drawdown della stessa riga | [DAY-016] |
| T3 | due strategie con trade diversi producono `decay_reports.actual_value` diversi | [DAY-005] |
| T4 | ogni decisione BUY/SELL ha `signal_id NOT NULL` e `signal_score` uguale al segnale referenziato | [DAY-010] |
| T5 | una posizione con peso > 0 non è azzerata da uno score fra `exit_threshold` e `entry_threshold` | [DAY-002] |
| T6 | un segnale `ensemble:A+B` ha esattamente 2 risposte `eligible=true`; `fallback_used=true` ⟹ `model_id` nomina FinBERT | [DAY-014] |
| T7 | `slippage_est ≠ cost_usd` su un fill con prezzo diverso dal riferimento | [DAY-007] |
| T8 | `orders_submitted == len(order_id persistiti nel ciclo)` | [DAY-008] |
| T9 | `ingestion_stats_daily.source ∈ connettori registrati nel beat`; `duplicates ≤ fetched` | [DAY-009], [DAY-018] |
| M1 | monitor giornaliero "roundtrip < 4 h" e "posizione chiusa da un articolo taggato a ≥ 3 ticker" | [DAY-001], [DAY-002] |
| M2 | percentile 50/90 della latenza `published_at → fetched_at` nel dossier | [DAY-012] |
| M3 | verifica che i log coprano le 24 h precedenti **prima** di avviare il ciclo forense | [DAY-017] |
| M4 | alert su posizione S4 con `entry_time` più vecchio di N giorni | [DAY-015] |

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza**, come prescritto dalla carta di osservazione: se non corretti,
l'evidenza raccolta fino al 28/09 è sbagliata.

| id | titolo | area | priorità | supera il test di esenzione? |
|---|---|---|---|---|
| **T-A** | Assegnare un tier di costo esplicito a tutti i simboli di watchlist; fallire o allertare sul default | PnL | **P1** | **Sì** — il costo modellato entra in `net_pnl`, che è la serie su cui si decide |
| **T-B** | Riconciliare `risk_reports`: una sola definizione di drawdown, `daily_pnl` derivato dagli snapshot NAV | Risk | **P1** | **Sì** — l'unico ALERT di rischio del sistema è oggi inutilizzabile |
| **T-C** | Registrare la strategia che origina l'uscita accanto a quella detentrice | PnL | **P1** | **Sì** — contamina la domanda di uscita n. 2 |
| **T-D** | Logging persistente dei container (driver file/journald con rotazione) | Ops | **P1** | **Sì** — senza log, intere categorie di anomalia sono non falsificabili |
| **T-E** | Separare `exit_threshold` da `entry_threshold` nel codice, valori uguali alla consegna | Signal | **P2** | **Sì** — oggi la banda non esiste come concetto, quindi non sarà tarabile al 28/09 |
| **T-F** | La sostituzione del segnale corrente pesa la confidenza; un fan-out a bassa confidenza non azzera una posizione | Signal | **P2** | **Sì** — decide quali posizioni vivono, quindi decide l'evidenza |
| **T-G** | `decay_reports` per-strategia da `trades.stop_strategy`; escludere le sleeve senza posizioni | Ops | **P2** | Sì (debole) |
| **T-H** | Rendere `llm_responses.eligible` coerente e distinguere il degrado single-model dal fallback FinBERT | LLM | **P2** | **Sì** — oggi non sappiamo quali modelli formino un segnale |
| **T-I** | Isolare il database di test da quello di produzione | Data | **P2** | Sì (debole) — righe di test in tabelle di evidenza |
| **T-J** | `signal_id` propagato su ogni `execution_decisions`; `signal_score` derivato dalla riga referenziata | Data | **P3** | Sì (debole) |
| **T-K** | Finestre beat derivate dal calendario Alpaca invece che da un'ora UTC fissa | Ops | **P3** | Sì (debole) |
| **T-L** | Persistere il prezzo di riferimento pre-invio e calcolare lo slippage reale | PnL | **P3** | No — strumentazione nuova, non correzione |
| **T-M** | `orders_targeted` separato da `orders_submitted` | Ops | **P4** | No |

## 16. Stato sistema

| voce | stato |
|---|---|
| **Ollama Cloud** | **UP, 0 h di downtime.** 392 risposte su 392 attese (196 segnali × 2 modelli), 0 errori, 0 timeout, 0 output invalidi. `fallback_counters.consecutive_fallback = 0`, ultimo incremento 2026-08-05 |
| **Coppia attiva** | `glm52,gptoss` (`config:sentiment_llm_models`) — coerente con la coppia di design |
| **Pesi ensemble** | glm-5.2 0,6009 / gpt-oss 0,3991 — invariati: auto-apply **congelato** il 08-10 alle 04:00 per `IC variance 0.188 ≥ 0.15`. ICIR purificato: glm **+0,293**, gptoss **−0,084** |
| **FinBERT fallback rate** | **0,0% delle decisioni** — FinBERT non è stato invocato. Il 26,5% di segnali `fallback_used=true` è degrado a modello singolo, non FinBERT ([DAY-014]) |
| **Costo LLM** | 0,2307 $ · 115.374 token in · 15.129 out · `budget_exhausted = false` |
| **Worker restart** | **2 ricreazioni complete** — la prima il 2026-08-10 alle 22:13 UTC (dopo la chiusura), la seconda il 2026-08-11 alle 12:20 UTC. `RestartCount = 0` su tutti: sono ricreazioni da deploy, non crash. **Nessun restart durante la sessione analizzata** |
| **Postgres / Redis** | up da 3 giorni, healthy, nessun riavvio |
| **Gate d'ingresso S4** | `feedback:entry_threshold:S4 = 0,30` (TTL 291.514 s) — non risalito, deroga #191 rispettata |
| **Kill-switch** | inattivo e corretto: `system:halted_by_operator` assente, drawdown reale 0,25% contro trigger 5% |
| **Incidenti mobile** | 5, tutti `recovered`: 2 all'apertura (ciclo e segnali in ritardo — [DAY-006]), 1 alle 15:24 ([DAY-013]), 2 alle 23:41 (dati broker / market_clock) |
| **Riconciliazione** | 48 posizioni broker = 48 in DB. 8 ordini = 8 fill = 4 aperture + 4 chiusure |

---

*Report generato in modalità read-only. Nessun file di codice modificato, nessun ordine inviato,
nessun worker avviato.*
