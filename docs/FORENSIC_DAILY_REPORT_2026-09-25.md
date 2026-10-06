# Forensic Daily Report — 2026-09-25

Sessione forense autonoma, sola lettura (eseguita il 2026-10-06). Fuso operativo **UTC** (`src/workers/celery_app.py`, `timezone="UTC"`, `enable_utc=True`): tutti i timestamp sono UTC. Seduta RTH 13:30–20:00 UTC (EDT, venerdì).
Conto **paper** verificato, non assunto: `portfolio_monitor_snapshots.broker_environment='paper'` su 90/90 istantanee; `/api/orders` punta a `paper-api.alpaca.markets`. `execution.engine=portfolio`.

Periodo di **sola osservazione** (`docs/evidence/OBSERVATION_CHARTER.md`, scadenza 2026-09-28): nessuna taratura proposta; i ticket riguardano solo difetti di correttezza o strumentazione.

**Nota di processo sul ledger.** Al momento di questa sessione `docs/evidence/findings.json` (working tree, non committato) conteneva già 28 occorrenze con `fonte` `FORENSIC_DAILY_REPORT_2026-09-25.md` (DAY-001…DAY-028), scritte da una sessione precedente per lo stesso giorno, interrotta prima di salvare il report (il file non esisteva né in git né su disco). Questo report **adotta quegli id** e non ne aggiunge altri: riappendere le stesse occorrenze le duplicherebbe e ne falserebbe la ricorrenza. Ho riverificato in modo indipendente su DB e log i numeri portanti (segnali, fallback, ordini, trade, NAV, rete, ingest); tutti coincidono con le note del ledger. Nessuna anomalia nuova rispetto a quelle già registrate. Esiste anche `docs/ALPHA_MISS_REPORT_2026-09-25.md` che ha registrato con costo F-001 (4,97), F-023 (−23,26), F-089 (33,74): qui agganciati con `costo_usd: null` per non contarli due volte.

---

## 1. Executive summary

La pipeline ha girato end-to-end: 745 articoli Benzinga + 1.505 GDELT ingeriti → 178 righe scorate (56 simboli) → 24 cicli portfolio (14:07–19:52) → 5 BUY e 3 SELL S4, tutti `filled` sul conto paper, più 2 SKIP_PYRAMIDING. Nessun ordine fuori orario, duplicato, o senza causa nel `reason`.
Ollama è rimasto raggiungibile tutta la seduta (29 errori di ensemble: 18 timeout gpt-oss, 7 glm, nessun periodo di blackout). FinBERT reale usato su **3** segnali (1,7%), non sui 77 che il contatore del task dichiara (F-078).
NAV 109.953,87 → 109.984,26 $ (**+30,39 $, +0,03%**) contro SPY **+0,54%**. Realizzato S4 dei 3 round-trip chiusi: −17,08 $ netto (ARM −29,19, HOOD +0,84, MSFT +11,27); NVDA e COST restano aperte overnight (uscite il 28/09, +27,98 e +4,74).
Perdita di rete DNS 16:54–17:03 in seduta (e 13:16–13:29 pre-market): i job di ingest leggono il guasto come «market closed» e terminano `succeeded` (F-074); ciclo 17:07 regolare, articoli recuperati con ~14 min di ritardo.
Due difetti di correttezza toccano le decisioni di oggi: **F-088** (pesi ensemble 0,5/0,5 invece dei dichiarati: il BUY MSFT non sarebbe partito) e **F-023** (ogni ultimo segnale fan-out positivo sotto gate sovrascrive l'ingresso: 3/3 SELL). F-089 lascia MU/INTC/PANW senza uscita S4.
Strumentazione: `/api/trades` riporta un realizzato lordo +181,82 $ contro −15,14 $ del ledger (F-084); 3/3 SELL con `signal_id` NULL (F-011); `decision_price` NULL su 8/8 ordini (F-015); regime da un solo LLM per 410 Gone su `qwen3.5:cloud` (F-017).

## 2. Verdict

**Anomalie significative.**

Il percorso del denaro è corretto: ogni BUY ha segnale sopra gate, ogni SELL ha un `exit_mechanism` osservato (`below_entry_gate`), cap e stop applicati, fill riconciliati col broker. Ma le decisioni del giorno dipendono da difetti noti non corretti (pesi F-088, sovrascrittura segnale F-023, uscita S4 disarmata F-089) e l'endpoint di P&L dei trade è inaffidabile (F-084). Nessuno richiede di fermare il sistema; vanno dichiarati prima della sintesi di fine osservazione (28/09).

**Avvertenza `exit_mechanism` (#184).** I 3 SELL del 25/09 hanno `exit_mechanism='below_entry_gate'` **osservato** (post-fix, testo del motivo `[below_entry_gate] …`). Non è una stima per età. Il vocabolario di `trades.exit_reason` è diverso (`hold_minimum_expiry` su ARM/HOOD, `portfolio_sell` su MSFT): non va letto come meccanismo di uscita.

---

## 3. Timeline del 2026-09-25 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 00:00–13:29 | `worker-news-stream` | WS Benzinga 24/7; dispatch sentiment | `skipped: market_closed` (84 dispatch) | `worker-inference-…log`, F-069 |
| 03:00 | `worker` | daily performance report | ok | `worker-…log` |
| 07:00:56 | `detect_regime` | LLM-2 `410 Gone` → regime da 1 modello (SIDEWAYS ×0,7) | task succeeded, nessun alert | `worker-inference-…log`, F-017 |
| 08:20 · 12:05 | deploy | Warm shutdown `worker`/`worker-inference` + restart `beat`; 4 messaggi unack ripristinati; job 8134 perso (SIGTERM) | fuori seduta | log, `WorkerLostError` |
| 13:16–13:29 | rete | DNS/`No route` pre-market; alert `broker_stale` + `market_clock` critical 13:17:32 | rientrato | `mobile_events`, F-074 |
| 13:30:01 | alert | `portfolio_cycle_late` critical + `signal_stale` warning | rientrati 14:08 | `mobile_events` |
| 13:33:11–13:38:08 | sentiment | drena coda notturna: **187 stale** (età media 10,4 h) + 161 not_tradable | scartati | `news_queue_drops`, F-069 |
| 13:33:26 | sentiment | primo segnale | — | `sentiment_signals` |
| 13:36:34 | `detect_regime` | seconda occorrenza 410 Gone | idem | log |
| 14:07:00 | portfolio-cycle | **BUY ARM** @321,95 (sig 12671, +0,323×1,20→0,387, peso 2%) | filled 14:07:15 | `execution_decisions` 45669, trade 1029 |
| 14:07:15 · 14:22:15 | notifier | Telegram `400 Bad Request` | non consegnato | log, F-005 |
| 14:22:00 | portfolio-cycle | **BUY HOOD** @118,68 (sig 12706) | filled | trade 1030 |
| 14:37:00 | portfolio-cycle | **BUY MSFT** @514,00 (sig 12712, +0,310) | filled | trade 1031 |
| 14:52:11 | portfolio-cycle | SKIP_PYRAMIDING AMD (+0,390, S1 a libro dal 14/07) | 21 intenti 14:52–19:52 | F-031 |
| 15:37:10 | portfolio-cycle | SKIP_PYRAMIDING WDC (+0,338) | 18 intenti | F-031 |
| 15:52:00 | portfolio-cycle | **SELL ARM** `below_entry_gate` (nuovo segnale +0,035 da articolo BofA su AMD, 14:49) | filled 15:52:13 @315,81 | decisione 46491, F-023 |
| 16:07:00 | portfolio-cycle | **SELL HOOD** `below_entry_gate` (+0,021, 14:28) | filled @118,81 | decisione 46612 |
| 16:52:00 | portfolio-cycle | **BUY NVDA** @224,84 (sig 12789, +0,265) e **SELL MSFT** `below_entry_gate` (+0,165, 16:43) | filled 16:52:13 | 46979/46980 |
| 16:54–17:03 | rete | DNS in seduta; alert `broker_stale`/`market_clock` 16:58:32 | rientrato | F-074 |
| 17:00:16 | ingest | `run_alpaca_ingestion_worker`/GDELT leggono clock non raggiungibile come «market closed» | `succeeded {skipped}` | log worker, F-074 |
| 17:15 | ingest REST | recupero articoli 16:55/17:01 | ~14 min di ritardo | `news_log` |
| 17:52:00 | portfolio-cycle | **BUY COST** @921,45 (sig 12811, +0,326) | filled | trade 1033 |
| 18:22:07 | portfolio-cycle | SKIP_STALE MS (segnale 4,1 h > 4 h) | corretto | 1 riga |
| 19:28 | alert | `signal_stale` warning | — | `mobile_events` |
| 20:00:00 | monitor | NAV 109.984,26 (+30,39), 45 posizioni, unrealized 1.785,24 | snapshot paper | `portfolio_monitor_snapshots` |
| 21:00:00 | decay monitor | 8 righe DECAY CRITICAL (S1/S2/S4) solo `log.critical` | nessun canale | log, F-004/F-062 |
| 22:50:00–01 | alert | coverage `held_no_news_loss` AMAT/CSCO/VALE; griglia portfolio-cycle fuori seduta | aperti/chiusi in 1 s | `mobile_events`, F-058 |

---

## 4. News ingest

`ingestion_stats_daily` (2026-09-25):

| Fonte | fetched | queued | duplicates | no_ticker | stale | parse_fail |
|---|---|---|---|---|---|---|
| alpaca_benzinga | 745 | 470 | 3.882 | 0 | 187 | 0 |
| gdelt_gkg | 1.505 | 10 | 1 | 1.494 | 0 | 0 |

`news_log` (righe persistite il 25/09): Benzinga WS 164 (101 hash distinti; 13:33–19:50), Benzinga REST 4 (17:15), GDELT 10 (14:22–19:47). Nessun timestamp futuro (`published_at > fetched_at`: 0); nessun campo `body` mancante; lag mediano Benzinga ingest 295 s, massimo 7.092 s. 87 righe con entità HTML residue (`&#39;`, `&amp;`: F-076 già aperto), 30 con caratteri non-ASCII nel titolo.

`news_queue_drops`: `duplicate_id` 3.882 (Benzinga; il rapporto duplicates > fetched è F-007), `no_ticker` 1.494 (GDELT), `stale` 187, `not_tradable` 161, `duplicate_content` 1.

Duplicati: 22 `content_hash` ripetuti in `news_log` (stesso articolo su più ticker, atteso). Nessun segnale duplicato per `(news_log_id, symbol)`. 113 URL → 178 righe; 22 URL multi-ticker generano 87 righe (48,9%): F-012.

Tabella per ticker (top per attività): segnali per 56 simboli; massimi score |s| ≥ 0,30: COST (finbert −0,55; ensemble +0,33; single −0,30), NKE (−0,54, −0,41), XOM (−0,48 single), CMCSA (−0,47), NOW (+0,45 single), AMD (+0,39), WDC (+0,34), HOOD (+0,32), ARM (+0,32), MSFT (+0,31).

Top news per impatto sul segnale: ARM «Arm Stock Rises on Possible Continued Momentum From Meta's Muse AI Launch» (+0,323, BUY 14:07, pubblicata 12:14: notizia già nel gap, F-030); MSFT «Shares Jump 3.15%… Stifel Buy Upgrade» (GDELT, +0,310, BUY); HOOD «XRP, Solana Surge 22% After Clarity Act Failure…» (+0,323, BUY); «9 Of 11 Sectors Fall In Friday Trading» (16 ticker, fan-out).

Problemi trovati: copertura news zero su 40/96 simboli (F-001), ingest in blackout DNS (F-074), coda notturna scartata stale (F-069), bot token in chiaro nei log (F-018). Confidenza dell'analisi: **alta** per i conteggi (DB), media per la copertura temporale (nessun timeline per-minuto verificato fra provider).

## 5. Performance modelli LLM

`llm_responses` 25/09 (172 righe per modello; righe `eligible` = 47 per modello):

| Modello | Richieste | Eligible | polarity media | confidence media | score medio (pol×conf) | min / max |
|---|---|---|---|---|---|---|
| glm-5.3:cloud | 172 | 47 | +0,057 | 0,321 | +0,025 | −0,45 / +0,39 |
| gpt-oss:20b-cloud | 172 | 47 | +0,013 | 0,460 | +0,011 | −0,64 / +0,45 |

Errori di trasporto nei log (`ensemble model failed`): gpt-oss 18 timeout; glm-5.3 4 timeout + 2 HTTP 500 + 1 disconnect. La latenza per chiamata non è persistita (F-086): **non verificabile**.

Esiti dei 178 segnali: 101 `ensemble:glm-5.3+gpt-oss` (score medio |s| 0,04), 68 `single:gpt-oss` e 6 `single:glm-5.3` (lettura singola dopo filtro di eleggibilità, entrambe le risposte presenti: `fallback_used=true` ma **non** FinBERT), 3 `finbert` (COST −0,82/0,67, SPY 0,00/0,76, META +0,36/0,30; `finbert_fallback_events`, `body_chars` > 0: FinBERT ha visto parte del corpo, 129 caratteri medi). Il contatore del task `finbert_fallbacks` somma 77: F-078. Tasso FinBERT reale: 3/178 = 1,7%; tasso letture non-ensemble: 77/178 = 43,3%.

Disaccordo: `ensemble_std` max 0,283 (nessun caso > 0,30); 5 segni opposti su 101 ensemble, 12 su 68 single con 2 risposte: nessun gate di varianza (F-054/F-037); nessun ordine dipende da un caso di disaccordo. 54/101 segnali ensemble senza alcuna risposta eligible=true (F-010).

Verifiche funzionali: output LLM validato con enum/normalizzazione solo parziale (F-055); LLM chiamati offline nei worker `inference`, mai nel trading loop (i cicli leggono `sentiment_signals`); la stessa news può generare più segnali solo per fan-out multi-ticker (F-012); confidence bassa riduce il peso (score = polarity × confidence). Rischio hallucination diretta in decisione: ARM/HOOD/MSFT/NVDA/COST sono ordini su segnali ensemble + gate 0,30; nessun evento inventato osservato oggi (F-091 non ricorre).

Dato ancora una volta: pesi ensemble effettivi 0,5/0,5 (101/101 riprodotti), 114 WARNING «Ignoring weights for inactive sentiment models: [glm-5.2]» (F-088).

## 6. Segnali finali per ticker (≥ gate 0,30 o con ordine/decisione)

| Ticker | Segnale | Modello | Decisione | Note |
|---|---|---|---|---|
| ARM | +0,323 (12671) → ×1,20 = 0,387 | ensemble | BUY 14:07 | poi +0,035 (14:49) → SELL 15:52 |
| HOOD | +0,323 (12706) | ensemble | BUY 14:22 | poi +0,021 (14:28) → SELL 16:07 |
| MSFT | +0,310 (12712) | ensemble | BUY 14:37 | poi +0,165 (16:43) → SELL 16:52 |
| NVDA | +0,265 ×1,20 = 0,318 (12789) | ensemble | BUY 16:52 | 12 SIGNAL_DUPLICATE_SKIP |
| COST | +0,326 (12811) | ensemble | BUY 17:52 | 8 SIGNAL_DUPLICATE_SKIP |
| AMD | +0,390 (12722) | ensemble | SKIP_PYRAMIDING | S1 a libro dal 14/07 |
| WDC | +0,338 (12753) | ensemble | SKIP_PYRAMIDING | residuo S4 0,3347 az. |
| MS | −0,159 (12705) | — | SKIP_STALE 18:22 | 4,1 h > 4 h |
| INTC/PANW | 0,000 (12802/12805, fan-out «Whale Alerts») | — | SKIP_THRESHOLD ×11 | S4 detenute, F-089 |

Decisioni totali: OBSERVE_LATE_ENTRY 1.795, SKIP_THRESHOLD 695, SHADOW_LATE_ENTRY 332, SKIP_FALLBACK 31, BUY 5, SELL 3, SKIP_PYRAMIDING 2, SKIP_STALE 1. Nota: `execution_decisions.score` (0,020) è il peso target, non il punteggio: il punteggio è in `signal_score` (F-073); il controllo «score < 0,05 con ordine» non è applicabile alla colonna `score`, mentre i `signal_score` dei BUY sono 0,265–0,326, tutti ≥ gate.

## 7. Ordini generati/eseguiti (paper Alpaca)

| Decisione (tick) | Ticker | Azione | Qty | Prezzo fill | Stato | Segnale | Rationale / risk check |
|---|---|---|---|---|---|---|---|
| 45669 · 14:07 | ARM | BUY | 4,6203 | 321,95 | filled 14:07:15 | 12671 | S4, peso 2,0%, gate 0,387; stop 4 az. creato 14:22 |
| 45784 · 14:22 | HOOD | BUY | 12,5315 | 118,6777 | filled 14:22:17 | 12706 | S4, peso 2,0%; stop 12 az. creato 14:37 |
| 45896 · 14:37 | MSFT | BUY | 2,8959 | 514,00 | filled 14:37:13 | 12712 | S4, peso 2,0%; stop 2 az. creato 14:52 |
| 46491 · 15:52 | ARM | SELL | 4,6203 | 315,81 | filled 15:52:13 | NULL | `below_entry_gate` (+0,035, età 1,0 h) |
| 46612 · 16:07 | HOOD | SELL | 12,5315 | 118,81 | filled 16:07:12 | NULL | `below_entry_gate` (+0,021, età 1,6 h) |
| 46979 · 16:52 | NVDA | BUY | 6,6064 | 224,8421 | filled 16:52:13 | 12789 | S4, peso 2,0%; stop 6 az. creato 17:07 |
| 46980 · 16:52 | MSFT | SELL | 2,8959 | 517,9965 | filled 16:52:13 | NULL | `below_entry_gate` (+0,165, età 0,1 h) |
| 47465 · 17:52 | COST | BUY | 1,6123 | 921,452 | filled 17:52:09 | 12811 | S4, peso 2,0%; stop 1 az. stesso ciclo |

Stop protettivi (parte intera) cancellati dopo le uscite (ARM 4, HOOD 12, MSFT 2): corretto. Nessun ordine duplicato (idempotenza: `SIGNAL_DUPLICATE_SKIP` su NVDA ×12 e COST ×8; nessun ordine identico nello stesso minuto). `decision_price` NULL su 8/8 ordini (F-015: slippage non misurabile). `portfolio_cycles.orders_count` somma 73 contro 8 ordini inviati (F-014). Paper/live: coerente (`paper`).

## 8. PnL / rendimento

| Voce | Valore | Fonte / note |
|---|---|---|
| NAV 25/09 (prev close → 20:00) | 109.953,87 → 109.984,26 = **+30,39 $ (+0,028%)** | `portfolio_monitor_snapshots` |
| SPY (close-to-close) | **+0,54%** | dossier `mercato.rendimenti` |
| Realizzato S4 netto (3 round-trip) | **−17,08 $** (lordo −15,14) | ARM −29,19 (t.1029), HOOD +0,84 (t.1030), MSFT +11,27 (t.1031) |
| Costi (cost_usd) | 0,82 / 0,82 / 0,30 / 0,30 / 0,82 | `trades`; slippage_est = cost_usd (F-015) |
| Aperte il 25/09 e ancora a libro | NVDA (t.1032), COST (t.1033) | usciranno il 28/09 (+27,98 e +4,74 netto); MTM EOD 25/09 +1,51 e +2,12 |
| Unrealized del libro (45 posizioni) | +1.785,24 $ | snapshot 20:00 |
| PnL da posizioni aperte prima del 25/09 | non scomponibile con certezza fra S1 e S4 senza il ledger per sleeve | mancano per-strategia verificati |

Il rendimento giornaliero del libro (+0,03%) non è il rendimento della strategia: S4 pesa ~2% del NAV per posizione. Non confondere con `/api/trades`, che dichiara +181,82 $ lordi sugli stessi tre trade (F-084).

## 9. Correttezza buy/sell

- **BUY**: 5/5 con segnale ensemble sopra il gate effettivo (0,30 su `soglia_gate_usata`; ×1,20 di `velocity` su ARM/HOOD/NVDA/COST), peso 2% = size tipica S4. Nessun BUY da fallback FinBERT né da segnale stale (SKIP_FALLBACK 31 e SKIP_STALE 1 hanno funzionato). **Eccezione di correttezza (F-088):** ai pesi dichiarati il BUY MSFT (0,310 → 0,299) non sarebbe partito.
- **SELL**: 3/3 per `below_entry_gate`, **osservato**. Funzionalmente coerente con la regola, ma la regola è innescata dall'ultimo segnale per simbolo, che è un articolo fan-out positivo e non una riga contraria (F-023, F-012): ARM +0,035 da articolo su AMD, HOOD +0,021 da articolo su XRP, MSFT +0,165 da articolo su NVDA. Costo già registrato dall'alpha-miss (−23,26).
- **Stop-loss**: creati un ciclo dopo l'ingresso (15 minuti senza protezione, F-022); non attivati oggi.
- **Signal flip / max holding / rebalance band**: nessuna uscita per flip; i 3 SELL sono sotto 2 h di tenuta; nessuna banda di rebalance S4.
- **Pyramiding**: nessun BUY ripetuto; AMD/WDC correttamente bloccati (P0-05), con l'effetto F-031.
- **Ordini contrari/ravvicinati**: nessun roundtrip < 30 min; il minimo è 1,75 h (ARM, HOOD). Nessun BUY/SELL contrario sullo stesso simbolo nello stesso ciclo (16:52 NVDA BUY e MSFT SELL sono simboli diversi).
- **SELL con sentiment positivo (bug A5)**: i tre SELL hanno segnale positivo sotto gate (+0,035/+0,021/+0,165) e `signal_id` NULL (F-011): è la conseguenza di F-023, non un SELL con sentiment positivo oltre il gate.
- **Idempotenza Celery**: nessun ordine doppio; deploy 08:20/12:05 fuori seduta, con 1 job perso (SIGTERM).
- **Riconciliazione**: ordini ↔ trades ↔ posizioni OK (8 ordini filled, 5 trade, `reconcile-positions` 21:35 `anomalies: 0`); eccezione: WDC trade 373 `qty_open 0` mentre il broker ha 0,3347 az. (F-048).
- **Circuit breaker**: nessuno attivo; ensemble raggiungibile tutta la seduta.
- **NO-ORDER (decisione creata ma ordine non generato)**: nessuno oltre ai 2 SKIP_PYRAMIDING e ai SKIP_*, attesi.

---

## 10. Anomalie trovate

Gli id DAY-001…028 sono quelli già presenti nel ledger. «Costo» = quanto scritto in `findings.json` per quell'occorrenza (null = non stimato o già contato dall'alpha-miss).

### [DAY-001] Uscita S4 disarmata sulle posizioni S4 dentro il target congelato di S1
* Tipo: Bug · Area: Signal/Orders · Finding: **F-089** · Costo: 3,57 $ (attribuita, solo MU)
* Evidenza: tabella `execution_decisions`/`trades` (t.1014 MU, t.1007 INTC, t.1001 PANW); MU riceve 12727 +0,055 alle 14:58 e resta a libro senza «Exit hysteresis»; INTC/PANW ricevono 12802/12805 a 0,000 alle 17:35 e restano 11 cicli SKIP_THRESHOLD. ARM/HOOD/MSFT (fuori target) escono alla stessa regola.
* Descrizione: l'uscita per regola S4 dipende dall'appartenenza al target S1, non dalla regola dichiarata.
* Impatto: l'evidenza S4 del periodo di osservazione misura posizioni che non escono. · Severità: High · Confidenza: High
* Azione: vedi ticket T1. · Monitor: contare per giorno le posizioni S4 con segnale sotto gate senza SELL.

### [DAY-002] Score a pesi 0,5/0,5 invece dei pesi dichiarati
* Tipo: Bug · Area: LLM/Signal · Finding: **F-088** · Costo: −11,27 $ (attribuita, il difetto oggi ha reso)
* Evidenza: `sentiment_signals` 101/101 ensemble riprodotti a 0,5/0,5; 114 WARNING «Ignoring weights for inactive sentiment models: ['glm-5.2:cloud']» in `worker-inference-2026-09-25.log`. Ai pesi dichiarati MSFT 12712 0,310 → 0,299 (0,285 a 0,7/0,3): il BUY MSFT 14:37 non sarebbe partito.
* Impatto: la serie di score non è quella dichiarata; ogni giorno osservato è a pesi diversi. · Severità: High · Confidenza: High
* Azione: T2. · Monitor: asserire che i pesi persistiti coincidano con quelli applicati.

### [DAY-003] `/api/trades` espone una riga per ordine broker, P&L inverso
* Tipo: Bug · Area: PnL/Frontend · Finding: **F-084** · Costo: null
* Evidenza: `/api/trades` ARM entry 288,54 gross +126,00 vs ledger t.1029 321,95 −28,37; HOOD +42,11 vs +1,66; MSFT +13,72 vs +11,57; somma +181,82 contro −15,14.
* Impatto: segno inverso su ARM; chi legge l'API vede un realizzato 12× quello vero. · Severità: High · Confidenza: High
* Azione: T3. · Monitor: riconciliare somma `/api/trades` con `trades.net_pnl`.

### [DAY-004] Perdita di rete in seduta letta come «market closed»
* Tipo: Bug · Area: Ops/News · Finding: **F-074** · Costo: null
* Evidenza: log `worker` 16:54–17:03 (DNS) e 13:16–13:29; 17:00:16 `run_alpaca_ingestion_worker` e GDELT → `succeeded {'skipped': True, 'reason': 'market_closed'}`; `mobile_events` `broker_stale`/`market_clock` 16:58:32. Articoli 16:55/17:01 recuperati dal REST delle 17:15 (~14 min di ritardo). Ciclo 17:07 regolare.
* Impatto: ritardo di ingest silenzioso; qui nessun ordine perso. · Severità: Medium · Confidenza: High
* Azione: T4. · Monitor: fallire (non skippare) quando il clock non è raggiungibile.

### [DAY-005] Regime da un solo LLM per `410 Gone`
* Tipo: Bug · Area: LLM · Finding: **F-017** · Costo: null
* Evidenza: `worker-inference` 07:00:56 e 13:36:34 «LLM-2 failed in regime detection: Ollama API error 410: Gone» (`REGIME_LLM_MODEL_2` default `qwen3.5:cloud`); poi «Regime detected: sideways (x0.7), disagreement=False» con r2=r1; task `succeeded`; nessun alert. Prima comparsa (assente il 24/09).
* Impatto: guardia di disaccordo disarmata; moltiplicatore ×0,7 da un solo modello. · Severità: Medium · Confidenza: High
* Azione: T5. · Monitor: alert se LLM-2 fallisce o r2 non indipendente.

### [DAY-006] Ingresso a notizia già prezzata (ARM, MSFT, COST)
* Tipo: Anomalia · Area: Signal · Finding: **F-030** · Costo: 15,80 $ (misurata, trade 1029/1031; MTM per COST)
* Evidenza: ARM BUY 14:07 @321,95 su notizia pubblicata 12:14, `quota_nel_gap` 3,06, `entry_percentile` 0,77: net −29,19. MSFT 14:37 (GDELT «Shares Jump 3.15%», quota 0,87, +11,27); COST 17:52 (quota 0,96, percentile 0,91, MTM +2,12). Costo 29,19 − 11,27 − 2,12 = 15,80.
* Impatto: ricorrente (26 occorrenze). · Severità: Medium · Confidenza: Medium
* Azione: nessuna taratura (congelata). · Monitor: già nel dossier.

### [DAY-007] Ultimo segnale fan-out positivo sovrascrive l'ingresso
* Tipo: Bug · Area: Signal · Finding: **F-023** · Costo: null (già −23,26 in alpha-miss)
* Evidenza: SELL ARM 15:52 (+0,035, BofA su AMD), HOOD 16:07 (+0,021, «Forget Bitcoin, XRP»), MSFT 16:52 (+0,165, SemiAnalysis su NVDA).
* Impatto: 3/3 uscite S4 del giorno da un segnale non specifico del titolo. · Severità: High · Confidenza: High
* Azione: T6. · Monitor: contare le uscite `below_entry_gate` con segnale fan-out.

### [DAY-008] Righe scorate da articoli fan-out multi-ticker
* Tipo: Anomalia · Area: News/Signal · Finding: **F-012** · Costo: null
* Evidenza: 113 URL → 178 righe; 22 URL multi-ticker → 87 righe (48,9%); massimo 16 («9 Of 11 Sectors Fall In Friday Trading», XOM −0,48 e XLE −0,30 single). Le 3 uscite S4 e lo 0,000 INTC/PANW («Whale Alerts», 5 ticker) nascono da righe fan-out; TSM +0,28 da «What Is Going on With Qualcomm Stock».
* Severità: High · Confidenza: High · Azione: come T6.

### [DAY-009] Anti-pyramiding blocca ingressi S4 su simboli detenuti da S1
* Tipo: Anomalia · Area: Orders · Finding: **F-031** · Costo: −5,43 $ (congetturale, il blocco ha evitato una perdita su AMD)
* Evidenza: AMD 12722 +0,390 SKIP_PYRAMIDING 21 intenti 14:52–19:52 (S1 a libro dal 14/07); WDC 12753 +0,338 18 intenti (residuo S4 0,3347 az.); 1 riga `execution_decisions` ciascuno.
* Severità: Low · Confidenza: Medium.

### [DAY-010] Stop protettivi parziali e in ritardo di un ciclo
* Tipo: Rischio · Area: Risk · Finding: **F-022** · Costo: null
* Evidenza: ARM 4/4,620 (86,6%), HOOD 12/12,53, MSFT 2/2,896 (69,1%), NVDA 6/6,606, COST 1/1,612 (62,0%); creati un ciclo dopo l'ingresso (stesso ciclo su COST). #161: 11/44 posizioni sub-one-share senza stop; AMAT −18/−19%, WDC −17%.
* Severità: Medium · Confidenza: High.

### [DAY-011] Uscita parziale non riscritta su `trades` (WDC)
* Tipo: Bug · Area: PnL/Orders · Finding: **F-048** · Costo: null
* Evidenza: dossier `snapshot_apertura` WDC (t.373) `qty_open 0`, missingness `exit_fill_qty_exceeds_trade_qty`, broker 0,3347 az.; P&L c2c +2,18 $ omesso; `reconcile-positions` 21:35 `partially_wound_down_coheld: 2, anomalies: 0`.
* Severità: Medium · Confidenza: High.

### [DAY-012] SELL senza `signal_id`
* Tipo: Bug · Area: Orders · Finding: **F-011** · Costo: null
* Evidenza: 3/3 SELL (46491, 46612, 46980) con `signal_id` NULL; dossier `decision_signal_id_coverage.regressions=['SELL']`; BUY 5/5 pieno.
* Severità: Medium · Confidenza: High.

### [DAY-013] Qualità di esecuzione non misurata
* Tipo: Bug · Area: Orders · Finding: **F-015** · Costo: null
* Evidenza: `decision_price` NULL su 8/8 decisioni d'ordine; `trades.slippage_est` = `cost_usd` su t.1029–1033 (0,82/0,82/0,30/0,30/0,82).
* Severità: Medium · Confidenza: High.

### [DAY-014] Telemetria del ciclo fuorviante
* Tipo: Bug · Area: Ops · Finding: **F-014** · Costo: null
* Evidenza: `portfolio_cycles.orders_count` somma 73 su 24 cicli contro 8 ordini di decisione inviati (+5 stop); ciclo 16:52 `orders_before=4 orders_after=4` con 2 ordini inviati.
* Severità: Low · Confidenza: High.

### [DAY-015] `finbert_fallbacks` conta anche letture a modello singolo
* Tipo: Bug · Area: LLM/Ops · Finding: **F-078** · Costo: null
* Evidenza: esiti dei task sentiment sommano `finbert_fallbacks` 77; `finbert_fallback_events` ha 3 righe (COST, SPY, META); 68 single gpt-oss + 6 single glm + 3 FinBERT.
* Severità: Medium · Confidenza: High.

### [DAY-016] Disaccordo fra modelli senza gate di varianza
* Tipo: Rischio · Area: LLM · Finding: **F-054** · Costo: null
* Evidenza: 5 segni opposti su 101 ensemble, 12 su 68 single gpt-oss a due risposte; `ensemble_std` max 0,283. Nessun ordine dipende da un caso di disaccordo.
* Severità: Low · Confidenza: High.

### [DAY-017] `llm_responses.eligible` e floor 0 non propagati
* Tipo: Bug · Area: LLM · Finding: **F-010** · Costo: null
* Evidenza: 54/101 segnali ensemble senza alcuna risposta `eligible=true` (47 con 2/2, 0 con 1/2); glm-5.3 sotto floor 122/172.
* Severità: Medium · Confidenza: High.

### [DAY-018] Decay monitor CRITICAL non per strategia
* Tipo: Bug · Area: Risk · Finding: **F-004** · Costo: null
* Evidenza: 21:00:00 DECAY CRITICAL [S1] IC 0,035→−0,032, [S2] 0,042→−0,032, [S4] 0,028→−0,032; Sharpe −7,45 identico su S1/S2/S4 (metriche pipeline-globali).
* Severità: Medium · Confidenza: High.

### [DAY-019] Alert CRITICAL del decay monitor senza canale
* Tipo: Bug · Area: Ops · Finding: **F-062** · Costo: null
* Evidenza: le 8 righe DECAY CRITICAL delle 21:00 restano nel log; nessuna riga in `mobile_events`.
* Severità: Medium · Confidenza: High.

### [DAY-020] Telegram `400 Bad Request` non consegnato
* Tipo: Anomalia · Area: Ops · Finding: **F-005** · Costo: null
* Evidenza: TelegramNotifier «Failed to send alert: 400 Bad Request» 14:07:15 e 14:22:15. Inoltre ~93 errori di polling Telegram (DNS/rete) in `worker-inference`.
* Severità: Low · Confidenza: High.

### [DAY-021] Bot token Telegram in chiaro nei log
* Tipo: Rischio · Area: Ops/Sicurezza · Finding: **F-018** · Costo: null
* Evidenza: URL `api.telegram.org/bot<token>` in 17.179 righe dei log worker/worker-inference; `api_key=` (FRED) in 4 righe.
* Severità: High · Confidenza: High.

### [DAY-022] Fetch del benchmark SPY fallisce senza alert
* Tipo: Anomalia · Area: Data · Finding: **F-016** · Costo: null
* Evidenza: «SPY benchmark fetch failed: subscription does not permit querying recent SIP data» ×95 (84 + 11 rete), nessun alert.
* Severità: Low · Confidenza: High.

### [DAY-023] `duplicates` > `fetched` nello stesso giorno
* Tipo: Anomalia · Area: News · Finding: **F-007** · Costo: null
* Evidenza: `ingestion_stats_daily` alpaca_benzinga fetched 745, queued 470, duplicates 3.882 (`news_queue_drops` `duplicate_id`: 2.551 rest + 1.331 ws).
* Severità: Low · Confidenza: High.

### [DAY-024] Coda notturna drenata e scartata come stale
* Tipo: Anomalia · Area: News · Finding: **F-069** · Costo: null
* Evidenza: 183–187 articoli WS `enqueued_off_session` scartati stale 13:33:11–13:38:08 (età mediana 6,9 h; media 10,4 h) + 30 (161 nella tabella aggregata) `not_tradable`; 84 dispatch `run_sentiment_worker` `market_closed` fuori seduta. 42 articoli pre-apertura scorati comunque all'apertura (ingest→segnale mediana 86 min).
* Severità: Low · Confidenza: High. (Il conteggio `not_tradable` oscilla fra 30 e 161 a seconda della definizione della finestra: dato riportato per quello che il DB contiene a oggi.)

### [DAY-025] Evaluator mobile chiude incidenti di cui non è proprietario
* Tipo: Bug · Area: Ops · Finding: **F-058** · Costo: null
* Evidenza: `coverage:held_no_news_loss` AMAT/CSCO/VALE e `portfolio_cycle_session_grid` aperti 22:50:00 e chiusi 22:50:01.
* Severità: Low · Confidenza: High.

### [DAY-026] PoolError psycopg2 nel teardown dell'API
* Tipo: Bug · Area: Ops · Finding: **F-081** · Costo: null
* Evidenza: `api-2026-09-25.log` `quality_metrics failed: trying to put unkeyed connection` → `Exception in ASGI application` (1 occorrenza).
* Severità: Low · Confidenza: High.

### [DAY-027] Copertura news bassa sulla watchlist e 3 posizioni cieche lato uscita
* Tipo: Anomalia · Area: News · Finding: **F-001** · Costo: null (4,97 già in alpha-miss)
* Evidenza: `watchlist_zero_news` 40/96, effective-timely 35/96; AMAT −18,32%, VALE −7,04%, CSCO −4,29% da ingresso, notional cieco 2.958,41 $.
* Severità: Medium · Confidenza: High.

### [DAY-028] Prima finestra di ciclo portfolio alle 14:07 (beat UTC fisso)
* Tipo: Anomalia · Area: Ops · Finding: **F-021** · Costo: null
* Evidenza: primo portfolio-cycle 14:07:00 (`portfolio_cycle_late` 13:30:01–14:08:01); ARM +0,323 (13:40:59) entra alle 14:07 invece che al ciclo 13:52; prezzo 13:52 non ricostruito.
* Severità: Low · Confidenza: Medium.

---

## 11. False positive o aree risultate corrette

- Nessun ordine fuori orario, duplicato o senza causa; nessun BUY da segnale stale o da FinBERT; SKIP_STALE (MS 4,1 h) e SKIP_FALLBACK (31) funzionano.
- Nessun timestamp futuro nelle news; nessun `NaN`/campo mancante; `news_log` ↔ `sentiment_signals` coerenti per `news_log_id`.
- Nessun segnale duplicato per (news, simbolo); nessun roundtrip < 30 min; nessun pyramiding.
- `SIGNAL_DUPLICATE_SKIP` ha impedito reinvii su NVDA/COST (idempotenza del gate).
- Ordini ↔ fill ↔ posizioni riconciliati; `reconcile-positions` 21:35 `anomalies: 0`.
- Il «fallback rate 43%» NON è Ollama giù: 74/77 sono letture a modello singolo dopo filtro di eleggibilità con entrambi i modelli presenti (F-078/F-010). FinBERT reale 1,7%.
- Le `trades.exit_time` di NVDA/COST cadono il 28/09 (uscite del giorno di borsa successivo), non anteriori all'ingresso: letto senza data sembrava un errore, non lo è.

## 12. Dati mancanti o non accessibili

- Latenza per chiamata LLM e esito per richiesta: non persistiti (F-086); solo errori di log.
- Slippage: `decision_price` NULL (F-015); prezzo del ciclo 13:52 per ARM non ricostruibile.
- PnL per strategia delle 45 posizioni pre-esistenti: serve ledger per sleeve: `SELECT strategy, sum(net_pnl) FROM trades WHERE exit_time::date='2026-09-25' GROUP BY 1` (le righe pre-patch hanno `stop_strategy` NULL, F-002).
- Commissioni: solo `cost_usd` stimato dal TradeCostCalculator, non quelle del broker.
- Rilevazione indipendente della finestra di indisponibilità dell'API Ollama: nessuna traccia di trasporto persistita (F-086); l'uptime è dedotto dagli errori di log.

## 13. Raccomandazioni immediate (solo correttezza, nessuna taratura)

1. Correggere F-088 (pesi effettivi vs dichiarati) e dichiarare nel charter la discontinuità della serie di score.
2. Correggere F-084 (`/api/trades`): nessuna decisione operativa deve leggerlo finché non riconcilia col ledger.
3. Dichiarare F-023/F-089/F-012 come difetti noti nella sintesi del 28/09: i P&L S4 del periodo non misurano la regola dichiarata.
4. Far fallire (non skippare) i job di ingest quando `/v2/clock` non è raggiungibile (F-074).
5. Ruotare il token Telegram e redigere i log httpx (F-018).

## 14. Test o monitor da aggiungere

- Test: i pesi persistiti coincidono con i pesi applicati nell'ensemble; la regola di uscita S4 si applica anche alle posizioni nel target S1.
- Monitor: `/api/trades` vs `trades.net_pnl` giornaliero; `signal_id` NULL su SELL; `decision_price` NULL su ordini; `LLM-2 failed in regime detection`; log `Ignoring weights for inactive sentiment models`; ingest `skipped` con clock irraggiungibile.

## 15. Ticket tecnici suggeriti

- **T1** — Uscita S4 sulle posizioni dentro il target congelato S1 (F-089).
- **T2** — Pesi d'ensemble dopo lo swap di modello: persistenza e applicazione (F-088).
- **T3** — `/api/trades`: riga per trade, non per ordine broker (F-084).
- **T4** — Job di ingest: `failed` e non `skipped` quando il clock è irraggiungibile (F-074).
- **T5** — Regime detection: alert e task `failed` se LLM-2 non risponde; aggiornare `REGIME_LLM_MODEL_2` (F-017).
- **T6** — Segnale per le uscite S4: usare l'ultimo segnale *specifico del titolo*, non l'ultimo fan-out (F-023/F-012).
- **T7** — Scrivere `signal_id` sulle SELL e `decision_price` su tutte le decisioni d'ordine (F-011/F-015).
- **T8** — Alert CRITICAL del decay monitor su un canale (F-062).

## 16. Stato sistema

- **Ollama**: raggiungibile per tutta la seduta; nessun blackout. Errori ensemble 29 (gpt-oss 18 timeout, glm-5.3 4 timeout + 2 HTTP 500 + 1 disconnect, più 2 `410 Gone` sul regime): cluster di timeout sparsi (10–15 UTC). Ore di downtime: **0** stimate; uptime non misurato (F-086).
- **FinBERT fallback rate**: 3/178 segnali = **1,7%** (reale, `finbert_fallback_events`); il contatore del task dichiara 77 (43,3%) perché include letture a modello singolo (F-078).
- **Letture non-ensemble**: 77/178 (43,3%): 68 single gpt-oss, 6 single glm-5.3, 3 FinBERT.
- **Worker restart events**: 2 ricreazioni fuori seduta (08:20 e 12:05: `worker`, `worker-inference`, `beat`), 1 job perso (8134, SIGTERM) e 4 messaggi unack ripristinati. Nessun restart in seduta.
- **Rete**: DNS/route perdite 13:16–13:29 e 16:54–17:03 (host); WS news con 71 errori di comunicazione e 3 riavvii di connessione.
- **Alert**: 11 `mobile_events` (5 critical, 6 warning); i CRITICAL del decay monitor e la perdita DNS dei job ingest non hanno alert propri (F-062, F-074).
