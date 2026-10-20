# Forensic daily report — 2026-10-07 (mercoledì)

Analisi read-only. Timezone operativo: UTC (`celery_app.py`); DST USA in vigore (EDT): RTH = 13:30–20:00 UTC; le finestre beat a UTC fisso restano la fonte di ambiguità (F-021). Fonti: DB `trading` (SELECT), API REST locale (risponde con la chiave fornita), `logs/containers/*-2026-10-07.log`, `docs/evidence/dossier/2026-10-07.json`, `market_daily.jsonl`.

## 1. Executive summary

- Pipeline end-to-end coerente: 269 righe `news_log` (159 articoli unici, fan-out medio 1,69) → 269 segnali → 5 ordini S4 filled (1 BUY HOOD, 3 SELL, + 1 stop protettivo HOOD cancellato). Tutto `paper` (`broker_environment=paper`), nessun ordine duplicato, nessun roundtrip < 30 min, nessun pyramiding.
- PnL realizzato S4 **−9,29 $** (SPCX −40,59, NOW +13,06, HOOD +18,25; costi 3,39 $). NAV 110.696,80 → 110.523,94 (−172,86 $, −0,156%) vs SPY −0,24%, QQQ −0,25%. S1 realizzato 0.
- Nessun outage Ollama in RTH. Fallback complessivo 117/269 segnali (43,5%): 113 single-model, 4 FinBERT (1,5%). Burst 429 "quota exhausted" alle 12:15 solo nel worker shadow pre-market.
- Un ciclo sentiment ha colpito il soft time limit (780 s) alle 15:49:53: buco di ~16 min nell'ensemble (15:33→15:50); nessun segnale duplicato dopo il recovery (269 segnali / 269 news).
- Decisione `BUY` SPCX (14:37) senza ordine: bloccata dal reversal cooldown ma persistita come BUY (F-006).
- Le uscite NOW (14:22) e HOOD (18:07) hanno `signal_id` NULL e nascono da un segnale più recente e debole che sovrascrive quello d'ingresso (HOOD: articolo generico "whale activity", score 0,000 conf 0,20) (F-023, F-011).
- Copertura news 46,9% (45/96 ticker), 141/269 righe TAG_UNCONFIRMED, 32 ticker a zero news; `duplicates` 5.089 > `fetched` 896 per alpaca_benzinga (F-007).
- Decay monitor: 6 CRITICAL alle 21:00, solo log (F-062). Token del bot Telegram in chiaro in 17.275 righe di log (F-018).
- Nessun difetto di correttezza nuovo; 15 finding esistenti riconfermati, 0 nuovi.

## 2. Verdict finale

**OK con warning** — esecuzione coerente con le regole S4 e riconciliata ordini/trade/posizioni; warning per BUY senza ordine persistito, uscite guidate da segnali deboli/sovrascrittura, fallback al 43,5%, copertura news 46,9%, alert assenti.

## 3. Timeline (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 03:00 | worker | daily performance report | worker log |
| 05–10 | worker-inference | 5 timeout Ollama off-hours (ore 05,06,07,09,10), 2 regime LLM-2 `410 Gone` | worker-inference log |
| 12:15 | worker-inference | shadow off-session: 16 fallimenti 429 "quota exhausted" (glm-5.3 + gpt-oss), 8 item scorati, FinBERT per CWEN/EQT/SPY | log |
| 13:30 | snapshot | NAV 110.375,76 $, 41 posizioni, gross 34,2%, cash 72.585 $ | portfolio_monitor_snapshots |
| 13:31 | ingest | primo articolo Benzinga WS; ensemble attivo | news_log / ensemble_cycle_health |
| 14:07 | portfolio-cycle | SELL SPCX (sentiment_reversal −0,390 < −0,35, stop cancellato, fill 167,55); NOW flaggato per exit hysteresis; SKIP_PYRAMIDING MRVL/SHEL | execution_decisions, log |
| 14:22 | portfolio-cycle | SELL NOW (`below_entry_gate`, segnale +0,255 delle 13:49, fill 137,97) | execution_decisions |
| 14:37 | portfolio-cycle | decisione BUY SPCX (+0,314×1,20) **senza ordine**: "Reversal cooldown: skipping BUY" | log riga 4149 |
| 15:26 | sentiment | segnale HOOD +0,308 (Barclays PT) | sentiment_signals 14503 |
| 15:37 | portfolio-cycle | BUY HOOD notional, fill 107,97 | orders |
| 15:49:53 | worker-inference | SoftTimeLimit 780 s su `run_sentiment_worker`; 3 item rimessi in coda | log 32965 |
| 15:52 | portfolio-cycle | stop protettivo HOOD (qty 14 su 14,505) piazzato 15 min dopo l'ingresso | orders |
| 17:45 | sentiment | segnale HOOD 0,000 conf 0,20 ("Whale Activity") sovrascrive il +0,308 | sentiment_signals 14589 |
| 18:07 | portfolio-cycle | SELL HOOD (`below_entry_gate`, stop cancellato, fill 109,29) | orders |
| 19:46 | ingest | ultima news | news_log |
| 20:00 | snapshot | NAV 110.523,94 $, 39 posizioni | portfolio_monitor_snapshots |
| 21:00 | decay monitor | 6 CRITICAL (S1/S2/S4), solo log | worker log |
| 22:45 | counterfactual | calcolo controfattuali 1h | execution_decisions |

Ciclo portfolio: 24 cicli (14:07–19:52, ogni 15 min), nessun ciclo mancante.

## 4. News ingest

| Fonte | Righe news_log | Hash distinti | Ticker | Finestra | Scartate | Timestamp futuri |
|---|---|---|---|---|---|---|
| alpaca_benzinga (247 ws, 2 rest) | 249 | 139 | 61 | 13:31–19:46 | 0 | 0 |
| gdelt_gkg (org_lookup) | 20 | 20 | 15 | 14:28–19:16 | 0 | 0 |

`ingestion_stats_daily`: benzinga fetched 896, queued 646, duplicates **5.089**, discarded_stale 197; gdelt fetched 2.088, queued 20, discarded_no_ticker 2.065 (resa 0,96%). Righe per ora: 13h 29, 14h 65, 15h 46, 16h 23, 17h 65, 18h 34, 19h 7. Rilevanza: ISSUER_SPECIFIC 128, TAG_UNCONFIRMED 141; fan-out extra 110 (max 17 ticker per articolo). Copertura effective-timely 45/96 (46,9%); 32 ticker a zero news. Entità HTML (`&#39;`, `&amp;`) ancora nei titoli (F-076). Nessuna sanitizzazione mancante evidente oltre a questa. Confidenza analisi: alta (DB), media sul sotto-conteggio duplicati (contatore incoerente).

## 5. Performance modelli LLM

| Modello | Risposte | Eleggibili | polarity media | \|pol\| media | conf media | score medio | \|score\|≥0,3 | Errori RTH |
|---|---|---|---|---|---|---|---|---|
| glm-5.3:cloud | 262 | 68 | 0,016 | 0,202 | 0,322 | 0,007 | 14 | 9 timeout (log intera giornata) |
| gpt-oss:20b-cloud | 263 | 68 | 0,009 | 0,208 | 0,471 | 0,011 | 34 | 11 timeout |

Segnali per tipo: ensemble 152 (conf 0,391, std 0,074), single gpt-oss 104, single glm 9, FinBERT 4. Disaccordo: 259 coppie, 18 con segno opposto, 3 con \|Δ\| ≥ 0,6, \|Δ\| medio 0,120. Std massime: ORCL 0,460, XLK 0,438, AMD 0,354 (non usate come gate: F-037). Latenza per modello non persistita (F-086). Fallback FinBERT (`finbert_fallback_events`): 3 "Ollama timeout" (polarity 0,89, articolo AMD fan-out su MRVL/NVDA/META, score 0,685), 1 "ensemble divergence" (0,14); body_chars 420–444 > 0, FinBERT ha visto parte del corpo. Il fallback 0,685 non ha prodotto ordini (esclusi dal ranking BUY, #108). Il calcolo `ensemble_std` mascherato (log F-054) compare per GOOGL/SPY/MSFT/META.

## 6. Segnali finali per ticker (top)

| Ticker | N | Score medio | Max | Min | Fallback |
|---|---|---|---|---|---|
| SPY | 29 | −0,087 | 0,100 | −0,360 | 16 |
| NVDA | 23 | 0,103 | 0,685 | −0,240 | 12 |
| MRVL | 20 | 0,249 | 0,685 | −0,303 | 2 |
| GOOGL | 15 | 0,000 | 0,085 | −0,120 | 9 |
| MSFT | 15 | 0,034 | 0,156 | −0,055 | 4 |
| SPCX | 11 | −0,042 | 0,314 | −0,390 | 2 |
| CAT | 6 | −0,262 | −0,025 | −0,426 | 2 |
| HOOD | 5 | 0,070 | 0,308 | −0,080 | 3 |

Superamenti del gate 0,30 non fallback: MRVL (0,439/0,405/0,448/…), SHEL 0,366/0,500, SPCX 0,314 — tutti su posizioni già a libro (SKIP_PYRAMIDING, 9 righe) o bloccati da cooldown; HOOD 0,308 → BUY. SPCX −0,390 → SELL.

Decisioni 07/10: OBSERVE_LATE_ENTRY 1.747, SKIP_THRESHOLD 706, SHADOW_LATE_ENTRY 335, SKIP_FALLBACK 42 (1 sopra 0,30: XLK −0,492), SKIP_PYRAMIDING 9, SELL 3, BUY 2, SKIP_REVERSAL_OWNER 1 (CAT −0,426, posizione S1).

## 7. Ordini

| Ora | Strategia | Ticker | Azione | Qty | Fill | Stato | Motivo / segnale | Anomalie |
|---|---|---|---|---|---|---|---|---|
| 14:07 | S4 | SPCX | SELL | 9,1623 | 167,55 | filled | sentiment_reversal, sig 14416 (−0,390) | order.decision_id punta alla decisione d'ingresso, non al SELL 65366 |
| 14:22 | S4 | NOW | SELL | 11,5098 | 137,97 | filled | below_entry_gate, segnale +0,255 (13:49) | decisione 65393 con signal_id NULL |
| 14:37 | S4 | SPCX | BUY (decisione) | — | — | **nessun ordine** | cooldown reversal | F-006 |
| 15:37 | S4 | HOOD | BUY | 14,5053 (notional) | 107,97 | filled | sig 14503 (+0,308), peso 2,0% | ingresso tardivo |
| 15:52 | S4 | HOOD | SELL stop 14 | 14 | — | canceled 18:07 | stop protettivo | copre 96,5%, piazzato +15 min |
| 18:07 | S4 | HOOD | SELL | 14,5053 | 109,29 | filled | below_entry_gate, sig 14589 (0,000) | signal_id NULL |

Tutti gli ordini in RTH, nessun ordine fuori orario, nessun ordine identico nello stesso minuto, nessun ordine senza decisione.

## 8. PnL / rendimento

| Voce | Valore |
|---|---|
| Realizzato S4 (3 trade) | −9,29 $ (SPCX −40,59 id 1056; NOW +13,06 id 1057; HOOD +18,25 id 1058) |
| Realizzato S1 | 0,00 $ |
| Da posizioni aperte prima del 07/10 | SPCX −40,59, NOW +13,06 = −27,53 $ |
| Da posizioni aperte il 07/10 | HOOD +18,25 $ |
| Costi (cost_usd) | 3,39 $ (già inclusi nel net) |
| NAV 10-06 20:00 → 10-07 20:00 | 110.696,80 → 110.523,94 = −172,86 $ (−0,156%) |
| Variazione implicita non realizzata/mark | ≈ −163,6 $ (derivata) |
| SPY / QQQ | −0,24% / −0,25% |

Non calcolabile da DB senza altre query: PnL non realizzato per ticker (serve prezzo di chiusura 10-06 per le 39 posizioni, es. barre Alpaca daily + `positions`), slippage (trades.slippage_est è copia di cost_usd, F-015). Nota: `previous_close_equity` dello snapshot (110.693,28) differisce di 3,52 $ dall'ultimo NAV del 06/10 (110.696,80): differenza immateriale, non indagata.

## 9. Correttezza buy/sell

- BUY: HOOD rispetta gate 0,30, peso 2%, anti-pyramiding (MRVL, SHEL correttamente saltati). Ingresso con quota nel gap 1,43 (movimento già avvenuto, F-030).
- SELL: SPCX per reversal (regola #182(a) rispettata: posizione S4); CAT correttamente non chiuso (posizione S1, SKIP_REVERSAL_OWNER). NOW e HOOD chiusi per `below_entry_gate`: l'uscita è causata da un segnale più recente che scavalca quello d'ingresso (F-023), con SELL su sentiment ≥ 0 (NOW +0,255, HOOD 0,000): non è il bug A5 ma l'asimmetria di rigore F-059/F-013.
- Nessun roundtrip < 30 min; nessun BUY ripetuto; nessun ordine contrario ravvicinato (SPCX SELL 14:07 e BUY 14:37 bloccato dal cooldown, come progettato).
- Circuit breaker/regime: regime_mult 0,7 su tutte le decisioni; nessun breaker attivo.
- Paper/live coerente. Retry Celery: nessuna duplicazione (269 news / 269 segnali; SIGNAL_DUPLICATE_SKIP HOOD 15:52–17:37 funziona).
- Reconciliation: 5 ordini ↔ 3 trade chiusi ↔ posizioni 41→39 (HOOD +1 −1, SPCX −1, NOW −1); coerente con gli snapshot (40 dopo 15:40, 39 dopo 18:10).
- `exit_mechanism`: le righe 07/10 usano il testo del motivo (`below_entry_gate`, `sentiment_reversal`), osservato post-fix #184; nessuna stima per età.

## 10. Anomalie

### [DAY-001] BUY SPCX persistito senza ordine (reversal cooldown)

* Tipo: Anomalia
* Area: Orders
* Evidenza:
  * file/log/tabella: execution_decisions id 65507; worker log riga 4149
  * timestamp: 2026-10-07 14:37:01Z
  * snippet/query: `Reversal cooldown: skipping BUY for SPCX — force-sold on sentiment reversal`; decisione `BUY`, `order_id` NULL, reason = motivazione d'acquisto
* Descrizione: Il guard blocca l'ordine ma la decisione resta etichettata BUY (F-006).
* Impatto: BUY non distinguibile da un fallimento di submission; falsa il conteggio decisioni→ordini.
* Severità: Medium
* Confidenza: High
* Azione consigliata: persistere un decision code dedicato per i guard bloccanti.
* Test/monitor consigliato: invariante `decision IN (BUY,SELL) ⇒ order_id NOT NULL` per i cicli di giornata.

### [DAY-002] Uscite guidate da un segnale più recente e debole (HOOD, NOW)

* Tipo: Anomalia
* Area: Signal
* Evidenza:
  * file/log/tabella: execution_decisions 65393, 67178; sentiment_signals 14589, 14401
  * timestamp: 14:22Z, 18:07Z
  * snippet/query: HOOD `score=+0.000`, `age=0.4h`, segnale 17:45 "Whale Activity" conf 0,20 sovrascrive 14503 (+0,308, 15:26); NOW +0,255 (13:49) sovrascrive 14337 (+0,340)
* Descrizione: S4 usa solo il segnale più recente per simbolo (F-023); un articolo generico a bassa confidenza forza l'uscita (F-059). Drift post-uscita: HOOD +3,22 $ (perso), NOW −1,15 $ (evitato).
* Impatto: ≈ 2,07 $ netti; ricorrente.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna taratura in freeze; registrare l'occorrenza.
* Test/monitor consigliato: contare uscite con confidenza < 0,3 del segnale causante.

### [DAY-003] decisioni SELL senza signal_id e ordine collegato alla decisione d'ingresso

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: execution_decisions 65393, 67178; /api/orders (decision_id 64601, 64602, 65980)
  * timestamp: 14:07–18:07Z
  * snippet/query: dossier `decision_signal_id_coverage`: SELL 1/3 con signal_id; ordine SELL HOOD `decision_id=65980` = decisione BUY
* Descrizione: la catena segnale→decisione→ordine di uscita non è ricostruibile (F-011).
* Impatto: audit delle uscite impossibile senza log.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket di correttezza (propagare signal_id/decision_id del SELL).
* Test/monitor consigliato: copertura signal_id = 100% per SELL.

### [DAY-004] Fallback 43,5% e FinBERT fuori dall'inviluppo dei modelli

* Tipo: Rischio
* Area: LLM
* Evidenza:
  * file/log/tabella: sentiment_signals; finbert_fallback_events; ensemble_cycle_health
  * timestamp: intera RTH
  * snippet/query: 117/269 `fallback_used`; 3 FinBERT "Ollama timeout" polarity 0,89 su articolo AMD fan-out (score 0,685 su MRVL/NVDA/META)
* Descrizione: nessun outage, ma la maggior parte dei fallback sono single-model per timeout di uno dei due; FinBERT emette verdetti molto più forti dei modelli sostituiti (F-087).
* Impatto: nessun ordine causato (esclusi dal ranking, SKIP_FALLBACK); contamina IC e ensemble stat.
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: alert fallback > 50% per ora.

### [DAY-005] Soft time limit sentiment e 429 shadow mal etichettati

* Tipo: Anomalia
* Area: Ops
* Evidenza:
  * file/log/tabella: worker-inference log righe 32965–33012, 26727+
  * timestamp: 15:49:53Z; 12:15Z
  * snippet/query: `Soft time limit (780s) exceeded`; `Recovering 3 stuck items`; "All ensemble models timed out for CWEN" con errore reale 429
* Descrizione: buco ensemble 15:33:45→15:50:04 (~16 min); 3 item recuperati senza duplicati. Il fallimento 429 è etichettato "timed out" (F-086).
* Impatto: ritardo scoring 16 min su RTH; causa non tracciata.
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare (F-072, F-086).
* Test/monitor consigliato: alert su SoftTimeLimit e su 429.

### [DAY-006] HOOD: stop protettivo tardivo e parziale

* Tipo: Rischio
* Area: Risk
* Evidenza:
  * file/log/tabella: /api/orders `a611ecda…` (qty 14, submitted 15:52:07)
  * timestamp: 15:37 ingresso, 15:52 stop
* Descrizione: 15 min senza stop; copertura 96,5% (F-022).
* Impatto: esposizione non protetta per un ciclo; nessun evento di prezzo avverso.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: tempo ingresso→stop < 1 ciclo.

### [DAY-007] Copertura e qualità ingest (F-001, F-007, F-012)

* Tipo: Anomalia
* Area: News
* Evidenza:
  * file/log/tabella: ingestion_stats_daily, dossier `copertura_articoli`
  * snippet/query: duplicates 5.089 > fetched 896; copertura 45/96; TAG_UNCONFIRMED 141/269; 32 ticker a zero news
* Descrizione: contatore duplicates incoerente; fan-out 1,69 righe/articolo; GDELT resa 0,96%.
* Impatto: metriche di ingest non interpretabili; copertura bassa.
* Severità: Medium
* Confidenza: High
* Azione consigliata: registrare.
* Test/monitor consigliato: invariante duplicates ≤ fetched.

### [DAY-008] Alert CRITICAL del decay monitor senza canale; token Telegram nei log (F-062, F-018)

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: worker log 21:00; worker-inference log (17.275 righe httpx), worker (3)
  * snippet/query: `DECAY CRITICAL [S4]: Sharpe below 50% of baseline: -3.25 vs 0.80`
* Descrizione: 6 CRITICAL solo nel log; il token del bot compare negli URL loggati (non riportato qui). Un solo `sendMessage` 400 Bad Request nel worker.
* Impatto: alert non recapitati; credenziale esposta nei log.
* Severità: High (token), Medium (decay)
* Confidenza: High
* Azione consigliata: ruotare il token e silenziare il logger httpx; canale per CRITICAL.
* Test/monitor consigliato: grep CI per `bot[0-9]+:` nei log.

### [DAY-009] Entità HTML nei titoli

* Tipo: Bug
* Area: News
* Evidenza: titoli news_log con `&#39;`, `&amp;` (es. segnali 14526, 14543)
* Descrizione: sanitizer non decodifica le entità (F-076).
* Impatto: testo al modello alterato.
* Severità: Low
* Confidenza: High
* Azione consigliata: registrare (fix già esente da freeze).
* Test/monitor consigliato: test su `&#39;`.

### [DAY-010] Ingresso tardivo HOOD

* Tipo: Anomalia
* Area: Signal
* Evidenza: dossier `ingressi` HOOD: `quota_nel_gap` 1,43, `quota_movimento_precedente_al_segnale` −0,44
* Descrizione: notizia pubblicata a movimento avvenuto (F-030). Trade chiuso +18,25 $.
* Impatto: non stimabile.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: registrare.
* Test/monitor consigliato: già coperto da #512.

### [DAY-011] Varianza d'ensemble mai gate

* Tipo: Rischio
* Area: LLM
* Evidenza: ORCL std 0,460 (id 14526), XLK 0,438 (14495), score −0,24/−0,49 senza effetto
* Descrizione: nessun gate su `ensemble_std` (F-037); fallback XLK escluso solo perché single-model.
* Impatto: nessun ordine causato oggi.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: registrare.
* Test/monitor consigliato: contare segnali ≥ 0,30 con std ≥ 0,3.

## 11. Aree corrette

- Nessun ordine duplicato, fuori orario, senza decisione o senza risk context; nessun BUY ripetuto; nessun roundtrip < 30 min.
- Anti-pyramiding (9 SKIP) e SKIP_REVERSAL_OWNER (CAT S1) hanno funzionato; cooldown reversal ha evitato il re-buy di SPCX.
- SIGNAL_DUPLICATE_SKIP ha impedito il rientro HOOD sullo stesso segnale. Nessun timestamp futuro, nessun segnale senza news.
- Riconciliazione trades/ordini/posizioni coerente; snapshot ogni 5 min senza buchi; 24/24 cicli portfolio.

## 12. Dati mancanti

- PnL non realizzato per ticker (serve close 10-06 per ogni posizione: barre Alpaca daily).
- Latenza LLM per modello e uptime Ollama non persistiti (F-086); stima solo da warning.
- Worker restart: nessun evento di startup nei log del giorno (nessun restart osservato, non una prova).
- `news_queue_census` ha schema diverso da quello assunto: non interrogato.
- Slippage: prezzo atteso non persistito (F-015).

## 13. Raccomandazioni immediate

1. Ruotare il bot token Telegram e disabilitare il log httpx a INFO (F-018).
2. Persistere un decision code per i BUY/SELL bloccati dai guard (F-006).
3. Propagare signal_id/decision_id sulle SELL (F-011).
4. Nessuna taratura (freeze fino al 2026-09-28 scaduto: confermare nel charter lo stato corrente).

## 14. Test / monitor da aggiungere

- Invariante `BUY/SELL ⇒ order_id`.
- Alert su SoftTimeLimit, 429 Ollama, fallback > 50%/ora.
- `duplicates ≤ fetched` in `ingestion_stats_daily`.
- Scansione log per token.

## 15. Ticket suggeriti

- Correttezza: decision code per guard bloccanti (F-006).
- Correttezza: propagazione signal_id su SELL e ordini di uscita (F-011).
- Ops: rotazione token + redazione log (F-018).
- Ops: canale alert per CRITICAL del decay monitor (F-062).

## 16. Stato sistema

- Ollama: up in RTH (nessun downtime); 429 "quota exhausted" solo 12:15Z (shadow, ~4 s); 20 timeout totali sulla giornata (11 tra 15:00 e 15:59, 5 off-hours).
- FinBERT fallback: 4/269 = 1,5% (in senso stretto); fallback totale 117/269 = 43,5%.
- Worker restart: nessuno rilevato. SoftTimeLimit: 1 (15:49:53Z).
- Telegram: polling con 5 `Connection reset by peer`; 1 sendMessage 400.
